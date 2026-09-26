from flask_login import login_user, logout_user, login_required, current_user
from flask import request, current_app
from app import db
from app.api.helper import (
    validate_json_data,
    validate_json_fields,
    validate_user_email,
    get_user_by_email,
    normalize_email
)
from app.api.helper.responses import success, error
from app.api.helper.settings_flags import is_failed_login_monitoring_enabled
from app.api.user import user_bp
from app.logging.user_activity import create_user_log


def _record_failed_login(user):
    if not is_failed_login_monitoring_enabled():
        return
    try:
        create_user_log(user.UserID, "Failed login attempt")
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            f"Unable to record failed login attempt for user {user.UserID}"
        )


@user_bp.post('/login')
def login():
    """
    This function is for logging in a user and validating credentials.

    Expects:
    {
        "email": "email",
        "password": "password"
    }

    Returns:
        Standardized JSON response
    """

    data = request.get_json()

    err = validate_json_data(data)
    if err is not None:
        return err

    fields = {
        "email": str,
        "password": str
    }

    err = validate_json_fields(data, fields)
    if err is not None:
        return err

    email = data.get("email")
    password = data.get("password")

    err = validate_user_email(email)
    if err is not None:
        return err

    normalized_email = normalize_email(email)

    user = get_user_by_email(normalized_email)

    if user is None or not user.check_password(password):
        if user is not None:
            _record_failed_login(user)
        else:
            current_app.logger.warning(
                f"Failed login attempt for unknown email '{normalized_email}'."
            )
        return error("Invalid username or password.", 401)

    if user.Status.value != "Active":
        return error("Account inactive.", 403)

    if current_user.is_authenticated:
        return success(message="User already logged in.")

    login_user(user)

    return success(message="User logged in.")


@user_bp.post('/logout')
@login_required
def logout():
    logout_user()
    return success(message="User logged out.")
