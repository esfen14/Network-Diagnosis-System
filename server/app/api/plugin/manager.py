"""
manager.py — Plugin Manager API routes.

Routes
------
POST /plugin/scan            - Start a background filesystem scan (Phase 2)
GET  /plugin/scan/status     - Latest scan status (Phase 2)
GET  /plugin                 - Paginated plugin inventory (Phase 3)
GET  /plugin/summary         - Landing page summary counts (Phase 3)
GET  /plugin/<id>            - Single plugin's full details (Phase 3)
GET  /plugin/history         - Global plugin history, optional ?plugin_id= (Phase 3)
GET  /plugin/<id>/commands   - A plugin's commands + active overrides (Phase 3)
GET  /plugin/<id>/dependencies - A plugin's dependencies (Phase 3)

The scan routes (Phase 2) match app/api/system/network_discovery.py's
background-thread + status-polling pattern. The Phase 3 read routes
match app/api/system/log.py's pagination/filter/sort convention
(page, per_page, sort_by, order, search query params). All actual
querying lives in service.py — these routes only parse/validate
request args and format the response.
"""
from flask_login import login_required, current_user
from flask import current_app, request
import threading

from app.api.plugin import plugin_bp
from app.api.plugin import service
from app.api.helper import success, error
from app.api.helper.database_access.permissions import require_permission
from app.api.plugin.scanner import scan_plugin_directory, sync_plugin_inventory, NAGIOS_PLUGIN_DIR
from app.logging.plugin_scan_status import (
    create_plugin_scan_status,
    update_plugin_scan_status,
    get_plugin_scan_status,
)
from app.plugin_models import PluginScanStatusValue
from datetime import datetime, timezone
from app import app, db

scan_thread = None


def _run_scan(flask_app, user_id, plugin_scan_status_id):
    """
    Background worker: performs the actual scan + inventory sync,
    then updates the PluginScanStatus row with the outcome.

    Runs in its own thread, so it needs its own Flask app context
    (matches discover_network_create_hosts's pattern).
    """
    with flask_app.app_context():
        try:
            scan_results = scan_plugin_directory(NAGIOS_PLUGIN_DIR)
            summary = sync_plugin_inventory(scan_results)

            update_plugin_scan_status(
                plugin_scan_status_id,
                PluginScanStatusValue.SUCCESS,
                100,
                (
                    f"Scan complete: {summary['created']} added, "
                    f"{summary['updated']} updated, "
                    f"{summary['unchanged']} unchanged."
                ),
                completed_at=datetime.now(timezone.utc),
            )

        except FileNotFoundError:
            update_plugin_scan_status(
                plugin_scan_status_id,
                PluginScanStatusValue.FAILED,
                100,
                "Plugin scan failed.",
                completed_at=datetime.now(timezone.utc),
                error=f"Plugin directory not found: {NAGIOS_PLUGIN_DIR}",
            )

        except Exception as e:
            db.session.rollback()
            flask_app.logger.exception("Plugin scan failed.")
            update_plugin_scan_status(
                plugin_scan_status_id,
                PluginScanStatusValue.FAILED,
                100,
                "Plugin scan failed.",
                completed_at=datetime.now(timezone.utc),
                error=str(e),
            )


@plugin_bp.post('/scan')
@login_required
@require_permission('plugin.scan')
def start_plugin_scan():
    """
    Start a background filesystem scan of the Nagios plugin directory.

    Only one scan can run at a time; a second request while one is
    active is rejected.

    Inputs:
        None (no request body or query parameters).

    Returns (JSON):
        {
            "success": true,
            "message": "Plugin scan started."
        }

    Errors:
        400 - A scan is already running.
        500 - Unexpected server error (e.g. could not create the
              status record).
    """
    global scan_thread

    if scan_thread is not None and scan_thread.is_alive():
        return error("A plugin scan is already running.", 400)

    plugin_scan_status = create_plugin_scan_status(current_user.UserID)
    if plugin_scan_status is None:
        return error("Could not start plugin scan.", 500)

    scan_thread = threading.Thread(
        daemon=True,
        target=_run_scan,
        args=(app, current_user.UserID, plugin_scan_status.PluginScanStatusID),
    )
    scan_thread.start()

    return success(message="Plugin scan started.", status=202)


@plugin_bp.get('/scan/status')
@login_required
@require_permission('plugin.scan')
def plugin_scan_status_route():
    """
    Return the current or most recent plugin scan status.

    Inputs:
        None.

    Returns (JSON):
        On success (HTTP 200):
        {
            "success": true,
            "data": {
                "id":           int,
                "status":       str ("Running" | "Success" | "Failed"),
                "progress":     int (0-100),
                "message":      str,
                "start_at":     str (ISO-8601),
                "completed_at": str (ISO-8601) | null,
                "error":        str | null
            }
        }

        When no scan has occurred yet:
        {
            "success": true,
            "message": "No plugin scan has occurred yet."
        }

    Errors:
        500 - Unexpected server error.
    """
    try:
        scan_info = get_plugin_scan_status()

        if scan_info is None:
            return success(message="No plugin scan has occurred yet.")

        return success({
            "id": scan_info.PluginScanStatusID,
            "status": scan_info.Status.value,
            "progress": scan_info.Progress,
            "message": scan_info.Message,
            "start_at": scan_info.Start_At.isoformat(),
            "completed_at": (
                scan_info.Completed_At.isoformat()
                if scan_info.Completed_At else None
            ),
            "error": scan_info.Error,
        })

    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while fetching plugin scan status."
        )
        return error("An unexpected error occurred.", 500)


# ==========================================================
# PLUGIN INVENTORY
# ==========================================================

@plugin_bp.get('')
@login_required
@require_permission('plugin.view')
def plugin_inventory():
    """
    Retrieve the paginated plugin inventory (UI Flow Section 7).

    **Query Parameters**

    page (int, default 1)
    per_page (int, default 10, max 100)
    sort_by (str, default "name"): one of "name", "type", "status",
        "version", "updated_at"
    order (str, default "asc"): "asc" or "desc"
    search (str, optional): matched against plugin name/display name
    type (str, optional): "Nagios" or "Custom"
    status (str, optional): any PluginStatus value (e.g. "Ready",
        "Active", "Disabled", "Update Available"), or the literal
        "Failed" to match any of Validation/Dependency/Installation/
        Configuration Failed at once.

    **Returns (JSON via success())**

    .. code-block:: json

        {
            "success": true,
            "data": {
                "items": [
                    {
                        "id": 1,
                        "name": "check_ping",
                        "display_name": null,
                        "category": null,
                        "type": "Nagios",
                        "source": "Baseline (ISO)",
                        "status": "Ready",
                        "current_version": "2.4.12",
                        "updated_at": "2026-08-25T02:30:00+00:00"
                    }
                ],
                "page": 1, "per_page": 10, "pages": 1, "total": 1,
                "has_next": false, "has_prev": false
            }
        }

    **Errors**

    * ``400`` - invalid sort field, order, page, per_page, type, or status.
    * ``500`` - unexpected internal error (logged with traceback).
    """
    try:
        page = request.args.get("page", default=1, type=int)
        per_page = request.args.get("per_page", default=10, type=int)
        sort_by = request.args.get("sort_by", default="name", type=str)
        order = request.args.get("order", default="asc", type=str)
        search = request.args.get("search", default="", type=str)
        plugin_type = request.args.get("type", default=None, type=str)
        status = request.args.get("status", default=None, type=str)

        data = service.get_plugin_inventory(
            page=page, per_page=per_page, search=search,
            plugin_type=plugin_type, status=status,
            sort_by=sort_by, order=order,
        )
        return success(data)

    except service.InvalidQueryError as e:
        return error(str(e), 400)
    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while retrieving the plugin inventory."
        )
        return error("An unexpected error occurred.", 500)


# ==========================================================
# PLUGIN SUMMARY
# ==========================================================

@plugin_bp.get('/summary')
@login_required
@require_permission('plugin.view')
def plugin_summary():
    """
    Retrieve landing page summary counts (UI Flow Section 6).

    **Returns (JSON via success())**

    .. code-block:: json

        {
            "success": true,
            "data": {
                "installed_plugins": 12,
                "active_capabilities": 0,
                "custom_plugins": 1,
                "updates_available": 2,
                "validation_issues": 0
            }
        }

    **Errors**

    * ``500`` - unexpected internal error (logged with traceback).
    """
    try:
        return success(service.get_plugin_summary())
    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while retrieving the plugin summary."
        )
        return error("An unexpected error occurred.", 500)


# ==========================================================
# PLUGIN HISTORY (global, optional plugin_id filter)
# ==========================================================

@plugin_bp.get('/history')
@login_required
@require_permission('plugin.view')
def plugin_history():
    """
    Retrieve global plugin history (UI Flow Section 24), optionally
    filtered to one plugin via ?plugin_id=.

    **Query Parameters**

    page (int, default 1)
    per_page (int, default 10, max 100)
    sort_by (str, default "performed_at"): "id" or "performed_at"
    order (str, default "desc"): "asc" or "desc"
    plugin_id (int, optional): restrict to one plugin's history

    **Returns (JSON via success())**

    .. code-block:: json

        {
            "success": true,
            "data": {
                "items": [
                    {
                        "id": 1,
                        "plugin_id": 3,
                        "plugin_name": "check_snmp",
                        "action": "Command Override",
                        "administrator": "Jane Doe",
                        "result": "Success",
                        "performed_at": "2026-08-25T02:40:00+00:00",
                        "message": "Override applied."
                    }
                ],
                "page": 1, "per_page": 10, "pages": 1, "total": 1,
                "has_next": false, "has_prev": false
            }
        }

    **Errors**

    * ``400`` - invalid sort field, order, page, or per_page.
    * ``500`` - unexpected internal error (logged with traceback).
    """
    try:
        page = request.args.get("page", default=1, type=int)
        per_page = request.args.get("per_page", default=10, type=int)
        sort_by = request.args.get("sort_by", default="performed_at", type=str)
        order = request.args.get("order", default="desc", type=str)
        plugin_id = request.args.get("plugin_id", default=None, type=int)

        data = service.get_plugin_history(
            page=page, per_page=per_page, plugin_id=plugin_id,
            sort_by=sort_by, order=order,
        )
        return success(data)

    except service.InvalidQueryError as e:
        return error(str(e), 400)
    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while retrieving plugin history."
        )
        return error("An unexpected error occurred.", 500)


# ==========================================================
# PLUGIN DETAILS
# ==========================================================

@plugin_bp.get('/<int:plugin_id>')
@login_required
@require_permission('plugin.view')
def plugin_details(plugin_id):
    """
    Retrieve a single plugin's full details (UI Flow Section 8).

    **Returns (JSON via success())**

    .. code-block:: json

        {
            "success": true,
            "data": {
                "id": 1,
                "name": "check_ping",
                "display_name": null,
                "description": null,
                "author": null,
                "category": null,
                "type": "Nagios",
                "source": "Baseline (ISO)",
                "status": "Ready",
                "current_version": "2.4.12",
                "executable_path": "/usr/local/nagios/libexec/check_ping",
                "created_at": "2026-08-25T02:00:00+00:00",
                "updated_at": "2026-08-25T02:00:00+00:00",
                "commands_count": 1,
                "dependencies_count": 0,
                "monitoring_usage": {
                    "services": 4,
                    "devices": 2,
                    "placeholder": true,
                    "note": "Target linkage not implemented until Phase 10 (Monitoring Configuration)."
                }
            }
        }

    **Errors**

    * ``404`` - no plugin with that id.
    * ``500`` - unexpected internal error (logged with traceback).
    """
    try:
        data = service.get_plugin_details(plugin_id)
        if data is None:
            return error("Plugin not found.", 404)
        return success(data)
    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while retrieving plugin details."
        )
        return error("An unexpected error occurred.", 500)


# ==========================================================
# PLUGIN COMMANDS
# ==========================================================

@plugin_bp.get('/<int:plugin_id>/commands')
@login_required
@require_permission('plugin.view')
def plugin_commands(plugin_id):
    """
    Retrieve a plugin's commands, each with its currently active
    override (if any) merged in (UI Flow Sections 15-16).

    **Returns (JSON via success())**

    .. code-block:: json

        {
            "success": true,
            "data": [
                {
                    "id": 1,
                    "command_name": "check_snmp",
                    "default_command": "check_snmp -H $HOSTADDRESS$ -o $ARG1$",
                    "active_command": "check_snmp -H $HOSTADDRESS$ -o $ARG1$ -w 80 -c 90",
                    "is_overridden": true,
                    "is_default": true
                }
            ]
        }

    **Errors**

    * ``404`` - no plugin with that id.
    * ``500`` - unexpected internal error (logged with traceback).
    """
    try:
        data = service.get_plugin_commands(plugin_id)
        if data is None:
            return error("Plugin not found.", 404)
        return success(data)
    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while retrieving plugin commands."
        )
        return error("An unexpected error occurred.", 500)


# ==========================================================
# PLUGIN DEPENDENCIES
# ==========================================================

@plugin_bp.get('/<int:plugin_id>/dependencies')
@login_required
@require_permission('plugin.view')
def plugin_dependencies(plugin_id):
    """
    Retrieve a plugin's dependencies (UI Flow Section 8).

    **Returns (JSON via success())**

    .. code-block:: json

        {
            "success": true,
            "data": [
                {
                    "id": 1,
                    "name": "net-snmp",
                    "type": "Package",
                    "required_version": null,
                    "status": "Ok"
                }
            ]
        }

    **Errors**

    * ``404`` - no plugin with that id.
    * ``500`` - unexpected internal error (logged with traceback).
    """
    try:
        data = service.get_plugin_dependencies(plugin_id)
        if data is None:
            return error("Plugin not found.", 404)
        return success(data)
    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while retrieving plugin dependencies."
        )
        return error("An unexpected error occurred.", 500)
