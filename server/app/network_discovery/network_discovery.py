import nmap3
import xml.etree.ElementTree as ET
from app.logging import update_network_discovery_status, calculate_progress
from app.system_models import DiscoveryStatus

# this needs to be part of the settings

# What networks will be scanned
# prevent the user from adding localhost (might also check that in the backend) to prevent errors
NETWORKS = ["192.168.130.0/24"]
# What tcp ports will be scanned
TCP_PORTS = ["1-6000"]
# what udp ports will be scanned
UDP_PORTS = [53,67,68,69,123,161,162,514]

def _print_xml(xml):
    # print the XML file from the NMAP scan
    xml_result = ET.dump(xml)
    print(xml_result)


def _discover_host(subnet):
    nmap = nmap3.Nmap(path="/usr/local/bin/nmap-sudo")

    xmlroot = nmap.scan_command(subnet,"-PS -PA -PE -sn -R")

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
            service = port.find("service")
            service_name = "Unknown"

            if service is not None:
                service_name = service.attrib.get("name")

            service_dict[portid] = {
                "service_name": service_name
            }

    
            # Remember to get the OS too, then output that too
    
    return service_dict, os_name

def _discover_host_udp_port(ip):
    nmap = nmap3.Nmap(path="/usr/local/bin/nmap-sudo")
    
    args = "--open"

    if UDP_PORTS:
        port_string = ",".join(str(port) for port in UDP_PORTS)
        args += f" -p {port_string}"
    
    xmlroot = nmap.scan_command(ip,"-sU",args)

    # for debugging nmap scans
    # _print_xml(xml_result)   
    
    service_dict = {}

    host = xmlroot.find("host")
    if host is None:
        return service_dict

    ports = host.find("ports")
    if ports is None:
        return service_dict   

    for port in ports.findall("port"):
        portid = str(port.attrib.get("portid")) 

        state = port.find("state")
        if state is not None and state.attrib.get("state") == "open":
            service = port.find("service")
            service_name = "Unknown"

            if service is not None:
                service_name = service.attrib.get("name")

            service_dict[portid] = {
                "service_name": service_name
            }

    return service_dict

def discover_network(network_discvovery_status_id, progress_weight, stop_event):
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
            
            hosts[network][ip]["services"]["udp"] = _discover_host_udp_port(ip)


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
