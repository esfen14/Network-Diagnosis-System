"""
tests/test_plugin_custom.py — Tests for Phase 8 (Custom Plugins):
custom_plugin.py's file-staging/install logic + the 7 validation
checks + POST /plugin/custom's full atomic register-or-reject flow.

Uses a real temporary directory (tmp_path, patched in as
NAGIOS_PLUGIN_DIR) rather than mocking the filesystem layer — install/
staging is specifically about real file operations, so exercising it
for real is more meaningful here, same reasoning as
test_plugin_scanner.py's original design. Real files also work fine
cross-platform for this module specifically, since none of its checks
depend on POSIX-only permission bits (that's plugin_validator.py's
job, already covered in test_plugin_validation.py).
"""
import io
import json
import os
from contextlib import ExitStack
from unittest.mock import patch, MagicMock

import pytest

from app.plugin_models import Plugin, PluginVersion, PluginCommand, PluginDependency, PluginHistory
from app.api.plugin.custom_plugin import (
    stage_upload, check_name_collision, install_staged_file, cleanup_staging,
    InvalidFilenameError, UploadTooLargeError, NameCollisionError, MAX_UPLOAD_SIZE_BYTES,
)


def _mock_checks_pass(exit_code=0, output="check_x v1.0.0"):
    """
    Mocks the three plugin_validator.py checks (as imported into
    service.py) so file_detected/executable_permission/execution_test
    succeed regardless of platform. Same underlying fix already
    applied in test_plugin_scanner.py and test_plugin_validation.py:
    Windows' os.chmod()/os.stat() don't produce real POSIX mode bits,
    and Windows can't execute a #!/bin/sh script directly, so relying
    on real chmod'd shell scripts isn't portable.

    Patches at the SERVICE module level (app.api.plugin.service.
    check_executable, etc.) rather than patching os.stat/os.access
    directly: those are imported by name into service.py, so patching
    them there doesn't touch the shared os module object at all —
    patching os.stat directly on plugin_validator's os reference was
    tried first and rejected, since `import os` just binds a
    reference to the one shared os module, so that approach silently
    broke unrelated os.path.getsize() calls in custom_plugin.py too.

    exit_code lets test_bad_exit_code_fails_nagios_compatibility
    simulate a non-standard exit code while still passing the other
    two checks.
    """
    stack = ExitStack()
    stack.enter_context(patch(
        "app.api.plugin.service.check_executable",
        return_value={"passed": True, "message": "mocked"},
    ))
    stack.enter_context(patch(
        "app.api.plugin.service.check_permissions",
        return_value={"passed": True, "message": "mocked", "mode": "0755", "world_writable": False},
    ))
    stack.enter_context(patch(
        "app.api.plugin.service.check_execution",
        return_value={"passed": True, "message": "mocked", "exit_code": exit_code, "output": output},
    ))
    return stack


class FakeFileStorage:
    """Minimal stand-in for werkzeug's FileStorage, for unit-testing
    custom_plugin.py functions directly without going through a real
    HTTP request."""
    def __init__(self, filename, content):
        self.filename = filename
        self._content = content

    def save(self, path):
        with open(path, "wb") as f:
            f.write(self._content)


SCRIPT_CONTENT = b'#!/bin/sh\necho "check_x v1.0.0"\nexit 0\n'
BAD_EXIT_SCRIPT = b'#!/bin/sh\necho "weird"\nexit 127\n'


CHECK_DISPLAY_NAMES = {
    "file_detected": "Plugin file detected",
    "executable_permission": "Executable permission",
    "execution_test": "Plugin execution test",
    "command_definition": "Command definition detected",
    "metadata": "Metadata valid",
    "dependency_check": "Dependency check",
    "nagios_compatibility": "Nagios compatibility",
}


def _check(data, key):
    """Finds a check result in the response's checks array by its
    internal key (matches CHECK_DISPLAY_NAMES, mirroring
    service.py's CUSTOM_PLUGIN_CHECK_DISPLAY_NAMES)."""
    display_name = CHECK_DISPLAY_NAMES[key]
    return next(c for c in data["checks"] if c["name"] == display_name)


def _upload_data(filename="check_company.sh", content=SCRIPT_CONTENT, **fields):
    data = {
        "file": (io.BytesIO(content), filename),
        "name": "check_company",
        "command_name": "check_company",
        "command_definition": "check_company -H $HOSTADDRESS$",
    }
    data.update(fields)
    return data


# ─── custom_plugin.py: stage_upload ────────────────────────────────────────

class TestStageUpload:
    def test_stages_file_successfully(self):
        fs = FakeFileStorage("check_x.sh", SCRIPT_CONTENT)
        staged_path, safe_filename, staging_dir, checksum, size = stage_upload(fs)
        try:
            assert os.path.exists(staged_path)
            assert safe_filename == "check_x.sh"
            assert size == len(SCRIPT_CONTENT)
            assert len(checksum) == 64  # sha256 hex digest
            assert os.access(staged_path, os.X_OK)
        finally:
            cleanup_staging(staging_dir)

    def test_sanitizes_dangerous_filename(self):
        fs = FakeFileStorage("../../etc/cron.d/evil", SCRIPT_CONTENT)
        staged_path, safe_filename, staging_dir, checksum, size = stage_upload(fs)
        try:
            assert ".." not in safe_filename
            assert "/" not in safe_filename
        finally:
            cleanup_staging(staging_dir)

    def test_empty_filename_rejected(self):
        fs = FakeFileStorage("", SCRIPT_CONTENT)
        with pytest.raises(InvalidFilenameError):
            stage_upload(fs)

    def test_purely_path_traversal_filename_rejected(self):
        fs = FakeFileStorage("../../../..", SCRIPT_CONTENT)
        with pytest.raises(InvalidFilenameError):
            stage_upload(fs)

    def test_oversized_file_rejected(self):
        fs = FakeFileStorage("check_big.sh", b"x" * (MAX_UPLOAD_SIZE_BYTES + 1))
        with pytest.raises(UploadTooLargeError):
            stage_upload(fs)


# ─── custom_plugin.py: check_name_collision / install_staged_file ─────────

class TestNameCollisionAndInstall:
    def test_no_collision_when_absent(self, tmp_path):
        with patch("app.api.plugin.custom_plugin.get_plugin_dir", return_value=str(tmp_path)):
            check_name_collision("check_new.sh")  # should not raise

    def test_collision_when_present(self, tmp_path):
        (tmp_path / "check_existing.sh").write_text("x")
        with patch("app.api.plugin.custom_plugin.get_plugin_dir", return_value=str(tmp_path)):
            with pytest.raises(NameCollisionError):
                check_name_collision("check_existing.sh")

    def test_install_moves_file_into_target_dir(self, tmp_path):
        target_dir = tmp_path / "libexec"
        target_dir.mkdir()
        fs = FakeFileStorage("check_x.sh", SCRIPT_CONTENT)
        staged_path, safe_filename, staging_dir, checksum, size = stage_upload(fs)

        with patch("app.api.plugin.custom_plugin.get_plugin_dir", return_value=str(target_dir)):
            installed_path = install_staged_file(staged_path, safe_filename)

        assert os.path.exists(installed_path)
        assert installed_path == str(target_dir / "check_x.sh")
        assert not os.path.exists(staged_path)  # moved, not copied
        cleanup_staging(staging_dir)


# ─── POST /plugin/custom ────────────────────────────────────────────────────

class TestRegisterCustomPluginRoute:
    def test_requires_login(self, client, db_session):
        resp = client.post("/api/plugin/custom", data=_upload_data(), content_type="multipart/form-data")
        assert resp.status_code in (401, 302)

    def test_requires_permission(self, limited_client, db_session):
        resp = limited_client.post("/api/plugin/custom", data=_upload_data(), content_type="multipart/form-data")
        assert resp.status_code == 403

    def test_no_file_provided(self, logged_in_client, db_session):
        resp = logged_in_client.post("/api/plugin/custom", data={"name": "x"}, content_type="multipart/form-data")
        assert resp.status_code == 400

    def test_successful_registration(self, logged_in_client, db_session, tmp_path):
        with patch("app.api.plugin.custom_plugin.get_plugin_dir", return_value=str(tmp_path)), _mock_checks_pass():
            resp = logged_in_client.post(
                "/api/plugin/custom",
                data=_upload_data(name="check_success", command_name="check_success",
                                   command_definition="check_success -H $HOSTADDRESS$",
                                   version="2.0.0", plugin_type="Custom"),
                content_type="multipart/form-data",
            )

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["success"] is True
        assert data["plugin"]["name"] == "check_success"
        assert data["plugin"]["type"] == "Custom"
        assert all(c["passed"] for c in data["checks"])

        plugin = db_session.session.execute(
            db_session.select(Plugin).where(Plugin.Name == "check_success")
        ).scalar_one()
        assert plugin.Source.value == "Administrator Added"
        assert plugin.Current_Version == "2.0.0"
        assert os.path.exists(plugin.Executable_Path)

    def test_creates_version_command_and_history(self, logged_in_client, db_session, tmp_path):
        with patch("app.api.plugin.custom_plugin.get_plugin_dir", return_value=str(tmp_path)), _mock_checks_pass():
            logged_in_client.post(
                "/api/plugin/custom",
                data=_upload_data(name="check_full"),
                content_type="multipart/form-data",
            )

        plugin = db_session.session.execute(
            db_session.select(Plugin).where(Plugin.Name == "check_full")
        ).scalar_one()

        version = db_session.session.execute(
            db_session.select(PluginVersion).where(PluginVersion.PluginID == plugin.PluginID)
        ).scalar_one()
        assert version.Is_Current is True
        assert len(version.Checksum) == 64

        command = db_session.session.execute(
            db_session.select(PluginCommand).where(PluginCommand.PluginID == plugin.PluginID)
        ).scalar_one()
        assert command.Command_Name == "check_company"

        history = db_session.session.execute(
            db_session.select(PluginHistory).where(PluginHistory.PluginID == plugin.PluginID)
        ).scalar_one()
        assert history.Action.value == "Install"
        assert history.Result.value == "Success"

    def test_creates_dependencies(self, logged_in_client, db_session, tmp_path):
        with patch("app.api.plugin.custom_plugin.get_plugin_dir", return_value=str(tmp_path)), _mock_checks_pass():
            logged_in_client.post(
                "/api/plugin/custom",
                data=_upload_data(
                    name="check_deps",
                    dependencies=json.dumps([{"name": "net-snmp", "type": "Package"}]),
                ),
                content_type="multipart/form-data",
            )

        plugin = db_session.session.execute(
            db_session.select(Plugin).where(Plugin.Name == "check_deps")
        ).scalar_one()
        dep = db_session.session.execute(
            db_session.select(PluginDependency).where(PluginDependency.PluginID == plugin.PluginID)
        ).scalar_one()
        assert dep.Dependency_Name == "net-snmp"
        assert dep.Dependency_Type.value == "Package"

    def test_dangerous_command_fails_validation_no_persistence(self, logged_in_client, db_session, tmp_path):
        with patch("app.api.plugin.custom_plugin.get_plugin_dir", return_value=str(tmp_path)):
            resp = logged_in_client.post(
                "/api/plugin/custom",
                data=_upload_data(name="check_bad", command_definition="check_bad; rm -rf /"),
                content_type="multipart/form-data",
            )

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["success"] is False
        assert data["plugin"] is None
        assert _check(data, "command_definition")["passed"] is False

        # Nothing persisted, nothing installed.
        assert db_session.session.execute(
            db_session.select(Plugin).where(Plugin.Name == "check_bad")
        ).scalar_one_or_none() is None
        assert os.listdir(tmp_path) == []

    def test_bad_exit_code_fails_nagios_compatibility(self, logged_in_client, db_session, tmp_path):
        with patch("app.api.plugin.custom_plugin.get_plugin_dir", return_value=str(tmp_path)), \
             _mock_checks_pass(exit_code=127, output="weird"):
            resp = logged_in_client.post(
                "/api/plugin/custom",
                data=_upload_data(name="check_weird_exit", content=BAD_EXIT_SCRIPT),
                content_type="multipart/form-data",
            )

        data = resp.get_json()["data"]
        assert _check(data, "nagios_compatibility")["passed"] is False
        assert _check(data, "execution_test")["passed"] is True  # launched fine, just bad exit code
        assert data["success"] is False

    def test_missing_metadata_fails(self, logged_in_client, db_session, tmp_path):
        with patch("app.api.plugin.custom_plugin.get_plugin_dir", return_value=str(tmp_path)):
            resp = logged_in_client.post(
                "/api/plugin/custom",
                data=_upload_data(name="check_nometa", command_name="", command_definition=""),
                content_type="multipart/form-data",
            )

        data = resp.get_json()["data"]
        assert _check(data, "metadata")["passed"] is False
        assert data["success"] is False

    def test_invalid_dependency_type_fails(self, logged_in_client, db_session, tmp_path):
        with patch("app.api.plugin.custom_plugin.get_plugin_dir", return_value=str(tmp_path)):
            resp = logged_in_client.post(
                "/api/plugin/custom",
                data=_upload_data(
                    name="check_baddep",
                    dependencies=json.dumps([{"name": "x", "type": "NotARealType"}]),
                ),
                content_type="multipart/form-data",
            )

        data = resp.get_json()["data"]
        assert _check(data, "dependency_check")["passed"] is False
        assert data["success"] is False

    def test_malformed_dependencies_json_rejected(self, logged_in_client, db_session, tmp_path):
        with patch("app.api.plugin.custom_plugin.get_plugin_dir", return_value=str(tmp_path)):
            resp = logged_in_client.post(
                "/api/plugin/custom",
                data=_upload_data(name="check_x2", dependencies="not json"),
                content_type="multipart/form-data",
            )
        assert resp.status_code == 400

    def test_duplicate_plugin_name_rejected(self, logged_in_client, db_session, tmp_path):
        with patch("app.api.plugin.custom_plugin.get_plugin_dir", return_value=str(tmp_path)), _mock_checks_pass():
            logged_in_client.post(
                "/api/plugin/custom",
                data=_upload_data(name="check_dup", filename="check_dup1.sh"),
                content_type="multipart/form-data",
            )
            resp = logged_in_client.post(
                "/api/plugin/custom",
                data=_upload_data(name="check_dup", filename="check_dup2.sh"),
                content_type="multipart/form-data",
            )
        assert resp.status_code == 409

    def test_installed_file_name_collision_rejected(self, logged_in_client, db_session, tmp_path):
        (tmp_path / "check_taken.sh").write_text("existing")
        with patch("app.api.plugin.custom_plugin.get_plugin_dir", return_value=str(tmp_path)):
            resp = logged_in_client.post(
                "/api/plugin/custom",
                data=_upload_data(name="check_new_name", filename="check_taken.sh"),
                content_type="multipart/form-data",
            )
        assert resp.status_code == 409

    def test_invalid_plugin_type_rejected(self, logged_in_client, db_session, tmp_path):
        with patch("app.api.plugin.custom_plugin.get_plugin_dir", return_value=str(tmp_path)):
            resp = logged_in_client.post(
                "/api/plugin/custom",
                data=_upload_data(name="check_badtype", plugin_type="NotAType"),
                content_type="multipart/form-data",
            )
        assert resp.status_code == 400
