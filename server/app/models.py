from datetime import datetime, timezone
from typing import Optional
from flask_login import UserMixin
from app import login

import sqlalchemy as sa

import sqlalchemy.orm as so

from app import db

from werkzeug.security import generate_password_hash, check_password_hash




class ROLE(UserMixin, db.Model):
    RoleID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Role_Name: so.Mapped[str] = so.mapped_column(sa.String(50))
    Description: so.Mapped[Optional[str]] = so.mapped_column(sa.String(150))
    Created_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))


class USER(UserMixin, db.Model):
    UserID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Firstname: so.Mapped[str] = so.mapped_column(sa.String(120))
    Lastname: so.Mapped[str] = so.mapped_column(sa.String(120))
    Email: so.Mapped[str] = so.mapped_column(sa.String(120), index=True)
    Hashed_Password: so.Mapped[str] = so.mapped_column(sa.String(120))
    Status: so.Mapped[str] = so.mapped_column(sa.String(20), index=True)
    Created_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Updated_At: so.Mapped[Optional[datetime]] = so.mapped_column(default=lambda: datetime.now(timezone.utc))


class ACTIVITY_LOG(UserMixin, db.Model):
    LogID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Action_Type: so.Mapped[str] = so.mapped_column(sa.String(255))
    Performmed_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc)) 


class DEPLOYMENT_HISTORY(UserMixin, db.Model):
    DeployemntID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Notes: so.Mapped[Optional[str]] = so.mapped_column(sa.String(255))
    Deployed_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Updated_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))

class CONFIGURATION_CHANGES(UserMixin, db.Model):
    ConfChangesID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Conf_Type: so.Mapped[str] = so.mapped_column(sa.String(25))
    Parameter_Name: so.Mapped[str] = so.mapped_column(sa.String(50))
    Old_Value: so.Mapped[str] = so.mapped_column(sa.String(100))
    New_Value: so.Mapped[str] = so.mapped_column(sa.String(100))
    Changed_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))

class EXPORT_LOG(UserMixin, db.model):
    ExportID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Report_Type: so.Mapped[str] = so.mapped_column(sa.String(25))
    Start_Date: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc)) 
    End_Date: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Exported_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))

class NETWORK_DISCOVERY(UserMixin, db.model):
    NetDiscoveryID:  so.Mapped[int]  = so.mapped_column(primary_key=True)
    Hostname: so.Mapped[str] = so.mapped_column(sa.String(25))
    IP_Address: so.Mapped[str] = so.mapped_column(sa.String(16))
    Subnet_Mask: so.Mapped[str] = so.mapped_column(sa.String(16))
    OS_Type: so.Mapped[Optional[str]] = so.mapped_column(sa.String(25))
    Device_Type: so.Mapped[Optional[str]] = so.mapped_column(sa.String(25))
    NRPE_Eledgibe: so.Mapped[bool] = so.mapped_column(sa.Boolean())
    Scan_Status: so.Mapped[str] = so.mapped_column(sa.String(20))
    Scanned_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))

class SSH_CREDENTIALS(UserMixin, db.Model):
    SSHID: so.Mapped[int] = so.mapped_column(primary_key=True)
    SSH_Username: so.Mapped[str] = so.mapped_column(sa.String(50))
    SSH_Password: so.Mapped[str] = so.mapped_column(sa.String(256))
    SSH_Port: so.Mapped[int] = so.mapped_column(sa.Integer())
    Created_Art: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))

class NRPE_DEPLOYEMENT(UserMixin, db.Model):
    NRPEID: so.Mapped[int] = so.mapped_column(primary_key=True)
    NRPE_Port: so.Mapped[int] = so.mapped_column(sa.Integer())
    Plugin_Installed: so.Mapped[str] = so.mapped_column(sa.String(150))
    Agent_Status: so.Mapped[str] = so.mapped_column(sa.String(150))