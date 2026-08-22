from flask_login import login_required
from flask import request, current_app
from app.api.helper.database_access.permissions import require_permission
from app.api.monitoring import monitoring_bp
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

@monitoring_bp.get('/dashboard')
@login_required
@require_permission("monitoring.dashboard")
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
            "Unexpected error in GET /monitoring/dashboard"
        )
        return {"message": "An unexpected error occurred."}, 500


@monitoring_bp.get('/dashboard/hosts')
@login_required
@require_permission("monitoring.dashboard")
def get_dashboard_hosts():
    """
    Return a paginated list of latest host statuses, for the dashboard hosts table.

    Query params (all optional):
        page        — default 1
        per_page    — default 10, max 100
        order       — asc | desc (by hostname, default asc)
        search      — partial match on hostname
        state       — UP | DOWN | UNREACHABLE
    """
    try:
        page = request.args.get("page", default=1, type=int)
        per_page = request.args.get("per_page", default=10, type=int)
        order = request.args.get("order", default="asc", type=str)
        search = request.args.get("search", default="", type=str)
        state_filter = request.args.get("state", default="", type=str).upper()

        if page < 1:
            return {"message": "Page must be greater than 0."}, 400
        if per_page < 1 or per_page > 100:
            return {"message": "per_page must be between 1 and 100."}, 400
        if order not in ("asc", "desc"):
            return {"message": "Invalid order."}, 400

        latest_subq = (
            sa.select(
                HostStatus.Hostname,
                sa.func.max(HostStatus.Timestamp).label("max_ts")
            )
            .group_by(HostStatus.Hostname)
            .subquery()
        )

        query = (
            sa.select(HostStatus)
            .join(
                latest_subq,
                sa.and_(
                    HostStatus.Hostname == latest_subq.c.Hostname,
                    HostStatus.Timestamp == latest_subq.c.max_ts,
                )
            )
        )

        if search:
            query = query.where(HostStatus.Hostname.ilike(f"%{search}%"))

        if state_filter:
            try:
                state_enum = HostStateType[state_filter]
                query = query.where(HostStatus.Current_State == state_enum)
            except KeyError:
                return {"message": f"Invalid state filter: {state_filter}"}, 400

        if order == "asc":
            query = query.order_by(HostStatus.Hostname.asc())
        else:
            query = query.order_by(HostStatus.Hostname.desc())

        hosts = db.paginate(query, page=page, per_page=per_page, error_out=False)

        items = [{
            "hostname": h.Hostname,
            "state": h.Current_State.value,
            "plugin_status": h.Plugin_Status.value,
            "plugin_output": h.Plugin_Output,
            "is_flapping": h.Is_Flapping,
            "check_latency": h.Check_Latency,
            "check_execution_time": h.Check_Execution_Time,
            "last_check": h.Last_Check.isoformat() if h.Last_Check else None,
            "next_check": h.Next_Check.isoformat() if h.Next_Check else None,
            "timestamp": h.Timestamp.isoformat() if h.Timestamp else None,
        } for h in hosts.items]

        return {
            "items": items,
            "page": hosts.page,
            "per_page": hosts.per_page,
            "pages": hosts.pages,
            "total": hosts.total,
            "has_next": hosts.has_next,
            "has_prev": hosts.has_prev,
        }, 200

    except Exception:
        current_app.logger.exception(
            "Unexpected error in GET /monitoring/dashboard/hosts"
        )
        return {"message": "An unexpected error occurred."}, 500


@monitoring_bp.get('/dashboard/services')
@login_required
@require_permission("monitoring.dashboard")
def get_dashboard_services():
    """
    Return a paginated list of latest service statuses, for the dashboard services table.

    Query params (all optional):
        page        — default 1
        per_page    — default 10, max 100
        order       — asc | desc (by hostname then service, default asc)
        search      — partial match on hostname or service name
        hostname    — filter to one host
        state       — OK | WARNING | CRITICAL | UNKNOWN
    """
    try:
        page = request.args.get("page", default=1, type=int)
        per_page = request.args.get("per_page", default=10, type=int)
        order = request.args.get("order", default="asc", type=str)
        search = request.args.get("search", default="", type=str)
        hostname_filter = request.args.get("hostname", default="", type=str)
        state_filter = request.args.get("state", default="", type=str).upper()

        if page < 1:
            return {"message": "Page must be greater than 0."}, 400
        if per_page < 1 or per_page > 100:
            return {"message": "per_page must be between 1 and 100."}, 400
        if order not in ("asc", "desc"):
            return {"message": "Invalid order."}, 400

        latest_subq = (
            sa.select(
                ServiceStatus.Hostname,
                ServiceStatus.Service,
                sa.func.max(ServiceStatus.Timestamp).label("max_ts")
            )
            .group_by(ServiceStatus.Hostname, ServiceStatus.Service)
            .subquery()
        )

        query = (
            sa.select(ServiceStatus)
            .join(
                latest_subq,
                sa.and_(
                    ServiceStatus.Hostname == latest_subq.c.Hostname,
                    ServiceStatus.Service == latest_subq.c.Service,
                    ServiceStatus.Timestamp == latest_subq.c.max_ts,
                )
            )
        )

        if search:
            query = query.where(
                sa.or_(
                    ServiceStatus.Hostname.ilike(f"%{search}%"),
                    ServiceStatus.Service.ilike(f"%{search}%"),
                )
            )

        if hostname_filter:
            query = query.where(ServiceStatus.Hostname == hostname_filter)

        if state_filter:
            try:
                state_enum = ServiceStateType[state_filter]
                query = query.where(ServiceStatus.Current_State == state_enum)
            except KeyError:
                return {"message": f"Invalid state filter: {state_filter}"}, 400

        if order == "asc":
            query = query.order_by(
                ServiceStatus.Hostname.asc(),
                ServiceStatus.Service.asc()
            )
        else:
            query = query.order_by(
                ServiceStatus.Hostname.desc(),
                ServiceStatus.Service.desc()
            )

        services = db.paginate(query, page=page, per_page=per_page, error_out=False)

        items = [{
            "hostname": s.Hostname,
            "service": s.Service,
            "state": s.Current_State.value,
            "plugin_output": s.Plugin_Output,
            "is_flapping": s.Is_Flapping,
            "check_latency": s.Check_Latency,
            "check_execution_time": s.Check_Execution_Time,
            "last_check": s.Last_Check.isoformat() if s.Last_Check else None,
            "next_check": s.Next_Check.isoformat() if s.Next_Check else None,
            "timestamp": s.Timestamp.isoformat() if s.Timestamp else None,
        } for s in services.items]

        return {
            "items": items,
            "page": services.page,
            "per_page": services.per_page,
            "pages": services.pages,
            "total": services.total,
            "has_next": services.has_next,
            "has_prev": services.has_prev,
        }, 200

    except Exception:
        current_app.logger.exception(
            "Unexpected error in GET /monitoring/dashboard/services"
        )
        return {"message": "An unexpected error occurred."}, 500
