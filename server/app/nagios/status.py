import requests 
from flask import current_app
import sqlalchemy as sa
from app import db
from history_models import *
from datetime import datetime, timezone
from app.nagios.version import latest, last_checked
from app.api.helper import convert_host_state_type_enum, convert_plugin_status_type_enum, convert_acknowledgement_type_enum, convert_connection_state_type_enum, convert_service_state_type_enum, convert_to_UTC, parse_perf_token

# If nagios is installed externally (for some reason, or in a docker container, what is the IP, though this may net be needed)
NAGIOS_URL = "http://192.168.130.10/nagios/cgi-bin/statusjson.cgi"

USERNAME = "nagiosadmin"
PASSWORD = "password"

def insert_programstatus_data(data):
    try:
        program_status = ProgramStatus(
            Timestamp=datetime.now(timezone.utc),
            Version=data.get('version'),
            Update_Available=False,
            New_Version=latest,
            Last_Update_Check=last_checked,
            NagiosPID=data.get('nagios_pid'),
            Enable_Notifications=data.get('enable_notifications'),
            Enable_Flap_Detection=data.get('enable_flap_detection'),
            Daemon_Mode=data.get('daemon_mode'),
            Program_Start_Time=data.get('program_start'),
            Passive_Host_Checks_Enabled=data.get('passive_host_checks_enabled'),
            Active_Host_Checks_Enabled=data.get('active_host_checks_enabled'),
            Passive_Service_Checks_Enabled=data.get('passive_service_checks_enabled'),
            Active_Service_Checks_Enabled=data.get('active_service_checks_enabled'),
        )
        db.session.add(program_status)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Failed to insert program status")

def _extract_plugin_status(plugin_output):
    """Extract the status keyword (OK/WARNING/CRITICAL/UNKNOWN) from plugin output.
    
    Nagios plugins use diverse output formats. Hardcoded split(" ")[1] crashes on
    check_icmp, check_procs, check_http, check_dns, check_nagios, check_ntp_time,
    check_mysql, check_uptime, check_sensors, and many others.
    
    Strategy: case-insensitive search for status keywords in the output string.
    Returns the first match found, or UNKNOWN as fallback.
    """
    if not plugin_output:
        return "Unknown"
    upper = plugin_output.upper()
    for keyword in ("CRITICAL", "WARNING", "UNKNOWN", "OK"):
        if keyword in upper:
            return keyword
    return "Unknown"


def insert_host_status_data(data):
    try:
        plugin_status = _extract_plugin_status(data.get('plugin_output', ''))
        
        host_status = HostStatus(
            Timestamp=convert_to_UTC(data.get('last_update')),
            Hostname=data.get('name'),
            Current_State=convert_host_state_type_enum(data.get('status')),
            Plugin_Status=convert_plugin_status_type_enum(plugin_status),
            Plugin_Output=data.get('plugin_output', ''),
            State_Type=convert_connection_state_type_enum(data.get('state_type')),
            Current_Attempt=int(data.get('current_attempt', 1)),
            Max_Attempts=int(data.get('max_attempt', 3)),
            Last_Check=convert_to_UTC(data.get('last_check')),
            Next_Check=convert_to_UTC(data.get('next_check')),
            Last_State_Change=convert_to_UTC(data.get('last_state_change')),
            Last_Hard_State_Change=convert_to_UTC(data.get('last_hard_state_change')),
            Last_Time_Up=convert_to_UTC(data.get('last_time_up')),
            Last_Time_Down=convert_to_UTC(data.get('last_time_down')),
            Last_Time_Unreachable=convert_to_UTC(data.get('last_time_unreachable')),
            Check_Latency=float(data.get('latency', 0)),
            Check_Execution_Time=float(data.get('execution_time', 0)),
            Is_Flapping=data.get('is_flapping'),
            Acknowledgement_Type=convert_acknowledgement_type_enum(data.get('acknowledgement_type')),
            Scheduled_Downtime_Depth=data.get('scheduled_downtime_depth', 0),
            Notification_Enabled=data.get('notifications_enabled')
        )
        
        db.session.add(host_status)
        db.session.flush()
        
        # data['performance_data'] or perf_data field. Nagios statusjson puts
        # perf data in 'performance_data', which is space-separated key=value
        # pairs.  We guard against an empty / missing field gracefully.
        perf_raw = data.get('performance_data', '') or ''

        for perf in perf_raw.split(" "):

            if not perf or ("=" not in perf and ":" not in perf):
                continue

            for perf_data in parse_perf_token(perf):
                host_perf_data = HostPerfData(
                    HostStatusID= host_status.HostStatusID,
                    Metric= perf_data['metric'],
                    Measured_Value= perf_data['measured_value'],
                    Unit= perf_data['unit'],
                    Warning_Threshold= perf_data['warning_threshold'],
                    Critical_Threshold= perf_data['critical_threshold'],
                    Minimum= perf_data['minimum'],
                    Maximum= perf_data['maximum']
                )

                db.session.add(host_perf_data)
        
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Failed to insert host status")
        
def insert_service_status_data(service, data):
    try:
        service_status = ServiceStatus(
            Timestamp=convert_to_UTC(data.get('last_update')),
            Hostname=data.get('name'),
            Service=service,
            Current_State=convert_service_state_type_enum(data.get('status')),
            Plugin_Output=data.get('plugin_output', ''),
            State_Type=convert_connection_state_type_enum(data.get('state_type')),
            Last_Time_Ok=convert_to_UTC(data.get('last_time_ok')),
            Last_Time_Warning=convert_to_UTC(data.get('last_time_warning')),
            Last_Time_Critical=convert_to_UTC(data.get('last_time_critical')),
            Last_Time_Unknown=convert_to_UTC(data.get('last_time_unknown')),
            Current_Attempt=int(data.get('current_attempt', 1)),
            Max_Attempts=int(data.get('max_attempt', 3)),
            Last_Check=convert_to_UTC(data.get('last_check')),
            Next_Check=convert_to_UTC(data.get('next_check')),
            Last_State_Change=convert_to_UTC(data.get('last_state_change')),
            Last_Hard_State_Change=convert_to_UTC(data.get('last_hard_state_change')),
            Check_Latency=float(data.get('latency', 0)),
            Check_Execution_Time=float(data.get('execution_time', 0)),
            Notification_Enabled=data.get('notifications_enabled'),
            Acknowledgement_Type=convert_acknowledgement_type_enum(data.get('acknowledgement_type')),
            Is_Flapping=data.get('is_flapping'),
            Scheduled_Downtime_Depth=data.get('scheduled_downtime_depth', 0)
        )
        
        db.session.add(service_status)
        db.session.flush()
        
        # Bug fix: was data['plugin_putput'] (typo) and was missing add+flush
        # inside loop; now uses performance_data field correctly
        perf_raw = data.get('performance_data', '') or ''

        for perf in perf_raw.split(" "):
            # Bug fix: bare "=" check silently dropped colon-separated
            # perfdata (e.g. check_flexlm's "flexlm::up:2;down:1"). Skip
            # only tokens with neither "=" nor ":" — parse_perf_token
            # handles both separator styles.
            if not perf or ("=" not in perf and ":" not in perf):
                continue

            for perf_data in parse_perf_token(perf):
                service_perf_data = ServicePerfData(
                    ServiceStatusID= service_status.ServiceStatusID,
                    Metric= perf_data['metric'],
                    Measured_Value= perf_data['measured_value'],
                    Unit= perf_data['unit'],
                    Warning_Threshold= perf_data['warning_threshold'],
                    Critical_Threshold= perf_data['critical_threshold'],
                    Minimum= perf_data['minimum'],
                    Maximum= perf_data['maximum'],
                )
                # Bug fix: missing db.session.add inside loop
                db.session.add(service_perf_data)

        db.session.commit()
    except Exception as e:
        # Bug fix: was missing rollback entirely
        db.session.rollback()
        current_app.logger.exception("Failed to insert service status")

def get_status():
    try:
        programStatusParams = {
            "query": "programstatus"
        }

        response = requests.get(
            NAGIOS_URL,
            params=programStatusParams,
            auth=(USERNAME, PASSWORD),
            timeout=10
        )

        response.raise_for_status()

        data = response.json()
        
        programStatus = data['data']['programstatus']
        
        insert_programstatus_data(programStatus)
        
        hostParams = {
            "query": "hostlist",
            "formatoptions": "enumerate",
            "details": "true"
        }

        response = requests.get(
            NAGIOS_URL,
            params=hostParams,
            auth=(USERNAME, PASSWORD),
            timeout=10
        )
        response.raise_for_status()

        data = response.json()
        hostlist = data['data']['hostlist']
        
        for hostname, host_data in hostlist.items():
            
            insert_host_status_data(host_data)

            serviceParams = {
                "query": "servicelist",
                "hostname": hostname,
                "formatoptions": "enumerate",
                "details": "true"    
            }

            response = requests.get(
                NAGIOS_URL,
                params=serviceParams,
                auth=(USERNAME, PASSWORD),
                timeout=10
            )
            data = response.json()

            servicelist = data['data']['servicelist'].get(hostname, {})

            for service, service_data in servicelist.items():
                insert_service_status_data(service, service_data)
    except requests.RequestException as e:
        current_app.logger.error("Failed to request Nagios status: %s", e)
