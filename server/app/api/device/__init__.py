from flask import Blueprint

device_bp = Blueprint('device', __name__, url_prefix='/device')

from app.api.device import inventory
from app.api.device import topology