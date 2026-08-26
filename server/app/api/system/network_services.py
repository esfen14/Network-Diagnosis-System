"""
network_services.py — API routes for the Service Status Table (§2.3).

Routes:
  GET  /system/network-health/services
      Full paginated, filterable service status table.
      Supports filter by state, hostname, service name, and ack status.

  GET  /system/network-health/services/<hostname>/<path:service_name>/detail
      Inline service detail panel: perf data with thresholds, state timestamps.

  POST /system/network-health/services/acknowledge
      Acknowledge a service-level alert (requires system.acknowledge_alerts).

  DELETE /system/network-health/services/acknowledge
      Unacknowledge a service-level alert (requires system.acknowledge_alerts).

All routes require login and "system.network_health" permission, except the
acknowledge routes which require "system.acknowledge_alerts".
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from flask import request, current_app
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.api.helper.database_access.permissions import require_permission
from app.api.helper.responses import success, error
from app.api.system import system_bp
from app.history_models import (
    ServiceStatus,
    ServicePerfData,
    ServiceStateType,
)
from app.system_models import AlertAcknowledgement, AckHistory, AckAction

# ---------------------------------------------------------------------------
# §2.3  Service Status Table
# ---------------------------------------------------------------------------

@system_bp.get("/network-health/services")
@login_required
@require_permission("system.network_health")
def list_services():
    """
    Return a paginated, filterable list of the latest service status snapshot.

    Query params:
        page            — default 1
        per_page        — default 25, max 100
        sort_by         — hostname (default) | service | state | last_check | check_latency
        order           — asc (default) | desc
        search          — partial match on hostname OR service name
        hostname        — exact hostname filter
        state           — OK | WARNING | CRITICAL | UNKNOWN
        ack_filter      — all (default) | acknowledged | unacknowledged

    Each item:
    {
        "hostname":      str,
        "service":       str,
        "state":         str,        // OK / WARNING / CRITICAL / UNKNOWN
        "state_type":    str,        // Soft / Hard
        "last_check":    str | null, // ISO-8601
        "check_latency": float,      // seconds
        "plugin_output": str,
        "is_flapping":   bool,
        "in_downtime":   bool,
        "nagios_ack":    str,
        "ack": null | {
            "comment":          str,
            "acknowledged_by":  str,
            "acknowledged_at":  str,
        }
    }
    """
    try:
        page       = request.args.get("page", default=1, type=int)
        per_page   = min(request.args.get("per_page", default=25, type=int), 100)
        sort_by    = request.args.get("sort_by", default="hostname", type=str)
        order      = request.args.get("order", default="asc", type=str).lower()
        search     = request.args.get("search", default="", type=str)
        hostname_f = request.args.get("hostname", default="", type=str)
        state_arg  = request.args.get("state", default="", type=str).upper()
        ack_filter = request.args.get("ack_filter", default="all", type=str).lower()

        if page < 1:
            return error("page must be greater than 0.", 400)
        if per_page < 1:
            return error("per_page must be at least 1.", 400)
        if order not in ("asc", "desc"):
            return error("order must be 'asc' or 'desc'.", 400)
        if ack_filter not in ("all", "acknowledged", "unacknowledged"):
            return error(
                "ack_filter must be 'all', 'acknowledged', or 'unacknowledged'.", 400
            )

        _sort_map = {
            "hostname":      ServiceStatus.Hostname,
            "service":       ServiceStatus.Service,
            "state":         ServiceStatus.Current_State,
            "last_check":    ServiceStatus.Last_Check,
            "check_latency": ServiceStatus.Check_Latency,
        }
        sort_col = _sort_map.get(sort_by)
        if sort_col is None:
            return error(f"sort_by must be one of: {list(_sort_map)}", 400)

        # Subquery: most recent snapshot per (hostname, service).
        latest_subq = (
            sa.select(
                ServiceStatus.Hostname,
                ServiceStatus.Service,
                sa.func.max(ServiceStatus.Timestamp).label("max_ts"),
            )
            .group_by(ServiceStatus.Hostname, ServiceStatus.Service)
            .subquery()
        )

        query = (
            sa.select(ServiceStatus)
            .join(
                latest_subq,
                sa.and_(
                    ServiceStatus.Hostname  == latest_subq.c.Hostname,
                    ServiceStatus.Service   == latest_subq.c.Service,
                    ServiceStatus.Timestamp == latest_subq.c.max_ts,
                ),
            )
        )

        if search:
            query = query.where(
                sa.or_(
                    ServiceStatus.Hostname.ilike(f"%{search}%"),
                    ServiceStatus.Service.ilike(f"%{search}%"),
                )
            )

        if hostname_f:
            query = query.where(ServiceStatus.Hostname == hostname_f)

        if state_arg:
            try:
                state_enum = ServiceStateType[state_arg]
                query = query.where(ServiceStatus.Current_State == state_enum)
            except KeyError:
                return error(
                    f"Invalid state '{state_arg}'. Must be OK, WARNING, CRITICAL, or UNKNOWN.", 400
                )

        query = query.order_by(
            sort_col.asc() if order == "asc" else sort_col.desc()
        )

        # Load current acknowledgements for services (Service_Name is NOT NULL).
        ack_rows = db.session.scalars(
            sa.select(AlertAcknowledgement).where(
                AlertAcknowledgement.Service_Name.isnot(None)
            )
        ).all()
        # Key: (hostname, service_name)
        ack_map: dict[tuple, AlertAcknowledgement] = {
            (a.Hostname, a.Service_Name): a for a in ack_rows
        }

        # Apply ack filter.
        if ack_filter != "all":
            acked_pairs = list(ack_map.keys())
            if acked_pairs:
                in_clause = sa.or_(
                    *[
                        sa.and_(
                            ServiceStatus.Hostname == h,
                            ServiceStatus.Service  == s,
                        )
                        for h, s in acked_pairs
                    ]
                )
            else:
                # No ack records exist at all.
                in_clause = sa.false()

            if ack_filter == "acknowledged":
                query = query.where(in_clause)
            else:  # unacknowledged
                query = query.where(sa.not_(in_clause))

        page_result = db.paginate(query, page=page, per_page=per_page, error_out=False)

        items = []
        for s in page_result.items:
            ack = ack_map.get((s.Hostname, s.Service))
            items.append({
                "hostname":      s.Hostname,
                "service":       s.Service,
                "state":         s.Current_State.value,
                "state_type":    s.State_Type.value,
                "last_check":    s.Last_Check.isoformat() if s.Last_Check else None,
                "check_latency": s.Check_Latency,
                "plugin_output": s.Plugin_Output,
                "is_flapping":   s.Is_Flapping,
                "in_downtime":   s.Scheduled_Downtime_Depth > 0,
                "nagios_ack":    s.Acknowledgement_Type.value,
                "ack":           _serialize_ack(ack),
            })

        return success({
            "items":    items,
            "page":     page_result.page,
            "per_page": page_result.per_page,
            "pages":    page_result.pages,
            "total":    page_result.total,
            "has_next": page_result.has_next,
            "has_prev": page_result.has_prev,
        })

    except Exception:
        current_app.logger.exception(
            "Unexpected error in GET /system/network-health/services"
        )
        return error("An unexpected error occurred.", 500)


# ---------------------------------------------------------------------------
# §2.3  Service Detail Panel
# ---------------------------------------------------------------------------

@system_bp.get("/network-health/services/<hostname>/<path:service_name>/detail")
@login_required
@require_permission("system.network_health")
def service_detail(hostname: str, service_name: str):
    """
    Return the inline detail panel for a single service row.

    Includes:
      - All performance data with current value, unit, warn/crit thresholds
      - Full set of state timestamps (last_ok, last_warning, last_critical, last_unknown)
      - Acknowledgement if present

    Uses <path:service_name> so that service descriptions containing slashes
    (which NCPA services can have) are captured correctly.

    Response shape:
    {
        "hostname":             str,
        "service":              str,
        "state":                str,
        "state_type":           str,
        "plugin_output":        str,
        "last_check":           str | null,
        "last_state_change":    str | null,
        "last_hard_state_change": str | null,
        "last_time_ok":         str | null,
        "last_time_warning":    str | null,
        "last_time_critical":   str | null,
        "last_time_unknown":    str | null,
        "check_latency":        float,
        "check_execution_time": float,
        "is_flapping":          bool,
        "in_downtime":          bool,
        "nagios_ack":           str,
        "ack": null | { "comment", "acknowledged_by", "acknowledged_at" },
        "perf_data": [
            {
                "metric": str,
                "value":  float,
                "unit":   str | null,
                "warn":   float | null,
                "crit":   float | null,
                "min":    float | null,
                "max":    float | null,
            }
        ]
    }
    """
    try:
        latest_subq = (
            sa.select(sa.func.max(ServiceStatus.Timestamp))
            .where(
                ServiceStatus.Hostname == hostname,
                ServiceStatus.Service  == service_name,
            )
            .scalar_subquery()
        )
        svc = db.session.scalar(
            sa.select(ServiceStatus).where(
                ServiceStatus.Hostname  == hostname,
                ServiceStatus.Service   == service_name,
                ServiceStatus.Timestamp == latest_subq,
            )
        )

        if svc is None:
            return error(
                f"Service '{service_name}' on host '{hostname}' not found.", 404
            )

        perf_rows = db.session.scalars(
            sa.select(ServicePerfData).where(
                ServicePerfData.ServiceStatusID == svc.ServiceStatusID
            )
        ).all()

        perf_data = [
            {
                "metric": p.Metric,
                "value":  p.Measured_Value,
                "unit":   p.Unit,
                "warn":   p.Warning_Threshold,
                "crit":   p.Critical_Threshold,
                "min":    p.Minimum,
                "max":    p.Maximum,
            }
            for p in perf_rows
        ]

        ack = db.session.scalar(
            sa.select(AlertAcknowledgement).where(
                AlertAcknowledgement.Hostname     == hostname,
                AlertAcknowledgement.Service_Name == service_name,
            )
        )

        return success({
            "hostname":               svc.Hostname,
            "service":                svc.Service,
            "state":                  svc.Current_State.value,
            "state_type":             svc.State_Type.value,
            "plugin_output":          svc.Plugin_Output,
            "last_check":             svc.Last_Check.isoformat() if svc.Last_Check else None,
            "last_state_change":      svc.Last_State_Change.isoformat() if svc.Last_State_Change else None,
            "last_hard_state_change": svc.Last_Hard_State_Change.isoformat() if svc.Last_Hard_State_Change else None,
            "last_time_ok":           svc.Last_Time_Ok.isoformat() if svc.Last_Time_Ok else None,
            "last_time_warning":      svc.Last_Time_Warning.isoformat() if svc.Last_Time_Warning else None,
            "last_time_critical":     svc.Last_Time_Critical.isoformat() if svc.Last_Time_Critical else None,
            "last_time_unknown":      svc.Last_Time_Unknown.isoformat() if svc.Last_Time_Unknown else None,
            "check_latency":          svc.Check_Latency,
            "check_execution_time":   svc.Check_Execution_Time,
            "is_flapping":            svc.Is_Flapping,
            "in_downtime":            svc.Scheduled_Downtime_Depth > 0,
            "nagios_ack":             svc.Acknowledgement_Type.value,
            "ack":                    _serialize_ack(ack),
            "perf_data":              perf_data,
        })

    except Exception:
        current_app.logger.exception(
            f"Unexpected error in GET /system/network-health/services/"
            f"{hostname}/{service_name}/detail"
        )
        return error("An unexpected error occurred.", 500)


# ---------------------------------------------------------------------------
# §4  Acknowledge / Unacknowledge a service alert
# ---------------------------------------------------------------------------

@system_bp.post("/network-health/services/acknowledge")
@login_required
@require_permission("system.acknowledge_alerts")
def acknowledge_service():
    """
    Acknowledge a service-level alert from the Network Health service table.

    Request body (JSON):
    {
        "hostname":     str,
        "service_name": str,
        "comment":      str   // required, must not be blank
    }

    Returns 201 on success, 409 if already acknowledged, 404 if no active alert.
    """
    try:
        body         = request.get_json(silent=True) or {}
        hostname     = (body.get("hostname") or "").strip()
        service_name = (body.get("service_name") or "").strip()
        comment      = (body.get("comment") or "").strip()

        if not hostname:
            return error("hostname is required.", 400)
        if not service_name:
            return error("service_name is required.", 400)
        if not comment:
            return error("comment is required and must not be blank.", 400)

        # Verify the service is actually in a problem state.
        latest_subq = (
            sa.select(sa.func.max(ServiceStatus.Timestamp))
            .where(
                ServiceStatus.Hostname == hostname,
                ServiceStatus.Service  == service_name,
            )
            .scalar_subquery()
        )
        svc = db.session.scalar(
            sa.select(ServiceStatus).where(
                ServiceStatus.Hostname  == hostname,
                ServiceStatus.Service   == service_name,
                ServiceStatus.Timestamp == latest_subq,
            )
        )

        if svc is None:
            return error(
                f"Service '{service_name}' on host '{hostname}' not found.", 404
            )
        if svc.Current_State == ServiceStateType.OK:
            return error(
                "Service is currently OK — no active alert to acknowledge.", 409
            )

        now = datetime.now(timezone.utc)
        ack = AlertAcknowledgement(
            Hostname        = hostname,
            Service_Name    = service_name,
            Comment         = comment,
            Acknowledged_At = now,
            AcknowledgedBy  = current_user.UserID,
        )
        db.session.add(ack)
        db.session.add(AckHistory(
            Hostname     = hostname,
            Service_Name = service_name,
            Action       = AckAction.ACKNOWLEDGED,
            Actioned_At  = now,
            ActorUserID  = current_user.UserID,
            Comment      = comment,
        ))
        db.session.commit()

        return success(
            _serialize_ack(ack),
            message="Service alert acknowledged.",
            status=201,
        )

    except IntegrityError:
        db.session.rollback()
        return error("This service alert is already acknowledged.", 409)
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Unexpected error in POST /system/network-health/services/acknowledge"
        )
        return error("An unexpected error occurred.", 500)


@system_bp.delete("/network-health/services/acknowledge")
@login_required
@require_permission("system.acknowledge_alerts")
def unacknowledge_service():
    """
    Remove a service-level acknowledgement.

    Request body (JSON):
    {
        "hostname":     str,
        "service_name": str
    }

    Returns 200 on success, 404 if no acknowledgement exists.
    """
    try:
        body         = request.get_json(silent=True) or {}
        hostname     = (body.get("hostname") or "").strip()
        service_name = (body.get("service_name") or "").strip()

        if not hostname:
            return error("hostname is required.", 400)
        if not service_name:
            return error("service_name is required.", 400)

        ack = db.session.scalar(
            sa.select(AlertAcknowledgement).where(
                AlertAcknowledgement.Hostname     == hostname,
                AlertAcknowledgement.Service_Name == service_name,
            )
        )

        if ack is None:
            return error(
                "No acknowledgement found for the given host/service.", 404
            )

        db.session.delete(ack)
        db.session.add(AckHistory(
            Hostname     = hostname,
            Service_Name = service_name,
            Action       = AckAction.UNACKNOWLEDGED,
            Actioned_At  = datetime.now(timezone.utc),
            ActorUserID  = current_user.UserID,
            Comment      = None,
        ))
        db.session.commit()

        return success(message="Acknowledgement removed.")

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Unexpected error in DELETE /system/network-health/services/acknowledge"
        )
        return error("An unexpected error occurred.", 500)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _serialize_ack(ack: AlertAcknowledgement | None) -> dict | None:
    if ack is None:
        return None
    user      = ack.User
    full_name = f"{user.First_Name} {user.Last_Name}"
    return {
        "comment":         ack.Comment,
        "acknowledged_by": full_name,
        "acknowledged_at": ack.Acknowledged_At.isoformat(),
    }
