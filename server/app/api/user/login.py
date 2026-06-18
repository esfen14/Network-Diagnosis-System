from flask import Blueprint
from flask_login import login_user, logout_user, current_user
from flask import request
import sqlalchemy as sa
from app import db
from app.system_models import User
from app.api.helper.validation import valid_json, require_fields
from email_validator import validate_email, EmailNotValidError

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
    
    error = valid_json(data)

    if error is not None:
        return error

    fields = {
        "email": str,
        "password": str
    }
    
    error = require_fields(data, fields)

    if error is not None:
        return error

    email = data.get("email")
    password = data.get("password")
    
    try:
       validate_email(email, check_deliverability=False) 
    except EmailNotValidError:
        return {"message": "Invalid email."}
   
    normalized_email = validate_email(email)
     
    user = db.session.scalar(
        sa.select(User).where(User.Email == normalized_email)
    )
    
    if user is None or not user.check_password(password):
        return{
            "message": "Invalid username or password."
        }, 401
    
    login_user(user)
    return {
        "message": "User logged in."
    }, 200

@user_bp.post('/logout')
def logout():
    logout_user()
    return {
        "message": "User logged out."
    }, 200