"""
Plugin settings (Settings -> Plugins): network-wide defaults for plugins that
Network Discovery configures, starting with the SNMP OIDs every SNMP device is
checked for. A plugin's section is offered only once Plugin Manager has the
plugin installed (it has a Plugin row).

Defaults come from config.py. Saving stores them in the plugin's
PluginSettings row in system.db and rebuilds the Nagios config, so the change
is live at once (see app/network_discovery/plugin_settings.py). Both routes
need the "settings.plugins" permission, which also controls the Plugins tab on
the Settings page.

Routes
------
GET  /system/plugin-settings
    Return each editable plugin's settings, its config.py defaults, and whether
    the plugin is installed.

PUT  /system/plugin-settings/snmp
    Validate and save the SNMP OID table, then rebuild the Nagios config.
"""
import sqlalchemy as sa
from flask import request, current_app
from flask_login import login_required, current_user

from app import db
from app.api.system import system_bp
from app.api.system.device_identity import apply_config_change
from app.api.system.discovery_settings import short_value
from app.api.helper import success, error, validate_json_data
from app.api.helper.database_access.permissions import require_permission
from app.logging.configuration_changes import create_configuration_log
from app.network_discovery.plugin_settings import (
    SETTINGS_PLUGINS,
    PluginSettingsError,
    get_plugin_defaults,
    get_plugin_settings,
    get_plugin_settings_row,
    validate_snmp_oids,
)
from app.plugin_models import Plugin
from app.system_models import PluginSettings, SystemSettings


# ==========================================================
# HELPERS
# ==========================================================

def serialize_plugin_settings(plugin_name):
    """
    Return one plugin's section of GET /system/plugin-settings: whether the
    plugin is installed (and its Plugin Manager status), its effective values,
    their config.py defaults and the version to send back on save.
    """
    plugin = db.session.scalar(sa.select(Plugin).where(Plugin.Name == SETTINGS_PLUGINS[plugin_name]))
    row = get_plugin_settings_row(plugin_name)
    return {
        "plugin": SETTINGS_PLUGINS[plugin_name],
        "installed": plugin is not None,
        "status": plugin.Status.value if plugin is not None else None,
        "settings": get_plugin_settings(plugin_name),
        "defaults": get_plugin_defaults(plugin_name),
        "version": row.Version if row is not None else 0,
    }


# ==========================================================
# PLUGIN SETTINGS
# ==========================================================

@system_bp.get('/plugin-settings')
@login_required
@require_permission('settings.plugins')
def get_plugin_settings_route():
    """
    Return the settings of every plugin Settings -> Plugins can edit, keyed by
    plugin definition name, e.g.
    {"snmp": {"plugin": "check_snmp", "installed": true, "status": "Active",
              "settings": {"oids": [{"metric": "uptime", "oid": "1.3.6.1.2.1.1.3.0"}]},
              "defaults": {"oids": [...]}, "version": 0}}
    """
    try:
        return success({name: serialize_plugin_settings(name) for name in SETTINGS_PLUGINS})
    except Exception:
        current_app.logger.exception("An unexpected error occurred while fetching plugin settings.")
        return error("An unexpected error occurred.", 500)


@system_bp.put('/plugin-settings/snmp')
@login_required
@require_permission('settings.plugins')
def update_snmp_settings_route():
    """
    Validate and save the SNMP OID table, then rebuild the Nagios config so
    every SNMP device is checked for the new OIDs. Each entry becomes a service
    named "snmp-<metric>-<port>-udp", so renaming a description replaces that
    service and its history starts again. Refused with 400 if check_snmp is not
    installed or an entry is invalid, and with 409 if the version is stale.
    The response carries the saved section plus config_applied, config_ok and
    config_message, as other changes that rebuild the config do.

    JSON Format
    {
        "version": 0,
        "oids": [{"metric": "uptime", "oid": "1.3.6.1.2.1.1.3.0"}]
    }
    """
    data = request.get_json(silent=True)
    err = validate_json_data(data)
    if err is not None:
        return err

    if not serialize_plugin_settings("snmp")["installed"]:
        return error("check_snmp is not installed.", 400)

    if "oids" not in data:
        return error("Missing required field: 'oids'", 400)
    try:
        oids = validate_snmp_oids(data["oids"])
    except PluginSettingsError as exc:
        return error(str(exc), 400)

    try:
        row = get_plugin_settings_row("snmp")
        current_version = row.Version if row is not None else 0
        if data.get("version") != current_version:
            return error("SNMP settings were updated by someone else. Reload and try again.", 409)

        before = get_plugin_settings("snmp")["oids"]
        if before == oids:
            return success(
                {**serialize_plugin_settings("snmp"), "config_applied": False, "config_ok": True,
                 "config_message": "No changes to save."},
                message="No changes to save.",
            )

        if row is None:
            row = PluginSettings(Plugin_Name="snmp", Variables={}, Version=0)
            db.session.add(row)
        row.Variables = {**(row.Variables or {}), "oids": oids}
        row.Version += 1
        row.Updated_By = current_user.UserID

        system_settings = db.session.get(SystemSettings, 1)
        if system_settings is None or system_settings.Audit_Logging:
            create_configuration_log(
                current_user.UserID, "plugin_settings", "snmp_oids", short_value(before), short_value(oids)
            )

        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("An unexpected error occurred while updating SNMP settings.")
        return error("An unexpected error occurred.", 500)

    return success(
        {**serialize_plugin_settings("snmp"), **apply_config_change()},
        message="SNMP settings updated.",
    )
