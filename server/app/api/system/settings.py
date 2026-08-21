from flask import jsonify, request
from flask_login import login_required, current_user

from app import db
from app.api.system import system_bp
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
    row = _get_singleton_row()
    return jsonify(row.to_dict())


@system_bp.route("", methods=["PUT"])
@login_required
def update_settings():
    # TODO: replace @login_required with a permission check once
    # we confirm how Role/Permission is enforced elsewhere.
    row = _get_singleton_row()
    payload = request.get_json(force=True)

    incoming_version = payload.get("version")
    if incoming_version != row.Version:
        return jsonify({
            "error": "conflict",
            "message": "Settings were updated by someone else. Reload and try again.",
        }), 409

    row.System_Language = payload["systemLanguage"]
    row.Theme = payload["theme"]
    row.Time_Zone = payload["timeZone"]
    row.Date_Time_Format = payload["dateTimeFormat"]
    row.System_Font = payload["systemFont"]
    row.System_Font_Size = payload["systemFontSize"]
    row.Dashboard_Refresh_Rate = payload["dashboardRefreshRate"]
    row.Scan_Frequency = payload["scanFrequency"]
    row.Dashboard_Layout = payload["dashboardLayout"]
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
    return jsonify(row.to_dict())