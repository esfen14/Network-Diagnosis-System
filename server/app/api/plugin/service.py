"""
service.py — Query/serialization layer for Plugin Manager read endpoints
(Phase 3, Implementation Plan Section 18).

Keeps manager.py's routes thin: each route parses/validates request
args, calls one function here, and wraps the result with
success()/error(). All actual querying and response-shaping lives here.

Pagination/filter/sort conventions match app/api/system/log.py exactly
(page, per_page, sort_by, order, search query params; items/page/
per_page/pages/total/has_next/has_prev response shape).
"""
from datetime import datetime, timezone

import sqlalchemy as sa

from app import db
from app.plugin_models import (
    Plugin, PluginType, PluginStatus, PluginSource,
    PluginVersion,
    PluginCommand, PluginCommandOverride,
    PluginDependency, DependencyType, DependencyStatus,
    PluginConfiguration, PluginConfigurationStatus,
    PluginHistory, PluginHistoryAction, PluginActionResult,
)
from app.system_models import ActivityLog, User, NetworkDiscovery
from app.api.plugin.nagios_validator import validate_nagios_configuration
from app.api.plugin.command_validator import validate_command_definition
from app.api.plugin.plugin_validator import (
    validate_plugin_executable, check_executable, check_permissions, check_execution,
)
from app.api.plugin.custom_plugin import (
    stage_upload, check_name_collision, install_staged_file, cleanup_staging,
    InvalidFilenameError, UploadTooLargeError, NameCollisionError,
)
from app.api.plugin.plugin_update import (
    receive_archive, extract_archive, find_plugin_in_extracted,
    backup_plugin, replace_plugin, restore_from_backup, has_backup,
    cleanup_staging as cleanup_update_staging,
    InvalidUrlError, DownloadError, ArchiveTooLargeError,
    UnsupportedArchiveError, UnsafeArchiveError, PluginNotInArchiveError,
    NoBackupAvailableError,
)
from app.api.plugin.scanner import extract_version
from app.api.plugin.monitoring_config import (
    generate_command_name, generate_plugin_services_cfg, write_staged_cfg,
    ensure_cfg_file_directive, validate_plugin_services_config, apply_plugin_services_config,
)
import os


# Statuses considered "some kind of failure" for the inventory page's
# combined "Failed" filter chip (UI Flow Section 7) and for the
# landing page's "Validation Issues" summary count (Section 6). These
# are the 4 distinct *_FAILED members of PluginStatus.
FAILED_STATUSES = (
    PluginStatus.VALIDATION_FAILED,
    PluginStatus.DEPENDENCY_FAILED,
    PluginStatus.INSTALLATION_FAILED,
    PluginStatus.CONFIGURATION_FAILED,
)

# Statuses that block Enable/Disable outright — the 4 *_FAILED
# variants (must be resolved first) plus ROLLBACK (an in-progress
# problem state, not a normal enable/disable target). Confirmed:
# Enable is intentionally permissive otherwise (any other status,
# including AVAILABLE/READY/INSTALLED/UPDATE_AVAILABLE) — to be
# revisited once Phase 10 exists if it turns out to conflict with
# real monitoring-configuration behavior.
BLOCKED_TRANSITION_STATUSES = FAILED_STATUSES + (PluginStatus.ROLLBACK,)

PLUGIN_SORT_FIELDS = {
    "name": Plugin.Name,
    "type": Plugin.Plugin_Type,
    "status": Plugin.Status,
    "version": Plugin.Current_Version,
    "updated_at": Plugin.Updated_At,
}

HISTORY_SORT_FIELDS = {
    "id": PluginHistory.PluginHistoryID,
    "performed_at": ActivityLog.Performed_At,
}


class InvalidQueryError(ValueError):
    """Raised for any bad query param; routes turn this into a 400."""
    pass


def serialize_plugin_summary_row(plugin):
    """Shape used by the inventory list (one row per plugin)."""
    return {
        "id": plugin.PluginID,
        "name": plugin.Name,
        "display_name": plugin.Display_Name,
        "category": plugin.Category,
        "type": plugin.Plugin_Type.value,
        "source": plugin.Source.value,
        "status": plugin.Status.value,
        "current_version": plugin.Current_Version,
        "updated_at": plugin.Updated_At.isoformat(),
    }


def get_plugin_inventory(page, per_page, search, plugin_type, status, sort_by, order):
    """
    Paginated plugin inventory (UI Flow Section 7).

    Args:
        page, per_page: pagination.
        search: matched against Name and Display_Name (case-insensitive).
        plugin_type: PluginType enum VALUE string (e.g. "Nagios",
            "Custom") or None for no filter.
        status: PluginStatus enum VALUE string, OR the literal string
            "Failed" (matches ANY of FAILED_STATUSES, since the
            inventory page's filter chips collapse all 4 *_FAILED
            states into one "Failed" option), or None for no filter.
        sort_by: one of PLUGIN_SORT_FIELDS' keys.
        order: "asc" or "desc".

    Returns: dict shaped for success() -> items/page/per_page/pages/
        total/has_next/has_prev.

    Raises: InvalidQueryError for any invalid param.
    """
    if page < 1:
        raise InvalidQueryError("Page must be greater than 0")
    if per_page < 1 or per_page > 100:
        raise InvalidQueryError("per_page must be between 1 and 100")

    sort_column = PLUGIN_SORT_FIELDS.get(sort_by)
    if sort_column is None:
        raise InvalidQueryError("Invalid sort field")

    query = sa.select(Plugin)

    if search:
        query = query.where(
            sa.or_(
                Plugin.Name.ilike(f"%{search}%"),
                Plugin.Display_Name.ilike(f"%{search}%"),
            )
        )

    if plugin_type:
        try:
            query = query.where(Plugin.Plugin_Type == PluginType(plugin_type))
        except ValueError:
            raise InvalidQueryError(f"Invalid type filter: {plugin_type}")

    if status:
        if status == "Failed":
            query = query.where(Plugin.Status.in_(FAILED_STATUSES))
        else:
            try:
                query = query.where(Plugin.Status == PluginStatus(status))
            except ValueError:
                raise InvalidQueryError(f"Invalid status filter: {status}")

    if order == "desc":
        query = query.order_by(sort_column.desc())
    elif order == "asc":
        query = query.order_by(sort_column.asc())
    else:
        raise InvalidQueryError("Invalid order.")

    result = db.paginate(query, page=page, per_page=per_page, error_out=False)

    items = [serialize_plugin_summary_row(p) for p in result.items]

    return {
        "items": items,
        "page": result.page,
        "per_page": result.per_page,
        "pages": result.pages,
        "total": result.total,
        "has_next": result.has_next,
        "has_prev": result.has_prev,
    }


def get_running_checks(page, per_page, search):
    """
    Paginated list of monitoring checks that are live in Nagios right
    now: every PluginConfiguration with Status APPLIED, i.e. one plugin
    wired to one target device as a Nagios service. Backs the Plugin
    Manager's "Currently Running" tab. Pending and failed configurations
    are left out since they aren't running.

    Args:
        page, per_page: pagination.
        search: matched against plugin name, service description,
            device hostname and IP (case-insensitive).

    Returns: dict shaped for success() -> items/page/per_page/pages/
        total/has_next/has_prev.

    Raises: InvalidQueryError for invalid pagination.
    """
    if page < 1:
        raise InvalidQueryError("Page must be greater than 0")
    if per_page < 1 or per_page > 100:
        raise InvalidQueryError("per_page must be between 1 and 100")

    query = (
        sa.select(PluginConfiguration)
        .join(Plugin, Plugin.PluginID == PluginConfiguration.PluginID)
        .outerjoin(NetworkDiscovery, NetworkDiscovery.NetDiscoveryID == PluginConfiguration.NetDiscoveryID)
        .where(PluginConfiguration.Status == PluginConfigurationStatus.APPLIED)
    )

    if search:
        query = query.where(
            sa.or_(
                Plugin.Name.ilike(f"%{search}%"),
                Plugin.Display_Name.ilike(f"%{search}%"),
                PluginConfiguration.Service_Description.ilike(f"%{search}%"),
                NetworkDiscovery.Hostname.ilike(f"%{search}%"),
                NetworkDiscovery.IP_Address.ilike(f"%{search}%"),
            )
        )

    query = query.order_by(
        Plugin.Name.asc(),
        NetworkDiscovery.Hostname.asc(),
        PluginConfiguration.Service_Description.asc(),
    )

    result = db.paginate(query, page=page, per_page=per_page, error_out=False)

    items = []
    for config in result.items:
        plugin = config.Plugin_Configuration
        target = config.Target_Device
        items.append({
            "id": config.PluginConfigurationID,
            "plugin": {
                "id": plugin.PluginID,
                "name": plugin.Name,
                "display_name": plugin.Display_Name,
                "status": plugin.Status.value,
            },
            "target": {
                "id": target.NetDiscoveryID,
                "hostname": target.Hostname,
                "ip_address": target.IP_Address,
            } if target else None,
            "service_description": config.Service_Description,
            "applied_at": config.Updated_At.isoformat(),
        })

    return {
        "items": items,
        "page": result.page,
        "per_page": result.per_page,
        "pages": result.pages,
        "total": result.total,
        "has_next": result.has_next,
        "has_prev": result.has_prev,
    }


def get_plugin_details(plugin_id):
    """
    Single plugin's full detail view (UI Flow Section 8).

    Returns None if the plugin doesn't exist (route turns that into 404).

    NOTE on "monitoring_usage": PluginConfiguration has no target
    (host/service) linkage yet — that's Phase 10. Per explicit decision,
    this returns non-zero PLACEHOLDER numbers (taken directly from the
    UI Flow mockup's own example, Section 8) so the frontend has
    something to render before Phase 10 exists. "placeholder": true
    marks it clearly as not-yet-real data for any future caller.
    """
    plugin = db.session.get(Plugin, plugin_id)
    if plugin is None:
        return None

    commands_count = db.session.scalar(
        sa.select(sa.func.count()).select_from(PluginCommand).where(PluginCommand.PluginID == plugin_id)
    )
    dependencies_count = db.session.scalar(
        sa.select(sa.func.count()).select_from(PluginDependency).where(PluginDependency.PluginID == plugin_id)
    )

    return {
        "id": plugin.PluginID,
        "name": plugin.Name,
        "display_name": plugin.Display_Name,
        "description": plugin.Description,
        "author": plugin.Author,
        "category": plugin.Category,
        "type": plugin.Plugin_Type.value,
        "source": plugin.Source.value,
        "status": plugin.Status.value,
        "current_version": plugin.Current_Version,
        "executable_path": plugin.Executable_Path,
        "created_at": plugin.Created_At.isoformat(),
        "updated_at": plugin.Updated_At.isoformat(),
        "commands_count": commands_count,
        "dependencies_count": dependencies_count,
        "rollback_available": has_backup(plugin.Name),
        "monitoring_usage": {
            "services": 4,
            "devices": 2,
            "placeholder": True,
            "note": "Target linkage not implemented until Phase 10 (Monitoring Configuration).",
        },
    }


def get_plugin_history(page, per_page, plugin_id, sort_by, order):
    """
    Global plugin history (UI Flow Section 24) — one table across ALL
    plugins, optionally filtered to a single plugin_id (used when
    opened from that plugin's own [History] button, but it's the same
    underlying query either way).

    IMPLEMENTATION NOTE: this deliberately selects only PluginHistory
    (not a multi-entity sa.select(PluginHistory, Plugin, ActivityLog,
    User) join, the way log.py's activity_logs() does it) and reaches
    Plugin/ActivityLog/User via relationship navigation instead.
    db.paginate() in the installed Flask-SQLAlchemy version always
    calls .scalars() on the underlying result (see
    flask_sqlalchemy.pagination.SelectPagination._query_items), which
    keeps only the FIRST selected entity per row and silently drops
    the rest — this is what makes log.py's own
    "for activity, user in logs.items" line raise
    "TypeError: cannot unpack non-iterable ActivityLog object" (a
    pre-existing bug, confirmed by testing that route directly; not
    something introduced here, and out of Plugin Manager's scope to
    fix). Selecting a single entity avoids the problem entirely, and
    joinedload() avoids the N+1 queries relationship navigation would
    otherwise cost.
    """
    if page < 1:
        raise InvalidQueryError("Page must be greater than 0")
    if per_page < 1 or per_page > 100:
        raise InvalidQueryError("per_page must be between 1 and 100")

    sort_column = HISTORY_SORT_FIELDS.get(sort_by)
    if sort_column is None:
        raise InvalidQueryError("Invalid sort field")

    query = (
        sa.select(PluginHistory)
        .join(Plugin, Plugin.PluginID == PluginHistory.PluginID)
        .join(ActivityLog, ActivityLog.LogID == PluginHistory.LogID)
        .join(User, User.UserID == ActivityLog.UserID)
        .options(
            sa.orm.joinedload(PluginHistory.Plugin_History),
            sa.orm.joinedload(PluginHistory.Logs).joinedload(ActivityLog.User_Logs),
        )
    )

    if plugin_id is not None:
        query = query.where(PluginHistory.PluginID == plugin_id)

    if order == "desc":
        query = query.order_by(sort_column.desc())
    elif order == "asc":
        query = query.order_by(sort_column.asc())
    else:
        raise InvalidQueryError("Invalid order.")

    result = db.paginate(query, page=page, per_page=per_page, error_out=False)

    items = []
    for history in result.items:
        activity = history.Logs
        user = activity.User_Logs
        items.append({
            "id": history.PluginHistoryID,
            "plugin_id": history.PluginID,
            "plugin_name": history.Plugin_History.Name,
            "action": history.Action.value,
            "administrator": f"{user.First_Name} {user.Last_Name}",
            "result": history.Result.value,
            "performed_at": activity.Performed_At.isoformat(),
            "message": history.Message,
        })

    return {
        "items": items,
        "page": result.page,
        "per_page": result.per_page,
        "pages": result.pages,
        "total": result.total,
        "has_next": result.has_next,
        "has_prev": result.has_prev,
    }


def get_plugin_commands(plugin_id):
    """
    A plugin's commands (UI Flow Sections 15-16), each with its
    currently active override (if any) merged in. Returns None if the
    plugin doesn't exist.
    """
    plugin = db.session.get(Plugin, plugin_id)
    if plugin is None:
        return None

    commands = db.session.scalars(
        sa.select(PluginCommand).where(PluginCommand.PluginID == plugin_id)
    ).all()

    return [
        serialize_command(command, get_active_override(command.PluginCommandID))
        for command in commands
    ]


def get_plugin_dependencies(plugin_id):
    """
    A plugin's dependencies (UI Flow Section 8's "Dependencies:
    [OK] Nagios Core" list). Returns None if the plugin doesn't exist.
    """
    plugin = db.session.get(Plugin, plugin_id)
    if plugin is None:
        return None

    dependencies = db.session.scalars(
        sa.select(PluginDependency).where(PluginDependency.PluginID == plugin_id)
    ).all()

    return [
        {
            "id": dep.PluginDependencyID,
            "name": dep.Dependency_Name,
            "type": dep.Dependency_Type.value,
            "required_version": dep.Required_Version,
            "status": dep.Status.value,
        }
        for dep in dependencies
    ]


def get_plugin_summary():
    """
    Landing page summary counts (UI Flow Section 6).

    "Active Capabilities" and "Updates Available"/"Validation Issues"
    all read from Plugin.Status, which is the single source of truth
    for plugin lifecycle state (see plugin_models.py's PluginStatus
    docstring).
    """
    installed = db.session.scalar(sa.select(sa.func.count()).select_from(Plugin))
    active = db.session.scalar(
        sa.select(sa.func.count()).select_from(Plugin).where(Plugin.Status == PluginStatus.ACTIVE)
    )
    custom = db.session.scalar(
        sa.select(sa.func.count()).select_from(Plugin).where(Plugin.Plugin_Type == PluginType.CUSTOM)
    )
    updates_available = db.session.scalar(
        sa.select(sa.func.count()).select_from(Plugin).where(Plugin.Status == PluginStatus.UPDATE_AVAILABLE)
    )
    validation_issues = db.session.scalar(
        sa.select(sa.func.count()).select_from(Plugin).where(Plugin.Status.in_(FAILED_STATUSES))
    )

    return {
        "installed_plugins": installed,
        "active_capabilities": active,
        "custom_plugins": custom,
        "updates_available": updates_available,
        "validation_issues": validation_issues,
    }


# ==========================================================
# ENABLE / DISABLE (Phase 5)
# ==========================================================

class PluginNotFoundError(Exception):
    """No Plugin row with the given id."""
    pass


class InvalidTransitionError(Exception):
    """Current Plugin.Status doesn't allow the requested operation."""
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class NagiosValidationError(Exception):
    """Nagios's own config validation failed or Nagios isn't reachable."""
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def record_plugin_action(plugin, action, result, user_id, old_value=None, new_value=None, message=None):
    """Shared history-recording helper for enable/disable (and future
    mutating operations in later phases)."""
    log = ActivityLog(Action_Type=f"plugin.{action.value.lower()}", UserID=user_id)
    db.session.add(log)
    db.session.flush()

    db.session.add(PluginHistory(
        PluginID=plugin.PluginID,
        Action=action,
        Old_Value=old_value,
        New_Value=new_value,
        Result=result,
        Message=(message[:500] if message else None),
        LogID=log.LogID,
    ))


def enable_plugin(plugin_id, user_id):
    """
    Enable a plugin (UI Flow Section 8's [Enable] action).

    Runs Nagios's own config validation first (see nagios_validator.py
    for exactly what that checks and why). Idempotent: enabling an
    already-ENABLED or already-ACTIVE plugin is a no-op success (does
    not downgrade ACTIVE back to ENABLED — ACTIVE is Phase 10's
    territory).

    Raises:
        PluginNotFoundError, InvalidTransitionError, NagiosValidationError
    """
    plugin = db.session.get(Plugin, plugin_id)
    if plugin is None:
        raise PluginNotFoundError()

    if plugin.Status in BLOCKED_TRANSITION_STATUSES:
        raise InvalidTransitionError(f"Cannot enable a plugin in '{plugin.Status.value}' state.")

    if plugin.Status in (PluginStatus.ENABLED, PluginStatus.ACTIVE):
        return {"id": plugin.PluginID, "status": plugin.Status.value, "changed": False}

    is_valid, output = validate_nagios_configuration()

    if not is_valid:
        record_plugin_action(
            plugin, PluginHistoryAction.ENABLE, PluginActionResult.FAILED, user_id,
            old_value=plugin.Status.value, message=output,
        )
        db.session.commit()
        raise NagiosValidationError(output)

    old_status = plugin.Status.value
    plugin.Status = PluginStatus.ENABLED
    record_plugin_action(
        plugin, PluginHistoryAction.ENABLE, PluginActionResult.SUCCESS, user_id,
        old_value=old_status, new_value=PluginStatus.ENABLED.value,
    )
    db.session.commit()

    return {"id": plugin.PluginID, "status": plugin.Status.value, "changed": True}


def disable_plugin(plugin_id, user_id):
    """
    Disable a plugin (UI Flow Section 8's [Disable] action).

    Unlike enable_plugin, DISABLED is reachable from ACTIVE too (an
    admin turning off a currently-active monitoring capability is a
    normal disable, not something Phase 10-specific). Idempotent:
    disabling an already-DISABLED plugin is a no-op success.

    Raises:
        PluginNotFoundError, InvalidTransitionError, NagiosValidationError
    """
    plugin = db.session.get(Plugin, plugin_id)
    if plugin is None:
        raise PluginNotFoundError()

    if plugin.Status in BLOCKED_TRANSITION_STATUSES:
        raise InvalidTransitionError(f"Cannot disable a plugin in '{plugin.Status.value}' state.")

    if plugin.Status == PluginStatus.DISABLED:
        return {"id": plugin.PluginID, "status": plugin.Status.value, "changed": False}

    is_valid, output = validate_nagios_configuration()

    if not is_valid:
        record_plugin_action(
            plugin, PluginHistoryAction.DISABLE, PluginActionResult.FAILED, user_id,
            old_value=plugin.Status.value, message=output,
        )
        db.session.commit()
        raise NagiosValidationError(output)

    old_status = plugin.Status.value
    plugin.Status = PluginStatus.DISABLED
    record_plugin_action(
        plugin, PluginHistoryAction.DISABLE, PluginActionResult.SUCCESS, user_id,
        old_value=old_status, new_value=PluginStatus.DISABLED.value,
    )
    db.session.commit()

    return {"id": plugin.PluginID, "status": plugin.Status.value, "changed": True}


# ==========================================================
# COMMAND MANAGEMENT (Phase 6)
# ==========================================================

class CommandNotFoundError(Exception):
    """No PluginCommand with the given id belonging to the given plugin."""
    pass


class InvalidCommandError(Exception):
    """Proposed override command failed validate_command_definition()."""
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def serialize_command(command, active_override):
    return {
        "id": command.PluginCommandID,
        "command_name": command.Command_Name,
        "default_command": command.Command_Definition,
        "active_command": (
            active_override.Override_Command if active_override else command.Command_Definition
        ),
        "is_overridden": active_override is not None,
        "is_default": command.Is_Default,
    }


def get_command_for_plugin(plugin_id, command_id):
    """Shared lookup used by both override_command and
    restore_default_command. Returns (plugin, command) or raises
    PluginNotFoundError / CommandNotFoundError."""
    plugin = db.session.get(Plugin, plugin_id)
    if plugin is None:
        raise PluginNotFoundError()

    command = db.session.scalar(
        sa.select(PluginCommand).where(
            PluginCommand.PluginCommandID == command_id,
            PluginCommand.PluginID == plugin_id,
        )
    )
    if command is None:
        raise CommandNotFoundError()

    return plugin, command


def get_active_override(command_id):
    return db.session.scalar(
        sa.select(PluginCommandOverride)
        .where(
            PluginCommandOverride.PluginCommandID == command_id,
            PluginCommandOverride.Is_Active.is_(True),
        )
        .order_by(PluginCommandOverride.Created_At.desc())
    )


def override_command(plugin_id, command_id, override_command_text, user_id):
    """
    Save a command override (UI Flow Section 16's [Save Override]).

    DB-only — does not touch live nagios.cfg (see command_validator.py
    docstring for why). Deactivates any previously active override for
    this command (only one override is "active" at a time; full
    history is preserved via the deactivated rows, per Phase 1's
    PluginCommandOverride design).

    Raises:
        PluginNotFoundError, CommandNotFoundError, InvalidCommandError
    """
    plugin, command = get_command_for_plugin(plugin_id, command_id)

    is_valid, reason = validate_command_definition(override_command_text)
    if not is_valid:
        raise InvalidCommandError(reason)

    previous_override = get_active_override(command_id)
    old_active_command = previous_override.Override_Command if previous_override else command.Command_Definition

    if previous_override is not None:
        previous_override.Is_Active = False

    log = ActivityLog(Action_Type="plugin.command_override", UserID=user_id)
    db.session.add(log)
    db.session.flush()

    new_override = PluginCommandOverride(
        PluginCommandID=command.PluginCommandID,
        Original_Command=command.Command_Definition,
        Override_Command=override_command_text,
        LogID=log.LogID,
    )
    db.session.add(new_override)
    db.session.flush()

    db.session.add(PluginHistory(
        PluginID=plugin.PluginID,
        Action=PluginHistoryAction.COMMAND_OVERRIDE,
        Old_Value=old_active_command,
        New_Value=override_command_text,
        Result=PluginActionResult.SUCCESS,
        LogID=log.LogID,
    ))

    db.session.commit()

    return serialize_command(command, new_override)


def restore_default_command(plugin_id, command_id, user_id):
    """
    Restore a command's default (UI Flow Sections 15/16's
    [Restore Default]).

    Deactivates the currently active override (if any) and does NOT
    create a new override row — the effective active_command reverts
    to command.Command_Definition. Idempotent: if there's no active
    override already, this is a no-op success (matches Phase 5's
    enable/disable idempotency pattern).

    Raises:
        PluginNotFoundError, CommandNotFoundError
    """
    plugin, command = get_command_for_plugin(plugin_id, command_id)

    active_override = get_active_override(command_id)
    if active_override is None:
        return {**serialize_command(command, None), "changed": False}

    removed_command = active_override.Override_Command
    active_override.Is_Active = False

    log = ActivityLog(Action_Type="plugin.command_restore", UserID=user_id)
    db.session.add(log)
    db.session.flush()

    db.session.add(PluginHistory(
        PluginID=plugin.PluginID,
        Action=PluginHistoryAction.ROLLBACK,
        Old_Value=removed_command,
        New_Value=command.Command_Definition,
        Result=PluginActionResult.SUCCESS,
        LogID=log.LogID,
    ))

    db.session.commit()

    return {**serialize_command(command, None), "changed": True}


# ==========================================================
# VALIDATION (Phase 7)
# ==========================================================

def validate_plugin(plugin_id, user_id):
    """
    Validate a single plugin's executable/permissions/execution (UI
    Flow Section 8's [Validate] action). Deliberately does NOT run
    nagios_validator.py's config check or re-check PluginDependency
    rows — see plugin_validator.py's module docstring for why those
    stay separate.

    Confirmed: updates Plugin.Status based on the result. Failing
    checks set VALIDATION_FAILED. Passing checks on a plugin that was
    previously VALIDATION_FAILED reset it to READY. Passing checks on
    any OTHER status (e.g. ENABLED, ACTIVE) leave Status unchanged —
    validating an already-enabled plugin shouldn't silently downgrade
    it back to READY.

    Raises:
        PluginNotFoundError
    """
    plugin = db.session.get(Plugin, plugin_id)
    if plugin is None:
        raise PluginNotFoundError()

    result = validate_plugin_executable(plugin.Executable_Path)

    old_status = plugin.Status.value

    if not result["is_valid"]:
        plugin.Status = PluginStatus.VALIDATION_FAILED
    elif plugin.Status == PluginStatus.VALIDATION_FAILED:
        plugin.Status = PluginStatus.READY

    failed_checks = [name for name, check in result["checks"].items() if not check["passed"]]
    message = (
        "All checks passed."
        if result["is_valid"]
        else f"Failed checks: {', '.join(failed_checks)}."
    )

    record_plugin_action(
        plugin,
        PluginHistoryAction.VALIDATE,
        PluginActionResult.SUCCESS if result["is_valid"] else PluginActionResult.FAILED,
        user_id,
        old_value=old_status,
        new_value=plugin.Status.value,
        message=message,
    )
    db.session.commit()

    return {
        "plugin_id": plugin.PluginID,
        "is_valid": result["is_valid"],
        "status": plugin.Status.value,
        "checks": result["checks"],
    }


# ==========================================================
# CUSTOM PLUGINS (Phase 8)
# ==========================================================

class PluginNameTakenError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


# Exit codes 0-3 are the standard Nagios plugin API range
# (OK/WARNING/CRITICAL/UNKNOWN). Confirmed as the concrete stand-in
# for UI Flow's "Nagios compatibility" check: distinct from Phase 7's
# check_execution() (which accepts ANY exit code, by design, to avoid
# false negatives on real checks legitimately returning WARNING/
# CRITICAL) — here, on a --version invocation specifically, landing
# outside 0-3 is a real signal of non-standard behavior (e.g. a shell
# "command not found" 127, or an unhandled crash).
NAGIOS_STANDARD_EXIT_CODES = (0, 1, 2, 3)


def check_metadata(name, command_name, command_definition):
    """UI Flow Section 10's 'Metadata valid' check."""
    if not name or not name.strip():
        return {"passed": False, "message": "Plugin name is required."}
    if not command_name or not command_name.strip():
        return {"passed": False, "message": "Command name is required."}
    if not command_definition or not command_definition.strip():
        return {"passed": False, "message": "Command definition is required."}
    return {"passed": True, "message": "Metadata is valid."}


def check_command(command_definition):
    """UI Flow Section 10's 'Command definition detected' check —
    reuses Phase 6's validator on the admin-provided command string."""
    is_valid, message = validate_command_definition(command_definition)
    return {"passed": is_valid, "message": message or "Command definition is valid."}


def check_dependencies_well_formed(dependencies):
    """
    UI Flow Section 10's 'Dependency check'. Confirmed scope: no
    mechanism exists to verify real system state (is a package
    actually installed, etc.) — this checks that each DECLARED
    dependency entry is well-formed (non-empty name, a real
    DependencyType value), not that dependencies are satisfied.
    """
    if not dependencies:
        return {"passed": True, "message": "No dependencies declared."}

    for dep in dependencies:
        name = dep.get("name") if isinstance(dep, dict) else None
        dep_type = dep.get("type") if isinstance(dep, dict) else None

        if not name or not str(name).strip():
            return {"passed": False, "message": "A declared dependency is missing a name."}

        try:
            DependencyType(dep_type)
        except (ValueError, TypeError):
            valid_values = ", ".join(t.value for t in DependencyType)
            return {"passed": False, "message": f"Invalid dependency type '{dep_type}'. Must be one of: {valid_values}."}

    return {"passed": True, "message": f"{len(dependencies)} dependency entr{'y' if len(dependencies) == 1 else 'ies'} well-formed."}


def check_nagios_compatibility(execution_result):
    """UI Flow Section 10's 'Nagios compatibility' check — see
    NAGIOS_STANDARD_EXIT_CODES for what this actually verifies and why."""
    exit_code = execution_result.get("exit_code")
    if exit_code is None:
        return {"passed": False, "message": "Could not determine exit code (execution failed)."}
    if exit_code not in NAGIOS_STANDARD_EXIT_CODES:
        return {
            "passed": False,
            "message": f"Exit code {exit_code} is outside the standard Nagios plugin range (0-3).",
        }
    return {"passed": True, "message": f"Exit code {exit_code} is within the standard Nagios plugin range."}


def validate_custom_plugin_submission(staged_path, name, command_name, command_definition, dependencies):
    """
    Runs all 7 checks from UI Flow Section 10 against a staged
    (not-yet-installed) file and the admin-provided form fields.

    Returns:
        {"is_valid": bool, "checks": {...7 keys...}}
    """
    file_detected = check_executable(staged_path)
    executable_check = check_permissions(staged_path)
    execution_check = check_execution(staged_path)
    command_check = check_command(command_definition)
    metadata_check = check_metadata(name, command_name, command_definition)
    dependency_check = check_dependencies_well_formed(dependencies)
    compatibility_check = check_nagios_compatibility(execution_check)

    checks = {
        "file_detected": file_detected,
        "executable_permission": executable_check,
        "execution_test": execution_check,
        "command_definition": command_check,
        "metadata": metadata_check,
        "dependency_check": dependency_check,
        "nagios_compatibility": compatibility_check,
    }

    is_valid = all(c["passed"] for c in checks.values())

    return {"is_valid": is_valid, "checks": checks}


# Confirmed against client/src/types/plugin.ts (integration branch):
# the frontend's CustomPluginCheckResult expects {name, passed, message}
# array items, not our internal {key: {passed, message}} dict shape.
# These display names match UI Flow Section 10's own labels exactly.
CUSTOM_PLUGIN_CHECK_DISPLAY_NAMES = {
    "file_detected": "Plugin file detected",
    "executable_permission": "Executable permission",
    "execution_test": "Plugin execution test",
    "command_definition": "Command definition detected",
    "metadata": "Metadata valid",
    "dependency_check": "Dependency check",
    "nagios_compatibility": "Nagios compatibility",
}


def serialize_custom_plugin_checks(checks_dict):
    """Converts validate_custom_plugin_submission()'s internal
    {key: {passed, message}} dict into the [{name, passed, message}]
    list shape client/src/types/plugin.ts's CustomPluginCheckResult[]
    expects."""
    return [
        {
            "name": CUSTOM_PLUGIN_CHECK_DISPLAY_NAMES.get(key, key),
            "passed": check["passed"],
            "message": check["message"],
        }
        for key, check in checks_dict.items()
    ]


def register_custom_plugin(file_storage, name, version, description, author, plugin_type,
                            command_name, command_definition, dependencies, user_id):
    """
    Full Phase 8 workflow, atomically, per the confirmed single-endpoint
    design: Upload -> Stage -> Validate -> Install -> Register ->
    Define Command -> Available for monitoring.

    On ANY validation failure, nothing is persisted (no DB rows, no
    installed file) and the staging directory is cleaned up — the
    structured check results are still returned so a future frontend
    can show UI Flow Section 10's "Plugin Validation Failed" screen.

    Args:
        file_storage: werkzeug FileStorage from request.files.
        name, version, description, author: plugin metadata.
        plugin_type: "Nagios" or "Custom" (PluginType value string).
        command_name, command_definition: the plugin's Nagios command.
        dependencies: list of {"name": str, "type": str} dicts, or None.
        user_id: the acting administrator.

    Returns:
        {"success": bool, "checks": [...], "plugin": {...} | None, "message": str}
        Matches client/src/types/plugin.ts's CustomPluginUploadResult
        exactly (confirmed against the integration branch) — field
        names here (success/checks-as-list/message) differ from
        validate_custom_plugin_submission()'s internal shape
        (is_valid/checks-as-dict) on purpose.

    Raises:
        InvalidFilenameError, UploadTooLargeError, NameCollisionError,
        PluginNameTakenError, ValueError (bad plugin_type)
    """
    dependencies = dependencies or []

    try:
        plugin_type_enum = PluginType(plugin_type)
    except ValueError:
        valid_values = ", ".join(t.value for t in PluginType)
        raise ValueError(f"Invalid plugin type '{plugin_type}'. Must be one of: {valid_values}.")

    if db.session.scalar(sa.select(Plugin).where(Plugin.Name == name)):
        raise PluginNameTakenError(f"A plugin named '{name}' already exists.")

    staged_path, safe_filename, staging_dir, checksum, size_bytes = stage_upload(file_storage)

    try:
        check_name_collision(safe_filename)

        result = validate_custom_plugin_submission(
            staged_path, name, command_name, command_definition, dependencies,
        )

        if not result["is_valid"]:
            failed_names = [
                CUSTOM_PLUGIN_CHECK_DISPLAY_NAMES.get(k, k)
                for k, c in result["checks"].items() if not c["passed"]
            ]
            return {
                "success": False,
                "checks": serialize_custom_plugin_checks(result["checks"]),
                "plugin": None,
                "message": f"Validation failed: {', '.join(failed_names)}.",
            }

        installed_path = install_staged_file(staged_path, safe_filename)

        plugin = Plugin(
            Name=name,
            Display_Name=name,
            Description=description,
            Author=author,
            Plugin_Type=plugin_type_enum,
            Source=PluginSource.ADMINISTRATOR_ADDED,
            Status=PluginStatus.READY,
            Current_Version=version,
            Executable_Path=installed_path,
        )
        db.session.add(plugin)
        db.session.flush()

        db.session.add(PluginVersion(
            PluginID=plugin.PluginID,
            Version=version or "1.0.0",
            Executable_Path=installed_path,
            Checksum=checksum,
            Is_Current=True,
        ))

        db.session.add(PluginCommand(
            PluginID=plugin.PluginID,
            Command_Name=command_name,
            Command_Definition=command_definition,
            Is_Default=True,
        ))

        for dep in dependencies:
            db.session.add(PluginDependency(
                PluginID=plugin.PluginID,
                Dependency_Name=dep["name"],
                Dependency_Type=DependencyType(dep["type"]),
                Required_Version=dep.get("required_version"),
                Status=DependencyStatus.OK,
            ))

        record_plugin_action(
            plugin, PluginHistoryAction.INSTALL, PluginActionResult.SUCCESS, user_id,
            new_value=version, message=f"Custom plugin '{name}' registered.",
        )
        db.session.commit()

        return {
            "success": True,
            "checks": serialize_custom_plugin_checks(result["checks"]),
            "plugin": serialize_plugin_summary_row(plugin),
            "message": f"Custom plugin '{name}' registered successfully.",
        }

    except Exception:
        db.session.rollback()
        raise
    finally:
        cleanup_staging(staging_dir)


# ==========================================================
# UPDATES (Phase 9)
# ==========================================================

class NoExecutableError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def set_current_plugin_version(plugin, version, executable_path):
    """
    Marks `version` as the current PluginVersion for this plugin,
    updating Plugin.Current_Version to match. Reused by both a
    successful update and a rollback — rollback in particular
    routinely restores a version that already has a historical
    PluginVersion row from before it was originally superseded, so
    blindly inserting a new row would collide with PluginVersion's
    (PluginID, Version) uniqueness constraint. This checks for an
    existing row first and reactivates it instead of inserting a
    duplicate.

    version=None (extract_version couldn't determine it) is stored as
    the literal string "unknown" for the PluginVersion row (the
    column is NOT NULL), but Plugin.Current_Version is deliberately
    left at its PREVIOUS value in that case rather than overwritten
    with "unknown" — we know the file on disk changed, but not to
    what, so leaving the last known-good version displayed is more
    useful than replacing it with a placeholder.
    """
    version_label = version or "unknown"

    existing_current = db.session.scalar(
        sa.select(PluginVersion).where(
            PluginVersion.PluginID == plugin.PluginID, PluginVersion.Is_Current.is_(True)
        )
    )
    if existing_current and existing_current.Version == version_label:
        return  # already current with this exact version

    if existing_current:
        existing_current.Is_Current = False
        existing_current.Removed_At = datetime.now(timezone.utc)

    existing_for_version = db.session.scalar(
        sa.select(PluginVersion).where(
            PluginVersion.PluginID == plugin.PluginID, PluginVersion.Version == version_label
        )
    )
    if existing_for_version:
        existing_for_version.Is_Current = True
        existing_for_version.Executable_Path = executable_path
        existing_for_version.Removed_At = None
    else:
        db.session.add(PluginVersion(
            PluginID=plugin.PluginID,
            Version=version_label,
            Executable_Path=executable_path,
            Is_Current=True,
        ))

    if version:
        plugin.Current_Version = version


def start_plugin_update(plugin_id, user_id, file_storage=None, url=None):
    """
    Full Phase 9 workflow (Implementation Plan Section 18): receive
    archive -> extract -> identify selected plugin -> backup current
    -> replace -> validate -> Nagios config check -> apply, OR leave
    in a failed-but-recoverable state for manual rollback.

    Confirmed design: rollback is NOT automatic on failure (see
    rollback_plugin_update()) — a failed update sets
    Status=ROLLBACK and stops there. "Individual extracted plugins
    are the managed units" (Phase 9's IMPORTANT note): only the ONE
    file matching plugin.Name is ever installed, regardless of what
    else the archive contains.

    Raises:
        PluginNotFoundError, InvalidTransitionError, NoExecutableError,
        InvalidUrlError, DownloadError, ArchiveTooLargeError,
        UnsupportedArchiveError, UnsafeArchiveError, PluginNotInArchiveError
    """
    plugin = db.session.get(Plugin, plugin_id)
    if plugin is None:
        raise PluginNotFoundError()

    if plugin.Status in BLOCKED_TRANSITION_STATUSES:
        raise InvalidTransitionError(f"Cannot update a plugin in '{plugin.Status.value}' state.")

    if not plugin.Executable_Path or not os.path.exists(plugin.Executable_Path):
        raise NoExecutableError("Plugin has no installed executable to update.")

    archive_path, staging_dir = receive_archive(file_storage=file_storage, url=url)

    try:
        extract_dir = os.path.join(staging_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        extract_archive(archive_path, extract_dir)

        new_file_path = find_plugin_in_extracted(extract_dir, plugin.Name)

        old_version = plugin.Current_Version
        old_status = plugin.Status.value

        backup_plugin(plugin.Name, plugin.Executable_Path)
        replace_plugin(new_file_path, plugin.Executable_Path)

        validation_result = validate_plugin_executable(plugin.Executable_Path)
        nagios_valid, nagios_output = validate_nagios_configuration()

        if not validation_result["is_valid"] or not nagios_valid:
            failed_step = "plugin validation" if not validation_result["is_valid"] else "Nagios configuration check"
            plugin.Status = PluginStatus.ROLLBACK

            record_plugin_action(
                plugin, PluginHistoryAction.UPDATE, PluginActionResult.FAILED, user_id,
                old_value=old_version, new_value=None,
                message=f"Update failed at {failed_step}. Backup available for rollback.",
            )
            db.session.commit()

            return {
                "success": False,
                "plugin_id": plugin.PluginID,
                "status": plugin.Status.value,
                "rollback_available": True,
                "failed_step": failed_step,
                "validation": validation_result,
                "nagios_check": {"passed": nagios_valid, "output": nagios_output},
            }

        new_version, _ = extract_version(plugin.Executable_Path)

        set_current_plugin_version(plugin, new_version, plugin.Executable_Path)

        # Preserve the prior status unless it was specifically
        # UPDATE_AVAILABLE (matches Phase 7's "don't downgrade
        # ENABLED/ACTIVE" precedent — a successful update on an
        # already-enabled plugin should stay enabled, not reset).
        if plugin.Status == PluginStatus.UPDATE_AVAILABLE:
            plugin.Status = PluginStatus.READY

        record_plugin_action(
            plugin, PluginHistoryAction.UPDATE, PluginActionResult.SUCCESS, user_id,
            old_value=old_version, new_value=new_version,
        )
        db.session.commit()

        return {
            "success": True,
            "plugin_id": plugin.PluginID,
            "status": plugin.Status.value,
            "previous_version": old_version,
            "current_version": new_version,
            "rollback_available": True,
        }

    except Exception:
        db.session.rollback()
        raise
    finally:
        cleanup_update_staging(staging_dir)


def rollback_plugin_update(plugin_id, user_id):
    """
    Manual rollback (UI Flow Section 23's [Rollback] button — confirmed
    NOT automatic). Restores the single backed-up file over whatever
    is currently installed, and records a new "current" PluginVersion
    for the restored version.

    Raises:
        PluginNotFoundError, NoExecutableError, NoBackupAvailableError
    """
    plugin = db.session.get(Plugin, plugin_id)
    if plugin is None:
        raise PluginNotFoundError()

    if not plugin.Executable_Path:
        raise NoExecutableError("Plugin has no installed executable path recorded.")

    if not has_backup(plugin.Name):
        raise NoBackupAvailableError(f"No backup is available for '{plugin.Name}'.")

    old_version = plugin.Current_Version

    restore_from_backup(plugin.Name, plugin.Executable_Path)

    restored_version, _ = extract_version(plugin.Executable_Path)

    set_current_plugin_version(plugin, restored_version, plugin.Executable_Path)
    plugin.Status = PluginStatus.READY

    record_plugin_action(
        plugin, PluginHistoryAction.ROLLBACK, PluginActionResult.SUCCESS, user_id,
        old_value=old_version, new_value=restored_version,
    )
    db.session.commit()

    return {
        "success": True,
        "plugin_id": plugin.PluginID,
        "status": plugin.Status.value,
        "restored_version": restored_version,
    }


# ==========================================================
# MONITORING CONFIGURATION (Phase 10)
# ==========================================================

class TargetNotFoundError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class NoCommandDefinedError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class ConfigurationNotFoundError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def get_active_command_line(plugin_id):
    """
    Resolves the effective command line for a plugin: an active
    override if one exists (Phase 6), otherwise the default command
    (Phase 1). Reused by Phase 10 to know what a target's generated
    Nagios `command` object should actually run.

    Returns:
        (command_line: str | None, command: PluginCommand | None)
    """
    default_command = db.session.scalar(
        sa.select(PluginCommand).where(
            PluginCommand.PluginID == plugin_id, PluginCommand.Is_Default.is_(True),
        )
    )
    if default_command is None:
        return None, None

    active_override = db.session.scalar(
        sa.select(PluginCommandOverride).where(
            PluginCommandOverride.PluginCommandID == default_command.PluginCommandID,
            PluginCommandOverride.Is_Active.is_(True),
        )
    )
    command_line = active_override.Override_Command if active_override else default_command.Command_Definition
    return command_line, default_command


def build_configuration_tuples(configurations):
    """
    Resolves each PluginConfiguration row into the
    (host_name, service_description, command_name, command_line)
    tuple generate_plugin_services_cfg() needs, skipping any row
    whose plugin/target/command can no longer be resolved (e.g. the
    plugin or target was deleted after this configuration was
    applied) rather than letting one bad row break the whole rebuild.
    """
    tuples = []
    for config in configurations:
        plugin = db.session.get(Plugin, config.PluginID)
        target = db.session.get(NetworkDiscovery, config.NetDiscoveryID)
        if plugin is None or target is None:
            continue

        command_line, _ = get_active_command_line(config.PluginID)
        if not command_line:
            continue

        tuples.append((
            target.Hostname or target.IP_Address,
            config.Service_Description,
            generate_command_name(plugin.Name),
            command_line,
        ))
    return tuples


def get_configuration_targets():
    """
    List the discovered devices a plugin can be applied to, sorted by
    hostname then IP. Only devices still included in scanning are
    returned, since excluded devices are not monitored by Nagios.
    Backs the target picker for POST /plugin/<id>/configurations.
    """
    devices = db.session.scalars(
        sa.select(NetworkDiscovery)
        .where(NetworkDiscovery.Include_Device_In_Scanning.is_(True))
        .order_by(NetworkDiscovery.Hostname.asc(), NetworkDiscovery.IP_Address.asc())
    ).all()

    result = []
    for device in devices:
        result.append({
            "id": device.NetDiscoveryID,
            "hostname": device.Hostname,
            "ip_address": device.IP_Address,
        })
    return result


def get_plugin_configurations(plugin_id):
    """GET /plugin/<id>/configurations — list this plugin's applied/pending/failed targets."""
    configs = db.session.scalars(
        sa.select(PluginConfiguration).where(PluginConfiguration.PluginID == plugin_id)
    ).all()

    result = []
    for config in configs:
        target = db.session.get(NetworkDiscovery, config.NetDiscoveryID)
        result.append({
            "id": config.PluginConfigurationID,
            "target": {
                "id": target.NetDiscoveryID,
                "hostname": target.Hostname,
                "ip_address": target.IP_Address,
            } if target else None,
            "service_description": config.Service_Description,
            "status": config.Status.value,
            "configuration_data": config.Configuration_Data,
            "updated_at": config.Updated_At.isoformat(),
        })
    return result


def apply_plugin_configuration(plugin_id, net_discovery_id, service_description, user_id, configuration_data=None):
    """
    Full Phase 10 workflow (Implementation Plan Section 18):
    Administrator selects plugin capability -> selects target ->
    Plugin Manager generates/updates Nagios configuration -> validates
    it -> applies/reloads Nagios -> Nagios monitors target.

    Regenerates plugin-services.cfg from scratch each pass (all
    currently-Applied configurations, PLUS this one as a candidate) —
    matches Network Discovery's own established full-rebuild
    convention for its file, rather than incrementally patching.

    On success: this configuration's Status becomes APPLIED, and
    Plugin.Status becomes ACTIVE — the one thing in the entire Plugin
    Manager module that can set that status; every earlier phase
    stopped short of it deliberately.

    On failure: nothing live is touched (validation runs against a
    throwaway temp copy, never the real files) — this configuration's
    Status becomes FAILED and Plugin.Status is left alone.

    Raises:
        PluginNotFoundError, InvalidTransitionError, TargetNotFoundError,
        NoCommandDefinedError
    """
    plugin = db.session.get(Plugin, plugin_id)
    if plugin is None:
        raise PluginNotFoundError()

    if plugin.Status in BLOCKED_TRANSITION_STATUSES:
        raise InvalidTransitionError(
            f"Cannot apply monitoring configuration for a plugin in '{plugin.Status.value}' state."
        )

    target = db.session.get(NetworkDiscovery, net_discovery_id)
    if target is None:
        raise TargetNotFoundError(f"No target device with id {net_discovery_id}.")

    command_line, _ = get_active_command_line(plugin_id)
    if not command_line:
        raise NoCommandDefinedError(f"Plugin '{plugin.Name}' has no command definition.")

    existing_config = db.session.scalar(
        sa.select(PluginConfiguration).where(
            PluginConfiguration.PluginID == plugin_id,
            PluginConfiguration.NetDiscoveryID == net_discovery_id,
            PluginConfiguration.Service_Description == service_description,
        )
    )
    if existing_config:
        config = existing_config
        config.Configuration_Data = configuration_data
    else:
        config = PluginConfiguration(
            PluginID=plugin_id,
            NetDiscoveryID=net_discovery_id,
            Service_Description=service_description,
            Configuration_Data=configuration_data,
            Status=PluginConfigurationStatus.PENDING,
        )
        db.session.add(config)
    db.session.flush()

    already_applied = db.session.scalars(
        sa.select(PluginConfiguration).where(
            PluginConfiguration.Status == PluginConfigurationStatus.APPLIED,
            PluginConfiguration.PluginConfigurationID != config.PluginConfigurationID,
        )
    ).all()

    candidate_configs = list(already_applied) + [config]
    tuples = build_configuration_tuples(candidate_configs)

    cfg_contents = generate_plugin_services_cfg(tuples)
    staged_path = write_staged_cfg(cfg_contents)

    try:
        is_valid, output = validate_plugin_services_config(staged_path)

        if not is_valid:
            config.Status = PluginConfigurationStatus.FAILED
            record_plugin_action(
                plugin, PluginHistoryAction.CONFIGURE, PluginActionResult.FAILED, user_id,
                message=f"Monitoring configuration validation failed: {output[:500]}",
            )
            db.session.commit()
            return {
                "success": False,
                "configuration_id": config.PluginConfigurationID,
                "status": config.Status.value,
                "validation_output": output,
            }

        directive_ok = ensure_cfg_file_directive()
        if not directive_ok:
            config.Status = PluginConfigurationStatus.FAILED
            record_plugin_action(
                plugin, PluginHistoryAction.CONFIGURE, PluginActionResult.FAILED, user_id,
                message="Could not ensure plugin-services.cfg is referenced by nagios.cfg.",
            )
            db.session.commit()
            return {
                "success": False,
                "configuration_id": config.PluginConfigurationID,
                "status": config.Status.value,
                "validation_output": "Failed to update nagios.cfg's cfg_file directives.",
            }

        applied, apply_message = apply_plugin_services_config(staged_path)

        if not applied:
            config.Status = PluginConfigurationStatus.FAILED
            record_plugin_action(
                plugin, PluginHistoryAction.CONFIGURE, PluginActionResult.FAILED, user_id,
                message=apply_message,
            )
            db.session.commit()
            return {
                "success": False,
                "configuration_id": config.PluginConfigurationID,
                "status": config.Status.value,
                "validation_output": apply_message,
            }

        config.Status = PluginConfigurationStatus.APPLIED
        plugin.Status = PluginStatus.ACTIVE

        record_plugin_action(
            plugin, PluginHistoryAction.CONFIGURE, PluginActionResult.SUCCESS, user_id,
            new_value=service_description,
            message=f"Applied to {target.Hostname or target.IP_Address}: {service_description}.",
        )
        db.session.commit()

        return {
            "success": True,
            "configuration_id": config.PluginConfigurationID,
            "status": config.Status.value,
            "plugin_status": plugin.Status.value,
        }

    finally:
        staged_path.unlink(missing_ok=True)
