"""UDP ports nmap reports as open|filtered are recorded as skipped, not stored."""

import xml.etree.ElementTree as ET

from app.network_discovery.create_host_cfg import unconfirmed_udp_skips
from app.network_discovery.network_discovery import _parse_udp_ports

NMAP_XML = """<nmaprun><host><ports>
<port protocol="udp" portid="161"><state state="open"/><service name="snmp" method="probed" conf="10"/></port>
<port protocol="udp" portid="69"><state state="open|filtered"/><service name="tftp"/></port>
<port protocol="udp" portid="123"><state state="closed"/></port>
</ports></host></nmaprun>"""


def test_open_and_unconfirmed_ports_are_split():
    confirmed, unconfirmed = _parse_udp_ports(ET.fromstring(NMAP_XML))

    assert confirmed == {"161": {"service_name": "snmp", "identified_by": "FINGERPRINT"}}
    assert unconfirmed == {"69": {"service_name": "tftp", "identified_by": "PORT_HINT"}}


def test_no_host_yields_nothing():
    assert _parse_udp_ports(ET.fromstring("<nmaprun/>")) == ({}, {})


def test_unconfirmed_ports_become_skipped_entries():
    hosts = {"10.0.0.0/28": {"10.0.0.3": {
        "data": {"hostname": "target02", "udp_unconfirmed": {"69": {"service_name": "tftp"}}},
        "services": {"tcp": {}, "udp": {}},
    }}}

    (entry,) = unconfirmed_udp_skips(hosts)

    assert entry["hostname"] == "target02" and entry["ip_address"] == "10.0.0.3"
    assert entry["port"] == "69" and entry["protocol"] == "UDP"
    assert "unconfirmed" in entry["reason"]
