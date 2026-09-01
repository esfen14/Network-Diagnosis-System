from flask import Blueprint

system_bp = Blueprint('system', __name__, url_prefix='/system')

from app.api.system import network_discovery
from app.api.system import log
from app.api.system import report
from app.api.system import settings
from app.api.system import ncpa_deployment
from app.api.system import dashboard
from app.api.system import network_health
from app.api.system import network_hosts
from app.api.system import network_services
from app.api.system import statistics
from app.api.system import notifications
from app.api.system import history
