from flask import Blueprint

monitoring_bp = Blueprint('monitoring', __name__, url_prefix='/monitoring')

from app.api.monitoring import dashboard
from app.api.monitoring import network_health