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


    Role: so.Mapped['Role'] = so.relationship(back_populates='RolePermissions')
    Permissions: so.Mapped['Permission'] = so.relationship(back_populates='RolePermission')
   
class UserStatus(Enum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"
    SUSPENDED = "Suspended"
    
class User(UserMixin, db.Model):
    # Table Name
    __tablename__ = "USER"

    # Table Fields
    UserID: so.Mapped[int] = so.mapped_column(primary_key=True)
    First_Name: so.Mapped[str] = so.mapped_column(sa.String(120))
    Last_Name: so.Mapped[str] = so.mapped_column(sa.String(120))
    Email: so.Mapped[str] = so.mapped_column(sa.String(120), unique=True, index=True)
    Hashed_Password: so.Mapped[str] = so.mapped_column(sa.String(256))
    Status: so.Mapped[UserStatus] = so.mapped_column(sa.Enum(UserStatus))
    Must_Change_Password: so.Mapped[bool] = so.mapped_column(
        sa.Boolean(), default=False, server_default=sa.false()
    )
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
    Deployment_Logs: so.WriteOnlyMapped['NCPADeploymentStatus'] = so.relationship(back_populates='Logs')
    Config_Logs: so.WriteOnlyMapped['ConfigurationChanges'] = so.relationship(back_populates='Logs')
    Export_Logs: so.WriteOnlyMapped['ExportLog'] = so.relationship(back_populates='Logs')
    NetDiscover_Logs: so.WriteOnlyMapped['NetworkDiscoveryStatus'] = so.relationship(back_populates='Logs')
    Plugin_History_Logs: so.WriteOnlyMapped['PluginHistory'] = so.relationship(back_populates='Logs')
    Plugin_Override_Logs: so.WriteOnlyMapped['PluginCommandOverride'] = so.relationship(back_populates='Logs')
    Plugin_Scan_Logs: so.WriteOnlyMapped['PluginScanStatus'] = so.relationship(back_populates='Logs')
    
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
    XLS="xls"
    
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

class DiscoveryStatus(Enum):
    RUNNING = "Running"
    SUCCESS = "Success"
    FAILED = "Failed"
    INTERRUPTED = "Interrupted"

class NetworkDiscoveryStatus(db.Model):
    # Table name
    __tablename__ = "NETWORK_DISCOVERY_STATUS"

    # Table Fields
    DiscoveryStatusID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Status: so.Mapped[DiscoveryStatus] = so.mapped_column(sa.Enum(DiscoveryStatus))
    Progress: so.Mapped[int] = so.mapped_column()
    Message: so.Mapped[str] = so.mapped_column(sa.String(100))
    Start_At: so.Mapped[datetime] = so.mapped_column(default= lambda: datetime.now(timezone.utc))
    Completed_At: so.Mapped[Optional[datetime]] = so.mapped_column()
    Error: so.Mapped[Optional[str]] = so.mapped_column()

    # Foreign Key Fields
    LogID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(ActivityLog.LogID), index=True)

    Logs: so.Mapped[ActivityLog] = so.relationship(back_populates='NetDiscover_Logs')
    Devices: so.Mapped['NetworkDiscovery'] = so.relationship(back_populates='DiscoveryRecord')
    Skipped_Services: so.WriteOnlyMapped['SkippedService'] = so.relationship(back_populates='DiscoveryRecord')

"""
ServiceProtocol Enum so that Protocol is consistent
To call use "SkippedService.Protocol = ServiceProtocol.UDP"
The models class need to be imported to use the Enums
"""

class ServiceProtocol(Enum):
    TCP = "TCP"
    UDP = "UDP"

"""
A discovered open port that Network Discovery did NOT turn into a Nagios
service during one discovery run (e.g. a UDP port with no plugin that can
check it). Kept so administrators can see in the discovery log what was left
unmonitored and why. Hostname and IP_Address are snapshots taken at the time
of the run, so the record stays readable if the device changes later.
"""

class SkippedService(db.Model):
    # Table name
    __tablename__ = "SKIPPED_SERVICE"

    # Table Fields
    SkippedServiceID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Hostname: so.Mapped[str] = so.mapped_column(sa.String(255))
    IP_Address: so.Mapped[Optional[str]] = so.mapped_column(sa.String(45))
    Port_Number: so.Mapped[int] = so.mapped_column()
    Protocol: so.Mapped[ServiceProtocol] = so.mapped_column(sa.Enum(ServiceProtocol))
    Service_Name: so.Mapped[str] = so.mapped_column(sa.String(100))
    Reason: so.Mapped[str] = so.mapped_column(sa.String(255))
    Skipped_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))

    # Foreign Key Fields
    DiscoveryStatusID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(NetworkDiscoveryStatus.DiscoveryStatusID), index=True)

    DiscoveryRecord: so.Mapped[NetworkDiscoveryStatus] = so.relationship(back_populates='Skipped_Services')

"""
Device identity enums (see "docs/plans/DHCP_Device_Identity_Plan.md").

AddressingMode   - how the device gets its IP; set by a user or inferred.
IdentityConfidence - how sure PinPoint is that a record is one physical device.
DeviceState      - lifecycle of a device record and of its Nagios config entry.
IdentifierKind   - the kind of evidence stored in DeviceIdentifier.
AddressSource    - what produced a DeviceAddressHistory row.
ReviewKind       - why a DeviceReviewItem was raised.
"""

class AddressingMode(Enum):
    DHCP = "DHCP"
    STATIC = "Static"
    UNKNOWN = "Unknown"

class IdentityConfidence(Enum):
    VERIFIED = "Verified"
    LIKELY = "Likely"
    UNVERIFIED = "Unverified"

class DeviceState(Enum):
    ACTIVE = "Active"
    MISSING = "Missing"
    ADDRESS_UNKNOWN = "Address Unknown"
    RETIRED = "Retired"
    MERGED = "Merged"

class IdentifierKind(Enum):
    NCPA_CERT = "NCPA Certificate"
    MACHINE_ID = "Machine ID"
    SSH_HOST_KEY = "SSH Host Key"
    MAC = "MAC"
    DNS_NAME = "DNS Name"

class AddressSource(Enum):
    SCAN = "Scan"
    NCPA_RELOCATE = "NCPA Relocate"
    MANUAL = "Manual"

class ReviewKind(Enum):
    CONFLICT = "Conflict"
    IDENTITY_CHANGED = "Identity Changed"
    IP_REUSE = "IP Reused"
    DUPLICATE_IDENTITY = "Duplicate Identity"
    STATIC_MOVED = "Static Device Moved"
    SERVICE_CHANGED = "Service Changed"

"""
Port lifecycle enums for Open_TCP_Services / Open_UDP_Services.
"""

class PortState(Enum):
    SUGGESTED = "Suggested"
    MONITORED = "Monitored"
    MISSING = "Missing"
    ARCHIVED = "Archived"
    IGNORED = "Ignored"

class PortSource(Enum):
    SCAN = "Scan"
    NCPA = "NCPA"
    USER = "User"

class ServiceIdentification(Enum):
    """
    How a port's Service_Name was decided, strongest first. USER is pinned by
    an operator and never changed by a scan; PORT_RULE comes from an "always
    treat port X as Y" setting; FINGERPRINT means nmap identified the service
    by probing it; PORT_HINT is only a guess from the port number.
    """
    USER = "User"
    PORT_RULE = "Port Rule"
    FINGERPRINT = "Fingerprint"
    PORT_HINT = "Port Hint"

"""
ScanStatus Enum so that Scan_Status is consistent
To call use "NetworkDiscovery.Scan_Status = ScanStatus.PENDING"
The models class need to be imported to use the Enums
"""

class NetworkDiscovery(db.Model):
    # Table Name
    __tablename__ = "NETWORK_DISCOVERY"
    __table_args__ = (
        sa.UniqueConstraint('Nagios_Host_Name', name='uq_network_discovery_nagios_host_name'),
    )
    
    # Table Fields
    NetDiscoveryID:  so.Mapped[int]  = so.mapped_column(primary_key=True)
    Hostname: so.Mapped[Optional[str]] = so.mapped_column(sa.String(100))
    IP_Address: so.Mapped[str] = so.mapped_column(sa.String(16), index=True)
    Network: so.Mapped[str] = so.mapped_column(sa.String(16), index=True)
    MAC_Address: so.Mapped[Optional[str]] = so.mapped_column(sa.String(17), index=True)
    OS_Type: so.Mapped[Optional[str]] = so.mapped_column(sa.String(25))
    Device_Type: so.Mapped[Optional[str]] = so.mapped_column(sa.String(25))
    NCPA_Eligible: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    Scanned_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Include_Device_In_Scanning: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=True)
    # Per-host plugin variable overrides keyed by plugin name, e.g.
    # {"snmp": {"community": "private", "port": 1161}}. Layered on top of
    # the defaults in network_discovery/plugin_registry.py when this host's
    # Nagios services are generated.
    Plugin_Variables: so.Mapped[Optional[dict]] = so.mapped_column(sa.JSON())

    # Device identity (DHCP plan section 5). IP_Address always holds the
    # CURRENT address; Nagios_Host_Name is fixed at creation and never derived
    # from it. Hostname is only "the name DNS reported" and Nagios ignores it.
    Nagios_Host_Name: so.Mapped[Optional[str]] = so.mapped_column(sa.String(100))
    Display_Name: so.Mapped[Optional[str]] = so.mapped_column(sa.String(100))
    Addressing: so.Mapped[AddressingMode] = so.mapped_column(sa.Enum(AddressingMode), default=AddressingMode.UNKNOWN)
    Identity_Confidence: so.Mapped[IdentityConfidence] = so.mapped_column(sa.Enum(IdentityConfidence), default=IdentityConfidence.UNVERIFIED)
    Device_State: so.Mapped[DeviceState] = so.mapped_column(sa.Enum(DeviceState), default=DeviceState.ACTIVE, index=True)
    First_Seen_At: so.Mapped[Optional[datetime]] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Last_Seen_At: so.Mapped[Optional[datetime]] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Missed_Scans: so.Mapped[int] = so.mapped_column(default=0)

    # Foreign Key Fields
    DiscoveryStatusID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(NetworkDiscoveryStatus.DiscoveryStatusID), index=True)
    Merged_Into_ID: so.Mapped[Optional[int]] = so.mapped_column(sa.ForeignKey("NETWORK_DISCOVERY.NetDiscoveryID"))

    """
    Gets on instnce of ActivityLog
    back_populate sepcifies that you can access this table from either side, (i.e DeploymentHistory <--> ActivityLog and vise versa)
    """
    DiscoveryRecord: so.Mapped[NetworkDiscoveryStatus] = so.relationship(back_populates='Devices')

    """
    WriteOnlyMapped enables for Many of the DeploymentHistory
    WriteOnlyMapped is to explicity load only that is queried
    back_populate sepcifies that you can access this table from either side, (i.e DeploymentHistory <--> ActivityLog and vise versa)
    """
    SSH_Creds: so.WriteOnlyMapped['SSHCredentials'] = so.relationship(back_populates='Device')
    NCPA_Deployment: so.WriteOnlyMapped['NCPADeployment'] = so.relationship(back_populates='Device')
    # Phase 10 (Plugin Manager): plugin configurations targeting this device.
    Plugin_Configurations: so.WriteOnlyMapped['PluginConfiguration'] = so.relationship(back_populates='Target_Device')
    
class DeviceIdentifier(db.Model):
    """
    One piece of evidence that identifies a device across IP changes (NCPA
    certificate, machine-id, SSH host key, MAC, DNS name). Strong identifiers
    are unique on (Kind, Value) so one key can never belong to two devices.
    A multi-NIC device simply has several MAC rows.
    """
    __tablename__ = "DEVICE_IDENTIFIER"
    __table_args__ = (
        # Unique only for strong identifiers: two devices may share a weak one
        # (e.g. the same reverse-DNS name).
        sa.Index('uq_device_identifier_strong', 'Kind', 'Value', unique=True,
                 sqlite_where=sa.text('"Is_Strong" = 1'),
                 postgresql_where=sa.text('"Is_Strong" = true')),
    )

    IdentifierID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Kind: so.Mapped[IdentifierKind] = so.mapped_column(sa.Enum(IdentifierKind))
    Value: so.Mapped[str] = so.mapped_column(sa.String(255))
    Is_Strong: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=True)
    First_Seen_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Last_Seen_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))

    NetDiscoveryID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(NetworkDiscovery.NetDiscoveryID), index=True)

class DeviceAddressHistory(db.Model):
    """
    Every IP a device has been seen at. The open row (Closed_At IS NULL) is
    the current address; a device has at most one open row.
    """
    __tablename__ = "DEVICE_ADDRESS_HISTORY"

    AddressID: so.Mapped[int] = so.mapped_column(primary_key=True)
    IP_Address: so.Mapped[str] = so.mapped_column(sa.String(45))
    Network: so.Mapped[Optional[str]] = so.mapped_column(sa.String(18))
    MAC_Address: so.Mapped[Optional[str]] = so.mapped_column(sa.String(17))
    Source: so.Mapped[AddressSource] = so.mapped_column(sa.Enum(AddressSource), default=AddressSource.SCAN)
    First_Seen_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Last_Seen_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Closed_At: so.Mapped[Optional[datetime]] = so.mapped_column()

    NetDiscoveryID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(NetworkDiscovery.NetDiscoveryID), index=True)

class DeviceReviewItem(db.Model):
    """
    A decision the reconciler refused to make on its own (conflicting
    identifiers, identity change, IP reuse, ...). Shown on the "Needs review"
    list until a user resolves it. Candidate_Device_IDs lists the devices
    involved so the UI can offer Merge / Retire.
    """
    __tablename__ = "DEVICE_REVIEW_ITEM"

    ReviewID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Kind: so.Mapped[ReviewKind] = so.mapped_column(sa.Enum(ReviewKind))
    IP_Address: so.Mapped[Optional[str]] = so.mapped_column(sa.String(45))
    MAC_Address: so.Mapped[Optional[str]] = so.mapped_column(sa.String(17))
    Message: so.Mapped[str] = so.mapped_column(sa.String(255))
    Candidate_Device_IDs: so.Mapped[Optional[list]] = so.mapped_column(sa.JSON())
    Created_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Resolved_At: so.Mapped[Optional[datetime]] = so.mapped_column()

    DiscoveryStatusID: so.Mapped[Optional[int]] = so.mapped_column(sa.ForeignKey(NetworkDiscoveryStatus.DiscoveryStatusID), index=True)

class Open_TCP_Services(db.Model):
    __tablename__ = "OPEN_TCP_Services"
    __table_args__ = (
        sa.UniqueConstraint('NetDiscoveryID', 'Port_Number', name='uq_open_tcp_device_port'),
    )

    OpenPortID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Port_Number: so.Mapped[int] = so.mapped_column()
    Service_Name: so.Mapped[str] = so.mapped_column(sa.String(255))

    # Port lifecycle (DHCP plan section 9). Plugin_Name is frozen when the
    # port becomes MONITORED so a later nmap guess cannot rename the service.
    Port_State: so.Mapped[PortState] = so.mapped_column(sa.Enum(PortState), default=PortState.MONITORED)
    Source: so.Mapped[PortSource] = so.mapped_column(sa.Enum(PortSource), default=PortSource.SCAN)
    Plugin_Name: so.Mapped[Optional[str]] = so.mapped_column(sa.String(100))
    # Latest nmap guess, kept apart from Service_Name once the port is
    # monitored so a changed guess becomes a suggestion, not a rename.
    Observed_Service_Name: so.Mapped[Optional[str]] = so.mapped_column(sa.String(255))
    # How Service_Name was decided; NULL for ports recorded before this existed.
    Identified_By: so.Mapped[Optional[ServiceIdentification]] = so.mapped_column(sa.Enum(ServiceIdentification))
    # The service the Port -> Service setting expects on this port when nmap
    # fingerprinted something else ("Not used as intended"). The port keeps the
    # service nmap saw; it is not monitored until an admin acknowledges it
    # (Mismatch_Acknowledged_At). A change in what nmap sees clears the
    # acknowledgement.
    Expected_Service_Name: so.Mapped[Optional[str]] = so.mapped_column(sa.String(255))
    Mismatch_Acknowledged_At: so.Mapped[Optional[datetime]] = so.mapped_column()
    # An admin chose to leave this port Suggested, or it was Suggested at an upgrade and an
    # enabled plugin would have started monitoring it. While True no plugin promotes it;
    # promoting it by hand (state MONITORED, or acknowledging a mismatch) clears it.
    Promotion_Held: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False, server_default=sa.false())
    First_Seen_At: so.Mapped[Optional[datetime]] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Last_Seen_At: so.Mapped[Optional[datetime]] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Closed_At: so.Mapped[Optional[datetime]] = so.mapped_column()
    Missed_Scans: so.Mapped[int] = so.mapped_column(default=0)

    NetDiscoveryID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(NetworkDiscovery.NetDiscoveryID), index=True)

class Open_UDP_Services(db.Model):
    __tablename__ = "OPEN_UDP_Services"
    __table_args__ = (
        sa.UniqueConstraint('NetDiscoveryID', 'Port_Number', name='uq_open_udp_device_port'),
    )

    OpenPortID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Port_Number: so.Mapped[int] = so.mapped_column()
    Service_Name: so.Mapped[str] = so.mapped_column(sa.String(255))

    # Port lifecycle (DHCP plan section 9). Plugin_Name is frozen when the
    # port becomes MONITORED so a later nmap guess cannot rename the service.
    Port_State: so.Mapped[PortState] = so.mapped_column(sa.Enum(PortState), default=PortState.MONITORED)
    Source: so.Mapped[PortSource] = so.mapped_column(sa.Enum(PortSource), default=PortSource.SCAN)
    Plugin_Name: so.Mapped[Optional[str]] = so.mapped_column(sa.String(100))
    # Latest nmap guess, kept apart from Service_Name once the port is
    # monitored so a changed guess becomes a suggestion, not a rename.
    Observed_Service_Name: so.Mapped[Optional[str]] = so.mapped_column(sa.String(255))
    # How Service_Name was decided; NULL for ports recorded before this existed.
    Identified_By: so.Mapped[Optional[ServiceIdentification]] = so.mapped_column(sa.Enum(ServiceIdentification))
    # The service the Port -> Service setting expects on this port when nmap
    # fingerprinted something else ("Not used as intended"). The port keeps the
    # service nmap saw; it is not monitored until an admin acknowledges it
    # (Mismatch_Acknowledged_At). A change in what nmap sees clears the
    # acknowledgement.
    Expected_Service_Name: so.Mapped[Optional[str]] = so.mapped_column(sa.String(255))
    Mismatch_Acknowledged_At: so.Mapped[Optional[datetime]] = so.mapped_column()
    # An admin chose to leave this port Suggested, or it was Suggested at an upgrade and an
    # enabled plugin would have started monitoring it. While True no plugin promotes it;
    # promoting it by hand (state MONITORED, or acknowledging a mismatch) clears it.
    Promotion_Held: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False, server_default=sa.false())
    First_Seen_At: so.Mapped[Optional[datetime]] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Last_Seen_At: so.Mapped[Optional[datetime]] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Closed_At: so.Mapped[Optional[datetime]] = so.mapped_column()
    Missed_Scans: so.Mapped[int] = so.mapped_column(default=0)

    NetDiscoveryID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(NetworkDiscovery.NetDiscoveryID), index=True)

class SSHCredentials(db.Model):
    # Table Name
    __tablename__ = "SSH_CREDENTIALS"
    
    # Table Fields
    SSHID: so.Mapped[int] = so.mapped_column(primary_key=True)
    SSH_Port: so.Mapped[int] = so.mapped_column(sa.Integer())
    Key_Installed: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    Key_Fingerprint: so.Mapped[Optional[str]] = so.mapped_column()
    Created_At: so.Mapped[Optional[datetime]] = so.mapped_column(default=lambda: datetime.now(timezone.utc))

    # Foreign Key Field
    NetworkDiscoveryID:  so.Mapped[int] = so.mapped_column(sa.ForeignKey(NetworkDiscovery.NetDiscoveryID), index=True)

    """
    Gets on instnce of NetworkDiscovery
    back_populate sepcifies that you can access this table from either side, (i.e DeploymentHistory <--> ActivityLog and vise versa)
    """
    Device: so.Mapped[NetworkDiscovery] = so.relationship(back_populates='SSH_Creds')

class DeploymentStatus(Enum):
    RUNNING = "Running"
    SUCCESS = "Success"
    PARTIAL_FAILURE = "Partial Failure"
    FAILED = "Failed"
    INTERRUPTED = "Interrupted"

class NCPADeploymentStatus(db.Model):
    # Table Name
    __tablename__ = "NCPA_DEPLOYMENT_STATUS"

    # Table Fields
    NCPADeployStatusID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Status: so.Mapped[DeploymentStatus] = so.mapped_column()
    Progress: so.Mapped[int] = so.mapped_column()
    Message: so.Mapped[str] = so.mapped_column(sa.String(100))
    Start_At: so.Mapped[datetime] = so.mapped_column(default= lambda: datetime.now(timezone.utc))
    Completed_At: so.Mapped[Optional[datetime]] = so.mapped_column()
    Error: so.Mapped[Optional[str]] = so.mapped_column()

    # Set when an administrator marks a finished run as reviewed.
    Reviewed_At: so.Mapped[Optional[datetime]] = so.mapped_column()

    # Foreign Key
    LogID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(ActivityLog.LogID))
    Reviewed_By: so.Mapped[Optional[int]] = so.mapped_column(sa.ForeignKey(User.UserID))

    # Relationships
    Logs: so.Mapped[ActivityLog] = so.relationship(back_populates='Deployment_Logs')
    Device_Deployment: so.Mapped['NCPADeployment'] = so.relationship(back_populates='Deployment_Status')
    Reviewer: so.Mapped[Optional[User]] = so.relationship(foreign_keys=[Reviewed_By])
    Results: so.WriteOnlyMapped['NCPADeploymentResult'] = so.relationship(back_populates='Run')


class DeploymentOutcome(Enum):
    """What happened to one device in one NCPA deployment run."""
    PENDING = "Pending"            # accepted for the run, not started yet
    RUNNING = "Running"
    SUCCESS = "Success"
    FAILED = "Failed"
    UNREACHABLE = "Down"           # the device did not answer on SSH
    INCOMPATIBLE = "Incompatible"  # unsupported operating system
    REJECTED = "Rejected"          # failed the pre-flight checks in /start
    SKIPPED = "Skipped"            # the run was stopped before this device


class NCPADeploymentResult(db.Model):
    """
    One row per device per NCPA deployment run. NCPADeployment holds only a
    device's latest state; these rows keep what happened in every run.
    Hostname and IP are copied at run time so history stays readable after
    a device is renamed or moves. Error holds a user-facing reason only,
    never credentials or command output.
    """
    # Table Name
    __tablename__ = "NCPA_DEPLOYMENT_RESULT"

    # Table Fields
    NCPADeployResultID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Hostname: so.Mapped[Optional[str]] = so.mapped_column(sa.String(255))
    IP_Address: so.Mapped[Optional[str]] = so.mapped_column(sa.String(45))
    Outcome: so.Mapped[DeploymentOutcome] = so.mapped_column(sa.Enum(DeploymentOutcome))
    Error: so.Mapped[Optional[str]] = so.mapped_column(sa.String(255))
    Started_At: so.Mapped[Optional[datetime]] = so.mapped_column()
    Completed_At: so.Mapped[Optional[datetime]] = so.mapped_column()

    # Foreign Key Fields
    NCPADeploymentStatusID: so.Mapped[int] = so.mapped_column(
        sa.ForeignKey(NCPADeploymentStatus.NCPADeployStatusID), index=True
    )
    NetworkDiscoveryID: so.Mapped[int] = so.mapped_column(
        sa.ForeignKey(NetworkDiscovery.NetDiscoveryID), index=True
    )

    # Relationships
    Run: so.Mapped[NCPADeploymentStatus] = so.relationship(back_populates='Results')
"""
AgentStatus Enum so that Agent_Status is consistent
To call use "NRPEDeployment.Agent_Status = AgentStatus.DISCOVERED"
The models class need to be imported to use the Enums
"""
class AgentStatus(Enum):
    PENDING_NCPA = "Pending NCPA"
    DEPLOYED = "Deployed NCPA"
    FAILED = "Deployment Failed"
    EXCLUDED = "Excluded"
    INCOMPATIBLE = "Incompatible"

class DeploymentMethod(Enum):
    AUTOMATIC = "Automatic"
    MANUAL = "Manual"
    
class NCPADeployment(db.Model):
    # Table Name
    __tablename__ = "NCPA_DEPLOYMENT"
    
    # Table Fields
    NCPADeployID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Deployement_Method: so.Mapped[Optional[DeploymentMethod]] = so.mapped_column(sa.Enum(DeploymentMethod))
    Token: so.Mapped[Optional[str]] = so.mapped_column(sa.String(32))
    Agent_Status: so.Mapped[Optional[AgentStatus]] = so.mapped_column(sa.Enum(AgentStatus))
    Error: so.Mapped[Optional[str]] = so.mapped_column()

    # Foreign Key Field
    NCPADeploymentStatusID: so.Mapped[Optional[int]] = so.mapped_column(sa.ForeignKey(NCPADeploymentStatus.NCPADeployStatusID))
    NetworkDiscoveryID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(NetworkDiscovery.NetDiscoveryID), index=True)

    """
    Gets on instnce of NetworkDiscovery
    back_populate sepcifies that you can access this table from either side, (i.e DeploymentHistory <--> ActivityLog and vise versa)
    """
    Device: so.Mapped[NetworkDiscovery] = so.relationship(back_populates='NCPA_Deployment')
    
    """
    Gets on instnce of NCPADeploymentStatus
    back_populate sepcifies that you can access this table from either side, (i.e DeploymentHistory <--> ActivityLog and vise versa)
    """
    Deployment_Status: so.Mapped[NCPADeploymentStatus] = so.relationship(back_populates='Device_Deployment')

    """
    WriteOnlyMapped to the partition rows collected during NCPA installation.
    One deployment can have many partitions.
    """
    Partitions: so.WriteOnlyMapped['NCPADevicePartition'] = so.relationship(back_populates='Deployment')


class NCPADevicePartition(db.Model):
    """
    Stores the logical partitions (block devices) discovered on a remote
    machine during NCPA installation.  One row per partition per deployment.

    The Name field holds the partition identifier exactly as reported by
    lsblk (e.g. 'sda1', 'nvme0n1p2', 'vda').
    """
    # Table Name
    __tablename__ = "NCPA_DEVICE_PARTITION"

    # Table Fields
    PartitionID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Name: so.Mapped[str] = so.mapped_column(sa.String(64))

    # Foreign Key Field — links to the specific NCPA deployment
    NCPADeployID: so.Mapped[int] = so.mapped_column(
        sa.ForeignKey('NCPA_DEPLOYMENT.NCPADeployID'), index=True
    )

    """
    Back-reference to the NCPADeployment this partition belongs to.
    back_populates specifies that you can access this table from either side.
    """
    Deployment: so.Mapped['NCPADeployment'] = so.relationship(back_populates='Partitions')

"""
SystemSettings is a singleton table — there will only ever be one row (Id=1).
This holds system-wide configuration that applies regardless of which
user is logged in (security and system tabs on the Settings page).
Personal display preferences (theme, language, font, dashboard layout,
time zone, date format) live in UserPreferences instead, one row per user.
"""
class SystemSettings(db.Model):
    # Table Name
    __tablename__ = "SYSTEM_SETTINGS"

    # Table Fields
    Id: so.Mapped[int] = so.mapped_column(primary_key=True)

    # General (system-wide only)
    Scan_Frequency: so.Mapped[int] = so.mapped_column(sa.Integer(), default=6)
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
            "scanFrequency": self.Scan_Frequency,
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


class DiscoverySettings(db.Model):
    # Table Name
    __tablename__ = "DISCOVERY_SETTINGS"

    # Table Fields
    Id: so.Mapped[int] = so.mapped_column(primary_key=True)
    Networks: so.Mapped[Optional[list]] = so.mapped_column(sa.JSON())
    TCP_Ports: so.Mapped[Optional[list]] = so.mapped_column(sa.JSON())
    UDP_Ports: so.Mapped[Optional[list]] = so.mapped_column(sa.JSON())
    # {port: service name}: the service an admin expects on each port.
    TCP_Port_Services: so.Mapped[Optional[dict]] = so.mapped_column(sa.JSON())
    UDP_Port_Services: so.Mapped[Optional[dict]] = so.mapped_column(sa.JSON())

    # Concurrency + audit trail
    Version: so.Mapped[int] = so.mapped_column(sa.Integer(), default=1)
    Updated_At: so.Mapped[datetime] = so.mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    Updated_By: so.Mapped[Optional[int]] = so.mapped_column(sa.ForeignKey(User.UserID), index=True)


class PluginSettings(db.Model):
    # Table Name
    __tablename__ = "PLUGIN_SETTINGS"

    # Table Fields
    Id: so.Mapped[int] = so.mapped_column(primary_key=True)
    # The plugin definition the values belong to ("snmp"), see plugin_registry.py.
    Plugin_Name: so.Mapped[str] = so.mapped_column(sa.String(50), unique=True, index=True)
    # {variable: value} saved from Settings -> Plugins, e.g. {"oids": [{"metric": ..., "oid": ...}]}.
    # A variable that is absent uses its config.py default.
    Variables: so.Mapped[dict] = so.mapped_column(sa.JSON())

    # Concurrency + audit trail
    Version: so.Mapped[int] = so.mapped_column(sa.Integer(), default=1)
    Updated_At: so.Mapped[datetime] = so.mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    Updated_By: so.Mapped[Optional[int]] = so.mapped_column(sa.ForeignKey(User.UserID), index=True)


class NetworkProfile(db.Model):
    __tablename__ = "NETWORK_PROFILE"

    Id: so.Mapped[int] = so.mapped_column(primary_key=True)
    Name: so.Mapped[str] = so.mapped_column(sa.String(100))
    Reference: so.Mapped[Optional[str]] = so.mapped_column(sa.String(50))
    Details: so.Mapped[Optional[dict]] = so.mapped_column(sa.JSON())

    Updated_At: so.Mapped[datetime] = so.mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    Updated_By: so.Mapped[Optional[int]] = so.mapped_column(sa.ForeignKey(User.UserID), index=True)

"""
UserPreferences holds per-user personal display settings — one row per
user, unlike SystemSettings which is a shared singleton. These are things
a user would reasonably expect to be "theirs" on this account, not shared
system-wide config.
"""
class UserPreferences(db.Model):
    __tablename__ = "USER_PREFERENCES"

    Id: so.Mapped[int] = so.mapped_column(primary_key=True)
    UserID: so.Mapped[int] = so.mapped_column(
        sa.ForeignKey(User.UserID), unique=True, index=True
    )

    Theme: so.Mapped[str] = so.mapped_column(sa.String(10), default="dark")
    Time_Zone: so.Mapped[str] = so.mapped_column(sa.String(20), default="UTC+08:00")
    Date_Time_Format: so.Mapped[str] = so.mapped_column(sa.String(20), default="DD/MM/YYYY")
    System_Font: so.Mapped[str] = so.mapped_column(sa.String(30), default="Default")
    System_Font_Size: so.Mapped[str] = so.mapped_column(sa.String(10), default="medium")
    Dashboard_Layout: so.Mapped[str] = so.mapped_column(sa.String(15), default="default")
    Dashboard_Refresh_Rate: so.Mapped[int] = so.mapped_column(sa.Integer(), default=5)

    Updated_At: so.Mapped[datetime] = so.mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    User: so.Mapped["User"] = so.relationship()

    """
    Serializes this row into the shape the frontend expects
    (camelCase keys matching the SystemSettings TS type, since the
    frontend currently merges these fields into that same object).
    """
    def to_dict(self):
        return {
            "theme": self.Theme,
            "timeZone": self.Time_Zone,
            "dateTimeFormat": self.Date_Time_Format,
            "systemFont": self.System_Font,
            "systemFontSize": self.System_Font_Size,
            "dashboardLayout": self.Dashboard_Layout,
            "dashboardRefreshRate": self.Dashboard_Refresh_Rate,
        }


class NotificationCursor(db.Model):
    """
    Tracks the read/unread boundary for Nagios notifications per user.

    One row per user.  last_seen_ts is the UNIX timestamp of the most-recent
    notification the user has acknowledged (i.e. opened the notification panel).

    Any Nagios notification whose timestamp > last_seen_ts is considered "unread"
    for that user.  A value of 0 (default) means the user has never read anything,
    so everything is unread.
    """
    __tablename__ = "NOTIFICATION_CURSOR"

    UserID: so.Mapped[int] = so.mapped_column(
        sa.ForeignKey(User.UserID, ondelete="CASCADE"),
        primary_key=True,
    )
    last_seen_ts: so.Mapped[int] = so.mapped_column(
        sa.BigInteger(),
        default=0,
        nullable=False,
    )
    Updated_At: so.Mapped[datetime] = so.mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    User: so.Mapped['User'] = so.relationship()

class AlertAcknowledgement(db.Model):
    """
    Tracks acknowledgements made by users for active alerts (host or service
    problems). Acknowledgements are managed entirely within this system —
    nothing is written back to Nagios.

    An acknowledgement identifies an alert by (Hostname, Service_Name) where
    Service_Name is NULL for host-level alerts.

    One active acknowledgement per alert is enforced by the unique constraint.
    When an alert resolves (returns to OK/UP), its acknowledgement record is
    cleared by the backend. History is retained separately in the history DB.

    See Display_Requirements.md §4 for full business rules.
    """
    __tablename__ = "ALERT_ACKNOWLEDGEMENT"

    __table_args__ = (
        # Only one active acknowledgement per (host, service) pair.
        # Service_Name is nullable (NULL = host-level alert).
        sa.UniqueConstraint(
            'Hostname', 'Service_Name',
            name='uq_alert_acknowledgement_host_service'
        ),
    )

    # Table Fields
    AckID: so.Mapped[int] = so.mapped_column(primary_key=True)

    # The host the acknowledged alert belongs to.
    Hostname: so.Mapped[str] = so.mapped_column(sa.String(100), index=True)

    # NULL for host-level alerts; populated for service-level alerts.
    Service_Name: so.Mapped[Optional[str]] = so.mapped_column(
        sa.String(150), nullable=True, index=True
    )

    # Required comment from the acknowledging user (spec §4.4 step 1).
    Comment: so.Mapped[str] = so.mapped_column(sa.String(500))

    # When this acknowledgement was created.
    Acknowledged_At: so.Mapped[datetime] = so.mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )

    # Foreign key to the user who acknowledged the alert.
    AcknowledgedBy: so.Mapped[int] = so.mapped_column(
        sa.ForeignKey(User.UserID), index=True
    )

    # Relationship to the acknowledging user.
    User: so.Mapped['User'] = so.relationship()

class AckAction(Enum):
    ACKNOWLEDGED   = "Acknowledged"
    UNACKNOWLEDGED = "Unacknowledged"
    AUTO_RESOLVED  = "Auto-Resolved"   # cleared by the system when alert returns to OK/UP

class AckHistory(db.Model):
    """
    Append-only log of every acknowledgement lifecycle event.

    One row is written each time an alert is:
      - Acknowledged   (AckAction.ACKNOWLEDGED)
      - Unacknowledged manually by a user (AckAction.UNACKNOWLEDGED)
      - Cleared automatically when the alert resolves (AckAction.AUTO_RESOLVED)

    This table is the source of truth for the History page's
    "Acknowledged" badge and detail panel (§3.1, §3.2 of
    Alerts_Notifications_History_Requirements.md).

    Intentionally kept in system_models (main DB) alongside
    AlertAcknowledgement — both are system-generated, not Nagios-sourced.

    Users cannot be deleted in this system (only deactivated), so ActorUserID
    uses a proper FK constraint. Service_Name is NULL for host-level alerts.
    """
    __tablename__ = "ACK_HISTORY"

    # Table Fields
    AckHistoryID: so.Mapped[int] = so.mapped_column(primary_key=True)

    # The alert this action relates to.
    Hostname: so.Mapped[str] = so.mapped_column(sa.String(100), index=True)
    Service_Name: so.Mapped[Optional[str]] = so.mapped_column(
        sa.String(150), nullable=True, index=True
    )

    # The action taken.
    Action: so.Mapped[AckAction] = so.mapped_column(sa.Enum(AckAction))

    # When the action was taken.
    Actioned_At: so.Mapped[datetime] = so.mapped_column(
        index=True, default=lambda: datetime.now(timezone.utc)
    )

    # Who took the action. NULL for AUTO_RESOLVED (system action).
    # FK is safe because users are never deleted, only deactivated.
    ActorUserID: so.Mapped[Optional[int]] = so.mapped_column(
        sa.ForeignKey(User.UserID), nullable=True, index=True
    )

    # Comment — only populated for ACKNOWLEDGED actions.
    Comment: so.Mapped[Optional[str]] = so.mapped_column(
        sa.String(500), nullable=True
    )

    # Relationship to the acting user.
    Actor: so.Mapped[Optional['User']] = so.relationship()
