from app.plugin_models import PluginScanStatus, PluginScanStatusValue
from flask import current_app
import sqlalchemy as sa
from app import db
from app.logging.user_activity import create_user_log
# Reuse calculate_progress rather than duplicating it — it's a pure
# math helper, not actually Network-Discovery-specific.
from app.logging.network_discovery_status import calculate_progress  # noqa: F401


def create_plugin_scan_status(user_id):
    try:
        user_log = create_user_log(user_id, "Scanning Nagios Plugin Directory")

        plugin_scan_status = PluginScanStatus(
            Status=PluginScanStatusValue.RUNNING,
            Progress=0,
            Message="Plugin scan starting.",
            LogID=user_log.LogID
        )

        db.session.add(plugin_scan_status)
        db.session.commit()

        return plugin_scan_status
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(f"Cannot create plugin scan status {e}")
        return None


def update_plugin_scan_status(plugin_scan_status_id, status, progress, message, completed_at=None, error=None):
    try:
        plugin_scan_status = db.session.scalar(
            sa.select(PluginScanStatus).where(
                PluginScanStatus.PluginScanStatusID == plugin_scan_status_id
            )
        )

        if plugin_scan_status is None:
            raise ValueError(
                f"Plugin scan status {plugin_scan_status_id} does not exist"
            )

        plugin_scan_status.Status = status
        plugin_scan_status.Progress = progress
        plugin_scan_status.Message = message
        plugin_scan_status.Completed_At = completed_at
        plugin_scan_status.Error = error

        db.session.commit()

        return plugin_scan_status
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(f"Cannot update plugin scan status {e}")
        return None


def get_plugin_scan_status():
    try:
        return db.session.scalar(
            sa.select(PluginScanStatus)
            .order_by(PluginScanStatus.Start_At.desc())
            .limit(1)
        )
    except Exception as e:
        current_app.logger.exception("An Error Occurred")
        return None
