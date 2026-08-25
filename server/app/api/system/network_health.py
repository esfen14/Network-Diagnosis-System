from flask_login import login_required
from flask import request, current_app
from app.api.helper.database_access.permissions import require_permission
from app.api.system import system_bp
from app.nagios.notifications import (
    request_alerts_history,
    request_current_alerts,
    request_current_alert_count,
    request_alerts_last,
    request_alert_count_last,
)
from app import db
from app.history_models import HostStatus, ServiceStatus
import sqlalchemy as sa


# ─────────────────────────────────────────────────────────────────────────────
# ALERTS
# ─────────────────────────────────────────────────────────────────────────────

@system_bp.get('/alerts')
@login_required
@require_permission("system.alerts")
def get_alerts():
    """
    Query alert history from Nagios archivejson.

    Query params (all optional):
        start_date  — YYYY-MM-DD
        start_time  — HH:MM:SS  (requires start_date)
        end_date    — YYYY-MM-DD
        end_time    — HH:MM:SS  (requires end_date)
        hostname    — filter to one host
        service     — filter to one service
        last_days   — shorthand: alerts from the last N days (overrides date params)
        count_only  — if "true", return only the count
    """
    try:
        last_days = request.args.get("last_days", type=int)
        count_only = request.args.get("count_only", "false").lower() == "true"

        if last_days is not None:
            if count_only:
                data = request_alert_count_last(last_days)
            else:
                data = request_alerts_last(last_days)
        else:
            start_date = request.args.get("start_date")
            start_time = request.args.get("start_time")
            end_date = request.args.get("end_date")
            end_time = request.args.get("end_time")
            hostname = request.args.get("hostname")
            service = request.args.get("service")

            if count_only:
                data = request_current_alert_count()
            else:
                data = request_alerts_history(
                    start_date, start_time,
                    end_date, end_time,
                    hostname, service
                )

        if data is None:
            return {"message": "Failed to retrieve alert data from Nagios."}, 502

        return {"data": data}, 200

    except Exception:
        current_app.logger.exception("Unexpected error in GET /system/alerts")
        return {"message": "An unexpected error occurred."}, 500


@system_bp.get('/alerts/current')
@login_required
@require_permission("system.alerts")
def get_current_alerts():
    """Return today's alert list."""
    try:
        data = request_current_alerts()
        if data is None:
            return {"message": "Failed to retrieve current alerts from Nagios."}, 502
        return {"data": data}, 200
    except Exception:
        current_app.logger.exception("Unexpected error in GET /system/alerts/current")
        return {"message": "An unexpected error occurred."}, 500

# ─────────────────────────────────────────────────────────────────────────────
# NETWORK HEALTH — host + service status queries from the local history DB
# ─────────────────────────────────────────────────────────────────────────────

# needs to be revised
@system_bp.get('/network-health')
@login_required
@require_permission("system.network_health")
def get_network_health():
    """
    Return a paginated list of the latest host + service statuses
    stored in the history database.

    Query params (all optional):
        page        — default 1
        per_page    — default 10, max 100
        sort_by     — hostname (default) | state | timestamp
        order       — asc (default) | desc
        search      — partial match on hostname
        state       — filter by host state: UP | DOWN | UNREACHABLE
    """
    try:
        page = request.args.get("page", default=1, type=int)
        per_page = request.args.get("per_page", default=10, type=int)
        sort_by = request.args.get("sort_by", default="hostname", type=str)
        order = request.args.get("order", default="asc", type=str)
        search = request.args.get("search", default="", type=str)
        state_filter = request.args.get("state", default="", type=str).upper()

        if page < 1:
            return {"message": "Page must be greater than 0."}, 400

        if per_page < 1 or per_page > 100:
            return {"message": "per_page must be between 1 and 100."}, 400

        allowed_sorts = {
            "hostname": HostStatus.Hostname,
            "state": HostStatus.Current_State,
            "timestamp": HostStatus.Timestamp,
        }

        sort_col = allowed_sorts.get(sort_by)
        if sort_col is None:
            return {"message": "Invalid sort field."}, 400

        if order not in ("asc", "desc"):
            return {"message": "Invalid order."}, 400

        # Subquery: pick only the most recent HostStatus row per hostname
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
            from app.history_models import HostStateType
            try:
                state_enum = HostStateType[state_filter]
                query = query.where(HostStatus.Current_State == state_enum)
            except KeyError:
                return {"message": f"Invalid state filter: {state_filter}"}, 400

        if order == "asc":
            query = query.order_by(sort_col.asc())
        else:
            query = query.order_by(sort_col.desc())

        hosts = db.paginate(query, page=page, per_page=per_page, error_out=False)

        items = []
        for h in hosts.items:
            # Collect latest service statuses for this host
            services = db.session.scalars(
                sa.select(ServiceStatus)
                .where(ServiceStatus.Hostname == h.Hostname)
                .order_by(ServiceStatus.Timestamp.desc())
                .limit(50)
            ).all()

            service_list = []
            seen_services: set = set()
            for svc in services:
                if svc.Service in seen_services:
                    continue
                seen_services.add(svc.Service)
                service_list.append({
                    "service": svc.Service,
                    "state": svc.Current_State.value,
                    "plugin_output": svc.Plugin_Output,
                    "last_check": svc.Last_Check.isoformat() if svc.Last_Check else None,
                })

            items.append({
                "hostname": h.Hostname,
                "state": h.Current_State.value,
                "plugin_status": h.Plugin_Status.value,
                "plugin_output": h.Plugin_Output,
                "is_flapping": h.Is_Flapping,
                "notification_enabled": h.Notification_Enabled,
                "last_check": h.Last_Check.isoformat() if h.Last_Check else None,
                "timestamp": h.Timestamp.isoformat() if h.Timestamp else None,
                "services": service_list,
            })

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
            "Unexpected error in GET /system/network-health"
        )
        return {"message": "An unexpected error occurred."}, 500
