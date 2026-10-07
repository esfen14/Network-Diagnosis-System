"""
tests/unit/test_service_identification.py — Deciding which service a port runs.

A port number is a hint, not proof. nmap's <service> element says whether it
probed the service (method="probed") or only looked the port up in its table
(method="table"); only a probed, named service is a FINGERPRINT. Discovery
then applies the Port -> Service table, which says what an admin expects on a
port: it names a port nmap could not fingerprint (PORT_RULE), and a port nmap
fingerprinted as something else is flagged "not used as intended" instead of
being relabelled. The port lifecycle never auto-monitors a guess or a flagged
port, never renames a port an operator pinned (USER), and raises a
SERVICE_CHANGED review item instead of renaming a monitored port.
"""
import xml.etree.ElementTree as ET
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from app import db
from app.network_discovery.create_host_cfg import _apply_service_rules, apply_service_rules
from app.network_discovery.discovery_settings import get_port_services
from app.network_discovery.network_discovery import _parse_udp_ports, service_from_nmap
from app.network_discovery.port_lifecycle import (
    acknowledge_port_mismatch,
    pin_port_service,
    process_device_ports,
    promote_identified_ports,
)
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

# Ports are monitored only when their plugin is enabled in Plugin Manager.
pytestmark = pytest.mark.usefixtures("monitoring_plugins")

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

    @pytest.mark.parametrize("method", ["probed", "table"])
    def test_tcpwrapped_is_not_stored_as_a_service_name(self, method):
        assert service_from_nmap(service(name="tcpwrapped", method=method)) == {
            "service_name": "unknown", "identified_by": PORT_HINT}

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

    def test_the_ncpa_port_always_takes_the_table_service(self):
        data = apply_service_rules({"service_name": "https", "identified_by": FINGERPRINT},
                                   "5693", {"5693": "ncpa"}, {"5693"})
        assert data == {"service_name": "ncpa", "identified_by": PORT_RULE}

    def test_a_table_entry_names_a_port_nmap_only_guessed(self):
        data = apply_service_rules({"service_name": "tcpwrapped", "identified_by": PORT_HINT},
                                   "22", {"22": "ssh"})
        assert data == {"service_name": "ssh", "identified_by": PORT_RULE}

    def test_missing_identification_is_treated_as_a_guess(self):
        data = apply_service_rules({"service_name": "http-alt"}, "8080", {"8080": "http"})
        assert data == {"service_name": "http", "identified_by": PORT_RULE}

    def test_the_same_fingerprint_is_confirmed_by_the_table(self):
        data = apply_service_rules({"service_name": "ssh", "identified_by": FINGERPRINT},
                                   "22", {"22": "ssh"})
        assert data == {"service_name": "ssh", "identified_by": PORT_RULE}

    def test_an_alias_of_the_expected_service_is_not_a_mismatch(self):
        data = apply_service_rules({"service_name": "domain", "identified_by": FINGERPRINT},
                                   "53", {"53": "dns"})
        assert "expected_service" not in data

    def test_a_different_fingerprint_is_not_relabelled_but_flagged(self):
        # A web server really is on 22; the table's "22 is ssh" must not rename it.
        data = apply_service_rules({"service_name": "http", "identified_by": FINGERPRINT},
                                   "22", {"22": "ssh"})
        assert data == {"service_name": "http", "identified_by": FINGERPRINT, "expected_service": "ssh"}

    def test_a_port_without_an_entry_keeps_its_fingerprint(self):
        data = apply_service_rules({"service_name": "ssh", "identified_by": FINGERPRINT},
                                   "2222", {"22": "ssh"})
        assert data == {"service_name": "ssh", "identified_by": FINGERPRINT}

    def test_scan_step_applies_rules_to_every_host(self, app):
        hosts = {NET: {
            "10.0.0.5": {"data": {}, "services": {"tcp": {
                "5693": {"service_name": "https", "identified_by": FINGERPRINT},
                "8080": {"service_name": "http-proxy", "identified_by": PORT_HINT},
                "22": {"service_name": "http", "identified_by": FINGERPRINT},
            }, "udp": {}}},
        }}
        with app.app_context(), patch("app.network_discovery.create_host_cfg.update_network_discovery_status"):
            _apply_service_rules(1, hosts, "tcp", {"5693": "ncpa", "8080": "http", "22": "ssh"}, 60)

        tcp = hosts[NET]["10.0.0.5"]["services"]["tcp"]
        assert tcp["5693"] == {"service_name": "ncpa", "identified_by": PORT_RULE}
        assert tcp["8080"] == {"service_name": "http", "identified_by": PORT_RULE}
        assert tcp["22"] == {"service_name": "http", "identified_by": FINGERPRINT, "expected_service": "ssh"}

    def test_the_tcp_table_always_holds_the_ncpa_port(self, app):
        with app.app_context():
            assert get_port_services("tcp")[app.config["NCPA_PORT"]] == "ncpa"
            assert app.config["NCPA_PORT"] not in app.config["TCP_PORT_SERVICES"]
            assert app.config["NCPA_PORT"] not in get_port_services("udp")


# ==========================================================
# PORT LIFECYCLE
# ==========================================================

@pytest.fixture
def device(db_session, admin_user):
    """A Linux device already saved by a scan with no ports."""
    status = make_status(db_session, admin_user)
    return run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1))[(NET, "10.0.0.5")]


def scan_port(device, port, name, identified_by, protocol="tcp", expected_service=None):
    services = {"tcp": {}, "udp": {}}
    services[protocol][str(port)] = {"service_name": name, "identified_by": identified_by}
    if expected_service is not None:
        services[protocol][str(port)]["expected_service"] = expected_service
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

    def test_removed_port_rule_refreshes_the_label_but_not_the_name(self, device):
        scan_port(device, 8444, "http", PORT_RULE)
        port = tcp_port(device, 8444)
        plugin = port.Plugin_Name

        scan_port(device, 8444, "http", FINGERPRINT)
        port = tcp_port(device, 8444)
        assert port.Identified_By is ServiceIdentification.FINGERPRINT
        assert port.Service_Name == "http" and port.Plugin_Name == plugin
        assert review_items() == []

    def test_a_port_rule_that_still_applies_keeps_its_label(self, device):
        scan_port(device, 8444, "http", PORT_RULE)
        scan_port(device, 8444, "http", PORT_RULE)
        assert tcp_port(device, 8444).Identified_By is ServiceIdentification.PORT_RULE

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


class TestNotUsedAsIntended:
    """A fingerprint that contradicts the Port -> Service table waits for an admin."""

    def flagged(self, device):
        scan_port(device, 22, "http", FINGERPRINT, expected_service="ssh")
        return tcp_port(device, 22)

    def test_the_port_keeps_what_nmap_saw_and_is_not_monitored(self, device):
        port = self.flagged(device)
        assert port.Service_Name == "http"
        assert port.Expected_Service_Name == "ssh"
        assert port.Port_State is PortState.SUGGESTED
        assert port.Plugin_Name is None

    def test_promotion_skips_it_even_though_its_plugin_is_enabled(self, device):
        self.flagged(device)
        assert promote_identified_ports() == 0
        assert tcp_port(device, 22).Port_State is PortState.SUGGESTED

    def test_acknowledging_accepts_the_service_nmap_found_and_monitors_it(self, device):
        self.flagged(device)
        port = acknowledge_port_mismatch(device.NetDiscoveryID, "tcp", 22)
        db.session.commit()
        assert port.Mismatch_Acknowledged_At is not None
        assert port.Service_Name == "http"
        assert port.Port_State is PortState.MONITORED
        assert port.Plugin_Name == "http"

    def test_an_acknowledged_port_stays_acknowledged_while_nothing_changes(self, device):
        self.flagged(device)
        acknowledge_port_mismatch(device.NetDiscoveryID, "tcp", 22)
        db.session.commit()
        scan_port(device, 22, "http", FINGERPRINT, expected_service="ssh")
        assert tcp_port(device, 22).Mismatch_Acknowledged_At is not None
        assert tcp_port(device, 22).Port_State is PortState.MONITORED

    def test_a_different_sighting_clears_the_acknowledgement(self, device):
        self.flagged(device)
        acknowledge_port_mismatch(device.NetDiscoveryID, "tcp", 22)
        db.session.commit()
        scan_port(device, 22, "mysql", FINGERPRINT, expected_service="ssh")
        port = tcp_port(device, 22)
        assert port.Mismatch_Acknowledged_At is None
        assert port.Expected_Service_Name == "ssh"

    def test_acknowledging_a_suggestion_whose_plugin_is_off_leaves_it_suggested(self, device):
        scan_port(device, 3306, "mysql", FINGERPRINT, expected_service="ssh")
        acknowledge_port_mismatch(device.NetDiscoveryID, "tcp", 3306)
        db.session.commit()
        port = tcp_port(device, 3306)
        assert port.Mismatch_Acknowledged_At is not None
        assert port.Port_State is PortState.SUGGESTED

    def test_the_table_agreeing_again_clears_the_flag(self, device):
        self.flagged(device)
        scan_port(device, 22, "ssh", PORT_RULE)
        port = tcp_port(device, 22)
        assert port.Expected_Service_Name is None
        assert port.Mismatch_Acknowledged_At is None

    def test_acknowledging_twice_or_an_unflagged_port_is_refused(self, device):
        scan_port(device, 80, "http", FINGERPRINT)
        with pytest.raises(ValueError):
            acknowledge_port_mismatch(device.NetDiscoveryID, "tcp", 80)
        self.flagged(device)
        acknowledge_port_mismatch(device.NetDiscoveryID, "tcp", 22)
        with pytest.raises(ValueError):
            acknowledge_port_mismatch(device.NetDiscoveryID, "tcp", 22)

    def test_acknowledging_a_missing_port_returns_none(self, device):
        assert acknowledge_port_mismatch(device.NetDiscoveryID, "tcp", 9999) is None

    def test_pinning_the_service_settles_the_flag(self, device):
        self.flagged(device)
        pin_port_service(device.NetDiscoveryID, "tcp", 22, "ssh")
        db.session.commit()
        port = tcp_port(device, 22)
        assert port.Expected_Service_Name is None
        assert port.Identified_By is ServiceIdentification.USER

    def test_a_pinned_port_is_never_flagged(self, device):
        scan_port(device, 22, "http-proxy", PORT_HINT)
        pin_port_service(device.NetDiscoveryID, "tcp", 22, "ssh")
        db.session.commit()
        scan_port(device, 22, "http", FINGERPRINT, expected_service="ssh")
        assert tcp_port(device, 22).Expected_Service_Name is None

    def test_a_monitored_port_is_flagged_but_keeps_running(self, device):
        scan_port(device, 22, "ssh", FINGERPRINT)
        scan_port(device, 22, "ssh", FINGERPRINT, expected_service="ssh2")
        port = tcp_port(device, 22)
        assert port.Port_State is PortState.MONITORED
        assert port.Expected_Service_Name == "ssh2"
