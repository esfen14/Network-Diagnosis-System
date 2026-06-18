import sqlalchemy as sa
from app import db
from app.system_models import User, Role, Permission, UserStatus
from email_validator import validate_email, EmailNotValidError

def valid_password(password):
    MIN_PASSWORD_LENGTH = 12
    password = password.strip()
    if password.isspace():
        return {"message":"Password must not be empty."}, 400
    if len(password) < MIN_PASSWORD_LENGTH:
        return {"message":"Password must be at least "+ str(MIN_PASSWORD_LENGTH) +" characters long"}, 400
    if not any (char.isupper() for char in password):
        return {"message":"Password must contain an uppercase letter."}, 400
    if not any (char.islower() for char in password):
        return {"message":"Password must contain a lowercase letter."}, 400
    if not any (char.isdigit() for char in password):
        return {"message":"Password must contain a number."}, 400
    if not any(not char.isalnum() for char in password):
        return {"message":"Password must contain a special character."}, 400
    return None

def find_user_id(user_id):
    exists = db.session.scalar(
        sa.select(
            sa.exists()
            .where(
                User.UserID == user_id
            )
        )
    )
    return exists

def find_user_email(user_email):
    exists = db.session.scalar(
        sa.select(
            sa.exists()
            .where(
                sa.func.lower(User.Email) == user_email.lower()
            )
        )
    )
    return exists

def user_exists(user):
    exists = True
    if isinstance(user, int):
        exists = find_user_id(user)

    elif isinstance(user, str):
        exists = find_user_email(user)  

    else:
        return {"message": "Invalid Datatype."}, 400
    
    if not exists:
        return {"message": "User does not exist."}, 404
    
    return None


def find_role_id(role_id):
    exists = db.session.scalar(
        sa.select(
            sa.exists()
            .where(
                Role.RoleID == role_id
            )
        )
    ) 

    return exists
    
def find_role_name(role_name):
    exists = db.session.scalar(
        sa.select(
            sa.exists()
            .where(
                sa.func.lower(Role.Name) == role_name.lower()
            )
        )
    ) 
    return exists

def role_exists(role):
    exists = True
    if isinstance(role, int):
        exists = find_role_id(role)

    elif isinstance(role, str):
        exists = find_role_name(role)  

    else:
        return {"message": "Invalid Datatype."}, 400

    if not exists:
        return {"message": "Role does not exist."}, 404

    return None

def check_email(email):
    try:
        validate_email(email, check_deliverability=False)

    except EmailNotValidError:
        return {"message": "Not a valid email."}, 400
    
    exists = db.session.scalar(
            sa.select(
                sa.exists()
                .where(
                    User.Email == email
                )
            )
        )
    
    if exists:
        return {"message": "That email is already taken."}, 400
        
    return None
    

def find_permission_id(permission_id):
    exists = db.session.scalar(
        sa.select(
            sa.exists() 
            .where(
                Permission.PermissionID == permission_id
            )
        )
    )
    
    return exists

def find_permission_name(permission_name):
    exists = db.session.scalar(
        sa.select(
            sa.exists() 
            .where(
                Permission.Name == permission_name
            )
        )
    )
    
    return exists


def permission_exists(permission):
    
    exists = True
    if isinstance(permission, int):
        exists = find_permission_id(permission)

    elif isinstance(permission, str):
        exists = find_permission_name(permission)  
    
    else:
        return {"message": "Invalid Datatype."}, 400
    
    if not exists:
        return {"message": "Permission does not exist."}, 404
    
    return None

def valid_json(data):
    if data is None:
        return {"message": "No JSON data provided"}, 400

    if not isinstance(data,dict):
        return {"message": "JSON body must be an object"}, 400
    
    if len(data) ==  0:
        return {"message": "JSON body must not be empty"}, 400
    
    return None

def require_fields(data, required_fields):
    """_summary_

    Args:
        data (json or dict): the data from the fronend
        required_fields (dict): a dict of the fields and their datatype

    Returns:
        message: the message reply
        http status code: tells if there is an error
    """
    missing = []
    invalid_types = []

    for field, expected_type in required_fields.items():
        if field not in data:
            missing.append(field)
            continue

        if not isinstance(data[field], expected_type):
            invalid_types.append(
                f"{field} (expected {expected_type.__name__})"
            )

    if missing:
        return {
            "message": f"Fields: {', '.join(missing)} are required"
        }, 400

    if invalid_types:
        return {
            "message": f"Invalid field types: {', '.join(invalid_types)}"
        }, 400

    return None


def check_user_status(status):
    status = status.strip().lower()
    for main_status in UserStatus:
        if status == main_status.value.lower():
            return None
    return {"message": "Not a valid status"}, 400