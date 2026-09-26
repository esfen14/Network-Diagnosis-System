from pathlib import Path
from datetime import datetime, timezone
import subprocess
import shutil

from app.network_discovery.network_discovery import discover_network
from app.network_discovery.host_config_templates import *
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
    AgentStatus 
from app.logging import create_network_discovery_status, update_network_discovery_status, calculate_progress, create_skipped_service_logs
from app.logging.deployment_history import update_ncpa_deployment_status
from app.system_models import DiscoveryStatus, DeploymentStatus
import socket
import ipaddress
import tempfile

# Network discovery / host-config settings (TCP_SERVICE_OVERRIDES,
# UDP_SERVICE_OVERRIDES, DOMAIN, NCPA_PORT, HOST_CONFIG_DIR, BACKUP_DIR)
# and the advanced Nagios settings (NAGIOS_HOST_CFG, NAGIOS_BIN,
# NAGIOS_MAIN_CFG) now live in server/config.py's Config class. Each
# function below that needs one reads it from current_app.config into a
# same-named local at the top of the function, so the settings are
# centralized without a Settings UI needing to touch call sites here.

PROGRESS_WEIGHT = [40,50,55,60,70,80,90,95,100]

# Progress stages for add_ncpa_port: adding the port to the db, reloading
# hosts, generating the config, validating, and applying it. Imported
# directly by app/ncpa_deployment/ncpa_deployment.py, so this must stay
# a real module-level constant (not a config-backed local alias).
ADD_NCPA_PORT_PROGRESS_WEIGHT = [40, 55, 70, 85, 100]

def _add_space(spaces):
    return "\n" * spaces


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

    Returns a list of dicts with base_name ("<label>[-<metric>]-<port>"),
    transport, check_command and plugin. Raises PluginConfigurationError if
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
    Turn planned services into (service_name, check_command, plugin) tuples
    whose names are unique on the host. A "-TCP"/"-UDP" suffix is added only
    when the same base name exists on both transports (e.g. DNS on 53/TCP
    and 53/UDP); any remaining duplicate gets a numeric suffix.
    """
    transports_by_name = {}
    for service in planned:
        transports_by_name.setdefault(service["base_name"], set()).add(service["transport"])

    services = []
    used_names = set()
    for service in planned:
        name = service["base_name"]
        if len(transports_by_name[name]) > 1:
            name = f"{name}-{service['transport'].value}"

        unique_name = name
        counter = 2
        while unique_name in used_names:
            unique_name = f"{name}-{counter}"
            counter += 1

        used_names.add(unique_name)
        services.append((unique_name, service["check_command"], service["plugin"]))
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
            plugin_name = resolve_plugin_name(discovered_name, transport)
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

    for hosts in discovered_hosts.values():
        for ip, host_data in hosts.items():
            host = {}
            host["host_name"] = host_data["data"]["hostname"]
            host["alias"] = "alias"
            host["address"] = ip
            host["contact_groups"] = "system_users"
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

            for service_name, command, plugin_name in host_services:
                # Remember the plugin so its `define command` is written once
                # in the "Define Commands" section at the end of the file.
                used_plugins.add(plugin_name)

                service = {
                    "host_name": host_data["data"]["hostname"],
                    "service_name": service_name,
                    "contact_groups": "system_users"
                }

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
    total_hosts = sum(len(hosts) for hosts in discovered_hosts.values())
    processed_hosts = 0

    monitoring_server_ips = get_monitoring_server_ips()

    try:
        for network, hosts in discovered_hosts.items():
            
            for ip_address, host_data in hosts.items():

                if ip_address in monitoring_server_ips:
                    continue

                data = host_data["data"]
                services = host_data.get("services", {})

                hostname = data.get("hostname")
                mac_address = data.get("mac_address")
                os_type = data.get("os")

                if mac_address is not None:
                    device = db.session.scalar(
                            sa.select(NetworkDiscovery).where(
                                NetworkDiscovery.MAC_Address == mac_address,
                                NetworkDiscovery.Network == network
                        )
                    )
                else:
                    device = db.session.scalar(
                        sa.select(NetworkDiscovery).where(
                            NetworkDiscovery.IP_Address == ip_address,
                            NetworkDiscovery.Network == network
                        )
                    )

                NCPA_Eligible = False

                if os_type == "Linux":
                    NCPA_Eligible = True

                    

                # -------------------------------------------------
                # Create device if it doesn't exist
                # -------------------------------------------------

                if device is None:
                    device = NetworkDiscovery(
                        Hostname = hostname,
                        IP_Address = ip_address,
                        Network = network,
                        MAC_Address = mac_address,
                        OS_Type = os_type,
                        NCPA_Eligible = NCPA_Eligible,
                        DiscoveryStatusID = network_discovery_id
                    )

                    db.session.add(device)
                    db.session.flush()

                    if device.NCPA_Eligible == True:
                        ssh = SSHCredentials(
                            SSH_Port = int(port_number) ,
                            Key_Installed = False,
                            Key_Fingerprint = None,
                            Created_At = None,
                            NetworkDiscoveryID = device.NetDiscoveryID
                        )
                                                                    
                        db.session.add(ssh)
                                                                    
                        ncpa = NCPADeployment(
                            Agent_Status = AgentStatus.PENDING_NCPA,
                            NetworkDiscoveryID = device.NetDiscoveryID
                        )
                                                                    
                        db.session.add(ncpa)
                        db.session.flush()

                else:
                    NCPA_Eligible = False

                    device.Hostname = hostname
                    device.MAC_Address = mac_address
                    device.OS_Type = os_type
                    device.NCPA_Eligible = NCPA_Eligible
                    device.DiscoveryStatusID = network_discovery_id

                # -------------------------------------------------
                # TCP services — add/update found ports, then
                # remove any DB-stored port not seen in this scan
                # -------------------------------------------------

                scanned_tcp_ports = set()

                for port_number, service_data in services.get("tcp", {}).items():
                    # Model column is an int; scan data comes in as a string —
                    # normalize here so comparisons/deletes below match correctly
                    port_number_int = int(port_number)
                    scanned_tcp_ports.add(port_number_int)

                    existing_service = db.session.scalar(
                        sa.select(Open_TCP_Services).join(
                            NetworkDiscovery,
                            Open_TCP_Services.NetDiscoveryID == NetworkDiscovery.NetDiscoveryID
                        )
                        .where(
                            Open_TCP_Services.NetDiscoveryID == device.NetDiscoveryID,
                            Open_TCP_Services.Port_Number == port_number_int,
                            NetworkDiscovery.Include_Device_In_Scanning.is_(True)
                        )
                    )

                    service_name = service_data.get("service_name", "Unknown")

                    if existing_service is None:

                        new_service = Open_TCP_Services(
                            Port_Number=port_number_int,
                            Service_Name=service_name,
                            NetDiscoveryID=device.NetDiscoveryID
                        )
                        db.session.add(new_service)
                        db.session.flush()
                    else:
                        # Service still open — keep its name in sync in case
                        # nmap's guess changed between scans (e.g. Unknown -> ssh)
                        existing_service.Service_Name = service_name

                # Remove TCP services that were recorded before but weren't
                # seen in this scan — they're no longer open on this host
                stale_tcp_query = sa.select(Open_TCP_Services).where(
                    Open_TCP_Services.NetDiscoveryID == device.NetDiscoveryID
                )
                if scanned_tcp_ports:
                    stale_tcp_query = stale_tcp_query.where(
                        Open_TCP_Services.Port_Number.not_in(scanned_tcp_ports)
                    )

                stale_tcp_services = db.session.scalars(stale_tcp_query).all()
                for stale_service in stale_tcp_services:
                    db.session.delete(stale_service)

                # -------------------------------------------------
                # UDP services — same add/update/remove pattern
                # -------------------------------------------------

                scanned_udp_ports = set()

                for port_number, service_data in services.get("udp", {}).items():
                    port_number_int = int(port_number)
                    scanned_udp_ports.add(port_number_int)

                    existing_service = db.session.scalar(
                        sa.select(Open_UDP_Services).join(
                            NetworkDiscovery,
                            Open_UDP_Services.NetDiscoveryID == NetworkDiscovery.NetDiscoveryID
                        )
                        .where(
                            Open_UDP_Services.NetDiscoveryID == device.NetDiscoveryID,
                            Open_UDP_Services.Port_Number == port_number_int,
                            NetworkDiscovery.Include_Device_In_Scanning.is_(True)
                        )
                    )

                    service_name = service_data.get("service_name", "Unknown")

                    if existing_service is None:
                        new_service = Open_UDP_Services(
                            Port_Number=port_number_int,
                            Service_Name=service_name,
                            NetDiscoveryID=device.NetDiscoveryID
                        )
                        db.session.add(new_service)
                        db.session.flush()
                    else:
                        existing_service.Service_Name = service_name

                stale_udp_query = sa.select(Open_UDP_Services).where(
                    Open_UDP_Services.NetDiscoveryID == device.NetDiscoveryID
                )
                if scanned_udp_ports:
                    stale_udp_query = stale_udp_query.where(
                        Open_UDP_Services.Port_Number.not_in(scanned_udp_ports)
                    )

                stale_udp_services = db.session.scalars(stale_udp_query).all()
                for stale_service in stale_udp_services:
                    db.session.delete(stale_service)

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
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(f"Failed to insert new hosts: {e}")

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

    shutil.copy2(NAGIOS_HOST_CFG, backup_path)

    return backup_path

def _load_monitored_hosts(network_discovery_id=None, progress_weight=None):
    """
    Rebuilds a discovered_hosts dict from the database, in the same
    shape as discover_network()'s output:

        {
            network: {
                ip_address: {
                    "data": {"hostname": ..., "mac_address": ..., "os": ...,
                             "net_discovery_id": ..., "plugin_variables": {...} | None},
                    "services": {"tcp": {port: {"service_name": ...}}, "udp": {...}}
                }
            }
        }

    Returns:
        dict: discovered_hosts-shaped dict sourced from the DB.
    """
    discovered_hosts = {}

    devices = db.session.scalars(
        sa.select(NetworkDiscovery).where(NetworkDiscovery.Include_Device_In_Scanning.is_(True))
    ).all()

    if not devices:
        return discovered_hosts

    device_ids = [device.NetDiscoveryID for device in devices]

    # Fetch all services in two queries instead of one query per device (N+1)
    tcp_services = db.session.scalars(
        sa.select(Open_TCP_Services).where(
            Open_TCP_Services.NetDiscoveryID.in_(device_ids)
        )
    ).all()

    udp_services = db.session.scalars(
        sa.select(Open_UDP_Services).where(
            Open_UDP_Services.NetDiscoveryID.in_(device_ids)
        )
    ).all()

    # Group services by their owning device, keyed by port
    tcp_by_device = {}
    for service in tcp_services:
        tcp_by_device.setdefault(service.NetDiscoveryID, {})[str(service.Port_Number)] = {
            "service_name": service.Service_Name
        }

    udp_by_device = {}
    for service in udp_services:
        udp_by_device.setdefault(service.NetDiscoveryID, {})[str(service.Port_Number)] = {
            "service_name": service.Service_Name
        }

    total_hosts = len(devices)
    processed_hosts = 0

    for device in devices:
        discovered_hosts.setdefault(device.Network, {})

        discovered_hosts[device.Network][device.IP_Address] = {
            "data": {
                "hostname": device.Hostname,
                "mac_address": device.MAC_Address,
                "os": device.OS_Type,
                # Used by build_host_services() to look up this device's
                # plugin facts and per-host plugin variable overrides.
                "net_discovery_id": device.NetDiscoveryID,
                "plugin_variables": device.Plugin_Variables,
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
        shutil.copy2(cfg_path, NAGIOS_HOST_CFG)
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
            current_app.logger.error(result.stdout + result.stderr)

    except Exception as e:
        # Reload failed — roll back to the last known-good config so Nagios
        # never keeps running on a broken/half-applied file
        shutil.copy2(backup_path, NAGIOS_HOST_CFG)
        return False, (
            f"Failed to reload Nagios after applying new config. "
            f"Rolled back to backup at {backup_path}. Error: {e}"
        )

    return True, f"Applied {cfg_path} successfully. Backup stored at {backup_path}"

def _create_hostname(network_discovery_id, discovered_hosts, progress_weight):
    DOMAIN = current_app.config['DOMAIN']
    total_hosts = sum(len(hosts) for hosts in discovered_hosts.values())
    processed_hosts = 0

    for hosts in discovered_hosts.values():
        for ip, host_data in hosts.items():
            if host_data["data"]["hostname"] == "Unknown":
                host_data["data"]["hostname"] = f"{ip}.{DOMAIN}"

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
                    "Creating hostnames"
                )

    return discovered_hosts

def _override_service_names(network_discovery_id, discovered_hosts, protocol, service_overrides,progress_weight):
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
            f"No {protocol.upper()} services to override"
        )
        return discovered_hosts

    processed_services = 0

    for hosts in discovered_hosts.values():

        for host_data in hosts.values():

            services = host_data["services"].get(protocol, {})

            for port_id, service_data in services.items():

                service_name = service_data.get(
                    "service_name",
                    "Unknown"
                )

                # Override Nmap's service name if configured
                service_data["service_name"] = service_overrides.get(
                    port_id,
                    service_name
                )

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
                        f"Overriding {protocol} service names"
                    )

    return discovered_hosts   

def discover_network_create_hosts(app, user_id, stop_event):
    network_discovery_id = None
   
    with app.app_context():
        try:
            TCP_SERVICE_OVERRIDES = current_app.config['TCP_SERVICE_OVERRIDES']
            UDP_SERVICE_OVERRIDES = current_app.config['UDP_SERVICE_OVERRIDES']

            print("Created Log")
            network_discovery_id = create_network_discovery_status(user_id).DiscoveryStatusID

            if stop_event.is_set():
                return
            
            # Gets the network info
            print("Discovering Hosts")
            discovered_hosts = discover_network(network_discovery_id, PROGRESS_WEIGHT[0], stop_event)

            if discovered_hosts is None:
                update_network_discovery_status(
                    network_discovery_id,
                    DiscoveryStatus.INTERRUPTED,
                    100,
                    "Network discovery was stopped.",
                    datetime.now(timezone.utc)
                )
                return

            if stop_event.is_set():
                return
            
            # Creates hostnames for hosts that don't have names
            discovered_hosts = _create_hostname(network_discovery_id, discovered_hosts, PROGRESS_WEIGHT[1])

            if stop_event.is_set():
                return
            
            # Overrides services names due to NMAP not always being right
            discovered_hosts = _override_service_names(network_discovery_id, discovered_hosts,"tcp", TCP_SERVICE_OVERRIDES, PROGRESS_WEIGHT[2])
            discovered_hosts = _override_service_names(network_discovery_id, discovered_hosts,"udp", UDP_SERVICE_OVERRIDES, PROGRESS_WEIGHT[3])

            if stop_event.is_set():
                return
            
            # Save it to the database
            _save_discovered_hosts(discovered_hosts, network_discovery_id, PROGRESS_WEIGHT[4])

            if stop_event.is_set():
                return
            
            system_hosts = _load_monitored_hosts(network_discovery_id, PROGRESS_WEIGHT[5])

            if stop_event.is_set():
                return
            
            skipped_services = []
            new_cfg = _create_host_cfg_file(system_hosts, skipped_services)
            print(f"Created: {new_cfg}")
            create_skipped_service_logs(network_discovery_id, skipped_services)
            update_network_discovery_status(
                network_discovery_id,
                DiscoveryStatus.RUNNING,
                PROGRESS_WEIGHT[6],
                "Generated new Nagios configuration"
            )

            if stop_event.is_set():
                return
            
            update_network_discovery_status(
                network_discovery_id,
                DiscoveryStatus.RUNNING,
                PROGRESS_WEIGHT[7],
                "Validating config"
            )
            
            is_valid, result = _validate_config(new_cfg)

            if stop_event.is_set():
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

                existing_service = db.session.scalar(
                    sa.select(Open_TCP_Services)
                    .join(NetworkDiscovery, 
                          Open_TCP_Services.NetDiscoveryID == NetworkDiscovery.NetDiscoveryID)
                    .where(
                        Open_TCP_Services.NetDiscoveryID == device_id,
                        Open_TCP_Services.Port_Number == int(NCPA_PORT),
                        NetworkDiscovery.Include_Device_In_Scanning.is_(True)
                    )
                )

                if existing_service is None:
                    new_service = Open_TCP_Services(
                        Port_Number=int(NCPA_PORT),
                        Service_Name="ncpa",
                        NetDiscoveryID=device_id
                    )
                    db.session.add(new_service)

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