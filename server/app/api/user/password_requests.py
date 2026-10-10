"""
Forgot-password flow. No email is sent and no self-service reset link exists:
a user asks from the login page, administrators (anyone holding
``account.edit``) see the request in the app, and only an administrator sets
the new password. The new password is temporary (Must_Change_Password).

Routes
------
POST /user/forgot-password                          public
GET  /user/password-requests                        account.edit
POST /user/password-requests/<id>/resolve           account.edit
POST /user/password-requests/<id>/dismiss           account.edit
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from flask import request, current_app
from flask_login import login_required, current_user

from app import db
from app.api.helper import (
    validate_json_data,
    validate_json_fields,
    validate_user_email,
    validate_password,
    validate_password_is_same,
    get_user_by_email,
    normalize_email,
)
from app.api.helper.responses import success, error
from app.api.helper.database_access.permissions import require_permission
from app.api.user import user_bp
from app.logging.user_activity import create_user_log
from app.system_models import PasswordResetRequest, User, UserStatus

PENDING = "Pending"
COMPLETED = "Completed"
DISMISSED = "Dismissed"

# Identical for known and unknown emails so the form can't be used to find
# out which addresses have accounts.
_GENERIC_MESSAGE = (
    "If that email belongs to an active account, an administrator has been "
    "notified and will reset your password."
)


@user_bp.post('/forgot-password')
def forgot_password():
    try:
        data = request.get_json(silent=True)
        err = validate_json_data(data)
        if err is not None:
            return err

        err = validate_json_fields(data, {"email": str})
        if err is not None:
            return err

        email = data.get("email")
        err = validate_user_email(email)
        if err is not None:
            return err

        user = get_user_by_email(normalize_email(email))

        if user is not None and user.Status == UserStatus.ACTIVE:
            already_pending = db.session.scalar(
                sa.select(PasswordResetRequest.RequestID).where(
                    PasswordResetRequest.UserID == user.UserID,
                    PasswordResetRequest.Status == PENDING,
                )
            )
            if already_pending is None:
                try:
                    db.session.add(PasswordResetRequest(UserID=user.UserID, Status=PENDING))
                    create_user_log(user.UserID, "Requested a password reset")
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    current_app.logger.exception(
                        f"Unable to record password reset request for user {user.UserID}"
                    )

        return success(message=_GENERIC_MESSAGE)
    except Exception:
        current_app.logger.exception("An unexpected error occured.")
        return error("An unexpected error occured.", 500)


@user_bp.get('/password-requests')
@login_required
@require_permission("account.edit")
def list_password_requests():
    """Pending requests, oldest first."""
    try:
        rows = db.session.execute(
            sa.select(PasswordResetRequest, User)
            .join(User, User.UserID == PasswordResetRequest.UserID)
            .where(PasswordResetRequest.Status == PENDING)
            .order_by(PasswordResetRequest.Requested_At.asc())
        ).all()

        items = [
            {
                "id": req.RequestID,
                "user_id": user.UserID,
                "name": f"{user.First_Name} {user.Last_Name}".strip(),
                "email": user.Email,
                "requested_at": req.Requested_At.replace(tzinfo=timezone.utc).isoformat()
                if req.Requested_At.tzinfo is None else req.Requested_At.isoformat(),
            }
            for req, user in rows
        ]
        return success({"items": items, "count": len(items)})
    except Exception:
        current_app.logger.exception("An unexpected error occured.")
        return error("An unexpected error occured.", 500)


def _get_pending(request_id):
    req = db.session.get(PasswordResetRequest, request_id)
    if req is None:
        return None, error("Request does not exist.", 404)
    if req.Status != PENDING:
        return None, error("Request has already been handled.", 409)
    return req, None


@user_bp.post('/password-requests/<int:id>/resolve')
@login_required
@require_permission("account.edit")
def resolve_password_request(id):
    """
    Body: {"password": "...", "confirm_password": "..."}
    Sets a temporary password; the user must change it at next login.
    """
    try:
        data = request.get_json(silent=True)
        err = validate_json_data(data)
        if err is not None:
            return err

        err = validate_json_fields(data, {"password": str, "confirm_password": str})
        if err is not None:
            return err

        req, err = _get_pending(id)
        if err is not None:
            return err

        err = validate_password_is_same(data["password"], data["confirm_password"])
        if err is not None:
            return err

        err = validate_password(data["password"])
        if err is not None:
            return err

        user = db.session.get(User, req.UserID)
        try:
            user.set_password(data["password"])
            user.Must_Change_Password = True
            req.Status = COMPLETED
            req.Resolved_At = datetime.now(timezone.utc)
            req.Resolved_By = current_user.UserID
            create_user_log(
                current_user.UserID,
                f"Reset password for {user.Email} (forgot-password request)",
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception(f"Failed to resolve password request {id}")
            return error("An error occurred.", 400)

        return success(message="Password reset. The user must change it at next login.")
    except Exception:
        current_app.logger.exception("An unexpected error occured.")
        return error("An unexpected error occured.", 500)


@user_bp.post('/password-requests/<int:id>/dismiss')
@login_required
@require_permission("account.edit")
def dismiss_password_request(id):
    try:
        req, err = _get_pending(id)
        if err is not None:
            return err

        try:
            req.Status = DISMISSED
            req.Resolved_At = datetime.now(timezone.utc)
            req.Resolved_By = current_user.UserID
            create_user_log(
                current_user.UserID,
                f"Dismissed password reset request #{id}",
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception(f"Failed to dismiss password request {id}")
            return error("An error occurred.", 400)

        return success(message="Request dismissed.")
    except Exception:
        current_app.logger.exception("An unexpected error occured.")
        return error("An unexpected error occured.", 500)
