"""
tests/unit/test_ssh_port.py — NCPA deployment on a device whose SSH is not on 22.

The SSH port comes from the device's recorded ports
(port_lifecycle.device_ssh_port), is pinned together with the host-key
fingerprint at trust confirmation (SSHCredentials.SSH_Port), and is the port
every later deployment connection uses. Discovery probes the SSH host key on
every port nmap identified as ssh. The NCPA helper configures the agent's
listener on Config.NCPA_PORT.
"""
import shutil
import subprocess
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa

from app import db
from app.api.system import ncpa_deployment as ncpa_routes
from app.ncpa_deployment import ncpa_deployment as ncpa
from app.network_discovery import identity_probes
from app.network_discovery.port_lifecycle import add_user_port, device_ssh_port
from app.system_models import (
    DeploymentOutcome,
    IdentifierKind,
    NCPADeploymentResult,
    Open_TCP_Services,
    PortState,
    SSHCredentials,
)
from tests.support.identity_helpers import MAC_1, NET, SSH_1, make_status, patched_config, run_scan, scan


def make_device(db_session, admin_user, tcp):
    """A Linux device saved by a scan that saw the given {port: service} TCP ports."""
    status = make_status(db_session, admin_user)
    return run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1, tcp=tcp))[(NET, "10.0.0.5")]


def tcp_port(device, number):
    return db.session.scalar(sa.select(Open_TCP_Services).where(
        Open_TCP_Services.NetDiscoveryID == device.NetDiscoveryID,
        Open_TCP_Services.Port_Number == number))


def ssh_credentials(device):
    return db.session.scalar(sa.select(SSHCredentials).where(
        SSHCredentials.NetworkDiscoveryID == device.NetDiscoveryID))


# ==========================================================
# DEVICE SSH PORT
# ==========================================================

class TestDeviceSshPort:

    def test_no_ssh_port_on_record_uses_the_standard_port(self, db_session, admin_user):
        device = make_device(db_session, admin_user, {80: "http"})
        assert device_ssh_port(device.NetDiscoveryID) == 22

    def test_ssh_on_a_non_standard_port(self, db_session, admin_user):
        device = make_device(db_session, admin_user, {2222: "ssh", 80: "http"})
        assert device_ssh_port(device.NetDiscoveryID) == 2222

    def test_standard_port_wins_when_both_are_ssh(self, db_session, admin_user):
        device = make_device(db_session, admin_user, {22: "ssh", 2222: "ssh"})
        assert device_ssh_port(device.NetDiscoveryID) == 22

    def test_hand_added_port_wins(self, db_session, admin_user):
        device = make_device(db_session, admin_user, {22: "ssh"})
        add_user_port(device.NetDiscoveryID, "tcp", 2200, "ssh")
        db.session.commit()
        assert device_ssh_port(device.NetDiscoveryID) == 2200

    def test_monitored_port_wins_over_a_suggestion(self, db_session, admin_user):
        device = make_device(db_session, admin_user, {22: "ssh", 2222: "ssh"})
        tcp_port(device, 22).Port_State = PortState.SUGGESTED
        db.session.commit()
        assert device_ssh_port(device.NetDiscoveryID) == 2222

    def test_ports_that_stopped_answering_are_passed_over(self, db_session, admin_user):
        device = make_device(db_session, admin_user, {22: "ssh", 2222: "ssh"})
        tcp_port(device, 22).Port_State = PortState.MISSING
        db.session.commit()
        assert device_ssh_port(device.NetDiscoveryID) == 2222

        tcp_port(device, 2222).Port_State = PortState.ARCHIVED
        db.session.commit()
        assert device_ssh_port(device.NetDiscoveryID) == 22

    def test_frozen_plugin_counts_as_ssh(self, db_session, admin_user):
        device = make_device(db_session, admin_user, {2222: "EtherNetIP-1"})
        port = tcp_port(device, 2222)
        port.Plugin_Name = "ssh"
        db.session.commit()
        assert device_ssh_port(device.NetDiscoveryID) == 2222

    def test_follows_the_configured_standard_port(self, app, db_session, admin_user):
        device = make_device(db_session, admin_user, {80: "http"})
        with patched_config(app, SSH_PORT=2022):
            assert device_ssh_port(device.NetDiscoveryID) == 2022


# ==========================================================
# TRUST CONFIRMATION AND DEPLOYMENT ROUTES
# ==========================================================

class TestRoutesUseTheDevicePort:

    def test_fingerprint_is_read_from_the_discovered_port(self, logged_in_client, db_session, admin_user):
        device = make_device(db_session, admin_user, {2222: "ssh"})

        with patch.object(ncpa_routes, "get_host_key_fingerprint", return_value="fp:2222") as probe:
            resp = logged_in_client.get(f"/api/system/deployment/ncpa/{device.NetDiscoveryID}/fingerprint")

        assert resp.status_code == 200
        assert resp.get_json()["data"]["ssh_port"] == 2222
        probe.assert_called_once_with("10.0.0.5", 2222)

    def test_confirm_trust_pins_the_port_with_the_fingerprint(self, logged_in_client, db_session, admin_user):
        device = make_device(db_session, admin_user, {2222: "ssh"})
        assert ssh_credentials(device).SSH_Port == 22

        with patch.object(ncpa_routes, "get_host_key_fingerprint", return_value="fp:2222") as probe:
            resp = logged_in_client.post(
                f"/api/system/deployment/ncpa/{device.NetDiscoveryID}/confirm-trust",
                json={"fingerprint": "fp:2222"},
            )

        assert resp.status_code == 200
        probe.assert_called_once_with("10.0.0.5", 2222)
        creds = ssh_credentials(device)
        db.session.refresh(creds)
        assert (creds.Key_Fingerprint, creds.SSH_Port) == ("fp:2222", 2222)

    def test_a_key_that_changed_on_the_device_port_is_not_trusted(self, logged_in_client, db_session, admin_user):
        device = make_device(db_session, admin_user, {2222: "ssh"})

        with patch.object(ncpa_routes, "get_host_key_fingerprint", return_value="fp:NEW") as probe:
            resp = logged_in_client.post(
                f"/api/system/deployment/ncpa/{device.NetDiscoveryID}/confirm-trust",
                json={"fingerprint": "fp:2222"},
            )

        assert resp.status_code == 409
        assert resp.get_json()["data"]["fingerprint"] == "fp:NEW"
        probe.assert_called_once_with("10.0.0.5", 2222)
        creds = ssh_credentials(device)
        db.session.refresh(creds)
        # Nothing is trusted, and the port is only pinned together with a trusted key.
        assert (creds.Key_Fingerprint, creds.SSH_Port) == (None, 22)

    def test_unreachable_device_port_is_502_and_saves_nothing(self, logged_in_client, db_session, admin_user):
        device = make_device(db_session, admin_user, {2222: "ssh"})

        with patch.object(ncpa_routes, "get_host_key_fingerprint", return_value=None):
            resp = logged_in_client.post(
                f"/api/system/deployment/ncpa/{device.NetDiscoveryID}/confirm-trust",
                json={"fingerprint": "fp:2222"},
            )

        assert resp.status_code == 502
        assert ssh_credentials(device).Key_Fingerprint is None

    def test_deploy_checks_the_host_key_on_the_pinned_port(self, logged_in_client, db_session, admin_user):
        device = make_device(db_session, admin_user, {2222: "ssh"})
        creds = ssh_credentials(device)
        creds.Key_Fingerprint, creds.SSH_Port = "fp:2222", 2222
        db.session.commit()

        with patch.object(ncpa_routes, "deploy_ncpa_thread", None), \
             patch.object(ncpa_routes.threading, "Thread"), \
             patch.object(ncpa_routes, "get_host_key_fingerprint", return_value="fp:2222") as probe:
            resp = logged_in_client.post("/api/system/deployment/ncpa/start", json={
                "devices": [{"device_id": device.NetDiscoveryID, "username": "u", "password": "p"}],
            })

        assert resp.status_code == 202
        data = resp.get_json()["data"]
        assert data["started"] == 1
        probe.assert_called_once_with("10.0.0.5", 2222)
        # The run records the accepted device as Pending.
        outcomes = db.session.scalars(
            sa.select(NCPADeploymentResult.Outcome).where(
                NCPADeploymentResult.NCPADeploymentStatusID == data["run_id"])
        ).all()
        assert outcomes == [DeploymentOutcome.PENDING]

    def test_deploy_rejects_a_changed_key_on_the_pinned_port(self, logged_in_client, db_session, admin_user):
        device = make_device(db_session, admin_user, {2222: "ssh"})
        creds = ssh_credentials(device)
        creds.Key_Fingerprint, creds.SSH_Port = "fp:2222", 2222
        db.session.commit()

        with patch.object(ncpa_routes, "deploy_ncpa_thread", None), \
             patch.object(ncpa_routes.threading, "Thread") as thread_cls, \
             patch.object(ncpa_routes, "get_host_key_fingerprint", return_value="fp:NEW"):
            resp = logged_in_client.post("/api/system/deployment/ncpa/start", json={
                "devices": [{"device_id": device.NetDiscoveryID, "username": "u", "password": "p"}],
            })

        assert resp.status_code == 400
        assert resp.get_json()["data"]["rejected"] == [
            {"device_id": device.NetDiscoveryID, "reason": "Host key mismatch."}]
        thread_cls.assert_not_called()


# ==========================================================
# SSH CONNECTION
# ==========================================================

class TestSshConnection:

    def test_query_trusted_host_returns_fingerprint_and_port(self, db_session, admin_user):
        device = make_device(db_session, admin_user, {2222: "ssh"})
        creds = ssh_credentials(device)
        creds.Key_Fingerprint, creds.SSH_Port = "fp", 2222
        db.session.commit()

        assert ncpa.query_trusted_host(device.NetDiscoveryID) == ("fp", 2222)
        assert ncpa.query_trusted_host(999999) == (None, None)

    def test_host_key_name_follows_known_hosts_convention(self):
        assert ncpa.ssh_host_key_name("10.0.0.5", 22) == "10.0.0.5"
        assert ncpa.ssh_host_key_name("10.0.0.5", 2222) == "[10.0.0.5]:2222"

    @pytest.mark.parametrize("port, key_name", [(22, "10.0.0.5"), (2222, "[10.0.0.5]:2222")])
    def test_connect_uses_the_port_and_registers_the_key_under_its_name(self, app, port, key_name):
        client = MagicMock()
        transport = MagicMock()
        with app.app_context(), \
             patch.object(ncpa, "verify_host_fingerprint", return_value=True) as verify, \
             patch.object(ncpa.paramiko, "SSHClient", return_value=client), \
             patch.object(ncpa.paramiko, "Transport", return_value=transport) as transport_cls:
            result = ncpa.connect_with_fingerprint_check("10.0.0.5", port, "user", "fp", password="pw")

        assert result is client
        verify.assert_called_once_with("10.0.0.5", port, "fp")
        transport_cls.assert_called_once_with(("10.0.0.5", port))
        assert client.get_host_keys().add.call_args.args[0] == key_name
        assert client.connect.call_args.kwargs["port"] == port

    def test_a_host_unreachable_on_the_pinned_port_is_not_connected(self, app):
        with app.app_context(), \
             patch.object(ncpa, "get_host_key_fingerprint", return_value=None) as probe, \
             patch.object(ncpa.paramiko, "SSHClient") as client_cls:
            assert ncpa.connect_with_fingerprint_check("10.0.0.5", 2222, "user", "fp") is None

        probe.assert_called_once_with("10.0.0.5", 2222)
        client_cls.assert_not_called()


# ==========================================================
# DISCOVERY IDENTITY PROBES
# ==========================================================

class TestSshIdentityProbe:

    def test_probes_ssh_on_a_non_standard_port(self, app):
        with app.app_context(), \
             patch.object(identity_probes, "ssh_host_key_fingerprint", return_value=SSH_1) as probe:
            found = identity_probes.collect_identifiers("10.0.0.5", {"2222": {"service_name": "ssh"}})

        assert found == [(IdentifierKind.SSH_HOST_KEY, SSH_1)]
        probe.assert_called_once_with("10.0.0.5", 2222)

    def test_other_services_on_other_ports_are_not_probed(self, app):
        with app.app_context(), \
             patch.object(identity_probes, "ssh_host_key_fingerprint", return_value=SSH_1) as probe:
            found = identity_probes.collect_identifiers("10.0.0.5", {"8080": {"service_name": "http"}})

        assert found == []
        probe.assert_not_called()

    def test_one_key_on_two_ports_is_reported_once(self, app):
        with app.app_context(), \
             patch.object(identity_probes, "ssh_host_key_fingerprint", return_value=SSH_1) as probe:
            found = identity_probes.collect_identifiers(
                "10.0.0.5", {"22": {"service_name": "ssh"}, "2222": {"service_name": "ssh"}}
            )

        assert found == [(IdentifierKind.SSH_HOST_KEY, SSH_1)]
        assert [call.args[1] for call in probe.call_args_list] == [22, 2222]


# ==========================================================
# NCPA LISTENER PORT
# ==========================================================

class TestHelperUsesConfiguredNcpaPort:

    def install_helper(self):
        """Run install_deployment_helper against a mock client; returns the helper text written."""
        client = MagicMock()
        written = client.open_sftp.return_value.file.return_value.__enter__.return_value
        with patch.object(ncpa, "run_sudo_command", return_value={"success": True}):
            assert ncpa.install_deployment_helper(client, "pw") is True
        return written.write.call_args.args[0]

    def test_default_port(self, app):
        with app.app_context():
            helper = self.install_helper()
        assert 'NCPA_PORT="5693"' in helper
        assert "__NCPA_PORT__" not in helper
        assert "/^\\[listener\\]/a port = $NCPA_PORT" in helper

    def test_configured_port(self, app):
        with app.app_context(), patched_config(app, NCPA_PORT="5800"):
            helper = self.install_helper()
        assert 'NCPA_PORT="5800"' in helper

    def test_reachability_and_api_use_the_configured_port(self, app):
        with app.app_context(), patched_config(app, NCPA_PORT="5800"), \
             patch.object(ncpa.requests, "get") as get:
            get.return_value.status_code = 200
            ncpa.verify_ncpa_reachable("10.0.0.5", "tok")
            ncpa._ncpa_get("10.0.0.5", "tok", "disk/logical")

        urls = [call.args[0] for call in get.call_args_list]
        assert urls == ["https://10.0.0.5:5800/api", "https://10.0.0.5:5800/api/disk/logical"]

    @pytest.mark.parametrize("bad", ["0", "70000", "56a", "abc", None])
    def test_an_invalid_port_is_never_written_into_the_helper(self, app, bad):
        with app.app_context(), patched_config(app, NCPA_PORT=bad), \
             pytest.raises(ValueError, match="NCPA_PORT must be an integer between 1 and 65535."):
            ncpa.ncpa_port()

    def test_agent_restarts_through_systemd(self, app):
        with app.app_context():
            helper = self.install_helper()
        assert '"$SYSTEMCTL" restart ncpa' in helper
        assert "/etc/init.d/ncpa" not in helper


STOCK_LISTENER = """[listener]
# ip =
# port =
uuid = abc

[api]
community_string = old
"""


@pytest.mark.skipif(shutil.which("bash") is None or shutil.which("sed") is None, reason="needs bash and sed")
class TestHelperListenerPortEdit:
    """Run the helper's real [listener] port edit against sample ncpa.cfg files."""

    def edit(self, app, tmp_path, config_text, port="5800"):
        with app.app_context(), patched_config(app, NCPA_PORT=port):
            helper = TestHelperUsesConfiguredNcpaPort().install_helper()
        start = helper.index("# Listen on PinPoint's configured NCPA port.")
        end = helper.index("# Use a persistent self-signed certificate")
        config = tmp_path / "ncpa.cfg"
        config.write_text(config_text)
        script = (
            'set -euo pipefail\nSED=/usr/bin/sed\n'
            f'NCPA_PORT="{port}"\nNCPA_CONFIG="{config}"\n' + helper[start:end]
        )
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        return result, config.read_text()

    def listener_port_lines(self, text):
        found = []
        in_listener = False
        for line in text.splitlines():
            if line.startswith("["):
                in_listener = line == "[listener]"
            elif in_listener and line.startswith("port"):
                found.append(line)
        return found

    def test_stock_config_with_commented_port(self, app, tmp_path):
        result, text = self.edit(app, tmp_path, STOCK_LISTENER)
        assert result.returncode == 0, result.stderr
        assert self.listener_port_lines(text) == ["port = 5800"]
        assert "# ip =" in text and "community_string = old" in text

    def test_existing_active_port_is_replaced(self, app, tmp_path):
        result, text = self.edit(app, tmp_path, STOCK_LISTENER.replace("# port =", "port = 5693"))
        assert result.returncode == 0, result.stderr
        assert self.listener_port_lines(text) == ["port = 5800"]

    def test_redeploy_is_idempotent(self, app, tmp_path):
        _, once = self.edit(app, tmp_path, STOCK_LISTENER)
        result, twice = self.edit(app, tmp_path, once)
        assert result.returncode == 0, result.stderr
        assert self.listener_port_lines(twice) == ["port = 5800"]

    def test_config_without_listener_section_fails_with_a_specific_message(self, app, tmp_path):
        result, _ = self.edit(app, tmp_path, "[api]\ncommunity_string = old\n")
        assert result.returncode == 1
        assert "Could not set the NCPA listener port." in result.stderr
