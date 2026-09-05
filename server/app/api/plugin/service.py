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
    Plugin, PluginType, PluginStatus,
    PluginCommand, PluginCommandOverride,
    PluginDependency,
    PluginHistory,
)
from app.system_models import ActivityLog, User


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


def _serialize_plugin_summary_row(plugin):
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

    items = [_serialize_plugin_summary_row(p) for p in result.items]

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

    items = []
    for command in commands:
        active_override = db.session.scalar(
            sa.select(PluginCommandOverride)
            .where(
                PluginCommandOverride.PluginCommandID == command.PluginCommandID,
                PluginCommandOverride.Is_Active.is_(True),
            )
            .order_by(PluginCommandOverride.Created_At.desc())
        )

        items.append({
            "id": command.PluginCommandID,
            "command_name": command.Command_Name,
            "default_command": command.Command_Definition,
            "active_command": (
                active_override.Override_Command if active_override else command.Command_Definition
            ),
            "is_overridden": active_override is not None,
            "is_default": command.Is_Default,
        })

    return items


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
