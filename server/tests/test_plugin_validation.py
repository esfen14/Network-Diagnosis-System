"""
tests/test_plugin_validation.py — Tests for Phase 7 (Validation):
plugin_validator.py's three checks + the POST /plugin/<id>/validate
route and its Plugin.Status transitions.

CROSS-PLATFORM NOTE: an earlier version of this file relied on real
os.chmod()'d files to exercise permission/execution logic on any OS.
That's the same mistake already fixed once in test_plugin_scanner.py:
Windows' os.chmod()/os.stat() do not produce real POSIX mode bits —
chmod(0o777) and chmod(0o755) can both be reported back as the same
synthetic value (observed directly: a real Windows run reported '0666'
for a file just chmod'd to 0o777). So this file now mocks at the
function boundary (check_executable/check_permissions/check_execution,
or subprocess.run) for every test that's really about LOGIC, and keeps
a small dedicated Linux-only class at the bottom for exercising real
POSIX permission bits for real — matching the pattern already
established and working in test_plugin_scanner.py.
"""
import os
import platform
from unittest.mock import patch, MagicMock

import pytest

from app.plugin_models import Plugin, PluginType, PluginSource, PluginStatus, PluginHistory
from app.api.plugin.plugin_validator import (
    check_executable, check_permissions, check_execution, validate_plugin_executable,
)


def _make_plugin(db_session, name, executable_path=None, status=PluginStatus.READY):
    plugin = Plugin(
        Name=name, Plugin_Type=PluginType.NAGIOS, Source=PluginSource.BASELINE_ISO,
        Status=status, Executable_Path=executable_path,
    )
    db_session.session.add(plugin)
    db_session.session.commit()
    return plugin


def _mock_completed_process(returncode, stdout="", stderr=""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def _mock_check_result(passed, **extra):
    return {"passed": passed, "message": "mocked", **extra}


def _mock_validate_result(is_valid):
    return {
        "is_valid": is_valid,
        "checks": {
            "executable": _mock_check_result(is_valid),
            "permissions": _mock_check_result(is_valid, mode="0755", world_writable=not is_valid),
            "execution": _mock_check_result(is_valid, exit_code=0, output=""),
        },
    }


# ─── check_executable (existence/is-file are OS-agnostic; execute bit is mocked) ──

class TestCheckExecutable:
    def test_no_path_recorded(self):
        result = check_executable(None)
        assert result["passed"] is False

    def test_missing_file(self, tmp_path):
        result = check_executable(str(tmp_path / "does_not_exist"))
        assert result["passed"] is False

    def test_directory_not_file(self, tmp_path):
        result = check_executable(str(tmp_path))
        assert result["passed"] is False

    def test_non_executable_file(self, tmp_path):
        path = tmp_path / "check_x"
        path.write_text("placeholder")
        with patch("app.api.plugin.plugin_validator.os.access", return_value=False):
            result = check_executable(str(path))
        assert result["passed"] is False

    def test_valid_executable(self, tmp_path):
        path = tmp_path / "check_x"
        path.write_text("placeholder")
        with patch("app.api.plugin.plugin_validator.os.access", return_value=True):
            result = check_executable(str(path))
        assert result["passed"] is True


# ─── check_permissions (mocked os.stat — real chmod isn't portable) ───────────

class TestCheckPermissions:
    def test_missing_file(self, tmp_path):
        result = check_permissions(str(tmp_path / "does_not_exist"))
        assert result["passed"] is False

    def test_normal_permissions_pass(self, tmp_path):
        path = tmp_path / "check_x"
        path.write_text("x")
        fake_stat = MagicMock(st_mode=0o100755)  # regular file, rwxr-xr-x
        with patch("app.api.plugin.plugin_validator.os.stat", return_value=fake_stat):
            result = check_permissions(str(path))
        assert result["passed"] is True
        assert result["world_writable"] is False
        assert result["mode"] == "0755"

    def test_world_writable_fails(self, tmp_path):
        path = tmp_path / "check_x"
        path.write_text("x")
        fake_stat = MagicMock(st_mode=0o100777)  # regular file, rwxrwxrwx
        with patch("app.api.plugin.plugin_validator.os.stat", return_value=fake_stat):
            result = check_permissions(str(path))
        assert result["passed"] is False
        assert result["world_writable"] is True
        assert result["mode"] == "0777"


# ─── check_execution (subprocess.run mocked — real shell scripts aren't portable) ──

class TestCheckExecution:
    def test_missing_file(self, tmp_path):
        result = check_execution(str(tmp_path / "does_not_exist"))
        assert result["passed"] is False

    def test_successful_execution(self, tmp_path):
        path = tmp_path / "check_x"
        path.write_text("x")
        with patch("app.api.plugin.plugin_validator.subprocess.run",
                    return_value=_mock_completed_process(0, stdout="check_x v1.0.0")):
            result = check_execution(str(path))
        assert result["passed"] is True
        assert result["exit_code"] == 0
        assert "check_x v1.0.0" in result["output"]

    def test_nonzero_exit_still_passes(self, tmp_path):
        """A plugin returning WARNING/CRITICAL on --version shouldn't be
        treated as a validation failure — only launch failures should."""
        path = tmp_path / "check_x"
        path.write_text("x")
        with patch("app.api.plugin.plugin_validator.subprocess.run",
                    return_value=_mock_completed_process(2, stdout="some output")):
            result = check_execution(str(path))
        assert result["passed"] is True
        assert result["exit_code"] == 2


# ─── validate_plugin_executable (combined, sub-functions mocked) ──────────────

class TestValidatePluginExecutable:
    def test_all_checks_pass(self):
        with patch("app.api.plugin.plugin_validator.check_executable", return_value=_mock_check_result(True)), \
             patch("app.api.plugin.plugin_validator.check_permissions",
                   return_value=_mock_check_result(True, mode="0755", world_writable=False)), \
             patch("app.api.plugin.plugin_validator.check_execution",
                   return_value=_mock_check_result(True, exit_code=0, output="v1.0")):
            result = validate_plugin_executable("/fake/path")
        assert result["is_valid"] is True

    def test_world_writable_fails_overall(self):
        with patch("app.api.plugin.plugin_validator.check_executable", return_value=_mock_check_result(True)), \
             patch("app.api.plugin.plugin_validator.check_permissions",
                   return_value=_mock_check_result(False, mode="0777", world_writable=True)), \
             patch("app.api.plugin.plugin_validator.check_execution",
                   return_value=_mock_check_result(True, exit_code=0, output="")):
            result = validate_plugin_executable("/fake/path")
        assert result["is_valid"] is False
        assert result["checks"]["permissions"]["passed"] is False
        assert result["checks"]["executable"]["passed"] is True  # unaffected

    def test_missing_file_fails_all_three(self):
        with patch("app.api.plugin.plugin_validator.check_executable", return_value=_mock_check_result(False)), \
             patch("app.api.plugin.plugin_validator.check_permissions",
                   return_value=_mock_check_result(False, mode=None, world_writable=None)), \
             patch("app.api.plugin.plugin_validator.check_execution",
                   return_value=_mock_check_result(False, exit_code=None, output="")):
            result = validate_plugin_executable("/fake/path")
        assert result["is_valid"] is False
        assert all(not c["passed"] for c in result["checks"].values())


# ─── POST /plugin/<id>/validate (validate_plugin_executable mocked at the service boundary) ──

class TestValidatePluginRoute:
    def test_requires_login(self, client, db_session):
        plugin = _make_plugin(db_session, "check_x")
        resp = client.post(f"/api/plugin/{plugin.PluginID}/validate")
        assert resp.status_code in (401, 302)

    def test_requires_permission(self, limited_client, db_session):
        plugin = _make_plugin(db_session, "check_x")
        resp = limited_client.post(f"/api/plugin/{plugin.PluginID}/validate")
        assert resp.status_code == 403

    def test_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.post("/api/plugin/999999/validate")
        assert resp.status_code == 404

    def test_valid_plugin_stays_ready(self, logged_in_client, db_session):
        plugin = _make_plugin(db_session, "check_good", executable_path="/fake/path", status=PluginStatus.READY)

        with patch("app.api.plugin.service.validate_plugin_executable", return_value=_mock_validate_result(True)):
            resp = logged_in_client.post(f"/api/plugin/{plugin.PluginID}/validate")

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["is_valid"] is True
        assert data["status"] == "Ready"

        db_session.session.refresh(plugin)
        assert plugin.Status == PluginStatus.READY

    def test_invalid_plugin_sets_validation_failed(self, logged_in_client, db_session):
        plugin = _make_plugin(db_session, "check_bad", executable_path="/fake/path", status=PluginStatus.READY)

        with patch("app.api.plugin.service.validate_plugin_executable", return_value=_mock_validate_result(False)):
            resp = logged_in_client.post(f"/api/plugin/{plugin.PluginID}/validate")

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["is_valid"] is False
        assert data["status"] == "Validation Failed"

        db_session.session.refresh(plugin)
        assert plugin.Status == PluginStatus.VALIDATION_FAILED

    def test_passing_resets_previously_failed_plugin(self, logged_in_client, db_session):
        plugin = _make_plugin(db_session, "check_good", executable_path="/fake/path",
                               status=PluginStatus.VALIDATION_FAILED)

        with patch("app.api.plugin.service.validate_plugin_executable", return_value=_mock_validate_result(True)):
            resp = logged_in_client.post(f"/api/plugin/{plugin.PluginID}/validate")

        assert resp.status_code == 200
        db_session.session.refresh(plugin)
        assert plugin.Status == PluginStatus.READY

    def test_passing_does_not_downgrade_enabled(self, logged_in_client, db_session):
        """Validating an already-ENABLED plugin shouldn't reset it to READY."""
        plugin = _make_plugin(db_session, "check_good", executable_path="/fake/path", status=PluginStatus.ENABLED)

        with patch("app.api.plugin.service.validate_plugin_executable", return_value=_mock_validate_result(True)):
            resp = logged_in_client.post(f"/api/plugin/{plugin.PluginID}/validate")

        assert resp.status_code == 200
        db_session.session.refresh(plugin)
        assert plugin.Status == PluginStatus.ENABLED

    def test_records_history(self, logged_in_client, db_session):
        plugin = _make_plugin(db_session, "check_good", executable_path="/fake/path", status=PluginStatus.READY)

        with patch("app.api.plugin.service.validate_plugin_executable", return_value=_mock_validate_result(True)):
            logged_in_client.post(f"/api/plugin/{plugin.PluginID}/validate")

        history = db_session.session.execute(
            db_session.select(PluginHistory).where(PluginHistory.PluginID == plugin.PluginID)
        ).scalar_one()
        assert history.Action.value == "Validate"
        assert history.Result.value == "Success"


# ─── Real POSIX permission bits, Linux only ────────────────────────────────────

@pytest.mark.skipif(
    platform.system() != "Linux",
    reason="Exercises real POSIX permission bits (chmod) and real shell-script "
           "execution; production target is the Linux Nagios appliance, so "
           "this is validated for real only there. Cross-platform logic is "
           "covered above via mocking instead.",
)
class TestRealPermissionChecks:
    def _write_script(self, path, content, mode, exit_code=0):
        script = f"#!/bin/sh\necho \"{content}\"\nexit {exit_code}\n"
        with open(path, "w") as f:
            f.write(script)
        os.chmod(path, mode)
        return str(path)

    def test_real_executable_passes(self, tmp_path):
        path = self._write_script(tmp_path / "check_good", "v1.0", mode=0o755)
        assert check_executable(path)["passed"] is True

    def test_real_non_executable_fails(self, tmp_path):
        path = self._write_script(tmp_path / "check_bad", "v1.0", mode=0o644)
        assert check_executable(path)["passed"] is False

    def test_real_normal_permissions_pass(self, tmp_path):
        path = self._write_script(tmp_path / "check_good", "v1.0", mode=0o755)
        result = check_permissions(path)
        assert result["passed"] is True
        assert result["world_writable"] is False

    def test_real_world_writable_fails(self, tmp_path):
        path = self._write_script(tmp_path / "check_bad", "v1.0", mode=0o777)
        result = check_permissions(path)
        assert result["passed"] is False
        assert result["world_writable"] is True

    def test_real_execution_succeeds(self, tmp_path):
        path = self._write_script(tmp_path / "check_good", "check_good v1.0.0", mode=0o755)
        result = check_execution(path)
        assert result["passed"] is True
        assert "check_good v1.0.0" in result["output"]

    def test_real_full_validation_passes(self, tmp_path):
        path = self._write_script(tmp_path / "check_good", "check_good v1.0.0", mode=0o755)
        result = validate_plugin_executable(path)
        assert result["is_valid"] is True
