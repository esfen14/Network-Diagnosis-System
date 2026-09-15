from datetime import datetime, timezone

from flask import request, current_app
from flask_login import login_required, current_user
import sqlalchemy as sa

from app import db
from app.system_models import (
    ActivityLog,
    ConfigurationChanges,
    NetworkDiscoveryStatus,
    NCPADeploymentStatus,
    ExportLog,
    ExportFormat,
    User
)
from app.api.helper import success, error
from app.api.helper.database_access.permissions import require_permission
from app.api.system import system_bp
from app.logging.export_logs import create_export_log


class _ManualPagination:

    def __init__(self, items, page, per_page, total):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total
        self.pages = max(1, (total + per_page - 1) // per_page) if per_page else 1
        self.has_next = page < self.pages
        self.has_prev = page > 1


def _paginate_multi(query, page, per_page):
    total = db.session.scalar(
        sa.select(sa.func.count()).select_from(query.subquery())
    ) or 0
    offset = (page - 1) * per_page
    rows = db.session.execute(query.limit(per_page).offset(offset)).all()
    return _ManualPagination(rows, page, per_page, total)


# ==========================================================
# ACTIVITY LOG
# ==========================================================

@system_bp.get('/log')
@login_required
@require_permission("system.logs")
def activity_logs():
    """Retrieve paginated user activity logs.

    Queries the ``ActivityLog`` table joined with ``User`` to produce a
    chronological feed of user actions such as logins, logouts, and
    configuration modifications.

    **Query Parameters**

    page (int, default 1):
        Page number (1-based).
    per_page (int, default 10, max 100):
        Number of items per page.
    sort_by (str, default "performed_at"):
        Column to sort by. Allowed values: ``id``, ``action_type``,
        ``performed_at``.
    order (str, default "desc"):
        Sort direction. Allowed values: ``asc``, ``desc``.
    search (str, default ""):
        Free-text filter matched against ``Action_Type``, user first name,
        last name, and email.
    start_date (str, default "", format YYYY-MM-DD):
        Inclusive start of date range filter on ``Performed_At``.
    end_date (str, default "", format YYYY-MM-DD):
        Inclusive end of date range filter on ``Performed_At``.

    **Returns (JSON via ``success()``)**

    On success (HTTP 200):

    .. code-block:: json

        {
            "success": true,
            "data": {
                "items": [
                    {
                        "id":          1,
                        "category":    "activity",
                        "type":        "account",
                        "title":       "User Login",
                        "user":        "John Doe",
                        "description": "User Login",
                        "timestamp":   "2025-01-15T10:30:00",
                        "tagId":       "AL-0001"
                    }
                ],
                "page":     1,
                "per_page": 10,
                "pages":    5,
                "total":    42,
                "has_next": true,
                "has_prev": false
            }
        }

    On error:

    * ``400`` – invalid sort field, page < 1, or per_page out of range.
    * ``500`` – unexpected internal error (logged with traceback).
    """
    try:
        page     = request.args.get("page",     default=1,    type=int)
        per_page = request.args.get("per_page", default=10,   type=int)
        sort_by  = request.args.get("sort_by",  default="performed_at", type=str)
        order    = request.args.get("order",    default="desc", type=str)
        search   = request.args.get("search",   default="",   type=str)
        start_date = request.args.get("start_date", default="", type=str)
        end_date   = request.args.get("end_date",   default="", type=str)

        allowed_sorts = {
            "id":           ActivityLog.LogID,
            "action_type":  ActivityLog.Action_Type,
            "performed_at": ActivityLog.Performed_At,
        }
        sort_column = allowed_sorts.get(sort_by)

        if sort_column is None:
            return error("Invalid sort field", 400)
        if page < 1:
            return error("Page must be greater than 0", 400)
        if per_page < 1 or per_page > 100:
            return error("per_page must be between 1 and 100", 400)

        # Every specialized log category (config change, discovery, NCPA
        # deployment, export) also writes a generic ActivityLog row to hang
        # its details off of — that's how ConfigurationChanges.LogID etc.
        # link back to a user/timestamp. Without this exclusion, each of
        # those events would show up twice: once here as a generic entry,
        # and once under its own specialized tab. Activity Log should only
        # surface genuinely generic actions (logins, account changes, etc).
        query = (
            sa.select(ActivityLog, User)
            .join(User, User.UserID == ActivityLog.UserID)
            .where(
                ~sa.exists(sa.select(1).where(ConfigurationChanges.LogID == ActivityLog.LogID)),
                ~sa.exists(sa.select(1).where(NetworkDiscoveryStatus.LogID == ActivityLog.LogID)),
                ~sa.exists(sa.select(1).where(NCPADeploymentStatus.LogID == ActivityLog.LogID)),
                ~sa.exists(sa.select(1).where(ExportLog.LogID == ActivityLog.LogID)),
            )
        )

        if search:
            query = query.where(
                sa.or_(
                    ActivityLog.Action_Type.ilike(f"%{search}%"),
                    User.First_Name.ilike(f"%{search}%"),
                    User.Last_Name.ilike(f"%{search}%"),
                    User.Email.ilike(f"%{search}%"),
                )
            )

        if start_date:
            query = query.where(
                sa.cast(ActivityLog.Performed_At, sa.Date) >= start_date
            )
        if end_date:
            query = query.where(
                sa.cast(ActivityLog.Performed_At, sa.Date) <= end_date
            )

        if order == "desc":
            query = query.order_by(sort_column.desc())
        elif order == "asc":
            query = query.order_by(sort_column.asc())
        else:
            return error("Invalid order.", 400)

        logs = _paginate_multi(query, page, per_page)

        items = []
        for activity, user in logs.items:
            items.append({
                "id":          activity.LogID,
                "category":    "activity",
                "type":        "account",
                "title":       activity.Action_Type,
                "user":        f"{user.First_Name} {user.Last_Name}",
                "description": activity.Action_Type,
                "timestamp":   activity.Performed_At.isoformat(),
                "tagId":       f"AL-{activity.LogID:04d}",
            })

        return success({
            "items":    items,
            "page":     logs.page,
            "per_page": logs.per_page,
            "pages":    logs.pages,
            "total":    logs.total,
            "has_next": logs.has_next,
            "has_prev": logs.has_prev,
        })

    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while retrieving activity logs."
        )
        return error("An unexpected error occurred.", 500)


# ==========================================================
# CONFIGURATION CHANGE
# ==========================================================

@system_bp.get('/configurationchange')
@login_required
@require_permission("system.logs")
def configuration_change_logs():
    """Retrieve paginated configuration change logs.

    Queries the ``ConfigurationChanges`` table joined with ``ActivityLog``
    and ``User`` to produce an audit trail of parameter-level configuration
    updates, including old and new values.

    **Query Parameters**

    page (int, default 1):
        Page number (1-based).
    per_page (int, default 10, max 100):
        Number of items per page.
    sort_by (str, default "changed_at"):
        Column to sort by. Allowed values: ``id``, ``type``,
        ``parameter``, ``changed_at``.
    order (str, default "desc"):
        Sort direction. Allowed values: ``asc``, ``desc``.
    search (str, default ""):
        Free-text filter matched against ``Conf_Type``, ``Parameter_Name``,
        ``Old_Value``, ``New_Value``, and user names.
    start_date (str, default "", format YYYY-MM-DD):
        Inclusive start of date range on ``Changed_At``.
    end_date (str, default "", format YYYY-MM-DD):
        Inclusive end of date range on ``Changed_At``.

    **Returns (JSON via ``success()``)**

    On success (HTTP 200):

    .. code-block:: json

        {
            "success": true,
            "data": {
                "items": [
                    {
                        "id":          1,
                        "category":    "configurationChange",
                        "type":        "configuration",
                        "title":       "Configuration Updated",
                        "user":        "John Doe",
                        "description": "timeout changed from '30' to '60'.",
                        "timestamp":   "2025-01-15T10:30:00",
                        "tagId":       "CC-0001",
                        "details": {
                            "configuration_type": "network",
                            "parameter_name":     "timeout",
                            "old_value":          "30",
                            "new_value":          "60",
                            "log_id":             1
                        }
                    }
                ],
                "page":     1,
                "per_page": 10,
                "pages":    5,
                "total":    42,
                "has_next": true,
                "has_prev": false
            }
        }

    On error:

    * ``400`` – invalid sort field, page < 1, or per_page out of range.
    * ``500`` – unexpected internal error (logged with traceback).
    """
    try:
        page     = request.args.get("page",     default=1,    type=int)
        per_page = request.args.get("per_page", default=10,   type=int)
        sort_by  = request.args.get("sort_by",  default="changed_at", type=str)
        order    = request.args.get("order",    default="desc", type=str)
        search   = request.args.get("search",   default="",   type=str)
        start_date = request.args.get("start_date", default="", type=str)
        end_date   = request.args.get("end_date",   default="", type=str)

        allowed_sorts = {
            "id":        ConfigurationChanges.ConfChangesID,
            "type":      ConfigurationChanges.Conf_Type,
            "parameter": ConfigurationChanges.Parameter_Name,
            "changed_at": ConfigurationChanges.Changed_At,
        }
        sort_column = allowed_sorts.get(sort_by)

        if sort_column is None:
            return error("Invalid sort field", 400)
        if page < 1:
            return error("Page must be greater than 0", 400)
        if per_page < 1 or per_page > 100:
            return error("per_page must be between 1 and 100", 400)

        query = (
            sa.select(ConfigurationChanges, ActivityLog, User)
            .join(ActivityLog, ActivityLog.LogID == ConfigurationChanges.LogID)
            .join(User, User.UserID == ActivityLog.UserID)
        )

        if search:
            query = query.where(
                sa.or_(
                    ConfigurationChanges.Conf_Type.ilike(f"%{search}%"),
                    ConfigurationChanges.Parameter_Name.ilike(f"%{search}%"),
                    ConfigurationChanges.Old_Value.ilike(f"%{search}%"),
                    ConfigurationChanges.New_Value.ilike(f"%{search}%"),
                    User.First_Name.ilike(f"%{search}%"),
                    User.Last_Name.ilike(f"%{search}%"),
                )
            )

        if start_date:
            query = query.where(
                sa.cast(ConfigurationChanges.Changed_At, sa.Date) >= start_date
            )
        if end_date:
            query = query.where(
                sa.cast(ConfigurationChanges.Changed_At, sa.Date) <= end_date
            )

        if order == "desc":
            query = query.order_by(sort_column.desc())
        elif order == "asc":
            query = query.order_by(sort_column.asc())
        else:
            return error("Invalid order.", 400)

        logs = _paginate_multi(query, page, per_page)

        items = []
        for config, activity, user in logs.items:
            items.append({
                "id":          config.ConfChangesID,
                "category":    "configurationChange",
                "type":        "configuration",
                "title":       "Configuration Updated",
                "user":        f"{user.First_Name} {user.Last_Name}",
                "description": (
                    f"{config.Parameter_Name} changed "
                    f"from '{config.Old_Value}' to '{config.New_Value}'."
                ),
                "timestamp":   config.Changed_At.isoformat(),
                "tagId":       f"CC-{config.ConfChangesID:04d}",
                "details": {
                    "configuration_type": config.Conf_Type,
                    "parameter_name":     config.Parameter_Name,
                    "old_value":          config.Old_Value,
                    "new_value":          config.New_Value,
                    "log_id":             config.LogID,
                },
            })

        return success({
            "items":    items,
            "page":     logs.page,
            "per_page": logs.per_page,
            "pages":    logs.pages,
            "total":    logs.total,
            "has_next": logs.has_next,
            "has_prev": logs.has_prev,
        })

    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while retrieving configuration logs."
        )
        return error("An unexpected error occurred.", 500)


# ==========================================================
# NETWORK DISCOVERY
# ==========================================================

@system_bp.get('/networkdiscovery')
@login_required
@require_permission("system.logs")
def network_discovery_logs():
    """Retrieve paginated network discovery status logs.

    Queries the ``NetworkDiscoveryStatus`` table joined with
    ``ActivityLog`` and ``User`` to track the lifecycle of network
    discovery scans (queued, running, completed, failed).

    **Query Parameters**

    page (int, default 1):
        Page number (1-based).
    per_page (int, default 10, max 100):
        Number of items per page.
    sort_by (str, default "start_at"):
        Column to sort by. Allowed values: ``id``, ``status``,
        ``progress``, ``start_at``, ``completed_at``.
    order (str, default "desc"):
        Sort direction. Allowed values: ``asc``, ``desc``.
    search (str, default ""):
        Free-text filter matched against ``Message``, ``Error``, and user
        names.
    start_date (str, default "", format YYYY-MM-DD):
        Inclusive start of date range on ``Start_At``.
    end_date (str, default "", format YYYY-MM-DD):
        Inclusive end of date range on ``Start_At``.

    **Returns (JSON via ``success()``)**

    On success (HTTP 200):

    .. code-block:: json

        {
            "success": true,
            "data": {
                "items": [
                    {
                        "id":          1,
                        "category":    "networkDiscovery",
                        "type":        "network",
                        "title":       "Network Discovery",
                        "user":        "John Doe",
                        "description": "Discovery scan completed successfully",
                        "timestamp":   "2025-01-15T10:30:00",
                        "tagId":       "ND-0001",
                        "details": {
                            "status":       "completed",
                            "progress":     100,
                            "message":      "Discovery scan completed successfully",
                            "start_at":     "2025-01-15T10:00:00",
                            "completed_at": "2025-01-15T10:30:00",
                            "error":        null,
                            "log_id":       1
                        }
                    }
                ],
                "page":     1,
                "per_page": 10,
                "pages":    5,
                "total":    42,
                "has_next": true,
                "has_prev": false
            }
        }

    On error:

    * ``400`` – invalid sort field, page < 1, or per_page out of range.
    * ``500`` – unexpected internal error (logged with traceback).
    """
    try:
        page     = request.args.get("page",     default=1,    type=int)
        per_page = request.args.get("per_page", default=10,   type=int)
        sort_by  = request.args.get("sort_by",  default="start_at", type=str)
        order    = request.args.get("order",    default="desc", type=str)
        search   = request.args.get("search",   default="",   type=str)
        start_date = request.args.get("start_date", default="", type=str)
        end_date   = request.args.get("end_date",   default="", type=str)

        allowed_sorts = {
            "id":           NetworkDiscoveryStatus.DiscoveryStatusID,
            "status":       NetworkDiscoveryStatus.Status,
            "progress":     NetworkDiscoveryStatus.Progress,
            "start_at":     NetworkDiscoveryStatus.Start_At,
            "completed_at": NetworkDiscoveryStatus.Completed_At,
        }
        sort_column = allowed_sorts.get(sort_by)

        if sort_column is None:
            return error("Invalid sort field", 400)
        if page < 1:
            return error("Page must be greater than 0", 400)
        if per_page < 1 or per_page > 100:
            return error("per_page must be between 1 and 100", 400)

        query = (
            sa.select(NetworkDiscoveryStatus, ActivityLog, User)
            .join(ActivityLog, ActivityLog.LogID == NetworkDiscoveryStatus.LogID)
            .join(User, User.UserID == ActivityLog.UserID)
        )

        if search:
            query = query.where(
                sa.or_(
                    NetworkDiscoveryStatus.Message.ilike(f"%{search}%"),
                    NetworkDiscoveryStatus.Error.ilike(f"%{search}%"),
                    User.First_Name.ilike(f"%{search}%"),
                    User.Last_Name.ilike(f"%{search}%"),
                )
            )

        if start_date:
            query = query.where(
                sa.cast(NetworkDiscoveryStatus.Start_At, sa.Date) >= start_date
            )
        if end_date:
            query = query.where(
                sa.cast(NetworkDiscoveryStatus.Start_At, sa.Date) <= end_date
            )

        if order == "desc":
            query = query.order_by(sort_column.desc())
        elif order == "asc":
            query = query.order_by(sort_column.asc())
        else:
            return error("Invalid order.", 400)

        logs = _paginate_multi(query, page, per_page)

        items = []
        for discovery, activity, user in logs.items:
            status = discovery.Status.value if discovery.Status else "Unknown"
            items.append({
                "id":          discovery.DiscoveryStatusID,
                "category":    "networkDiscovery",
                "type":        "network",
                "title":       "Network Discovery",
                "user":        f"{user.First_Name} {user.Last_Name}",
                "description": discovery.Message,
                "timestamp":   discovery.Start_At.isoformat(),
                "tagId":       f"ND-{discovery.DiscoveryStatusID:04d}",
                "details": {
                    "status":       status,
                    "progress":     discovery.Progress,
                    "message":      discovery.Message,
                    "start_at":     discovery.Start_At.isoformat() if discovery.Start_At else None,
                    "completed_at": discovery.Completed_At.isoformat() if discovery.Completed_At else None,
                    "error":        discovery.Error,
                    "log_id":       discovery.LogID,
                },
            })

        return success({
            "items":    items,
            "page":     logs.page,
            "per_page": logs.per_page,
            "pages":    logs.pages,
            "total":    logs.total,
            "has_next": logs.has_next,
            "has_prev": logs.has_prev,
        })

    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while retrieving network discovery logs."
        )
        return error("An unexpected error occurred.", 500)


# ==========================================================
# NCPA DEPLOYMENT
# ==========================================================

@system_bp.get('/ncpadeployment')
@login_required
@require_permission("system.logs")
def ncpa_deployment_logs():
    """Retrieve paginated NCPA deployment status logs.

    Queries the ``NCPADeploymentStatus`` table joined with ``ActivityLog``
    and ``User`` to track the lifecycle of NCPA agent deployments
    (queued, running, completed, failed).

    **Query Parameters**

    page (int, default 1):
        Page number (1-based).
    per_page (int, default 10, max 100):
        Number of items per page.
    sort_by (str, default "start_at"):
        Column to sort by. Allowed values: ``id``, ``status``,
        ``progress``, ``start_at``, ``completed_at``.
    order (str, default "desc"):
        Sort direction. Allowed values: ``asc``, ``desc``.
    search (str, default ""):
        Free-text filter matched against ``Message``, ``Error``, and user
        names.
    start_date (str, default "", format YYYY-MM-DD):
        Inclusive start of date range on ``Start_At``.
    end_date (str, default "", format YYYY-MM-DD):
        Inclusive end of date range on ``Start_At``.

    **Returns (JSON via ``success()``)**

    On success (HTTP 200):

    .. code-block:: json

        {
            "success": true,
            "data": {
                "items": [
                    {
                        "id":          1,
                        "category":    "ncpaDeployment",
                        "type":        "deployment",
                        "title":       "NCPA Deployment",
                        "user":        "John Doe",
                        "description": "Deployment completed successfully",
                        "timestamp":   "2025-01-15T10:30:00",
                        "tagId":       "NP-0001",
                        "details": {
                            "status":       "completed",
                            "progress":     100,
                            "message":      "Deployment completed successfully",
                            "start_at":     "2025-01-15T10:00:00",
                            "completed_at": "2025-01-15T10:30:00",
                            "error":        null,
                            "log_id":       1
                        }
                    }
                ],
                "page":     1,
                "per_page": 10,
                "pages":    5,
                "total":    42,
                "has_next": true,
                "has_prev": false
            }
        }

    On error:

    * ``400`` – invalid sort field, page < 1, or per_page out of range.
    * ``500`` – unexpected internal error (logged with traceback).
    """
    try:
        page     = request.args.get("page",     default=1,    type=int)
        per_page = request.args.get("per_page", default=10,   type=int)
        sort_by  = request.args.get("sort_by",  default="start_at", type=str)
        order    = request.args.get("order",    default="desc", type=str)
        search   = request.args.get("search",   default="",   type=str)
        start_date = request.args.get("start_date", default="", type=str)
        end_date   = request.args.get("end_date",   default="", type=str)

        allowed_sorts = {
            "id":           NCPADeploymentStatus.NCPADeployStatusID,
            "status":       NCPADeploymentStatus.Status,
            "progress":     NCPADeploymentStatus.Progress,
            "start_at":     NCPADeploymentStatus.Start_At,
            "completed_at": NCPADeploymentStatus.Completed_At,
        }
        sort_column = allowed_sorts.get(sort_by)

        if sort_column is None:
            return error("Invalid sort field", 400)
        if page < 1:
            return error("Page must be greater than 0", 400)
        if per_page < 1 or per_page > 100:
            return error("per_page must be between 1 and 100", 400)

        query = (
            sa.select(NCPADeploymentStatus, ActivityLog, User)
            .join(ActivityLog, ActivityLog.LogID == NCPADeploymentStatus.LogID)
            .join(User, User.UserID == ActivityLog.UserID)
        )

        if search:
            query = query.where(
                sa.or_(
                    NCPADeploymentStatus.Message.ilike(f"%{search}%"),
                    NCPADeploymentStatus.Error.ilike(f"%{search}%"),
                    User.First_Name.ilike(f"%{search}%"),
                    User.Last_Name.ilike(f"%{search}%"),
                )
            )

        if start_date:
            query = query.where(
                sa.cast(NCPADeploymentStatus.Start_At, sa.Date) >= start_date
            )
        if end_date:
            query = query.where(
                sa.cast(NCPADeploymentStatus.Start_At, sa.Date) <= end_date
            )

        if order == "desc":
            query = query.order_by(sort_column.desc())
        elif order == "asc":
            query = query.order_by(sort_column.asc())
        else:
            return error("Invalid order.", 400)

        logs = _paginate_multi(query, page, per_page)

        items = []
        for deployment, activity, user in logs.items:
            status = deployment.Status.value if deployment.Status else "Unknown"
            items.append({
                "id":          deployment.NCPADeployStatusID,
                "category":    "ncpaDeployment",
                "type":        "deployment",
                "title":       "NCPA Deployment",
                "user":        f"{user.First_Name} {user.Last_Name}",
                "description": deployment.Message,
                "timestamp":   deployment.Start_At.isoformat(),
                "tagId":       f"NP-{deployment.NCPADeployStatusID:04d}",
                "details": {
                    "status":       status,
                    "progress":     deployment.Progress,
                    "message":      deployment.Message,
                    "start_at":     deployment.Start_At.isoformat() if deployment.Start_At else None,
                    "completed_at": deployment.Completed_At.isoformat() if deployment.Completed_At else None,
                    "error":        deployment.Error,
                    "log_id":       deployment.LogID,
                },
            })

        return success({
            "items":    items,
            "page":     logs.page,
            "per_page": logs.per_page,
            "pages":    logs.pages,
            "total":    logs.total,
            "has_next": logs.has_next,
            "has_prev": logs.has_prev,
        })

    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while retrieving NCPA deployment logs."
        )
        return error("An unexpected error occurred.", 500)


# ==========================================================
# EXPORT LOG
# ==========================================================

@system_bp.post('/exportlog')
@login_required
def record_export():
    """Record that the current user exported data from a page.

    Exports are generated entirely client-side (CSV/XLS/PDF built in the
    browser, no server round-trip for the file itself) — this endpoint
    just records that it happened, for the Export Log audit trail.

    Request body (JSON):
    {
        "report_type": str,           // e.g. "host-availability", "accounts"
        "format":      "CSV"|"PDF"|"XLS",
        "start_date":  str, optional  // ISO-8601, defaults to now
        "end_date":    str, optional  // ISO-8601, defaults to now
    }

    Only requires being logged in — exporting data you can already see
    doesn't need a separate permission grant.
    """
    try:
        body = request.get_json(silent=True) or {}
        report_type = (body.get("report_type") or "").strip()
        export_format = (body.get("format") or "").strip().upper()

        if not report_type:
            return error("report_type is required.", 400)

        try:
            format_enum = ExportFormat[export_format]
        except KeyError:
            return error(
                f"Invalid format. Valid values: {', '.join(f.name for f in ExportFormat)}",
                400,
            )

        def _parse_date(value):
            if not value:
                return datetime.now(timezone.utc)
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return datetime.now(timezone.utc)

        start_date = _parse_date(body.get("start_date"))
        end_date = _parse_date(body.get("end_date"))

        create_export_log(current_user.UserID, report_type, format_enum, start_date, end_date)
        db.session.commit()

        return success(message="Export recorded.", status=201)

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "An unexpected error occurred while recording an export."
        )
        return error("An unexpected error occurred.", 500)


@system_bp.get('/exportlog')
@login_required
@require_permission("system.logs")
def export_logs():
    """Retrieve paginated system log export history.

    Queries the ``ExportLog`` table joined with ``ActivityLog`` and ``User``
    to track when and how system reports were exported (PDF, CSV, etc.).

    **Query Parameters**

    page (int, default 1):
        Page number (1-based).
    per_page (int, default 10, max 100):
        Number of items per page.
    sort_by (str, default "exported_at"):
        Column to sort by. Allowed values: ``id``, ``report_type``,
        ``format``, ``exported_at``.
    order (str, default "desc"):
        Sort direction. Allowed values: ``asc``, ``desc``.
    search (str, default ""):
        Free-text filter matched against ``Report_Type`` and user names
        / email.
    start_date (str, default "", format YYYY-MM-DD):
        Inclusive start of date range on ``Exported_At``.
    end_date (str, default "", format YYYY-MM-DD):
        Inclusive end of date range on ``Exported_At``.

    **Returns (JSON via ``success()``)**

    On success (HTTP 200):

    .. code-block:: json

        {
            "success": true,
            "data": {
                "items": [
                    {
                        "id":          1,
                        "category":    "exportLog",
                        "type":        "export",
                        "title":       "System Logs Exported",
                        "user":        "John Doe",
                        "description": "Exported network report as PDF.",
                        "timestamp":   "2025-01-15T10:30:00",
                        "tagId":       "EX-0001",
                        "details": {
                            "report_type": "network",
                            "format":      "pdf",
                            "start_date":  "2025-01-01",
                            "end_date":    "2025-01-15",
                            "exported_at": "2025-01-15T10:30:00",
                            "log_id":      1
                        }
                    }
                ],
                "page":     1,
                "per_page": 10,
                "pages":    5,
                "total":    42,
                "has_next": true,
                "has_prev": false
            }
        }

    On error:

    * ``400`` – invalid sort field, page < 1, or per_page out of range.
    * ``500`` – unexpected internal error (logged with traceback).
    """
    try:
        page     = request.args.get("page",     default=1,    type=int)
        per_page = request.args.get("per_page", default=10,   type=int)
        sort_by  = request.args.get("sort_by",  default="exported_at", type=str)
        order    = request.args.get("order",    default="desc", type=str)
        search   = request.args.get("search",   default="",   type=str)
        start_date = request.args.get("start_date", default="", type=str)
        end_date   = request.args.get("end_date",   default="", type=str)

        allowed_sorts = {
            "id":          ExportLog.ExportID,
            "report_type": ExportLog.Report_Type,
            "format":      ExportLog.Export_Format,
            "exported_at": ExportLog.Exported_At,
        }
        sort_column = allowed_sorts.get(sort_by)

        if sort_column is None:
            return error("Invalid sort field", 400)
        if page < 1:
            return error("Page must be greater than 0", 400)
        if per_page < 1 or per_page > 100:
            return error("per_page must be between 1 and 100", 400)

        query = (
            sa.select(ExportLog, ActivityLog, User)
            .join(ActivityLog, ActivityLog.LogID == ExportLog.LogID)
            .join(User, User.UserID == ActivityLog.UserID)
        )

        if search:
            query = query.where(
                sa.or_(
                    ExportLog.Report_Type.ilike(f"%{search}%"),
                    User.First_Name.ilike(f"%{search}%"),
                    User.Last_Name.ilike(f"%{search}%"),
                    User.Email.ilike(f"%{search}%"),
                )
            )

        if start_date:
            query = query.where(
                sa.cast(ExportLog.Exported_At, sa.Date) >= start_date
            )
        if end_date:
            query = query.where(
                sa.cast(ExportLog.Exported_At, sa.Date) <= end_date
            )

        if order == "desc":
            query = query.order_by(sort_column.desc())
        elif order == "asc":
            query = query.order_by(sort_column.asc())
        else:
            return error("Invalid order.", 400)

        logs = _paginate_multi(query, page, per_page)

        items = []
        for export, activity, user in logs.items:
            export_format = export.Export_Format.value if export.Export_Format else "Unknown"
            items.append({
                "id":          export.ExportID,
                "category":    "exportLog",
                "type":        "export",
                "title":       "System Logs Exported",
                "user":        f"{user.First_Name} {user.Last_Name}",
                "description": (
                    f"Exported {export.Report_Type} report as {export_format.upper()}."
                ),
                "timestamp":   export.Exported_At.isoformat(),
                "tagId":       f"EX-{export.ExportID:04d}",
                "details": {
                    "report_type": export.Report_Type,
                    "format":      export_format,
                    "start_date":  export.Start_Date.isoformat() if export.Start_Date else None,
                    "end_date":    export.End_Date.isoformat() if export.End_Date else None,
                    "exported_at": export.Exported_At.isoformat() if export.Exported_At else None,
                    "log_id":      export.LogID,
                },
            })

        return success({
            "items":    items,
            "page":     logs.page,
            "per_page": logs.per_page,
            "pages":    logs.pages,
            "total":    logs.total,
            "has_next": logs.has_next,
            "has_prev": logs.has_prev,
        })

    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while retrieving export logs."
        )
        return error("An unexpected error occurred.", 500)
