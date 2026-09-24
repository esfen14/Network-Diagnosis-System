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
import json

from app.api.plugin import plugin_bp
from app.api.plugin import service
from app.api.helper import success, error, validate_json_data, validate_json_fields
from app.api.helper.database_access.permissions import require_permission
from app.api.plugin.scanner import scan_plugin_directory, sync_plugin_inventory, NAGIOS_PLUGIN_DIR
from app.logging.plugin_scan_status import (
    create_plugin_scan_status,
    update_plugin_scan_status,
    get_plugin_scan_status,
)
from app.plugin_models import PluginScanStatusValue, Plugin
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


# ==========================================================
# ENABLE / DISABLE (Phase 5)
# ==========================================================

@plugin_bp.post('/<int:plugin_id>/enable')
@login_required
@require_permission('plugin.enable')
def enable_plugin_route(plugin_id):
    """
    Enable a plugin (UI Flow Section 8's [Enable] action).

    Runs Nagios's own configuration validation first
    (nagios_validator.py) — this validates Nagios's ENTIRE config, not
    anything plugin-specific, since Plugin Manager doesn't write any
    Nagios config yet (that's Phase 10). Idempotent: enabling an
    already-ENABLED or already-ACTIVE plugin succeeds with no change.

    **Inputs:** None (no request body).

    **Returns (JSON via success())**

    .. code-block:: json

        {"success": true, "data": {"id": 3, "status": "Enabled", "changed": true}}

    **Errors**

    * ``404`` - no plugin with that id.
    * ``409`` - plugin is in a state that blocks enabling (e.g. a
      *_FAILED status, or Rollback).
    * ``502`` - Nagios configuration validation failed, or the nagios
      binary isn't reachable (e.g. running on a machine without
      Nagios installed).
    * ``500`` - unexpected internal error (logged with traceback).
    """
    try:
        data = service.enable_plugin(plugin_id, current_user.UserID)
        return success(data)
    except service.PluginNotFoundError:
        return error("Plugin not found.", 404)
    except service.InvalidTransitionError as e:
        return error(e.message, 409)
    except service.NagiosValidationError as e:
        return error(f"Nagios configuration validation failed: {e.message}", 502)
    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while enabling the plugin."
        )
        return error("An unexpected error occurred.", 500)


@plugin_bp.post('/<int:plugin_id>/disable')
@login_required
@require_permission('plugin.disable')
def disable_plugin_route(plugin_id):
    """
    Disable a plugin (UI Flow Section 8's [Disable] action).

    Same Nagios validation as enable_plugin_route. Unlike Enable,
    Disable is reachable from ACTIVE (turning off a currently-active
    monitoring capability). Idempotent: disabling an already-DISABLED
    plugin succeeds with no change.

    **Inputs:** None (no request body).

    **Returns (JSON via success())**

    .. code-block:: json

        {"success": true, "data": {"id": 3, "status": "Disabled", "changed": true}}

    **Errors**

    * ``404`` - no plugin with that id.
    * ``409`` - plugin is in a state that blocks disabling.
    * ``502`` - Nagios configuration validation failed, or the nagios
      binary isn't reachable.
    * ``500`` - unexpected internal error (logged with traceback).
    """
    try:
        data = service.disable_plugin(plugin_id, current_user.UserID)
        return success(data)
    except service.PluginNotFoundError:
        return error("Plugin not found.", 404)
    except service.InvalidTransitionError as e:
        return error(e.message, 409)
    except service.NagiosValidationError as e:
        return error(f"Nagios configuration validation failed: {e.message}", 502)
    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while disabling the plugin."
        )
        return error("An unexpected error occurred.", 500)


# ==========================================================
# COMMAND MANAGEMENT (Phase 6)
# ==========================================================

@plugin_bp.post('/<int:plugin_id>/commands/<int:command_id>/override')
@login_required
@require_permission('plugin.command_override')
def override_command_route(plugin_id, command_id):
    """
    Save a command override (UI Flow Section 16's [Save Override]).

    DB-only — does not touch live nagios.cfg (that happens later, in
    Phase 10's Apply step). The override string is validated for
    shell-injection risk (see command_validator.py) since it will
    eventually be executed by Nagios once applied.

    **Inputs (JSON body)**

    .. code-block:: json

        {"override_command": "check_snmp -H $HOSTADDRESS$ -o $ARG1$ -w 80 -c 90"}

    **Returns (JSON via success())**

    .. code-block:: json

        {
            "success": true,
            "data": {
                "id": 1,
                "command_name": "check_snmp",
                "default_command": "check_snmp -H $HOSTADDRESS$ -o $ARG1$",
                "active_command": "check_snmp -H $HOSTADDRESS$ -o $ARG1$ -w 80 -c 90",
                "is_overridden": true,
                "is_default": true
            }
        }

    **Errors**

    * ``400`` - missing/invalid request body, or the command string
      failed validation (empty, too long, or contains a disallowed
      shell metacharacter).
    * ``404`` - no plugin or command with that id (or the command
      doesn't belong to that plugin).
    * ``500`` - unexpected internal error (logged with traceback).
    """
    try:
        body = request.get_json(silent=True) or {}
        override_command_text = body.get("override_command")

        if not override_command_text or not isinstance(override_command_text, str):
            return error("override_command is required.", 400)

        data = service.override_command(plugin_id, command_id, override_command_text, current_user.UserID)
        return success(data)

    except service.PluginNotFoundError:
        return error("Plugin not found.", 404)
    except service.CommandNotFoundError:
        return error("Command not found for this plugin.", 404)
    except service.InvalidCommandError as e:
        return error(e.message, 400)
    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while saving the command override."
        )
        return error("An unexpected error occurred.", 500)


@plugin_bp.post('/<int:plugin_id>/commands/<int:command_id>/restore-default')
@login_required
@require_permission('plugin.command_restore')
def restore_default_command_route(plugin_id, command_id):
    """
    Restore a command's default (UI Flow Sections 15/16's
    [Restore Default]).

    Idempotent: if there's no active override already, succeeds with
    no change.

    **Inputs:** None (no request body).

    **Returns (JSON via success())**

    .. code-block:: json

        {
            "success": true,
            "data": {
                "id": 1,
                "command_name": "check_snmp",
                "default_command": "check_snmp -H $HOSTADDRESS$ -o $ARG1$",
                "active_command": "check_snmp -H $HOSTADDRESS$ -o $ARG1$",
                "is_overridden": false,
                "is_default": true,
                "changed": true
            }
        }

    **Errors**

    * ``404`` - no plugin or command with that id.
    * ``500`` - unexpected internal error (logged with traceback).
    """
    try:
        data = service.restore_default_command(plugin_id, command_id, current_user.UserID)
        return success(data)
    except service.PluginNotFoundError:
        return error("Plugin not found.", 404)
    except service.CommandNotFoundError:
        return error("Command not found for this plugin.", 404)
    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while restoring the default command."
        )
        return error("An unexpected error occurred.", 500)


# ==========================================================
# VALIDATION (Phase 7)
# ==========================================================

@plugin_bp.post('/<int:plugin_id>/validate')
@login_required
@require_permission('plugin.validate')
def validate_plugin_route(plugin_id):
    """
    Validate a plugin's executable, permissions, and that it can
    actually run (UI Flow Section 8's [Validate] action).

    Does NOT validate Nagios configuration or dependencies — those are
    separate, distinct steps (see plugin_validator.py's docstring).
    Updates Plugin.Status: failing checks set VALIDATION_FAILED;
    passing checks reset a previously VALIDATION_FAILED plugin to
    READY; any other status is left unchanged.

    **Inputs:** None (no request body).

    **Returns (JSON via success())**

    .. code-block:: json

        {
            "success": true,
            "data": {
                "plugin_id": 3,
                "is_valid": false,
                "status": "Validation Failed",
                "checks": {
                    "executable": {"passed": true, "message": "..."},
                    "permissions": {
                        "passed": false,
                        "message": "File is world-writable (0777) — any user could modify this plugin.",
                        "mode": "0777",
                        "world_writable": true
                    },
                    "execution": {
                        "passed": true,
                        "message": "Executed successfully (exit code 0).",
                        "exit_code": 0,
                        "output": "check_snmp v2.4.12 (nagios-plugins 2.4.12)"
                    }
                }
            }
        }

    **Errors**

    * ``404`` - no plugin with that id.
    * ``500`` - unexpected internal error (logged with traceback).
    """
    try:
        data = service.validate_plugin(plugin_id, current_user.UserID)
        return success(data)
    except service.PluginNotFoundError:
        return error("Plugin not found.", 404)
    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while validating the plugin."
        )
        return error("An unexpected error occurred.", 500)


# ==========================================================
# CUSTOM PLUGINS (Phase 8)
# ==========================================================

@plugin_bp.post('/custom')
@login_required
@require_permission('plugin.custom_add')
def register_custom_plugin_route():
    """
    Upload and register a custom plugin (UI Flow Sections 9-11: Add
    Custom Plugin -> Custom Plugin Validation -> Custom Plugin
    Registered), in one atomic request.

    Confirmed design: unlike the UI mockup's two separate buttons
    ([Validate Plugin] then [Register Plugin]), this is a single
    endpoint — no server-side staging state is kept across requests.
    On validation failure, nothing is persisted; the response still
    returns the full 7-check structured results either way.

    **Inputs:** multipart/form-data (NOT JSON — this is a file upload)

    - ``file`` (required): the plugin executable.
    - ``name`` (required): becomes Plugin.Name (must be unique) and
      the installed filename.
    - ``version`` (optional): defaults to "1.0.0" if omitted.
    - ``description``, ``author`` (optional).
    - ``plugin_type`` (optional, default "Nagios"): "Nagios" or "Custom".
    - ``command_name`` (required).
    - ``command_definition`` (required): validated by command_validator.py.
    - ``dependencies`` (optional): a JSON-encoded string, e.g.
      ``[{"name": "net-snmp", "type": "Package"}]``. Each ``type``
      must be a real DependencyType value.

    **Returns (JSON via success())**

    .. code-block:: json

        {
            "success": true,
            "data": {
                "success": true,
                "checks": [
                    {"name": "Plugin file detected", "passed": true, "message": "..."},
                    {"name": "Executable permission", "passed": true, "message": "..."},
                    {"name": "Plugin execution test", "passed": true, "message": "..."},
                    {"name": "Command definition detected", "passed": true, "message": "..."},
                    {"name": "Metadata valid", "passed": true, "message": "..."},
                    {"name": "Dependency check", "passed": true, "message": "..."},
                    {"name": "Nagios compatibility", "passed": true, "message": "..."}
                ],
                "plugin": {"id": 9, "name": "check_company", "status": "Ready", "...": "..."},
                "message": "Custom plugin 'check_company' registered successfully."
            }
        }

        On validation failure, "plugin" is null and "success" is false
        — this is still a 200 response, not an error, since the
        request itself was valid; the SUBMITTED PLUGIN failed
        validation. Matches UI Flow's "Plugin Validation Failed" screen
        being a normal outcome, not a server error. Confirmed against
        client/src/types/plugin.ts (integration branch)'s
        CustomPluginUploadResult / CustomPluginCheckResult — this
        shape (success/checks-as-array/message) is deliberately
        different from validate_custom_plugin_submission()'s internal
        shape (is_valid/checks-as-dict) to match that contract exactly.

    **Errors**

    * ``400`` - no file provided, invalid filename, file too large,
      invalid plugin_type, malformed dependencies JSON, or an invalid
      dependency type within it.
    * ``409`` - a plugin with that name already exists, or a file with
      that name already exists in the Nagios plugin directory.
    * ``500`` - unexpected internal error (logged with traceback).
    """
    try:
        if "file" not in request.files or request.files["file"].filename == "":
            return error("No file provided.", 400)

        name = request.form.get("name", "").strip()
        version = request.form.get("version", "").strip() or None
        description = request.form.get("description", "").strip() or None
        author = request.form.get("author", "").strip() or None
        plugin_type = request.form.get("plugin_type", "Nagios").strip()
        command_name = request.form.get("command_name", "").strip()
        command_definition = request.form.get("command_definition", "").strip()

        dependencies_raw = request.form.get("dependencies", "")
        dependencies = []
        if dependencies_raw:
            try:
                dependencies = json.loads(dependencies_raw)
                if not isinstance(dependencies, list):
                    raise ValueError
            except (json.JSONDecodeError, ValueError):
                return error("'dependencies' must be a JSON array.", 400)

        data = service.register_custom_plugin(
            file_storage=request.files["file"],
            name=name, version=version, description=description, author=author,
            plugin_type=plugin_type, command_name=command_name,
            command_definition=command_definition, dependencies=dependencies,
            user_id=current_user.UserID,
        )
        return success(data)

    except service.InvalidFilenameError as e:
        return error(e.message, 400)
    except service.UploadTooLargeError as e:
        return error(e.message, 400)
    except ValueError as e:
        return error(str(e), 400)
    except service.NameCollisionError as e:
        return error(e.message, 409)
    except service.PluginNameTakenError as e:
        return error(e.message, 409)
    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while registering the custom plugin."
        )
        return error("An unexpected error occurred.", 500)


# ==========================================================
# UPDATES (Phase 9)
# ==========================================================

@plugin_bp.post('/<int:plugin_id>/update')
@login_required
@require_permission('plugin.update')
def update_plugin_route(plugin_id):
    """
    Update a plugin from an archive (UI Flow Sections 19-21).

    Confirmed design: failure does NOT auto-rollback — it leaves the
    plugin in Status=Rollback, awaiting POST .../update/rollback
    (Section 23's explicit [Rollback] button).

    **Inputs:** multipart/form-data

    - ``file`` (optional): the update archive (.tar.gz/.tgz/.zip).
    - ``url`` (optional): a URL to download the archive from instead.
      Exactly one of ``file``/``url`` must be given.

    **Returns (JSON via success())**

    .. code-block:: json

        {
            "success": true,
            "data": {
                "success": true,
                "plugin_id": 3,
                "status": "Ready",
                "previous_version": "2.4.12",
                "current_version": "2.4.13",
                "rollback_available": true
            }
        }

        On a failed update (still HTTP 200 — the REQUEST succeeded,
        the update itself did not):

        .. code-block:: json

            {
                "success": true,
                "data": {
                    "success": false,
                    "status": "Rollback",
                    "rollback_available": true,
                    "failed_step": "plugin validation",
                    "validation": {"...": "..."},
                    "nagios_check": {"passed": false, "output": "..."}
                }
            }

    **Errors**

    * ``400`` - neither/both of file+url given, invalid URL (including
      SSRF-blocked private addresses), unsupported archive type,
      archive too large, unsafe archive contents (path traversal or
      symlink members), or no executable currently installed.
    * ``404`` - no plugin with that id, or the archive doesn't contain
      a file matching this plugin's name.
    * ``409`` - plugin is in a state that blocks updating.
    * ``502`` - the download failed.
    * ``500`` - unexpected internal error (logged with traceback).
    """
    try:
        file_storage = request.files.get("file")
        url = request.form.get("url", "").strip() or None

        if bool(file_storage) == bool(url):
            return error("Provide exactly one of 'file' or 'url'.", 400)

        data = service.start_plugin_update(
            plugin_id, current_user.UserID, file_storage=file_storage, url=url,
        )
        return success(data)

    except service.PluginNotFoundError:
        return error("Plugin not found.", 404)
    except service.InvalidTransitionError as e:
        return error(e.message, 409)
    except service.NoExecutableError as e:
        return error(e.message, 400)
    except service.PluginNotInArchiveError as e:
        return error(e.message, 404)
    except service.InvalidUrlError as e:
        return error(e.message, 400)
    except service.DownloadError as e:
        return error(e.message, 502)
    except (service.ArchiveTooLargeError, service.UnsupportedArchiveError, service.UnsafeArchiveError) as e:
        return error(e.message, 400)
    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while updating the plugin."
        )
        return error("An unexpected error occurred.", 500)


@plugin_bp.post('/<int:plugin_id>/update/rollback')
@login_required
@require_permission('plugin.update_rollback')
def rollback_plugin_update_route(plugin_id):
    """
    Manually roll back to the backed-up version (UI Flow Section 23's
    [Rollback] button). Available whenever a backup exists — not only
    after a failed update; a successful update's backup also stays
    available (Section 22 shows "Rollback: Available" on success too).

    **Inputs:** None (no request body).

    **Returns (JSON via success())**

    .. code-block:: json

        {
            "success": true,
            "data": {
                "success": true,
                "plugin_id": 3,
                "status": "Ready",
                "restored_version": "2.4.12"
            }
        }

    **Errors**

    * ``404`` - no plugin with that id, or no backup is available.
    * ``500`` - unexpected internal error (logged with traceback).
    """
    try:
        data = service.rollback_plugin_update(plugin_id, current_user.UserID)
        return success(data)
    except service.PluginNotFoundError:
        return error("Plugin not found.", 404)
    except service.NoExecutableError as e:
        return error(e.message, 400)
    except service.NoBackupAvailableError as e:
        return error(e.message, 404)
    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while rolling back the plugin update."
        )
        return error("An unexpected error occurred.", 500)


# ==========================================================
# MONITORING CONFIGURATION (Phase 10)
# ==========================================================

@plugin_bp.get('/<int:plugin_id>/configurations')
@login_required
@require_permission('plugin.view')
def get_plugin_configurations_route(plugin_id):
    """
    List a plugin's applied/pending/failed monitoring targets (UI Flow
    Section 8's monitoring-usage context, now backed by real data
    instead of Phase 3's placeholder).

    **Returns (JSON via success())**

    .. code-block:: json

        {
            "success": true,
            "data": [
                {
                    "id": 4,
                    "target": {"id": 12, "hostname": "router-01", "ip_address": "192.168.130.10"},
                    "service_description": "Interface Traffic",
                    "status": "Applied",
                    "configuration_data": null,
                    "updated_at": "2026-09-22T12:00:00"
                }
            ]
        }

    **Errors**

    * ``404`` - no plugin with that id.
    * ``500`` - unexpected internal error (logged with traceback).
    """
    try:
        if db.session.get(Plugin, plugin_id) is None:
            return error("Plugin not found.", 404)
        data = service.get_plugin_configurations(plugin_id)
        return success(data)
    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while retrieving plugin configurations."
        )
        return error("An unexpected error occurred.", 500)


@plugin_bp.post('/<int:plugin_id>/configurations')
@login_required
@require_permission('plugin.configure')
def apply_plugin_configuration_route(plugin_id):
    """
    Apply a plugin to a target device/service — the full Phase 10
    workflow (UI Flow Sections 13-17: Administrator selects plugin
    capability -> selects target -> Plugin Manager generates/updates
    Nagios configuration -> validates -> applies/reloads Nagios ->
    Nagios monitors target).

    Confirmed design: targets are always an existing NetworkDiscovery
    device (the only source of real Nagios host objects in this
    codebase) — free-form/unscanned targets are out of scope.

    On success, this is the ONLY thing in Plugin Manager that can set
    Plugin.Status to Active — every earlier phase stopped short of it
    deliberately.

    **Inputs (JSON body)**

    - ``net_discovery_id`` (required): the target device's id.
    - ``service_description`` (required): e.g. "Interface Traffic".
    - ``configuration_data`` (optional): arbitrary JSON (e.g. warning/
      critical thresholds), stored as-is.

    **Returns (JSON via success())**

    .. code-block:: json

        {
            "success": true,
            "data": {
                "success": true,
                "configuration_id": 4,
                "status": "Applied",
                "plugin_status": "Active"
            }
        }

        On failure (still HTTP 200 — the request itself was valid; the
        CONFIGURATION failed to apply):

        .. code-block:: json

            {
                "success": true,
                "data": {
                    "success": false,
                    "configuration_id": 4,
                    "status": "Failed",
                    "validation_output": "..."
                }
            }

    **Errors**

    * ``400`` - missing required fields.
    * ``404`` - no plugin with that id, or no target device with that id.
    * ``409`` - plugin is in a state that blocks configuration, or has
      no command definition.
    * ``500`` - unexpected internal error (logged with traceback).
    """
    try:
        data = request.get_json()
        err = validate_json_data(data)
        if err is not None:
            return err

        err = validate_json_fields(data, {"net_discovery_id": int, "service_description": str})
        if err is not None:
            return err

        result = service.apply_plugin_configuration(
            plugin_id,
            data["net_discovery_id"],
            data["service_description"],
            current_user.UserID,
            configuration_data=data.get("configuration_data"),
        )
        return success(result)

    except service.PluginNotFoundError:
        return error("Plugin not found.", 404)
    except service.InvalidTransitionError as e:
        return error(e.message, 409)
    except service.TargetNotFoundError as e:
        return error(e.message, 404)
    except service.NoCommandDefinedError as e:
        return error(e.message, 409)
    except Exception:
        current_app.logger.exception(
            "An unexpected error occurred while applying the monitoring configuration."
        )
        return error("An unexpected error occurred.", 500)
