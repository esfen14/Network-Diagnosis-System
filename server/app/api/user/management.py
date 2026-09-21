from flask import request
from flask_login import login_required, current_user
from app.api.helper.database_access.permissions import require_permission
from app.system_models import Permission, User, Role, RolePermission
from app.api.helper import *
from app.api.helper.responses import success, error
from flask import current_app

import sqlalchemy as sa
from app import db

from app.api.user import user_bp
    
@user_bp.get('/permissions/options')
@login_required
@require_permission("role.edit")
def permission_list():
    try:
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
        
        return success({"items": items})
    except Exception:
        current_app.logger.exception("An unexpected error occured.")
        return error("An unexpected error occured.", 500)

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
    try:
        data = request.get_json()
        
        err = validate_json_data(data)
        if err is not None:
            return err

        fields = {
            "role_name": str,
            "description": str,
            "permissions": list,
        }
        err = validate_json_fields(data, fields)
        if err is not None:
            return err
        
        role_name = data.get("role_name")
        description = data.get("description")
        permissions = list(set(data.get("permissions")))

        err = validate_role_not_exists(role_name)
        if err is not None:
            return err

        for permission_id in permissions:
            err = validate_permission_exists(permission_id)
            if err is not None:
                return err
            
        try:
            role = Role(Name=role_name, Is_Active=True, Description=description)
        
            db.session.add(role)
            db.session.flush()
            for permission_id in permissions:
                role_permission = RolePermission(
                    RoleID=role.RoleID,
                    PermissionID=int(permission_id)
                )
                db.session.add(role_permission)
            
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception(f"Failed to create role '{role_name}'")
            return error("An error occurred.", 500)
        
        return success(message="Role successfully created.", status=201)
    except Exception:
        current_app.logger.exception("An unexpected error occured.")
        return error("An unexpected error occured.", 500)

@user_bp.get('/roles')
@login_required
@require_permission("role.view")
def roles():
    try:
        page = request.args.get("page", default=1, type=int)
        per_page = request.args.get("per_page", default=10, type=int)
        sort_by = request.args.get("sort_by", default="name", type=str)
        order = request.args.get("order", default="asc", type=str)
        search = request.args.get("search", default="", type=str)
        
        allowed_sorts = {
            "name": Role.Name,
            "created_at": Role.Created_At,
            "id": Role.RoleID
        }
        
        sort_column = allowed_sorts.get(sort_by)
        if sort_column is None:
            return error("Invalid sort field", 400)
        
        query = sa.select(Role)
        
        if page < 1:
            return error("Page must be greater than 0", 400)
        
        if per_page < 1 or per_page > 100:
            return error("per_page must be between 1 and 100", 400)
        
        if order == 'desc':
            query = query.order_by(sort_column.desc())
        elif order == 'asc':
            query = query.order_by(sort_column.asc())
        else:
            return error("Invalid order.", 400)
        
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
        
        return success({
            "items": items,
            "page": roles.page,
            "per_page": roles.per_page,
            "pages": roles.pages,
            "total": roles.total,
            "has_next": roles.has_next,
            "has_prev": roles.has_prev
        })
    except Exception:
        current_app.logger.exception("An unexpected error occured.")
        return error("An unexpected error occured.", 500)


@user_bp.get('/roles/options')
@login_required
@require_permission("role.list")
def list_roles():
    try:
        query = (sa.select(Role)
                .order_by(Role.Name.asc())
                .where(Role.Is_Active.is_(True))
                )
        
        roles = db.session.scalars(query)
        
        items = []
        
        for role in roles:
            items.append(
                {
                    "id": role.RoleID,
                    "name": role.Name
                }
            )
        
        return success({"items": items})
    except Exception:
        current_app.logger.exception("An unexpected error occured.")
        return error("An unexpected error occured.", 500)

@user_bp.get('/roles/<int:id>')
@login_required
@require_permission("role.info")
def role_info(id):
    try:
        err = validate_role_exists(id)
        if err is not None:
            return err

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
        
        return success({
            "id": role.RoleID,
            "name": role.Name,
            "description": role.Description,
            "is_active": role.Is_Active,
            "permissions": permission_list
        })
    except Exception:
        current_app.logger.exception("An unexpected error occured.")
        return error("An unexpected error occured.", 500)


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
    try:
        err = validate_role_exists(id)
        if err is not None:
            return err

        data = request.get_json()
        
        err = validate_json_data(data)
        if err is not None:
            return err

        fields = {
            "name": str,
            "description": str,
            "permissions": list,
        }
        err = validate_json_fields(data, fields)
        if err is not None:
            return err
        
        role_name = data.get("name")
        description = data.get("description")
        permissions = list(set(data.get("permissions")))

        if not has_name(role_name, id):
            err = validate_role_name_available(role_name)
            if err is not None:
                return err
        
        for permission_id in permissions:
            err = validate_permission_exists(permission_id)
            if err is not None:
                return err
        
        try:
            role = get_role_by_id(id)
            
            role.Name = role_name
            role.Description = description

            db.session.execute(
                sa.delete(RolePermission)
                .where(RolePermission.RoleID == role.RoleID)
            )
            
            for permission_id in permissions:
                role_permission = RolePermission(
                    RoleID=role.RoleID,
                    PermissionID=int(permission_id)
                )
                db.session.add(role_permission)
            
            db.session.commit()
            
        except Exception:
            db.session.rollback()
            current_app.logger.exception(f"Failed to update role '{role_name}'")
            return error("An error occurred.", 500)
        
        return success(message="Role successfully updated.")
    except Exception:
        current_app.logger.exception("An unexpected error occured.")
        return error("An unexpected error occured.", 500)


@user_bp.put('/roles/<int:id>/status')
@login_required
@require_permission("role.edit")
def roles_status(id):
    try:
        err = validate_role_exists(id)
        if err is not None:
            return err
        
        role = get_role_by_id(id)
        old_status = role.Is_Active
        try:
            role.Is_Active = not role.Is_Active
            db.session.commit()
        except Exception:   
            db.session.rollback()
            current_app.logger.exception("Failed to change role status")
            return error("An error occurred.", 500)
        
        return success({
            "previous_status": old_status,
            "current_status": role.Is_Active
        }, message="Role status updated successfully.")
    except Exception:
        current_app.logger.exception("An unexpected error occured.")
        return error("An unexpected error occured.", 500)


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
        "role_id": 1
    }
    """
    try:
        data = request.get_json()
        err = validate_json_data(data)
        if err is not None:
            return err

        fields = {
            "first_name": str,
            "last_name": str,
            "email": str,
            "password": str,
            "confirm_password": str,
            "status": str,
            "role_id": int
        }

        err = validate_json_fields(data, fields)
        if err is not None:
            return err
        
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        email = data.get('email')
        password = data.get('password')
        confirm_password = data.get('confirm_password')
        status = data.get('status')
        role_id = data.get('role_id')
        
        err = validate_role_exists(role_id)
        if err is not None:
            return err

        err = validate_userstatus(status)
        if err is not None:
            return err
        
        err = validate_password_is_same(password, confirm_password)
        if err is not None:
            return err
        
        err = validate_password(password)
        if err is not None:
            return err
        
        err = validate_user_email(email)
        if err is not None:
            return err
        
        normalized_email = normalize_email(email)
        
        err = validate_email_available(normalized_email)
        if err is not None:
            return err
        
        normalized_status = convert_user_status(status)
        applied_role = get_role_by_id(role_id)
        
        try:
            user = User(
                First_Name=first_name,
                Last_Name=last_name,
                Email=normalized_email,
                Status=normalized_status,
                RoleID=applied_role.RoleID
            )
            user.set_password(password)

            db.session.add(user)
            db.session.commit()
        except Exception:
            current_app.logger.exception(f"Failed to create account '{email}'")
            db.session.rollback()
            return error("An error occurred.", 500)
        
        return success(message="Account successfully created.", status=201)
    except Exception:
        current_app.logger.exception("An unexpected error occured.")
        return error("An unexpected error occured.", 500)

@user_bp.get('/accounts')
@login_required
@require_permission("account.view")
def available_accounts():
    try:
        page = request.args.get("page", default=1, type=int)
        per_page = request.args.get("per_page", default=10, type=int)
        sort_by = request.args.get("sort_by", default="first_name", type=str)
        order = request.args.get("order", default="asc", type=str)
        search = request.args.get("search", default="", type=str).strip()
        
        allowed_sorts = {
            "id": User.UserID,
            "first_name": User.First_Name,
            "last_name": User.Last_Name, 
            "email": User.Email,
            "role": Role.Name,
            "status": User.Status,
            "created_at": User.Created_At,
            "updated_at": User.Updated_At
        }
        
        sort_column = allowed_sorts.get(sort_by)
        
        if sort_column is None:
            return error("Invalid sort field", 400)
        
        query = sa.select(User).join(Role)
        
        if page < 1:
            return error("Page must be greater than 0", 400)
        
        if per_page < 1 or per_page > 100:
            return error("per_page must be between 1 and 100", 400)
        
        if order == 'desc':
            query = query.order_by(sort_column.desc())
        elif order == 'asc':
            query = query.order_by(sort_column.asc())
        else:
            return error("Invalid order.", 400)
        
        if search:
            query = query.where(
                sa.or_(
                    User.First_Name.ilike(f"%{search}%"),
                    User.Last_Name.ilike(f"%{search}%"),
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
                    "first_name": user.First_Name,
                    "last_name": user.Last_Name,
                    "email": user.Email,
                    "role": user.Role.Name,
                    "status": user.Status.value,
                    "created_at": user.Created_At.isoformat(),
                    "updated_at": user.Updated_At.isoformat()
                }
            )
        
        return success({
            "items": items,
            "page": users.page,
            "per_page": users.per_page,
            "pages": users.pages,
            "total": users.total,
            "has_next": users.has_next,
            "has_prev": users.has_prev
        })
    except Exception:
        current_app.logger.exception("An unexpected error occured.")
        return error("An unexpected error occured.", 500)

@user_bp.get('/accounts/<int:id>')
@login_required
@require_permission("account.info")
def account_info(id):
    try:
        err = validate_user_exists(id)
        if err is not None:
            return err

        user = get_user_by_id(id)
        
        return success({
            "id": user.UserID,
            "first_name": user.First_Name,
            "last_name": user.Last_Name,
            "email": user.Email,
            "role": user.Role.Name,
            "status": user.Status.value,
            "created_at": user.Created_At.isoformat(),
            "updated_at": user.Updated_At.isoformat()
        })
    except Exception:
        current_app.logger.exception("An unexpected error occured.")
        return error("An unexpected error occured.", 500)

@user_bp.put('/accounts/<int:id>')
@login_required
@require_permission("account.edit")
def edit_account(id):
    try:
        err = validate_user_exists(id)
        if err is not None:
            return err
        
        data = request.get_json()
        
        err = validate_json_data(data)
        if err is not None:
            return err
        
        fields = {
            "first_name": str, 
            "last_name": str,
            "email": str,
            "password": str,
            "confirm_password": str,
            "role_id": int,
            "status": str
        }
        err = validate_json_fields(data, fields)
        if err is not None:
            return err

        first_name = data.get('first_name')
        last_name = data.get('last_name')
        email = data.get('email')
        password = data.get('password')
        confirm_password = data.get('confirm_password')
        role = data.get('role_id')
        status = data.get('status')

        err = validate_userstatus(status)
        if err is not None:
            return err
        
        err = validate_password_is_same(password, confirm_password)
        if err is not None:
            return err
        
        err = validate_password(password)
        if err is not None:
            return err
        
        err = validate_user_email(email)
        if err is not None:
            return err
        
        normalized_email = normalize_email(email)
        
        if not has_email(email, id):
            err = validate_email_available(email)
            if err is not None:
                return err
        
        err = validate_role_exists(role)
        if err is not None:
            return err
        
        user_info = get_user_by_id(id)
        role_info = get_role_by_id(role)

        normalized_status = convert_user_status(status)

        try:
            user_info.First_Name = first_name
            user_info.Last_Name = last_name
            user_info.Email = normalized_email 
            user_info.set_password(password)
            user_info.RoleID = role_info.RoleID
            user_info.Status = normalized_status

            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception(f"Failed to update account '{email}'")
            return error("An error occurred.", 400)
        
        return success(message="Successfully updated user.")
    except Exception:
        current_app.logger.exception("An unexpected error occured.")
        return error("An unexpected error occured.", 500)

@user_bp.get('/me')
@login_required
def user_permission():
    try:
        permissions = db.session.scalars(
            sa.select(Permission)
            .join(RolePermission)
            .where(
                RolePermission.RoleID == current_user.RoleID
            )
        ).all()

        if permissions is None:
            return error("There is no role with that ID.", 404)
        
        permission_array = []
        
        for permission in permissions:
            permission_array.append(permission.Name)
        
        role_name = db.session.scalar(
            sa.select(Role.Name)
            .where(
                Role.RoleID == current_user.RoleID
            )
        )

        if role_name is None:
            return error(f"The role does not exist.", 404)
            
        return success({
            "first_name": current_user.First_Name,
            "last_name": current_user.Last_Name,
            "email": current_user.Email,
            "role": role_name,
            "permissions": permission_array
        })
    except Exception:
        current_app.logger.exception("An unexpected error occured.")
        return error("An unexpected error occured.", 500)
