"""
Editable Network Discovery settings: which networks nmap scans, which
TCP/UDP ports it probes, and the Port -> Service table per protocol: the
service an admin expects on each port. NCPA_PORT -> ncpa is always part of the
TCP table; it is derived when the table is read and never stored.

The defaults live in config.py (NETWORKS, TCP_PORTS, UDP_PORTS,
TCP_PORT_SERVICES, UDP_PORT_SERVICES). Once an administrator
saves them from the Settings page they are stored in the
DiscoverySettings row in system.db, which takes precedence over
config.py from the next scan on — no restart needed.

Every value here ends up on the nmap command line or in generated Nagios
config, so the validators below are strict: networks must parse as IPv4
networks, ports must be plain integers or "a-b" ranges, and service names
are limited to lowercase letters, digits, "-" and "_". Anything else is
rejected before it is stored.
"""
import ipaddress
import re

from flask import current_app

from app import db
from app.network_discovery.plugin_registry import (
    GENERIC_PLUGIN_FOR_TRANSPORT,
    Transport,
    find_plugin_by_name_or_alias,
)
from app.system_models import DiscoverySettings


# Largest network a single entry may cover. A /16 is already 65k
# addresses; anything wider would make a scan run for days.
MIN_PREFIX_LENGTH = 16

MAX_NETWORKS = 32
MAX_PORT_ENTRIES = 100
MAX_OVERRIDES = 200

SERVICE_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
PORT_RANGE_PATTERN = re.compile(r"^(\d{1,5})-(\d{1,5})$")

# (DiscoverySettings column, config.py key, API key)
SETTING_FIELDS = [
    ("Networks", "NETWORKS", "networks"),
    ("TCP_Ports", "TCP_PORTS", "tcpPorts"),
    ("UDP_Ports", "UDP_PORTS", "udpPorts"),
    ("TCP_Port_Services", "TCP_PORT_SERVICES", "tcpPortServices"),
    ("UDP_Port_Services", "UDP_PORT_SERVICES", "udpPortServices"),
]

# The service NCPA_PORT always maps to (deployment configures the agent there).
NCPA_SERVICE = "ncpa"


class DiscoverySettingsError(ValueError):
    """Raised when a submitted discovery setting fails validation."""


def get_discovery_settings_row():
    """
    Return the DiscoverySettings singleton, or None if nothing has been
    saved yet. Never creates the row.
    """
    return db.session.get(DiscoverySettings, 1)


def get_discovery_setting(config_key):
    """
    Return the effective value of one discovery setting by its config.py
    key (e.g. "NETWORKS"): the saved value if one exists, otherwise the
    config.py default. Used by the scan so edits apply on the next run.
    """
    row = get_discovery_settings_row()
    for column, key, _ in SETTING_FIELDS:
        if key != config_key:
            continue
        if row is not None and getattr(row, column) is not None:
            return getattr(row, column)
        return current_app.config[key]
    raise KeyError(config_key)


def ncpa_port_key():
    """NCPA_PORT as the string key used in the Port -> Service tables."""
    return str(int(current_app.config["NCPA_PORT"]))


def with_ncpa_entry(port_services, protocol):
    """
    Return a copy of a stored Port -> Service table with the derived
    NCPA_PORT -> ncpa entry added (TCP only). The derived entry wins over a
    stored one for the same port.
    """
    table = dict(port_services or {})
    if str(protocol).lower() == "tcp":
        table[ncpa_port_key()] = NCPA_SERVICE
    return table


def get_port_services(protocol):
    """
    Return the effective {port: service} table for "tcp" or "udp" as the scan
    uses it: the saved table (or the config.py default) plus the derived NCPA
    entry.
    """
    config_key = "TCP_PORT_SERVICES" if str(protocol).lower() == "tcp" else "UDP_PORT_SERVICES"
    return with_ncpa_entry(get_discovery_setting(config_key), protocol)


def resolve_port_service(service_name, protocol):
    """
    Say which check a service name leads to: {"plugin": "check_ssh",
    "kind": "plugin"}, {"plugin": "check_tcp", "kind": "generic"} for a TCP
    service with no plugin of its own, or {"plugin": None, "kind": "skipped"}
    for a UDP service with none (discovery skips those).
    """
    transport = Transport.UDP if str(protocol).lower() == "udp" else Transport.TCP
    definition = find_plugin_by_name_or_alias(service_name)
    if definition is not None and transport in definition.transports:
        generic = GENERIC_PLUGIN_FOR_TRANSPORT[transport]
        if definition.name != generic:
            return {"plugin": definition.check_plugin, "kind": "plugin"}
    if transport is Transport.TCP:
        return {"plugin": "check_tcp", "kind": "generic"}
    return {"plugin": None, "kind": "skipped"}


def get_discovery_settings(include_derived=True):
    """
    Return every discovery setting in its API shape (camelCase keys),
    with saved values taking precedence over config.py, plus the row's
    version for optimistic concurrency (0 when nothing is saved yet).
    With include_derived (the default) the TCP table also holds the derived
    NCPA entry, "ncpaPort" names that port, and "resolution" says which
    check each table entry leads to. Pass False for the stored form, to
    compare with a submitted payload.
    """
    row = get_discovery_settings_row()
    data = {}
    for column, config_key, api_key in SETTING_FIELDS:
        value = getattr(row, column) if row is not None else None
        data[api_key] = value if value is not None else current_app.config[config_key]
    data["version"] = row.Version if row is not None else 0
    data["updatedAt"] = row.Updated_At.isoformat() if row is not None else None
    if include_derived:
        add_derived_fields(data)
    return data


def add_derived_fields(data):
    """Add the NCPA entry, "ncpaPort" and "resolution" to API-shaped settings, in place."""
    data["tcpPortServices"] = with_ncpa_entry(data["tcpPortServices"], "tcp")
    data["ncpaPort"] = int(ncpa_port_key())
    data["resolution"] = {
        "tcp": {port: resolve_port_service(name, "tcp") for port, name in data["tcpPortServices"].items()},
        "udp": {port: resolve_port_service(name, "udp") for port, name in data["udpPortServices"].items()},
    }
    return data


def get_discovery_defaults():
    """Return the config.py defaults in the API shape, for "Reset to Defaults"."""
    data = {}
    for _, config_key, api_key in SETTING_FIELDS:
        data[api_key] = current_app.config[config_key]
    return add_derived_fields(data)


# ==========================================================
# VALIDATION
# ==========================================================

def validate_networks(networks):
    """
    Validate and normalize a list of networks to scan. Each entry must be
    an IPv4 address or CIDR network (host bits are cleared, so
    "192.168.1.5/24" becomes "192.168.1.0/24"). Loopback, multicast,
    unspecified and networks larger than a /16 are rejected. Returns the
    normalized list; raises DiscoverySettingsError on bad input.
    """
    if not isinstance(networks, list):
        raise DiscoverySettingsError("Networks must be a list.")
    if len(networks) == 0:
        raise DiscoverySettingsError("At least one network is required.")
    if len(networks) > MAX_NETWORKS:
        raise DiscoverySettingsError(f"No more than {MAX_NETWORKS} networks can be scanned.")

    normalized = []
    for entry in networks:
        if not isinstance(entry, str):
            raise DiscoverySettingsError("Each network must be a string such as 192.168.1.0/24.")
        try:
            network = ipaddress.ip_network(entry.strip(), strict=False)
        except ValueError:
            raise DiscoverySettingsError(f"'{entry}' is not a valid IPv4 network.")

        if network.version != 4:
            raise DiscoverySettingsError(f"'{entry}' is not an IPv4 network.")
        if network.is_loopback:
            raise DiscoverySettingsError(f"'{entry}' is a loopback network. Scanning localhost is not allowed.")
        if network.is_multicast or network.is_unspecified or network.is_reserved:
            raise DiscoverySettingsError(f"'{entry}' cannot be scanned.")
        if network.prefixlen < MIN_PREFIX_LENGTH:
            raise DiscoverySettingsError(
                f"'{entry}' is too large. Networks must be /{MIN_PREFIX_LENGTH} or smaller."
            )

        value = str(network)
        if value in normalized:
            raise DiscoverySettingsError(f"'{value}' is listed more than once.")
        normalized.append(value)

    return normalized


def parse_port(value):
    """
    Return value as a port number if it is an integer (or a string of
    digits) between 1 and 65535, otherwise None.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        port = value
    elif isinstance(value, str) and value.strip().isdigit():
        port = int(value.strip())
    else:
        return None
    if 1 <= port <= 65535:
        return port
    return None


def validate_ports(ports, label):
    """
    Validate and normalize a TCP or UDP port list. Entries are single
    ports (stored as ints) or "start-end" ranges (stored as strings).
    An empty list is allowed and means "use nmap's default ports".
    Raises DiscoverySettingsError on bad input.
    """
    if not isinstance(ports, list):
        raise DiscoverySettingsError(f"{label} ports must be a list.")
    if len(ports) > MAX_PORT_ENTRIES:
        raise DiscoverySettingsError(f"No more than {MAX_PORT_ENTRIES} {label} port entries are allowed.")

    normalized = []
    for entry in ports:
        port = parse_port(entry)
        if port is not None:
            value = port
        else:
            match = PORT_RANGE_PATTERN.match(entry.strip()) if isinstance(entry, str) else None
            if match is None:
                raise DiscoverySettingsError(
                    f"'{entry}' is not a valid {label} port. Use a number (1-65535) or a range like 1-1024."
                )
            start = parse_port(match.group(1))
            end = parse_port(match.group(2))
            if start is None or end is None or start > end:
                raise DiscoverySettingsError(f"'{entry}' is not a valid {label} port range.")
            value = f"{start}-{end}"

        if value in normalized:
            raise DiscoverySettingsError(f"{label} port '{value}' is listed more than once.")
        normalized.append(value)

    return normalized


def validate_port_services(port_services, label):
    """
    Validate a {port: service name} table. Ports must be 1-65535 and names
    must be lowercase letters, digits, "-" or "_" (max 32 chars), since they
    are written into Nagios config. Keys are normalized to strings, matching
    how create_host_cfg looks them up. Raises DiscoverySettingsError on bad
    input.
    """
    if not isinstance(port_services, dict):
        raise DiscoverySettingsError(f"{label} port services must be an object of port: name pairs.")
    if len(port_services) > MAX_OVERRIDES:
        raise DiscoverySettingsError(f"No more than {MAX_OVERRIDES} {label} port services are allowed.")

    normalized = {}
    for port, name in port_services.items():
        parsed_port = parse_port(port)
        if parsed_port is None:
            raise DiscoverySettingsError(f"'{port}' is not a valid {label} port.")
        if not isinstance(name, str) or not SERVICE_NAME_PATTERN.match(name.strip()):
            raise DiscoverySettingsError(
                f"Service name for {label} port {parsed_port} must be lowercase letters, digits, '-' or '_'."
            )
        key = str(parsed_port)
        if key in normalized:
            raise DiscoverySettingsError(f"{label} port {key} is listed more than once.")
        normalized[key] = name.strip()

    return normalized


def validate_tcp_port_services(port_services):
    """
    Validate the TCP table and drop the derived NCPA entry, which is never
    stored. NCPA_PORT cannot be mapped to anything but ncpa.
    """
    normalized = validate_port_services(port_services, "TCP")
    ncpa_key = ncpa_port_key()
    if ncpa_key in normalized:
        if normalized[ncpa_key] != NCPA_SERVICE:
            raise DiscoverySettingsError(
                f"TCP port {ncpa_key} is NCPA's port and always maps to {NCPA_SERVICE}."
            )
        del normalized[ncpa_key]
    return normalized


def validate_discovery_settings(payload):
    """
    Validate every discovery setting in an API payload and return them
    normalized, keyed by DiscoverySettings column name. Raises
    DiscoverySettingsError on the first invalid value, or KeyError when
    a field is missing.
    """
    return {
        "Networks": validate_networks(payload["networks"]),
        "TCP_Ports": validate_ports(payload["tcpPorts"], "TCP"),
        "UDP_Ports": validate_ports(payload["udpPorts"], "UDP"),
        "TCP_Port_Services": validate_tcp_port_services(payload["tcpPortServices"]),
        "UDP_Port_Services": validate_port_services(payload["udpPortServices"], "UDP"),
    }
