"""
tests/unit/test_service_identification.py — Deciding which service a port runs.

A port number is a hint, not proof. nmap's <service> element says whether it
probed the service (method="probed") or only looked the port up in its table
(method="table"); only a probed, named service is a FINGERPRINT. Discovery
then applies the port rules: an "always treat port as" rule (PORT_RULE) wins,
a fallback name only replaces a PORT_HINT. The port lifecycle never
auto-monitors a guess, never renames a port an operator pinned (USER), and
raises a SERVICE_CHANGED review item instead of renaming a monitored port.
"""
import xml.etree.ElementTree as ET
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from app import db
from app.network_discovery.create_host_cfg import _apply_service_rules, apply_service_rules
from app.network_discovery.network_discovery import _parse_udp_ports, service_from_nmap
from app.network_discovery.port_lifecycle import pin_port_service, process_device_ports
from app.system_models import (
    DeviceReviewItem,
    NCPADeployment,
    Open_TCP_Services,
    PortSource,
    PortState,
    ReviewKind,
    ServiceIdentification,
)
from tests.support.identity_helpers import MAC_1, NET, make_status, run_scan, scan

FINGERPRINT = ServiceIdentification.FINGERPRINT.name
PORT_HINT = ServiceIdentification.PORT_HINT.name
PORT_RULE = ServiceIdentification.PORT_RULE.name


def service(**attrs):
    return ET.fromstring("<service " + " ".join(f'{k}="{v}"' for k, v in attrs.items()) + "/>")


# ==========================================================
# NMAP EVIDENCE
# ==========================================================

class TestServiceFromNmap:

    def test_probed_service_is_a_fingerprint(self):
        assert service_from_nmap(service(name="ssh", method="probed", conf="10")) == {
            "service_name": "ssh", "identified_by": FINGERPRINT}

    def test_table_lookup_is_only_a_hint(self):
        assert service_from_nmap(service(name="http-alt", method="table", conf="3")) == {
            "service_name": "http-alt", "identified_by": PORT_HINT}

    def test_http_inside_tls_is_https(self):
        result = service_from_nmap(service(name="http", tunnel="ssl", method="probed"))
        assert result == {"service_name": "https", "identified_by": FINGERPRINT}

    @pytest.mark.parametrize("name", ["tcpwrapped", "unknown"])
    def test_unidentified_answers_are_hints(self, name):
        assert service_from_nmap(service(name=name, method="probed"))["identified_by"] == PORT_HINT

    def test_no_service_element(self):
        assert service_from_nmap(None) == {"service_name": "unknown", "identified_by": PORT_HINT}

    def test_names_are_lowercased(self):
        assert service_from_nmap(service(name="SSH", method="probed"))["service_name"] == "ssh"

    def test_udp_ports_carry_their_identification(self):
        xml = ET.fromstring("""<nmaprun><host><ports>
        <port protocol="udp" portid="161"><state state="open"/><service name="snmp" method="probed"/></port>
        <port protocol="udp" portid="1900"><state state="open"/><service name="upnp" method="table"/></port>
        </ports></host></nmaprun>""")
        confirmed, _ = _parse_udp_ports(xml)
        assert confirmed["161"]["identified_by"] == FINGERPRINT
        assert confirmed["1900"]["identified_by"] == PORT_HINT


# ==========================================================
# PORT RULES
# ==========================================================

class TestPortRules:

    def test_forced_rule_beats_a_fingerprint(self):
        data = apply_service_rules({"service_name": "https", "identified_by": FINGERPRINT},
                                   "5693", {"5693": "ncpa"}, {})
        assert data == {"service_name": "ncpa", "identified_by": PORT_RULE}

    def test_fallback_does_not_override_a_fingerprint(self):
        # SSH really is on 80 here; the conventional "80 is http" must not win.
        data = apply_service_rules({"service_name": "ssh", "identified_by": FINGERPRINT},
                                   "80", {}, {"80": "http"})
        assert data == {"service_name": "ssh", "identified_by": FINGERPRINT}

    def test_fallback_replaces_a_guess(self):
        data = apply_service_rules({"service_name": "tcpwrapped", "identified_by": PORT_HINT},
                                   "22", {}, {"22": "ssh"})
        assert data == {"service_name": "ssh", "identified_by": PORT_HINT}

    def test_missing_identification_is_treated_as_a_guess(self):
        data = apply_service_rules({"service_name": "http-alt"}, "8080", {}, {"8080": "http"})
        assert data == {"service_name": "http", "identified_by": PORT_HINT}

    def test_non_standard_port_keeps_its_fingerprint(self):
        data = apply_service_rules({"service_name": "ssh", "identified_by": FINGERPRINT},
                                   "2222", {}, {"22": "ssh"})
        assert data == {"service_name": "ssh", "identified_by": FINGERPRINT}

    def test_scan_step_applies_rules_to_every_host(self, app):
        hosts = {NET: {
            "10.0.0.5": {"data": {}, "services": {"tcp": {
                "5693": {"service_name": "https", "identified_by": FINGERPRINT},
                "8080": {"service_name": "http-proxy", "identified_by": PORT_HINT},
            }, "udp": {}}},
        }}
        with app.app_context(), patch("app.network_discovery.create_host_cfg.update_network_discovery_status"):
            _apply_service_rules(1, hosts, "tcp", {"5693": "ncpa"}, {"8080": "http"}, 60)

        tcp = hosts[NET]["10.0.0.5"]["services"]["tcp"]
        assert tcp["5693"] == {"service_name": "ncpa", "identified_by": PORT_RULE}
        assert tcp["8080"] == {"service_name": "http", "identified_by": PORT_HINT}

    def test_config_forces_the_ncpa_port(self, app):
        assert app.config["TCP_FORCED_SERVICES"] == {app.config["NCPA_PORT"]: "ncpa"}
        assert "5693" not in app.config["TCP_SERVICE_OVERRIDES"]


# ==========================================================
# PORT LIFECYCLE
# ==========================================================

@pytest.fixture
def device(db_session, admin_user):
    """A Linux device already saved by a scan with no ports."""
    status = make_status(db_session, admin_user)
    return run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1))[(NET, "10.0.0.5")]


def scan_port(device, port, name, identified_by, protocol="tcp"):
    services = {"tcp": {}, "udp": {}}
    services[protocol][str(port)] = {"service_name": name, "identified_by": identified_by}
    process_device_ports(device, services, host_seen=True)
    db.session.commit()


def tcp_port(device, number):
    return db.session.scalar(sa.select(Open_TCP_Services).where(
        Open_TCP_Services.NetDiscoveryID == device.NetDiscoveryID,
        Open_TCP_Services.Port_Number == number))


def review_items():
    return db.session.scalars(
        sa.select(DeviceReviewItem).where(DeviceReviewItem.Kind == ReviewKind.SERVICE_CHANGED)
    ).all()


class TestLifecycleIdentification:

    def test_fingerprinted_auto_service_is_monitored(self, device):
        scan_port(device, 2222, "ssh", FINGERPRINT)
        port = tcp_port(device, 2222)
        assert port.Port_State is PortState.MONITORED
        assert port.Plugin_Name == "ssh"
        assert port.Identified_By is ServiceIdentification.FINGERPRINT

    def test_a_guess_is_only_suggested(self, device):
        scan_port(device, 22, "ssh", PORT_HINT)
        port = tcp_port(device, 22)
        assert port.Port_State is PortState.SUGGESTED
        assert port.Identified_By is ServiceIdentification.PORT_HINT

    def test_ruled_service_is_monitored(self, device):
        scan_port(device, 5693, "ncpa", PORT_RULE)
        assert tcp_port(device, 5693).Port_State is PortState.MONITORED

    def test_a_guess_confirmed_later_starts_monitoring(self, device):
        scan_port(device, 22, "ssh", PORT_HINT)
        scan_port(device, 22, "ssh", FINGERPRINT)
        port = tcp_port(device, 22)
        assert port.Port_State is PortState.MONITORED
        assert port.Identified_By is ServiceIdentification.FINGERPRINT

    def test_a_user_suggestion_is_not_promoted_again(self, device):
        scan_port(device, 22, "ssh", FINGERPRINT)
        port = tcp_port(device, 22)
        port.Port_State = PortState.SUGGESTED
        db.session.commit()

        scan_port(device, 22, "ssh", FINGERPRINT)
        assert tcp_port(device, 22).Port_State is PortState.SUGGESTED

    def test_pinned_port_is_never_renamed(self, device):
        scan_port(device, 8080, "http-proxy", PORT_HINT)
        pin_port_service(device.NetDiscoveryID, "tcp", 8080, "http")
        db.session.commit()

        scan_port(device, 8080, "squid-http", FINGERPRINT)
        port = tcp_port(device, 8080)
        assert port.Service_Name == "http"
        assert port.Identified_By is ServiceIdentification.USER
        assert port.Observed_Service_Name == "squid-http"
        assert review_items() == []

    def test_pinning_a_monitored_port_refreezes_its_plugin(self, device):
        scan_port(device, 8080, "http", FINGERPRINT)
        assert tcp_port(device, 8080).Plugin_Name == "http"

        pin_port_service(device.NetDiscoveryID, "tcp", 8080, "ncpa")
        db.session.commit()
        assert tcp_port(device, 8080).Plugin_Name == "ncpa"

    def test_pinning_a_missing_port_returns_none(self, device):
        assert pin_port_service(device.NetDiscoveryID, "tcp", 9999, "http") is None


class TestServiceChangedReview:

    def test_fingerprint_change_raises_one_review_and_keeps_the_service(self, device):
        scan_port(device, 8080, "http", FINGERPRINT)
        scan_port(device, 8080, "ssh", FINGERPRINT)
        scan_port(device, 8080, "ssh", FINGERPRINT)

        port = tcp_port(device, 8080)
        assert (port.Service_Name, port.Plugin_Name) == ("http", "http")
        (item,) = review_items()
        assert item.Candidate_Device_IDs == [device.NetDiscoveryID]
        assert item.IP_Address == "10.0.0.5"
        assert "tcp/8080" in item.Message and "monitored as http" in item.Message and "ssh" in item.Message

    def test_a_changed_guess_raises_nothing(self, device):
        scan_port(device, 8080, "http", FINGERPRINT)
        scan_port(device, 8080, "http-proxy", PORT_HINT)
        assert review_items() == []

    def test_same_plugin_under_another_name_raises_nothing(self, device):
        scan_port(device, 53, "dns", FINGERPRINT)
        scan_port(device, 53, "domain", FINGERPRINT)
        assert review_items() == []

    def test_deployed_ncpa_port_raises_nothing(self, device):
        scan_port(device, 5693, "ncpa", PORT_RULE)
        port = tcp_port(device, 5693)
        port.Source = PortSource.NCPA
        deployment = db.session.scalar(sa.select(NCPADeployment).where(
            NCPADeployment.NetworkDiscoveryID == device.NetDiscoveryID))
        deployment.Token = "tok"
        db.session.commit()

        # An administrator removed the forced rule, so nmap's https comes through.
        scan_port(device, 5693, "https", FINGERPRINT)
        assert review_items() == []
