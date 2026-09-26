import atexit
import os
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from apscheduler.schedulers.background import BackgroundScheduler
from flask import current_app

from app import app, db
from app.nagios.status import get_status

POLL_INTERVAL_SECONDS = 60

_scheduler: BackgroundScheduler | None = None


def _poll_nagios_status():
    with app.app_context():
        get_status()


def _purge_old_data():
    with app.app_context():
        try:
            from app.system_models import (
                SystemSettings,
                ActivityLog,
                ConfigurationChanges,
                NetworkDiscoveryStatus,
                NCPADeploymentStatus,
                ExportLog,
            )
            from app.history_models import (
                HostStatus,
                HostPerfData,
                ServiceStatus,
                ServicePerfData,
                ProgramStatus,
            )

            settings = db.session.get(SystemSettings, 1)
            if settings is None:
                return

            now = datetime.now(timezone.utc)

            # --- Activity / audit log retention ---------------------------
            log_cutoff = now - timedelta(days=settings.Log_Retention_Days)
            old_log_ids = db.session.scalars(
                sa.select(ActivityLog.LogID).where(ActivityLog.Performed_At < log_cutoff)
            ).all()
            if old_log_ids:
                # Children first — they FK onto ActivityLog.LogID.
                db.session.execute(sa.delete(ConfigurationChanges).where(ConfigurationChanges.LogID.in_(old_log_ids)))
                db.session.execute(sa.delete(NetworkDiscoveryStatus).where(NetworkDiscoveryStatus.LogID.in_(old_log_ids)))
                db.session.execute(sa.delete(NCPADeploymentStatus).where(NCPADeploymentStatus.LogID.in_(old_log_ids)))
                db.session.execute(sa.delete(ExportLog).where(ExportLog.LogID.in_(old_log_ids)))
                db.session.execute(sa.delete(ActivityLog).where(ActivityLog.LogID.in_(old_log_ids)))

            # --- Diagnostic history retention (Nagios snapshots) ----------
            diag_cutoff = now - timedelta(days=settings.Diagnostic_History_Retention_Days)

            old_host_ids = db.session.scalars(
                sa.select(HostStatus.HostStatusID).where(HostStatus.Timestamp < diag_cutoff)
            ).all()
            if old_host_ids:
                db.session.execute(sa.delete(HostPerfData).where(HostPerfData.HostStatusID.in_(old_host_ids)))
                db.session.execute(sa.delete(HostStatus).where(HostStatus.HostStatusID.in_(old_host_ids)))

            old_service_ids = db.session.scalars(
                sa.select(ServiceStatus.ServiceStatusID).where(ServiceStatus.Timestamp < diag_cutoff)
            ).all()
            if old_service_ids:
                db.session.execute(sa.delete(ServicePerfData).where(ServicePerfData.ServiceStatusID.in_(old_service_ids)))
                db.session.execute(sa.delete(ServiceStatus).where(ServiceStatus.ServiceStatusID.in_(old_service_ids)))

            db.session.execute(sa.delete(ProgramStatus).where(ProgramStatus.Timestamp < diag_cutoff))

            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Unexpected error while purging old data")


def init_scheduler():
    """Start the background scheduler, once, in the actual serving process.

    Flask's debug reloader imports this module twice: once in the reloader's
    monitor process (no WERKZEUG_RUN_MAIN) and once in the real worker
    process (WERKZEUG_RUN_MAIN=true). Starting in both would double every
    poll/purge, so skip the monitor process when debug+reloader are active.

    The scheduler is also suppressed entirely under ``app.testing`` so that
    background jobs never race against test-created in-memory databases.
    """
    global _scheduler
    if _scheduler is not None:
        return

    if app.testing:
        return

    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        _poll_nagios_status,
        "interval",
        seconds=POLL_INTERVAL_SECONDS,
        id="nagios_poll",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(),
    )
    _scheduler.add_job(
        _purge_old_data,
        "interval",
        days=1,
        id="retention_purge",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(),
    )
    _scheduler.start()
    atexit.register(lambda: _scheduler.shutdown(wait=False))
