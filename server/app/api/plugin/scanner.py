"""
scanner.py — Plugin Manager filesystem scanner (Phase 2).

Detects Nagios plugin executables under NAGIOS_PLUGIN_DIR and syncs
what's found into the Plugin/PluginVersion tables (plugin_models.py,
Phase 1).

ARCHITECTURE: Nagios and the PinPoint Flask app run on the SAME
machine (confirmed — an earlier draft of this module assumed a
separate machine reached over SSH; that assumption was wrong and has
been discarded). Detection here is plain local filesystem access
(os.scandir) — no network calls, no paramiko.

IN SCOPE for this phase:
    - Detect plugin executables under NAGIOS_PLUGIN_DIR.
    - Determine executable state via os.access(path, os.X_OK).
    - Determine version by executing every plugin with --version,
      every scan (not just newly-discovered ones) — best-effort: a
      plugin that doesn't support --version, times out, or errors is
      still registered, just with Version=None.
    - Classify PluginSource: if this is the very first scan ever
      (Plugin table is empty when the scan starts), everything found
      is BASELINE_ISO. On every later scan, any newly-discovered
      plugin is ADMINISTRATOR_ADDED.
    - If a re-scan finds an existing plugin's version has changed,
      DO NOT overwrite Current_Version automatically — flag
      Status=UPDATE_AVAILABLE and leave the actual update decision to
      the administrator (Phase 9 territory).
    - Add/update Plugin + PluginVersion rows.

DELIBERATELY NOT in scope for this phase:
    - PluginHistory is not written here (that requires a real
      ActivityLog/UserID tied to an admin action — see manager.py for
      where scan-level logging happens instead). Per-plugin history
      wiring belongs to Phase 11.
    - Detecting plugins that were removed from disk since the last
      scan — Phase 12's "Synchronize plugin inventory" task. This
      module only adds/updates.
    - Any Nagios monitoring-config or monitored-device wiring — this
      only populates Plugin Manager's own inventory tables (see
      architectural rules 5/8: plugins are never installed onto
      monitored devices, and "installed" is not "active").
"""
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa

from app import db
from app.plugin_models import Plugin, PluginVersion, PluginType, PluginSource, PluginStatus


# Confirmed from the ISO's install-nagios-plugins.sh / install-nagios-core.sh:
# both build with no --prefix, so the default install path is used.
NAGIOS_PLUGIN_DIR = "/usr/local/nagios/libexec/"

VERSION_CHECK_TIMEOUT_SECONDS = 5

# Loosely matches common Nagios plugin --version output, e.g.:
#   "check_ping v2.4.12 (nagios-plugins 2.4.12)"
#   "check_disk (nagios-plugins 2.4.12)"
_VERSION_PATTERN = re.compile(r'(\d+\.\d+(?:\.\d+)?)')


@dataclass
class ScannedPlugin:
    name: str
    path: str
    size: int
    modified_at: datetime
    is_executable: bool
    version: Optional[str]
    version_raw_output: Optional[str]


def _extract_version(plugin_path):
    """
    Best-effort: run `<plugin_path> --version` locally and try to
    parse a version number out of the combined stdout+stderr. Never
    raises — any failure (unsupported flag, non-zero exit, timeout,
    unparsable output) just returns (None, None).
    """
    try:
        result = subprocess.run(
            [plugin_path, "--version"],
            capture_output=True,
            text=True,
            timeout=VERSION_CHECK_TIMEOUT_SECONDS,
        )
    except Exception:
        return None, None

    raw_output = ((result.stdout or "") + (result.stderr or "")).strip()

    if not raw_output:
        return None, None

    match = _VERSION_PATTERN.search(raw_output)
    version = match.group(1) if match else None

    return version, raw_output


def _is_executable(entry, entry_stat):
    """
    Whether a scanned filesystem entry should be treated as a plugin
    executable. Separated out from scan_plugin_directory specifically
    so tests can patch this single function directly, rather than
    trying to fake real OS-level executable-permission bits — which
    turned out to behave inconsistently across platforms in practice
    (Windows' os.scandir()/DirEntry.stat() does not reliably reproduce
    the same extension-based execute-bit guessing that a plain
    os.stat() call does, contrary to Windows' own documented
    behavior). Production code path is unaffected by this — on Linux
    (the actual deployment target), this checks real POSIX permission
    bits exactly as before.
    """
    return bool(entry_stat.st_mode & stat.S_IXUSR) and os.access(entry.path, os.X_OK)


def scan_plugin_directory(directory=NAGIOS_PLUGIN_DIR):
    """
    Detects every plugin executable under `directory`. Pure detection
    — does not touch the database.

    Args:
        directory: local directory to scan (defaults to
            NAGIOS_PLUGIN_DIR).

    Returns:
        list[ScannedPlugin]

    Raises:
        FileNotFoundError: if `directory` doesn't exist. Callers
            decide how to surface this (manager.py turns it into a
            failed PluginScanStatus).
    """
    results = []

    with os.scandir(directory) as it:
        for entry in it:
            if not entry.is_file(follow_symlinks=True):
                continue

            entry_stat = entry.stat()
            is_executable = _is_executable(entry, entry_stat)

            if not is_executable:
                continue

            version, raw_output = _extract_version(entry.path)

            results.append(ScannedPlugin(
                name=entry.name,
                path=entry.path,
                size=entry_stat.st_size,
                modified_at=datetime.fromtimestamp(entry_stat.st_mtime, tz=timezone.utc),
                is_executable=is_executable,
                version=version,
                version_raw_output=raw_output,
            ))

    return results


def sync_plugin_inventory(scan_results):
    """
    Upserts scan_results (from scan_plugin_directory()) into the
    Plugin / PluginVersion tables.

    PluginSource rule: if the Plugin table has zero rows at the start
    of this call, this is treated as the initial seed — every scanned
    plugin becomes BASELINE_ISO. Otherwise, any plugin not already in
    the table is ADMINISTRATOR_ADDED.

    Version-change rule: if an already-registered plugin's detected
    version differs from Current_Version, Current_Version is NOT
    overwritten automatically. Instead, Status is set to
    UPDATE_AVAILABLE so an administrator can decide. (If a plugin
    previously had no known version and one is now detected, that's
    just filling in missing data, not an "update" — Status is left
    alone in that case.)

    Does NOT delete/deregister plugins that are in the DB but weren't
    found in scan_results (see module docstring — Phase 12).
    Does NOT write PluginHistory (see module docstring — Phase 11).

    Returns:
        dict: {"created": int, "updated": int, "unchanged": int}
    """
    is_initial_seed = db.session.scalar(
        sa.select(sa.func.count()).select_from(Plugin)
    ) == 0

    created = 0
    updated = 0
    unchanged = 0

    for scanned in scan_results:
        plugin = db.session.scalar(
            sa.select(Plugin).where(Plugin.Name == scanned.name)
        )

        if plugin is None:
            plugin = Plugin(
                Name=scanned.name,
                Plugin_Type=PluginType.NAGIOS,
                Source=PluginSource.BASELINE_ISO if is_initial_seed else PluginSource.ADMINISTRATOR_ADDED,
                Status=PluginStatus.READY,
                Executable_Path=scanned.path,
                Current_Version=scanned.version,
            )
            db.session.add(plugin)
            db.session.flush()  # get plugin.PluginID

            if scanned.version:
                db.session.add(PluginVersion(
                    PluginID=plugin.PluginID,
                    Version=scanned.version,
                    Executable_Path=scanned.path,
                    Is_Current=True,
                ))

            created += 1
            continue

        changed = False

        if plugin.Executable_Path != scanned.path:
            plugin.Executable_Path = scanned.path
            changed = True

        if scanned.version and plugin.Current_Version and scanned.version != plugin.Current_Version:
            # Known version changed to a different known version:
            # flag for admin review, don't auto-apply.
            plugin.Status = PluginStatus.UPDATE_AVAILABLE
            changed = True
        elif scanned.version and not plugin.Current_Version:
            # Filling in a previously-unknown version — not an "update".
            plugin.Current_Version = scanned.version
            db.session.add(PluginVersion(
                PluginID=plugin.PluginID,
                Version=scanned.version,
                Executable_Path=scanned.path,
                Is_Current=True,
            ))
            changed = True

        if changed:
            updated += 1
        else:
            unchanged += 1

    db.session.commit()

    return {"created": created, "updated": updated, "unchanged": unchanged}
