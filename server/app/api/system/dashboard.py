from flask_login import login_required
from flask import request, current_app
from app.api.helper.database_access.permissions import require_permission
from app.api.system import system_bp
from app import db
from app.history_models import (
    HostStatus,
    ServiceStatus,
    ProgramStatus,
    HostStateType,
    ServiceStateType,
)
import sqlalchemy as sa


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD — aggregated summary data for the front-end dashboard page
# ─────────────────────────────────────────────────────────────────────────────

# needs to be revied for proper data showcase of the system
@system_bp.get('/dashboard')
@login_required
@require_permission("system.dashboard")
def get_dashboard():
    """
    Return a high-level summary of network health for the dashboard.

    Response shape:
    {
        "program_status": { ... },   # latest Nagios program status
        "host_summary": {
            "total": int,
            "up": int, "down": int, "unreachable": int
        },
        "service_summary": {
            "total": int,
            "ok": int, "warning": int, "critical": int, "unknown": int
        },
        "hosts_down": [ { hostname, state, last_check, plugin_output }, ... ],
        "services_critical": [ { hostname, service, state, last_check, plugin_output }, ... ]
    }
    """
    try:
        # ── Latest program status ────────────────────────────────────────────
        program_row = db.session.scalar(
            sa.select(ProgramStatus)
            .order_by(ProgramStatus.Timestamp.desc())
            .limit(1)
        )

        program_status = None
        if program_row:
            program_status = {
                "timestamp": program_row.Timestamp.isoformat(),
                "version": program_row.Version,
                "update_available": program_row.Update_Available,
                "new_version": program_row.New_Version,
                "nagios_pid": program_row.NagiosPID,
                "enable_notifications": program_row.Enable_Notifications,
                "enable_flap_detection": program_row.Enable_Flap_Detection,
                "daemon_mode": program_row.Daemon_Mode,
                "program_start_time": (
                    program_row.Program_Start_Time.isoformat()
                    if program_row.Program_Start_Time else None
                ),
            }

        # ── Latest host status per host ──────────────────────────────────────
        latest_host_subq = (
            sa.select(
                HostStatus.Hostname,
                sa.func.max(HostStatus.Timestamp).label("max_ts")
            )
            .group_by(HostStatus.Hostname)
            .subquery()
        )

        latest_hosts = db.session.scalars(
            sa.select(HostStatus)
            .join(
                latest_host_subq,
                sa.and_(
                    HostStatus.Hostname == latest_host_subq.c.Hostname,
                    HostStatus.Timestamp == latest_host_subq.c.max_ts,
                )
            )
        ).all()

        host_counts = {s: 0 for s in HostStateType}
        hosts_down = []

        for h in latest_hosts:
            host_counts[h.Current_State] += 1
            if h.Current_State in (HostStateType.DOWN, HostStateType.UNREACHABLE):
                hosts_down.append({
                    "hostname": h.Hostname,
                    "state": h.Current_State.value,
                    "plugin_output": h.Plugin_Output,
                    "last_check": h.Last_Check.isoformat() if h.Last_Check else None,
                })

        host_summary = {
            "total": len(latest_hosts),
            "up": host_counts[HostStateType.UP],
            "down": host_counts[HostStateType.DOWN],
            "unreachable": host_counts[HostStateType.UNREACHABLE],
        }

        # ── Latest service status per (host, service) pair ───────────────────
        latest_svc_subq = (
            sa.select(
                ServiceStatus.Hostname,
                ServiceStatus.Service,
                sa.func.max(ServiceStatus.Timestamp).label("max_ts")
            )
            .group_by(ServiceStatus.Hostname, ServiceStatus.Service)
            .subquery()
        )

        latest_services = db.session.scalars(
            sa.select(ServiceStatus)
            .join(
                latest_svc_subq,
                sa.and_(
                    ServiceStatus.Hostname == latest_svc_subq.c.Hostname,
                    ServiceStatus.Service == latest_svc_subq.c.Service,
                    ServiceStatus.Timestamp == latest_svc_subq.c.max_ts,
                )
            )
        ).all()

        svc_counts = {s: 0 for s in ServiceStateType}
        services_critical = []

        for svc in latest_services:
            svc_counts[svc.Current_State] += 1
            if svc.Current_State in (ServiceStateType.CRITICAL, ServiceStateType.WARNING):
                services_critical.append({
                    "hostname": svc.Hostname,
                    "service": svc.Service,
                    "state": svc.Current_State.value,
                    "plugin_output": svc.Plugin_Output,
                    "last_check": svc.Last_Check.isoformat() if svc.Last_Check else None,
                })

        service_summary = {
            "total": len(latest_services),
            "ok": svc_counts[ServiceStateType.OK],
            "warning": svc_counts[ServiceStateType.WARNING],
            "critical": svc_counts[ServiceStateType.CRITICAL],
            "unknown": svc_counts[ServiceStateType.UNKNOWN],
        }

        return {
            "program_status": program_status,
            "host_summary": host_summary,
            "service_summary": service_summary,
            "hosts_down": hosts_down,
            "services_critical": services_critical,
        }, 200

    except Exception:
        current_app.logger.exception(
            "Unexpected error in GET /system/dashboard"
        )
        return {"message": "An unexpected error occurred."}, 500
