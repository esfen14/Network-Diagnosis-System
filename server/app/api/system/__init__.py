from flask import Blueprint

system_bp = Blueprint('system', __name__, url_prefix='/system')

from app.api.system import network_discovery
from app.api.system import logs
from app.api.system import report
from app.api.system import settings