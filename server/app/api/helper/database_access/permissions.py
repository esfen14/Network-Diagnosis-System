import sqlalchemy as sa
from app import db
from flask_login import current_user
from app.system_models import Permission, RolePermission
from functools import wraps

def _has_permission(permission_name):
    # Get the permission id of the input
    permission_id = db.session.scalar(sa.select(Permission.PermissionID)
        .where(Permission.Name == permission_name)
    )
    
    # check if the input is a valid permission 
    if permission_id is None:
        return {"message": "Permission does not exist."}, 400
   
    exists = db.session.scalar(
       sa.select(
           sa.exists().where(
               RolePermission.RoleID == current_user.RoleID,
               RolePermission.PermissionID == permission_id)
            )
        ) 

    if not exists:
        return {"message": "User has no permission."}, 403
    
    return None


"""_summary_
    expects:
    input of string "permission_name"
    
    Returns:
    {"message" : "error message"}, http status code
    
This is a decorator to simply the usage of has_permissiosn()
    
it will beu use like this:
@require_permission("permission_name")
it will automatically give an error if the user doesn't have the permission
    
"""
# Stores permission_name
def require_permission(permission_name):

    if permission_name is None:
        raise ValueError("permission_name is required for require_permission decorator")

    if not isinstance(permission_name, str):
        raise ValueError("permission_name must be a string.")

    if permission_name.strip() == "":
        raise ValueError("permission_name must not be empty.")

    # Stores the function
    def decorator(func):
        @wraps(func)
        # Runs on requests
        def wrapper(*args, **kwargs):
            # Runs the check first
            error = _has_permission(permission_name)
            if error is not None:
                return error
            
            # If no errors occur, run the function
            return func(*args, **kwargs)
        return wrapper
    return decorator

# ============ Checks From Database ===================
def exists_permission_by_id(permission_id):
    return db.session.scalar(
        sa.select(
            sa.exists() 
            .where(
                Permission.PermissionID == permission_id
            )
        )
    )

def exists_permission_by_name(permission_name):
    return db.session.scalar(
        sa.select(
            sa.exists() 
            .where(
                Permission.Name == permission_name
            )
        )
    )