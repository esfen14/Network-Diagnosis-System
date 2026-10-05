"""
Editable Network Discovery settings: which networks nmap scans, which
TCP/UDP ports it probes, the "always treat port as" rules (forced
services) and the fallback service names used when nmap only guessed a
service from its port number.

The defaults live in config.py (NETWORKS, TCP_PORTS, UDP_PORTS,
TCP_FORCED_SERVICES, UDP_FORCED_SERVICES, TCP_SERVICE_OVERRIDES,
UDP_SERVICE_OVERRIDES). Once an administrator
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
    ("TCP_Service_Overrides", "TCP_SERVICE_OVERRIDES", "tcpServiceOverrides"),
    ("UDP_Service_Overrides", "UDP_SERVICE_OVERRIDES", "udpServiceOverrides"),
    ("TCP_Forced_Services", "TCP_FORCED_SERVICES", "tcpForcedServices"),
    ("UDP_Forced_Services", "UDP_FORCED_SERVICES", "udpForcedServices"),
]


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


def get_discovery_settings():
    """
    Return every discovery setting in its API shape (camelCase keys),
    with saved values taking precedence over config.py, plus the row's
    version for optimistic concurrency (0 when nothing is saved yet).
    """
    row = get_discovery_settings_row()
    data = {}
    for column, config_key, api_key in SETTING_FIELDS:
        value = getattr(row, column) if row is not None else None
        data[api_key] = value if value is not None else current_app.config[config_key]
    data["version"] = row.Version if row is not None else 0
    data["updatedAt"] = row.Updated_At.isoformat() if row is not None else None
    return data


def get_discovery_defaults():
    """Return the config.py defaults in the API shape, for "Reset to Defaults"."""
    data = {}
    for _, config_key, api_key in SETTING_FIELDS:
        data[api_key] = current_app.config[config_key]
    return data


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


def validate_service_overrides(overrides, label):
    """
    Validate a {port: service name} mapping. Ports must be 1-65535 and
    names must be lowercase letters, digits, "-" or "_" (max 32 chars),
    since they are written into Nagios config. Keys are normalized to
    strings, matching how create_host_cfg looks them up.
    Raises DiscoverySettingsError on bad input.
    """
    if not isinstance(overrides, dict):
        raise DiscoverySettingsError(f"{label} service overrides must be an object of port: name pairs.")
    if len(overrides) > MAX_OVERRIDES:
        raise DiscoverySettingsError(f"No more than {MAX_OVERRIDES} {label} service overrides are allowed.")

    normalized = {}
    for port, name in overrides.items():
        parsed_port = parse_port(port)
        if parsed_port is None:
            raise DiscoverySettingsError(f"'{port}' is not a valid {label} port.")
        if not isinstance(name, str) or not SERVICE_NAME_PATTERN.match(name.strip()):
            raise DiscoverySettingsError(
                f"Service name for {label} port {parsed_port} must be lowercase letters, digits, '-' or '_'."
            )
        key = str(parsed_port)
        if key in normalized:
            raise DiscoverySettingsError(f"{label} port {key} has more than one override.")
        normalized[key] = name.strip()

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
        "TCP_Service_Overrides": validate_service_overrides(payload["tcpServiceOverrides"], "TCP"),
        "UDP_Service_Overrides": validate_service_overrides(payload["udpServiceOverrides"], "UDP"),
        "TCP_Forced_Services": validate_service_overrides(payload["tcpForcedServices"], "TCP"),
        "UDP_Forced_Services": validate_service_overrides(payload["udpForcedServices"], "UDP"),
    }
