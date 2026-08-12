from flask_login import login_required, current_user
from app import app
import threading
from app.api.system import system_bp
from app.api.helper.database_access.permissions import require_permission
from app.network_discovery import discover_network_create_hosts
from app.logging.network_discovery_status import get_network_discovery_status

discovery_thread = None

@system_bp.post('/discover/start')
@login_required
@require_permission('system.discover')
def start_discover_network():
    global discovery_thread

    if discovery_thread is not None and discovery_thread.is_alive():
        return {"message": "Network discovery is already running."}, 400

    discovery_thread = threading.Thread(
        daemon=True,
        target=discover_network_create_hosts,
        args=(app, current_user.UserID)
    )

    discovery_thread.start()
    return {"message": "Network discovery started."}, 202


@system_bp.get('/discover/status')
@login_required
@require_permission('system.discover')
def discover_network_status():

    if discovery_thread is None:
        return {"message": "There is no network discovery occuring right now."}, 200

    discover_info = get_network_discovery_status()

    return {
        "Status": discover_info.Status.value,
        "Progress": discover_info.Progress,
        "Message": discover_info.Message,
        "Error": discover_info.Error,
    }, 200