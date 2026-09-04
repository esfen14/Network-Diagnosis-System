"""
manager.py — Plugin Manager API routes (Phase 2: scan trigger only;
Phase 3 adds the GET inventory/details/history/commands/dependencies
routes into this same file, per the Implementation Plan).

Routes
------
POST /plugin/scan          - Start a background filesystem scan
GET  /plugin/scan/status   - Latest scan status

Pattern matches app/api/system/network_discovery.py exactly: a
module-level background thread + a status table polled via GET,
rather than a synchronous response. Unlike Network Discovery/NCPA,
there is deliberately no POST /plugin/scan/stop — a local directory
scan is expected to finish in a few seconds, so a stop/cancel affordance
was judged not worth the extra scope for this phase.
"""
from flask_login import login_required, current_user
from flask import current_app
import threading

from app.api.plugin import plugin_bp
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
