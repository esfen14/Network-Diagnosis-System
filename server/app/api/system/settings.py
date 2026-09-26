"""
System-wide settings: the singleton SystemSettings row.

The Settings page has three tabs. General settings can be changed by any
logged-in user; the Security and System tabs each need their own
permission, assigned per role in Manage Roles. The whole object is sent
on every save, so the check is on which fields actually changed.

Routes
------
GET  /system
    Return the current settings. Open to any logged-in user, since every
    page reads them (theme, refresh rate, session timeout, maintenance).

PUT  /system
    Save settings, rejecting fields the user isn't allowed to change.
"""
from flask import request, current_app
from flask_login import login_required, current_user

from app import db
from app.api.system import system_bp
from app.api.helper import success, error, user_has_permission
from app.system_models import SystemSettings
from app.logging.configuration_changes import create_configuration_log


# Which permission guards each settings field. Fields not listed here
# are General settings, open to every logged-in user.
FIELD_PERMISSIONS = {
    "Session_Timeout": "settings.security",
    "Strong_Password_Policy": "settings.security",
    "Failed_Login_Monitoring": "settings.security",
    "Audit_Logging": "settings.security",
    "Security_Check_Frequency": "settings.security",
    "System_Update_Frequency": "settings.system",
    "Maintenance_Mode": "settings.system",
    "Automatic_Backups": "settings.system",
    "Log_Retention_Days": "settings.system",
    "Diagnostic_History_Retention_Days": "settings.system",
}

PERMISSION_LABELS = {
    "settings.security": "Security",
    "settings.system": "System",
}


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
    """
    Save the settings. The client sends the full settings object with the
    version it loaded; a stale version is rejected with 409. Changing a
    Security or System field without that tab's permission is rejected
    with 403 and nothing is saved. Unchanged restricted fields are fine,
    so users without those permissions can still save General settings.

    JSON Format
    {
        "version": 3,
        "scanFrequency": 6,
        "notifications": true,
        "exportFormats": ["CSV", "PDF", "XLS"],
        "sessionTimeout": 30,
        "strongPasswordPolicy": true,
        "failedLoginMonitoring": true,
        "auditLogging": true,
        "securityCheckFrequency": "weekly",
        "systemUpdateFrequency": "monthly",
        "maintenanceMode": false,
        "automaticBackups": true,
        "logRetentionDays": 30,
        "diagnosticHistoryRetentionDays": 90
    }
    """
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

        # Whether to record this save's diffs in the Configuration Change
        # log — governed by the policy in effect when the save started, not
        # whatever Audit_Logging ends up as after this same request applies.
        audit_logging_enabled = bool(row.Audit_Logging)

        field_map = [
            ("Scan_Frequency", "scanFrequency"),
            ("Notifications", "notifications"),
            ("Session_Timeout", "sessionTimeout"),
            ("Strong_Password_Policy", "strongPasswordPolicy"),
            ("Failed_Login_Monitoring", "failedLoginMonitoring"),
            ("Audit_Logging", "auditLogging"),
            ("Security_Check_Frequency", "securityCheckFrequency"),
            ("System_Update_Frequency", "systemUpdateFrequency"),
            ("Maintenance_Mode", "maintenanceMode"),
            ("Automatic_Backups", "automaticBackups"),
            ("Log_Retention_Days", "logRetentionDays"),
            ("Diagnostic_History_Retention_Days", "diagnosticHistoryRetentionDays"),
        ]

        changes = []
        for attr, key in field_map:
            old_value = getattr(row, attr)
            new_value = payload[key]
            if old_value != new_value:
                changes.append((attr, old_value, new_value))
                setattr(row, attr, new_value)

        new_export_formats = ",".join(payload["exportFormats"])
        if row.Export_Formats != new_export_formats:
            changes.append(("Export_Formats", row.Export_Formats, new_export_formats))
            row.Export_Formats = new_export_formats

        denied = []
        for attr, _, _ in changes:
            permission = FIELD_PERMISSIONS.get(attr)
            if permission is None or permission in denied:
                continue
            if not user_has_permission(permission):
                denied.append(permission)

        if denied:
            db.session.rollback()
            tabs = " and ".join(PERMISSION_LABELS[p] for p in denied)
            return error(f"You don't have permission to change {tabs} settings.", 403)

        row.Version += 1
        row.Updated_By = current_user.UserID

        if audit_logging_enabled:
            for attr, old_value, new_value in changes:
                create_configuration_log(
                    current_user.UserID, "system_settings", attr, str(old_value), str(new_value)
                )

        db.session.commit()
        return success(row.to_dict(), message="Settings updated.")

    except KeyError as exc:
        return error(f"Missing required field: {exc}", 400)
    except Exception:
        current_app.logger.exception("An unexpected error occurred while updating settings.")
        return error("An unexpected error occurred.", 500)
