from flask_login import login_user, logout_user, current_user, login_required
from flask import request
from app.api.helper import(
    validate_json_data,
    validate_json_fields,
    validate_user_email,
    get_user_by_email,
    normalize_email
)
from app.api.user import user_bp

@user_bp.post('/login')
def login():
    """_summary_
        This function is for logging in user along with checking if
        the log in credentials are valid for logging in.
        
    Expects:
    {
        "email": "email",
        "password": "password",
    }
    
    Returns:
        {"message": "decription"}, http response code
    """

    if current_user.is_authenticated:
        return {"message": "User is already logged in."}, 200
    
    data = request.get_json()
    
    error = validate_json_data(data)

    if error is not None:
        return error

    fields = {
        "email": str,
        "password": str
    }
    
    error = validate_json_fields(data, fields)
    if error is not None:
        return error

    email = data.get("email")
    password = data.get("password")
    
    error = validate_user_email(email)
    if error is not None:
        return error
   
    normalized_email = normalize_email(email)
     
    user = get_user_by_email(normalized_email)
    
    if user is None or not user.check_password(password):
        return{
            "message": "Invalid username or password."
        }, 401
    
    login_user(user)
    return {
        "message": "User logged in."
    }, 200

@user_bp.post('/logout')
@login_required
def logout():
    logout_user()
    return {
        "message": "User logged out."
    }, 200