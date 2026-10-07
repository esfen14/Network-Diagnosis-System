"""
Custom checks: Plugin Manager plugins that discovery cannot attach to a port, run
by an administrator against one discovered device with arguments they supply
(spec files/Custom_Checks_Plan.md).

This module is pure: it knows which plugins take a custom check, what arguments
each takes, and how a check becomes a Nagios command. It never touches the
database or Nagios; api/plugin/custom_checks.py stores the checks and
network_discovery/create_host_cfg.py writes them.

Commands reuse the registry's rendering and validation. Each custom plugin gets
one `pinpoint_custom_<plugin>` command; required arguments are passed as
$ARG1$..$ARGn$ and optional ones are rendered together into the final $ARG$, so
every value is single-quoted and checked against FORBIDDEN_VALUE_CHARACTERS.
Error messages name the argument, never its value.

Plugin classes (Custom_Checks_Plan.md section 2.4)
--------------------------------------------------
service      Discovery drives it from a port (the registry); enable it.
custom       Probes a device over the network; takes a custom check.
server       Checks the machine Nagios runs on; takes a server check (one service on the
             Nagios server's own host, written without touching localhost.cfg).
credentials  Would take a custom check but needs a password nothing can store yet.
stock        One of the five checks Nagios Core runs itself (localhost.cfg); not managed here.
advanced     Needs arguments Pinpoint cannot build yet.
unsupported  Aggregates other services; out of scope for now.
replaced     Superseded by a plugin discovery already drives.
"""
import re
from dataclasses import dataclass

from app.network_discovery.plugin_registry import (
    PluginConfigurationError,
    PluginDefinition,
    Transport,
    COMMAND_TEMPLATE,
    PLUGIN_DEFINITIONS,
    normalize_plugin_name,
    resolve_plugin_command,
    sanitize_name_part,
)

CUSTOM_COMMAND_PREFIX = "pinpoint_custom_"
CUSTOM_SERVICE_PREFIX = "custom-"
SERVER_SERVICE_PREFIX = "server-"
# The Nagios server's own host object (statistics.NAGIOS_HOST, defined by localhost.cfg). Server
# checks are written as services of this host in hosts.cfg; localhost.cfg itself is never edited.
SERVER_HOST_NAME = "localhost"
MAX_CHECK_NAME_LENGTH = 60
MAX_ARGUMENT_LENGTH = 300

CHECK_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]*$")


@dataclass(frozen=True)
class CheckField:
    """One argument of a custom check: its variable name, flag, label and whether it is required."""
    name: str
    flag: str
    label: str
    required: bool = False
    placeholder: str = ""


def field(name, flag, label, required=False, placeholder=""):
    return CheckField(name, flag, label, required, placeholder)


WARNING = field("warning", "-w", "Warning threshold")
CRITICAL = field("critical", "-c", "Critical threshold")
COMMUNITY = field("community", "-C", "SNMP community", placeholder="public")

# Plugins that take a custom check and the arguments each accepts. Fields that
# need a password (check_nt -s, check_disk_smb -p, ...) are left out on purpose:
# no secrets are stored (plan section 2.3).
CUSTOM_CHECK_FIELDS = {
    "check_by_ssh": (
        field("command", "-C", "Command to run on the device", True, "/usr/lib/nagios/plugins/check_apt"),
        field("port", "-p", "SSH port", placeholder="22"),
        field("user", "-l", "SSH user"),
        field("identity", "-i", "Identity file (path on the Nagios server)"),
    ),
    "check_breeze": (field("warning", "-w", "Warning (% signal strength)", True),
                     field("critical", "-c", "Critical (% signal strength)", True), COMMUNITY),
    "check_wave": (field("warning", "-w", "Warning (% signal strength)", True),
                   field("critical", "-c", "Critical (% signal strength)", True)),
    "check_hpjd": (COMMUNITY, field("port", "-p", "SNMP port", placeholder="161")),
    "check_ifstatus": (COMMUNITY, field("port", "-p", "SNMP port", placeholder="161")),
    "check_ifoperstatus": (field("index", "-k", "Interface index", True), COMMUNITY,
                           field("port", "-p", "SNMP port", placeholder="161")),
    "check_ups": (field("ups", "-u", "UPS name", True), field("port", "-p", "NUT port", placeholder="3493"),
                  field("warning", "-w", "Warning battery level (%)"),
                  field("critical", "-c", "Critical battery level (%)")),
    "check_ssl_validity": (field("port", "-p", "Port", placeholder="443"),
                           field("warning", "-w", "Warn if it expires in fewer than N days"),
                           field("critical", "-c", "Critical if it expires in fewer than N days")),
    "check_nt": (field("variable", "-v", "Variable (CPULOAD, UPTIME, USEDDISKS, ...)", True),
                 field("port", "-p", "NSClient port", placeholder="1248"), WARNING, CRITICAL,
                 field("params", "-l", "Additional parameters (for example a drive letter)")),
    "check_nwstat": (field("variable", "-v", "Variable (LOAD1, CONNS, ...)", True),
                     field("port", "-p", "Port"), WARNING, CRITICAL),
    "check_overcr": (field("variable", "-v", "Variable (LOAD, DISK, PROCS, UPTIME)", True),
                     field("port", "-p", "Port"), WARNING, CRITICAL),
    "check_real": (field("url", "-u", "URL of the content to check", True),
                   field("port", "-p", "RTSP port", placeholder="554"),
                   field("warning", "-w", "Warning response time (s)"),
                   field("critical", "-c", "Critical response time (s)")),
    "check_game": (field("game", "-G", "Game type (qstat name)", True), field("port", "-P", "Game server port")),
    "check_clamd": (field("port", "-p", "Port", placeholder="3310"), WARNING, CRITICAL),
    # The ping family (Q-C7): a service that tracks the device itself rather than a port.
    # Thresholds are "round-trip ms,packet loss %" (check_fping: loss first), as the plugins take them.
    "check_ping": (field("warning", "-w", "Warning (round trip ms, loss %)", True, "100.0,20%"),
                   field("critical", "-c", "Critical (round trip ms, loss %)", True, "500.0,60%"),
                   field("packets", "-p", "Packets to send", placeholder="5")),
    "check_icmp": (field("warning", "-w", "Warning (round trip ms, loss %)", True, "100.0,20%"),
                   field("critical", "-c", "Critical (round trip ms, loss %)", True, "200.0,40%"),
                   field("packets", "-n", "Packets to send", placeholder="5")),
    "check_fping": (field("warning", "-w", "Warning (loss %, round trip ms)", True, "20%,100"),
                    field("critical", "-c", "Critical (loss %, round trip ms)", True, "40%,200"),
                    field("packets", "-n", "Packets to send", placeholder="1")),
    "check_dig": (field("lookup", "-l", "DNS record to look up", False, "example.com"),
                  field("record_type", "-T", "Record type", placeholder="A"),
                  field("expected", "-a", "Expected address in the answer"),
                  field("port", "-p", "DNS port", placeholder="53"),
                  field("warning", "-w", "Warning response time (s)"),
                  field("critical", "-c", "Critical response time (s)")),
    "check_disk_smb": (field("share", "-s", "Share name", True), field("user", "-u", "SMB user", placeholder="guest"),
                       field("workgroup", "-W", "Workgroup or domain"),
                       field("warning", "-w", "Warning free-space threshold (%)"),
                       field("critical", "-c", "Critical free-space threshold (%)")),
}

# Plugins that check the machine Nagios runs on. They take no host: the service is written on the
# Nagios server's own host. Everything here runs as the nagios user on that machine, so a path or
# device an administrator names is read by that account (plugin.custom_check is the guard).
# check_log is left out on purpose: it writes a state file at a path the administrator chooses.
SERVER_CHECK_FIELDS = {
    "check_apt": (field("warning", "-w", "Warn if this many packages need upgrading"),
                  field("include", "-i", "Only packages matching this regex"),
                  field("exclude", "-e", "Skip packages matching this regex"),
                  field("timeout", "-t", "Timeout (s)", placeholder="10")),
    "check_uptime": (WARNING, CRITICAL,
                     field("unit", "-u", "Unit of the thresholds", placeholder="seconds"),
                     field("timeout", "-t", "Timeout (s)")),
    "check_sensors": (),
    "check_ide_smart": (field("device", "-d", "Block device", True, "/dev/sda"),),
    "check_file_age": (field("file", "-f", "File to check", True, "/var/backups/db.sql"),
                       field("warning", "-w", "Warn if older than (s)"),
                       field("critical", "-c", "Critical if older than (s)"),
                       field("min_warning", "-W", "Warn if smaller than (bytes)"),
                       field("min_critical", "-C", "Critical if smaller than (bytes)")),
    "check_mailq": (field("warning", "-w", "Warning queue length", True),
                    field("critical", "-c", "Critical queue length", True),
                    field("mta", "-M", "Mail system", placeholder="postfix")),
    "check_nagios": (field("status_log", "-F", "Nagios status log file", True, "/usr/local/nagios/var/status.dat"),
                     field("max_age", "-e", "Longest age of the status log (minutes)", True, "5"),
                     field("process", "-C", "Nagios process to look for", True, "/usr/local/nagios/bin/nagios")),
    "check_flexlm": (field("license_file", "-F", "FlexLM license.dat file", True),),
}

# Every field table, for validation and rendering.
ALL_CHECK_FIELDS = {**CUSTOM_CHECK_FIELDS, **SERVER_CHECK_FIELDS}

# Every catalog plugin outside the registry has one class (Custom_Checks_Plan.md section 2.4).
# The registry's own plugins are class "service" and are not listed here.
PLUGIN_CLASSES = {
    **{name: "custom" for name in CUSTOM_CHECK_FIELDS},
    **{name: "credentials" for name in ("check_mysql_query", "check_dbi", "check_oracle", "check_radius")},
    **{name: "server" for name in SERVER_CHECK_FIELDS},
    **{name: "stock" for name in ("check_load", "check_disk", "check_swap", "check_procs", "check_users")},
    **{name: "advanced" for name in ("check_log", "check_mrtg", "check_mrtgtraf", "check_dummy", "check_dhcp")},
    "check_cluster": "unsupported",
    "check_ntp": "replaced",
}

PLUGIN_CLASS_NOTES = {
    "credentials": "Needs a password, which custom checks cannot store yet.",
    "stock": "Checks the Nagios server itself through Nagios Core. Not managed here.",
    "advanced": "Needs arguments Pinpoint cannot build yet.",
    "unsupported": "Aggregates other services. Not available yet.",
    "replaced": "Replaced by check_ntp_time, which discovery already uses for NTP ports.",
}


def plugin_class(plugin_name):
    """
    The class of a Plugin Manager plugin (extension ignored): "service", "custom",
    "credentials", "server", "unsupported", "replaced", or None for a plugin the audit
    does not cover (a custom upload).
    """
    key = normalize_plugin_name(plugin_name)
    if key in {definition.check_plugin for definition in PLUGIN_DEFINITIONS.values()}:
        return "service"
    return PLUGIN_CLASSES.get(key)


def is_custom_checkable(plugin_name):
    """True if the plugin takes custom checks, on a device or on the Nagios server."""
    return normalize_plugin_name(plugin_name) in ALL_CHECK_FIELDS


def check_target(plugin_name):
    """Where a plugin's checks run: "device" (a discovered device), "server" (the Nagios server) or None."""
    key = normalize_plugin_name(plugin_name)
    if key in SERVER_CHECK_FIELDS:
        return "server"
    return "device" if key in CUSTOM_CHECK_FIELDS else None


def plugin_fields(plugin_name):
    """The CheckFields of a custom-checkable plugin, or an empty tuple."""
    return ALL_CHECK_FIELDS.get(normalize_plugin_name(plugin_name), ())


def build_definitions():
    """
    One PluginDefinition per custom-checkable plugin, its command named pinpoint_custom_<plugin>.
    Server checks run without a target host (takes_host is False).
    """
    definitions = {}
    for plugin, fields in ALL_CHECK_FIELDS.items():
        definitions[plugin] = PluginDefinition(
            name=plugin,
            check_plugin=plugin,
            transports=(Transport.TCP,),
            arguments=tuple((f.flag, f.name) for f in fields if f.required),
            options={f.name: f.flag for f in fields if not f.required},
            command_prefix=CUSTOM_COMMAND_PREFIX,
            takes_host=plugin not in SERVER_CHECK_FIELDS,
        )
    return definitions


CUSTOM_DEFINITIONS = build_definitions()


def clean_variables(plugin_name, variables):
    """
    The variables of a check, limited to the plugin's fields, as strings with blanks
    dropped. Raises PluginConfigurationError for an unknown plugin, a missing required
    argument, an over-long value or a forbidden character (the message names the
    argument, never its value).
    """
    key = normalize_plugin_name(plugin_name)
    if key not in CUSTOM_DEFINITIONS:
        raise PluginConfigurationError(f"{plugin_name} does not take custom checks.")
    if not isinstance(variables, dict):
        raise PluginConfigurationError("Arguments must be an object.")

    allowed = {f.name: f for f in ALL_CHECK_FIELDS[key]}
    unknown = sorted(set(variables) - set(allowed))
    if unknown:
        raise PluginConfigurationError(f"Unknown argument '{unknown[0]}'.")

    cleaned = {}
    for name, spec in allowed.items():
        value = variables.get(name)
        text = "" if value is None else str(value).strip()
        if text == "":
            if spec.required:
                raise PluginConfigurationError(f"'{spec.label}' is required.")
            continue
        if len(text) > MAX_ARGUMENT_LENGTH:
            raise PluginConfigurationError(f"'{spec.label}' is too long.")
        cleaned[name] = text

    # Run the registry's own rendering so the values are validated exactly as discovery's are.
    resolve_plugin_command_for(key, cleaned)
    return cleaned


def resolve_plugin_command_for(plugin_name, variables):
    """The Nagios check_command for one check, e.g. "pinpoint_custom_check_ups!nut1!!-w '50'"."""
    return resolve_plugin_command(normalize_plugin_name(plugin_name), variables, definitions=CUSTOM_DEFINITIONS)


def render_command_definition(plugin_name):
    """The Nagios `define command` object for a custom-checkable plugin."""
    definition = CUSTOM_DEFINITIONS[normalize_plugin_name(plugin_name)]
    return COMMAND_TEMPLATE.format(command_name=definition.command_name, command_line=definition.command_line)


def plugin_for_custom_command(command_name):
    """
    The plugin ("check_by_ssh") behind a pinpoint_custom_ command name, or None.
    Arguments after "!" are ignored.
    """
    name = str(command_name or "").split("!")[0].strip()
    if not name.startswith(CUSTOM_COMMAND_PREFIX):
        return None
    plugin = name[len(CUSTOM_COMMAND_PREFIX):]
    return plugin if plugin in CUSTOM_DEFINITIONS else None


def validate_check_name(name):
    """The check name trimmed, or raises PluginConfigurationError if it is empty, long or has odd characters."""
    text = str(name or "").strip()
    if not text:
        raise PluginConfigurationError("A name is required.")
    if len(text) > MAX_CHECK_NAME_LENGTH:
        raise PluginConfigurationError(f"The name must be at most {MAX_CHECK_NAME_LENGTH} characters.")
    if not CHECK_NAME_PATTERN.match(text):
        raise PluginConfigurationError("The name may use letters, numbers, spaces, '.', '_' and '-'.")
    return text


def service_name(plugin_name, check_name):
    """
    The Nagios service name of a check: plugin check_by_ssh and name "Weekly updates"
    give "custom-by_ssh-weekly_updates"; a server check of check_apt gives "server-apt-weekly_updates".
    Unique per device (or among the server's checks) in the API.
    """
    short = normalize_plugin_name(plugin_name)
    prefix = SERVER_SERVICE_PREFIX if short in SERVER_CHECK_FIELDS else CUSTOM_SERVICE_PREFIX
    short = short[len("check_"):] if short.startswith("check_") else short
    return f"{prefix}{short}-{sanitize_name_part(check_name.strip().lower().replace(' ', '_'))}"
