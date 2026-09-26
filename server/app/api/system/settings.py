from flask import request, current_app
from flask_login import login_required, current_user

from app import db
from app.api.system import system_bp
from app.api.helper import success, error
from app.system_models import SystemSettings
from app.logging.configuration_changes import create_configuration_log


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
