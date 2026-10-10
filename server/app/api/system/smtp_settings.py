"""
Email settings (Settings -> Email): the Gmail account PinPoint's notification
mail is sent through.

Saving sends the settings to the root helper (see app/smtp_settings.py), which
writes /etc/msmtprc, and stores them in the SmtpSettings singleton in
system.db. The helper's error text is returned as-is so the card can show it.
The password is write-only: it is stored encrypted and no route returns it. All
routes need the "settings.email" permission, which also controls the Email tab
on the Settings page.

Routes
------
GET  /system/smtp-settings
    Return the saved settings (with "passwordSet", never the password) and the
    Gmail preset.

PUT  /system/smtp-settings
    Validate the settings, apply them through the helper and save them.

POST /system/smtp-settings/test
    Send a test email with the saved settings to the signed-in user's address.
"""
from flask import request, current_app
from flask_login import login_required, current_user

from app import db
from app.api.system import system_bp
from app.api.helper import success, error, validate_json_data
from app.api.helper.database_access.permissions import require_permission
from app.logging.configuration_changes import create_configuration_log
from app.secrets_store import SecretsError, decrypt, encrypt
from app.smtp_settings import (
    GMAIL,
    MailHelperError,
    SmtpSettingsError,
    get_smtp_row,
    get_smtp_settings,
    run_apply_helper,
    send_test_email,
    validate_smtp_settings,
)
from app.system_models import SmtpSettings, SystemSettings


LOGGED_FIELDS = (("Host", "host"), ("Port", "port"), ("Tls", "tls"), ("Username", "username"), ("Sender", "sender"))


@system_bp.get('/smtp-settings')
@login_required
@require_permission('settings.email')
def get_smtp_settings_route():
    """Return the saved email settings (never the password) and the Gmail preset."""
    try:
        return success({"settings": get_smtp_settings(), "presets": {"gmail": GMAIL}})
    except Exception:
        current_app.logger.exception("An unexpected error occurred while fetching email settings.")
        return error("An unexpected error occurred.", 500)


@system_bp.put('/smtp-settings')
@login_required
@require_permission('settings.email')
def update_smtp_settings_route():
    """
    Validate, apply and save the email settings. The client sends the full
    object with the version it loaded; a stale version is rejected with 409.
    Only Gmail over STARTTLS on port 587 is accepted. "password" is optional
    once one is saved: leave it out or empty to keep it. It is used exactly as
    sent (never trimmed or stripped of spaces). The settings are saved only if
    the helper accepts them; its error text is returned as the message.

    JSON Format
    {
        "version": 0,
        "provider": "gmail",
        "host": "smtp.gmail.com",
        "port": 587,
        "tls": "starttls",
        "username": "you@gmail.com",
        "sender": "you@gmail.com",
        "password": "abcd efgh ijkl mnop"
    }
    """
    data = request.get_json(silent=True)
    err = validate_json_data(data)
    if err is not None:
        return err

    try:
        row = get_smtp_row()
        current_version = row.Version if row is not None else 0
        has_saved_password = row is not None and bool(row.Password_Encrypted)

        try:
            values = validate_smtp_settings(data, has_saved_password)
        except SmtpSettingsError as exc:
            return error(exc.message, 400)

        if data.get("version") != current_version:
            return error("Email settings were updated by someone else. Reload and try again.", 409)

        password_changed = values["password"] is not None
        try:
            password = values["password"] if password_changed else decrypt(row.Password_Encrypted)
            encrypted = encrypt(password) if password_changed else row.Password_Encrypted
        except SecretsError as exc:
            return error(exc.message, 400)

        try:
            run_apply_helper(values, password)
        except MailHelperError as exc:
            return error(exc.message, 400 if exc.rejected else 500)

        changes = []
        if row is None:
            row = SmtpSettings(Id=1, Version=0)
            db.session.add(row)
            before = {}
        else:
            before = {column: getattr(row, column) for column, _ in LOGGED_FIELDS}
        for column, key in LOGGED_FIELDS:
            if before.get(column) != values[key]:
                changes.append((key, before.get(column, ""), values[key]))
            setattr(row, column, values[key])
        if password_changed:
            changes.append(("password", "-", "changed"))
        row.Provider = values["provider"]
        row.Password_Encrypted = encrypted
        row.Version += 1
        row.Updated_By = current_user.UserID

        system_settings = db.session.get(SystemSettings, 1)
        if system_settings is None or system_settings.Audit_Logging:
            for key, old_value, new_value in changes:
                create_configuration_log(current_user.UserID, "smtp_settings", key, str(old_value), str(new_value))

        db.session.commit()
        return success(get_smtp_settings(row), message="Email settings updated.")

    except Exception:
        db.session.rollback()
        current_app.logger.exception("An unexpected error occurred while updating email settings.")
        return error("An unexpected error occurred.", 500)


@system_bp.post('/smtp-settings/test')
@login_required
@require_permission('settings.email')
def test_smtp_settings_route():
    """
    Send a test email with the saved settings to the signed-in user's email
    address. A failed send is still a 200: the body is {"ok": false, "code",
    "message", "explanation", "details"} where "message" is plain language,
    "explanation" says technically what happened and what to check, and
    "details" is the mail server's own text. A rejected Gmail login has code "auth_failed";
    "connect_failed" and "host_not_found" cover a blocked port and a wrong host.
    """
    try:
        row = get_smtp_row()
        if row is None or not row.Password_Encrypted:
            return error("Save the email settings first.", 400)
        try:
            password = decrypt(row.Password_Encrypted)
        except SecretsError as exc:
            return error(exc.message, 400)

        settings = get_smtp_settings(row)
        return success(send_test_email(settings, password, current_user.Email))
    except Exception:
        current_app.logger.exception("An unexpected error occurred while sending the test email.")
        return error("An unexpected error occurred.", 500)
