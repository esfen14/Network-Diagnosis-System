"""
tests/unit/test_host_file_modes.py — who can read the generated Nagios host files.

A custom check that needs a password has it written into the host file, because Nagios needs it in the
check's command. The candidate file Pinpoint generates and the backup it keeps are therefore created so only the
app can read them, whatever the umask. The live hosts.cfg keeps the mode the operator gave it (copying onto an
existing file does not change it), and Pinpoint logs a warning when that file holds a password and everyone can
read it. File modes only mean something on POSIX, so those cases are skipped elsewhere.
"""
import os
import stat
import subprocess
from unittest.mock import patch

import pytest

from app import db
from app.network_discovery import create_host_cfg
from app.network_discovery.create_host_cfg import (
    _apply_new_host_cfg, _backup_running_host_cfg, _create_host_cfg_file, _load_monitored_hosts,
    write_private_file,
)
from tests.unit.test_custom_checks_config_structure import add_check

posix_only = pytest.mark.skipif(os.name != "posix", reason="file modes are only meaningful on POSIX")


def mode_of(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def test_the_file_content_is_written_unchanged(tmp_path):
    target = tmp_path / "host.cfg"
    write_private_file(target, "define host {\n}\n")
    assert target.read_text() == "define host {" + chr(10) + "}" + chr(10)


def test_an_existing_file_is_replaced_not_appended(tmp_path):
    target = tmp_path / "host.cfg"
    target.write_text("old content that is much longer than the new one")
    write_private_file(target, "new")
    assert target.read_text() == "new"


@posix_only
def test_a_private_file_is_not_readable_by_group_or_others_even_with_a_permissive_umask(tmp_path):
    previous = os.umask(0)
    try:
        target = tmp_path / "host.cfg"
        write_private_file(target, "x")
    finally:
        os.umask(previous)
    assert mode_of(target) == 0o600


@posix_only
def test_an_existing_permissive_file_is_made_private(tmp_path):
    target = tmp_path / "host.cfg"
    target.write_text("x")
    target.chmod(0o666)
    write_private_file(target, "y")
    assert mode_of(target) == 0o600


@posix_only
def test_the_generated_candidate_file_is_private(app, db_session, tmp_path):
    original = app.config["HOST_CONFIG_DIR"]
    app.config["HOST_CONFIG_DIR"] = tmp_path
    try:
        candidate = _create_host_cfg_file(_load_monitored_hosts())
    finally:
        app.config["HOST_CONFIG_DIR"] = original
    assert mode_of(candidate) == 0o600


@posix_only
def test_the_backup_of_the_live_file_is_private(app, tmp_path):
    live = tmp_path / "hosts.cfg"
    live.write_text("live")
    live.chmod(0o644)
    originals = (app.config["NAGIOS_HOST_CFG"], app.config["BACKUP_DIR"])
    app.config["NAGIOS_HOST_CFG"], app.config["BACKUP_DIR"] = live, tmp_path / "backups"
    try:
        with app.app_context():
            backup = _backup_running_host_cfg()
    finally:
        app.config["NAGIOS_HOST_CFG"], app.config["BACKUP_DIR"] = originals
    assert mode_of(backup) == 0o600 and backup.read_text() == "live"
    assert mode_of(live) == 0o644


class TestApplying:

    def apply(self, app, live, candidate, caplog):
        originals = (app.config["NAGIOS_HOST_CFG"], app.config["BACKUP_DIR"])
        app.config["NAGIOS_HOST_CFG"], app.config["BACKUP_DIR"] = live, live.parent / "backups"
        try:
            with patch.object(create_host_cfg.subprocess, "run",
                              return_value=subprocess.CompletedProcess([], 0, "", "")), \
                    patch.object(create_host_cfg, "migrate_legacy_service_history"):
                with app.app_context():
                    return _apply_new_host_cfg(candidate)
        finally:
            app.config["NAGIOS_HOST_CFG"], app.config["BACKUP_DIR"] = originals

    def files(self, tmp_path, live_mode):
        live = tmp_path / "hosts.cfg"
        live.write_text("old")
        live.chmod(live_mode)
        candidate = tmp_path / "candidate.cfg"
        write_private_file(candidate, "new")
        return live, candidate

    @posix_only
    def test_applying_keeps_the_mode_the_operator_gave_the_live_file(self, app, db_session, tmp_path, caplog):
        live, candidate = self.files(tmp_path, 0o640)
        ok, _ = self.apply(app, live, candidate, caplog)
        assert ok and live.read_text() == "new"
        assert mode_of(live) == 0o640

    @posix_only
    def test_a_world_readable_live_file_with_a_password_is_reported(self, app, db_session, tmp_path, caplog):
        add_check("check_radius", "Auth", {"user": "probe", "password": "Lab-Pw_1", "config": "/etc/radius.conf"})
        db.session.commit()
        live, candidate = self.files(tmp_path, 0o644)
        with caplog.at_level("WARNING"):
            ok, _ = self.apply(app, live, candidate, caplog)
        assert ok
        assert "readable by every user" in caplog.text and str(live) in caplog.text
        assert "Lab-Pw_1" not in caplog.text

    @posix_only
    def test_a_protected_live_file_is_not_reported(self, app, db_session, tmp_path, caplog):
        add_check("check_radius", "Auth", {"user": "probe", "password": "Lab-Pw_1", "config": "/etc/radius.conf"})
        db.session.commit()
        live, candidate = self.files(tmp_path, 0o640)
        with caplog.at_level("WARNING"):
            self.apply(app, live, candidate, caplog)
        assert "readable by every user" not in caplog.text

    @posix_only
    def test_a_world_readable_live_file_without_any_password_is_not_reported(self, app, db_session, tmp_path, caplog):
        live, candidate = self.files(tmp_path, 0o644)
        with caplog.at_level("WARNING"):
            self.apply(app, live, candidate, caplog)
        assert "readable by every user" not in caplog.text
