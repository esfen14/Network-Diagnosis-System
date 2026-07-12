from datetime import datetime
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

class HostStatus(db.Model):
    # Table Name
    __tablename__ = "HOST_STATUS"
    __bind_key__ = "history"

    # Table Fields
    HostStatusID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Timestamp: so.Mapped[datetime] = so.mapped_column(index=True)
    Hostname: so.Mapped[str] = so.mapped_column(sa.String(100), index=True)
    Current_State: so.Mapped[HostStateType] = so.mapped_column(sa.Enum(HostStateType))
    Plugin_Status: so.Mapped[PluginStatusType] = so.mapped_column(sa.Enum(PluginStatusType))
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

    # Relationships
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
    Timestamp:  so.Mapped[datetime] = so.mapped_column(index=True)
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
    
    # Relationships
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
    Timestamp: so.Mapped[datetime] = so.mapped_column(index=True)
    Version: so.Mapped[Optional[str]] = so.mapped_column(sa.String(20))
    Update_Available: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    New_Version: so.Mapped[Optional[str]] = so.mapped_column(sa.String(20))
    Last_Update_Check: so.Mapped[datetime] = so.mapped_column()
    NagiosPID: so.Mapped[Optional[int]] = so.mapped_column()
    Enable_Notifications:  so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    Enable_Flap_Detection: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    Daemon_Mode: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=True)
    Program_Start_Time: so.Mapped[datetime] = so.mapped_column()
    Passive_Host_Checks_Enabled: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    Active_Host_Checks_Enabled: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    Passive_Service_Checks_Enabled: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    Active_Service_Checks_Enabled: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=True)