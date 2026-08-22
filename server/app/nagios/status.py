import requests 
from flask import current_app
import sqlalchemy as sa
from app import db
from history_models import *
from datetime import datetime, timezone
from app.nagios.version import latest, last_checked
from app.api.helper import convert_host_state_type_enum, convert_plugin_status_type_enum, convert_acknowledgement_type_enum, convert_connection_state_type_enum, convert_service_state_type_enum, convert_to_UTC, parse_perf_data

# If nagios is installed externally (for some reason, or in a docker container, what is the IP, though this may net be needed)
NAGIOS_URL = "http://192.168.130.10/nagios/cgi-bin/statusjson.cgi"

USERNAME = "nagiosadmin"
PASSWORD = "password"

def insert_programstatus_data(data):
    try:
        program_status = ProgramStatus(
            Timestamp= datetime.now(timezone.utc),
            Version= data['version'],
            Update_Available= False,
            New_Version= latest,
            Last_Update_Check= last_checked,
            NagiosPID= data['nagios_pid'],
            Enable_Notifications= data['enable_notifications'],
            Enable_Flap_Detection= data['enable_flap_detection'],
            Daemon_Mode= data['daemon_mode'],
            Program_Start_Time= data['program_start']
        )
        db.session.add(program_status)
        db.session.commit()
    except Exception as e:
        # Bug fix: was db.rollback() — must be db.session.rollback()
        db.session.rollback()
        current_app.logger.exception("Failed to insert program status")

def insert_host_status_data(data):
    try:
        plugin_status = data['plugin_output'].split(" ")[1]
        
        host_status = HostStatus(
            Timestamp= convert_to_UTC(data['last_update']),
            Hostname= data['name'],
            Current_State= convert_host_state_type_enum(data['status']),
            Plugin_Status=  convert_plugin_status_type_enum(plugin_status),
            Plugin_Output= data['plugin_output'],
            State_Type= convert_connection_state_type_enum(data['check_type']),
            Current_Attempt= int(data['current_attempt']), 
            Max_Attempts= int(data['max_attempt']),
            Last_Check= convert_to_UTC(data['last_check']),
            Next_Check= convert_to_UTC(data['next_check']),
            Last_State_Change= convert_to_UTC(data['last_state_change']),
            Last_Hard_State_Change= convert_to_UTC(data['last_hard_state_change']),
            Last_Time_Up= convert_to_UTC(data['last_time_up']),
            Last_Time_Down= convert_to_UTC(data['last_time_down']),
            Last_Time_Unreachable= convert_to_UTC(data['last_time_unreachable']),
            Check_Latency= float(data['latency']),
            Check_Execution_Time= float(data['execution_time']),
            Is_Flapping= data['is_flapping'],
            Acknowledgement_Type= data['acknowledgement_type'],
            Scheduled_Downtime_Depth= data['scheduled_downtime_depth'],
            Notification_Enabled= data['notifications_enabled']
        )
        
        db.session.add(host_status)
        db.session.flush()
        
        # Bug fix: was iterating data['plugin_output'] (the text) instead of
        # data['performance_data'] or perf_data field. Nagios statusjson puts
        # perf data in 'performance_data', which is space-separated key=value
        # pairs.  We guard against an empty / missing field gracefully.
        perf_raw = data.get('performance_data', '') or ''

        for perf in perf_raw.split(" "):
            if not perf or "=" not in perf:
                continue

            perf_data = parse_perf_data(perf)
            
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
            # Bug fix: db.session.add was outside the loop — every perf entry
            # must be added individually inside the loop
            db.session.add(host_perf_data)
        
        db.session.commit()
    except Exception as e:
        # Bug fix: was db.rollback()
        db.session.rollback()
        current_app.logger.exception("Failed to insert host status")
        
def insert_service_status_data(service, data):
    try:
        
        service_status = ServiceStatus(
            Timestamp= convert_to_UTC(data['last_update']),
            Hostname= data['name'],
            Service= service, 
            Current_State= convert_service_state_type_enum(data['status']),
            Plugin_Output= data['plugin_output'],
            State_Type= data['state_type'],
            Last_Time_Ok= convert_to_UTC(data['last_time_ok']),
            Last_Time_Warning= convert_to_UTC(data['last_time_warning']),
            Last_Time_Critical= convert_to_UTC(data['last_time_critical']),
            Last_Time_Unknown= convert_to_UTC(data['last_time_unknown']),
            Current_Attempt= data['current_attempt'],
            Max_Attempts= data['max_attempt'],
            Last_Check= convert_to_UTC(data['last_check']),
            Next_Check= convert_to_UTC(data['next_check']),
            Last_State_Change= convert_to_UTC(data['last_state_change']),
            Last_Hard_State_Change= convert_to_UTC(data['last_hard_state_change']),
            Check_Latency= float(data['latency']),
            Check_Execution_Time= float(data['execution_time']),
            Notification_Enabled= data['notifications_enabled'],
            Acknowledgement_Type= data['acknowledgement_type'],
            Is_Flapping= data['is_flapping'],
            Scheduled_Downtime_Depth= data['scheduled_downtime_depth']
        )
        
        db.session.add(service_status)
        db.session.flush()
        
        # Bug fix: was data['plugin_putput'] (typo) and was missing add+flush
        # inside loop; now uses performance_data field correctly
        perf_raw = data.get('performance_data', '') or ''

        for perf in perf_raw.split(" "):
            if not perf or "=" not in perf:
                continue

            perf_data = parse_perf_data(perf)
            
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
