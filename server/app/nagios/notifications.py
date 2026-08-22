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
        current_app.logger.error("Failed to request Nagios alerts: %s", e)
        return None
'''
    There is a difference between notifications and alerts.
    
    Alerts - What occured monitoring the network.
    
    Notifications - Nagios itself did something.
'''

# ======================= ALERTS =====================================
def request_alerts_history(
        start_date,
        start_time,
        end_date,
        end_time,
        hostname,
        service
    ):
    
    params = {
        "starttime": convert_to_UNIX(start_date,start_time) if start_date and start_time else 0,
        "endtime": convert_to_UNIX(end_date,end_time) if end_date and end_time else 999999999,
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
    
    return _request_archive("alertlist",params)

def request_current_alert_count():
    # Bug fix: was datetime.now().date (missing parentheses — returns method not value)
    today = datetime.now().date()
        
    params = {
        "starttime": convert_to_UNIX(str(today), time.min),
        "endtime": convert_to_UNIX(str(today), time.max),
    }
    
    return _request_archive("alertcount", params)


def request_alerts_last(
        day=None
    ):
    start, end = get_range_day(day)
        
    params = {
        "starttime": start,
        "endtime": end,
    }
    return _request_archive("alertlist",params)

def request_alert_count_last(
        day=None
    ):
    start, end = get_range_day(day)
        
    params = {
        "starttime": start,
        "endtime": end,
    }
    return _request_archive("alertcount",params)



# ================================ Notifications ==============================


def request_notifications_history(
        start_date,
        start_time,
        end_date,
        end_time,
        hostname,
        service
    ):
    
    params = {
        "starttime": convert_to_UNIX(start_date,start_time) if start_date and start_time else 0,
        "endtime": convert_to_UNIX(end_date,end_time) if end_date and end_time else 999999999,
    }
    
    if hostname:
        params['hostname'] = hostname
            
    if service:
        params['service'] = service
    
    # Bug fix: was querying "alertlist" — notifications use "notificationlist"
    return _request_archive("notificationlist", params)

def request_current_notifications():

    today = datetime.now().date()
        
    params = {
        "starttime": convert_to_UNIX(str(today), time.min),
        "endtime": convert_to_UNIX(str(today), time.max),
    }
    
    # Bug fix: was querying "alertlist" — notifications use "notificationlist"
    return _request_archive("notificationlist", params)

def request_current_alert_notification():
    # Bug fix: was datetime.now().date (missing parentheses — returns method not value)
    today = datetime.now().date()
        
    params = {
        "starttime": convert_to_UNIX(str(today), time.min),
        "endtime": convert_to_UNIX(str(today), time.max),
    }
    
    return _request_archive("notificationcount", params)


def request_notifications_last(
        day=None
    ):
    start, end = get_range_day(day)
        
    params = {
        "starttime": start,
        "endtime": end,
    }
    # Bug fix: was querying "alertlist" — notifications use "notificationlist"
    return _request_archive("notificationlist",params)

def request_notifications_count_last(
        day=None
    ):
    start, end = get_range_day(day)
        
    params = {
        "starttime": start,
        "endtime": end,
    }
    return _request_archive("alertcount",params)