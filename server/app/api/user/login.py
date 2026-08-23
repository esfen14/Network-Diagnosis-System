from flask_login import login_user, logout_user, current_user, login_required
from flask import request, current_app
from app.api.helper import (
    validate_json_data,
    validate_json_fields,
    validate_user_email,
    get_user_by_email,
    normalize_email
)
from app.api.helper.responses import success, error
from app.api.user import user_bp


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

    if current_user.is_authenticated:
        return success(message="User is already logged in.")

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
        return error("Invalid username or password.", 401)

    if user.Status.value != "Active":
        return error("Account inactive.", 403)

    login_user(user)

    return success(message="User logged in.")


@user_bp.post('/logout')
@login_required
def logout():
    logout_user()
    return success(message="User logged out.")
