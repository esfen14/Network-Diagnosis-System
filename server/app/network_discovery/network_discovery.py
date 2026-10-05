import nmap3
import xml.etree.ElementTree as ET
from flask import current_app
from app.logging import update_network_discovery_status, calculate_progress
from app.system_models import DiscoveryStatus, ServiceIdentification
from app.network_discovery.discovery_settings import get_discovery_setting

# NETWORKS, TCP_PORTS, UDP_PORTS default to server/config.py's Config
# class but can be edited from the Settings page (DiscoverySettings row).
# Each function that needs one reads the effective value through
# get_discovery_setting() into a same-named local at the top.

# nmap names that mean "something answered but nmap does not know what".
UNIDENTIFIED_SERVICE_NAMES = frozenset({"unknown", "tcpwrapped"})

# Seconds one host may spend on UDP version detection (step 2 of the UDP scan).
UDP_VERSION_HOST_TIMEOUT = "90s"


def service_from_nmap(service):
    """
    Turn one nmap <service> element into {"service_name", "identified_by"}.

    nmap reports method="probed" when a protocol probe matched (an SSH banner,
    an HTTP reply...) and method="table" when it only looked the port number
    up in nmap-services, so only a probed, named service counts as a
    FINGERPRINT; everything else is a PORT_HINT that discovery may replace
    with a configured fallback name. HTTP inside a TLS tunnel is reported as
    "https" so it gets a TLS check.
    """
    if service is None:
        return {"service_name": "unknown", "identified_by": ServiceIdentification.PORT_HINT.name}

    name = (service.attrib.get("name") or "unknown").strip().lower()
    if service.attrib.get("tunnel") == "ssl" and name == "http":
        name = "https"

    identified_by = ServiceIdentification.PORT_HINT
    if name in UNIDENTIFIED_SERVICE_NAMES:
        # "tcpwrapped" means the port accepted and closed; nothing named it.
        name = "unknown"
    elif service.attrib.get("method") == "probed":
        identified_by = ServiceIdentification.FINGERPRINT

    return {"service_name": name, "identified_by": identified_by.name}


def _print_xml(xml):
    # print the XML file from the NMAP scan
    xml_result = ET.dump(xml)
    print(xml_result)


def _discover_host(subnet):
    nmap = nmap3.Nmap(path="/usr/local/bin/nmap-sudo")

    xmlroot = nmap.scan_command(subnet,"-PS -PA -PE -sn -R", "--open")

    host_dict = {}

    scanned_host = xmlroot.findall("host")

    # for debugging Nmap scans
    # _print_xml(xmlroot)

    
    for host in scanned_host:

        ipv4 = None
        mac_address = None
        hostnames = "Unknown"

        status = host.find("status")
        state = status.get("state") if status is not None else "down"

        if state != "up":
            continue
        
        for address in host.findall("address"):

            if address.attrib.get("addrtype") == "ipv4":
                ipv4 = address.attrib["addr"]

            elif address.attrib.get("addrtype") == "mac":
                mac_address = address.attrib["addr"]
                
        hostnames = host.find("hostnames")
        hostname = "Unknown"

        if hostnames is not None:
            hostname_element = hostnames.find("hostname")
        
            if hostname_element is not None:
                hostname = hostname_element.get("name", "Unknown")

        if ipv4 is None:
            continue
        
        host_dict[ipv4] = {
            "data":{
                "hostname": hostname,
                "mac_address":mac_address,
                "os": "Unknown",
            },
            "services":{}
        }
           
    return host_dict

def _discover_host_tcp_port(ip):
    TCP_PORTS = get_discovery_setting('TCP_PORTS')
    nmap = nmap3.Nmap(path="/usr/local/bin/nmap-sudo")

    args = "--open"

    if TCP_PORTS:
        port_string = ",".join(str(port) for port in TCP_PORTS)
        args += f" -p {port_string}"
    
    xmlroot = nmap.scan_command(ip,"-sV -O --version-all",args)

    # for debugging nmap scans
    # _print_xml(xmlroot)    

    service_dict = {}
    os_name = "Unknown"

    host = xmlroot.find("host")

    if host is None:
        return service_dict, os_name

    # Get OS name
    os_element = host.find("os")

    if os_element is not None:
        os_class = os_element.find("osmatch/osclass")

        if os_class is not None:
            os_name = os_class.get("osfamily", "Unknown")

    ports = host.find("ports")

    if ports is None:
        return service_dict, os_name

    # Try to find all the TCP servcies of a certain IP
    for port in ports.findall("port"):
        portid = str(port.attrib.get("portid"))

        state = port.find("state")
        if state is not None and state.attrib.get("state") == "open":
            service_dict[portid] = service_from_nmap(port.find("service"))

    return service_dict, os_name

def _discover_host_udp_port(ip):
    UDP_PORTS = get_discovery_setting('UDP_PORTS')
    nmap = nmap3.Nmap(path="/usr/local/bin/nmap-sudo")

    args = "--open"

    if UDP_PORTS:
        port_string = ",".join(str(port) for port in UDP_PORTS)
        args += f" -p {port_string}"

    # Step 1: find which ports answer. Without -sV this takes seconds, but a
    # port's name is only a guess from its number.
    xmlroot = nmap.scan_command(ip,"-sU",args)

    # for debugging nmap scans
    # _print_xml(xml_result)

    confirmed, unconfirmed = _parse_udp_ports(xmlroot)
    if not confirmed:
        return confirmed, unconfirmed

    # Step 2: -sV sends each port's protocol probe, so a matched UDP service
    # is a fingerprint rather than a guess. Only the ports that answered are
    # probed; version detection on every listed port is what made it slow.
    open_ports = []
    for portid in confirmed:
        open_ports.append(str(portid))

    try:
        version_xml = nmap.scan_command(
            ip,
            "-sU -sV",
            f"--open -p {','.join(open_ports)} --host-timeout {UDP_VERSION_HOST_TIMEOUT}",
        )
    except Exception:
        current_app.logger.warning(
            f"UDP version detection failed for {ip}; keeping the port-number names.", exc_info=True
        )
        return confirmed, unconfirmed

    versioned, _ = _parse_udp_ports(version_xml)
    for portid, service_data in versioned.items():
        if portid in confirmed:
            confirmed[portid] = service_data

    return confirmed, unconfirmed


def _parse_udp_ports(xmlroot):
    """
    Split nmap's UDP result into (confirmed, unconfirmed)
    {port: {"service_name", "identified_by"}}.

    "open" ports answered a probe. "open|filtered" ports ignored it, so nmap
    cannot tell them from a firewalled port; they are not stored as services
    but are reported so the discovery log can show them as skipped.
    """
    confirmed, unconfirmed = {}, {}

    host = xmlroot.find("host")
    if host is None:
        return confirmed, unconfirmed

    ports = host.find("ports")
    if ports is None:
        return confirmed, unconfirmed

    for port in ports.findall("port"):
        portid = str(port.attrib.get("portid"))

        state = port.find("state")
        state_name = state.attrib.get("state") if state is not None else None
        if state_name not in ("open", "open|filtered"):
            continue

        target = confirmed if state_name == "open" else unconfirmed
        target[portid] = service_from_nmap(port.find("service"))

    return confirmed, unconfirmed

def discover_network(network_discvovery_status_id, progress_weight, stop_event):
    NETWORKS = get_discovery_setting('NETWORKS')
    hosts = {}

    total_networks = len(NETWORKS)

    if total_networks == 0:
        return hosts

    for network_index, network in enumerate(NETWORKS):

        if stop_event.is_set():
            return None
        
        hosts[network] = _discover_host(network)

        total_hosts = len(hosts[network])

        # Portion of the overall 0-50% range belonging to this subnet
        subnet_start = (network_index / total_networks) * progress_weight
        subnet_end = ((network_index + 1) / total_networks) * progress_weight

        for host_index, ip in enumerate(hosts[network]):

            if stop_event.is_set():
                return None
            
            hosts[network][ip]["services"]["tcp"], hosts[network][ip]["data"]["os"]= _discover_host_tcp_port(ip)

            if stop_event.is_set():
                return None
            
            hosts[network][ip]["services"]["udp"], hosts[network][ip]["data"]["udp_unconfirmed"] =                 _discover_host_udp_port(ip)


            if total_hosts > 0:
                progress = calculate_progress(host_index + 1, 
                                            total_hosts, 
                                            subnet_start, 
                                            subnet_end
                                            )
            else:
                progress = subnet_end
            
            update_network_discovery_status(
                    network_discvovery_status_id,
                    DiscoveryStatus.RUNNING,
                    int(progress),
                    "Discovering hosts."
            )
    return hosts
