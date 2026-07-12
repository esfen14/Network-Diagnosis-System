from flask import request
from flask_login import login_required, current_user
from app.api.helper.database_access.permissions import require_permission
from app.system_models import Permission, User, Role, RolePermission
from app.api.helper import *
from flask import current_app

import sqlalchemy as sa
from app import db

from app.api.user import user_bp
    
@user_bp.get('/permissions/options')
@login_required
@require_permission("role.edit")
def permission_list():
    
    query = (
        sa.select(Permission)
        .order_by(Permission.Name.asc())
    )
    
    permissions_list = db.session.scalars(query)
    
    items = []
    
    for permission in permissions_list:
        items.append(
            {
                "id": permission.PermissionID,
                "name": permission.Name
            }
        )
    
    return {"items": items}, 200

@user_bp.post('/roles')
@login_required
@require_permission("role.edit")
def create_role():
    """
    JSON format
    {
        "role_name": "name"
        "description": "description"
        "permissions":[1,2,4,5,..]
    }
    """
    data = request.get_json()
    
    error = validate_json_data(data)
    if error is not None:
        return error

    fields = {
        "role_name": str,
        "description": str,
        "permissions": list,
    }
    error = validate_json_fields(data, fields)
    if error is not None:
        return error
    
    role_name = data.get("role_name")
    description = data.get("description")
    permission_list = list(set(data.get("permissions")))

    error = validate_role_not_exists(role_name)
    if error is not None:
        return error

    for permission_id in permission_list:
        error = validate_permission_exists(permission_id)
        if error is not None:
            return error
        
    try:
        role = Role(Name=role_name, Is_Active=True, Description=description)
    
        db.session.add(role)
        db.session.flush()
        for permission_id in permission_list:
            role_permission = RolePermission(
                RoleID=role.RoleID,
                PermissionID=int(permission_id)
            )
            db.session.add(role_permission)
        
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(f"Failed to create role' {role_name}'")
        return {"message": "An error occurred."}, 500
    
    return {
        "message": "Role successfully created."
        }, 201

@user_bp.get('/roles')
@login_required
@require_permission("role.view")
def roles():
    page = request.args.get("page", default=1, type=int)
    per_page = request.args.get("per_page", default=10, type=int)
    sort_by = request.args.get("sort_by", default="name", type=str)
    order = request.args.get("order", default="asc", type=str)
    search =  request.args.get("search", default= "", type=str)
    
    allowed_sorts = {
        "name": Role.Name,
        "created_at": Role.Created_At,
        "id": Role.RoleID
    }
    
    sort_column = allowed_sorts.get(sort_by)
    if sort_column is None:
        return {"message": "Invalid sort field"}, 400
    
    query = sa.select(Role)
    
    if page < 1:
        return {"message": "Page must be greater than 0"}, 400
    
    if per_page < 1 or per_page > 100:
        return {"message": "per_page must be between 1 and 100"}, 400
    
    if order == 'desc':
        query = query.order_by(sort_column.desc())
    elif order == 'asc':
        query = query.order_by(sort_column.asc())
    else:
        return {"message": "Invalid order."}, 400
    
    if search:
        query = query.where(Role.Name.ilike(f"%{search}%"))
    
    roles = db.paginate(
        query,
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    items = []
    
    for role in roles.items:
        items.append(
            {
                "id": role.RoleID,
                "name": role.Name,
                "description": role.Description,
                "is_active": role.Is_Active,
                "created_at": role.Created_At.isoformat()
            }
        )
    
    return {
        "items": items,
        "page": roles.page,
        "per_page": roles.per_page,
        "pages": roles.pages,
        "total": roles.total,
        "has_next": roles.has_next,
        "has_prev": roles.has_prev
        },200


@user_bp.get('/roles/options')
@login_required
@require_permission("role.list")
def list_roles():
    query = (sa.select(Role)
             .order_by(Role.Name.asc())
             .where(Role.Is_Active.is_(True))
            )
    
    roles = db.session.scalars(query)
    
    items = []
    
    for role in roles:
        items.append(
            {
                "id":role.RoleID,
                "name":role.Name
            }
        )
    
    return {"items": items},200

@user_bp.get('/roles/<int:id>')
@login_required
@require_permission("role.info")
def role_info(id):
    error = validate_role_exists(id)
    if error is not None:
        return error

    role = get_role_by_id(id)

    permission_list = []
    
    query = (
        sa.select(RolePermission)
        .join(Permission)
        .where(RolePermission.RoleID == role.RoleID)
        )
    
    role_permissions = db.session.scalars(query).all()

    for permission in role_permissions:
        permission_list.append(
            {
                "id": permission.PermissionID,
                "name": permission.Permissions.Name
            }
        )
    
    return {
        "id": role.RoleID,
        "name": role.Name,
        "description": role.Description,
        "is_active": role.Is_Active,
        "permissions": permission_list
        },200


@user_bp.put('/roles/<int:id>')
@login_required
@require_permission("role.edit")
def edit_role(id):
    """
    JSON Format
    {
        "name": "name",
        "description": "description",
        "permissions": [1,2,4,5,..]
    }
    """
    
    error = validate_role_exists(id)
    if error is not None:
        return error

    data = request.get_json()
    
    error = validate_json_data(data)
    if error is not None:
        return error

    fields = {
        "name": str,
        "description": str,
        "permissions": list,
    }
    error = validate_json_fields(data, fields)
    if error is not None:
        return error
    
    role_name = data.get("name")
    description = data.get("description")
    permission_list = list(set(data.get("permissions")))

    if not has_name(role_name, id):
        error = validate_role_name_available(role_name)
        if error is not None:
            return error
    
    for permission_id in permission_list:
        error = validate_permission_exists(permission_id)
        if error is not None:
            return error
     
    try:

        role = get_role_by_id(id)
        
        role.Name = role_name
        role.Description = description


        db.session.execute(
            sa.delete(RolePermission)
            .where(RolePermission.RoleID == role.RoleID)
        )
        
        for permission_id in permission_list:
            role_permission = RolePermission(
                RoleID=role.RoleID,
                PermissionID = int(permission_id)
            )
            db.session.add(role_permission)
        
        db.session.commit()
        
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            f"Failed to update role '{role_name}'"
        )
        return {"message": "An error occurred."}, 500
    
    
    return {"message": "Role successfully updated."},200


@user_bp.put('/roles/<int:id>/status')
@login_required
@require_permission("role.edit")
def roles_status(id):
    error = validate_role_exists(id)
    if error is not None:
        return error
    
    role = get_role_by_id(id)
    old_status = role.Is_Active
    try:
        
        role.Is_Active = not role.Is_Active
        
        db.session.commit()
            
    except Exception:   
        db.session.rollback()
        current_app.logger.exception(
            f"Failed to change role status"
        )
        return {"message": "An error occurred."}, 500
    
    return {"message": "Role status updated sucessfully.",
            "previous_status": old_status,
            "current_status": role.Is_Active
        },200


@user_bp.post('/accounts')
@login_required
@require_permission("account.edit")
def create_account():
    """
    JSON format
    {
        "first_name": "first name",
        "last_name": "last_name",
        "email": "email@email",
        "password": "password",
        "confirm_password": "password",
        "status": "status",
        "role": 1
    }
    """

    data = request.get_json()
    error = validate_json_data(data)
    if error is not None:
        return error

    fields = {
        "first_name": str,
        "last_name": str,
        "email": str,
        "password": str,
        "confirm_password": str,
        "status": str,
        "role_id": int
    }

    error = validate_json_fields(data, fields)
    if error is not None:
        return error
    
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    email = data.get('email')
    password = data.get('password')
    confirm_password = data.get('confirm_password')
    status = data.get('status')
    role_id = data.get('role_id')
    
    error  = validate_role_exists(role_id)
    if error is not None:
        return error

    error = validate_userstatus(status)
    if error is not None:
        return error
    
    error =  validate_password_is_same(password, confirm_password)
    if error is not None:
        return error
    
    error = validate_password(password)
    if error is not None:
        return error
    
    error = validate_user_email(email)
    if error is not None:
        return error
    
    normalized_email = normalize_email(email)
    
    error = validate_email_available(normalized_email)
    if error is not None:
        return error
    
    normalized_status = convert_user_status(status)
    
    applied_role = get_role_by_id(role_id)
    
    try:
        user = User(
            First_name=first_name,
            Last_name=last_name,
            Email= normalized_email,
            Status= normalized_status,
            RoleID= applied_role.RoleID
        )
        user.set_password(password)

        db.session.add(user)
        db.session.commit()
    except Exception:
        current_app.logger.exception(
            f"Failed to create account '{email}'"
        )
        db.session.rollback()
        return {"message": "An error occurred."}, 500
    
    return {"message": "Account successfully created."},201

@user_bp.get('/accounts')
@login_required
@require_permission("account.view")
def available_accounts():
    page = request.args.get("page", default=1, type=int)
    per_page = request.args.get("per_page", default=10, type=int)
    sort_by = request.args.get("sort_by", default="first_name", type=str)
    order = request.args.get("order", default="asc", type=str)
    search =  request.args.get("search", default= "", type=str).strip()
    
    allowed_sorts = {
        "id": User.UserID,
        "first_name": User.First_name,
        "last_name": User.Last_name, 
        "email": User.Email,
        "role": Role.Name,
        "status": User.Status,
        "created_at": User.Created_At,
        "updated_at": User.Updated_At
    }
    
    sort_column = allowed_sorts.get(sort_by)
    
    if sort_column is None:
        return {"message": "Invalid sort field"}, 400
    
    query = sa.select(User).join(Role)
    
    if page < 1:
        return {"message": "Page must be greater than 0"}, 400
    
    if per_page < 1 or per_page > 100:
        return {"message": "per_page must be between 1 and 100"}, 400
    
    if order == 'desc':
        query = query.order_by(sort_column.desc())
    elif order == 'asc':
        query = query.order_by(sort_column.asc())
    else:
        return {"message": "Invalid order."}, 400
    
    if search:
        query = query.where(
            sa.or_(
                User.First_name.ilike(f"%{search}%"),
                User.Last_name.ilike(f"%{search}%"),
                User.Email.ilike(f"%{search}%"),
                User.Status.cast(sa.String).ilike(f"%{search}%"),
                Role.Name.ilike(f"%{search}%"),
            )
        )
    
    users = db.paginate(
        query,
        page=page,
        per_page=per_page,
        error_out=False
    )

    items = []
    
    for user in users.items:
        items.append(
            {
                "id": user.UserID,
                "first_name": user.First_name,
                "last_name": user.Last_name,
                "email": user.Email,
                "role": user.Role.Name,
                "status": user.Status.value,
                "created_at": user.Created_At.isoformat(),
                "updated_at": user.Updated_At.isoformat()
            }
        )
     
    return {
        "items": items,
        "page": users.page,
        "per_page": users.per_page,
        "pages": users.pages,
        "total": users.total,
        "has_next": users.has_next,
        "has_prev": users.has_prev
        },200

@user_bp.get('/accounts/<int:id>')
@login_required
@require_permission("account.info")
def account_info(id):
    error = validate_user_exists(id)
    if error is not None:
        return error

    user = get_user_by_id(id)
    
    return {
        "id": user.UserID,
        "first_name": user.First_name,
        "last_name": user.Last_name,
        "email": user.Email,
        "role": user.Role.Name,
        "status": user.Status.value,
        "created_at": user.Created_At.isoformat(),
        "updated_at": user.Updated_At.isoformat()
        },200

@user_bp.put('/accounts/<int:id>')
@login_required
@require_permission("account.edit")
def edit_account(id):
    error = validate_user_exists(id)
    if error is not None:
        return error
    
    data = request.get_json()
    
    error = validate_json_data(data)
    if error is not None:
        return error
    
    fields = {
        "first_name": str, 
        "last_name":  str,
        "email": str,
        "password": str,
        "confirm_password": str,
        "role_id": int,
        "status": str
        }
    error = validate_json_fields(data, fields)
    if error is not None:
        return error

    first_name = data.get('first_name')
    last_name = data.get('last_name')
    email = data.get('email')
    password = data.get('password')
    confirm_password = data.get('confirm_password')
    role = data.get('role_id')
    status = data.get('status')

    error = validate_userstatus(status)
    if error is not None:
        return error
    
    error =  validate_password_is_same(password, confirm_password)
    if error is not None:
        return error
    
    error = validate_password(password)
    if error is not None:
        return error
    
    error = validate_user_email(email)
    if error is not None:
        return error
    
    normalized_email = normalize_email(email)
     
    if not has_email(email, id):
        error = validate_email_available(email)
        if error is not None:
            return error
    
    error = validate_role_exists(role)
    if error is not None:
        return error
    
    user_info = get_user_by_id(id)
    role_info = get_role_by_id(role)

    normalized_status = convert_user_status(status)
    
   

    try:
        user_info.First_name = first_name
        user_info.Last_name = last_name
        user_info.Email = normalized_email 
        user_info.set_password(password)
        user_info.RoleID = role_info.RoleID
        user_info.Status = normalized_status

        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            f"Failed to update account '{email}'"
        )
        return {"message": "An error occurred."}, 400
    
    return {"message": "Sucessfully updated user."},200

@user_bp.get('/me')
@login_required
def user_permission():
    permissions = db.session.scalars(
        sa.select(Permission)
        .join(RolePermission)
        .where(
            RolePermission.RoleID == current_user.RoleID
        )
    ).all()
    
    permission_array = []
    
    for permission in permissions:
        permission_array.append(permission.Name)
    
    role_name = db.session.scalar(
        sa.select(Role.Name)
        .where(
            Role.RoleID == current_user.RoleID
        )
    )
        
    return {
        "first_name": current_user.First_name,
        "last_name": current_user.Last_name,
        "role": role_name,
        "permissions": permission_array
            },200