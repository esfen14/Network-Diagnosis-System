from flask_login import login_required, current_user
from app.api.system import system_bp
from app.api.helper.database_access.permissions import require_permission
from app.network_discovery import discover_network_create_hosts

@system_bp.post('/discover')
@login_required
@require_permission('system.discover')
def start_discover_network():
    result = discover_network_create_hosts(current_user.UserID)

    return result, 200


@system_bp.get('/discover/status')
@login_required
@require_permission('system.discover')
def discover_network_status():
    return {}, 200