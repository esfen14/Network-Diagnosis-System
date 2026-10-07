"""Read-only guards: Nagios Core's own config, service counts, app revision, status feed."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path
from typing import Any

from .common import BlockedError, HarnessError

SERVER_DIR = Path(__file__).resolve().parents[4]


def sha256_of(path: Path) -> str:
    """Return the SHA-256 of a file, or raise a Blocked error when it cannot be read."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise BlockedError(f"Cannot read {path}: {exc.strerror}") from exc


def localhost_config_path(config: dict[str, Any]) -> Path:
    """The Nagios Core server's own config: nagios.localhost_config, else objects/localhost.cfg."""
    nagios = config["nagios"]
    configured = nagios.get("localhost_config")
    if configured:
        return Path(configured)
    return Path(nagios["main_config"]).parent / "objects" / "localhost.cfg"


def record_localhost_hash(config: dict[str, Any], run_dir: Path) -> str:
    """Store the baseline hash once per run; Pinpoint must never change this file (O-6)."""
    target = run_dir / "evidence" / "localhost-cfg.sha256"
    if target.exists():
        return target.read_text(encoding="utf-8").split()[0]
    digest = sha256_of(localhost_config_path(config))
    target.write_text(f"{digest}\n", encoding="utf-8")
    return digest


def assert_localhost_unchanged(config: dict[str, Any], run_dir: Path) -> str:
    """Fail the run when localhost.cfg differs from the recorded baseline."""
    baseline = record_localhost_hash(config, run_dir)
    current = sha256_of(localhost_config_path(config))
    if current != baseline:
        raise HarnessError("localhost.cfg changed during the run; Pinpoint must leave Nagios Core's own checks alone.")
    return current


def count_services(hosts_config: Path) -> int:
    """Count `define service` blocks in the generated hosts.cfg."""
    try:
        text = hosts_config.read_text(encoding="utf-8")
    except OSError as exc:
        raise BlockedError(f"Cannot read {hosts_config}: {exc.strerror}") from exc
    return len(re.findall(r"^\s*service_description\s", text, re.M))


def migration_heads(versions_dir: Path | None = None) -> set[str]:
    """Return the Alembic head revisions of the checked-out migrations."""
    versions_dir = versions_dir or SERVER_DIR / "migrations" / "versions"
    revisions, parents = set(), set()
    for path in versions_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        found = re.search(r"^revision\s*=\s*['\"]([0-9a-f]+)['\"]", text, re.M)
        if not found:
            continue
        revisions.add(found.group(1))
        down = re.search(r"^down_revision\s*=\s*(.+)$", text, re.M)
        if down:
            parents.update(re.findall(r"['\"]([0-9a-f]+)['\"]", down.group(1)))
    return revisions - parents


def database_revision(system_db: Path) -> str | None:
    """Return the Alembic revision recorded in the app's system database."""
    try:
        connection = sqlite3.connect(f"file:{system_db}?mode=ro", uri=True)
        try:
            row = connection.execute("select version_num from alembic_version").fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return None
    return row[0] if row else None


def app_revision_matches(system_db: Path, versions_dir: Path | None = None) -> bool:
    """True when the app's database is at the checkout's single migration head."""
    heads = migration_heads(versions_dir)
    return len(heads) == 1 and database_revision(system_db) in heads


def status_feed_state(services: list[dict[str, Any]]) -> bool | None:
    """
    Whether Pinpoint receives Nagios check results: True when any service has a
    last check, False when services exist but none has one, None when there is
    nothing to judge yet.
    """
    if not services:
        return None
    return any(item.get("last_check") for item in services)
