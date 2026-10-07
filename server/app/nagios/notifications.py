import requests
from app.api.helper import get_range_day
from flask import current_app

# NAGIOS_URL/USERNAME/PASSWORD now live in server/config.py's Config
# class as NAGIOS_ARCHIVE_URL, NAGIOS_USERNAME, NAGIOS_PASSWORD — read
# into same-named locals inside _request_archive() below.

def _request_archive(query, params, result_key=None):
    """
    Call archivejson.cgi and return data[result_key] (data[query] by
    default). Returns None if Nagios can't be reached or the key is missing.
    """
    NAGIOS_URL = current_app.config['NAGIOS_ARCHIVE_URL']
    USERNAME = current_app.config['NAGIOS_USERNAME']
    PASSWORD = current_app.config['NAGIOS_PASSWORD']
    try:

        params["query"] = query

        response = requests.get(
            NAGIOS_URL,
            params=params,
            auth=(USERNAME,PASSWORD),
            timeout=10
        )
        
        response.raise_for_status()

        data = response.json()
        
        return data['data'][result_key or query]
    except requests.RequestException as e:
        current_app.logger.error("Failed to request Nagios archive: %s", e)
        return None
    except (KeyError, TypeError, ValueError) as e:
        current_app.logger.error("Unexpected Nagios archive response for %s: %s", query, e)
        return None
'''
    There is a difference between notifications and alerts.
    
    Alerts       - What occurred monitoring the network (host/service state changes).
    Notifications - What Nagios sent out (emails, pager, etc.) in response to state changes.
'''

# ======================= ALERTS =====================================
def request_alerts_range(start_ts, end_ts, hostname=None, service=None):
    """Query alerts for an arbitrary UNIX timestamp range."""
    params = {
        "starttime": start_ts,
        "endtime": end_ts,
    }

    if hostname:
        params['hostname'] = hostname

    if service:
        params['servicedescription'] = service

    return _request_archive("alertlist", params)

def request_alert_count_range(start_ts, end_ts, hostname=None, service=None):
    """Query alert count for an arbitrary UNIX timestamp range."""
    params = {
        "starttime": start_ts,
        "endtime": end_ts,
    }

    if hostname:
        params['hostname'] = hostname

    if service:
        params['servicedescription'] = service

    return _request_archive("alertcount", params)


# ======================= AVAILABILITY ===============================
def request_host_availability_range(start_ts, end_ts):
    """
    Query per-host availability for a UNIX timestamp range. Returns the
    list under data.hosts — one dict per host with time_up, time_down,
    time_unreachable and time_indeterminate_* (seconds) — or None if
    Nagios can't be reached.
    """
    params = {
        "availabilityobjecttype": "hosts",
        "starttime": start_ts,
        "endtime": end_ts,
    }

    return _request_archive("availability", params, result_key="hosts")


# ================================ NOTIFICATIONS ==============================


def request_notifications_last(day=None):
    start, end = get_range_day(day)
        
    params = {
        "starttime": start,
        "endtime": end,
    }
    # Bug fix: was querying "alertlist" — notifications use "notificationlist"
    return _request_archive("notificationlist",params)

def request_notifications_range(start_ts, end_ts, hostname=None, service=None):
    """Query notifications for an arbitrary UNIX timestamp range."""
    params = {
        "starttime": start_ts,
        "endtime": end_ts,
    }

    if hostname:
        params['hostname'] = hostname

    if service:
        params['servicedescription'] = service

    return _request_archive("notificationlist", params)

def request_notification_count_range(start_ts, end_ts, hostname=None, service=None):
    """Query notification count for an arbitrary UNIX timestamp range."""
    params = {
        "starttime": start_ts,
        "endtime": end_ts,
    }

    if hostname:
        params['hostname'] = hostname

    if service:
        params['servicedescription'] = service

    return _request_archive("notificationcount", params)


# ======================= NORMALIZATION ===============================
# archivejson key names differ between Nagios versions, so each canonical
# field is read from several aliases (first non-empty wins).
# "name" is how archivejson labels the host of a host-level event.
_HOST_KEYS = ("hostname", "host_name", "host", "name")
_SERVICE_KEYS = ("servicedesc", "service_description", "description", "service")
_STATE_KEYS = ("notificationreason", "notification_reason", "state")
_TYPE_KEYS = ("notificationtype", "notification_type")
_CONTACT_KEYS = ("contact", "contact_name")
_MESSAGE_KEYS = ("output", "plugin_output", "message")
_METHOD_KEYS = ("notificationmethod", "method", "command")


def _first(raw, keys):
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return ""


# Nagios archivejson reports event timestamps in milliseconds.
_MS_TIMESTAMP_FLOOR = 100_000_000_000


def _timestamp_seconds(value) -> int:
    """UNIX seconds from an archivejson timestamp that may be in milliseconds."""
    value = value if isinstance(value, (int, float)) else 0
    return int(value // 1000) if value >= _MS_TIMESTAMP_FLOOR else int(value)


def normalize_notification(raw: dict) -> dict:
    """
    Return the raw Nagios notification with canonical keys added
    (hostname, servicedesc, state, notificationtype, contact, output,
    notificationmethod) and the timestamp in UNIX seconds (Nagios may send
    milliseconds). Original keys are kept; empty values stay empty.
    """
    return {
        **raw,
        "timestamp":          _timestamp_seconds(raw.get("timestamp")),
        "hostname":           _first(raw, _HOST_KEYS),
        "servicedesc":        _first(raw, _SERVICE_KEYS) or None,
        "state":              str(_first(raw, _STATE_KEYS)).upper(),
        "notificationtype":   str(_first(raw, _TYPE_KEYS)).upper(),
        "contact":            _first(raw, _CONTACT_KEYS),
        "output":             _first(raw, _MESSAGE_KEYS),
        "notificationmethod": _first(raw, _METHOD_KEYS),
    }


# archivejson sends states as bit flags (host 1/2/4, service 8/16/32/64) and
# state types as soft=1, hard=2; plain 0-3 codes are accepted too.
_HOST_STATES = {0: "UP", 1: "UP", 2: "DOWN", 4: "UNREACHABLE"}
_SERVICE_STATES = {0: "OK", 8: "OK", 16: "WARNING", 32: "CRITICAL", 64: "UNKNOWN", 1: "WARNING", 2: "CRITICAL", 3: "UNKNOWN"}

def _alert_state(value, is_service: bool) -> str:
    """State name for a Nagios alert state: numeric codes map by object type, strings pass through."""
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, int):
        return (_SERVICE_STATES if is_service else _HOST_STATES).get(value, "")
    return str(value).upper()


def normalize_alert(raw: dict) -> dict:
    """
    Return one archivejson alertlist entry with canonical keys: hostname,
    service_description (None for host alerts), state, last_state, state_type
    ("hard"/"soft"), timestamp (UNIX seconds), duration_seconds and
    plugin_output. Real Nagios sends numeric states, a millisecond timestamp
    and the host under "name"/"host_name"; already-canonical entries pass
    through unchanged. Fields Nagios does not provide stay empty.
    """
    service = _first(raw, _SERVICE_KEYS) or None
    is_service = service is not None or raw.get("object_type") == 2

    state_type = raw.get("state_type")
    if isinstance(state_type, int):
        state_type = "hard" if state_type == 2 else "soft"

    return {
        **raw,
        "hostname":            _first(raw, _HOST_KEYS) or "",
        "service_description": service,
        "state":               _alert_state(raw.get("state"), is_service),
        "last_state":          _alert_state(raw.get("last_state"), is_service),
        "state_type":          str(state_type or "").lower(),
        "timestamp":           _timestamp_seconds(raw.get("timestamp")),
        "duration_seconds":    raw.get("duration_seconds") or 0,
        "plugin_output":       raw.get("plugin_output") or "",
    }


def collapse_repeats(items: list) -> list:
    """
    Collapse repeat notifications — the same host/service re-notifying in the
    same state — into one entry carrying the newest timestamp plus
    `repeat_count` and `first_timestamp`. A state change starts a new entry.
    Items without a host name are never collapsed. Input items must already be
    normalized; the result is newest-first.
    """
    groups = []
    last_group = {}  # (host, service) -> most recent group for that object
    for item in sorted(items, key=lambda n: n.get("timestamp", 0)):
        host = item.get("hostname")
        key = (host, item.get("servicedesc"))
        group = last_group.get(key) if host else None
        if group is not None and group["state"] == item.get("state"):
            group["timestamp"] = item.get("timestamp", 0)
            group["repeat_count"] += 1
            continue
        group = {**item, "repeat_count": 1, "first_timestamp": item.get("timestamp", 0)}
        groups.append(group)
        if host:
            last_group[key] = group
    groups.sort(key=lambda n: n.get("timestamp", 0), reverse=True)
    return groups
