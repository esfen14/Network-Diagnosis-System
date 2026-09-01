import requests
from app.api.helper import get_range_day
from flask import current_app

# NAGIOS_URL/USERNAME/PASSWORD now live in server/config.py's Config
# class as NAGIOS_ARCHIVE_URL, NAGIOS_USERNAME, NAGIOS_PASSWORD — read
# into same-named locals inside _request_archive() below.

def _request_archive(query, params):
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
        
        return data['data'][query]
    except requests.RequestException as e:
        current_app.logger.error("Failed to request Nagios archive: %s", e)
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
