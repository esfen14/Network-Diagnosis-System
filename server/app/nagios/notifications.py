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
        params['service'] = service

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
        params['service'] = service

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
        params['service'] = service

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
        params['service'] = service

    return _request_archive("notificationcount", params)
