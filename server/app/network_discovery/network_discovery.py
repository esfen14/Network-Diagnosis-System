import nmap3
import xml.etree.ElementTree as ET

# this needs to be part of the settings
NETWORKS = ["localhost","192.168.130.0/24","10.10.99.0/24"]
TCP_PORTS = ["1-6000"]
UDP_PORTS = [53,67,68,69,123,161,162,514]

def _print_xml(xml):
    # print the XML file from the NMAP scan
    xml_result = ET.dump(xml)
    print(xml_result)


def _discover_host(subnet):
    nmap = nmap3.Nmap()

    xmlroot = nmap.scan_command(subnet,"-PS -PA -PE -sn -R")

    host_dict = {}

    scanned_host = xmlroot.findall("host")

    # for debugging Nmap scans
    _print_xml(xmlroot)

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
    _print_xml(xmlroot)    

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

def discover_network():
    hosts = {}

    for network in NETWORKS:
        hosts[network] = _discover_host(network)

        for ip in hosts[network]:
            hosts[network][ip]["services"]["tcp"], hosts[network][ip]["data"]["os"]= _discover_host_tcp_port(ip)

            hosts[network][ip]["services"]["udp"] = _discover_host_udp_port(ip)

    return hosts

result = discover_network()
print(result)