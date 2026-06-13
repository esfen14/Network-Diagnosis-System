from flask import Blueprint
from flask_login import login_user, logout_user
from flask import request
import sqlalchemy as sa
from app import db
from app.system_models import User

login_bp = Blueprint('login', __name__)


@login_bp.route('/login', methods=['POST'])
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
        {"message": "decription"}
        html 
    """
    data = request.get_json()
    
    if not data:
        return{
            "message": "No JSON data provided"
        }, 400

    email = data.get("email")
    password = data.get("password")
    
    if not email or not password:
        return{
            "message": "Email and Password are required"
        }, 400

    user = db.session.scalar(
        sa.select(User).where(User.Email == email)
    )
    
    if user is None or not user.check_password(password):
        return{
            "message":"Invalid username or password"
        }, 401
    
    login_user(user)
    return {
        "message": "logged in"
    }, 200

@login_bp.route('/logout', methods=['POST'])
def logout():
    logout_user()
    return {
        "message": "user logged out"
    }, 200