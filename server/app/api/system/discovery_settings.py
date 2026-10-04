"""
Network Discovery settings: the networks, TCP/UDP ports and port ->
service name overrides used by the discovery scan.

Defaults come from config.py. Saving here stores them in the
DiscoverySettings singleton in system.db, which the scan reads on its
next run (see app/network_discovery/discovery_settings.py). Both routes
need the "settings.discovery" permission, which is assigned per role in
Manage Roles and also controls the Network Discovery tab on the Settings
page. Edits are refused while a scan is running so a single scan never
mixes old and new settings.

Routes
------
GET  /system/discovery-settings
    Return the effective discovery settings and the config.py defaults.

PUT  /system/discovery-settings
    Validate and save the discovery settings.
"""
import json

from flask import request, current_app
from flask_login import login_required, current_user

from app import db
from app.api.system import system_bp
from app.api.system.network_discovery import is_discovery_running
from app.api.helper import success, error, validate_json_data
from app.api.helper.database_access.permissions import require_permission
from app.system_models import DiscoverySettings, SystemSettings
from app.network_discovery.discovery_settings import (
    DiscoverySettingsError,
    SETTING_FIELDS,
    get_discovery_defaults,
    get_discovery_settings,
    get_discovery_settings_row,
    validate_discovery_settings,
)
from app.logging.configuration_changes import create_configuration_log


# Longest value written to the Configuration Change log. Its Old_Value
# and New_Value columns are 100 characters and the combined activity-log
# action is 255, so long port lists and override maps are shortened.
MAX_LOGGED_VALUE_LENGTH = 90


def short_value(value):
    """
    Render a setting value for the Configuration Change log, cut to
    MAX_LOGGED_VALUE_LENGTH characters with a trailing "..." if longer.
    """
    text = json.dumps(value, separators=(",", ":"))
    if len(text) <= MAX_LOGGED_VALUE_LENGTH:
        return text
    return text[:MAX_LOGGED_VALUE_LENGTH - 3] + "..."


# ==========================================================
# DISCOVERY SETTINGS
# ==========================================================

@system_bp.get('/discovery-settings')
@login_required
@require_permission('settings.discovery')
def get_discovery_settings_route():
    """
    Return the discovery settings currently in effect (saved values, or
    the config.py defaults for anything never saved), the defaults
    themselves for "Reset to Defaults", and whether a scan is running.
    """
    try:
        return success({
            "settings": get_discovery_settings(),
            "defaults": get_discovery_defaults(),
            "scanRunning": is_discovery_running(),
        })
    except Exception:
        current_app.logger.exception("An unexpected error occurred while fetching discovery settings.")
        return error("An unexpected error occurred.", 500)


@system_bp.put('/discovery-settings')
@login_required
@require_permission('settings.discovery')
def update_discovery_settings_route():
    """
    Validate and save every discovery setting. The client sends the full
    object with the version it loaded; a stale version is rejected with
    409, as is any save while a discovery scan is running. Networks must
    be IPv4 addresses or CIDR ranges no larger than a /16 (loopback is
    rejected); ports are numbers 1-65535 or "start-end" ranges; service
    names are lowercase letters, digits, "-" or "_". Forced services
    ("always treat port as") apply on every device whatever nmap reports;
    service overrides are fallbacks used only when nmap could not
    fingerprint a port. Changes take effect
    on the next scan and are recorded in the Configuration Change log
    when audit logging is on.

    JSON Format
    {
        "version": 1,
        "networks": ["192.168.130.0/24"],
        "tcpPorts": ["1-6000"],
        "udpPorts": [53, 161],
        "tcpServiceOverrides": {"22": "ssh"},
        "udpServiceOverrides": {"161": "snmp"},
        "tcpForcedServices": {"5693": "ncpa"},
        "udpForcedServices": {}
    }
    """
    data = request.get_json(silent=True)
    err = validate_json_data(data)
    if err is not None:
        return err

    if is_discovery_running():
        return error("A network discovery scan is running. Try again when it finishes.", 409)

    try:
        values = validate_discovery_settings(data)
    except KeyError as exc:
        return error(f"Missing required field: {exc}", 400)
    except DiscoverySettingsError as exc:
        return error(str(exc), 400)

    try:
        row = get_discovery_settings_row()
        current_version = row.Version if row is not None else 0
        if data.get("version") != current_version:
            return error("Discovery settings were updated by someone else. Reload and try again.", 409)

        before = get_discovery_settings()
        if row is None:
            row = DiscoverySettings(Id=1, Version=0)
            db.session.add(row)

        changes = []
        for column, _, api_key in SETTING_FIELDS:
            if before[api_key] != values[column]:
                changes.append((column, before[api_key], values[column]))
            setattr(row, column, values[column])

        if not changes:
            db.session.rollback()
            return success(get_discovery_settings(), message="No changes to save.")

        row.Version += 1
        row.Updated_By = current_user.UserID

        system_settings = db.session.get(SystemSettings, 1)
        if system_settings is None or system_settings.Audit_Logging:
            for column, old_value, new_value in changes:
                create_configuration_log(
                    current_user.UserID, "discovery_settings", column, short_value(old_value), short_value(new_value)
                )

        db.session.commit()
        return success(get_discovery_settings(), message="Discovery settings updated.")

    except Exception:
        db.session.rollback()
        current_app.logger.exception("An unexpected error occurred while updating discovery settings.")
        return error("An unexpected error occurred.", 500)
