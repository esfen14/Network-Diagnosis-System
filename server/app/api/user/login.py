import time

from flask_login import login_user, logout_user, login_required, current_user
from flask import request, current_app, session
from app import db
from app.api.helper import (
    validate_json_data,
    validate_json_fields,
    validate_user_email,
    get_user_by_email,
    normalize_email
)
from app.api.helper.responses import success, error
from app.api.helper.settings_flags import (
    is_failed_login_monitoring_enabled,
    get_session_timeout_minutes
)
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


# ==========================================================
# SESSION TIMEOUT
# ==========================================================

@user_bp.before_app_request
def enforce_session_timeout():
    """
    Expire a logged-in session after it has been idle longer than the
    Session Timeout in System Settings. Runs before every request: the
    time of the last request is kept in the signed session cookie, and
    if the gap since then is too long the user is logged out and the
    request is rejected with 401. Otherwise the timestamp is refreshed,
    so any request counts as activity.

    The front-end also logs the user out after the same idle period
    (SessionTimeoutWatcher), since background polling keeps making
    requests while a page is open. This check covers the cases the
    browser can't, such as a closed tab or a sleeping machine.
    """
    if not current_user.is_authenticated:
        return None

    now = time.time()
    last_activity = session.get("last_activity")
    timeout_seconds = get_session_timeout_minutes() * 60

    if last_activity is not None and now - last_activity > timeout_seconds:
        logout_user()
        session.pop("last_activity", None)
        return error("Session expired. Please log in again.", 401)

    session["last_activity"] = now
    return None


# ==========================================================
# LOGIN / LOGOUT
# ==========================================================

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
    session["last_activity"] = time.time()

    return success(message="User logged in.")


@user_bp.post('/logout')
@login_required
def logout():
    logout_user()
    session.pop("last_activity", None)
    return success(message="User logged out.")
