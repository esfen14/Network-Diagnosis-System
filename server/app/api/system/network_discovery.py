from flask_login import login_required, current_user
from flask import current_app
from app import app, db
import threading
from app.api.system import system_bp
from app.api.helper import success, error
from app.api.helper.database_access.permissions import require_permission
from app.network_discovery import discover_network_create_hosts
from app.logging.network_discovery_status import get_network_discovery_status
from app.system_models import NetworkDiscovery
import sqlalchemy as sa

discovery_thread = None
discovery_thread_stop_event = threading.Event()


@system_bp.post('/discover/start')
@login_required
@require_permission('system.discover')
def start_discover_network():
    global discovery_thread

    if discovery_thread is not None and discovery_thread.is_alive():
        return error("Network discovery is already running.", 400)

    discovery_thread_stop_event.clear()
    discovery_thread = threading.Thread(
        daemon=True,
        target=discover_network_create_hosts,
        args=(app,
              current_user.UserID,
              discovery_thread_stop_event
              )
    )

    discovery_thread.start()
    return success(message="Network discovery started.", status=202)


@system_bp.post('/network-discovery/stop')
@login_required
@require_permission('network.discovery')
def stop_network_discovery():
    global discovery_thread

    if discovery_thread is None or not discovery_thread.is_alive():
        return error("There is no network discovery running.", 400)

    discovery_thread_stop_event.set()
    return success(message="Network discovery stop requested.")


@system_bp.get('/discover/status')
@login_required
@require_permission('system.discover')
def discover_network_status():
    try:
        discover_info = get_network_discovery_status()

        if discover_info is None:
            return success(message="No network discovery has occurred yet.")

        return success({
            "id": discover_info.DiscoveryStatusID,
            "status": discover_info.Status.value,
            "progress": discover_info.Progress,
            "message": discover_info.Message,
            "start_at": discover_info.Start_At.isoformat(),
            "completed_at": (
                discover_info.Completed_At.isoformat()
                if discover_info.Completed_At else None
            ),
            "error": discover_info.Error,
        })

    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while fetching discovery status."
        )
        return error("An unexpected error occurred.", 500)
