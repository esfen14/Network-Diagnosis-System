import requests
from datetime import datetime, time
from app.api.helper import convert_to_UNIX, get_range_day
from flask import current_app

NAGIOS_URL = "http://192.168.130.10/nagios/cgi-bin/archivejson.cgi"

USERNAME = "nagiosadmin"
PASSWORD = "password"

def _request_archive(query, params):
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
def request_alerts_history(
        start_date,
        start_time,
        end_date,
        end_time,
        hostname=None,
        service=None
    ):
    
    params = {
        "starttime": convert_to_UNIX(start_date, start_time) if start_date and start_time else 0,
        "endtime": convert_to_UNIX(end_date, end_time) if end_date and end_time else 999999999,
    }
    
    if hostname:
        params['hostname'] = hostname
            
    if service:
        params['service'] = service
    
    return _request_archive("alertlist", params)

def request_current_alerts():

    today = datetime.now().date()
        
    params = {
        "starttime": convert_to_UNIX(str(today), time.min),
        "endtime": convert_to_UNIX(str(today), time.max),
    }
    
    return _request_archive("alertlist", params)

def request_current_alert_count():

    today = datetime.now().date()
        
    params = {
        "starttime": convert_to_UNIX(str(today), time.min),
        "endtime": convert_to_UNIX(str(today), time.max),
    }
    
    return _request_archive("alertcount", params)


def request_alerts_last(day=None):
    start, end = get_range_day(day)
        
    params = {
        "starttime": start,
        "endtime": end,
    }
    return _request_archive("alertlist", params)

def request_alert_count_last(day=None):
    start, end = get_range_day(day)
        
    params = {
        "starttime": start,
        "endtime": end,
    }
    return _request_archive("alertcount", params)

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


def request_notifications_history(
        start_date,
        start_time,
        end_date,
        end_time,
        hostname=None,
        service=None
    ):
    
    params = {
        "starttime": convert_to_UNIX(start_date, start_time) if start_date and start_time else 0,
        "endtime": convert_to_UNIX(end_date, end_time) if end_date and end_time else 999999999,
    }
    
    if hostname:
        params['hostname'] = hostname
            
    if service:
        params['service'] = service
    
    return _request_archive("notificationlist", params)

def request_current_notifications():

    today = datetime.now().date()
        
    params = {
        "starttime": convert_to_UNIX(str(today), time.min),
        "endtime": convert_to_UNIX(str(today), time.max),
    }
    
    return _request_archive("notificationlist", params)

def request_current_notification_count():

    today = datetime.now().date()
        
    params = {
        "starttime": convert_to_UNIX(str(today), time.min),
        "endtime": convert_to_UNIX(str(today), time.max),
    }
    
    return _request_archive("notificationcount", params)


def request_notifications_last(day=None):
    start, end = get_range_day(day)
        
    params = {
        "starttime": start,
        "endtime": end,
    }
    return _request_archive("notificationlist", params)

def request_notifications_count_last(day=None):
    start, end = get_range_day(day)
        
    params = {
        "starttime": start,
        "endtime": end,
    }
    return _request_archive("notificationcount", params)

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
