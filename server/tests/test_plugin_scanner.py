"""
tests/test_plugin_scanner.py — Tests for the Plugin Manager filesystem
scanner (Phase 2).

Covers:
  - scanner.py: scan_plugin_directory() / sync_plugin_inventory() logic
  - manager.py routes: POST /api/plugin/scan, GET /api/plugin/scan/status

CROSS-PLATFORM NOTE: an earlier version of this file tried to fake real
OS-level executable permissions (chmod +x on POSIX, a .bat extension on
Windows) so scan_plugin_directory's actual filesystem/permission-bit
logic would run unmocked. That turned out to be unreliable on Windows:
os.scandir()'s DirEntry.stat() does not consistently reproduce the
same extension-based execute-bit guessing that Windows documents for
a plain os.stat() call, so is-this-executable came back False
regardless of the .bat trick.

Rather than continuing to chase undocumented, version-dependent
Windows internals, this file instead patches
app.api.plugin.scanner._is_executable directly wherever "is this file
executable" matters for a test. This makes the classification/sync
logic tests fully OS-independent and deterministic. The one thing this
approach does NOT exercise is _is_executable's own real POSIX-bit
logic — that's covered separately by the small Linux-only class at the
bottom of this file (skipped on non-Linux), which uses real chmod
against real files, matching the actual deployment target exactly.
"""
import os
import platform
import stat
from unittest.mock import patch, MagicMock

import pytest

from app.plugin_models import Plugin, PluginVersion, PluginType, PluginSource, PluginStatus
from app.api.plugin.scanner import scan_plugin_directory, sync_plugin_inventory


# ─── helpers ──────────────────────────────────────────────────────────────────

def _write_fake_plugin(directory, name):
    """
    Writes a placeholder file. Content is irrelevant — subprocess.run
    is mocked in every test below, and _is_executable is patched
    directly rather than relying on real file permissions.
    """
    path = os.path.join(directory, name)
    with open(path, "w") as f:
        f.write("placeholder\n")
    return path


def _mock_completed_process(output):
    """A fake subprocess.CompletedProcess for mocking subprocess.run."""
    m = MagicMock()
    m.stdout = output or ""
    m.stderr = ""
    m.returncode = 0
    return m


# All tests in this section run with every file treated as executable
# (the realistic case for a directory that's genuinely full of Nagios
# plugins) unless a specific test overrides it.
_ALWAYS_EXECUTABLE = patch("app.api.plugin.scanner._is_executable", return_value=True)


# ─── scan_plugin_directory ────────────────────────────────────────────────────

class TestScanPluginDirectory:
    def test_detects_executable_files(self, tmp_path):
        _write_fake_plugin(tmp_path, "check_ping")
        _write_fake_plugin(tmp_path, "check_disk")

        with _ALWAYS_EXECUTABLE, \
             patch("app.api.plugin.scanner.subprocess.run",
                   return_value=_mock_completed_process("v2.4.12")):
            results = scan_plugin_directory(str(tmp_path))

        names = sorted(r.name for r in results)
        assert names == ["check_disk", "check_ping"]

    def test_skips_non_executable_files(self, tmp_path):
        _write_fake_plugin(tmp_path, "check_ping")
        _write_fake_plugin(tmp_path, "README")

        def fake_is_executable(entry, entry_stat):
            return entry.name == "check_ping"

        with patch("app.api.plugin.scanner._is_executable", side_effect=fake_is_executable), \
             patch("app.api.plugin.scanner.subprocess.run",
                   return_value=_mock_completed_process("v2.4.12")):
            results = scan_plugin_directory(str(tmp_path))

        names = [r.name for r in results]
        assert "check_ping" in names
        assert "README" not in names

    def test_extracts_version_when_supported(self, tmp_path):
        _write_fake_plugin(tmp_path, "check_http")

        with _ALWAYS_EXECUTABLE, \
             patch("app.api.plugin.scanner.subprocess.run",
                   return_value=_mock_completed_process("check_http v2.4.12 (nagios-plugins 2.4.12)")):
            results = scan_plugin_directory(str(tmp_path))

        assert results[0].version == "2.4.12"
        assert "check_http" in results[0].version_raw_output

    def test_version_none_when_unsupported(self, tmp_path):
        _write_fake_plugin(tmp_path, "check_weird")

        with _ALWAYS_EXECUTABLE, \
             patch("app.api.plugin.scanner.subprocess.run",
                   return_value=_mock_completed_process("")):
            results = scan_plugin_directory(str(tmp_path))

        assert results[0].version is None

    def test_missing_directory_raises(self, tmp_path):
        missing = str(tmp_path / "does_not_exist")
        with pytest.raises(FileNotFoundError):
            scan_plugin_directory(missing)

    def test_file_info_populated(self, tmp_path):
        _write_fake_plugin(tmp_path, "check_ping")

        with _ALWAYS_EXECUTABLE, \
             patch("app.api.plugin.scanner.subprocess.run",
                   return_value=_mock_completed_process("v2.4.12")):
            results = scan_plugin_directory(str(tmp_path))

        r = results[0]
        assert r.path == str(tmp_path / "check_ping")
        assert r.size > 0
        assert r.is_executable is True
        assert r.modified_at is not None


# ─── sync_plugin_inventory ────────────────────────────────────────────────────

class TestSyncPluginInventory:
    def test_initial_seed_marks_baseline(self, db_session, tmp_path):
        """When the Plugin table is empty, everything found is BASELINE_ISO."""
        _write_fake_plugin(tmp_path, "check_ping")

        with _ALWAYS_EXECUTABLE, \
             patch("app.api.plugin.scanner.subprocess.run",
                   return_value=_mock_completed_process("check_ping v2.4.12")):
            scan_results = scan_plugin_directory(str(tmp_path))

        summary = sync_plugin_inventory(scan_results)

        assert summary == {"created": 1, "updated": 0, "unchanged": 0}

        plugin = db_session.session.execute(
            db_session.select(Plugin).where(Plugin.Name == "check_ping")
        ).scalar_one()
        assert plugin.Source == PluginSource.BASELINE_ISO
        assert plugin.Plugin_Type == PluginType.NAGIOS
        assert plugin.Current_Version == "2.4.12"

        version = db_session.session.execute(
            db_session.select(PluginVersion).where(PluginVersion.PluginID == plugin.PluginID)
        ).scalar_one()
        assert version.Is_Current is True
        assert version.Version == "2.4.12"

    def test_later_scan_marks_new_plugin_administrator_added(self, db_session, tmp_path):
        """Once the table is non-empty, a newly-found plugin is ADMINISTRATOR_ADDED."""
        _write_fake_plugin(tmp_path, "check_ping")
        with _ALWAYS_EXECUTABLE, \
             patch("app.api.plugin.scanner.subprocess.run",
                   return_value=_mock_completed_process("check_ping v2.4.12")):
            sync_plugin_inventory(scan_plugin_directory(str(tmp_path)))

        _write_fake_plugin(tmp_path, "check_snmp")
        with _ALWAYS_EXECUTABLE, \
             patch("app.api.plugin.scanner.subprocess.run",
                   return_value=_mock_completed_process("check_snmp v2.4.12")):
            summary = sync_plugin_inventory(scan_plugin_directory(str(tmp_path)))

        assert summary["created"] == 1
        assert summary["unchanged"] == 1  # check_ping, nothing changed

        new_plugin = db_session.session.execute(
            db_session.select(Plugin).where(Plugin.Name == "check_snmp")
        ).scalar_one()
        assert new_plugin.Source == PluginSource.ADMINISTRATOR_ADDED

    def test_version_change_flags_update_available_without_overwriting(self, db_session, tmp_path):
        """A re-scan detecting a different known version doesn't silently apply it."""
        _write_fake_plugin(tmp_path, "check_ping")
        with _ALWAYS_EXECUTABLE, \
             patch("app.api.plugin.scanner.subprocess.run",
                   return_value=_mock_completed_process("check_ping v2.4.12")):
            sync_plugin_inventory(scan_plugin_directory(str(tmp_path)))

        with _ALWAYS_EXECUTABLE, \
             patch("app.api.plugin.scanner.subprocess.run",
                   return_value=_mock_completed_process("check_ping v2.4.13")):
            summary = sync_plugin_inventory(scan_plugin_directory(str(tmp_path)))

        assert summary["updated"] == 1

        plugin = db_session.session.execute(
            db_session.select(Plugin).where(Plugin.Name == "check_ping")
        ).scalar_one()
        assert plugin.Current_Version == "2.4.12"
        assert plugin.Status == PluginStatus.UPDATE_AVAILABLE

    def test_filling_in_previously_unknown_version_is_not_flagged(self, db_session, tmp_path):
        """Going from no known version -> a known version isn't treated as an update."""
        _write_fake_plugin(tmp_path, "check_weird")
        with _ALWAYS_EXECUTABLE, \
             patch("app.api.plugin.scanner.subprocess.run",
                   return_value=_mock_completed_process("")):
            sync_plugin_inventory(scan_plugin_directory(str(tmp_path)))

        plugin = db_session.session.execute(
            db_session.select(Plugin).where(Plugin.Name == "check_weird")
        ).scalar_one()
        assert plugin.Current_Version is None
        assert plugin.Status == PluginStatus.READY

        with _ALWAYS_EXECUTABLE, \
             patch("app.api.plugin.scanner.subprocess.run",
                   return_value=_mock_completed_process("check_weird v1.0.0")):
            summary = sync_plugin_inventory(scan_plugin_directory(str(tmp_path)))

        assert summary["updated"] == 1

        db_session.session.refresh(plugin)
        assert plugin.Current_Version == "1.0.0"
        assert plugin.Status == PluginStatus.READY  # not UPDATE_AVAILABLE

    def test_unchanged_plugin_reported_as_unchanged(self, db_session, tmp_path):
        _write_fake_plugin(tmp_path, "check_ping")
        with _ALWAYS_EXECUTABLE, \
             patch("app.api.plugin.scanner.subprocess.run",
                   return_value=_mock_completed_process("check_ping v2.4.12")):
            sync_plugin_inventory(scan_plugin_directory(str(tmp_path)))
            summary = sync_plugin_inventory(scan_plugin_directory(str(tmp_path)))

        assert summary == {"created": 0, "updated": 0, "unchanged": 1}


# ─── _is_executable: real permission bits, Linux only ─────────────────────────

@pytest.mark.skipif(
    platform.system() != "Linux",
    reason="Exercises real POSIX execute-permission bits; production target "
           "is the Linux Nagios appliance, so this is validated for real "
           "only there. Cross-platform logic tests above cover the rest of "
           "scan_plugin_directory via a mocked _is_executable instead.",
)
class TestIsExecutableRealPermissions:
    def test_chmod_executable_file_is_detected(self, tmp_path):
        path = _write_fake_plugin(tmp_path, "check_ping")
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        with patch("app.api.plugin.scanner.subprocess.run",
                    return_value=_mock_completed_process("v2.4.12")):
            results = scan_plugin_directory(str(tmp_path))

        assert [r.name for r in results] == ["check_ping"]

    def test_non_executable_file_is_skipped(self, tmp_path):
        path = _write_fake_plugin(tmp_path, "README")
        mode = os.stat(path).st_mode
        os.chmod(path, mode & ~stat.S_IXUSR & ~stat.S_IXGRP & ~stat.S_IXOTH)

        results = scan_plugin_directory(str(tmp_path))

        assert results == []


# ─── routes: POST /api/plugin/scan, GET /api/plugin/scan/status ──────────────

class TestPluginScanStart:
    def test_scan_start_requires_login(self, client, db_session):
        resp = client.post("/api/plugin/scan")
        assert resp.status_code in (401, 302)

    def test_scan_start_requires_permission(self, limited_client, db_session):
        resp = limited_client.post("/api/plugin/scan")
        assert resp.status_code == 403

    def test_scan_start_success(self, logged_in_client, db_session, admin_user):
        with patch("app.api.plugin.manager.threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread.is_alive.return_value = False
            mock_thread_cls.return_value = mock_thread

            import app.api.plugin.manager as manager_module
            manager_module.scan_thread = None

            resp = logged_in_client.post("/api/plugin/scan")

        assert resp.status_code == 202
        data = resp.get_json()
        assert "message" in data

    def test_scan_start_already_running(self, logged_in_client, db_session):
        import app.api.plugin.manager as manager_module

        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        manager_module.scan_thread = mock_thread

        try:
            resp = logged_in_client.post("/api/plugin/scan")
            assert resp.status_code == 400
            data = resp.get_json()
            assert "message" in data
        finally:
            manager_module.scan_thread = None


class TestPluginScanStatusRoute:
    def test_scan_status_no_records(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/plugin/scan/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "message" in data

    def test_scan_status_requires_login(self, client, db_session):
        resp = client.get("/api/plugin/scan/status")
        assert resp.status_code in (401, 302)
