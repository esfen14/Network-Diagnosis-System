from app.system_models import UserStatus
from email_validator import validate_email, EmailNotValidError
from .database_access import *
from .responses import error

"""
This is a separation of concern that requires checking of input
"""
# ================= PASSWORD  =====================
def validate_password(password):
    MIN_PASSWORD_LENGTH = 12
    password = password.strip()
    if not password:
        return error("Password must not be empty.", 400)
    if len(password) < MIN_PASSWORD_LENGTH:
        return error(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long", 400)
    if not any(char.isupper() for char in password):
        return error("Password must contain an uppercase letter.", 400)
    if not any(char.islower() for char in password):
        return error("Password must contain a lowercase letter.", 400)
    if not any(char.isdigit() for char in password):
        return error("Password must contain a number.", 400)
    if not any(not char.isalnum() for char in password):
        return error("Password must contain a special character.", 400)
    return None

def validate_password_is_same(password, confirm_password):
    if not password == confirm_password:
        return error("Password is not the same.", 400)
    return None

# ================= USER  =========================
def validate_user_exists(user):
    
    exists = True
    if isinstance(user, int):
        exists = exists_user_by_id(user)
    else:
        return error("Invalid Datatype.", 400)
    
    if not exists:
        return error("User does not exist.", 404)
    
    return None

def validate_user_not_exists(user):
    
    exists = True
    if isinstance(user, int):
        exists = exists_user_by_id(user)
    else:
        return error("Invalid Datatype.", 400)
    
    if exists:
        return error("User already exists.", 409)
    
    return None

# ================= ROLE  ========================
def validate_role_exists(role):
    
    exists = True
    if isinstance(role, int):
        exists = exists_role_by_id(role)
    else:
        return error("Invalid Datatype.", 400)
    
    if not exists:
        return error("Role does not exist.", 404)
    
    return None

def validate_role_not_exists(role):
    exists = True
    if isinstance(role, int):
        exists = exists_role_by_id(role)
    elif isinstance(role, str) and not role.isdigit():
        exists = exists_role_by_name(role)
    else:
        return error("Invalid Datatype.", 400)
    
    if exists:
        return error("Role already exists.", 409)
    
    return None

def validate_role_name_available(role):
    if exists_role_by_name(role):
        return error("That role name is already taken.", 409)
    return None

# ================= PERMISSION  ==================
def validate_permission_exists(permission):
    
    exists = True
    if isinstance(permission, int):
        exists = exists_permission_by_id(permission)
    else:
        return error("Invalid Datatype.", 400)
    
    if not exists:
        return error("Permission does not exist.", 404)
    
    return None

# ================== JSON  =======================
def validate_json_data(data):
    if data is None:
        return error("No JSON data provided", 400)

    if not isinstance(data, dict):
        return error("JSON body must be an object", 400)
    
    if len(data) == 0:
        return error("JSON body must not be empty", 400)
    
    return None

def validate_json_fields(data, required_fields):
    """
    Args:
        data (json or dict): the data from the frontend
        required_fields (dict): a dict of the fields and their datatype

    Returns:
        tuple or None: (response, status_code) if error, None if valid
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
        return error(f"Fields: {', '.join(missing)} are required", 400)

    if invalid_types:
        return error(f"Invalid field types: {', '.join(invalid_types)}", 400)

    return None

# ================ USERSTATUS ====================
def validate_userstatus(status):
    status = status.strip().lower()
    for main_status in UserStatus:
        if status == main_status.value.lower():
            return None
    return error("Not a valid status", 400)

# =================== EMAIL ======================
def validate_user_email(email):
    try:
        validate_email(email, check_deliverability=False)
        return None
    except EmailNotValidError:
        return error("Not a valid email.", 400)

def validate_email_available(email):
    if exists_user_by_email(email):
        return error("Email already exists.", 409)
    return None
