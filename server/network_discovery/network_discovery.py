import nmap3
import xml.etree.ElementTree as ET
import json
NETWORK = "192.168.130.0/24"


def discover_host(subnet):
    nmap = nmap3.Nmap()

    print("Discovering hosts...")

    xmlroot = nmap.scan_command(subnet,"-PS -PA -O","--open")

    host_dict = {}

    scanned_host = xmlroot.findall("host")
    xml_result = ET.dump(xmlroot)
    print(xml_result)
    for host in scanned_host:
        ipv4 = None
        mac_address = None
        addresses = host.findall("address")
        for address in addresses:
            if address.attrib.get("addrtype") == "ipv4":
                ipv4 = address.attrib["addr"]
            elif address.attrib.get("addrtype") == "mac":
                mac_address = address.attrib["addr"]
                
        state = host.find("status").get("state")

        if state == "up":
            host_dict[ipv4] = {}
            host_dict[ipv4]["mac_address"] = mac_address
            
    return host_dict

def discover_host_tcp_port(ip):
    nmap = nmap3.Nmap()

    print(f"Discovering {ip} tcp service...")

    xmlroot = nmap.scan_command(ip,"-sV","--open")

    host_dict = {}

    scanned_host = xmlroot.findall("host")
    xml_result = ET.dump(xmlroot)
    print(xml_result)
    # Try to find all the TCP servcies of a certain IP
            
    return host_dict

def discover_host_udp_port(ip):
    nmap = nmap3.Nmap()
    
    print("Discovering hosts...")
    
    xmlroot = nmap.scan_command(subnet,"-sU","--open")
    
    host_dict = {}
    
    scanned_host = xmlroot.findall("host")
    xml_result = ET.dump(xmlroot)
    print(xml_result)
    
    # you're going to find all the UDP services within a certain range
    # the user can specify the UDP ports that will be discovered
    for host in scanned_host:

        state = host.find("status").get("state")
    
        if state == "up":
            host_dict[ipv4] = {}
            host_dict[ipv4]["mac_address"] = mac_address
                
    return host_dict


subnet = NETWORK
result = discover_host(subnet)
print(result)