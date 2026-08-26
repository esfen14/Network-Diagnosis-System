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
The active alerts feed (§1.6) sources data from Nagios' archivejson.cgi
alertlist query rather than from the history.db snapshots. The alertlist
returns state-change events; we determine "currently active" alerts by
reducing to the most recent event per (hostname, servicedesc) and keeping
only those still in a problem state (i.e., not OK / UP / RECOVERY).
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
from app.nagios.notifications import request_alerts_last, request_notifications_last
from app.system_models import AlertAcknowledgement, AckHistory, AckAction

# States that mean "recovered / no longer a problem" in archivejson alertlist.
# String form (mock / older Nagios): "ok", "up", "recovery"
# Integer form (Nagios archivejson): 0 = HOST_UP / SERVICE_OK
_OK_STATES = {"ok", "up", "recovery"}
_OK_STATE_INTS = {0}

# Nagios archivejson integer state → human-readable string.
# HOST states: 0=UP, 1=DOWN, 2=UNREACHABLE
# SERVICE states: 0=OK, 16=WARNING, 32=CRITICAL, 48=UNKNOWN
# object_type: 1=HOST, 2=SERVICE
_HOST_STATE_MAP    = {0: "UP", 1: "DOWN", 2: "UNREACHABLE"}
_SERVICE_STATE_MAP = {0: "OK", 16: "WARNING", 32: "CRITICAL", 48: "UNKNOWN"}
_STATE_TYPE_MAP    = {1: "SOFT", 2: "HARD"}

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

        if prog:
            nagios_info = {
                # Nagios is considered "running" if it reported a PID.
                "running":               prog.NagiosPID is not None,
                "pid":                   prog.NagiosPID,
                "version":               prog.Version,
                "program_start_time":    (
                    prog.Program_Start_Time.isoformat()
                    if prog.Program_Start_Time else None
                ),
                # Timestamp of the most-recent status write is the ProgramStatus row timestamp.
                "last_status_update":    prog.Timestamp.isoformat(),
                "active_host_checks":    prog.Active_Host_Checks_Enabled,
                "active_service_checks": prog.Active_Service_Checks_Enabled,
                "notifications_enabled": prog.Enable_Notifications,
                "enable_flap_detection": prog.Enable_Flap_Detection,
            }
        else:
            # No status data at all — Nagios has never reported or DB is empty.
            nagios_info = {
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
    Return the active alerts feed sourced from Nagios archivejson.cgi alertlist.

    We query the alertlist for the last 7 days, then reduce to the most recent
    event per (hostname, servicedesc). Any entity whose most recent event is
    still in a problem state (not OK / UP / RECOVERY) is considered an active
    alert and included in the feed.

    This means the feed reflects what Nagios has recorded as the latest known
    state for each monitored entity, without relying on the history.db snapshots.

    Query params:
        limit       — max rows to return (default 15, max 100)
        ack_filter  — "all" (default) | "unacknowledged" | "acknowledged"

    Each alert row:
    {
        "type":              "host" | "service",
        "hostname":          str,
        "service_name":      str | null,
        "state":             str,           // e.g. WARNING, CRITICAL, DOWN
        "state_type":        str | null,    // "SOFT" | "HARD" | null if not provided
        "timestamp":         int,           // UNIX timestamp of the state-change event
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

        # ── Fetch alert events from archivejson.cgi ──────────────────────────
        raw = request_alerts_last(day=7)

        if raw is None:
            return error("Failed to retrieve alert data from Nagios.", 502)

        # archivejson returns a dict keyed by string index or a list.
        if isinstance(raw, dict):
            events = list(raw.values())
        else:
            events = list(raw)

        # ── Reduce to most-recent event per (hostname, servicedesc) ─────────
        # Key: (hostname, service_name_or_None)
        # Nagios archivejson uses "host_name" and "description"; older/mock
        # data may use "hostname" and "servicedesc" — handle both.
        latest: dict[tuple, dict] = {}
        for ev in events:
            hostname = ev.get("host_name") or ev.get("hostname") or ""
            svc      = ev.get("description") or ev.get("servicedesc") or None
            svc      = svc if svc else None   # empty string → None
            raw_ts   = ev.get("timestamp") or 0
            # archivejson returns timestamps in milliseconds; convert to seconds.
            ts = raw_ts // 1000 if raw_ts > 9_999_999_999 else raw_ts
            key = (hostname, svc)
            if key not in latest or ts > (latest[key].get("_ts_sec", 0)):
                ev["_ts_sec"] = ts   # cache converted timestamp on the event
                latest[key] = ev

        # ── Keep only those still in a problem state ─────────────────────────
        now_ts = int(datetime.now(timezone.utc).timestamp())

        # Load app-side acknowledgements keyed by (hostname, service_name).
        ack_rows = db.session.scalars(sa.select(AlertAcknowledgement)).all()
        ack_map: dict[tuple, AlertAcknowledgement] = {
            (a.Hostname, a.Service_Name): a for a in ack_rows
        }

        alerts: list[dict] = []

        for (hostname, svc), ev in latest.items():
            raw_state = ev.get("state")

            # Nagios archivejson returns integer state codes.
            # Determine object type: "object_type" 1=host, 2=service.
            # Fall back to presence of svc when the field is absent.
            obj_type = ev.get("object_type")
            is_service = (obj_type == 2) if obj_type is not None else bool(svc)

            if isinstance(raw_state, int):
                if raw_state in _OK_STATE_INTS:
                    continue  # recovered
                state_map = _SERVICE_STATE_MAP if is_service else _HOST_STATE_MAP
                state_str = state_map.get(raw_state, str(raw_state))
            else:
                # String state from mock data or older Nagios versions.
                state_str_lower = str(raw_state or "").strip().lower()
                if state_str_lower in _OK_STATES:
                    continue  # recovered
                state_str = str(raw_state or "").strip().upper()

            ack = ack_map.get((hostname, svc))
            is_acked = ack is not None

            if ack_filter == "unacknowledged" and is_acked:
                continue
            if ack_filter == "acknowledged" and not is_acked:
                continue

            ev_ts    = ev.get("_ts_sec", 0)
            duration = max(now_ts - ev_ts, 0)

            # state_type may be an int (2=HARD, 1=SOFT) or a string.
            raw_st = ev.get("state_type") or ev.get("statetype")
            if isinstance(raw_st, int):
                state_type_str = _STATE_TYPE_MAP.get(raw_st)
            else:
                state_type_str = str(raw_st).upper() if raw_st else None

            # plugin_output key differs between archivejson versions.
            output = (
                ev.get("plugin_output")
                or ev.get("output")
                or ev.get("pluginoutput")
                or ""
            )

            alerts.append({
                "type":             "service" if is_service else "host",
                "hostname":         hostname,
                "service_name":     svc,
                "state":            state_str,
                "state_type":       state_type_str,
                "timestamp":        ev_ts,
                "duration_seconds": duration,
                "plugin_output":    output,
                "in_downtime":      bool(ev.get("indowntime")),
                "ack":              _serialize_ack(ack),
            })

        # ── Sort: downtime last → severity → acked below unacked → duration desc ──
        _SEVERITY = {
            "down":         0,
            "unreachable":  1,
            "critical":     0,
            "warning":      1,
            "unknown":      2,
        }

        def _sort_key(a: dict) -> tuple:
            sev      = _SEVERITY.get(a["state"].lower(), 2)
            acked    = 1 if a["ack"] is not None else 0
            downtime = 1 if a["in_downtime"] else 0
            return (downtime, sev, acked, -a["duration_seconds"])

        alerts.sort(key=_sort_key)
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

            db.session.add(AlertAcknowledgement(
                Hostname        = hostname,
                Service_Name    = service_name,
                Comment         = comment,
                Acknowledged_At = now,
                AcknowledgedBy  = current_user.UserID,
            ))
            db.session.add(AckHistory(
                Hostname     = hostname,
                Service_Name = service_name,
                Action       = AckAction.ACKNOWLEDGED,
                Actioned_At  = now,
                ActorUserID  = current_user.UserID,
                Comment      = comment,
            ))
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
            hostname = item.get("hostname") or item.get("host_name") or ""
            raw_ts   = item.get("timestamp") or 0
            # Convert millisecond timestamps to seconds if needed.
            ts_sec   = raw_ts // 1000 if raw_ts > 9_999_999_999 else raw_ts
            notifications.append({
                "timestamp":    ts_sec,
                "type":         (item.get("notificationtype") or "").upper(),
                "hostname":     hostname,
                "service_name": item.get("servicedesc") or item.get("description") or None,
                "state":        item.get("notificationreason") or item.get("state") or "",
                "contact":      item.get("contact") or "",
                "message":      (item.get("output") or item.get("plugin_output") or "")[:200],
            })

        # Sort newest first and cap at 5.
        notifications.sort(key=lambda n: n["timestamp"] or 0, reverse=True)
        notifications = notifications[:5]

        return success({"notifications": notifications})

    except Exception:
        current_app.logger.exception(
            "Unexpected error in GET /system/dashboard/notifications"
        )
        return error("An unexpected error occurred.", 500)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

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
