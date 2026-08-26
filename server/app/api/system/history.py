"""
history.py — Alerts and Notifications History page routes.

Serves the two-tab history browsing interface defined in
Alerts_Notifications_History_Requirements.md.

Alerts come from Nagios archivejson.cgi (state-change events).
Notifications come from the same CGI (contact events sent by Nagios).
Acknowledgement records come from ACK_HISTORY in system_models.py (main DB).

Both endpoints are read-only. Filtering, sorting, and pagination follow
the same pattern as the other paginated routes in this project.

Routes
------
GET /system/history/alerts
    Paginated list of Nagios alert state-change events with filters for
    time range, type, host, service, new state, state type, and
    acknowledgement status.

GET /system/history/alerts/detail
    Full detail for a single alert event — untruncated plugin output,
    acknowledgement record if any, and linked notifications.

GET /system/history/notifications
    Paginated list of Nagios notification events with filters for
    time range, type, host, service, state, and contact.

GET /system/history/notifications/detail
    Full detail for a single notification event — full message,
    all contacts, and a link back to the related alert if it exists.
"""

from datetime import datetime, timezone, timedelta

import sqlalchemy as sa
from flask import request, current_app
from flask_login import login_required

from app import db
from app.api.system import system_bp
from app.api.helper import success, error
from app.api.helper.database_access.permissions import require_permission
from app.api.helper.converter import get_range_day, get_range_custom
from app.system_models import AckHistory, AckAction, User
from app.nagios.notifications import (
    request_alerts_range,
    request_notifications_range,
)

# Valid per-page values from the spec (§3.5).
_VALID_PER_PAGE = {25, 50, 100}

# Time range presets in days. 1 hour and 6 hours are handled separately
# since get_range_day works in whole days.
_PRESET_HOURS = {
    "1h":   1,
    "6h":   6,
    "24h":  24,
    "7d":   168,
    "30d":  720,
}


# ==========================================================
# HELPERS
# ==========================================================

def resolve_time_range(preset, start_date, end_date):
    """
    Return (start_ts, end_ts) as UNIX integers for the requested time range.

    If preset is given it takes priority over start_date/end_date.
    Preset values: "1h", "6h", "24h", "7d", "30d".
    For a custom range, pass start_date and end_date as YYYY-MM-DD strings.
    Returns (None, None) if the inputs are invalid.
    """
    now = int(datetime.now(timezone.utc).timestamp())

    if preset:
        hours = _PRESET_HOURS.get(preset)
        if hours is None:
            return None, None
        start_ts = now - hours * 3600
        return start_ts, now

    if start_date and end_date:
        try:
            return get_range_custom(start_date, end_date)
        except ValueError:
            return None, None

    # Default: last 24 hours
    return now - 86400, now


def normalize_nagios_list(raw):
    """
    Normalize the Nagios archivejson response to a plain list.

    Nagios returns alert/notification lists as a dict keyed by stringified
    index e.g. {"0": {...}, "1": {...}} rather than a proper list.
    """
    if isinstance(raw, dict):
        return list(raw.values())
    return list(raw) if raw else []


def fetch_ack_history(hostname, service_name):
    """
    Return the most recent ACKNOWLEDGED AckHistory row for a given alert,
    or None if the alert was never acknowledged.

    Matches on hostname and service_name (None for host-level alerts).
    """
    return db.session.scalar(
        sa.select(AckHistory)
        .where(
            AckHistory.Hostname == hostname,
            AckHistory.Service_Name == service_name,
            AckHistory.Action == AckAction.ACKNOWLEDGED,
        )
        .order_by(AckHistory.Actioned_At.desc())
        .limit(1)
    )


def serialize_ack(ack_row):
    """
    Serialize an AckHistory row into a frontend-ready dict, or return None.

    Joins to User to resolve the actor's full name.
    """
    if ack_row is None:
        return None

    actor = db.session.get(User, ack_row.ActorUserID) if ack_row.ActorUserID else None
    full_name = f"{actor.First_Name} {actor.Last_Name}" if actor else None

    return {
        "acknowledged_by": full_name,
        "acknowledged_at": ack_row.Actioned_At.isoformat(),
        "comment":         ack_row.Comment,
    }


def paginate_list(items, page, per_page):
    """
    Slice a list into a page and return it with pagination metadata.

    Returns a dict with keys: items, page, per_page, total, pages,
    has_next, has_prev.
    """
    total = len(items)
    pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    end = start + per_page

    return {
        "items":    items[start:end],
        "page":     page,
        "per_page": per_page,
        "total":    total,
        "pages":    pages,
        "has_next": page < pages,
        "has_prev": page > 1,
    }


# ==========================================================
# ALERTS HISTORY
# ==========================================================

@system_bp.get('/history/alerts')
@login_required
@require_permission("system.history")
def alerts_history():
    """
    Return a paginated list of Nagios alert state-change events.

    Filters, sorts, and paginates in-memory after fetching from Nagios
    because archivejson.cgi does not support server-side pagination.

    Query params:
        preset      — time range shortcut: 1h | 6h | 24h | 7d | 30d
        start_date  — YYYY-MM-DD (used when preset is absent)
        end_date    — YYYY-MM-DD (used when preset is absent)
        type        — host | service (omit for all)
        hostname    — filter to one host
        service     — filter to one service
        new_state   — filter by resulting state string (e.g. CRITICAL, DOWN, OK)
        state_type  — hard | soft (omit for all)
        ack_filter  — all | acknowledged | unacknowledged (default all)
        sort_by     — timestamp (default) | hostname | new_state | duration
        order       — desc (default) | asc
        page        — default 1
        per_page    — 25 (default) | 50 | 100
    """
    try:
        preset     = request.args.get("preset", default="", type=str).lower()
        start_date = request.args.get("start_date", default="", type=str)
        end_date   = request.args.get("end_date", default="", type=str)
        type_f     = request.args.get("type", default="", type=str).lower()
        hostname_f = request.args.get("hostname", default="", type=str)
        service_f  = request.args.get("service", default="", type=str)
        new_state_f= request.args.get("new_state", default="", type=str).upper()
        state_type_f= request.args.get("state_type", default="", type=str).lower()
        ack_filter = request.args.get("ack_filter", default="all", type=str).lower()
        sort_by    = request.args.get("sort_by", default="timestamp", type=str).lower()
        order      = request.args.get("order", default="desc", type=str).lower()
        page       = request.args.get("page", default=1, type=int)
        per_page   = request.args.get("per_page", default=25, type=int)

        if page < 1:
            return error("page must be greater than 0.", 400)
        if per_page not in _VALID_PER_PAGE:
            return error(f"per_page must be one of: {sorted(_VALID_PER_PAGE)}.", 400)
        if order not in ("asc", "desc"):
            return error("order must be 'asc' or 'desc'.", 400)
        if ack_filter not in ("all", "acknowledged", "unacknowledged"):
            return error("ack_filter must be 'all', 'acknowledged', or 'unacknowledged'.", 400)

        start_ts, end_ts = resolve_time_range(
            preset or None, start_date or None, end_date or None
        )
        if start_ts is None:
            return error(
                "Invalid time range. Use a preset (1h, 6h, 24h, 7d, 30d) "
                "or provide start_date and end_date as YYYY-MM-DD.", 400
            )

        raw = request_alerts_range(
            start_ts, end_ts,
            hostname=hostname_f or None,
            service=service_f or None,
        )

        if raw is None:
            return error("Failed to retrieve alert history from Nagios.", 502)

        alerts = normalize_nagios_list(raw)

        # Load all ack history records for annotating the list.
        # Keyed by (hostname, service_name) — service_name is None for host alerts.
        ack_map = build_ack_map()

        items = []
        for alert in alerts:
            hostname    = alert.get("hostname", "")
            service     = alert.get("service_description") or None
            alert_type  = "service" if service else "host"
            new_state   = (alert.get("state") or "").upper()
            prev_state  = (alert.get("last_state") or "").upper()
            state_type  = (alert.get("state_type") or "").lower()
            timestamp   = alert.get("timestamp", 0)
            duration    = alert.get("duration_seconds") or 0
            output      = alert.get("plugin_output") or ""

            # Apply filters
            if type_f and alert_type != type_f:
                continue
            if new_state_f and new_state != new_state_f:
                continue
            if state_type_f and state_type != state_type_f:
                continue

            is_acked = (hostname, service) in ack_map
            if ack_filter == "acknowledged" and not is_acked:
                continue
            if ack_filter == "unacknowledged" and is_acked:
                continue

            items.append({
                "timestamp":    timestamp,
                "type":         alert_type,
                "hostname":     hostname,
                "service_name": service,
                "previous_state": prev_state,
                "new_state":    new_state,
                "state_type":   state_type,
                "duration_seconds": duration,
                "plugin_output": output[:200],
                "acknowledged": is_acked,
            })

        # Sort
        _sort_keys = {
            "timestamp": lambda a: a["timestamp"],
            "hostname":  lambda a: a["hostname"].lower(),
            "new_state": lambda a: a["new_state"],
            "duration":  lambda a: a["duration_seconds"],
        }
        key_fn = _sort_keys.get(sort_by, _sort_keys["timestamp"])
        items.sort(key=key_fn, reverse=(order == "desc"))

        result = paginate_list(items, page, per_page)
        return success(result)

    except Exception:
        current_app.logger.exception(
            "Unexpected error in GET /system/history/alerts"
        )
        return error("An unexpected error occurred.", 500)


@system_bp.get('/history/alerts/detail')
@login_required
@require_permission("system.history")
def alerts_history_detail():
    """
    Return full detail for a single alert event.

    Includes untruncated plugin output, acknowledgement record if any,
    recovery duration if the new state is OK or UP, and any Nagios
    notification events linked to this alert within a 5-minute window.

    Query params (all required):
        hostname    — host the alert belongs to
        timestamp   — UNIX timestamp of the alert event (integer)
        new_state   — the resulting state string (e.g. CRITICAL, DOWN)
        service     — service name (omit for host-level alerts)
    """
    try:
        hostname  = request.args.get("hostname", default="", type=str)
        timestamp = request.args.get("timestamp", default=0, type=int)
        new_state = request.args.get("new_state", default="", type=str).upper()
        service   = request.args.get("service", default="", type=str) or None

        if not hostname:
            return error("hostname is required.", 400)
        if not timestamp:
            return error("timestamp is required.", 400)

        # Fetch a narrow window around the event to find this specific row.
        window_start = timestamp - 5
        window_end   = timestamp + 5
        raw = request_alerts_range(
            window_start, window_end,
            hostname=hostname,
            service=service,
        )

        if raw is None:
            return error("Failed to retrieve alert detail from Nagios.", 502)

        alerts = normalize_nagios_list(raw)

        # Find the specific event — match on timestamp and new_state.
        alert = next(
            (a for a in alerts
             if a.get("timestamp") == timestamp
             and (a.get("state") or "").upper() == new_state),
            None
        )

        if alert is None:
            return error("Alert event not found.", 404)

        full_output  = alert.get("plugin_output") or ""
        prev_state   = (alert.get("last_state") or "").upper()
        state_type   = (alert.get("state_type") or "").lower()
        duration     = alert.get("duration_seconds") or 0

        # Acknowledgement detail from ACK_HISTORY
        ack_row = fetch_ack_history(hostname, service)
        ack     = serialize_ack(ack_row)

        # Recovery duration — meaningful when new state is OK or UP
        recovery_duration = None
        if new_state in ("OK", "UP"):
            recovery_duration = duration

        # Linked notifications — look for notifications in a ±5 minute window
        # around this alert's timestamp for the same host/service.
        notif_raw = request_notifications_range(
            timestamp - 300, timestamp + 300,
            hostname=hostname,
            service=service,
        )
        linked_notifications = []
        if notif_raw:
            for notif in normalize_nagios_list(notif_raw):
                linked_notifications.append({
                    "timestamp": notif.get("timestamp"),
                    "contact":   notif.get("contact"),
                    "state":     (notif.get("notification_reason") or notif.get("state") or "").upper(),
                    "message":   (notif.get("output") or "")[:200],
                })

        return success({
            "hostname":           hostname,
            "service_name":       service,
            "timestamp":          timestamp,
            "type":               "service" if service else "host",
            "previous_state":     prev_state,
            "new_state":          new_state,
            "state_type":         state_type,
            "duration_seconds":   duration,
            "plugin_output":      full_output,
            "acknowledged":       ack is not None,
            "ack":                ack,
            "recovery_duration":  recovery_duration,
            "linked_notifications": linked_notifications,
        })

    except Exception:
        current_app.logger.exception(
            "Unexpected error in GET /system/history/alerts/detail"
        )
        return error("An unexpected error occurred.", 500)


# ==========================================================
# NOTIFICATIONS HISTORY
# ==========================================================

@system_bp.get('/history/notifications')
@login_required
@require_permission("system.history")
def notifications_history():
    """
    Return a paginated list of Nagios notification events.

    Filters, sorts, and paginates in-memory after fetching from Nagios.

    Query params:
        preset      — time range shortcut: 1h | 6h | 24h | 7d | 30d
        start_date  — YYYY-MM-DD (used when preset is absent)
        end_date    — YYYY-MM-DD (used when preset is absent)
        type        — host | service (omit for all)
        hostname    — filter to one host
        service     — filter to one service
        state       — filter by state at notification time (e.g. CRITICAL)
        contact     — filter by contact name (partial match)
        sort_by     — timestamp (default) | hostname | state
        order       — desc (default) | asc
        page        — default 1
        per_page    — 25 (default) | 50 | 100
    """
    try:
        preset     = request.args.get("preset", default="", type=str).lower()
        start_date = request.args.get("start_date", default="", type=str)
        end_date   = request.args.get("end_date", default="", type=str)
        type_f     = request.args.get("type", default="", type=str).lower()
        hostname_f = request.args.get("hostname", default="", type=str)
        service_f  = request.args.get("service", default="", type=str)
        state_f    = request.args.get("state", default="", type=str).upper()
        contact_f  = request.args.get("contact", default="", type=str).lower()
        sort_by    = request.args.get("sort_by", default="timestamp", type=str).lower()
        order      = request.args.get("order", default="desc", type=str).lower()
        page       = request.args.get("page", default=1, type=int)
        per_page   = request.args.get("per_page", default=25, type=int)

        if page < 1:
            return error("page must be greater than 0.", 400)
        if per_page not in _VALID_PER_PAGE:
            return error(f"per_page must be one of: {sorted(_VALID_PER_PAGE)}.", 400)
        if order not in ("asc", "desc"):
            return error("order must be 'asc' or 'desc'.", 400)

        start_ts, end_ts = resolve_time_range(
            preset or None, start_date or None, end_date or None
        )
        if start_ts is None:
            return error(
                "Invalid time range. Use a preset (1h, 6h, 24h, 7d, 30d) "
                "or provide start_date and end_date as YYYY-MM-DD.", 400
            )

        raw = request_notifications_range(
            start_ts, end_ts,
            hostname=hostname_f or None,
            service=service_f or None,
        )

        if raw is None:
            return error("Failed to retrieve notification history from Nagios.", 502)

        notifications = normalize_nagios_list(raw)

        items = []
        for notif in notifications:
            hostname  = notif.get("hostname", "")
            service   = notif.get("service_description") or None
            notif_type= "service" if service else "host"
            state     = (notif.get("notification_reason") or notif.get("state") or "").upper()
            contact   = notif.get("contact") or ""
            timestamp = notif.get("timestamp", 0)
            message   = notif.get("output") or ""
            method    = notif.get("notificationmethod") or ""

            if type_f and notif_type != type_f:
                continue
            if state_f and state != state_f:
                continue
            if contact_f and contact_f not in contact.lower():
                continue

            items.append({
                "timestamp":    timestamp,
                "type":         notif_type,
                "hostname":     hostname,
                "service_name": service,
                "state":        state,
                "contact":      contact,
                "method":       method,
                "message":      message[:200],
            })

        _sort_keys = {
            "timestamp": lambda n: n["timestamp"],
            "hostname":  lambda n: n["hostname"].lower(),
            "state":     lambda n: n["state"],
        }
        key_fn = _sort_keys.get(sort_by, _sort_keys["timestamp"])
        items.sort(key=key_fn, reverse=(order == "desc"))

        result = paginate_list(items, page, per_page)
        return success(result)

    except Exception:
        current_app.logger.exception(
            "Unexpected error in GET /system/history/notifications"
        )
        return error("An unexpected error occurred.", 500)


@system_bp.get('/history/notifications/detail')
@login_required
@require_permission("system.history")
def notifications_history_detail():
    """
    Return full detail for a single notification event.

    Includes the full untruncated message, all contacts notified, and
    a link to the related alert event if one exists in the same ±5 minute
    window for the same host and service.

    Query params (all required):
        hostname    — host the notification belongs to
        timestamp   — UNIX timestamp of the notification event (integer)
        service     — service name (omit for host-level notifications)
    """
    try:
        hostname  = request.args.get("hostname", default="", type=str)
        timestamp = request.args.get("timestamp", default=0, type=int)
        service   = request.args.get("service", default="", type=str) or None

        if not hostname:
            return error("hostname is required.", 400)
        if not timestamp:
            return error("timestamp is required.", 400)

        # Narrow fetch to find this specific notification.
        raw = request_notifications_range(
            timestamp - 5, timestamp + 5,
            hostname=hostname,
            service=service,
        )

        if raw is None:
            return error("Failed to retrieve notification detail from Nagios.", 502)

        notifications = normalize_nagios_list(raw)

        # Find the specific notification by timestamp.
        notif = next(
            (n for n in notifications if n.get("timestamp") == timestamp),
            None
        )

        if notif is None:
            return error("Notification event not found.", 404)

        state   = (notif.get("notification_reason") or notif.get("state") or "").upper()
        contact = notif.get("contact") or ""
        message = notif.get("output") or ""
        method  = notif.get("notificationmethod") or ""

        # All contacts — Nagios may list multiple separated by commas.
        contacts = [c.strip() for c in contact.split(",") if c.strip()]

        # Linked alert — look for an alert in a ±5 minute window.
        alert_raw = request_alerts_range(
            timestamp - 300, timestamp + 300,
            hostname=hostname,
            service=service,
        )
        linked_alert = None
        if alert_raw:
            alerts = normalize_nagios_list(alert_raw)
            if alerts:
                # Take the closest alert to this notification's timestamp.
                alerts.sort(
                    key=lambda a: abs((a.get("timestamp") or 0) - timestamp)
                )
                a = alerts[0]
                linked_alert = {
                    "timestamp":  a.get("timestamp"),
                    "new_state":  (a.get("state") or "").upper(),
                    "prev_state": (a.get("last_state") or "").upper(),
                }

        return success({
            "hostname":     hostname,
            "service_name": service,
            "timestamp":    timestamp,
            "type":         "service" if service else "host",
            "state":        state,
            "contacts":     contacts,
            "method":       method,
            "message":      message,
            "linked_alert": linked_alert,
        })

    except Exception:
        current_app.logger.exception(
            "Unexpected error in GET /system/history/notifications/detail"
        )
        return error("An unexpected error occurred.", 500)


# ==========================================================
# INTERNAL HELPERS
# ==========================================================

def build_ack_map():
    """
    Return a set of (hostname, service_name) tuples for all alerts that
    have at least one ACKNOWLEDGED record in ACK_HISTORY.

    Used to annotate the alerts list without making one DB query per row.
    Service_name is None for host-level alerts.
    """
    rows = db.session.execute(
        sa.select(AckHistory.Hostname, AckHistory.Service_Name)
        .where(AckHistory.Action == AckAction.ACKNOWLEDGED)
        .distinct()
    ).all()

    return {(row.Hostname, row.Service_Name) for row in rows}
