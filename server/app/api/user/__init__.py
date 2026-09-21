from flask import Blueprint

user_bp = Blueprint('user', __name__, url_prefix='/user')

from app.api.user import login
from app.api.user import management
from app.api.user import preferences