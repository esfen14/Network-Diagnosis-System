import sqlalchemy as sa
from flask import jsonify
from app import db
from flask_login import current_user
from app.system_models import Permission, RolePermission, Role
from functools import wraps


def _has_permission(permission_name):
    # Get the permission id of the input
    permission_id = db.session.scalar(
        sa.select(Permission.PermissionID)
        .where(Permission.Name == permission_name)
    )

    # Check if the input is a valid permission
    if permission_id is None:
        return jsonify({"success": False, "message": "Permission does not exist."}), 400

    query = (
        sa.select(RolePermission)
        .join(Role)
        .where(
            RolePermission.RoleID == current_user.RoleID,
            RolePermission.PermissionID == permission_id,
            Role.Is_Active.is_(True)
        )
    )

    exists = db.session.scalar(sa.select(sa.exists(query)))
    if not exists:
        return jsonify({"success": False, "message": "User has no permission."}), 403

    return None


"""
Decorator to enforce a named permission on a route.

Usage:
    @require_permission("permission_name")

Returns a standardized 400/403 JSON error if the check fails;
otherwise calls the decorated route function normally.
"""
def require_permission(permission_name):

    if permission_name is None:
        raise ValueError("permission_name is required for require_permission decorator")

    if not isinstance(permission_name, str):
        raise ValueError("permission_name must be a string.")

    if permission_name.strip() == "":
        raise ValueError("permission_name must not be empty.")

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            err = _has_permission(permission_name)
            if err is not None:
                return err
            return func(*args, **kwargs)
        return wrapper
    return decorator


# ============ Checks From Database ===================

def exists_permission_by_id(permission_id):
    return db.session.scalar(
        sa.select(
            sa.exists()
            .where(Permission.PermissionID == permission_id)
        )
    )


def exists_permission_by_name(permission_name):
    return db.session.scalar(
        sa.select(
            sa.exists()
            .where(Permission.Name == permission_name)
        )
    )
