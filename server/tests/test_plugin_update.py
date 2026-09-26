"""
tests/test_plugin_update.py — Tests for Phase 9 (Updates):
plugin_update.py's SSRF/archive-safety functions + the full
update/rollback route workflow.

Uses REAL files and REAL archives (tar.gz/zip) rather than mocking the
filesystem layer, since backup/replace/extract are specifically about
real file operations — same reasoning as test_plugin_custom.py.
validate_nagios_configuration is mocked at the service-module level
(not raw subprocess.run) to avoid the same shared-module-object
contamination that broke an earlier manual test of this phase: os and
subprocess are shared module objects across every file that imports
them, so patching a raw OS/subprocess call in one place can silently
affect unrelated code elsewhere that happens to import the same
module. Patching the higher-level function service.py actually calls
avoids that entirely.
"""
import io
import os
import platform
import tarfile
import zipfile
from contextlib import ExitStack
from unittest.mock import patch

import pytest

from app.plugin_models import Plugin, PluginType, PluginSource, PluginStatus, PluginVersion, PluginHistory
from app.api.plugin.plugin_update import (
    validate_download_url, extract_archive, find_plugin_in_extracted,
    InvalidUrlError, UnsafeArchiveError, PluginNotInArchiveError,
)


def _make_plugin(db_session, name, executable_path, version="1.0.0", status=PluginStatus.READY):
    plugin = Plugin(
        Name=name, Plugin_Type=PluginType.NAGIOS, Source=PluginSource.BASELINE_ISO,
        Status=status, Current_Version=version, Executable_Path=executable_path,
    )
    db_session.session.add(plugin)
    db_session.session.flush()
    db_session.session.add(PluginVersion(
        PluginID=plugin.PluginID, Version=version, Executable_Path=executable_path, Is_Current=True,
    ))
    db_session.session.commit()
    return plugin


def _write_plugin_script(path, version_string, exit_code=0):
    with open(path, "w") as f:
        f.write(f'#!/bin/sh\necho "{version_string}"\nexit {exit_code}\n')
    os.chmod(path, 0o755)
    return path


def _build_tar_gz(dest_path, members):
    """members: dict of {arcname: local_file_path}"""
    with tarfile.open(dest_path, "w:gz") as tar:
        for arcname, local_path in members.items():
            tar.add(local_path, arcname=arcname)
    return dest_path


def _build_zip(dest_path, members):
    with zipfile.ZipFile(dest_path, "w") as zf:
        for arcname, local_path in members.items():
            zf.write(local_path, arcname=arcname)
    return dest_path


def _mock_nagios_ok():
    return patch("app.api.plugin.service.validate_nagios_configuration", return_value=(True, "ok"))


def _mock_nagios_fail(output="config error"):
    return patch("app.api.plugin.service.validate_nagios_configuration", return_value=(False, output))


def _mock_update_pipeline(validation_passes=True, versions=None):
    """
    Mocks the two functions in the update/rollback pipeline that
    internally execute the plugin binary via subprocess
    (validate_plugin_executable, via plugin_validator.py's real
    checks, and extract_version) — same class of issue already fixed
    in test_plugin_scanner.py/test_plugin_validation.py/
    test_plugin_custom.py: Windows can't run a #!/bin/sh script
    directly, so relying on real script execution to determine
    outcomes isn't portable for tests that need precise control over
    the result.

    validation_passes: controls whether Phase 7's combined validation
        (executable/permissions/execution) succeeds.
    versions: list of version strings returned by successive calls to
        extract_version — e.g. ["2.4.13"] for a single update, or
        ["2.4.13", "2.4.12"] for an update followed by a rollback (the
        function is called once per pipeline pass). None leaves
        extract_version unmocked.

    Returns an ExitStack — use as a context manager.
    """
    stack = ExitStack()

    validation_result = {
        "is_valid": validation_passes,
        "checks": {
            "executable": {"passed": validation_passes, "message": "mocked"},
            "permissions": {
                "passed": validation_passes, "message": "mocked",
                "mode": "0755", "world_writable": False,
            },
            "execution": {
                "passed": validation_passes, "message": "mocked",
                "exit_code": 0, "output": "mocked",
            },
        },
    }
    stack.enter_context(patch(
        "app.api.plugin.service.validate_plugin_executable", return_value=validation_result,
    ))

    if versions is not None:
        stack.enter_context(patch(
            "app.api.plugin.service.extract_version",
            side_effect=[(v, f"mocked v{v}") for v in versions],
        ))

    return stack


# ─── validate_download_url (SSRF) ──────────────────────────────────────────

class TestValidateDownloadUrl:
    def test_public_https_allowed(self):
        validate_download_url("https://example.com/plugin.tar.gz")  # no raise

    @pytest.mark.parametrize("url", [
        "http://localhost/evil.tar.gz",
        "http://127.0.0.1/evil.tar.gz",
        "http://169.254.169.254/latest/meta-data",
        "http://192.168.1.1/evil.tar.gz",
        "http://10.0.0.5/evil.tar.gz",
    ])
    def test_private_addresses_blocked(self, url):
        with pytest.raises(InvalidUrlError):
            validate_download_url(url)

    @pytest.mark.parametrize("url", [
        "file:///etc/passwd",
        "ftp://example.com/x.tar.gz",
    ])
    def test_bad_schemes_blocked(self, url):
        with pytest.raises(InvalidUrlError):
            validate_download_url(url)


# ─── extract_archive (path traversal / symlink safety) ────────────────────

class TestExtractArchiveSafety:
    def test_path_traversal_tar_member_rejected(self, tmp_path):
        payload = tmp_path / "payload"
        payload.write_text("evil")
        archive = tmp_path / "evil.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            info = tar.gettarinfo(str(payload), arcname="../../../tmp/escaped")
            with open(payload, "rb") as f:
                tar.addfile(info, f)

        dest = tmp_path / "extract_dest"
        dest.mkdir()
        with pytest.raises(UnsafeArchiveError):
            extract_archive(str(archive), str(dest))

    def test_symlink_member_rejected(self, tmp_path):
        """Crafts a tar entry with type=SYMTYPE directly, rather than
        creating a real OS-level symlink first: os.symlink() requires
        Administrator privileges or Developer Mode on Windows, which
        isn't available in CI/most dev environments. This is also a
        more accurate attack simulation — a real attacker building a
        malicious archive wouldn't need symlink-creation rights on
        their OWN machine either, just a tool that writes tar entries
        directly."""
        archive = tmp_path / "evil_symlink.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            info = tarfile.TarInfo(name="innocuous_name")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"  # target need not actually exist
            tar.addfile(info)

        dest = tmp_path / "extract_dest"
        dest.mkdir()
        with pytest.raises(UnsafeArchiveError):
            extract_archive(str(archive), str(dest))

    def test_safe_tar_gz_extracts_normally(self, tmp_path):
        script = _write_plugin_script(tmp_path / "check_x", "check_x v1.0.0")
        archive = tmp_path / "safe.tar.gz"
        _build_tar_gz(archive, {"check_x": str(script)})

        dest = tmp_path / "extract_dest"
        dest.mkdir()
        extract_archive(str(archive), str(dest))
        assert os.path.exists(dest / "check_x")

    def test_safe_zip_extracts_normally(self, tmp_path):
        script = _write_plugin_script(tmp_path / "check_x", "check_x v1.0.0")
        archive = tmp_path / "safe.zip"
        _build_zip(archive, {"check_x": str(script)})

        dest = tmp_path / "extract_dest"
        dest.mkdir()
        extract_archive(str(archive), str(dest))
        assert os.path.exists(dest / "check_x")

    def test_zip_path_traversal_rejected(self, tmp_path):
        payload = tmp_path / "payload"
        payload.write_text("evil")
        archive = tmp_path / "evil.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.write(str(payload), arcname="../../../tmp/escaped")

        dest = tmp_path / "extract_dest"
        dest.mkdir()
        with pytest.raises(UnsafeArchiveError):
            extract_archive(str(archive), str(dest))


# ─── find_plugin_in_extracted ───────────────────────────────────────────────

class TestFindPluginInExtracted:
    def test_finds_file_at_top_level(self, tmp_path):
        (tmp_path / "check_snmp").write_text("x")
        result = find_plugin_in_extracted(str(tmp_path), "check_snmp")
        assert result == str(tmp_path / "check_snmp")

    def test_finds_file_in_nested_folder(self, tmp_path):
        nested = tmp_path / "nagios-plugins-2.4.13"
        nested.mkdir()
        (nested / "check_snmp").write_text("x")
        result = find_plugin_in_extracted(str(tmp_path), "check_snmp")
        assert result == str(nested / "check_snmp")

    def test_missing_plugin_raises(self, tmp_path):
        (tmp_path / "check_other").write_text("x")
        with pytest.raises(PluginNotInArchiveError):
            find_plugin_in_extracted(str(tmp_path), "check_snmp")

    def test_only_matching_file_selected_others_ignored(self, tmp_path):
        """Confirms Phase 9's IMPORTANT note: an archive containing many
        plugins only ever yields the ONE being updated."""
        (tmp_path / "check_snmp").write_text("target")
        (tmp_path / "check_disk").write_text("not this one")
        (tmp_path / "check_http").write_text("not this one either")
        result = find_plugin_in_extracted(str(tmp_path), "check_snmp")
        assert "check_snmp" in result


# ─── POST /plugin/<id>/update and .../update/rollback ──────────────────────

class TestUpdatePluginRoute:
    def test_requires_login(self, client, db_session, tmp_path):
        installed = _write_plugin_script(tmp_path / "check_x", "check_x v1.0.0")
        plugin = _make_plugin(db_session, "check_x", str(installed))
        resp = client.post(f"/api/plugin/{plugin.PluginID}/update")
        assert resp.status_code in (401, 302)

    def test_requires_permission(self, limited_client, db_session, tmp_path):
        installed = _write_plugin_script(tmp_path / "check_x", "check_x v1.0.0")
        plugin = _make_plugin(db_session, "check_x", str(installed))
        resp = limited_client.post(f"/api/plugin/{plugin.PluginID}/update")
        assert resp.status_code == 403

    def test_not_found(self, logged_in_client, db_session, tmp_path):
        script = _write_plugin_script(tmp_path / "check_x", "check_x v1.0.0")
        archive = _build_tar_gz(tmp_path / "update.tar.gz", {"check_x": str(script)})
        with open(archive, "rb") as f:
            resp = logged_in_client.post(
                "/api/plugin/999999/update",
                data={"file": (f, "update.tar.gz")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 404

    def test_neither_file_nor_url_rejected(self, logged_in_client, db_session, tmp_path):
        installed = _write_plugin_script(tmp_path / "check_x", "check_x v1.0.0")
        plugin = _make_plugin(db_session, "check_x", str(installed))
        resp = logged_in_client.post(f"/api/plugin/{plugin.PluginID}/update")
        assert resp.status_code == 400

    def test_both_file_and_url_rejected(self, logged_in_client, db_session, tmp_path):
        installed = _write_plugin_script(tmp_path / "check_x", "check_x v1.0.0")
        plugin = _make_plugin(db_session, "check_x", str(installed))
        new_script = _write_plugin_script(tmp_path / "check_x_new", "check_x v2.0.0")
        archive = _build_tar_gz(tmp_path / "update.tar.gz", {"check_x": str(new_script)})
        with open(archive, "rb") as f:
            resp = logged_in_client.post(
                f"/api/plugin/{plugin.PluginID}/update",
                data={"file": (f, "update.tar.gz"), "url": "https://example.com/x.tar.gz"},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 400

    def test_successful_update(self, logged_in_client, db_session, tmp_path):
        installed_dir = tmp_path / "libexec"
        installed_dir.mkdir()
        installed = _write_plugin_script(installed_dir / "check_snmp", "check_snmp v2.4.12")

        plugin = _make_plugin(db_session, "check_snmp", str(installed), version="2.4.12")

        new_script = _write_plugin_script(tmp_path / "new_check_snmp", "check_snmp v2.4.13")
        archive = _build_tar_gz(tmp_path / "update.tar.gz", {"check_snmp": str(new_script)})

        with patch("app.api.plugin.plugin_update.get_plugin_dir", return_value=str(installed_dir)), \
             _mock_nagios_ok(), _mock_update_pipeline(validation_passes=True, versions=["2.4.13"]):
            with open(archive, "rb") as f:
                resp = logged_in_client.post(
                    f"/api/plugin/{plugin.PluginID}/update",
                    data={"file": (f, "update.tar.gz")},
                    content_type="multipart/form-data",
                )

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["success"] is True
        assert data["previous_version"] == "2.4.12"
        assert data["current_version"] == "2.4.13"
        assert data["rollback_available"] is True

        db_session.session.refresh(plugin)
        assert plugin.Current_Version == "2.4.13"
        assert plugin.Status == PluginStatus.READY
        assert "v2.4.13" in open(installed).read()

        backup_path = installed_dir / ".pinpoint_backups" / "check_snmp"
        assert backup_path.exists()
        assert "v2.4.12" in backup_path.read_text()

    def test_update_creates_history(self, logged_in_client, db_session, tmp_path):
        installed_dir = tmp_path / "libexec"
        installed_dir.mkdir()
        installed = _write_plugin_script(installed_dir / "check_snmp", "check_snmp v2.4.12")
        plugin = _make_plugin(db_session, "check_snmp", str(installed), version="2.4.12")
        new_script = _write_plugin_script(tmp_path / "new_check_snmp", "check_snmp v2.4.13")
        archive = _build_tar_gz(tmp_path / "update.tar.gz", {"check_snmp": str(new_script)})

        with patch("app.api.plugin.plugin_update.get_plugin_dir", return_value=str(installed_dir)), \
             _mock_nagios_ok(), _mock_update_pipeline(validation_passes=True, versions=["2.4.13"]):
            with open(archive, "rb") as f:
                logged_in_client.post(
                    f"/api/plugin/{plugin.PluginID}/update",
                    data={"file": (f, "update.tar.gz")},
                    content_type="multipart/form-data",
                )

        history = db_session.session.execute(
            db_session.select(PluginHistory).where(PluginHistory.PluginID == plugin.PluginID)
        ).scalar_one()
        assert history.Action.value == "Update"
        assert history.Result.value == "Success"
        assert history.Old_Value == "2.4.12"
        assert history.New_Value == "2.4.13"

    def test_plugin_not_in_archive(self, logged_in_client, db_session, tmp_path):
        installed_dir = tmp_path / "libexec"
        installed_dir.mkdir()
        installed = _write_plugin_script(installed_dir / "check_snmp", "check_snmp v2.4.12")
        plugin = _make_plugin(db_session, "check_snmp", str(installed))

        other_script = _write_plugin_script(tmp_path / "check_other", "check_other v1.0.0")
        archive = _build_tar_gz(tmp_path / "update.tar.gz", {"check_other": str(other_script)})

        with patch("app.api.plugin.plugin_update.get_plugin_dir", return_value=str(installed_dir)):
            with open(archive, "rb") as f:
                resp = logged_in_client.post(
                    f"/api/plugin/{plugin.PluginID}/update",
                    data={"file": (f, "update.tar.gz")},
                    content_type="multipart/form-data",
                )
        assert resp.status_code == 404
        # Original file untouched, no backup created.
        assert "v2.4.12" in open(installed).read()
        assert not (installed_dir / ".pinpoint_backups" / "check_snmp").exists()

    def test_failed_nagios_check_sets_rollback_status_no_autorollback(self, logged_in_client, db_session, tmp_path):
        installed_dir = tmp_path / "libexec"
        installed_dir.mkdir()
        installed = _write_plugin_script(installed_dir / "check_snmp", "check_snmp v2.4.12")
        plugin = _make_plugin(db_session, "check_snmp", str(installed), version="2.4.12")
        new_script = _write_plugin_script(tmp_path / "new_check_snmp", "check_snmp v2.4.13")
        archive = _build_tar_gz(tmp_path / "update.tar.gz", {"check_snmp": str(new_script)})

        with patch("app.api.plugin.plugin_update.get_plugin_dir", return_value=str(installed_dir)), \
             _mock_nagios_fail(), _mock_update_pipeline(validation_passes=True):
            with open(archive, "rb") as f:
                resp = logged_in_client.post(
                    f"/api/plugin/{plugin.PluginID}/update",
                    data={"file": (f, "update.tar.gz")},
                    content_type="multipart/form-data",
                )

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["success"] is False
        assert data["status"] == "Rollback"
        assert data["failed_step"] == "Nagios configuration check"

        db_session.session.refresh(plugin)
        assert plugin.Status == PluginStatus.ROLLBACK
        # Confirmed design: NOT auto-rolled-back — the bad file stays installed.
        assert "v2.4.13" in open(installed).read()

    def test_update_blocked_in_failed_status(self, logged_in_client, db_session, tmp_path):
        installed = _write_plugin_script(tmp_path / "check_x", "check_x v1.0.0")
        plugin = _make_plugin(db_session, "check_x", str(installed), status=PluginStatus.VALIDATION_FAILED)
        archive = _build_tar_gz(tmp_path / "update.tar.gz", {"check_x": str(installed)})
        with open(archive, "rb") as f:
            resp = logged_in_client.post(
                f"/api/plugin/{plugin.PluginID}/update",
                data={"file": (f, "update.tar.gz")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 409


class TestRollbackUpdateRoute:
    def test_requires_permission(self, limited_client, db_session, tmp_path):
        installed = _write_plugin_script(tmp_path / "check_x", "check_x v1.0.0")
        plugin = _make_plugin(db_session, "check_x", str(installed))
        resp = limited_client.post(f"/api/plugin/{plugin.PluginID}/update/rollback")
        assert resp.status_code == 403

    def test_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.post("/api/plugin/999999/update/rollback")
        assert resp.status_code == 404

    def test_no_backup_available(self, logged_in_client, db_session, tmp_path):
        installed_dir = tmp_path / "libexec"
        installed_dir.mkdir()
        installed = _write_plugin_script(installed_dir / "check_x", "check_x v1.0.0")
        plugin = _make_plugin(db_session, "check_x", str(installed))

        with patch("app.api.plugin.plugin_update.get_plugin_dir", return_value=str(installed_dir)):
            resp = logged_in_client.post(f"/api/plugin/{plugin.PluginID}/update/rollback")
        assert resp.status_code == 404

    def test_rollback_after_failed_update(self, logged_in_client, db_session, tmp_path):
        installed_dir = tmp_path / "libexec"
        installed_dir.mkdir()
        installed = _write_plugin_script(installed_dir / "check_snmp", "check_snmp v2.4.12")
        plugin = _make_plugin(db_session, "check_snmp", str(installed), version="2.4.12")
        new_script = _write_plugin_script(tmp_path / "new_check_snmp", "check_snmp v2.4.13")
        archive = _build_tar_gz(tmp_path / "update.tar.gz", {"check_snmp": str(new_script)})

        with patch("app.api.plugin.plugin_update.get_plugin_dir", return_value=str(installed_dir)), \
             _mock_nagios_fail(), _mock_update_pipeline(validation_passes=True, versions=["2.4.12"]):
            with open(archive, "rb") as f:
                logged_in_client.post(
                    f"/api/plugin/{plugin.PluginID}/update",
                    data={"file": (f, "update.tar.gz")},
                    content_type="multipart/form-data",
                )

            resp = logged_in_client.post(f"/api/plugin/{plugin.PluginID}/update/rollback")

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["restored_version"] == "2.4.12"

        db_session.session.refresh(plugin)
        assert plugin.Status == PluginStatus.READY
        assert plugin.Current_Version == "2.4.12"
        assert "v2.4.12" in open(installed).read()

    def test_rollback_does_not_duplicate_existing_version_row(self, logged_in_client, db_session, tmp_path):
        """Regression test: rollback restoring a version that already has
        a historical PluginVersion row must not hit the (PluginID,
        Version) uniqueness constraint."""
        installed_dir = tmp_path / "libexec"
        installed_dir.mkdir()
        installed = _write_plugin_script(installed_dir / "check_snmp", "check_snmp v2.4.12")
        plugin = _make_plugin(db_session, "check_snmp", str(installed), version="2.4.12")
        new_script = _write_plugin_script(tmp_path / "new_check_snmp", "check_snmp v2.4.13")
        archive = _build_tar_gz(tmp_path / "update.tar.gz", {"check_snmp": str(new_script)})

        with patch("app.api.plugin.plugin_update.get_plugin_dir", return_value=str(installed_dir)), \
             _mock_nagios_ok(), _mock_update_pipeline(validation_passes=True, versions=["2.4.13", "2.4.12"]):
            with open(archive, "rb") as f:
                logged_in_client.post(
                    f"/api/plugin/{plugin.PluginID}/update",
                    data={"file": (f, "update.tar.gz")},
                    content_type="multipart/form-data",
                )
            # Successful update -> rollback is still available per UI Flow
            # Section 22 ("Rollback: Available" shown on success too).
            resp = logged_in_client.post(f"/api/plugin/{plugin.PluginID}/update/rollback")

        assert resp.status_code == 200

        versions = db_session.session.execute(
            db_session.select(PluginVersion).where(PluginVersion.PluginID == plugin.PluginID)
        ).scalars().all()
        version_strings = [v.Version for v in versions]
        # No duplicates: each version string appears in exactly one row.
        assert len(version_strings) == len(set(version_strings))
        assert "2.4.12" in version_strings
        assert "2.4.13" in version_strings

    def test_rollback_records_history(self, logged_in_client, db_session, tmp_path):
        installed_dir = tmp_path / "libexec"
        installed_dir.mkdir()
        installed = _write_plugin_script(installed_dir / "check_snmp", "check_snmp v2.4.12")
        plugin = _make_plugin(db_session, "check_snmp", str(installed), version="2.4.12")
        new_script = _write_plugin_script(tmp_path / "new_check_snmp", "check_snmp v2.4.13")
        archive = _build_tar_gz(tmp_path / "update.tar.gz", {"check_snmp": str(new_script)})

        with patch("app.api.plugin.plugin_update.get_plugin_dir", return_value=str(installed_dir)), \
             _mock_nagios_fail(), _mock_update_pipeline(validation_passes=True, versions=["2.4.12"]):
            with open(archive, "rb") as f:
                logged_in_client.post(
                    f"/api/plugin/{plugin.PluginID}/update",
                    data={"file": (f, "update.tar.gz")},
                    content_type="multipart/form-data",
                )
            logged_in_client.post(f"/api/plugin/{plugin.PluginID}/update/rollback")

        histories = db_session.session.execute(
            db_session.select(PluginHistory)
            .where(PluginHistory.PluginID == plugin.PluginID)
            .order_by(PluginHistory.PluginHistoryID)
        ).scalars().all()
        assert histories[-1].Action.value == "Rollback"
        assert histories[-1].Result.value == "Success"


# ─── Real end-to-end pipeline, Linux only ──────────────────────────────────

@pytest.mark.skipif(
    platform.system() != "Linux",
    reason="Exercises the real update/rollback pipeline with real "
           "#!/bin/sh script execution (real plugin_validator checks, "
           "real scanner.extract_version) — Windows can't run a "
           "shebang script directly, so this is validated for real "
           "only on Linux, matching the actual deployment target. "
           "The mocked route tests above cover the same scenarios "
           "cross-platform.",
)
class TestRealUpdatePipeline:
    def test_real_update_and_rollback_end_to_end(self, logged_in_client, db_session, tmp_path):
        installed_dir = tmp_path / "libexec"
        installed_dir.mkdir()
        installed = _write_plugin_script(installed_dir / "check_snmp", "check_snmp v2.4.12")
        plugin = _make_plugin(db_session, "check_snmp", str(installed), version="2.4.12")

        new_script = _write_plugin_script(tmp_path / "new_check_snmp", "check_snmp v2.4.13")
        archive = _build_tar_gz(tmp_path / "update.tar.gz", {"check_snmp": str(new_script)})

        with patch("app.api.plugin.plugin_update.get_plugin_dir", return_value=str(installed_dir)), _mock_nagios_ok():
            with open(archive, "rb") as f:
                resp = logged_in_client.post(
                    f"/api/plugin/{plugin.PluginID}/update",
                    data={"file": (f, "update.tar.gz")},
                    content_type="multipart/form-data",
                )

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["success"] is True
        # Real extract_version() genuinely parsed this from the real file.
        assert data["current_version"] == "2.4.13"

        with patch("app.api.plugin.plugin_update.get_plugin_dir", return_value=str(installed_dir)):
            resp = logged_in_client.post(f"/api/plugin/{plugin.PluginID}/update/rollback")

        assert resp.status_code == 200
        assert resp.get_json()["data"]["restored_version"] == "2.4.12"
        assert "v2.4.12" in open(installed).read()

        versions = db_session.session.execute(
            db_session.select(PluginVersion).where(PluginVersion.PluginID == plugin.PluginID)
        ).scalars().all()
        version_strings = [v.Version for v in versions]
        assert len(version_strings) == len(set(version_strings))
        assert set(version_strings) == {"2.4.12", "2.4.13"}
