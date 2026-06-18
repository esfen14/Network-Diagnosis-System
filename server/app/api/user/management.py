from flask import request
from flask_login import login_user, logout_user, login_required, current_user
from app.system_models import Permission, User, Role, RolePermission
from datetime import datetime, timezone
from api.helper.validation import user_exists, valid_json, require_fields, permission_exists, role_exists, check_email, check_user_status
from api.helper.converter import convert_user_status
from api.helper.permissions import require_permission
from email_validator import validate_email

import sqlalchemy as sa
from app import db

from user import user_bp

# DO NOT PUT A ROUTE ON THIS ONE, THIS IS FOR THE SERVER TO CREATE PERMISSIONS
# ALONG WITH THAT TESTING PURPOSES
def CreatePermission(Name, Description):
    # check if the user has input a permission that is already in the database
    # if there is
    # print out a erorr message, saying,that permission has already been created
    # stop the function 
    # else
    # get the inputs an insert it into the database
    # commit the changes
    print()
    
@user_bp.get('/permissions/options')
@login_required
@require_permission("Placeholder")
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
@require_permission("Placeholder")
def create_role():
    # check if the user has the permission or the user's role has the permission (function)
    # if not give an error
    # get the json of the input
    # It should be the name of the role and description
    # check if the input is a json
    # if not
    # give an error
    # else
    # check if its an empty json
    # if it is give an error
    # else continue
    # check if the role name is already in the system, not case sensitive
    # if there is
    # give an error
    # else
    # get the inputs
    # insert it into the database
    # commit changes
    # retun success message
    """
    JSON format
    {
        "role_name": "name"
        "description": "description"
        "permissions":[1,2,4,5,..]
    }
    """
    data = request.get_json()
    
    error = valid_json(data)
    if error is not None:
        return error

    fields = {
        "role_name": str,
        "description": str,
        "permissions": list,
    }
    error = require_fields(data, fields)
    if error is not None:
        return error
    
    role_name = data.get("role_name")
    description = data.get("description")
    permission_list = list(set(data.get("permissions")))

    error = role_exists(role_name)
    
    if error is not None:
        return error

    for permission_id in permission_list:
        error = permission_exists(permission_id)
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
    except Exception:
        db.session.rollback()
        return {"message": "An error occurred."}, 500
    
    return {"message": "Role successfully created."}, 201

@user_bp.get('/roles')
@login_required
@require_permission("Placeholder")
def roles():
    # check if the user has the permission or the user's role has the permission (function)
    # if not give an error
    # Get the the page argument (remember put a min and max)
    # Get the per_page amount argument (remember put a min and max)
    # Get the sorting argument
    # get the search argument
    # if else for the sorting argument given
    # ask for the query made with the page and item and error out false
    # 
    # return the data:
    # items, page, per_page, pages, total, has_next, has_prev
    page = request.args.get("page", default=1, type=int)
    pages = request.args.get("pages", default=1, type=int)
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
                "is_active": role.Is_Active
            }
        )
    
    return {
        "items": items,
        "page": roles.page,
        "per_page": roles.per_page,
        "total": roles.total,
        "has_next": roles.has_next,
        "has_prev": roles.has_prev
        },200


@user_bp.get('/roles/options')
@login_required
@require_permission("Placeholder")
def list_roles():
    # check if the user has the permission or the user's role has the permission (function)
    # if not give an error
    # ask for the query for all roles that are active
    # return the data:
    # items
    
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
@require_permission("Placeholder")
def role_info(id):
    # check if the user has the permission or the user's role has the permission (function)
    # get the id argument of the url
    # make a query for the id given
    # check if that id exists
    # if not give an error
    # else give the data
    error = role_exists(id)
    if error is not None:
        return error

    role = db.session.get(Role, id)

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
@require_permission("Placeholder")
def edit_role(id):
    # check if the user has the permission or the user's role has the permission (function)
    # get the id of the role needs to be modified
    # check if that role exists
    # if not give an error
    # else 
    # check the format of the data given
    # get the new info
    # update the info of the given id
    # commit changes
    
    """
    JSON Format
    {
        "id": number,
        "name": "name",
        "description": "description",
        "permissions": [1,2,4,5,..]
    }
    """
    
    error = role_exists(id)
    if error is not None:
        return error

    data = request.get_json()
    
    error = valid_json(data)
    if error is not None:
        return error

    fields = {
        "id": int,
        "name": str,
        "description": str,
        "permissions": list,
    }
    error = require_fields(data, fields)
    if error is not None:
        return error
    
    name = data.get("name")
    description = data.get("description")
    permission_list = data.get("permissions")

    for permission_id in permission_list:
        error = permission_exists(permission_id)
        if error is not None:
            return error
     
    try:

        role = db.session.get(Role,id)
        
        role.Name = name
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
        return {"message": "An error occurred."}, 500
    
    
    return {"message": "Role successfully updated."},200


@user_bp.put('/roles/<int:id>/status')
@login_required
@require_permission("Placeholder")
def roles_status(id):
    # check if the user has the permission or the user's role has the permission (function)
    # get the id of the role that needs to be modified
    # check if that role exists
    # if not, give an error
    # get the current status of the role
    # if the current status is the same as input status
    # give an error
    # if not change the status
    # commit changes
    
    error = role_exists(id)
    if error is not None:
        return error
    
    role = db.session.get(Role, id)
    old_status = role.Is_Active
    try:
        
        role.Is_Active = not role.Is_Active
        
        db.session.commit()
            
    except Exception:   
        db.session.rollback()
        return {"message": "An error occurred."}, 500
    
    return {"message": "User status updated sucessfully.",
            "previous_status": old_status,
            "current_status": role.Is_Active
        },200


@user_bp.post('/accounts')
@login_required
@require_permission("Placeholder")
def create_account():
    # check if the user has the permission or the user's role has the permission (function)
    # if not give an error
    # get the json of the input
    # if the input is json, if not give an error
    # if the json is emtpy, if not give an error
    # check if the user's email is already in the system
    # if yes then give an error
    # get the inputs
    # get the role of the input
    # get the id of the role 
    # insert the user into the database
    # commit changes
    # get the all the permissions
    # add the permissions of the user
    # commit changes
    """
    JSON format
    {
        "first_name": "first name",
        "last_name": "last_name",
        "email": "email@email",
        "passowrd": "password",
        "status": "status",
        "role": 1
    }
    """

    data = request.get_json()
    error = valid_json(data)
    if error is not None:
        return error

    fields = {
        "first_name": str,
        "last_name": str,
        "email": str,
        "password": str,
        "status": str,
        "role": int 
    }

    error = require_fields(data, fields)
    if error is not None:
        return error
    
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    email = data.get('email')
    password = data.get('password')
    status = data.get('status')
    role = data.get('role')

    error = check_email(email)
    if error is not None:
        return error

    error = check_user_status(status)
    if error is not None:
        return error
    
    normalized_status = convert_user_status(status)
    
    normalized_email = validate_email(email)
    try:
        user = User(
            First_name=first_name,
            Last_name=last_name,
            Email= normalized_email,
            Status= normalized_status,
            Role= role
        )
        user.set_password(password)

        db.session.add(user)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return {"message": "An error occurred."}, 500
    
    return {"message": "Placeholder"},200

@user_bp.get('/accounts')
@login_required
@require_permission("Placeholder")
def available_accounts():
    # check if the user has the permission or the user's role has the permission (function)
    # if not give an error
    # get page argument
    # get the per_page argument
    # get the sorting argument
    # get the search argument
    # if else for the given sorting argument
    # ask the query made with the page and item and error out false
    #
    # return the data:
    # items, page, per_page, pages, total, has_next, has_prev
    
    return {"message": "Placeholder"},200

@user_bp.get('/accounts/<int:id>')
@login_required
@require_permission("Placeholder")
def account_info():
    # check if the user has the permission or the user's role has the permission (function)
    # if not give an error
    # get the id argument of the url
    # make a query for the id given
    # check if that id exists
    #  if not give an erorr
    # else give the data
    
    return {"message": "Placeholder"},200

@user_bp.put('/accounts/<int:id>')
@login_required
@require_permission("Placeholder")
def edit_account(id):
    # check if the user has the permission or the user's role has the permission (function)
    # if not give an error
    # check if that user exists
    # if not give an error
    # else
    # check the format of the given data
    # get the new info 
    # update the info of the given id
    # commit changes
    
    error = user_exists(id)
    if error is not None:
        return error
    
    data = request.get_json()
    error = valid_json(data)
    
    if error is not None:
        return error
    
    fields = ["first_name", "last_name", "password", "role_name","permissions"]
    error = require_fields(data, fields)
    if error is not None:
        return error

    
    
    return {"message": "Placeholder"},200

@user_bp.get('/me')
@login_required
def user_permission():
    # get the id of the user
    # check if the id of the user exists
    # if not give an error
    # query the user's role permission
    # return the output
    
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
        "first_name": current_user.Firstname,
        "last_name": current_user.Lastname,
        "role": role_name,
        "permissions": permission_array
            },200

# Possible functions to make for a helper module
# data input checker, user permission checker
# user id exists, role id exists, password creation rules checker
# json data format checker function