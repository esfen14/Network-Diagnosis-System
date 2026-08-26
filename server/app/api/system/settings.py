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
    row = _get_singleton_row()
    payload = request.get_json(force=True)

    incoming_version = payload.get("version")
    if incoming_version != row.Version:
        return jsonify({
            "error": "conflict",
            "message": "Settings were updated by someone else. Reload and try again.",
        }), 409

    row.Scan_Frequency = payload.get("scanFrequency", row.Scan_Frequency)
    row.Notifications = payload.get("notifications", row.Notifications)
    if "exportFormats" in payload:
        row.Export_Formats = ",".join(payload["exportFormats"])

    row.Session_Timeout = payload.get("sessionTimeout", row.Session_Timeout)
    row.Strong_Password_Policy = payload.get("strongPasswordPolicy", row.Strong_Password_Policy)
    row.Failed_Login_Monitoring = payload.get("failedLoginMonitoring", row.Failed_Login_Monitoring)
    row.Audit_Logging = payload.get("auditLogging", row.Audit_Logging)
    row.Security_Check_Frequency = payload.get("securityCheckFrequency", row.Security_Check_Frequency)

    row.System_Update_Frequency = payload.get("systemUpdateFrequency", row.System_Update_Frequency)
    row.Maintenance_Mode = payload.get("maintenanceMode", row.Maintenance_Mode)
    row.Automatic_Backups = payload.get("automaticBackups", row.Automatic_Backups)
    row.Log_Retention_Days = payload.get("logRetentionDays", row.Log_Retention_Days)
    row.Diagnostic_History_Retention_Days = payload.get(
        "diagnosticHistoryRetentionDays", row.Diagnostic_History_Retention_Days
    )

    row.Version += 1
    row.Updated_By = current_user.UserID

    db.session.commit()
    return jsonify(row.to_dict())