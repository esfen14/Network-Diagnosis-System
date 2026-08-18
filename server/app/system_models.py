from datetime import datetime, timezone
from typing import Optional
from flask_login import UserMixin
from app import login
from enum import Enum

import sqlalchemy as sa

import sqlalchemy.orm as so

from app import db

from werkzeug.security import generate_password_hash, check_password_hash


class Permission(db.Model):
    # Table Name
    __tablename__ = "PERMISSION"
    
    # Table Fields
    PermissionID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Name: so.Mapped[str] = so.mapped_column(sa.String(50), unique=True, index=True)
    Description: so.Mapped[Optional[str]] = so.mapped_column(sa.String(255))
    
    RolePermission: so.WriteOnlyMapped['RolePermission'] = so.relationship(back_populates='Permissions')
        
class Role(db.Model):
    # Table Name
    __tablename__ = "ROLE"
    
    # Table Fields
    RoleID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Name: so.Mapped[str] = so.mapped_column(sa.String(50), unique=True, index=True)
    Is_Active: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=True)
    Description: so.Mapped[Optional[str]] = so.mapped_column(sa.String(150))
    Created_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))

    """
    Relationship with User and RolePermission table
    WriteOnlyMappped links each role to many users and many permissions
    WriteOnlyMapped is to explicity load only that is queried
    back_populate spcifies that you can access this table from either side, (i.e DeploymentHistory <--> ActivityLog and vise versa)
    """
    Users: so.WriteOnlyMapped['User'] = so.relationship(back_populates='Role')
    RolePermissions: so.WriteOnlyMapped['RolePermission'] = so.relationship(back_populates='Role')


class RolePermission(db.Model):
    # Table Name
    __tablename__ = "ROLE_PERMISSION"
    
    # Forces rows to be unique 
    __table_args__= (
        sa.UniqueConstraint('RoleID', 'PermissionID', name='uq_role_permission'),
    )
    # Table Fields
    RolePermissionID: so.Mapped[int] = so.mapped_column(primary_key=True)
    
    # Foreign Key Fields
    RoleID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(Role.RoleID), index=True)
    PermissionID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(Permission.PermissionID), index=True)

    """
    Relationship with Role
    back_populate spcifies that you can access this table from either side, (i.e DeploymentHistory <--> ActivityLog and vise versa)
    """
    Role: so.Mapped['Role'] = so.relationship(back_populates='RolePermissions')
    Permissions: so.Mapped['Permission'] = so.relationship(back_populates='RolePermission')
   
"""
UserStatus Enum so that Status is consistent
To call use "User.Status = UserStatus.ACTIVE"
The models class need to be imported to use the Enums
"""
class UserStatus(Enum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"
    SUSPENDED = "Suspended"
    
class User(UserMixin, db.Model):
    # Table Name
    __tablename__ = "USER"

    # Table Fields
    UserID: so.Mapped[int] = so.mapped_column(primary_key=True)
    First_name: so.Mapped[str] = so.mapped_column(sa.String(120))
    Last_name: so.Mapped[str] = so.mapped_column(sa.String(120))
    Email: so.Mapped[str] = so.mapped_column(sa.String(120), unique=True, index=True)
    Hashed_Password: so.Mapped[str] = so.mapped_column(sa.String(256))
    Status: so.Mapped[UserStatus] = so.mapped_column(sa.Enum(UserStatus))
    Created_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Updated_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc),onupdate= lambda: datetime.now(timezone.utc))

    # Foreign Key Field
    RoleID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(Role.RoleID), index=True)

    """
    Relationship with the Logs table this will only load users with the provided Foreign key
    WriteOnlyMapped enables for Many of the ActivityLog
    WriteOnlyMapped is to explicity load only that is queried
    Allows many instances of the user to be used in the ActivityLog
    back_populate sepcifies that you can access this table from either side, (i.e DeploymentHistory <--> ActivityLog and vise versa)
    """
    Logs: so.WriteOnlyMapped['ActivityLog'] = so.relationship(back_populates='User_Logs')

    """
    Gets one instance of the Role Table
    back_populate sepcifies that you can access this table from either side, (i.e DeploymentHistory <--> ActivityLog and vise versa)
    """
    Role: so.Mapped['Role'] = so.relationship(back_populates='Users')  

    """
    Override for the get_id in Flask Login, this is to get the UserID of the user
    rather than call the default id for the user's id
    """
    def get_id(self):
        return str(self.UserID)
    """
    This is to set the password, it uses Flask Login forgenerating password hashes
    """
    def set_password(self, password):
        self.Hashed_Password = generate_password_hash(password)
    
    """
    This is used to check the input password to the password of the user
    This uses Flask login for checking the hash
    """
    def check_password(self, password):
        return check_password_hash(self.Hashed_Password, password)

@login.user_loader
def load_user(id):
    return db.session.get(User, int(id))
    
class ActivityLog(db.Model):
    # Table Name
    __tablename__ = "ACTIVITY_LOG"
    
    # Table Fields
    LogID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Action_Type: so.Mapped[str] = so.mapped_column(sa.String(255))
    Performed_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc)) 

    # Foreign key Field
    UserID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(User.UserID), index=True)

    """
    Gets one instance of the User Table
    back_populate sepcifies that you can access this table from either side, (i.e DeploymentHistory <--> ActivityLog and vise versa)
    """
    User_Logs: so.Mapped[User] = so.relationship(back_populates='Logs')

    """
    Relationships with the specific Log tables
    WriteOnlyMapped enables for Many of the ActivityLog
    WriteOnlyMapped is to explicity load only that is queried
    back_populate sepcifies that you can access this table from either side, (i.e DeploymentHistory <--> ActivityLog and vise versa)
    """
    Deployment: so.WriteOnlyMapped['DeploymentHistory'] = so.relationship(back_populates='Logs')
    Config_Logs: so.WriteOnlyMapped['ConfigurationChanges'] = so.relationship(back_populates='Logs')
    Export_Logs: so.WriteOnlyMapped['ExportLog'] = so.relationship(back_populates='Logs')
    NetDiscover_Logs: so.WriteOnlyMapped['NetworkDiscovery'] = so.relationship(back_populates='Logs')
    
    
"""
DeploymentStatus Enum so that Deployment_Status is consistent
To call use "DeploymentHistory.Deployment_Status = DeploymentStatus.FAILED"
The models class need to be imported to use the Enums
"""
class DeploymentStatus(Enum):
    FAILED="Failed"
    SUCCESS="Success"
    
class DeploymentHistory(db.Model):
    # Table Name
    __tablename__ = "DEPLOYMENT_HISTORY"
    
    # Table Fields
    DeploymentID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Notes: so.Mapped[Optional[str]] = so.mapped_column(sa.String(255))
    Deployment_Status: so.Mapped[DeploymentStatus] = so.mapped_column(sa.Enum(DeploymentStatus))
    Deployed_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Updated_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc), onupdate= lambda: datetime.now(timezone.utc))

    # Foreign Key Fields
    LogID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(ActivityLog.LogID), index=True)

    """
    WriteOnlyMapped enables for Many of the DeploymentHistory
    WriteOnlyMapped is to explicity load only that is queried
    back_populate sepcifies that you can access this table from either side, (i.e DeploymentHistory <--> ActivityLog and vise versa)
    """
    NRPE_Deployment: so.WriteOnlyMapped['NRPEDeployment'] = so.relationship(back_populates='Deployment')
    
    """
    Gets one instance from the ActivityLog table
    back_populate sepcifies that you can access this table from either side, (i.e DeploymentHistory <--> ActivityLog and vise versa)
    """
    Logs: so.Mapped[ActivityLog] = so.relationship(back_populates='Deployment')

class ConfigurationChanges( db.Model):
    # Table Name
    __tablename__ = "CONFIGURATION_CHANGES"
    
    # Table Fields
    ConfChangesID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Conf_Type: so.Mapped[str] = so.mapped_column(sa.String(25))
    Parameter_Name: so.Mapped[str] = so.mapped_column(sa.String(50))
    Old_Value: so.Mapped[str] = so.mapped_column(sa.String(100))
    New_Value: so.Mapped[str] = so.mapped_column(sa.String(100))
    Changed_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))

    # Foreign Key Field
    LogID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(ActivityLog.LogID), index=True)

    """
    Gets one instance of ActivityLog
    back_populate sepcifies that you can access this table from either side, (i.e DeploymentHistory <--> ActivityLog and vise versa)
    """
    Logs: so.Mapped[ActivityLog] = so.relationship(back_populates='Config_Logs')


"""
ExportFormat Enum so that Export_Format is consistent
To call use "ExportFormat.Export_Format = ExportFormat.PDF"
The models class need to be imported to use the Enums
"""
class ExportFormat(Enum):
    CSV="csv"
    PDF="pdf"
    
class ExportLog(db.Model):
    # Table Name
    __tablename__ = "EXPORT_LOG"
    
    # Table Field
    ExportID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Report_Type: so.Mapped[str] = so.mapped_column(sa.String(25))
    Export_Format: so.Mapped[ExportFormat] = so.mapped_column(sa.Enum(ExportFormat))
    Start_Date: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc)) 
    End_Date: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Exported_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))

    # Foreign Key Field
    LogID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(ActivityLog.LogID), index=True)

    """
    Gets on instnce of ActivityLog
    back_populate sepcifies that you can access this table from either side, (i.e DeploymentHistory <--> ActivityLog and vise versa)
    """
    Logs: so.Mapped[ActivityLog] = so.relationship(back_populates='Export_Logs')

"""
ScanStatus Enum so that Scan_Status is consistent
To call use "NetworkDiscovery.Scan_Status = ScanStatus.PENDING"
The models class need to be imported to use the Enums
"""
class ScanStatus(Enum):
    PENDING = "Pending"    
    DEPLOYING = "Deploying"
    DEPLOYED = "Deployed"
    FAILED = "Failed"
    UNREACHABLE = "Unreachable"
    UNINSTALLED = "Uninstalled"

class NetworkDiscovery(db.Model):
    # Table Name
    __tablename__ = "NETWORK_DISCOVERY"
    
    # Table Fields
    NetDiscoveryID:  so.Mapped[int]  = so.mapped_column(primary_key=True)
    Hostname: so.Mapped[Optional[str]] = so.mapped_column(sa.String(100))
    IP_Address: so.Mapped[str] = so.mapped_column(sa.String(16), index=True)
    Subnet_Mask: so.Mapped[str] = so.mapped_column(sa.String(16), index=True)
    MAC_Address: so.Mapped[Optional[str]] = so.mapped_column(sa.String(17), index=True)
    OS_Type: so.Mapped[Optional[str]] = so.mapped_column(sa.String(25))
    Device_Type: so.Mapped[Optional[str]] = so.mapped_column(sa.String(25))
    NRPE_Eligible: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    Scan_Status: so.Mapped[ScanStatus] = so.mapped_column(sa.Enum(ScanStatus))
    Scanned_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))

    # Foreign Key Fields
    LogID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(ActivityLog.LogID), index=True)

    """
    Gets on instnce of ActivityLog
    back_populate sepcifies that you can access this table from either side, (i.e DeploymentHistory <--> ActivityLog and vise versa)
    """
    Logs: so.Mapped[ActivityLog] = so.relationship(back_populates='NetDiscover_Logs')

    """
    WriteOnlyMapped enables for Many of the DeploymentHistory
    WriteOnlyMapped is to explicity load only that is queried
    back_populate sepcifies that you can access this table from either side, (i.e DeploymentHistory <--> ActivityLog and vise versa)
    """
    SSH_Creds: so.WriteOnlyMapped['SSHCredentials'] = so.relationship(back_populates='Device')
    NRPE_Deployment: so.WriteOnlyMapped['NRPEDeployment'] = so.relationship(back_populates='Device')
    

class SSHCredentials(db.Model):
    # Table Name
    __tablename__ = "SSH_CREDENTIALS"
    
    # Table Fields
    SSHID: so.Mapped[int] = so.mapped_column(primary_key=True)
    SSH_Username: so.Mapped[str] = so.mapped_column(sa.String(50))
    SSH_Port: so.Mapped[int] = so.mapped_column(sa.Integer())
    Key_Installed: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    Created_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))

    # Foreign Key Field
    NetworkDiscoveryID:  so.Mapped[int] = so.mapped_column(sa.ForeignKey(NetworkDiscovery.NetDiscoveryID), index=True)

    """
    Gets on instnce of NetworkDiscovery
    back_populate sepcifies that you can access this table from either side, (i.e DeploymentHistory <--> ActivityLog and vise versa)
    """
    Device: so.Mapped[NetworkDiscovery] = so.relationship(back_populates='SSH_Creds')

"""
AgentStatus Enum so that Agent_Status is consistent
To call use "NRPEDeployment.Agent_Status = AgentStatus.DISCOVERED"
The models class need to be imported to use the Enums
"""
class AgentStatus(Enum):
    DISCOVERED = "Discovered"
    PENDING_NRPE = "Pending_NRPE"
    MONITORED = "Monitored"
    UNREACHABLE = "Unreachable"
    EXCLUDED = "Excluded"
    
class NRPEDeployment(db.Model):
    # Table Name
    __tablename__ = "NRPE_DEPLOYMENT"
    
    # Table Fields
    NRPEID: so.Mapped[int] = so.mapped_column(primary_key=True)
    NRPE_Port: so.Mapped[int] = so.mapped_column(sa.Integer())
    Plugin_Installed: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    Agent_Status: so.Mapped[AgentStatus] = so.mapped_column(sa.Enum(AgentStatus))

    # Foreign Key Field
    NetworkDiscoveryID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(NetworkDiscovery.NetDiscoveryID), index=True)
    DeploymentID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(DeploymentHistory.DeploymentID), index=True)

    """
    Gets on instnce of NetworkDiscovery
    back_populate sepcifies that you can access this table from either side, (i.e DeploymentHistory <--> ActivityLog and vise versa)
    """
    Device: so.Mapped[NetworkDiscovery] = so.relationship(back_populates='NRPE_Deployment')
    
    """
    Gets on instnce of DeploymentHistory
    back_populate sepcifies that you can access this table from either side, (i.e DeploymentHistory <--> ActivityLog and vise versa)
    """
    Deployment: so.Mapped[DeploymentHistory] = so.relationship(back_populates='NRPE_Deployment')
    
    """
SystemSettings is a singleton table — there will only ever be one row (Id=1).
This holds system-wide configuration that applies regardless of which
user is logged in (general, security, and system tabs on the Settings page).
"""
class SystemSettings(db.Model):
    # Table Name
    __tablename__ = "SYSTEM_SETTINGS"

    # Table Fields
    Id: so.Mapped[int] = so.mapped_column(primary_key=True)

    # General
    System_Language: so.Mapped[str] = so.mapped_column(sa.String(20), default="English")
    Theme: so.Mapped[str] = so.mapped_column(sa.String(10), default="dark")
    Time_Zone: so.Mapped[str] = so.mapped_column(sa.String(20), default="UTC+08:00")
    Date_Time_Format: so.Mapped[str] = so.mapped_column(sa.String(20), default="DD/MM/YYYY")
    System_Font: so.Mapped[str] = so.mapped_column(sa.String(30), default="Default")
    System_Font_Size: so.Mapped[str] = so.mapped_column(sa.String(10), default="medium")
    Dashboard_Refresh_Rate: so.Mapped[int] = so.mapped_column(sa.Integer(), default=5)
    Scan_Frequency: so.Mapped[int] = so.mapped_column(sa.Integer(), default=6)
    Dashboard_Layout: so.Mapped[str] = so.mapped_column(sa.String(15), default="default")
    Notifications: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=True)
    Export_Formats: so.Mapped[str] = so.mapped_column(sa.String(50), default="CSV,PDF,XLS")

    # Security
    Session_Timeout: so.Mapped[int] = so.mapped_column(sa.Integer(), default=30)
    Strong_Password_Policy: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=True)
    Failed_Login_Monitoring: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=True)
    Audit_Logging: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=True)
    Security_Check_Frequency: so.Mapped[str] = so.mapped_column(sa.String(10), default="weekly")

    # System
    System_Update_Frequency: so.Mapped[str] = so.mapped_column(sa.String(10), default="monthly")
    Maintenance_Mode: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    Automatic_Backups: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=True)
    Log_Retention_Days: so.Mapped[int] = so.mapped_column(sa.Integer(), default=30)
    Diagnostic_History_Retention_Days: so.Mapped[int] = so.mapped_column(sa.Integer(), default=90)

    # Concurrency + audit trail
    Version: so.Mapped[int] = so.mapped_column(sa.Integer(), default=1)
    Updated_At: so.Mapped[datetime] = so.mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    Updated_By: so.Mapped[Optional[int]] = so.mapped_column(sa.ForeignKey(User.UserID), index=True)

    """
    Serializes this row into the shape the frontend expects
    (camelCase keys matching the SystemSettings TS type).
    """
    def to_dict(self):
        return {
            "systemLanguage": self.System_Language,
            "theme": self.Theme,
            "timeZone": self.Time_Zone,
            "dateTimeFormat": self.Date_Time_Format,
            "systemFont": self.System_Font,
            "systemFontSize": self.System_Font_Size,
            "dashboardRefreshRate": self.Dashboard_Refresh_Rate,
            "scanFrequency": self.Scan_Frequency,
            "dashboardLayout": self.Dashboard_Layout,
            "notifications": self.Notifications,
            "exportFormats": self.Export_Formats.split(",") if self.Export_Formats else [],
            "sessionTimeout": self.Session_Timeout,
            "strongPasswordPolicy": self.Strong_Password_Policy,
            "failedLoginMonitoring": self.Failed_Login_Monitoring,
            "auditLogging": self.Audit_Logging,
            "securityCheckFrequency": self.Security_Check_Frequency,
            "systemUpdateFrequency": self.System_Update_Frequency,
            "maintenanceMode": self.Maintenance_Mode,
            "automaticBackups": self.Automatic_Backups,
            "logRetentionDays": self.Log_Retention_Days,
            "diagnosticHistoryRetentionDays": self.Diagnostic_History_Retention_Days,
            "version": self.Version,
            "updatedAt": self.Updated_At.isoformat(),
        }
