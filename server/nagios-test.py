from app import app
from app.nagios.status import get_status

with app.app_context():
    get_status()