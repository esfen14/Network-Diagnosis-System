from flask_login import login_required
from flask import request, current_app
from app.api.helper.database_access.permissions import require_permission
from app.api.system import system_bp
from app import db
from app.history_models import (
    ServiceStatus,
    ServiceStateType,
)
import sqlalchemy as sa

@system_bp.get('/services')
@login_required
@require_permission("sysetem.dashboard")
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
            "check_latency": s.Check_Latency,
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