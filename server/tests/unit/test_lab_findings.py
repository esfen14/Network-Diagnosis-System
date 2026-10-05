"""
tests/unit/test_lab_findings.py — regressions for the 2026-10-05 NCPA, SSH-port
and service-identification lab test (defects D1, D5, D9 and the leftover note).
"""
import ssl
import socket
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import pytest

from app.ncpa_deployment import ncpa_deployment as ncpa
from app.network_discovery import identity_probes, network_discovery
from app.system_models import DeploymentOutcome


# ==========================================================
# D1: THE CERTIFICATE PROBE CLOSES TLS CLEANLY
# ==========================================================

class TestTlsProbeShutdown:

    def probe(self, unwrap_error=None):
        tls = MagicMock()
        tls.getpeercert.return_value = b"der-bytes"
        if unwrap_error is not None:
            tls.unwrap.side_effect = unwrap_error
        context = MagicMock()
        context.wrap_socket.return_value.__enter__.return_value = tls
        with patch.object(identity_probes.ssl, "SSLContext", return_value=context), \
             patch.object(identity_probes.socket, "create_connection"):
            return identity_probes.tls_certificate_fingerprint("10.0.0.5", 5693), tls

    def test_session_is_unwrapped_after_the_certificate_is_read(self):
        fingerprint, tls = self.probe()
        assert fingerprint is not None
        tls.unwrap.assert_called_once_with()

    @pytest.mark.parametrize("error", [ssl.SSLError("closed"), OSError("reset")])
    def test_a_failed_shutdown_keeps_the_fingerprint(self, error):
        fingerprint, _tls = self.probe(unwrap_error=error)
        assert fingerprint is not None


class TestPortAcceptsConnections:

    def test_open_port(self):
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        try:
            assert identity_probes.port_accepts_connections("127.0.0.1", server.getsockname()[1]) is True
        finally:
            server.close()

    def test_closed_port(self):
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
        server.close()
        assert identity_probes.port_accepts_connections("127.0.0.1", port, timeout=1) is False


# ==========================================================
# D5: PSEUDO FILESYSTEMS ARE NOT DISKS
# ==========================================================

@pytest.mark.parametrize("name, info, expected", [
    ("|", {"fstype": "ext4"}, True),
    ("|data", {"fstype": "xfs"}, True),
    ("|sys|fs|bpf", {"fstype": "bpf"}, False),
    ("|sys|kernel|tracing", {}, False),
    ("|boot|efi", {"fstype": "vfat"}, False),
    ("|run|user|1000", {"fstype": "tmpfs"}, False),
    ("|bootstrap", {"fstype": "ext4"}, True),
])
def test_monitorable_disk_nodes(name, info, expected):
    assert ncpa._is_monitorable_disk_node(name, info) is expected


# ==========================================================
# FAILED DEPLOYMENT LEFTOVERS
# ==========================================================

class TestLeftoverNote:

    def deploy(self, bootstrap, install):
        with patch.object(ncpa, "give_program_permissions", return_value=bootstrap), \
             patch.object(ncpa, "install_ncpa", return_value=install), \
             patch.object(ncpa, "update_ncpa_deployment_info") as update:
            return ncpa.deploy_device(1, 1, "10.0.0.5", "u", "p"), update

    def test_install_failure_mentions_the_remaining_account(self):
        (outcome, error), update = self.deploy(
            (DeploymentOutcome.SUCCESS, None), (DeploymentOutcome.FAILED, "NCPA install failed."))
        assert outcome is DeploymentOutcome.FAILED
        assert error == f"NCPA install failed. {ncpa.LEFTOVER_NOTE}"
        update.assert_called_once()

    def test_bootstrap_failure_has_no_note(self):
        (_outcome, error), _update = self.deploy(
            (DeploymentOutcome.FAILED, "SSH authentication failed."), (DeploymentOutcome.SUCCESS, None))
        assert error == "SSH authentication failed."

    def test_success_has_no_note(self):
        (outcome, error), _update = self.deploy(
            (DeploymentOutcome.SUCCESS, None), (DeploymentOutcome.SUCCESS, None))
        assert (outcome, error) == (DeploymentOutcome.SUCCESS, None)


# ==========================================================
# D9: TWO-STEP UDP SCAN
# ==========================================================

def udp_xml(*ports):
    body = ""
    for portid, state, name, method in ports:
        body += (f'<port protocol="udp" portid="{portid}"><state state="{state}"/>'
                 f'<service name="{name}" method="{method}"/></port>')
    return ET.fromstring(f"<nmaprun><host><ports>{body}</ports></host></nmaprun>")


class TestUdpTwoStepScan:

    def run_scan(self, results, app):
        nmap = MagicMock()
        nmap.scan_command.side_effect = results
        with app.app_context(), patch.object(network_discovery.nmap3, "Nmap", return_value=nmap), \
             patch.object(network_discovery, "get_discovery_setting", return_value=[53, 69, 161]):
            found = network_discovery._discover_host_udp_port("10.0.0.5")
        return found, nmap

    def test_version_detection_only_covers_ports_that_answered(self, app):
        first = udp_xml(("53", "open", "domain", "table"), ("69", "open|filtered", "tftp", "table"),
                        ("161", "open", "snmp", "table"))
        second = udp_xml(("53", "open", "domain", "probed"), ("161", "open", "snmp", "probed"))

        (confirmed, unconfirmed), nmap = self.run_scan([first, second], app)

        assert nmap.scan_command.call_count == 2
        first_call, second_call = nmap.scan_command.call_args_list
        assert "-sV" not in first_call.args[1]
        assert "-sV" in second_call.args[1]
        assert "-p 53,161" in second_call.args[2]
        assert confirmed["53"]["identified_by"] == "FINGERPRINT"
        assert confirmed["161"]["identified_by"] == "FINGERPRINT"
        assert list(unconfirmed) == ["69"]

    def test_no_second_scan_when_nothing_answered(self, app):
        (confirmed, _unconfirmed), nmap = self.run_scan([udp_xml(("69", "open|filtered", "tftp", "table"))], app)
        assert confirmed == {}
        assert nmap.scan_command.call_count == 1

    def test_failed_version_detection_keeps_the_port_number_names(self, app):
        first = udp_xml(("53", "open", "domain", "table"))
        (confirmed, _unconfirmed), _nmap = self.run_scan([first, RuntimeError("nmap failed")], app)
        assert confirmed["53"] == {"service_name": "domain", "identified_by": "PORT_HINT"}
