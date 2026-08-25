from app.system_models import UserStatus
from typing import Union
from email_validator import validate_email
from app.history_models import ConnectionStateType, HostStateType, ServiceStateType, PluginStatusType, AcknowledgementType
from datetime import datetime, timedelta, timezone
    
"""
This is a separation of conern regarding conversion of data
"""
def convert_user_status(status):
    status = status.strip().upper()
    return getattr(UserStatus, status)

def convert_host_state_type_enum(str):
    return getattr(HostStateType, str.upper())

def convert_connection_state_type_enum(val):
    """Convert Nagios state_type to ConnectionStateType enum.
    
    Nagios sends state_type as "0" (soft) or "1" (hard).
    SQLAlchemy enum expects "Soft" or "Hard".
    """
    if val is None:
        return ConnectionStateType.SOFT
    s = str(val).strip()
    if s in ("0", "Soft", "SOFT", "soft"):
        return ConnectionStateType.SOFT
    if s in ("1", "Hard", "HARD", "hard"):
        return ConnectionStateType.HARD
    # Fallback: try direct getattr
    try:
        return getattr(ConnectionStateType, s.upper())
    except AttributeError:
        return ConnectionStateType.SOFT

def convert_service_state_type_enum(val):
    """Convert Nagios status to ServiceStateType enum.
    
    Nagios sends status as "0" (OK), "1" (WARNING), "2" (CRITICAL), "3" (UNKNOWN).
    """
    if val is None:
        return ServiceStateType.UNKNOWN
    s = str(val).strip()
    mapping = {
        "0": ServiceStateType.OK,
        "1": ServiceStateType.WARNING,
        "2": ServiceStateType.CRITICAL,
        "3": ServiceStateType.UNKNOWN,
        "Ok": ServiceStateType.OK,
        "OK": ServiceStateType.OK,
        "Warning": ServiceStateType.WARNING,
        "WARNING": ServiceStateType.WARNING,
        "Critical": ServiceStateType.CRITICAL,
        "CRITICAL": ServiceStateType.CRITICAL,
        "Unknown": ServiceStateType.UNKNOWN,
        "UNKNOWN": ServiceStateType.UNKNOWN,
    }
    return mapping.get(s, ServiceStateType.UNKNOWN)

def convert_plugin_status_type_enum(val):
    """Convert plugin status string to PluginStatusType enum.
    
    Handles both direct enum names ("Ok", "Warning", etc.) and Nagios
    numeric codes ("0", "1", "2", "3").
    """
    if val is None:
        return PluginStatusType.UNKNOWN
    s = str(val).strip()
    mapping = {
        "0": PluginStatusType.OK,
        "1": PluginStatusType.WARNING,
        "2": PluginStatusType.CRITICAL,
        "3": PluginStatusType.UNKNOWN,
        "Ok": PluginStatusType.OK,
        "OK": PluginStatusType.OK,
        "Warning": PluginStatusType.WARNING,
        "WARNING": PluginStatusType.WARNING,
        "Critical": PluginStatusType.CRITICAL,
        "CRITICAL": PluginStatusType.CRITICAL,
        "Unknown": PluginStatusType.UNKNOWN,
        "UNKNOWN": PluginStatusType.UNKNOWN,
    }
    return mapping.get(s, PluginStatusType.OK)

def convert_acknowledgement_type_enum(str):
    return getattr(AcknowledgementType, str.upper())

def convert_to_UTC(timestamp):
    # Bug fix: was datetime.datetime.fromtimestamp(..., datetime.timezone.utc)
    # — datetime is already imported as the class, so it's just datetime.fromtimestamp
    # Nagios timestamps are Unix seconds (int), not milliseconds.
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, timezone.utc)

def convert_to_UNIX(date_str, time_obj):
    # Bug fix: was strptime(f"{date_str} {time_str}", "%m:%d:%Y %H:%M")
    # — the separator in the format was ":" not "-" and time_obj is a datetime.time,
    # not a string; also date format from Nagios is YYYY-MM-DD not MM:DD:YYYY.
    if hasattr(time_obj, 'hour'):
        # time_obj is a datetime.time instance (e.g. time.min / time.max)
        time_str = time_obj.strftime("%H:%M:%S")
    else:
        time_str = str(time_obj)
    dt = datetime.strptime(
        f"{date_str} {time_str}",
        "%Y-%m-%d %H:%M:%S"
    )
    return int(dt.timestamp())

def normalize_email(email):
    return validate_email(email, check_deliverability=False).normalized

def split_value_unit(data):
    """Split a performance data value string into (measured_value, unit).
    
    Handles formats like "45.2%", "100", "1.5s", "-5.2", "1024B".
    The parentheses around the `or` clause fix operator precedence:
    without them, `and` binds tighter than `or`, causing IndexError
    when data[i] is not a digit but the `or` short-circuits past bounds.
    """
    i = 0
    while i < len(data) and (data[i].isdigit() or data[i] in ".-+"):
        i += 1
    
    if i == 0:
        return None, data or None
    
    measured_value = float(data[:i])
    unit = data[i:] or None
    return measured_value, unit
    
def parse_perf_data(perf_data):
    """Parse a single Nagios performance data key=value pair.

    Format: label=value[unit];[warn];[crit];[min];[max]
    Handles missing thresholds gracefully (e.g., "metric=45.2%" with no ;).
    """
    raw_metric = perf_data.split("=")
    if len(raw_metric) < 2:
        return {
            "metric": perf_data,
            "measured_value": None,
            "unit": None,
            "warning_threshold": None,
            "critical_threshold": None,
            "minimum": None,
            "maximum": None,
        }

    metric = raw_metric[0]
    metric_data = raw_metric[1].split(";")

    data = metric_data[0]
    measured_value, unit = split_value_unit(data)

    # Bounds-safe threshold extraction
    warning_threshold = float(metric_data[1]) if len(metric_data) > 1 and metric_data[1] else None
    critical_threshold = float(metric_data[2]) if len(metric_data) > 2 and metric_data[2] else None
    minimum = float(metric_data[3]) if len(metric_data) > 3 and metric_data[3] else None
    maximum = float(metric_data[4]) if len(metric_data) > 4 and metric_data[4] else None

    return {
        "metric": str(metric),
        "measured_value": measured_value,
        "unit": unit,
        "warning_threshold": warning_threshold,
        "critical_threshold": critical_threshold,
        "minimum": minimum,
        "maximum": maximum,
    }

def parse_perf_token(token):
    """Parse one whitespace-delimited performance-data token into one or more
    metric dicts (see parse_perf_data for the dict shape).

    Most plugins follow the standard `label=value[unit];warn;crit;min;max`
    convention, in which case this just delegates to parse_perf_data.

    check_flexlm is the one shipped plugin that breaks that convention: it
    emits a single semicolon-joined token with `:` instead of `=` as the
    label/value separator and no thresholds, e.g. "flexlm::up:2;down:1"
    (two metrics — "flexlm::up"=2 and "down"=1 — packed into one token).
    For that shape we split on ";" and treat each "label:value" piece as
    its own metric with no thresholds.
    """
    if "=" in token:
        return [parse_perf_data(token)]

    if ":" in token:
        metrics = []
        for piece in token.split(";"):
            if not piece or ":" not in piece:
                continue
            label, _, value = piece.rpartition(":")
            measured_value, unit = split_value_unit(value)
            metrics.append({
                "metric": label,
                "measured_value": measured_value,
                "unit": unit,
                "warning_threshold": None,
                "critical_threshold": None,
                "minimum": None,
                "maximum": None,
            })
        if metrics:
            return metrics

    return [parse_perf_data(token)]
    
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
