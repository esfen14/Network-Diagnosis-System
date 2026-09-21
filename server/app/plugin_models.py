"""
plugin_models.py — Plugin Manager database models.

Architecture basis: PinPoint Plugin Manager — Revised Architecture v0.3
Implements the data model described in:
    PinPoint Plugin Manager — Implementation Plan v0.1, Section 4.

IMPORTANT (do not violate — see Implementation Plan Section 25):
    - Nagios Core remains the monitoring engine.
    - These models describe server-side Nagios plugins managed on the
      PinPoint/Nagios server. They do NOT represent software installed
      on monitored devices.
    - "Installed" is not the same as "Active". A plugin's lifecycle
      state (Status) is tracked separately from whether it is actually
      being used for monitoring (that requires a PluginConfiguration
      row wired into Nagios — see Phase 10).
    - Command overrides must preserve the original command definition
      even if the plugin's default command later changes.

Bind: these tables live on the DEFAULT bind (system.db), not the
"history" bind. The "history" bind (history_models.py) is reserved for
mirrored Nagios host/service status telemetry, a different concept
from Plugin Manager's own administrative state and audit trail. Since
PluginHistory and PluginCommandOverride foreign-key into ActivityLog
(system.db, default bind), they must live in the same bind as
ActivityLog — SQLite cannot enforce a foreign key across two separate
database files.
"""
from datetime import datetime, timezone
from typing import Optional
from enum import Enum

import sqlalchemy as sa
import sqlalchemy.orm as so

from app import db
from app.system_models import ActivityLog


"""
PluginType Enum so that Plugin_Type is consistent
To call use "Plugin.Plugin_Type = PluginType.CUSTOM"
The models class need to be imported to use the Enums
"""
class PluginType(Enum):
    NAGIOS = "Nagios"
    CUSTOM = "Custom"


"""
PluginSource Enum — distinguishes plugins that shipped with the
baseline Nagios/ISO install from plugins an administrator registered
manually through Plugin Manager (UI Flow Section 8, "Installation
Source").
"""
class PluginSource(Enum):
    BASELINE_ISO = "Baseline (ISO)"
    ADMINISTRATOR_ADDED = "Administrator Added"


"""
PluginStatus Enum — the plugin lifecycle/state machine described in
UI Flow Section 12 ("Plugin Availability vs Active Monitoring").
This single field is the source of truth for the state shown in the
Plugin Inventory / Plugin Details screens. "Installed" is intentionally
distinct from "Active": a plugin only reaches ACTIVE once an
administrator has configured a monitoring capability for it, Nagios
configuration has validated, and that configuration has been applied
(Phase 10).
"""
class PluginStatus(Enum):
    AVAILABLE = "Available"
    READY = "Ready"
    INSTALLED = "Installed"
    ENABLED = "Enabled"
    ACTIVE = "Active"
    DISABLED = "Disabled"
    UPDATE_AVAILABLE = "Update Available"
    VALIDATION_FAILED = "Validation Failed"
    DEPENDENCY_FAILED = "Dependency Failed"
    INSTALLATION_FAILED = "Installation Failed"
    CONFIGURATION_FAILED = "Configuration Failed"
    ROLLBACK = "Rollback"


class Plugin(db.Model):
    # Table Name
    __tablename__ = "PLUGIN"

    # Table Fields
    PluginID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Name: so.Mapped[str] = so.mapped_column(sa.String(100), unique=True, index=True)
    Display_Name: so.Mapped[Optional[str]] = so.mapped_column(sa.String(150))
    Description: so.Mapped[Optional[str]] = so.mapped_column(sa.String(500))
    Author: so.Mapped[Optional[str]] = so.mapped_column(sa.String(100))
    Category: so.Mapped[Optional[str]] = so.mapped_column(sa.String(50))
    Plugin_Type: so.Mapped[PluginType] = so.mapped_column(sa.Enum(PluginType))
    Source: so.Mapped[PluginSource] = so.mapped_column(sa.Enum(PluginSource))
    Current_Version: so.Mapped[Optional[str]] = so.mapped_column(sa.String(20))
    Status: so.Mapped[PluginStatus] = so.mapped_column(sa.Enum(PluginStatus))
    Executable_Path: so.Mapped[Optional[str]] = so.mapped_column(sa.String(255))
    Created_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Updated_At: so.Mapped[datetime] = so.mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    """
    Relationships with the specific Plugin Manager tables
    WriteOnlyMapped enables for Many of the related rows
    WriteOnlyMapped is to explicity load only that is queried
    back_populate specifies that you can access this table from either side
    """
    Versions: so.WriteOnlyMapped['PluginVersion'] = so.relationship(back_populates='Plugin_Version')
    Commands: so.WriteOnlyMapped['PluginCommand'] = so.relationship(back_populates='Plugin_Command')
    Dependencies: so.WriteOnlyMapped['PluginDependency'] = so.relationship(back_populates='Plugin_Dependency')
    Configurations: so.WriteOnlyMapped['PluginConfiguration'] = so.relationship(back_populates='Plugin_Configuration')
    History: so.WriteOnlyMapped['PluginHistory'] = so.relationship(back_populates='Plugin_History')


class PluginVersion(db.Model):
    # Table Name
    __tablename__ = "PLUGIN_VERSION"

    # Forces one row per plugin/version pair
    __table_args__ = (
        sa.UniqueConstraint('PluginID', 'Version', name='uq_plugin_version'),
    )

    # Table Fields
    PluginVersionID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Version: so.Mapped[str] = so.mapped_column(sa.String(20))
    Executable_Path: so.Mapped[Optional[str]] = so.mapped_column(sa.String(255))
    Checksum: so.Mapped[Optional[str]] = so.mapped_column(sa.String(64))
    Source: so.Mapped[Optional[str]] = so.mapped_column(sa.String(100))
    Is_Current: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=False)
    Installed_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Removed_At: so.Mapped[Optional[datetime]] = so.mapped_column()

    # Foreign Key Field
    PluginID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(Plugin.PluginID), index=True)

    """
    Gets one instance of Plugin
    back_populate specifies that you can access this table from either side
    """
    Plugin_Version: so.Mapped[Plugin] = so.relationship(back_populates='Versions')


class PluginCommand(db.Model):
    # Table Name
    __tablename__ = "PLUGIN_COMMAND"

    # Table Fields
    PluginCommandID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Command_Name: so.Mapped[str] = so.mapped_column(sa.String(100))
    Command_Definition: so.Mapped[str] = so.mapped_column(sa.String(500))
    Is_Default: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=True)
    Created_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Updated_At: so.Mapped[datetime] = so.mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Foreign Key Field
    PluginID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(Plugin.PluginID), index=True)

    """
    Gets one instance of Plugin
    back_populate specifies that you can access this table from either side
    """
    Plugin_Command: so.Mapped[Plugin] = so.relationship(back_populates='Commands')

    """
    WriteOnlyMapped enables for Many PluginCommandOverride rows
    (full override history is preserved, not just the active one)
    """
    Overrides: so.WriteOnlyMapped['PluginCommandOverride'] = so.relationship(back_populates='Command')


class PluginCommandOverride(db.Model):
    # Table Name
    __tablename__ = "PLUGIN_COMMAND_OVERRIDE"

    # Table Fields
    PluginCommandOverrideID: so.Mapped[int] = so.mapped_column(primary_key=True)

    """
    Original_Command is captured as an immutable snapshot at the moment
    the override is created, rather than derived live from
    PluginCommand.Command_Definition. This guarantees the original is
    preserved (Implementation Plan rule 11 / 14) even if the plugin's
    default command definition is later changed by an update.
    """
    Original_Command: so.Mapped[str] = so.mapped_column(sa.String(500))
    Override_Command: so.Mapped[str] = so.mapped_column(sa.String(500))
    Is_Active: so.Mapped[bool] = so.mapped_column(sa.Boolean(), default=True)
    Created_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Updated_At: so.Mapped[datetime] = so.mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Foreign Key Fields
    PluginCommandID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(PluginCommand.PluginCommandID), index=True)
    LogID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(ActivityLog.LogID), index=True)

    """
    Gets one instance of PluginCommand
    back_populate specifies that you can access this table from either side
    """
    Command: so.Mapped[PluginCommand] = so.relationship(back_populates='Overrides')

    """
    Gets one instance of ActivityLog — identifies which administrator
    made this override and when (repo convention: see
    ConfigurationChanges/NCPADeploymentStatus/ExportLog)
    """
    Logs: so.Mapped[ActivityLog] = so.relationship(back_populates='Plugin_Override_Logs')


class DependencyType(Enum):
    BINARY = "Binary"
    LIBRARY = "Library"
    PACKAGE = "Package"
    RUNTIME = "Runtime"
    # Linux capability requirement, e.g. CAP_NET_RAW for check_dhcp / check_icmp.
    # See spec files/Plugins_List.md (documents "Requires root/CAP_NET_RAW"
    # for specific plugins in the bundled 2.4.12 set).
    CAPABILITY = "Capability"


class DependencyStatus(Enum):
    OK = "Ok"
    MISSING = "Missing"
    INCOMPATIBLE = "Incompatible"


class PluginDependency(db.Model):
    # Table Name
    __tablename__ = "PLUGIN_DEPENDENCY"

    # Table Fields
    PluginDependencyID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Dependency_Name: so.Mapped[str] = so.mapped_column(sa.String(100))
    Dependency_Type: so.Mapped[DependencyType] = so.mapped_column(sa.Enum(DependencyType))
    Required_Version: so.Mapped[Optional[str]] = so.mapped_column(sa.String(20))
    Status: so.Mapped[DependencyStatus] = so.mapped_column(sa.Enum(DependencyStatus))

    # Foreign Key Field
    PluginID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(Plugin.PluginID), index=True)

    """
    Gets one instance of Plugin
    back_populate specifies that you can access this table from either side
    """
    Plugin_Dependency: so.Mapped[Plugin] = so.relationship(back_populates='Dependencies')


class PluginConfiguration(db.Model):
    """
    Stores Plugin Manager configuration state (e.g. argument defaults
    such as warning/critical thresholds) for a plugin.

    NOTE — scoped deliberately narrow for Phase 1:
    This does NOT yet link a plugin to a specific target host/service.
    UI Flow Section 13-17 shows configuration being applied to specific
    device/service targets ("Router-01 / Interface Traffic"), but the
    repository does not yet have a Service/monitoring-target model to
    foreign-key against (NetworkDiscovery models hosts, not services).
    Wiring PluginConfiguration to concrete targets is Phase 10
    (Monitoring Configuration) and will likely require an additional
    table/column once the target model is decided — do not treat this
    table as final/complete until that phase.
    """
    # Table Name
    __tablename__ = "PLUGIN_CONFIGURATION"

    # Table Fields
    PluginConfigurationID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Configuration_Data: so.Mapped[Optional[dict]] = so.mapped_column(sa.JSON())
    Created_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Updated_At: so.Mapped[datetime] = so.mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Foreign Key Field
    PluginID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(Plugin.PluginID), index=True)

    """
    Gets one instance of Plugin
    back_populate specifies that you can access this table from either side
    """
    Plugin_Configuration: so.Mapped[Plugin] = so.relationship(back_populates='Configurations')


class PluginHistoryAction(Enum):
    INSTALL = "Install"
    UPDATE = "Update"
    ENABLE = "Enable"
    DISABLE = "Disable"
    CONFIGURE = "Configure"
    COMMAND_OVERRIDE = "Command Override"
    VALIDATE = "Validate"
    ROLLBACK = "Rollback"
    REMOVE = "Remove"


class PluginActionResult(Enum):
    SUCCESS = "Success"
    FAILED = "Failed"


class PluginHistory(db.Model):
    # Table Name
    __tablename__ = "PLUGIN_HISTORY"

    # Table Fields
    PluginHistoryID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Action: so.Mapped[PluginHistoryAction] = so.mapped_column(sa.Enum(PluginHistoryAction))
    Old_Value: so.Mapped[Optional[str]] = so.mapped_column(sa.String(255))
    New_Value: so.Mapped[Optional[str]] = so.mapped_column(sa.String(255))
    Result: so.Mapped[PluginActionResult] = so.mapped_column(sa.Enum(PluginActionResult))
    Message: so.Mapped[Optional[str]] = so.mapped_column(sa.String(500))

    # Foreign Key Fields
    PluginID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(Plugin.PluginID), index=True)
    LogID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(ActivityLog.LogID), index=True)

    """
    Gets one instance of Plugin
    back_populate specifies that you can access this table from either side
    """
    Plugin_History: so.Mapped[Plugin] = so.relationship(back_populates='History')

    """
    Gets one instance of ActivityLog — identifies which administrator
    performed this action and when (repo convention: see
    ConfigurationChanges/NCPADeploymentStatus/ExportLog)
    """
    Logs: so.Mapped[ActivityLog] = so.relationship(back_populates='Plugin_History_Logs')


class PluginScanStatusValue(Enum):
    RUNNING = "Running"
    SUCCESS = "Success"
    FAILED = "Failed"


class PluginScanStatus(db.Model):
    """
    Tracks a single filesystem-scan run (Phase 2). Mirrors
    NetworkDiscoveryStatus's shape exactly, since Plugin Manager's
    scan-trigger route follows the same background-thread +
    status-polling pattern already established by Network Discovery
    and NCPA deployment elsewhere in this codebase.
    """
    # Table Name
    __tablename__ = "PLUGIN_SCAN_STATUS"

    # Table Fields
    PluginScanStatusID: so.Mapped[int] = so.mapped_column(primary_key=True)
    Status: so.Mapped[PluginScanStatusValue] = so.mapped_column(sa.Enum(PluginScanStatusValue))
    Progress: so.Mapped[int] = so.mapped_column()
    Message: so.Mapped[str] = so.mapped_column(sa.String(100))
    Start_At: so.Mapped[datetime] = so.mapped_column(default=lambda: datetime.now(timezone.utc))
    Completed_At: so.Mapped[Optional[datetime]] = so.mapped_column()
    Error: so.Mapped[Optional[str]] = so.mapped_column()

    # Foreign Key Field
    LogID: so.Mapped[int] = so.mapped_column(sa.ForeignKey(ActivityLog.LogID), index=True)

    """
    Gets one instance of ActivityLog
    back_populate specifies that you can access this table from either side
    """
    Logs: so.Mapped[ActivityLog] = so.relationship(back_populates='Plugin_Scan_Logs')
