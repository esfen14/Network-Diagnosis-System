from datetime import datetime, timezone
from typing import Optional
from enum import Enum

import sqlalchemy as sa

import sqlalchemy.orm as so 

from app import db 



class ConnectionStateType(Enum):
    SOFT = "Soft"
    HARD = "Hard"

class HostStateType(Enum):
    UP = "Up"
    DOWN = "Down"
    UNREACHABLE = "Unreachable"

class ServiceStateType(Enum):
    OK = "Ok"
    WARNING = "Warning"
    CRITICAL = "Critical"
    UNKNOWN = "Unknown"
    
class PluginStatusType(Enum):
    OK = "Ok"
    WARNING = "Warning"
    CRITICAL = "Critical"
    UNKNOWN = "Unknown" 

class AcknowledgementType(Enum):
    NOACK = "No Acknowledgement"
    NORMACK = "Normal Acknowledgement"
    STICKYACK = "Sticky Acknowledgement"
    
class NagiosLog(db.Model):
    # Table Name
    __tablename__ = "NAGIOS_LOG" 
    __bind_key__ = "history"

    # Table Fields
    NagiosLogID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Timestamp: so.Mapped[datetime] = so.mapped_column(index=True)
    Entry_Type: so.Mapped[str] = so.mapped_column(sa.String(100))

    # Relationships
    HostLog: so.Mapped[Optional['HostLog']] = so.relationship(back_populates='NagiosLogInfo', uselist=False)
    ServiceLog: so.Mapped[Optional['ServiceLog']] = so.relationship(back_populates='NagiosLogInfo', uselist=False)
    Message: so.Mapped[Optional['LogMessage']] = so.relationship(back_populates='NagiosLogInfo', uselist=False)
 
class HostLog(db.Model):
    # Table Name
    __tablename__ = "HOST_LOG"
    __bind_key__ = "history"
    
    # Table Fields
    HostAlertID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Is_Alert: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    Hostname: so.Mapped[str] = so.mapped_column(sa.String(100), index=True)
    Host_State: so.Mapped[HostStateType] = so.mapped_column(sa.Enum(HostStateType))
    State_Type: so.Mapped[ConnectionStateType] = so.mapped_column(sa.Enum(ConnectionStateType))
    Attempt_Count: so.Mapped[int] = so.mapped_column()
    Plugin_Status: so.Mapped[PluginStatusType] = so.mapped_column(sa.Enum(PluginStatusType))
    Plugin_Output: so.Mapped[str] = so.mapped_column(sa.String(100))

    # Foreign Key Field
    NagiosLogID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(NagiosLog.NagiosLogID), index=True, unique=True)

    # Relationship
    NagiosLogInfo: so.Mapped['NagiosLog'] = so.relationship(back_populates='HostLog')

class ServiceLog(db.Model): 
    # Table Name
    __tablename__ = "SERVICE_LOG"
    __bind_key__ = "history"

    # Table Fields
    ServiceStateID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Is_Alert: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    Hostname: so.Mapped[str] = so.mapped_column(sa.String(100), index=True)
    Service: so.Mapped[str] = so.mapped_column(sa.String(150), index=True)
    Service_State: so.Mapped[ServiceStateType] = so.mapped_column(sa.Enum(ServiceStateType))
    State_Type: so.Mapped[ConnectionStateType] = so.mapped_column(sa.Enum(ConnectionStateType))
    Attempt_count: so.Mapped[int] = so.mapped_column()
    Plugin_Status: so.Mapped[PluginStatusType] = so.mapped_column(sa.Enum(PluginStatusType))
    Plugin_Output: so.Mapped[str] = so.mapped_column(sa.String(255))

    # Foreign Key Field
    NagiosLogID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(NagiosLog.NagiosLogID), index=True, unique=True)
    
    # Relationship
    NagiosLogInfo: so.Mapped['NagiosLog'] = so.relationship(back_populates='ServiceLog')

class LogMessage(db.Model):
    # Table Name 
    __tablename__ = "LOG_MESSAGE"
    __bind_key__ = "history"

    # Table Fields
    LogMessageID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Message: so.Mapped[str] = so.mapped_column(sa.String(255))
    
    # Foreign Key Fields
    NagiosLogID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(NagiosLog.NagiosLogID), index=True, unique=True)

    # Relationships
    NagiosLogInfo: so.Mapped['NagiosLog'] = so.relationship(back_populates='Message')

class NetworkStatus(db.Model):
    # Table Name
    __tablename__ = "NAGIOS_STATUS_INFO"
    __bind_key__ = "history"

    # Table Fields    
    StatusID:  so.Mapped[int] = so.mapped_column(primary_key=True)
    Timestamp:  so.Mapped[datetime] = so.mapped_column(index=True)
    Entry_Type: so.Mapped[str] = so.mapped_column(sa.String(20))

    # Relationships
    HostsInfo: so.WriteOnlyMapped['HostStatus'] = so.relationship(back_populates='StatusInfo')
    ServicesInfo: so.WriteOnlyMapped['ServiceStatus'] = so.relationship(back_populates='StatusInfo')
    ProgramStatusInfo: so.WriteOnlyMapped['ProgramStatus'] = so.relationship(back_populates='NetworkStatusInfo')

class HostStatus(db.Model):
    # Table Name
    __tablename__ = "HOST_STATUS"
    __bind_key__ = "history"

    # Table Fields
    HostStatusID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Hostname: so.Mapped[str] = so.mapped_column(sa.String(100), index=True)
    Current_State: so.Mapped[HostStateType] = so.mapped_column(sa.Enum(HostStateType))
    Plugin_Output: so.Mapped[str] = so.mapped_column(sa.String(255))
    State_Type: so.Mapped[ConnectionStateType] = so.mapped_column(sa.Enum(ConnectionStateType))
    Current_Attempt: so.Mapped[int] = so.mapped_column()
    Max_Attempts: so.Mapped[int] = so.mapped_column()
    Last_Check: so.Mapped[datetime] = so.mapped_column()
    Next_Check: so.Mapped[datetime] = so.mapped_column()
    Last_State_Change: so.Mapped[Optional[datetime]] = so.mapped_column()
    Last_Hard_State_Change: so.Mapped[Optional[datetime]] = so.mapped_column()
    Last_Time_Up: so.Mapped[Optional[datetime]] = so.mapped_column()
    Last_Time_Down: so.Mapped[Optional[datetime]] = so.mapped_column()
    Last_Time_Unreachable: so.Mapped[Optional[datetime]] = so.mapped_column()
    Check_Latency: so.Mapped[float] = so.mapped_column(sa.Float(precision=6))
    Check_Execution_Time: so.Mapped[float] = so.mapped_column(sa.Float(precision=6))
    Is_Flapping: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    Acknowledgement_Type: so.Mapped[AcknowledgementType] = so.mapped_column(sa.Enum(AcknowledgementType))
    Scheduled_Downtime_Depth: so.Mapped[int] = so.mapped_column()
    Notification_Enabled: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=True)

    # Foreign Key Field
    StatusID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(NetworkStatus.StatusID), index=True)

    # Relationships
    StatusInfo: so.Mapped['NetworkStatus'] = so.relationship(back_populates='HostsInfo')
    PerfData: so.WriteOnlyMapped['HostPerfData'] = so.relationship(back_populates='HostStatusInfo')
    
class HostPerfData(db.Model):
    # Table Name
    __tablename__ = "HOST_PERF_DATA"
    __bind_key__ = "history"

    # Table Fields
    HostPerfDataID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Metric: so.Mapped[str] = so.mapped_column(sa.String(50))
    Measured_Value: so.Mapped[float] = so.mapped_column(sa.Float(precision=6))
    Unit: so.Mapped[Optional[str]] = so.mapped_column(sa.String(5))
    Warning_Threshold: so.Mapped[Optional[float]] = so.mapped_column(sa.Float(precision=6))
    Critical_Threshold: so.Mapped[Optional[float]] = so.mapped_column(sa.Float(precision=6))
    Minimum: so.Mapped[Optional[float]] = so.mapped_column(sa.Float(precision=6))
    Maximum: so.Mapped[Optional[float]] = so.mapped_column(sa.Float(precision=6))

    # Foreign Key Fields
    HostStatusID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(HostStatus.HostStatusID), index=True)

    # Relationship
    HostStatusInfo: so.Mapped['HostStatus'] = so.relationship(back_populates='PerfData')

class ServiceStatus(db.Model): 
    # Table Name
    __tablename__ = "SERVICE_STATUS"
    __bind_key__ = "history"
    
    # Table Fields
    ServiceStatusID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Hostname: so.Mapped[str] = so.mapped_column(sa.String(100), index=True) 
    Service: so.Mapped[str] = so.mapped_column(sa.String(150))
    Current_State: so.Mapped[ServiceStateType] = so.mapped_column(sa.Enum(ServiceStateType))
    Plugin_Output: so.Mapped[str] = so.mapped_column(sa.String(255))
    State_Type: so.Mapped[ConnectionStateType] = so.mapped_column(sa.Enum(ConnectionStateType))
    Last_Time_Ok: so.Mapped[Optional[datetime]] = so.mapped_column()
    Last_Time_Warning: so.Mapped[Optional[datetime]] = so.mapped_column()
    Last_Time_Critical: so.Mapped[Optional[datetime]] = so.mapped_column()
    Last_Time_Unknown: so.Mapped[Optional[datetime]] = so.mapped_column()
    Current_Attempt: so.Mapped[int] = so.mapped_column()
    Max_Attempts: so.Mapped[int] = so.mapped_column()
    Last_Check: so.Mapped[datetime] = so.mapped_column()
    Next_Check: so.Mapped[datetime] = so.mapped_column()
    Last_State_Change: so.Mapped[Optional[datetime]] = so.mapped_column()
    Last_Hard_State_Change: so.Mapped[Optional[datetime]] = so.mapped_column()
    Check_Latency: so.Mapped[float] = so.mapped_column(sa.Float(precision=6))
    Check_Execution_Time: so.Mapped[float] = so.mapped_column(sa.Float(precision=6))
    Notification_Enabled: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    Acknowledgement_Type: so.Mapped[AcknowledgementType] = so.mapped_column(sa.Enum(AcknowledgementType))
    Is_Flapping: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    Scheduled_Downtime_Depth: so.Mapped[int] = so.mapped_column()

    # Foreign Key Fields
    StatusID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(NetworkStatus.StatusID), index=True)

    # Relationships
    StatusInfo: so.Mapped['NetworkStatus'] = so.relationship(back_populates='ServicesInfo')
    PerfData: so.WriteOnlyMapped['ServicePerfData'] = so.relationship(back_populates='ServiceStatusInfo')

class ServicePerfData(db.Model):
    # Table Names
    __tablename__ = "SERVICE_PERF_DATA"
    __bind_key__ = "history"
    
    # Table Fields
    ServicePerfDataID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Metric: so.Mapped[str] = so.mapped_column(sa.String(50))
    Measured_Value: so.Mapped[float] = so.mapped_column(sa.Float(precision=6))
    Unit: so.Mapped[Optional[str]] = so.mapped_column(sa.String(5))
    Warning_Threshold: so.Mapped[Optional[float]] = so.mapped_column(sa.Float(precision=6))
    Critical_Threshold: so.Mapped[Optional[float]] = so.mapped_column(sa.Float(precision=6))
    Minimum: so.Mapped[Optional[float]] = so.mapped_column(sa.Float(precision=6))
    Maximum:so.Mapped[Optional[float]] = so.mapped_column(sa.Float(precision=6))

    # Foreign Key Field
    ServiceStatusID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(ServiceStatus.ServiceStatusID), index=True)

    # Relationship
    ServiceStatusInfo: so.Mapped['ServiceStatus'] = so.relationship(back_populates='PerfData')

class ProgramStatus(db.Model):
    # Table Name
    __tablename__ = "PROGRAM_STATUS"
    __bind_key__ = "history"
    
    # Table Fields
    ProgramStatusID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Enable_Notifications:  so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    Enable_Flap_Detection: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    Daemon_Mode: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=True)
    Program_Start_Time: so.Mapped[datetime] = so.mapped_column()
    Passive_Host_Checks_Enabled: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    Active_Host_Checks_Enabled: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    Passive_Service_Checks_Enabled: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    Active_Service_Checks_Enabled: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=True)

    # Foreign Key Field
    StatusID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(NetworkStatus.StatusID), index=True)

    # Relationship
    NetworkStatusInfo: so.Mapped['NetworkStatus'] = so.relationship(back_populates='ProgramStatusInfo')

class ReadStatus(Enum):
    SUCCESS = "Success"
    INPROGRESS = "In Progress"
    ERROR = "Error"

class FileReadTracker(db.Model):
    # Table Name
    __tablename__ = "FILE_READ_TRACKER"
    __bind_key__ = "history"
    
    # Table Fields
    FileReadTrackerID:  so.Mapped[int] = so.mapped_column(primary_key=True)
    File_Name: so.Mapped[str] = so.mapped_column(sa.String(100))
    File_Path: so.Mapped[str] = so.mapped_column(sa.String(500))
    Last_Line_Read: so.Mapped[int] = so.mapped_column()
    Last_Read_Timestamp: so.Mapped[datetime] = so.mapped_column()
    Read_Status: so.Mapped[ReadStatus] = so.mapped_column(sa.Enum(ReadStatus))
    Error_Message: so.Mapped[Optional[str]] = so.mapped_column(sa.String(500))