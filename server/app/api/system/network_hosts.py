"""
network_hosts.py — API routes for the Host Status Table (§2.2).

Routes:
  GET  /system/network-health/hosts
      Full paginated, filterable host status table.
      Supports filter by state, ack status, and free-text hostname search.

  GET  /system/network-health/hosts/<hostname>/detail
      Inline host detail panel: perf data with thresholds, associated service
      mini-list, and full set of host timestamps.

  POST /system/network-health/hosts/acknowledge
      Acknowledge a host-level alert (requires system.acknowledge_alerts).

  DELETE /system/network-health/hosts/acknowledge
      Unacknowledge a host-level alert (requires system.acknowledge_alerts).

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
    HostStatus,
    HostPerfData,
    HostStateType,
    ServiceStatus,
)
from app.system_models import AlertAcknowledgement, AckHistory, AckAction

# ---------------------------------------------------------------------------
# §2.2  Host Status Table
# ---------------------------------------------------------------------------

@system_bp.get("/network-health/hosts")
@login_required
@require_permission("system.network_health")
def list_hosts():
    """
    Return a paginated, filterable list of the latest host status snapshot.

    Query params:
        page            — default 1
        per_page        — default 25, max 100
        sort_by         — hostname (default) | state | last_check | check_latency
        order           — asc (default) | desc
        search          — partial match on hostname
        state           — UP | DOWN | UNREACHABLE
        ack_filter      — all (default) | acknowledged | unacknowledged

    Each item:
    {
        "hostname":        str,
        "state":           str,         // UP / DOWN / UNREACHABLE
        "state_type":      str,         // Soft / Hard
        "last_check":      str | null,  // ISO-8601
        "check_latency":   float,       // seconds
        "plugin_output":   str,
        "is_flapping":     bool,
        "in_downtime":     bool,
        "nagios_ack":      str,         // Nagios-side acknowledgement type
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
        state_arg  = request.args.get("state", default="", type=str).upper()
        ack_filter = request.args.get("ack_filter", default="all", type=str).lower()

        if page < 1:
            return error("Page must be greater than 0.", 400)
        if per_page < 1:
            return error("per_page must be at least 1.", 400)
        if order not in ("asc", "desc"):
            return error("order must be 'asc' or 'desc'.", 400)
        if ack_filter not in ("all", "acknowledged", "unacknowledged"):
            return error("ack_filter must be 'all', 'acknowledged', or 'unacknowledged'.", 400)

        _sort_map = {
            "hostname":      HostStatus.Hostname,
            "state":         HostStatus.Current_State,
            "last_check":    HostStatus.Last_Check,
            "check_latency": HostStatus.Check_Latency,
        }
        sort_col = _sort_map.get(sort_by)
        if sort_col is None:
            return error(f"sort_by must be one of: {list(_sort_map)}", 400)

        # Subquery: most recent snapshot per host.
        latest_subq = (
            sa.select(
                HostStatus.Hostname,
                sa.func.max(HostStatus.Timestamp).label("max_ts"),
            )
            .group_by(HostStatus.Hostname)
            .subquery()
        )

        query = (
            sa.select(HostStatus)
            .join(
                latest_subq,
                sa.and_(
                    HostStatus.Hostname  == latest_subq.c.Hostname,
                    HostStatus.Timestamp == latest_subq.c.max_ts,
                ),
            )
        )

        if search:
            query = query.where(HostStatus.Hostname.ilike(f"%{search}%"))

        if state_arg:
            try:
                state_enum = HostStateType[state_arg]
                query = query.where(HostStatus.Current_State == state_enum)
            except KeyError:
                return error(f"Invalid state: {state_arg}. Must be UP, DOWN, or UNREACHABLE.", 400)

        query = query.order_by(
            sort_col.asc() if order == "asc" else sort_col.desc()
        )

        # Load all current acknowledgements for the ack_filter and ack field.
        ack_rows = db.session.scalars(
            sa.select(AlertAcknowledgement).where(
                AlertAcknowledgement.Service_Name.is_(None)
            )
        ).all()
        ack_map: dict[str, AlertAcknowledgement] = {a.Hostname: a for a in ack_rows}

        # Apply ack filter by building a set of acknowledged hostnames.
        if ack_filter == "acknowledged":
            query = query.where(
                HostStatus.Hostname.in_(list(ack_map.keys()))
            )
        elif ack_filter == "unacknowledged":
            query = query.where(
                HostStatus.Hostname.notin_(list(ack_map.keys()))
            )

        page_result = db.paginate(query, page=page, per_page=per_page, error_out=False)

        items = []
        for h in page_result.items:
            ack = ack_map.get(h.Hostname)
            items.append({
                "hostname":      h.Hostname,
                "state":         h.Current_State.value,
                "state_type":    h.State_Type.value,
                "last_check":    h.Last_Check.isoformat() if h.Last_Check else None,
                "check_latency": h.Check_Latency,
                "plugin_output": h.Plugin_Output,
                "is_flapping":   h.Is_Flapping,
                "in_downtime":   h.Scheduled_Downtime_Depth > 0,
                "nagios_ack":    h.Acknowledgement_Type.value,
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
            "Unexpected error in GET /system/network-health/hosts"
        )
        return error("An unexpected error occurred.", 500)


# ---------------------------------------------------------------------------
# §2.2  Host Detail Panel
# ---------------------------------------------------------------------------

@system_bp.get("/network-health/hosts/<hostname>/detail")
@login_required
@require_permission("system.network_health")
def host_detail(hostname: str):
    """
    Return the inline detail panel for a single host row.

    Includes:
      - All performance metrics with current value, unit, warn/crit thresholds
      - Full set of state timestamps
      - Mini service list with current state badges
      - Acknowledgement if present

    Response shape:
    {
        "hostname":                 str,
        "state":                    str,
        "state_type":               str,
        "plugin_output":            str,
        "last_check":               str | null,
        "last_state_change":        str | null,
        "last_hard_state_change":   str | null,
        "last_time_up":             str | null,
        "last_time_down":           str | null,
        "last_time_unreachable":    str | null,
        "check_latency":            float,
        "check_execution_time":     float,
        "is_flapping":              bool,
        "in_downtime":              bool,
        "nagios_ack":               str,
        "ack": null | { "comment", "acknowledged_by", "acknowledged_at" },
        "perf_data": [
            {
                "metric":    str,
                "value":     float,
                "unit":      str | null,
                "warn":      float | null,
                "crit":      float | null,
                "min":       float | null,
                "max":       float | null,
            }
        ],
        "services": [
            {
                "service":  str,
                "state":    str,
                "plugin_output": str,
                "last_check":    str | null,
            }
        ]
    }
    """
    try:
        # Latest HostStatus row for this hostname.
        latest_subq = (
            sa.select(sa.func.max(HostStatus.Timestamp))
            .where(HostStatus.Hostname == hostname)
            .scalar_subquery()
        )
        host = db.session.scalar(
            sa.select(HostStatus).where(
                HostStatus.Hostname  == hostname,
                HostStatus.Timestamp == latest_subq,
            )
        )

        if host is None:
            return error(f"Host '{hostname}' not found.", 404)

        # Performance data for this host status row.
        perf_rows = db.session.scalars(
            sa.select(HostPerfData).where(
                HostPerfData.HostStatusID == host.HostStatusID
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

        # Latest service for each service on this host.
        svc_subq = (
            sa.select(
                ServiceStatus.Service,
                sa.func.max(ServiceStatus.Timestamp).label("max_ts"),
            )
            .where(ServiceStatus.Hostname == hostname)
            .group_by(ServiceStatus.Service)
            .subquery()
        )
        svc_rows = db.session.scalars(
            sa.select(ServiceStatus).join(
                svc_subq,
                sa.and_(
                    ServiceStatus.Service   == svc_subq.c.Service,
                    ServiceStatus.Timestamp == svc_subq.c.max_ts,
                ),
            ).where(ServiceStatus.Hostname == hostname)
        ).all()

        services = [
            {
                "service":       s.Service,
                "state":         s.Current_State.value,
                "plugin_output": s.Plugin_Output,
                "last_check":    s.Last_Check.isoformat() if s.Last_Check else None,
            }
            for s in svc_rows
        ]

        # Acknowledgement for this host (service_name IS NULL).
        ack = db.session.scalar(
            sa.select(AlertAcknowledgement).where(
                AlertAcknowledgement.Hostname     == hostname,
                AlertAcknowledgement.Service_Name.is_(None),
            )
        )

        return success({
            "hostname":               host.Hostname,
            "state":                  host.Current_State.value,
            "state_type":             host.State_Type.value,
            "plugin_output":          host.Plugin_Output,
            "last_check":             host.Last_Check.isoformat() if host.Last_Check else None,
            "last_state_change":      host.Last_State_Change.isoformat() if host.Last_State_Change else None,
            "last_hard_state_change": host.Last_Hard_State_Change.isoformat() if host.Last_Hard_State_Change else None,
            "last_time_up":           host.Last_Time_Up.isoformat() if host.Last_Time_Up else None,
            "last_time_down":         host.Last_Time_Down.isoformat() if host.Last_Time_Down else None,
            "last_time_unreachable":  host.Last_Time_Unreachable.isoformat() if host.Last_Time_Unreachable else None,
            "check_latency":          host.Check_Latency,
            "check_execution_time":   host.Check_Execution_Time,
            "is_flapping":            host.Is_Flapping,
            "in_downtime":            host.Scheduled_Downtime_Depth > 0,
            "nagios_ack":             host.Acknowledgement_Type.value,
            "ack":                    _serialize_ack(ack),
            "perf_data":              perf_data,
            "services":               services,
        })

    except Exception:
        current_app.logger.exception(
            f"Unexpected error in GET /system/network-health/hosts/{hostname}/detail"
        )
        return error("An unexpected error occurred.", 500)


# ---------------------------------------------------------------------------
# §4  Acknowledge / Unacknowledge a host alert (from the host table)
# ---------------------------------------------------------------------------

@system_bp.post("/network-health/hosts/acknowledge")
@login_required
@require_permission("system.acknowledge_alerts")
def acknowledge_host():
    """
    Acknowledge a host-level alert from the Network Health host table.

    Request body (JSON):
    {
        "hostname": str,
        "comment":  str   // required, must not be blank
    }

    Returns 201 on success, 409 if already acknowledged, 404 if no active alert.
    """
    try:
        body     = request.get_json(silent=True) or {}
        hostname = (body.get("hostname") or "").strip()
        comment  = (body.get("comment") or "").strip()

        if not hostname:
            return error("hostname is required.", 400)
        if not comment:
            return error("comment is required and must not be blank.", 400)

        # Verify the host is actually in a problem state.
        latest_subq = (
            sa.select(sa.func.max(HostStatus.Timestamp))
            .where(HostStatus.Hostname == hostname)
            .scalar_subquery()
        )
        host = db.session.scalar(
            sa.select(HostStatus).where(
                HostStatus.Hostname  == hostname,
                HostStatus.Timestamp == latest_subq,
            )
        )

        if host is None:
            return error(f"Host '{hostname}' not found.", 404)
        if host.Current_State == HostStateType.UP:
            return error("Host is currently UP — no active alert to acknowledge.", 409)

        now = datetime.now(timezone.utc)
        ack = AlertAcknowledgement(
            Hostname        = hostname,
            Service_Name    = None,
            Comment         = comment,
            Acknowledged_At = now,
            AcknowledgedBy  = current_user.UserID,
        )
        db.session.add(ack)
        db.session.add(AckHistory(
            Hostname     = hostname,
            Service_Name = None,
            Action       = AckAction.ACKNOWLEDGED,
            Actioned_At  = now,
            ActorUserID  = current_user.UserID,
            Comment      = comment,
        ))
        db.session.commit()

        return success(_serialize_ack(ack), message="Host alert acknowledged.", status=201)

    except IntegrityError:
        db.session.rollback()
        return error("This host alert is already acknowledged.", 409)
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Unexpected error in POST /system/network-health/hosts/acknowledge"
        )
        return error("An unexpected error occurred.", 500)


@system_bp.delete("/network-health/hosts/acknowledge")
@login_required
@require_permission("system.acknowledge_alerts")
def unacknowledge_host():
    """
    Remove a host-level acknowledgement from the Network Health host table.

    Request body (JSON):
    {
        "hostname": str
    }

    Returns 200 on success, 404 if no acknowledgement exists.
    """
    try:
        body     = request.get_json(silent=True) or {}
        hostname = (body.get("hostname") or "").strip()

        if not hostname:
            return error("hostname is required.", 400)

        ack = db.session.scalar(
            sa.select(AlertAcknowledgement).where(
                AlertAcknowledgement.Hostname     == hostname,
                AlertAcknowledgement.Service_Name.is_(None),
            )
        )

        if ack is None:
            return error("No acknowledgement found for this host.", 404)

        db.session.delete(ack)
        db.session.add(AckHistory(
            Hostname     = hostname,
            Service_Name = None,
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
            "Unexpected error in DELETE /system/network-health/hosts/acknowledge"
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
