"""
dashboard.py — API routes for the Dashboard page.

Sections from Display_Requirements.md covered here:
  §1.1  Monitoring System Status  (GET /system/dashboard/status)
  §1.2  Summary Stat Cards        (part of GET /system/dashboard/summary)
  §1.3  Always-Visible Network Metrics  (part of GET /system/dashboard/summary)
  §1.4  Conditional NCPA Resource Metrics  (part of GET /system/dashboard/summary)
  §1.5  Service State Summary     (part of GET /system/dashboard/summary)
  §1.6  Active Alerts Feed        (GET /system/dashboard/alerts)
        Acknowledge single alert  (POST /system/dashboard/alerts/acknowledge)
        Acknowledge all visible   (POST /system/dashboard/alerts/acknowledge-all)
        Unacknowledge             (DELETE /system/dashboard/alerts/acknowledge)
  §1.7  Recent Notifications      (GET /system/dashboard/notifications)

All routes require login and the "system.dashboard" permission except the
acknowledge routes which additionally require "system.acknowledge_alerts".

Alert data source
-----------------
The active alerts feed (§1.6) sources data from the same history.db snapshots
as the "Active Alerts" stat card on GET /dashboard/summary (see statistics.py
active_alert_count()). An alert is any host/service whose latest polled
snapshot is in a problem state (not UP / OK). This keeps the stat card and
the feed always in agreement, and reflects "right now" as of the last poll
cycle rather than reconstructing state from Nagios' archived event log.

Historical alert *events* (state-change history over an arbitrary time range)
are a different concern, served by GET /system/history/alerts in history.py,
which does query Nagios' archivejson.cgi — that endpoint needs the durable
event log because it answers "what happened between two dates", a question
periodic history.db snapshots cannot answer without gaps.
"""

from datetime import datetime, timezone, timedelta

import sqlalchemy as sa
from flask import request, current_app
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.api.helper.database_access.permissions import require_permission
from app.api.helper.responses import success, error
from app.api.system import system_bp
from app.api.system.statistics import (
    get_latest_hosts,
    get_latest_services,
    host_counts,
    service_counts,
    active_alert_count,
    avg_ping_metrics,
    ncpa_averages,
    nagios_server_resources,
    NAGIOS_HOST,
)
from app.history_models import (
    HostStatus,
    HostStateType,
    ServiceStatus,
    ServiceStateType,
    ProgramStatus,
)
from app.nagios.notifications import request_notifications_last
from app.system_models import AlertAcknowledgement, AckHistory, AckAction

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_alert_row(
    type_: str,
    hostname: str,
    service_name: str | None,
    state: str,
    state_type: str,
    changed_at: datetime,
    plugin_output: str,
    in_downtime: bool,
    ack: AlertAcknowledgement | None,
    now_ts: int,
) -> dict:
    """Build a single alert row for the active alerts feed from a HostStatus/ServiceStatus row."""
    if changed_at.tzinfo is None:
        changed_at = changed_at.replace(tzinfo=timezone.utc)
    ts = int(changed_at.timestamp())
    return {
        "type":             type_,
        "hostname":         hostname,
        "service_name":     service_name,
        "state":            state,
        "state_type":       state_type,
        "timestamp":        ts,
        "duration_seconds": max(now_ts - ts, 0),
        "plugin_output":    plugin_output,
        "in_downtime":      in_downtime,
        "ack":              _serialize_ack(ack),
    }


def _serialize_ack(ack: AlertAcknowledgement | None) -> dict | None:
    """Serialize an AlertAcknowledgement row (or None) into a frontend-ready dict."""
    if ack is None:
        return None
    user      = ack.User
    full_name = f"{user.First_Name} {user.Last_Name}"
    return {
        "comment":         ack.Comment,
        "acknowledged_by": full_name,
        "acknowledged_at": ack.Acknowledged_At.isoformat(),
    }


def _host_is_active_alert(hostname: str) -> bool:
    """True if the latest HostStatus row for this host is in a problem state."""
    subq = (
        sa.select(sa.func.max(HostStatus.Timestamp))
        .where(HostStatus.Hostname == hostname)
        .scalar_subquery()
    )
    row = db.session.scalar(
        sa.select(HostStatus).where(
            HostStatus.Hostname  == hostname,
            HostStatus.Timestamp == subq,
        )
    )
    return row is not None and row.Current_State != HostStateType.UP


def _service_is_active_alert(hostname: str, service_name: str) -> bool:
    """True if the latest ServiceStatus row for this (host, service) is in a problem state."""
    subq = (
        sa.select(sa.func.max(ServiceStatus.Timestamp))
        .where(
            ServiceStatus.Hostname == hostname,
            ServiceStatus.Service  == service_name,
        )
        .scalar_subquery()
    )
    row = db.session.scalar(
        sa.select(ServiceStatus).where(
            ServiceStatus.Hostname  == hostname,
            ServiceStatus.Service   == service_name,
            ServiceStatus.Timestamp == subq,
        )
    )
    return row is not None and row.Current_State != ServiceStateType.OK


def _build_nagios_info(prog: ProgramStatus | None) -> dict:
    """Build the "nagios" section of GET /dashboard/status from the latest
    ProgramStatus row, or an all-None dict if Nagios has never reported."""
    if prog is None:
        return {
            "running":               False,
            "pid":                   None,
            "version":               None,
            "program_start_time":    None,
            "last_status_update":    None,
            "active_host_checks":    None,
            "active_service_checks": None,
            "notifications_enabled": None,
            "enable_flap_detection": None,
        }

    program_start_time = None
    if prog.Program_Start_Time is not None:
        program_start_time = prog.Program_Start_Time.isoformat()

    return {
        # Nagios is considered "running" if it reported a PID.
        "running":               prog.NagiosPID is not None,
        "pid":                   prog.NagiosPID,
        "version":               prog.Version,
        "program_start_time":    program_start_time,
        # Timestamp of the most-recent status write is the ProgramStatus row timestamp.
        "last_status_update":    prog.Timestamp.isoformat(),
        "active_host_checks":    prog.Active_Host_Checks_Enabled,
        "active_service_checks": prog.Active_Service_Checks_Enabled,
        "notifications_enabled": prog.Enable_Notifications,
        "enable_flap_detection": prog.Enable_Flap_Detection,
    }


def _build_ack_map() -> dict[tuple, AlertAcknowledgement]:
    """Return all app-side acknowledgements keyed by (hostname, service_name)."""
    ack_rows = db.session.scalars(sa.select(AlertAcknowledgement)).all()
    ack_map: dict[tuple, AlertAcknowledgement] = {}
    for a in ack_rows:
        ack_map[(a.Hostname, a.Service_Name)] = a
    return ack_map


def _passes_ack_filter(ack_filter: str, ack: AlertAcknowledgement | None) -> bool:
    """True if an alert with the given acknowledgement (or None) should be
    included under the requested ack_filter ("all" | "unacknowledged" | "acknowledged")."""
    if ack_filter == "unacknowledged" and ack is not None:
        return False
    if ack_filter == "acknowledged" and ack is None:
        return False
    return True


def _collect_active_alerts(
    ack_filter: str,
    ack_map: dict[tuple, AlertAcknowledgement],
    now_ts: int,
) -> list[dict]:
    """Build the unsorted active alerts feed (§1.6) from the latest history.db
    snapshot per host/service, applying ack_filter along the way."""
    alerts: list[dict] = []

    for h in get_latest_hosts():
        if h.Current_State == HostStateType.UP:
            continue
        ack = ack_map.get((h.Hostname, None))
        if not _passes_ack_filter(ack_filter, ack):
            continue

        changed_at = h.Timestamp
        if h.Last_State_Change is not None:
            changed_at = h.Last_State_Change

        in_downtime = h.Scheduled_Downtime_Depth > 0

        alerts.append(_build_alert_row(
            type_         = "host",
            hostname      = h.Hostname,
            service_name  = None,
            state         = h.Current_State.name,
            state_type    = h.State_Type.name,
            changed_at    = changed_at,
            plugin_output = h.Plugin_Output,
            in_downtime   = in_downtime,
            ack           = ack,
            now_ts        = now_ts,
        ))

    for s in get_latest_services():
        if s.Current_State == ServiceStateType.OK:
            continue
        ack = ack_map.get((s.Hostname, s.Service))
        if not _passes_ack_filter(ack_filter, ack):
            continue

        changed_at = s.Timestamp
        if s.Last_State_Change is not None:
            changed_at = s.Last_State_Change

        in_downtime = s.Scheduled_Downtime_Depth > 0

        alerts.append(_build_alert_row(
            type_         = "service",
            hostname      = s.Hostname,
            service_name  = s.Service,
            state         = s.Current_State.name,
            state_type    = s.State_Type.name,
            changed_at    = changed_at,
            plugin_output = s.Plugin_Output,
            in_downtime   = in_downtime,
            ack           = ack,
            now_ts        = now_ts,
        ))

    return alerts


# Severity rank used by _alert_sort_key() — lower sorts first.
_ALERT_SEVERITY = {
    "down":         0,
    "unreachable":  1,
    "critical":     0,
    "warning":      1,
    "unknown":      2,
}


def _alert_sort_key(alert: dict) -> tuple:
    """Sort key for the active alerts feed: downtime last → severity →
    acked below unacked → longest duration first within each group."""
    sev = _ALERT_SEVERITY.get(alert["state"].lower(), 2)

    acked = 0
    if alert["ack"] is not None:
        acked = 1

    downtime = 0
    if alert["in_downtime"]:
        downtime = 1

    return (downtime, sev, acked, -alert["duration_seconds"])


def _new_ack(
    hostname: str,
    service_name: str | None,
    comment: str,
    acknowledged_at: datetime,
) -> AlertAcknowledgement:
    """Build a new (unsaved) AlertAcknowledgement row for the current user."""
    return AlertAcknowledgement(
        Hostname        = hostname,
        Service_Name    = service_name,
        Comment         = comment,
        Acknowledged_At = acknowledged_at,
        AcknowledgedBy  = current_user.UserID,
    )


def _new_ack_history(
    hostname: str,
    service_name: str | None,
    action: AckAction,
    actioned_at: datetime,
    comment: str | None = None,
) -> AckHistory:
    """Build a new (unsaved) AckHistory row for the current user."""
    return AckHistory(
        Hostname     = hostname,
        Service_Name = service_name,
        Action       = action,
        Actioned_At  = actioned_at,
        ActorUserID  = current_user.UserID,
        Comment      = comment,
    )


def _normalize_notification(item: dict) -> dict:
    """Normalize one raw Nagios archivejson notification event into the
    frontend-ready shape used by GET /dashboard/notifications.

    Field names differ between archivejson versions/mock data — handles
    "hostname"/"host_name" and millisecond vs. second timestamps.
    """
    hostname = item.get("hostname") or item.get("host_name") or ""
    raw_ts   = item.get("timestamp") or 0

    # Convert millisecond timestamps to seconds if needed.
    ts_sec = raw_ts
    if raw_ts > 9_999_999_999:
        ts_sec = raw_ts // 1000

    return {
        "timestamp":    ts_sec,
        "type":         (item.get("notificationtype") or "").upper(),
        "hostname":     hostname,
        "service_name": item.get("servicedesc") or item.get("description") or None,
        "state":        item.get("notificationreason") or item.get("state") or "",
        "contact":      item.get("contact") or "",
        "message":      (item.get("output") or item.get("plugin_output") or "")[:200],
    }


def _notification_sort_key(notification: dict) -> int:
    """Sort key for GET /dashboard/notifications — used with reverse=True so
    the most recent notification (highest timestamp) comes first."""
    return notification["timestamp"] or 0

# ---------------------------------------------------------------------------
# §1.1  Monitoring System Status
# ---------------------------------------------------------------------------

@system_bp.get("/dashboard/status")
@login_required
@require_permission("system.dashboard")
def dashboard_status():
    """
    Return the health of the monitoring system itself (Nagios process state,
    version, uptime, check flags) plus the Nagios server's own resource metrics
    (check_load, check_disk, check_swap).

    Response shape:
    {
        "nagios": {
            "running":                  bool,
            "pid":                      int | null,
            "version":                  str | null,
            "program_start_time":       str (ISO-8601) | null,
            "last_status_update":       str (ISO-8601) | null,
            "active_host_checks":       bool,
            "active_service_checks":    bool,
            "notifications_enabled":    bool,
            "enable_flap_detection":    bool,
        },
        "server_resources": {
            "cpu_load": {
                "configured": bool,
                "load1": float | null,
                "load5": float | null,
                "load15": float | null,
            },
            "disk": {
                "configured": bool,
                "mounts": [ { "mount", "used_bytes", "warn", "crit" } ]
            },
            "swap": {
                "configured": bool,
                "swap_used_mb": float | null,
                "warn": float | null,
                "crit": float | null,
            }
        }
    }
    """
    try:
        # ── Latest ProgramStatus row ─────────────────────────────────────────
        prog = db.session.scalar(
            sa.select(ProgramStatus)
            .order_by(ProgramStatus.Timestamp.desc())
            .limit(1)
        )

        nagios_info = _build_nagios_info(prog)

        # ── Nagios server resource checks ────────────────────────────────────
        latest_services = get_latest_services()
        resources = nagios_server_resources(latest_services)

        return success({
            "nagios":            nagios_info,
            "server_resources":  resources,
        })

    except Exception:
        current_app.logger.exception("Unexpected error in GET /system/dashboard/status")
        return error("An unexpected error occurred.", 500)


# ---------------------------------------------------------------------------
# §1.2, §1.3, §1.4, §1.5  Summary + Network Metrics + NCPA + State Charts
# ---------------------------------------------------------------------------

@system_bp.get("/dashboard/summary")
@login_required
@require_permission("system.dashboard")
def dashboard_summary():
    """
    Return all at-a-glance summary data for the dashboard stat cards,
    always-visible network metrics, optional NCPA averages, and the
    service/host state proportions for the donut chart.

    Response shape:
    {
        "hosts": {
            "total": int, "up": int, "down": int, "unreachable": int,
            "flapping": int, "in_downtime": int
        },
        "services": {
            "total": int, "ok": int, "warning": int, "critical": int,
            "unknown": int, "flapping": int, "in_downtime": int
        },
        "active_alerts": {
            "total": int, "critical": int, "warning": int, "unknown": int
        },
        "ping_metrics": {
            "configured": bool,
            "avg_rta_ms": float | null,
            "avg_packet_loss_pct": float | null,
            "host_count": int,
            "insufficient_data"?: bool       // present only when host_count < 2
        },
        "ncpa_metrics": null | {             // null = NCPA not deployed, hide section
            "ncpa_host_count": int,
            "total_host_count": int,
            "avg_cpu_pct": float | null,
            "avg_disk_pct": float | null,
            "avg_memory_pct": float | null,
        }
    }
    """
    try:
        latest_hosts    = get_latest_hosts()
        latest_services = get_latest_services()

        h_counts  = host_counts(latest_hosts)
        s_counts  = service_counts(latest_services)
        a_counts  = active_alert_count(latest_hosts, latest_services)
        ping      = avg_ping_metrics(latest_hosts)
        ncpa      = ncpa_averages(latest_services, latest_hosts)

        return success({
            "hosts":         h_counts,
            "services":      s_counts,
            "active_alerts": a_counts,
            "ping_metrics":  ping,
            "ncpa_metrics":  ncpa,
        })

    except Exception:
        current_app.logger.exception("Unexpected error in GET /system/dashboard/summary")
        return error("An unexpected error occurred.", 500)


# ---------------------------------------------------------------------------
# §1.6  Active Alerts Feed
# ---------------------------------------------------------------------------

@system_bp.get("/dashboard/alerts")
@login_required
@require_permission("system.dashboard")
def dashboard_alerts():
    """
    Return the active alerts feed sourced from the latest history.db snapshot
    per host/service — the same source as the "Active Alerts" stat card on
    GET /dashboard/summary.

    Any host not in HostStateType.UP, or service not in ServiceStateType.OK,
    is considered an active alert. This reflects Nagios' current state as of
    the last poll cycle.

    Query params:
        limit       — max rows to return (default 15, max 100)
        ack_filter  — "all" (default) | "unacknowledged" | "acknowledged"

    Each alert row:
    {
        "type":              "host" | "service",
        "hostname":          str,
        "service_name":      str | null,
        "state":             str,           // e.g. WARNING, CRITICAL, DOWN
        "state_type":        str,           // "SOFT" | "HARD"
        "timestamp":         int,           // UNIX timestamp of the last state change
        "duration_seconds":  int,           // seconds since the state-change event
        "plugin_output":     str,
        "in_downtime":       bool,
        "ack": null | {
            "comment":          str,
            "acknowledged_by":  str,        // user's full name
            "acknowledged_at":  str,        // ISO-8601
        }
    }
    """
    try:
        limit      = min(request.args.get("limit", default=15, type=int), 100)
        ack_filter = request.args.get("ack_filter", default="all", type=str).lower()

        if ack_filter not in ("all", "unacknowledged", "acknowledged"):
            return error("ack_filter must be 'all', 'unacknowledged', or 'acknowledged'.", 400)

        ack_map = _build_ack_map()
        now_ts  = int(datetime.now(timezone.utc).timestamp())

        alerts = _collect_active_alerts(ack_filter, ack_map, now_ts)
        alerts.sort(key=_alert_sort_key)
        alerts = alerts[:limit]

        return success({
            "alerts":      alerts,
            "total_shown": len(alerts),
        })

    except Exception:
        current_app.logger.exception("Unexpected error in GET /system/dashboard/alerts")
        return error("An unexpected error occurred.", 500)


# ---------------------------------------------------------------------------
# §4.4  Acknowledge a single alert
# ---------------------------------------------------------------------------

@system_bp.post("/dashboard/alerts/acknowledge")
@login_required
@require_permission("system.acknowledge_alerts")
def acknowledge_alert():
    """
    Acknowledge a single host or service alert.

    Request body (JSON):
    {
        "hostname":     str,          // required
        "service_name": str | null,   // null for host-level alerts
        "comment":      str           // required, must not be blank
    }

    Returns 201 on success.
    Returns 409 if already acknowledged (use DELETE to unacknowledge first).
    """
    try:
        body = request.get_json(silent=True) or {}
        hostname     = (body.get("hostname") or "").strip()
        service_name = (body.get("service_name") or "").strip() or None
        comment      = (body.get("comment") or "").strip()

        if not hostname:
            return error("hostname is required.", 400)
        if not comment:
            return error("comment is required and must not be blank.", 400)

        # Verify the alert actually exists and is in a problem state.
        if service_name:
            exists = _service_is_active_alert(hostname, service_name)
        else:
            exists = _host_is_active_alert(hostname)

        if not exists:
            return error(
                "No active alert found for the given host/service. "
                "The alert may have already resolved.", 404
            )

        now = datetime.now(timezone.utc)
        ack = _new_ack(hostname, service_name, comment, now)
        db.session.add(ack)
        db.session.add(_new_ack_history(hostname, service_name, AckAction.ACKNOWLEDGED, now, comment))
        db.session.commit()

        return success(
            _serialize_ack(ack),
            message="Alert acknowledged.",
            status=201,
        )

    except IntegrityError:
        db.session.rollback()
        return error("This alert is already acknowledged.", 409)
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Unexpected error in POST /system/dashboard/alerts/acknowledge"
        )
        return error("An unexpected error occurred.", 500)


# ---------------------------------------------------------------------------
# §4.5  Acknowledge all visible alerts
# ---------------------------------------------------------------------------

@system_bp.post("/dashboard/alerts/acknowledge-all")
@login_required
@require_permission("system.acknowledge_alerts")
def acknowledge_all_alerts():
    """
    Acknowledge a batch of alerts in one operation.

    Request body (JSON):
    {
        "comment":   str,                   // required, applied to all
        "alerts": [                          // list of alerts to acknowledge
            { "hostname": str, "service_name": str | null },
            ...
        ]
    }

    Returns 200 with a count of newly acknowledged alerts.
    Already-acknowledged alerts in the list are silently skipped.
    """
    try:
        body    = request.get_json(silent=True) or {}
        comment = (body.get("comment") or "").strip()
        alerts  = body.get("alerts") or []

        if not comment:
            return error("comment is required and must not be blank.", 400)
        if not alerts:
            return error("alerts list must not be empty.", 400)

        now = datetime.now(timezone.utc)
        created = 0
        skipped = 0

        for item in alerts:
            hostname     = (item.get("hostname") or "").strip()
            service_name = (item.get("service_name") or "").strip() or None

            if not hostname:
                continue

            # Skip if already acked.
            already = db.session.scalar(
                sa.select(sa.exists().where(
                    AlertAcknowledgement.Hostname == hostname,
                    AlertAcknowledgement.Service_Name == service_name,
                ))
            )
            if already:
                skipped += 1
                continue

            db.session.add(_new_ack(hostname, service_name, comment, now))
            db.session.add(_new_ack_history(hostname, service_name, AckAction.ACKNOWLEDGED, now, comment))
            created += 1

        db.session.commit()

        return success({
            "acknowledged": created,
            "skipped":      skipped,
        }, message=f"Acknowledged {created} alert(s).")

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Unexpected error in POST /system/dashboard/alerts/acknowledge-all"
        )
        return error("An unexpected error occurred.", 500)


# ---------------------------------------------------------------------------
# §4.6  Unacknowledge a single alert
# ---------------------------------------------------------------------------

@system_bp.delete("/dashboard/alerts/acknowledge")
@login_required
@require_permission("system.acknowledge_alerts")
def unacknowledge_alert():
    """
    Remove an acknowledgement from a single alert.

    Request body (JSON):
    {
        "hostname":     str,
        "service_name": str | null
    }

    Returns 200 on success. Returns 404 if no acknowledgement exists.
    """
    try:
        body         = request.get_json(silent=True) or {}
        hostname     = (body.get("hostname") or "").strip()
        service_name = (body.get("service_name") or "").strip() or None

        if not hostname:
            return error("hostname is required.", 400)

        ack = db.session.scalar(
            sa.select(AlertAcknowledgement).where(
                AlertAcknowledgement.Hostname     == hostname,
                AlertAcknowledgement.Service_Name == service_name,
            )
        )

        if ack is None:
            return error("No acknowledgement found for the given host/service.", 404)

        db.session.delete(ack)
        db.session.add(_new_ack_history(
            hostname, service_name, AckAction.UNACKNOWLEDGED, datetime.now(timezone.utc)
        ))
        db.session.commit()

        return success(message="Acknowledgement removed.")

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Unexpected error in DELETE /system/dashboard/alerts/acknowledge"
        )
        return error("An unexpected error occurred.", 500)


# ---------------------------------------------------------------------------
# §1.7  Recent Notifications
# ---------------------------------------------------------------------------

@system_bp.get("/dashboard/notifications")
@login_required
@require_permission("system.dashboard")
def dashboard_notifications():
    # May be unecessary due to notifications.py
    """
    Return the 5 most recent Nagios notification events.

    Response shape:
    {
        "notifications": [
            {
                "timestamp":    int,    // UNIX timestamp from Nagios
                "type":         str,    // "HOST" or "SERVICE"
                "hostname":     str,
                "service_name": str | null,
                "state":        str,
                "contact":      str,
                "message":      str     // truncated to 200 chars
            },
            ...
        ]
    }
    """
    try:
        # Pull from the last 7 days and take the 5 most recent.
        raw = request_notifications_last(day=7)

        # raw is None when Nagios is unreachable or returns an error response.
        # Treat a missing/timed-out notificationlist as an empty result rather
        # than a 502 — the dashboard can still render with "No notifications".
        if raw is None:
            current_app.logger.warning(
                "Nagios notificationlist unavailable — returning empty list."
            )
            return success({"notifications": []})

        # Nagios archivejson returns a list of dicts.
        # Normalise field names: archivejson uses "host_name" in some versions.
        notifications = []
        for item in (raw or []):
            notifications.append(_normalize_notification(item))

        # Sort newest first and cap at 5.
        notifications.sort(key=_notification_sort_key, reverse=True)
        notifications = notifications[:5]

        return success({"notifications": notifications})

    except Exception:
        current_app.logger.exception(
            "Unexpected error in GET /system/dashboard/notifications"
        )
        return error("An unexpected error occurred.", 500)


