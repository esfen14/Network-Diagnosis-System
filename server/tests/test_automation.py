"""
Tests for app/automation.py — the scheduled tasks driven by System
Settings (scan frequency, update checks, security checks, backups and
maintenance mode).

Starting real network scans or plugin scans is out of scope here: the
thread starters are patched, so these tests only check which tasks are
started and when.
"""
import os
import sqlite3
import stat
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app import automation
from app.automation import (
    SECURITY_CHECK_ACTION,
    as_utc,
    backup_databases,
    get_automation_user_id,
    is_due,
    last_security_check,
    list_backups,
    run_due_automation,
    run_security_check,
)
from app.logging.user_activity import create_user_log
from app.plugin_models import Plugin, PluginSource, PluginStatus, PluginType
from app.system_models import ActivityLog, NetworkDiscoveryStatus, DiscoveryStatus, SystemSettings, UserStatus

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def make_settings(db_session, **overrides):
    values = {
        "Id": 1,
        "Scan_Frequency": 6,
        "Automatic_Backups": False,
        "Maintenance_Mode": False,
        "System_Update_Frequency": "monthly",
        "Security_Check_Frequency": "weekly",
    }
    values.update(overrides)
    settings = SystemSettings(**values)
    db_session.session.add(settings)
    db_session.session.commit()
    return settings


@contextmanager
def patched_starters(discovery=True, plugin_scan=True):
    with patch.object(automation, "start_discovery_thread", return_value=discovery) as start_discovery, \
         patch.object(automation, "start_plugin_scan_thread", return_value=plugin_scan) as start_scan:
        yield start_discovery, start_scan


def make_plugin(db_session, name, executable_path):
    plugin = Plugin(
        Name=name,
        Plugin_Type=PluginType.NAGIOS,
        Source=PluginSource.BASELINE_ISO,
        Status=PluginStatus.READY,
        Executable_Path=executable_path,
    )
    db_session.session.add(plugin)
    db_session.session.commit()
    return plugin


def write_script(path):
    path.write_text("#!/bin/sh\necho 'OK - test plugin'\nexit 0\n")
    os.chmod(path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP)
    return path


def make_sqlite_file(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE sample (value TEXT)")
    conn.execute("INSERT INTO sample VALUES ('kept')")
    conn.commit()
    conn.close()
    return path


# ==========================================================
# SCHEDULING HELPERS
# ==========================================================

class TestSchedulingHelpers:
    def test_as_utc_treats_naive_as_utc(self):
        assert as_utc(datetime(2026, 1, 1, 8, 0)) == datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)

    def test_as_utc_passes_none(self):
        assert as_utc(None) is None

    def test_never_run_is_due(self):
        assert is_due(None, timedelta(hours=1), NOW)

    def test_recent_run_is_not_due(self):
        assert not is_due(NOW - timedelta(minutes=30), timedelta(hours=1), NOW)

    def test_old_naive_run_is_due(self):
        assert is_due((NOW - timedelta(hours=2)).replace(tzinfo=None), timedelta(hours=1), NOW)


class TestAutomationUser:
    def test_prefers_user_who_last_saved_settings(self, db_session, admin_user, regular_user):
        settings = make_settings(db_session, Updated_By=regular_user.UserID)

        assert get_automation_user_id(settings) == regular_user.UserID

    def test_falls_back_to_user_with_discover_permission(self, db_session, admin_user, regular_user):
        regular_user.Status = UserStatus.INACTIVE
        db_session.session.commit()
        settings = make_settings(db_session, Updated_By=regular_user.UserID)

        assert get_automation_user_id(settings) == admin_user.UserID

    def test_none_without_eligible_user(self, db_session, regular_user):
        settings = make_settings(db_session)

        assert get_automation_user_id(settings) is None


# ==========================================================
# SCHEDULER ENTRY POINT
# ==========================================================

class TestRunDueAutomation:
    def test_nothing_without_settings_row(self, db_session):
        assert run_due_automation(NOW) == []

    def test_starts_all_due_tasks(self, db_session, admin_user):
        make_settings(db_session)

        with patched_starters() as (start_discovery, start_scan):
            started = run_due_automation(NOW)

        assert started == ["network_scan", "update_check", "security_check"]
        start_discovery.assert_called_once_with(admin_user.UserID)
        start_scan.assert_called_once_with(admin_user.UserID)

    def test_maintenance_mode_pauses_tasks(self, db_session, admin_user):
        make_settings(db_session, Maintenance_Mode=True)

        with patched_starters() as (start_discovery, start_scan):
            started = run_due_automation(NOW)

        assert started == []
        start_discovery.assert_not_called()
        start_scan.assert_not_called()

    def test_recent_scan_is_not_repeated(self, db_session, admin_user):
        make_settings(db_session, Scan_Frequency=1)
        log = create_user_log(admin_user.UserID, "Discovering Network Hosts")
        db_session.session.add(NetworkDiscoveryStatus(
            Status=DiscoveryStatus.SUCCESS,
            Progress=100,
            Message="done",
            Start_At=NOW - timedelta(minutes=30),
            LogID=log.LogID,
        ))
        db_session.session.commit()

        with patched_starters() as (start_discovery, _):
            started = run_due_automation(NOW)

        assert "network_scan" not in started
        start_discovery.assert_not_called()

    def test_scan_already_running_is_not_reported(self, db_session, admin_user):
        make_settings(db_session)

        with patched_starters(discovery=False):
            started = run_due_automation(NOW)

        assert "network_scan" not in started

    def test_manual_update_frequency_disables_update_check(self, db_session, admin_user):
        make_settings(db_session, System_Update_Frequency="manual")

        with patched_starters() as (_, start_scan):
            started = run_due_automation(NOW)

        assert "update_check" not in started
        start_scan.assert_not_called()

    def test_security_check_waits_for_its_interval(self, db_session, admin_user):
        make_settings(db_session, Security_Check_Frequency="daily")

        with patched_starters():
            first = run_due_automation(NOW)
            second = run_due_automation(NOW + timedelta(hours=1))

        assert "security_check" in first
        assert "security_check" not in second

    def test_skips_tasks_without_eligible_user(self, db_session, regular_user):
        make_settings(db_session)

        with patched_starters() as (start_discovery, _):
            started = run_due_automation(NOW)

        assert started == []
        start_discovery.assert_not_called()

    def test_backup_runs_once_a_day(self, app, db_session, admin_user, tmp_path):
        make_settings(db_session, Automatic_Backups=True, Maintenance_Mode=True)
        database = make_sqlite_file(tmp_path / "system.db")
        backup_dir = tmp_path / "backups"

        with patch.dict(app.config, {"DATABASE_BACKUP_DIR": backup_dir}), \
             patch.object(automation, "database_file_paths", return_value=[str(database)]):
            first = run_due_automation(NOW)
            later_same_day = run_due_automation(NOW + timedelta(hours=3))
            next_day = run_due_automation(NOW + timedelta(days=1))

        assert first == ["backup"]
        assert later_same_day == []
        assert next_day == ["backup"]
        assert len(list_backups(backup_dir)) == 2

    def test_backup_off_takes_no_backup(self, app, db_session, admin_user, tmp_path):
        make_settings(db_session, Automatic_Backups=False, Maintenance_Mode=True)
        backup_dir = tmp_path / "backups"

        with patch.dict(app.config, {"DATABASE_BACKUP_DIR": backup_dir}):
            started = run_due_automation(NOW)

        assert started == []
        assert list_backups(backup_dir) == []


# ==========================================================
# TASKS
# ==========================================================

class TestSecurityCheck:
    def test_flags_broken_plugins_and_logs_summary(self, db_session, admin_user, tmp_path):
        good = make_plugin(db_session, "check_good", str(write_script(tmp_path / "check_good")))
        bad = make_plugin(db_session, "check_missing", str(tmp_path / "does_not_exist"))

        failed, total = run_security_check(admin_user.UserID)

        assert (failed, total) == (1, 2)
        db_session.session.refresh(good)
        db_session.session.refresh(bad)
        assert good.Status == PluginStatus.READY
        assert bad.Status == PluginStatus.VALIDATION_FAILED
        assert last_security_check() is not None
        log = db_session.session.query(ActivityLog).filter(
            ActivityLog.Action_Type.like(f"{SECURITY_CHECK_ACTION}%")
        ).one()
        assert "1 of 2" in log.Action_Type

    def test_world_writable_plugin_fails(self, db_session, admin_user, tmp_path):
        script = write_script(tmp_path / "check_writable")
        os.chmod(script, 0o777)
        plugin = make_plugin(db_session, "check_writable", str(script))

        failed, _ = run_security_check(admin_user.UserID)

        db_session.session.refresh(plugin)
        assert failed == 1
        assert plugin.Status == PluginStatus.VALIDATION_FAILED


class TestBackupDatabases:
    def test_copies_database_contents(self, tmp_path):
        database = make_sqlite_file(tmp_path / "system.db")

        folder = backup_databases([str(database)], tmp_path / "backups", keep=7, now=NOW)

        conn = sqlite3.connect(folder / "system.db")
        assert conn.execute("SELECT value FROM sample").fetchall() == [("kept",)]
        conn.close()

    def test_keeps_only_newest_backups(self, tmp_path):
        database = make_sqlite_file(tmp_path / "system.db")
        backup_dir = tmp_path / "backups"

        for day in range(4):
            backup_databases([str(database)], backup_dir, keep=2, now=NOW + timedelta(days=day))

        kept = [taken_at for taken_at, _ in list_backups(backup_dir)]
        assert kept == [NOW + timedelta(days=2), NOW + timedelta(days=3)]

    def test_ignores_unrelated_folders(self, tmp_path):
        backup_dir = tmp_path / "backups"
        (backup_dir / "notes").mkdir(parents=True)

        assert list_backups(backup_dir) == []
