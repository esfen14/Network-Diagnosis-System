from flask import request, current_app
from flask_login import login_required, current_user

from app import db
from app.api.system import system_bp
from app.api.helper import success, error
from app.system_models import SystemSettings


def _get_singleton_row():
    row = db.session.get(SystemSettings, 1)
    if row is None:
        row = SystemSettings(Id=1)
        db.session.add(row)
        db.session.commit()
    return row


@system_bp.route("", methods=["GET"])
@login_required
def get_settings():
    try:
        row = _get_singleton_row()
        return success(row.to_dict())
    except Exception:
        current_app.logger.exception("An unexpected error occurred while fetching settings.")
        return error("An unexpected error occurred.", 500)


@system_bp.route("", methods=["PUT"])
@login_required
def update_settings():
    # TODO: replace @login_required with a permission check once
    # we confirm how Role/Permission is enforced elsewhere.
    try:
        row = _get_singleton_row()
        payload = request.get_json(force=True)

        if payload is None:
            return error("No JSON data provided.", 400)

        incoming_version = payload.get("version")
        if incoming_version != row.Version:
            return error(
                "Settings were updated by someone else. Reload and try again.",
                409,
            )

        row.Scan_Frequency = payload["scanFrequency"]
        row.Notifications = payload["notifications"]
        row.Export_Formats = ",".join(payload["exportFormats"])

        row.Session_Timeout = payload["sessionTimeout"]
        row.Strong_Password_Policy = payload["strongPasswordPolicy"]
        row.Failed_Login_Monitoring = payload["failedLoginMonitoring"]
        row.Audit_Logging = payload["auditLogging"]
        row.Security_Check_Frequency = payload["securityCheckFrequency"]

        row.System_Update_Frequency = payload["systemUpdateFrequency"]
        row.Maintenance_Mode = payload["maintenanceMode"]
        row.Automatic_Backups = payload["automaticBackups"]
        row.Log_Retention_Days = payload["logRetentionDays"]
        row.Diagnostic_History_Retention_Days = payload["diagnosticHistoryRetentionDays"]

        row.Version += 1
        row.Updated_By = current_user.UserID

        db.session.commit()
        return success(row.to_dict(), message="Settings updated.")

    except KeyError as exc:
        return error(f"Missing required field: {exc}", 400)
    except Exception:
        current_app.logger.exception("An unexpected error occurred while updating settings.")
        return error("An unexpected error occurred.", 500)
