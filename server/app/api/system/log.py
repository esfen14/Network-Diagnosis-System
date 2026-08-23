from flask import request, current_app
from flask_login import login_required
import sqlalchemy as sa

from app import db
from app.system_models import (
    ActivityLog,
    ConfigurationChanges,
    NetworkDiscoveryStatus,
    NCPADeploymentStatus,
    ExportLog,
    User
)
from app.api.helper import success, error
from app.api.helper.database_access.permissions import require_permission
from app.api.system import system_bp


# ==========================================================
# ACTIVITY LOG
# ==========================================================

@system_bp.get('/log')
@login_required
@require_permission("system.logs")
def activity_logs():
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

        query = (
            sa.select(ActivityLog, User)
            .join(User, User.UserID == ActivityLog.UserID)
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

        logs = db.paginate(query, page=page, per_page=per_page, error_out=False)

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

        logs = db.paginate(query, page=page, per_page=per_page, error_out=False)

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

        logs = db.paginate(query, page=page, per_page=per_page, error_out=False)

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

        logs = db.paginate(query, page=page, per_page=per_page, error_out=False)

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

@system_bp.get('/exportlog')
@login_required
@require_permission("system.logs")
def export_logs():
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

        logs = db.paginate(query, page=page, per_page=per_page, error_out=False)

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
