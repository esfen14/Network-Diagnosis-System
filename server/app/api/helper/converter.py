from app.system_models import UserStatus
from typing import Union
from email_validator import validate_email
from app.history_models import ConnectionStateType, HostStateType, ServiceStateType, PluginStatusType, AcknowledgementType
from datetime import datetime, timedelta
    
"""
This is a separation of conern regarding conversion of data
"""
def convert_user_status(status):
    status = status.strip().upper()
    return getattr(UserStatus, status)

def convert_host_state_type_enum(str):
    return getattr(HostStateType, str.upper())

def convert_connection_state_type_enum(str):
    return getattr(ConnectionStateType, str.upper())

def convert_service_state_type_enum(str):
    return getattr(ServiceStateType, str.upper())

def convert_plugin_status_type_enum(str):
    return getattr(PluginStatusType, str.upper())

def convert_acknowledgement_type_enum(str):
    return getattr(AcknowledgementType, str.upper())

def convert_to_UTC(time):
    return datetime.datetime.fromtimestamp(time/1000, datetime.timezone.utc)

def convert_to_UNIX(date_str, time_str):
    dt = datetime.strptime(
        f"{date_str} {time_str}",
        "%m:%d:%Y %H:%M"
    )
    return int(dt.timestamp())

def normalize_email(email):
    return validate_email(email, check_deliverability=False).normalized

def split_value_unit(data):
    i = 0
  
    while i < len(data) and data[i].isdigit() or data[i] in ".-+":
        i+=1
    
    # get all the strings until where the loop stops at
    # get the strings at [start:stop]
    measured_value = float(data[:i])
    # get the strings starting from i
    unit = data[i:] or None
    return measured_value, unit
    
def parse_perf_data(perf_data):
    raw_metric = perf_data.split("=")
    metric = raw_metric[0]
    metric_data = raw_metric[1].split(";")
    
    data = metric_data[0]
    
    measured_value, unit = split_value_unit(data)
    
    '''
    format of the statement:
    use metric_data if metric_data(has data) else None
    '''
    
    warning_threshold = float(metric_data[1]) if metric_data[1] else None
    
    critical_threshold = float(metric_data[2]) if metric_data[2] else None
    
    minimum = float(metric_data[3]) if metric_data[3] else None
    
    maximum = float(metric_data[4]) if len(metric_data) > 4 and metric_data[4] else None
    
    return {
        "metric": str(metric),
        "measured_value": measured_value,
        "unit": unit,
        "warning_threshold": warning_threshold,
        "critical_threshold": critical_threshold,
        "minimum": minimum,
        "maximum": maximum
    }
    
def get_range_day(days):
    end = datetime.now()
    start = end - timedelta(days)
    return int(start.timestamp()), int(end.timestamp())

def get_range_custom(start_str, end_str):
    """
    Convert a pair of ISO-8601 date strings (YYYY-MM-DD) to a UNIX timestamp
    range covering the full calendar days.

    start_str and end_str are both inclusive.
    Returns (start_unix, end_unix) as integers.

    Raises ValueError if the strings are malformed or end is before start.
    """
    fmt = "%Y-%m-%d"
    start_dt = datetime.strptime(start_str, fmt).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end_dt = datetime.strptime(end_str, fmt).replace(
        hour=23, minute=59, second=59, microsecond=999999
    )

    if end_dt < start_dt:
        raise ValueError("end_date must be on or after start_date")

    return int(start_dt.timestamp()), int(end_dt.timestamp())
