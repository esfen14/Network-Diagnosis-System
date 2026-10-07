"""
Plugin settings editable from Settings -> Plugins: network-wide defaults for a
plugin's variables, such as the SNMP OIDs every SNMP device is checked for and
the NCPA metrics every NCPA host is checked for.

The defaults live in config.py (SNMP_OIDS, NCPA_METRICS). Once an administrator saves a
plugin's settings they are stored in its PluginSettings row in system.db and
take precedence over config.py the next time the Nagios config is built.
Per-host overrides (NetworkDiscovery.Plugin_Variables) still win over both;
see the resolution order in plugin_registry.py.

Every value ends up in a generated Nagios object and a shell-executed check
command, and each SNMP metric is part of a Nagios service name
("snmp-<metric>-<port>-udp"), as is each NCPA metric ("ncpa-<metric>-<port>-tcp"),
so the validators below are strict.
"""
import re

import sqlalchemy as sa
from flask import current_app

from app import db
from app.system_models import PluginSettings


# Plugin definition -> {variable: config.py key} of the variables Settings -> Plugins edits.
EDITABLE_PLUGIN_SETTINGS = {
    "snmp": {"oids": "SNMP_OIDS"},
    "ncpa": {"metrics": "NCPA_METRICS"},
}

# The Plugin Manager plugin whose presence shows a definition's section.
SETTINGS_PLUGINS = {
    "snmp": "check_snmp",
    "ncpa": "check_ncpa",
}

MAX_SNMP_OIDS = 50
METRIC_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]{0,31}$")
OID_PATTERN = re.compile(r"^\.?[0-9]+(\.[0-9]+)+$")
MAX_OID_LENGTH = 128

MAX_NCPA_METRICS = 50
# An NCPA API path: "/"-separated segments of letters, digits, "_", "-", "." or "|" (NCPA's "/"
# inside a mount point), or the literal {partition}, which expands to one service per partition.
NCPA_PATH_PATTERN = re.compile(r"^([A-Za-z0-9_.|-]+|\{partition\})(/([A-Za-z0-9_.|-]+|\{partition\}))*$")
MAX_NCPA_PATH_LENGTH = 200
# A Nagios threshold range such as 80, 10:, ~:20, 10:20 or @10:20.
THRESHOLD_PATTERN = re.compile(r"^@?(~|-?[0-9]+(\.[0-9]+)?)?(:(-?[0-9]+(\.[0-9]+)?)?)?$")
UNITS_PATTERN = re.compile(r"^[A-Za-z%]{1,8}$")
# NCPA query arguments such as aggregate=avg or aggregate=avg,sample=5.
QUERYARGS_PATTERN = re.compile(r"^[A-Za-z0-9_]+=[A-Za-z0-9_.-]+(,[A-Za-z0-9_]+=[A-Za-z0-9_.-]+)*$")
NCPA_OPTIONAL_FIELDS = (
    ("warning", THRESHOLD_PATTERN, "Warning must be a Nagios threshold, e.g. 80 or 10:20."),
    ("critical", THRESHOLD_PATTERN, "Critical must be a Nagios threshold, e.g. 95 or 10:20."),
    ("units", UNITS_PATTERN, "Units must be up to 8 letters or '%', e.g. Gi."),
    ("queryargs", QUERYARGS_PATTERN, "Query args must be name=value pairs separated by ',', e.g. aggregate=avg."),
)


class PluginSettingsError(ValueError):
    """Raised when submitted plugin settings fail validation."""


def get_plugin_settings_row(plugin_name):
    """Return the PluginSettings row for a plugin definition, or None if nothing was saved."""
    return db.session.scalar(sa.select(PluginSettings).where(PluginSettings.Plugin_Name == plugin_name))


def get_plugin_defaults(plugin_name):
    """Return {variable: config.py default} for the variables of plugin_name that can be edited."""
    return {
        variable: current_app.config.get(config_key)
        for variable, config_key in EDITABLE_PLUGIN_SETTINGS[plugin_name].items()
    }


def get_plugin_settings(plugin_name):
    """
    Return {variable: effective value} for plugin_name: the saved value, or the
    config.py default for a variable never saved.
    """
    values = get_plugin_defaults(plugin_name)
    row = get_plugin_settings_row(plugin_name)
    if row is not None and row.Variables:
        for variable in values:
            if row.Variables.get(variable) is not None:
                values[variable] = row.Variables[variable]
    return values


def plugin_config(app_config=None):
    """
    Return a copy of the app config with every saved plugin setting in place of
    its config.py key, for the Nagios config planner (plan_host_services). Read
    once per build, not once per host.
    """
    config = dict(app_config if app_config is not None else current_app.config)
    for row in db.session.scalars(sa.select(PluginSettings)).all():
        keys = EDITABLE_PLUGIN_SETTINGS.get(row.Plugin_Name, {})
        for variable, config_key in keys.items():
            if row.Variables and row.Variables.get(variable) is not None:
                config[config_key] = row.Variables[variable]
    return config


def validate_snmp_oids(oids):
    """
    Return the SNMP OID list cleaned up, or raise PluginSettingsError. Expects a
    list of 1 to MAX_SNMP_OIDS {"metric": str, "oid": str} entries. The metric is
    the description of what the OID measures and becomes part of the service
    name, so it is lowercase letters, digits and "_", and unique. The OID is
    numeric and dotted (a leading "." is allowed) and unique.
    """
    if not isinstance(oids, list):
        raise PluginSettingsError("oids must be a list.")
    if not oids:
        raise PluginSettingsError("Add at least one OID. To stop SNMP checks, disable check_snmp in Plugin Manager.")
    if len(oids) > MAX_SNMP_OIDS:
        raise PluginSettingsError(f"At most {MAX_SNMP_OIDS} OIDs are allowed.")

    cleaned = []
    metrics = set()
    seen_oids = set()
    for entry in oids:
        if not isinstance(entry, dict):
            raise PluginSettingsError("Each OID entry needs a description and an OID.")
        metric = str(entry.get("metric") or "").strip().lower()
        oid = str(entry.get("oid") or "").strip()

        if not METRIC_PATTERN.match(metric):
            raise PluginSettingsError(
                "Description must start with a letter or digit and use only lowercase letters, digits and '_' (32 characters at most)."
            )
        if len(oid) > MAX_OID_LENGTH or not OID_PATTERN.match(oid):
            raise PluginSettingsError(f"OID for '{metric}' must be numeric and dotted, e.g. 1.3.6.1.2.1.1.3.0.")
        if metric in metrics:
            raise PluginSettingsError(f"Description '{metric}' is used more than once.")
        if oid.lstrip(".") in seen_oids:
            raise PluginSettingsError(f"OID {oid} is listed more than once.")

        metrics.add(metric)
        seen_oids.add(oid.lstrip("."))
        cleaned.append({"metric": metric, "oid": oid})
    return cleaned


def validate_ncpa_metrics(metrics):
    """
    Return the NCPA metric list cleaned up, or raise PluginSettingsError. Expects
    a list of 1 to MAX_NCPA_METRICS {"metric", "path"} entries with optional
    "warning", "critical", "units" and "queryargs" (an empty value is dropped).
    The metric is the description of what is measured and becomes part of the
    service name, so it follows the SNMP rules and is unique. The path is an NCPA
    API path; "{partition}" in it expands to one service per partition.
    """
    if not isinstance(metrics, list):
        raise PluginSettingsError("metrics must be a list.")
    if not metrics:
        raise PluginSettingsError("Add at least one metric. To stop NCPA checks, disable check_ncpa in Plugin Manager.")
    if len(metrics) > MAX_NCPA_METRICS:
        raise PluginSettingsError(f"At most {MAX_NCPA_METRICS} metrics are allowed.")

    cleaned = []
    names = set()
    for entry in metrics:
        if not isinstance(entry, dict):
            raise PluginSettingsError("Each metric entry needs a description and a path.")
        metric = str(entry.get("metric") or "").strip().lower()
        path = str(entry.get("path") or "").strip().strip("/")

        if not METRIC_PATTERN.match(metric):
            raise PluginSettingsError(
                "Description must start with a letter or digit and use only lowercase letters, digits and '_' (32 characters at most)."
            )
        if metric in names:
            raise PluginSettingsError(f"Description '{metric}' is used more than once.")
        if len(path) > MAX_NCPA_PATH_LENGTH or not NCPA_PATH_PATTERN.match(path):
            raise PluginSettingsError(
                f"Path for '{metric}' must be an NCPA path such as cpu/percent or disk/logical/{{partition}}/used_percent."
            )

        item = {"metric": metric, "path": path}
        for field, pattern, message in NCPA_OPTIONAL_FIELDS:
            value = str(entry.get(field) or "").strip()
            if not value:
                continue
            if not pattern.match(value):
                raise PluginSettingsError(f"{message} ('{metric}')")
            item[field] = value

        names.add(metric)
        cleaned.append(item)
    return cleaned


# Plugin definition -> (the variable its section edits, its validator).
PLUGIN_SETTINGS_VALIDATORS = {
    "snmp": ("oids", validate_snmp_oids),
    "ncpa": ("metrics", validate_ncpa_metrics),
}
