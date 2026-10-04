from pathlib import Path
from datetime import datetime, timezone
import hashlib
import re
import subprocess
import shutil
import threading

from app.network_discovery.network_discovery import discover_network
from app.network_discovery.device_identity import nagios_host_name, reconcile_scan
from app.network_discovery.identity_probes import collect_identifiers
from app.network_discovery.port_lifecycle import CONFIG_STATES, mark_ncpa_port, process_device_ports
from app.network_discovery.host_config_templates import *
from app.network_discovery.service_name_migration import migrate_legacy_service_history
from app.network_discovery.plugin_registry import (
    GENERIC_PLUGIN_FOR_TRANSPORT,
    PluginConfigurationError,
    Transport,
    build_service_checks,
    render_command_definition,
    resolve_plugin_command,
    resolve_plugin_name,
    resolve_plugin_variables,
    sanitize_name_part,
)

from app import db
from flask import current_app
import sqlalchemy as sa
from app.system_models import \
    User, \
    UserStatus, \
    NetworkDiscovery, \
    Open_TCP_Services, \
    Open_UDP_Services, \
    SSHCredentials, \
    NCPADeployment, \
    NCPADevicePartition, \
    AgentStatus, \
    DeviceState, \
    PortState
from app.logging import create_network_discovery_status, update_network_discovery_status, calculate_progress, create_skipped_service_logs
from app.logging.deployment_history import update_ncpa_deployment_status
from app.system_models import DiscoveryStatus, DeploymentStatus, NetworkDiscoveryStatus, ServiceIdentification
from app.network_discovery.discovery_settings import get_discovery_setting
import socket
import ipaddress
import tempfile

# Network discovery / host-config settings (DOMAIN, NCPA_PORT,
# HOST_CONFIG_DIR, BACKUP_DIR) and the advanced Nagios settings
# (NAGIOS_HOST_CFG, NAGIOS_BIN, NAGIOS_MAIN_CFG) live in server/config.py's
# Config class. Each function below that needs one reads it from
# current_app.config into a same-named local at the top of the function.
# The forced service lists and fallback service overrides
# (TCP_/UDP_FORCED_SERVICES, TCP_/UDP_SERVICE_OVERRIDES) are editable from the
# Settings page, so they are read through get_discovery_setting() instead,
# which falls back to config.py when nothing has been saved.

PROGRESS_WEIGHT = [40,50,55,60,70,80,90,95,100]

# Progress stages for add_ncpa_port: adding the port to the db, reloading
# hosts, generating the config, validating, and applying it. Imported
# directly by app/ncpa_deployment/ncpa_deployment.py, so this must stay
# a real module-level constant (not a config-backed local alias).
ADD_NCPA_PORT_PROGRESS_WEIGHT = [40, 55, 70, 85, 100]

def _add_space(spaces):
    return "\n" * spaces


# Discovery, add_ncpa_port(), NCPA relocation and user edits all regenerate
# the same hosts.cfg. Everything from "load hosts" to "apply" runs under this
# lock so two of them can never interleave and overwrite each other's result.
# Re-entrant so a caller that already holds it can call helpers that take it.
config_write_lock = threading.RLock()

# The first line of a generated file that differs between otherwise identical
# runs; ignored when deciding whether the config really changed.
GENERATED_AT_LINE = re.compile(r"^\s*#\s+generated at .*$", re.MULTILINE)


# ==========================================================
# PLUGIN SERVICE GENERATION
# ==========================================================
#
# Commands are resolved from the PLUGIN NAME, never the port — see
# plugin_registry.py for the full resolution order. The helpers below only
# gather each host's inputs (discovered ports, system facts, overrides) and
# turn the registry's output into uniquely named services.

def load_host_plugin_facts():
    """
    Return plugin variables that come from the system itself rather than
    from configuration, keyed by NetDiscoveryID and then plugin name — for
    now each deployed NCPA agent's token and recorded partitions, e.g.
    {12: {"ncpa": {"token": "...", "partitions": ["sda1"]}}}.

    Devices without a deployed token are left out, so their NCPA port falls
    back to a plain TCP check. If a device has several deployments, the most
    recent one wins. Read-only; does not touch the session.
    """
    deployments = db.session.scalars(
        sa.select(NCPADeployment)
        .where(NCPADeployment.Token.is_not(None))
        .order_by(NCPADeployment.NCPADeployID)
    ).all()

    partitions_by_deployment = {}
    partitions = db.session.scalars(
        sa.select(NCPADevicePartition).order_by(NCPADevicePartition.PartitionID)
    ).all()
    for partition in partitions:
        partitions_by_deployment.setdefault(partition.NCPADeployID, []).append(partition.Name)

    facts = {}
    for deployment in deployments:
        facts.setdefault(deployment.NetworkDiscoveryID, {})["ncpa"] = {
            "token": deployment.Token,
            "partitions": partitions_by_deployment.get(deployment.NCPADeployID, []),
        }
    return facts


def plan_plugin_services(plugin_name, service_label, port, transport, facts, overrides, app_config):
    """
    Resolve one discovered port into the services plugin_name produces for
    it — one per metric for multi-check plugins such as SNMP and NCPA.

    Returns a list of dicts with base_name ("<label>[-<metric>]-<port>"; the
    protocol is appended by finalize_service_names), transport, check_command and plugin. Raises PluginConfigurationError if
    the plugin cannot be configured for this host.
    """
    variables = resolve_plugin_variables(
        plugin_name,
        app_config,
        discovered={"port": port, **facts.get(plugin_name, {})},
        overrides=overrides.get(plugin_name),
    )

    planned = []
    for check, service_variables in build_service_checks(plugin_name, variables):
        name_parts = [service_label]
        if check.metric:
            name_parts.append(sanitize_name_part(check.metric))
        name_parts.append(str(service_variables.get("port", port)))

        planned.append({
            "base_name": "-".join(name_parts),
            "transport": transport,
            "check_command": resolve_plugin_command(plugin_name, service_variables, transport),
            "plugin": plugin_name,
        })
    return planned


def finalize_service_names(planned):
    """
    Turn planned services into (service_name, check_command, plugin) tuples.

    Every service is named "{service}[-{metric}]-{port}-{protocol}" in
    lowercase, e.g. "ssh-22-tcp", "dns-53-udp", "ncpa-cpu-5693-tcp". The port
    and protocol are always present, so names are unique per host by
    construction. If two services still end up with the same name (for
    instance a metric configured twice) the later one is dropped with a
    warning rather than renamed, since Nagios rejects duplicate services.
    """
    services = []
    used_names = set()
    for service in planned:
        name = f"{service['base_name']}-{service['transport'].value}".lower()
        if name in used_names:
            current_app.logger.warning(
                f"Skipping duplicate service name '{name}'; check the plugin's "
                f"configured metrics."
            )
            continue

        used_names.add(name)
        services.append((name, service["check_command"], service["plugin"]))
    return services


def build_host_services(host_data, facts, app_config, skipped=None):
    """
    Plan every Nagios service for one host from its discovered TCP and UDP
    services. Each port resolves to a plugin by its service NAME; the port
    is only passed along as that plugin's "port" variable.

    If the matched TCP plugin cannot be configured for this host (e.g. NCPA
    with no deployed token, MySQL with no user) the port falls back to the
    generic TCP port check so it is still monitored.

    UDP ports are only monitored through a plugin that speaks their protocol
    (dns, ntp, snmp). A generic UDP check cannot tell a healthy port from a
    dead one — most UDP services ignore an empty probe — so a UDP port with no
    matching plugin, or whose plugin cannot be configured, is skipped.

    Every skipped port is appended to skipped (if a list is given) as a dict
    with hostname, port, protocol, service_name and reason. Reasons never
    contain variable values, so secrets are not leaked into the log.

    Expects host_data in _load_monitored_hosts()'s shape and facts from
    load_host_plugin_facts(). Returns (service_name, check_command, plugin)
    tuples.
    """
    hostname = host_data["data"]["hostname"]
    overrides = host_data["data"].get("plugin_variables")
    if not isinstance(overrides, dict):
        overrides = {}
    host_facts = facts.get(host_data["data"].get("net_discovery_id"), {})

    def skip(discovered_name, port, transport, reason):
        current_app.logger.warning(
            f"Skipping {discovered_name} {port}/{transport.value} on {hostname}: {reason}"
        )
        if skipped is not None:
            skipped.append({
                "hostname": hostname,
                "port": port,
                "protocol": transport.value,
                "service_name": discovered_name,
                "reason": reason,
            })

    planned = []
    for transport in Transport:
        discovered_services = host_data["services"].get(transport.value.lower(), {})
        generic_plugin = GENERIC_PLUGIN_FOR_TRANSPORT[transport]

        for port, service_data in discovered_services.items():
            discovered_name = service_data.get("service_name") or "unknown"
            # A monitored port's plugin is frozen when it starts being
            # monitored; only ports that predate that fall back to resolving.
            plugin_name = service_data.get("plugin_name") or resolve_plugin_name(discovered_name, transport)
            service_label = sanitize_name_part(discovered_name)
            if plugin_name != generic_plugin:
                service_label = plugin_name

            if transport is Transport.UDP and plugin_name == generic_plugin:
                skip(discovered_name, port, transport,
                     "No plugin can check this UDP service.")
                continue

            try:
                planned.extend(plan_plugin_services(
                    plugin_name, service_label, port, transport, host_facts, overrides, app_config
                ))
                continue
            except PluginConfigurationError as e:
                if plugin_name == generic_plugin or transport is Transport.UDP:
                    skip(discovered_name, port, transport, str(e))
                    continue
                current_app.logger.warning(
                    f"{hostname} {discovered_name} {port}/{transport.value}: {e} "
                    f"Falling back to the generic {generic_plugin} check."
                )

            try:
                planned.extend(plan_plugin_services(
                    generic_plugin, sanitize_name_part(discovered_name), port, transport,
                    host_facts, overrides, app_config
                ))
            except PluginConfigurationError as e:
                skip(discovered_name, port, transport, str(e))

    return finalize_service_names(planned)

# Service names of the most recently generated candidate, {hostname: [names]}.
# Only read under config_write_lock, right after that candidate is applied.
_last_generated_names = {}


def unconfirmed_udp_skips(discovered_hosts):
    """
    Skipped-service entries for UDP ports nmap reported only as "open|filtered":
    the host ignored the probe, so the port is unconfirmed and never monitored.
    """
    entries = []
    for hosts in discovered_hosts.values():
        for ip, host_data in hosts.items():
            data = host_data.get("data", {})
            for port, info in (data.get("udp_unconfirmed") or {}).items():
                entries.append({
                    "hostname": data.get("hostname") or ip,
                    "ip_address": ip,
                    "port": port,
                    "protocol": "UDP",
                    "service_name": info.get("service_name") or "unknown",
                    "reason": "UDP port unconfirmed (open|filtered): the host did not answer nmap's probe.",
                })
    return entries


def _create_host_cfg_file(discovered_hosts, skipped=None):
    """
    Creates a new host configuration file.

    If skipped is a list, every discovered port that was not turned into a
    Nagios service is appended to it (see build_host_services), with the
    host's ip_address added.

    Returns:
        pathlib.Path: Path to the newly created file.
    """

    HOST_CONFIG_DIR = current_app.config['HOST_CONFIG_DIR']
    HOST_CONFIG_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%d-%m-%Y-%H-%M")
    filename = f"host-{timestamp}.cfg"

    cfg_path = HOST_CONFIG_DIR / filename

    host_config = []

    host_config.append(
        f"""
        ##########################################################################
        #   host.cfg file for Nagios generated by Pin Point
        #   
        #   generated at {timestamp}
        ##########################################################################
        """
    )

    host_config.append(_add_space(4))

    host_config.append(
        f"""

        #
        # Define Contacts
        #  

        """
    )

    users = db.session.scalars(
        sa.select(User).where(
            User.Status == UserStatus.ACTIVE
        )
    ).all()

    for user in users:
        user_information = {
            "contact_name": str(user.Email),
            "use": "generic-contact",
            "full_name": str(user.First_Name + " " + user.Last_Name),
            "email_address": str(user.Email)
        }

        host_config.append(create_contact(user_information))
        host_config.append(_add_space(4))

    # add the users to the contact group
    host_config.append(
        f"""

        #
        # Define Contactgroups
        #  
            
        """
    )

    contact_group = {
        "group_name": "system_users",
        "alias_name": "Nagios Users",
        "member_list": ",".join(user.Email for user in users)
    }

    host_config.append(create_contactgroup(contact_group))

    host_config.append(_add_space(4))


    host_config.append(
        f"""

        #
        # Define Hosts
        # 

        """
    )

    hostgroups = {
                "Linux":{
                    "devices":[]
                },
                "Windows":{
                    "devices":[]
                },
                "Mac OS X":{
                    "devices":[]
                },
                "Android":{
                    "devices":[]
                },
                "iOS":{
                    "devices":[]
                },
                "ChromeOS":{
                    "devices":[]
                },
                "OpenBSD":{
                    "devices":[]
                },
                "NetBSD":{
                    "devices":[]
                },
                "Mikrotik":{
                    "devices":[]
                },
                "OpenWRT":{
                    "devices":[]
                },
                "Cisco":{
                    "devices":[]
                },
                "Unknown":{
                    "devices":[]
                }

            }

    # System-derived plugin variables (e.g. NCPA tokens and partitions),
    # fetched once for all hosts rather than once per host.
    plugin_facts = load_host_plugin_facts()

    # Plugins actually used by at least one service - each needs its own
    # `define command` object, rendered once at the end of the file.
    used_plugins = set()
    global _last_generated_names
    generated_names = _last_generated_names = {}

    for hosts in discovered_hosts.values():
        for ip, host_data in hosts.items():
            # The dict key is the IP unless two devices share it (a device
            # whose address is unknown); "address" always has the real one.
            ip = host_data["data"].get("address", ip)
            active_checks = host_data["data"].get("active_checks_enabled", True)
            inactive_note = "Address unknown - waiting to be found"

            host = {}
            host["host_name"] = host_data["data"]["hostname"]
            host["alias"] = "alias"
            host["address"] = ip
            host["contact_groups"] = "system_users"
            if not active_checks:
                host["active_checks_enabled"] = False
                host["notes"] = inactive_note
            host_config.append(create_host(host))
            host_config.append(_add_space(4))

            # FIX (BUG_FINDINGS.md, Bug 1): restored — commit 6109a08e removed
            # this along with service generation, which left every OS
            # hostgroup below empty so none were ever written to the config.
            # Assigns the host to its OS hostgroup ("Unknown" if the OS isn't
            # one of the predefined groups).
            os_name = host_data["data"]["os"]
            if os_name in hostgroups:
                hostgroups[os_name]["devices"].append(host_data["data"]["hostname"])
            else:
                hostgroups["Unknown"]["devices"].append(host_data["data"]["hostname"])

            host_config.append(
                f"""

                #
                # Define Services of
                # Hostname: {host_data["data"]["hostname"]}
                # IP: {ip}
                #

                """
            )

            # FIX (BUG_FINDINGS.md, Bug 1): restored service generation.
            # Without it the generated config only had `define host` blocks,
            # so Nagios checked host up/down but never ran any plugin.
            # Each discovered port resolves to a plugin by service name
            # (plugin_registry.py); a plugin may produce several services
            # (one per SNMP OID, one per NCPA metric/partition), all bound to
            # this host only.
            host_skipped = []
            host_services = build_host_services(host_data, plugin_facts, current_app.config, host_skipped)
            if skipped is not None:
                for entry in host_skipped:
                    skipped.append({**entry, "ip_address": ip})

            generated_names[host_data["data"]["hostname"]] = [name for name, _c, _p in host_services]

            for service_name, command, plugin_name in host_services:
                # Remember the plugin so its `define command` is written once
                # in the "Define Commands" section at the end of the file.
                used_plugins.add(plugin_name)

                service = {
                    "host_name": host_data["data"]["hostname"],
                    "service_name": service_name,
                    "contact_groups": "system_users"
                }
                if not active_checks:
                    service["active_checks_enabled"] = False
                    service["notes"] = inactive_note

                host_config.append(
                    create_service(service,command)
                )
                host_config.append(_add_space(4))

    host_config.append(
        f"""

        #
        # Define Hostgroups 
        #  

        """
    )

    host_config.append(_add_space(4))

    host_config.append(
        f"""
    
        #
        # Define OS Groups
        #  
    
        """
    )

    for os, group_devices in hostgroups.items():

        devices = group_devices["devices"]

        if not devices:
            continue

        host_group={
            "group_name": os,
            "alias_name": os,
            "member_list": ",".join(devices)
        } 
        host_config.append(create_hostgroup(host_group))
        host_config.append(_add_space(4))

    # FIX (BUG_FINDINGS.md, Bug 1): restored the command definitions.
    # Every check_command above refers to a pinpoint_nd_<plugin> command;
    # Nagios rejects the config if that command isn't defined, so write one
    # `define command` per plugin actually used (sorted for stable output).
    host_config.append(
        f"""

        #
        # Define Commands
        #

        """
    )

    for plugin_name in sorted(used_plugins):
        host_config.append(render_command_definition(plugin_name))
        host_config.append(_add_space(2))

    with open(cfg_path, "w") as f:
        # remember to f.write("string") here after you're done with discovering devices
        f.write("".join(host_config))
    return cfg_path

def get_monitoring_server_ips():
    ips = set()

    for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        ip = info[4][0]
        address = ipaddress.ip_address(ip)

        if not address.is_loopback:
            ips.add(ip)

    return ips

def _save_discovered_hosts(discovered_hosts, network_discovery_id, progress_weight):
    """
    Save one scan's results. The scan only reports what it saw; the
    reconciler (device_identity.py) decides which known device each result is,
    so a changed IP moves a device instead of duplicating it and one device's
    record is never reused for another. Ports go through the port lifecycle
    (port_lifecycle.py): nothing is deleted, a missed port only counts while
    its device was seen, and new ports start as suggestions unless their
    service is auto-monitored.

    Everything is committed at once; on any error the whole save is rolled
    back and logged. Returns {(network, ip): NetworkDiscovery} for the saved
    observations (empty on failure).
    """
    total_hosts = sum(len(hosts) for hosts in discovered_hosts.values())
    processed_hosts = 0

    monitoring_server_ips = get_monitoring_server_ips()

    try:
        devices = reconcile_scan(discovered_hosts, network_discovery_id, monitoring_server_ips)

        for (network, ip_address), device in devices.items():
            host_data = discovered_hosts[network][ip_address]
            services = host_data.get("services", {})

            # The device was seen in this scan, so missed ports count.
            process_device_ports(device, services, host_seen=True)

            processed_hosts += 1

            progress = calculate_progress(
                processed_hosts,
                total_hosts,
                progress_weight - 10,
                progress_weight
                )

            if processed_hosts % 10 == 0 or processed_hosts == total_hosts:
                update_network_discovery_status(
                    network_discovery_id,
                    DiscoveryStatus.RUNNING,
                    progress,
                    "Saving hosts to database."
                )

        # Save everything at once
        db.session.commit()
        return devices
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(f"Failed to insert new hosts: {e}")
        return {}

def _backup_running_host_cfg():
    """
    Creates a backup of Nagios' currently running hosts.cfg.

    Returns:
        pathlib.Path: Path to the backup file.
    """

    BACKUP_DIR = current_app.config['BACKUP_DIR']
    NAGIOS_HOST_CFG = current_app.config['NAGIOS_HOST_CFG']
    BACKUP_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%d-%m-%Y-%H-%M")
    backup_name = f"host-{timestamp}.cfg"

    backup_path = BACKUP_DIR / backup_name

    shutil.copyfile(NAGIOS_HOST_CFG, backup_path)

    return backup_path

def _load_monitored_hosts(network_discovery_id=None, progress_weight=None):
    """
    Rebuilds a discovered_hosts dict from the database, in the same
    shape as discover_network()'s output:

        {
            network: {
                ip_address: {
                    "data": {"hostname": <Nagios host_name>, "mac_address": ..., "os": ...,
                             "net_discovery_id": ..., "plugin_variables": {...} | None,
                             "address": <current IP>, "active_checks_enabled": bool},
                    "services": {"tcp": {port: {"service_name": ..., "plugin_name": ...}}, "udp": {...}}
                }
            }
        }

    "hostname" is the device's stable Nagios host_name, not whatever DNS
    reported. Devices that are ACTIVE, MISSING or ADDRESS_UNKNOWN are included
    (the last with active checks disabled); RETIRED and MERGED are not. Only
    MONITORED and MISSING ports produce services. If two devices share an IP
    (a device whose address is unknown), the later one's key is
    "<ip>#<device id>"; "address" always holds the real IP.

    Returns:
        dict: discovered_hosts-shaped dict sourced from the DB.
    """
    discovered_hosts = {}

    devices = db.session.scalars(
        sa.select(NetworkDiscovery).where(
            NetworkDiscovery.Include_Device_In_Scanning.is_(True),
            NetworkDiscovery.Device_State.in_(
                (DeviceState.ACTIVE, DeviceState.MISSING, DeviceState.ADDRESS_UNKNOWN)
            ),
        ).order_by(NetworkDiscovery.NetDiscoveryID)
    ).all()

    if not devices:
        return discovered_hosts

    device_ids = [device.NetDiscoveryID for device in devices]

    # Fetch all services in two queries instead of one query per device (N+1)
    tcp_services = db.session.scalars(
        sa.select(Open_TCP_Services).where(
            Open_TCP_Services.NetDiscoveryID.in_(device_ids),
            Open_TCP_Services.Port_State.in_(CONFIG_STATES),
        )
    ).all()

    udp_services = db.session.scalars(
        sa.select(Open_UDP_Services).where(
            Open_UDP_Services.NetDiscoveryID.in_(device_ids),
            Open_UDP_Services.Port_State.in_(CONFIG_STATES),
        )
    ).all()

    # Group services by their owning device, keyed by port
    tcp_by_device = {}
    for service in tcp_services:
        tcp_by_device.setdefault(service.NetDiscoveryID, {})[str(service.Port_Number)] = {
            "service_name": service.Service_Name,
            "plugin_name": service.Plugin_Name,
        }

    udp_by_device = {}
    for service in udp_services:
        udp_by_device.setdefault(service.NetDiscoveryID, {})[str(service.Port_Number)] = {
            "service_name": service.Service_Name,
            "plugin_name": service.Plugin_Name,
        }

    total_hosts = len(devices)
    processed_hosts = 0

    for device in devices:
        bucket = discovered_hosts.setdefault(device.Network, {})
        key = device.IP_Address
        if key in bucket:
            key = f"{device.IP_Address}#{device.NetDiscoveryID}"

        bucket[key] = {
            "data": {
                "hostname": nagios_host_name(device),
                "mac_address": device.MAC_Address,
                "os": device.OS_Type,
                # Used by build_host_services() to look up this device's
                # plugin facts and per-host plugin variable overrides.
                "net_discovery_id": device.NetDiscoveryID,
                "plugin_variables": device.Plugin_Variables,
                "address": device.IP_Address,
                "active_checks_enabled": device.Device_State is not DeviceState.ADDRESS_UNKNOWN,
            },
            "services": {
                "tcp": tcp_by_device.get(device.NetDiscoveryID, {}),
                "udp": udp_by_device.get(device.NetDiscoveryID, {}),
            }
        }

        processed_hosts += 1

        if network_discovery_id is not None and (
            processed_hosts % 10 == 0 or processed_hosts == total_hosts
        ):
            progress = calculate_progress(
                processed_hosts,
                total_hosts,
                progress_weight - 10,
                progress_weight
            )
            update_network_discovery_status(
                network_discovery_id,
                DiscoveryStatus.RUNNING,
                progress,
                "Loading discovered hosts from database"
            )

    return discovered_hosts

def _build_temp_cfg_lines(main_cfg_lines, candidate_cfg_path):
    """
    Takes the real nagios.cfg's lines and returns a new list of lines
    where the line pointing to the live hosts.cfg has been swapped
    to point at our candidate file instead.

    Returns:
        tuple[list[str], bool]: (new_lines, was_replaced)
    """
    NAGIOS_HOST_CFG = current_app.config['NAGIOS_HOST_CFG']
    new_lines = []
    replaced = False
    for line in main_cfg_lines:
        stripped = line.strip()
        points_to_live_hosts_cfg = (
            stripped.startswith("cfg_file") and str(NAGIOS_HOST_CFG) in stripped
        )

        if points_to_live_hosts_cfg:
            new_lines.append(f"cfg_file={candidate_cfg_path}\n")
            replaced = True
        else:
            new_lines.append(line)

    return new_lines, replaced

def _write_temp_cfg(lines):
    """
    Writes the given lines to a throwaway temp file and returns its path.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".cfg", delete=False) as f:
        f.writelines(lines)
        return Path(f.name)

def _run_nagios_verify(main_cfg_path):
    """
    Runs `nagios -v` against the given main config file.

    Returns:
        tuple[bool, str]: (is_valid, output)
    """
    NAGIOS_BIN = current_app.config['NAGIOS_BIN']
    try:
        result = subprocess.run(
            [str(NAGIOS_BIN), "-v", str(main_cfg_path)],
            capture_output=True,
            text=True,
            timeout=60
        )
        is_valid = result.returncode == 0
        return is_valid, result.stdout + result.stderr

    except subprocess.TimeoutExpired:
        return False, "Nagios validation timed out."

    except FileNotFoundError:
        return False, f"Nagios binary not found at {NAGIOS_BIN}."

def _validate_config(cfg_path):
    """
    Validates a candidate host config file WITHOUT touching the live
    running config.

    How it works, step by step:
      1. Read the real nagios.cfg
      2. Swap its hosts.cfg reference to point at our candidate file instead
      3. Write that as a throwaway temp file
      4. Run `nagios -v` against the temp file
      5. Delete the temp file, return whatever Nagios said

    Args:
        cfg_path (pathlib.Path): Path to the candidate host cfg file.

    Returns:
        tuple[bool, str]: (is_valid, output)
    """
    NAGIOS_MAIN_CFG = current_app.config['NAGIOS_MAIN_CFG']
    NAGIOS_HOST_CFG = current_app.config['NAGIOS_HOST_CFG']

    if not NAGIOS_MAIN_CFG.exists():
        return False, f"Nagios main config not found at {NAGIOS_MAIN_CFG}"

    # Step 1: read the real nagios.cfg
    with open(NAGIOS_MAIN_CFG) as f:
        main_cfg_lines = f.readlines()

    # Step 2: point it at our candidate file instead of the live hosts.cfg
    temp_cfg_lines, replaced = _build_temp_cfg_lines(main_cfg_lines, cfg_path)

    if not replaced:
        return False, (
            f"Could not find a cfg_file directive pointing to {NAGIOS_HOST_CFG} "
            f"inside {NAGIOS_MAIN_CFG}. Nothing was validated."
        )

    # Step 3: write it out as a throwaway file
    temp_cfg_path = _write_temp_cfg(temp_cfg_lines)

    # Step 4: actually run the validation
    try:
        return _run_nagios_verify(temp_cfg_path)

    # Step 5: always clean up the temp file, pass or fail
    finally:
        temp_cfg_path.unlink(missing_ok=True)

def _apply_new_host_cfg(cfg_path):
    """
    Applies a validated candidate host config as the new live Nagios config.

    IMPORTANT: This assumes cfg_path has ALREADY been validated via
    _validate_config(). This function does not re-validate — call order
    matters (see __main__).

    Steps:
      1. Backup the current live hosts.cfg
      2. Copy the candidate config into the live Nagios path
      3. Reload Nagios so it picks up the new config
      4. If the reload fails, roll back to the backup automatically

    Args:
        cfg_path (pathlib.Path): Path to the validated candidate config file.

    Returns:
        tuple[bool, str]: (success, message)
            success - True if the config was applied and Nagios reloaded cleanly
            message - human-readable detail, useful for logging/UI feedback
    """
    NAGIOS_HOST_CFG = current_app.config['NAGIOS_HOST_CFG']
    try:
        backup_path = _backup_running_host_cfg()
    except Exception as e:
        return False, f"Failed to back up current config, aborting apply: {e}"

    try:
        shutil.copyfile(cfg_path, NAGIOS_HOST_CFG)
    except Exception as e:
        return False, f"Failed to copy new config into place: {e}"

    try:
        result = subprocess.run(
            ["sudo", "-n", "systemctl", "reload", "nagios"],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"reload exited with code {result.returncode}: "
                f"{result.stdout}{result.stderr}".strip()
            )

    except Exception as e:
        # Reload failed (nonzero exit, timeout, or could not run) — roll back
        # to the last known-good config so Nagios never keeps running on a
        # broken/half-applied file
        current_app.logger.error(f"Nagios reload failed: {e}")
        shutil.copyfile(backup_path, NAGIOS_HOST_CFG)
        # Bring the daemon back in line with the restored file.
        try:
            subprocess.run(["sudo", "-n", "systemctl", "reload", "nagios"],
                           capture_output=True, text=True, timeout=30)
        except Exception as reload_error:
            current_app.logger.error(f"Nagios reload after rollback failed: {reload_error}")
        return False, (
            f"Failed to reload Nagios after applying new config. "
            f"Rolled back to backup at {backup_path}. Error: {e}"
        )

    try:
        migrate_legacy_service_history(_last_generated_names)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Could not carry service history over to the new service names.")

    return True, f"Applied {cfg_path} successfully. Backup stored at {backup_path}"

def config_fingerprint(text):
    """
    SHA-256 of a generated hosts.cfg with its "generated at" timestamp line
    removed, so two runs that produce the same hosts and services hash alike.
    """
    return hashlib.sha256(GENERATED_AT_LINE.sub("", text).encode("utf-8")).hexdigest()


def config_unchanged(cfg_path):
    """
    True if the candidate config is identical (ignoring its timestamp) to the
    hosts.cfg Nagios is running, so validating, applying and reloading can be
    skipped. False if the live file is missing or unreadable.
    """
    NAGIOS_HOST_CFG = current_app.config['NAGIOS_HOST_CFG']
    try:
        live = Path(NAGIOS_HOST_CFG).read_text()
        candidate = Path(cfg_path).read_text()
    except OSError:
        return False
    return config_fingerprint(live) == config_fingerprint(candidate)


def _collect_identifiers(network_discovery_id, discovered_hosts, progress_weight):
    """
    Probe every discovered host for identity evidence (NCPA certificate when
    port 5693 is open, SSH host key when port 22 is) and store it in
    host_data["data"]["identifiers"] for the reconciler. Replaces the old
    step that invented "<ip>.<domain>" names: a host's Nagios name is now
    chosen once, when its device is created (device_identity.py), and never
    derives from its IP. A probe that fails is skipped.
    """
    total_hosts = sum(len(hosts) for hosts in discovered_hosts.values())
    processed_hosts = 0

    for hosts in discovered_hosts.values():
        for ip, host_data in hosts.items():
            host_data["data"]["identifiers"] = collect_identifiers(
                ip, host_data.get("services", {}).get("tcp", {})
            )

            processed_hosts += 1

            progress = calculate_progress(
                processed_hosts,
                total_hosts,
                progress_weight - 10,
                progress_weight
            )

            if processed_hosts % 10 == 0 or processed_hosts == total_hosts:
                update_network_discovery_status(
                    network_discovery_id,
                    DiscoveryStatus.RUNNING,
                    progress,
                    "Collecting device identity"
                )

    return discovered_hosts

def apply_service_rules(service_data, port_id, forced_services, fallback_services):
    """
    Decide one scanned port's service name from nmap's result
    ({"service_name", "identified_by"}, see network_discovery.service_from_nmap)
    and the configured port rules, in place. An "always treat port as" rule
    wins over everything nmap reported (PORT_RULE). A fallback name only
    replaces a guess nmap made from the port number; a fingerprinted service
    keeps nmap's name. A port pinned by an operator is handled later by the
    port lifecycle, which never renames it.
    """
    identified_by = service_data.get("identified_by") or ServiceIdentification.PORT_HINT.name
    service_data["identified_by"] = identified_by

    if port_id in forced_services:
        service_data["service_name"] = forced_services[port_id]
        service_data["identified_by"] = ServiceIdentification.PORT_RULE.name
    elif identified_by == ServiceIdentification.PORT_HINT.name and port_id in fallback_services:
        service_data["service_name"] = fallback_services[port_id]
    return service_data


def _apply_service_rules(network_discovery_id, discovered_hosts, protocol, forced_services, fallback_services, progress_weight):
    """
    Apply apply_service_rules() to every scanned port of one protocol and
    report progress. Returns discovered_hosts, changed in place.
    """
    total_services = sum(
        len(host_data["services"].get(protocol, {}))
        for hosts in discovered_hosts.values()
        for host_data in hosts.values()
    )

    if total_services == 0:
        update_network_discovery_status(
            network_discovery_id,
            DiscoveryStatus.RUNNING,
            progress_weight,
            f"No {protocol.upper()} services to identify"
        )
        return discovered_hosts

    processed_services = 0

    for hosts in discovered_hosts.values():

        for host_data in hosts.values():

            services = host_data["services"].get(protocol, {})

            for port_id, service_data in services.items():

                apply_service_rules(service_data, port_id, forced_services, fallback_services)

                processed_services += 1

                progress = calculate_progress(
                                processed_services,
                                total_services,
                                progress_weight - 5,
                                progress_weight
                            )

                if processed_services % 10 == 0 or processed_services == total_services:
                    update_network_discovery_status(
                        network_discovery_id,
                        DiscoveryStatus.RUNNING,
                        progress,
                        f"Identifying {protocol} services"
                    )

    return discovered_hosts

def mark_discovery_interrupted(network_discovery_id):
    """
    Record that a discovery run was cancelled through the stop route so
    its status leaves "Running" and pollers see it as finished. Keeps the
    progress the run had reached. Commits via update_network_discovery_status.
    """
    status = db.session.get(NetworkDiscoveryStatus, network_discovery_id)
    progress = status.Progress if status is not None else 0

    update_network_discovery_status(
        network_discovery_id,
        DiscoveryStatus.INTERRUPTED,
        progress,
        "Network discovery was cancelled.",
        datetime.now(timezone.utc)
    )


def discover_network_create_hosts(app, user_id, stop_event):
    network_discovery_id = None
   
    with app.app_context():
        try:
            TCP_SERVICE_OVERRIDES = get_discovery_setting('TCP_SERVICE_OVERRIDES')
            UDP_SERVICE_OVERRIDES = get_discovery_setting('UDP_SERVICE_OVERRIDES')
            TCP_FORCED_SERVICES = get_discovery_setting('TCP_FORCED_SERVICES')
            UDP_FORCED_SERVICES = get_discovery_setting('UDP_FORCED_SERVICES')

            print("Created Log")
            network_discovery_id = create_network_discovery_status(user_id).DiscoveryStatusID

            if stop_event.is_set():
                mark_discovery_interrupted(network_discovery_id)
                return
            
            # Gets the network info
            print("Discovering Hosts")
            discovered_hosts = discover_network(network_discovery_id, PROGRESS_WEIGHT[0], stop_event)

            if discovered_hosts is None:
                mark_discovery_interrupted(network_discovery_id)
                return

            if stop_event.is_set():
                mark_discovery_interrupted(network_discovery_id)
                return
            
            # Collects identity evidence (NCPA certificate, SSH host key)
            discovered_hosts = _collect_identifiers(network_discovery_id, discovered_hosts, PROGRESS_WEIGHT[1])

            if stop_event.is_set():
                mark_discovery_interrupted(network_discovery_id)
                return
            
            # Port rules: "always treat port as" wins; fallback names only
            # replace a service nmap guessed from the port number.
            discovered_hosts = _apply_service_rules(network_discovery_id, discovered_hosts, "tcp", TCP_FORCED_SERVICES, TCP_SERVICE_OVERRIDES, PROGRESS_WEIGHT[2])
            discovered_hosts = _apply_service_rules(network_discovery_id, discovered_hosts, "udp", UDP_FORCED_SERVICES, UDP_SERVICE_OVERRIDES, PROGRESS_WEIGHT[3])

            if stop_event.is_set():
                mark_discovery_interrupted(network_discovery_id)
                return
            
            # Save it to the database
            _save_discovered_hosts(discovered_hosts, network_discovery_id, PROGRESS_WEIGHT[4])

            if stop_event.is_set():
                mark_discovery_interrupted(network_discovery_id)
                return
            
            # One writer at a time: load -> generate -> validate -> apply.
            with config_write_lock:
                system_hosts = _load_monitored_hosts(network_discovery_id, PROGRESS_WEIGHT[5])

                if stop_event.is_set():
                    mark_discovery_interrupted(network_discovery_id)
                    return
            
                skipped_services = []
                new_cfg = _create_host_cfg_file(system_hosts, skipped_services)
                print(f"Created: {new_cfg}")
                skipped_services.extend(unconfirmed_udp_skips(discovered_hosts))
                create_skipped_service_logs(network_discovery_id, skipped_services)
                update_network_discovery_status(
                    network_discovery_id,
                    DiscoveryStatus.RUNNING,
                    PROGRESS_WEIGHT[6],
                    "Generated new Nagios configuration"
                )

                # Nothing really changed (same hosts, services and contacts):
                # leave Nagios alone instead of validating and reloading.
                if config_unchanged(new_cfg):
                    new_cfg.unlink(missing_ok=True)
                    update_network_discovery_status(
                        network_discovery_id,
                        DiscoveryStatus.SUCCESS,
                        PROGRESS_WEIGHT[8],
                        "Host configuration unchanged; Nagios was not reloaded",
                        datetime.now(timezone.utc)
                    )
                    return

                if stop_event.is_set():
                    mark_discovery_interrupted(network_discovery_id)
                    return
            
                update_network_discovery_status(
                    network_discovery_id,
                    DiscoveryStatus.RUNNING,
                    PROGRESS_WEIGHT[7],
                    "Validating config"
                )
            
                is_valid, result = _validate_config(new_cfg)

                if stop_event.is_set():
                    mark_discovery_interrupted(network_discovery_id)
                    return
            
                if is_valid:
                    applied, apply_message = _apply_new_host_cfg(new_cfg)

                    if applied:
                        update_network_discovery_status(
                            network_discovery_id,
                            DiscoveryStatus.SUCCESS,
                            PROGRESS_WEIGHT[8],
                            "New host.cfg successfully applied",
                            datetime.now(timezone.utc)
                            )
                        print(apply_message)
                    else:
                        update_network_discovery_status(
                            network_discovery_id,
                            DiscoveryStatus.FAILED,
                            PROGRESS_WEIGHT[8],
                            "Config not applied",
                            datetime.now(timezone.utc)
                            )
                        print(apply_message)

                else:
                    update_network_discovery_status(
                        network_discovery_id,
                        DiscoveryStatus.FAILED,
                        PROGRESS_WEIGHT[8],
                        "Config failed to validate",
                        datetime.now(timezone.utc),
                        result
                    )
                    print(result)
        except Exception as e:
            app.logger.exception(
                f"Network discovery failed."
            )
            if network_discovery_id is not None:
                update_network_discovery_status(
                    network_discovery_id,
                    DiscoveryStatus.FAILED,
                    100,
                    "Network discovery failed",
                    datetime.now(timezone.utc),
                    str(e)
                )

def add_ncpa_port(app, successful_device, ncpa_deployment_status_id, stop_event):
    with app.app_context():
        try:
            NCPA_PORT = current_app.config['NCPA_PORT']
            total_devices = len(successful_device)
            processed_devices = 0

            # Add the NCPA port to Open_TCP_Services for each device that was
            # successfully deployed. Unlike discover_network_create_hosts,
            # there's no nmap scan here — the port was already verified open
            # by the caller (after NCPA install), so we just insert an
            # Open_TCP_Services entry for NCPA_PORT on each device.
            for device_id in successful_device:
                if stop_event.is_set():
                    update_ncpa_deployment_status(
                        ncpa_deployment_status_id,
                        DeploymentStatus.INTERRUPTED,
                        calculate_progress(processed_devices, total_devices, 0, ADD_NCPA_PORT_PROGRESS_WEIGHT[0]),
                        "Adding NCPA port was stopped by user."
                    )
                    return

                # Upserts the NCPA port as MONITORED with Source NCPA, which
                # also protects it from being archived by later scans.
                mark_ncpa_port(device_id)

                processed_devices += 1

                progress = calculate_progress(
                    processed_devices,
                    total_devices,
                    0,
                    ADD_NCPA_PORT_PROGRESS_WEIGHT[0]
                )

                if processed_devices % 10 == 0 or processed_devices == total_devices:
                    update_ncpa_deployment_status(
                        ncpa_deployment_status_id,
                        DeploymentStatus.RUNNING,
                        progress,
                        "Adding NCPA port to database."
                    )

            db.session.commit()

            if stop_event.is_set():
                update_ncpa_deployment_status(
                    ncpa_deployment_status_id,
                    DeploymentStatus.INTERRUPTED,
                    ADD_NCPA_PORT_PROGRESS_WEIGHT[0],
                    "Adding NCPA port was stopped by user."
                )
                return

            # Reload the monitored hosts from the database so the newly added
            # port is reflected in the generated config
            # One writer at a time: load -> generate -> validate -> apply.
            with config_write_lock:
                system_hosts = _load_monitored_hosts()
                update_ncpa_deployment_status(
                    ncpa_deployment_status_id,
                    DeploymentStatus.RUNNING,
                    ADD_NCPA_PORT_PROGRESS_WEIGHT[1],
                    "Loaded monitored hosts from database."
                )

                if stop_event.is_set():
                    update_ncpa_deployment_status(
                        ncpa_deployment_status_id,
                        DeploymentStatus.INTERRUPTED,
                        ADD_NCPA_PORT_PROGRESS_WEIGHT[1],
                        "Adding NCPA port was stopped by user."
                    )
                    return

                # Generate a new Nagios host config file from the updated hosts
                new_cfg = _create_host_cfg_file(system_hosts)
                print(f"Created: {new_cfg}")
                update_ncpa_deployment_status(
                    ncpa_deployment_status_id,
                    DeploymentStatus.RUNNING,
                    ADD_NCPA_PORT_PROGRESS_WEIGHT[2],
                    "Generated new Nagios configuration."
                )

                if stop_event.is_set():
                    update_ncpa_deployment_status(
                        ncpa_deployment_status_id,
                        DeploymentStatus.INTERRUPTED,
                        ADD_NCPA_PORT_PROGRESS_WEIGHT[2],
                        "Adding NCPA port was stopped by user."
                    )
                    return

                # Validate the candidate config against the live nagios.cfg
                # before touching anything live
                is_valid, result = _validate_config(new_cfg)
                update_ncpa_deployment_status(
                    ncpa_deployment_status_id,
                    DeploymentStatus.RUNNING,
                    ADD_NCPA_PORT_PROGRESS_WEIGHT[3],
                    "Validated new Nagios configuration."
                )

                if stop_event.is_set():
                    update_ncpa_deployment_status(
                        ncpa_deployment_status_id,
                        DeploymentStatus.INTERRUPTED,
                        ADD_NCPA_PORT_PROGRESS_WEIGHT[3],
                        "Adding NCPA port was stopped by user."
                    )
                    return

                # If valid, apply it as the new live config: backs up the running
                # hosts.cfg, copies the new one into place, reloads Nagios, and
                # rolls back automatically if the reload fails
                if is_valid:
                    applied, apply_message = _apply_new_host_cfg(new_cfg)

                    if applied:
                        update_ncpa_deployment_status(
                            ncpa_deployment_status_id,
                            DeploymentStatus.SUCCESS,
                            ADD_NCPA_PORT_PROGRESS_WEIGHT[4],
                            "New host.cfg successfully applied.",
                            datetime.now(timezone.utc)
                        )
                    else:
                        update_ncpa_deployment_status(
                            ncpa_deployment_status_id,
                            DeploymentStatus.FAILED,
                            ADD_NCPA_PORT_PROGRESS_WEIGHT[4],
                            "Config not applied.",
                            datetime.now(timezone.utc),
                            apply_message
                        )
                    print(apply_message)
                else:
                    update_ncpa_deployment_status(
                        ncpa_deployment_status_id,
                        DeploymentStatus.FAILED,
                        ADD_NCPA_PORT_PROGRESS_WEIGHT[4],
                        "Config failed to validate.",
                        datetime.now(timezone.utc),
                        result
                    )
                    print(result)

        except Exception as e:
            db.session.rollback()
            app.logger.exception("Failed to add NCPA port")
            update_ncpa_deployment_status(
                ncpa_deployment_status_id,
                DeploymentStatus.FAILED,
                100,
                "Failed to add NCPA port.",
                datetime.now(timezone.utc),
                str(e)
            )

def regenerate_and_apply_config():
    """
    Rebuild hosts.cfg from the database and, if it really changed, validate
    and apply it. The single entry point for everything that is not a full
    scan: NCPA relocation and user edits (merge, retire, port changes).

    Runs under config_write_lock so it cannot interleave with discovery or
    add_ncpa_port(). Returns (changed, message): changed is True only when a
    new config was applied; when nothing changed or the config could not be
    applied the message says why. Does not touch the database session beyond
    reading.
    """
    with config_write_lock:
        new_cfg = _create_host_cfg_file(_load_monitored_hosts())

        if config_unchanged(new_cfg):
            new_cfg.unlink(missing_ok=True)
            return False, "Host configuration unchanged; Nagios was not reloaded."

        is_valid, result = _validate_config(new_cfg)
        if not is_valid:
            return False, f"Config failed to validate: {result}"

        applied, message = _apply_new_host_cfg(new_cfg)
        return applied, message
