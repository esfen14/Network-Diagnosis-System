"""
Notification routes — cursor-based read/unread tracking.

How it works
------------
Nagios has no concept of "read" or "unread".  Every notification is just a
timestamped event returned by archivejson.cgi.  We track what each user has
*seen* by storing a single UNIX timestamp per user in NOTIFICATION_CURSOR
(last_seen_ts).  The rule is:

    notification.timestamp > last_seen_ts  →  UNREAD
    notification.timestamp <= last_seen_ts →  READ

The front-end never needs to send timestamps or manage state.
It only calls mark-read when the user opens the notification panel.

Routes
------
GET  /system/notifications
    Returns recent notifications (default: last 7 days, up to 50 items),
    each annotated with `is_read`.  Also returns the current unread count.

GET  /system/notifications/unread-count
    Lightweight poll endpoint — returns only the count of unread notifications.
    Front-end polls this (e.g. every 30 s) to drive the bell badge.

POST /system/notifications/mark-read
    Advances the caller's cursor to `now` (or to an explicit `up_to`
    timestamp), marking everything up to that point as read.
"""

from datetime import datetime, timezone, timedelta

import sqlalchemy as sa
from flask import request, current_app
from flask_login import login_required, current_user

from app import db
from app.api.system import system_bp
from app.api.helper import success, error
from app.api.helper.database_access.permissions import require_permission
from app.system_models import NotificationCursor
from app.nagios.notifications import (
    request_notifications_range,
    request_notification_count_range,
)

_DEFAULT_LOOKBACK_DAYS = 7
_DEFAULT_LIMIT = 50


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_or_create_cursor(user_id: int) -> NotificationCursor:
    """
    Return the cursor row for this user, creating it with last_seen_ts=0
    if it does not exist yet.  Does NOT commit — caller is responsible.
    """
    cursor = db.session.get(NotificationCursor, user_id)
    if cursor is None:
        cursor = NotificationCursor(UserID=user_id, last_seen_ts=0)
        db.session.add(cursor)
        db.session.flush()
    return cursor


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _normalize_nagios_list(raw) -> list:
    """
    Nagios archivejson returns notifications as a dict keyed by stringified
    index (e.g. {"0": {...}, "1": {...}}) rather than a plain list.
    Normalise to a list regardless of which shape comes back.
    """
    if isinstance(raw, dict):
        return list(raw.values())
    return list(raw) if raw else []


# ---------------------------------------------------------------------------
# GET /system/notifications
# ---------------------------------------------------------------------------

@system_bp.get('/notifications')
@login_required
@require_permission("system.notifications")
def get_notifications():
    """
    Returns recent Nagios notifications annotated with a per-user `is_read`
    flag derived from the caller's cursor.

    Query params:
        limit        (int, 1-200, default 50) — max items to return
        lookback_days (int, 1-90, default 7)  — how many days back to query

    Response shape:
    {
        "success": true,
        "data": {
            "last_seen_ts":  1234567890,
            "unread_count":  3,
            "notifications": [
                { ...nagios fields..., "is_read": false },
                ...
            ]
        }
    }
    """
    try:
        limit = request.args.get("limit", default=_DEFAULT_LIMIT, type=int)
        lookback_days = request.args.get(
            "lookback_days", default=_DEFAULT_LOOKBACK_DAYS, type=int
        )

        if limit < 1 or limit > 200:
            return error("limit must be between 1 and 200.", 400)
        if lookback_days < 1 or lookback_days > 90:
            return error("lookback_days must be between 1 and 90.", 400)

        cursor = _get_or_create_cursor(current_user.UserID)
        db.session.commit()

        last_seen_ts = cursor.last_seen_ts
        now_ts = _now_ts()
        start_ts = int(
            (datetime.now(timezone.utc) - timedelta(days=lookback_days)).timestamp()
        )

        raw = request_notifications_range(start_ts, now_ts)

        if raw is None:
            return error(
                "Failed to retrieve notifications from Nagios. "
                "Check server logs for details.",
                502,
            )

        items = _normalize_nagios_list(raw)

        # Sort newest-first, then take only the requested limit
        items.sort(key=lambda n: n.get("timestamp", 0), reverse=True)
        items = items[:limit]

        # Annotate each item with is_read
        unread_count = 0
        annotated = []
        for item in items:
            ts = item.get("timestamp", 0)
            is_read = ts <= last_seen_ts
            if not is_read:
                unread_count += 1
            annotated.append({**item, "is_read": is_read})

        return success({
            "last_seen_ts":  last_seen_ts,
            "unread_count":  unread_count,
            "notifications": annotated,
        })

    except Exception:
        current_app.logger.exception("Unexpected error in get_notifications")
        return error("An unexpected error occurred.", 500)


# ---------------------------------------------------------------------------
# GET /system/notifications/unread-count
# ---------------------------------------------------------------------------

@system_bp.get('/notifications/unread-count')
@login_required
@require_permission("system.notifications")
def get_unread_count():
    """
    Returns only the count of notifications that arrived after the caller's
    cursor.  Intended to be polled frequently (e.g. every 30 s) to update
    the bell badge — no list data is returned so the call stays cheap.

    When the cursor is at 0 (never marked read) the query window is capped
    to the last 7 days to avoid scanning Nagios' entire history.

    Response shape:
    {
        "success": true,
        "data": {
            "unread_count": 3,
            "last_seen_ts": 1234567890
        }
    }
    """
    try:
        cursor = _get_or_create_cursor(current_user.UserID)
        db.session.commit()

        last_seen_ts = cursor.last_seen_ts
        now_ts = _now_ts()

        # Cap a never-read cursor so we don't ask Nagios to count all-time
        if last_seen_ts == 0:
            effective_start = int(
                (datetime.now(timezone.utc) - timedelta(days=_DEFAULT_LOOKBACK_DAYS)).timestamp()
            )
        else:
            effective_start = last_seen_ts

        count_data = request_notification_count_range(effective_start, now_ts)

        if count_data is None:
            return error(
                "Failed to retrieve notification count from Nagios. "
                "Check server logs for details.",
                502,
            )

        # Nagios notificationcount returns {"total": n, "ok": n, ...}
        if isinstance(count_data, dict):
            unread_count = count_data.get("total", 0)
        else:
            unread_count = int(count_data)

        return success({
            "unread_count": unread_count,
            "last_seen_ts": last_seen_ts,
        })

    except Exception:
        current_app.logger.exception("Unexpected error in get_unread_count")
        return error("An unexpected error occurred.", 500)


# ---------------------------------------------------------------------------
# POST /system/notifications/mark-read
# ---------------------------------------------------------------------------

@system_bp.post('/notifications/mark-read')
@login_required
@require_permission("system.notifications")
def mark_notifications_read():
    """
    Advances the caller's cursor, marking all notifications up to that point
    as read.

    The front-end should call this when the user opens the notification panel.

    Optional JSON body:
    {
        "up_to": 1234567890
    }

    `up_to` — UNIX timestamp ceiling.  Defaults to now if omitted or null.

    Passing the timestamp of the newest item received from GET /notifications
    as `up_to` is recommended: it prevents accidentally silencing a
    notification that arrived in the gap between the GET and this POST.

    The cursor only ever moves forward.  A stale or replayed request with an
    older timestamp is a no-op.

    Response shape:
    {
        "success": true,
        "data": {
            "previous_last_seen_ts": 0,
            "last_seen_ts":          1234567890
        }
    }
    """
    try:
        data = request.get_json(silent=True) or {}
        up_to = data.get("up_to")

        if up_to is not None:
            if not isinstance(up_to, (int, float)):
                return error("'up_to' must be a UNIX timestamp (integer).", 400)
            new_ts = int(up_to)
        else:
            new_ts = _now_ts()

        cursor = _get_or_create_cursor(current_user.UserID)
        previous_ts = cursor.last_seen_ts

        # Only move the cursor forward, never backward
        if new_ts > previous_ts:
            cursor.last_seen_ts = new_ts
            cursor.Updated_At = datetime.now(timezone.utc)

        db.session.commit()

        return success({
            "previous_last_seen_ts": previous_ts,
            "last_seen_ts":          cursor.last_seen_ts,
        })

    except Exception:
        current_app.logger.exception("Unexpected error in mark_notifications_read")
        db.session.rollback()
        return error("An unexpected error occurred.", 500)
