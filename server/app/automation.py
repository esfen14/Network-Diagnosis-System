"""
Scheduled automation driven by System Settings.

One scheduler job (registered in app/scheduler.py) calls
run_due_automation() every AUTOMATION_CHECK_MINUTES and starts whichever
tasks are due:

- Network discovery scan: every Scan_Frequency hours.
- Plugin update check: re-scans the plugin directory, which flags any
  plugin whose version changed as "Update Available". Runs on the
  System_Update_Frequency schedule; "manual" turns it off.
- Security check: re-validates every plugin executable (exists, is
  executable, not world-writable, runs). Failures show up as
  "Validation Failed" in the Plugin Manager. Runs on the
  Security_Check_Frequency schedule.
- Database backup: copies system.db and history.db once a day while
  Automatic_Backups is on, keeping the newest DATABASE_BACKUP_KEEP.

"Due" is measured from when the task last ran, manually or on schedule,
using records that already exist (discovery and plugin scan status rows,
the activity log, backup folders), so no extra tables are needed.

Maintenance mode pauses the scan, update check and security check.
Backups keep running, since maintenance is when you most want one.

Scheduled runs need a user for their activity-log rows. They are
attributed to the admin who last saved System Settings, falling back to
the first active user allowed to run network discovery.
"""
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sqlalchemy as sa
from flask import current_app

from app import app, db
from app.api.plugin import service as plugin_service
from app.api.plugin.manager import start_plugin_scan_thread
from app.api.system.network_discovery import start_discovery_thread
from app.logging.user_activity import create_user_log
from app.plugin_models import Plugin, PluginScanStatus
from app.system_models import (
    ActivityLog,
    NetworkDiscoveryStatus,
    Permission,
    RolePermission,
    SystemSettings,
    User,
    UserStatus,
)

UPDATE_CHECK_INTERVALS = {
    "weekly": timedelta(weeks=1),
    "monthly": timedelta(days=30),
    "quarterly": timedelta(days=91),
}

SECURITY_CHECK_INTERVALS = {
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    "monthly": timedelta(days=30),
}

BACKUP_INTERVAL = timedelta(days=1)
BACKUP_FOLDER_FORMAT = "%Y%m%d-%H%M%S"

SECURITY_CHECK_ACTION = "Scheduled security check"
AUTOMATION_PERMISSION = "system.discover"


# ==========================================================
# SCHEDULING HELPERS
# ==========================================================

def as_utc(value):
    """
    Return value as a timezone-aware UTC datetime. SQLite hands back
    naive datetimes even for columns written as UTC, so naive values
    are assumed to already be UTC. None passes through.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def is_due(last_run, interval, now):
    """
    Whether a task that last ran at last_run (None if never) is due
    again at now, given its interval.
    """
    last_run = as_utc(last_run)
    return last_run is None or now - last_run >= interval


def get_automation_user_id(settings):
    """
    Return the UserID that scheduled tasks are attributed to: the user
    who last saved System Settings if still active, otherwise the first
    active user whose role can run network discovery. Returns None if
    there is no such user.
    """
    if settings.Updated_By is not None:
        user = db.session.get(User, settings.Updated_By)
        if user is not None and user.Status == UserStatus.ACTIVE:
            return user.UserID

    return db.session.scalar(
        sa.select(User.UserID)
        .join(RolePermission, RolePermission.RoleID == User.RoleID)
        .join(Permission, Permission.PermissionID == RolePermission.PermissionID)
        .where(
            User.Status == UserStatus.ACTIVE,
            Permission.Name == AUTOMATION_PERMISSION,
        )
        .order_by(User.UserID)
        .limit(1)
    )


def last_discovery_start():
    """When the most recent network discovery scan started, or None."""
    return db.session.scalar(sa.select(sa.func.max(NetworkDiscoveryStatus.Start_At)))


def last_plugin_scan_start():
    """When the most recent plugin directory scan started, or None."""
    return db.session.scalar(sa.select(sa.func.max(PluginScanStatus.Start_At)))


def last_security_check():
    """When the most recent scheduled security check ran, or None."""
    return db.session.scalar(
        sa.select(sa.func.max(ActivityLog.Performed_At))
        .where(ActivityLog.Action_Type.like(f"{SECURITY_CHECK_ACTION}%"))
    )


def list_backups(backup_dir):
    """
    Return (taken_at, folder) pairs for the backup folders in
    backup_dir, oldest first. Folders not named by
    BACKUP_FOLDER_FORMAT are ignored.
    """
    backup_dir = Path(backup_dir)
    if not backup_dir.is_dir():
        return []

    backups = []
    for folder in backup_dir.iterdir():
        if not folder.is_dir():
            continue
        try:
            taken_at = datetime.strptime(folder.name, BACKUP_FOLDER_FORMAT).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        backups.append((taken_at, folder))

    backups.sort()
    return backups


# ==========================================================
# TASKS
# ==========================================================

def database_file_paths():
    """
    Return the file paths of every SQLite database the app uses
    (system.db and history.db), skipping in-memory databases.
    """
    paths = []
    for engine in [db.engine] + list(db.engines.values()):
        path = engine.url.database
        if path and path != ":memory:" and path not in paths:
            paths.append(path)
    return paths


def backup_databases(database_paths, backup_dir, keep, now):
    """
    Copy each SQLite database in database_paths into a new timestamped
    folder under backup_dir, using SQLite's online backup API so a copy
    taken mid-write is still consistent. Then deletes all but the newest
    `keep` backup folders. Returns the new folder's path.
    """
    folder = Path(backup_dir) / now.strftime(BACKUP_FOLDER_FORMAT)
    folder.mkdir(parents=True, exist_ok=True)

    for source_path in database_paths:
        source = sqlite3.connect(source_path)
        target = sqlite3.connect(folder / Path(source_path).name)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()

    backups = list_backups(backup_dir)
    for _, old_folder in backups[:-keep]:
        shutil.rmtree(old_folder, ignore_errors=True)

    return folder


def run_security_check(user_id):
    """
    Validate every registered plugin's executable (see
    plugin_service.validate_plugin, which updates each plugin's status
    and history and commits), then write one activity-log entry
    summarising the result. Returns (failed_count, total_count).
    """
    plugin_ids = db.session.scalars(sa.select(Plugin.PluginID).order_by(Plugin.PluginID)).all()

    failed = 0
    for plugin_id in plugin_ids:
        result = plugin_service.validate_plugin(plugin_id, user_id)
        if not result["is_valid"]:
            failed += 1

    create_user_log(
        user_id,
        f"{SECURITY_CHECK_ACTION}: {failed} of {len(plugin_ids)} plugins failed validation",
    )
    db.session.commit()

    return failed, len(plugin_ids)


# ==========================================================
# SCHEDULER ENTRY POINT
# ==========================================================

def run_due_automation(now=None):
    """
    Start every scheduled task that is due. Called by the scheduler, so
    it opens its own app context. Each task is isolated: one failing
    does not stop the others. Returns the names of the tasks started,
    for logging and tests.
    """
    with app.app_context():
        now = now or datetime.now(timezone.utc)
        started = []

        settings = db.session.get(SystemSettings, 1)
        if settings is None:
            return started

        if settings.Automatic_Backups:
            try:
                backup_dir = current_app.config["DATABASE_BACKUP_DIR"]
                backups = list_backups(backup_dir)
                last_backup = backups[-1][0] if backups else None
                if is_due(last_backup, BACKUP_INTERVAL, now):
                    backup_databases(
                        database_file_paths(),
                        backup_dir,
                        current_app.config["DATABASE_BACKUP_KEEP"],
                        now,
                    )
                    started.append("backup")
            except Exception:
                current_app.logger.exception("Scheduled database backup failed.")

        if settings.Maintenance_Mode:
            return started

        user_id = get_automation_user_id(settings)
        if user_id is None:
            current_app.logger.warning("No active user to attribute scheduled tasks to; skipping them.")
            return started

        try:
            scan_interval = timedelta(hours=settings.Scan_Frequency)
            if is_due(last_discovery_start(), scan_interval, now) and start_discovery_thread(user_id):
                started.append("network_scan")
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Scheduled network scan failed to start.")

        try:
            update_interval = UPDATE_CHECK_INTERVALS.get(settings.System_Update_Frequency)
            if (
                update_interval is not None
                and is_due(last_plugin_scan_start(), update_interval, now)
                and start_plugin_scan_thread(user_id)
            ):
                started.append("update_check")
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Scheduled plugin update check failed to start.")

        try:
            security_interval = SECURITY_CHECK_INTERVALS.get(settings.Security_Check_Frequency)
            if security_interval is not None and is_due(last_security_check(), security_interval, now):
                run_security_check(user_id)
                started.append("security_check")
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Scheduled security check failed.")

        return started
