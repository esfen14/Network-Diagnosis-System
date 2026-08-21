from flask import Blueprint

system_bp = Blueprint('system', __name__, url_prefix='/api/settings')

from app.api.system import settings