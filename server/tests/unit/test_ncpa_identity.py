"""
tests/unit/test_ncpa_identity.py — Phase 2 of "spec files/DHCP_Device_Identity_Plan.md":
identity evidence collected at NCPA deployment, identity probes used during
scans, and the relocation job that follows an NCPA device after a lease change.

Nothing talks to a real device: SSH, nmap and Nagios are mocked. The TLS
probe is tested against a real local TLS server so we can prove it reads the
certificate and sends no data (never a token).
"""
import base64
import hashlib
import shutil
import socket
import ssl
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa

from app import db
from app.history_models import HostStateType
from app.network_discovery import create_host_cfg, identity_probes, ncpa_relocation
from app.ncpa_deployment import ncpa_deployment as ncpa
from app.system_models import (
    AddressSource,
    DeviceState,
    IdentifierKind,
    IdentityConfidence,
    NCPADeployment,
    NCPADevicePartition,
    NetworkDiscovery,
    ReviewKind,
)
from tests.support.identity_helpers import (
    CERT_1, CERT_2, MAC_1, MAC_2, NET, SSH_1, address_rows, cert, identifier_values,
    make_status, open_addresses, patched_config, review_items, run_scan, scan,
)
from tests.support.seed_helpers import _make_host

MACHINE_ID = "0123456789abcdef0123456789abcdef"

HELPER_OUTPUT = f"""
Setting up ncpa ...
PARTITIONS_BEGIN
sda1
PARTITIONS_END
IDENTITY_BEGIN
machine_id={MACHINE_ID}
mac=00:11:22:33:44:01
mac=00:11:22:33:44:01
mac=02:aa:bb:cc:dd:ee
hostname=web01
IDENTITY_END
trailing noise
"""


# ==========================================================
# HELPER SCRIPT OUTPUT
# ==========================================================

class TestParseIdentity:

    def test_parses_machine_id_macs_and_hostname(self):
        identity = ncpa._parse_identity(HELPER_OUTPUT)

        assert identity == {"machine_id": MACHINE_ID, "macs": [MAC_1], "hostname": "web01"}

    def test_randomized_and_duplicate_macs_are_dropped(self):
        identity = ncpa._parse_identity(HELPER_OUTPUT)

        assert identity["macs"] == ["00:11:22:33:44:01"]

    def test_missing_block_gives_empty_identity(self):
        assert ncpa._parse_identity("PARTITIONS_BEGIN\nsda1\nPARTITIONS_END\n") == {
            "machine_id": None, "macs": [], "hostname": None}

    def test_invalid_values_are_ignored(self):
        text = "IDENTITY_BEGIN\nmachine_id=not-a-machine-id\nmac=garbage\nhostname=\nIDENTITY_END\n"

        assert ncpa._parse_identity(text) == {"machine_id": None, "macs": [], "hostname": None}

    def test_lines_outside_the_sentinels_are_ignored(self):
        text = f"machine_id={MACHINE_ID}\nIDENTITY_BEGIN\nIDENTITY_END\nmac={MAC_1}\n"

        assert ncpa._parse_identity(text) == {"machine_id": None, "macs": [], "hostname": None}


class TestHelperScript:

    @pytest.fixture
    def script(self, app):
        client = MagicMock()
        sftp = client.open_sftp.return_value
        written = []
        sftp.file.return_value.__enter__.return_value.write.side_effect = written.append
        with app.app_context(), patch.object(ncpa, "run_sudo_command", return_value={"success": True}):
            assert ncpa.install_deployment_helper(client, "pw") is True
        return written[0]

    def test_prints_the_identity_block(self, script):
        assert "IDENTITY_BEGIN" in script and "IDENTITY_END" in script
        assert "/etc/machine-id" in script
        assert "PARTITIONS_BEGIN" not in script and "lsblk" not in script

    def test_uses_a_persistent_certificate_instead_of_adhoc(self, script):
        assert "pinpoint-ncpa.crt" in script and "pinpoint-ncpa.key" in script
        assert "certificate = $CERT_FILE,$KEY_FILE" in script
        # Generated only when missing, so a redeploy keeps the same fingerprint.
        assert '[ ! -s "$CERT_FILE" ]' in script

    def test_never_prints_the_token(self, script):
        for line in script.splitlines():
            if "echo" in line:
                assert "TOKEN" not in line
        identity = script.split("IDENTITY_BEGIN")[1].split("IDENTITY_END")[0]
        assert "TOKEN" not in identity and "community_string" not in identity

    def test_key_is_group_readable_by_nagios_on_every_deploy(self, script):
        # The repair must sit outside the "create once" block.
        create_block, _, repair = script.partition('-keyout "$KEY_FILE"')
        assert "chown root:nagios" not in create_block
        assert 'chown root:nagios "$KEY_FILE"' in repair
        assert 'chmod 640 "$KEY_FILE"' in repair
        assert 'chmod 644 "$CERT_FILE"' in repair
        assert "runuser -u nagios" in repair

    def test_start_is_verified_by_a_real_listener_probe(self, script):
        assert 'ss -ltn' in script
        assert "/api/?token=$TOKEN" in script
        assert "grep -qi \"running\"" not in script

    @pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not available")
    def test_script_is_valid_bash(self, script, tmp_path):
        path = tmp_path / "helper.sh"
        path.write_text(script, newline="\n")

        result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)

        assert result.returncode == 0, result.stderr


# ==========================================================
# STORING IDENTITY AFTER DEPLOYMENT
# ==========================================================

def make_linux_device(db_session, admin_user, ip="10.0.0.5", mac=MAC_1, identifiers=(), hostname="web.lan"):
    status = make_status(db_session, admin_user)
    return run_scan(db_session, status, scan(ip, mac=mac, hostname=hostname, identifiers=identifiers))[(NET, ip)]


class TestStoreDeploymentIdentity:

    def test_stores_machine_id_macs_and_certificate(self, db_session, admin_user):
        device = make_linux_device(db_session, admin_user, mac=None)

        rejected = ncpa.store_deployment_identity(
            device.NetDiscoveryID, ncpa._parse_identity(HELPER_OUTPUT), CERT_1)

        assert rejected == []
        assert identifier_values(device, IdentifierKind.MACHINE_ID) == {MACHINE_ID}
        assert identifier_values(device, IdentifierKind.MAC) == {MAC_1}
        assert identifier_values(device, IdentifierKind.NCPA_CERT) == {CERT_1}
        assert device.Identity_Confidence is IdentityConfidence.VERIFIED

    def test_cloned_machine_id_raises_a_review_item_instead_of_moving(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        first = run_scan(db_session, status, scan("10.0.0.1"))[(NET, "10.0.0.1")]
        second = run_scan(db_session, status, scan("10.0.0.2"))[(NET, "10.0.0.2")]
        identity = {"machine_id": MACHINE_ID, "macs": [], "hostname": None}
        ncpa.store_deployment_identity(first.NetDiscoveryID, identity, None)

        rejected = ncpa.store_deployment_identity(second.NetDiscoveryID, identity, None)

        assert [e.kind for e in rejected] == [IdentifierKind.MACHINE_ID]
        assert identifier_values(first, IdentifierKind.MACHINE_ID) == {MACHINE_ID}
        assert identifier_values(second, IdentifierKind.MACHINE_ID) == set()
        assert len(review_items(ReviewKind.CONFLICT)) == 1

    def test_unknown_device_is_a_no_op(self, db_session):
        assert ncpa.store_deployment_identity(9999, {"machine_id": MACHINE_ID, "macs": []}, CERT_1) == []


class TestInstallNcpa:
    """install_ncpa() with SSH, the helper and NCPA reachability mocked."""

    def run_install(self, device, existing_token=None):
        if existing_token is not None:
            deployment = db.session.scalar(sa.select(NCPADeployment).where(
                NCPADeployment.NetworkDiscoveryID == device.NetDiscoveryID))
            deployment.Token = existing_token
            db.session.commit()

        client = MagicMock()
        run = MagicMock(return_value={"success": True, "message": "", "output": HELPER_OUTPUT, "error": ""})
        with patch.object(ncpa, "query_trusted_host", return_value=("fp", 22)), \
             patch.object(ncpa, "connect_with_fingerprint_check", return_value=client), \
             patch.object(ncpa, "run_command", run), \
             patch.object(ncpa, "verify_ncpa_reachable", return_value={"success": True, "message": ""}), \
             patch.object(ncpa, "tls_certificate_fingerprint", return_value=CERT_1) as probe:
            ok = ncpa.install_ncpa(device.NetDiscoveryID, None, device.IP_Address)
        return ok, run, probe

    def test_deployment_stores_identity_evidence(self, db_session, admin_user):
        device = make_linux_device(db_session, admin_user, mac=None)

        ok, _run, probe = self.run_install(device)

        assert ok is True
        probe.assert_called_once_with("10.0.0.5", 5693)
        assert identifier_values(device, IdentifierKind.NCPA_CERT) == {CERT_1}
        assert identifier_values(device, IdentifierKind.MACHINE_ID) == {MACHINE_ID}
        assert device.Identity_Confidence is IdentityConfidence.VERIFIED

    def test_success_clears_an_earlier_error(self, db_session, admin_user):
        device = make_linux_device(db_session, admin_user)
        deployment = db.session.scalar(sa.select(NCPADeployment).where(
            NCPADeployment.NetworkDiscoveryID == device.NetDiscoveryID))
        deployment.Error = "Privileged command failed."
        db.session.commit()

        ok, _run, _probe = self.run_install(device)

        assert ok is True
        db.session.refresh(deployment)
        assert deployment.Error is None

    def test_a_new_deployment_mints_a_token(self, db_session, admin_user):
        device = make_linux_device(db_session, admin_user)

        _ok, run, _probe = self.run_install(device)

        token = run.call_args.args[1].split()[-1].strip("'")
        assert len(token) == 32 and int(token, 16) >= 0

    def test_redeploy_reuses_the_existing_token(self, db_session, admin_user):
        device = make_linux_device(db_session, admin_user)
        existing = "f" * 32

        ok, run, _probe = self.run_install(device, existing_token=existing)

        assert ok is True
        assert run.call_args.args[1].endswith(existing)
        deployment = db.session.scalar(sa.select(NCPADeployment).where(
            NCPADeployment.NetworkDiscoveryID == device.NetDiscoveryID))
        assert deployment.Token == existing

    def test_identity_failure_does_not_fail_the_deployment(self, db_session, admin_user):
        device = make_linux_device(db_session, admin_user)

        with patch.object(ncpa, "store_deployment_identity", side_effect=RuntimeError("boom")):
            ok, _run, _probe = self.run_install(device)

        assert ok is True
        deployment = db.session.scalar(sa.select(NCPADeployment).where(
            NCPADeployment.NetworkDiscoveryID == device.NetDiscoveryID))
        assert deployment.Token is not None
        assert deployment.Agent_Status.name == "DEPLOYED"


# ==========================================================
# PROBES
# ==========================================================

@pytest.fixture
def tls_server(tmp_path):
    """
    A local TLS server with a self-signed certificate. Yields (port, der,
    received) where received collects any application data a client sends.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ncpa-test")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp_path / "c.pem", tmp_path / "k.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()))

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    received = []

    def serve():
        try:
            raw, _ = listener.accept()
            with context.wrap_socket(raw, server_side=True) as conn:
                conn.settimeout(2)
                try:
                    received.append(conn.recv(1024))
                except (OSError, ssl.SSLError):
                    received.append(b"")
        except OSError:
            pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield port, certificate.public_bytes(serialization.Encoding.DER), received
    listener.close()
    thread.join(3)


class TestTlsProbe:

    def test_returns_the_certificate_sha256_and_sends_no_data(self, tls_server):
        port, der, received = tls_server

        fingerprint = identity_probes.tls_certificate_fingerprint("127.0.0.1", port, timeout=3)

        assert fingerprint == hashlib.sha256(der).hexdigest()
        # The probe only completes the handshake: no token, no request.
        assert received == [] or received == [b""]

    def test_closed_port_returns_none(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        listener.close()

        assert identity_probes.tls_certificate_fingerprint("127.0.0.1", port, timeout=1) is None

    def test_non_tls_service_returns_none(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        def serve():
            try:
                conn, _ = listener.accept()
                conn.sendall(b"SSH-2.0-not-tls\r\n")
                conn.close()
            except OSError:
                pass

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            assert identity_probes.tls_certificate_fingerprint("127.0.0.1", port, timeout=2) is None
        finally:
            listener.close()
            thread.join(3)


class TestSshProbe:

    def test_fingerprint_matches_the_format_used_for_trust_confirmation(self, app):
        transport = MagicMock()
        transport.get_remote_server_key.return_value.asbytes.return_value = b"host-key-bytes"
        expected = base64.b64encode(hashlib.sha256(b"host-key-bytes").digest()).decode().rstrip("=")

        with app.app_context(), patch("paramiko.Transport", return_value=transport):
            probe = identity_probes.ssh_host_key_fingerprint("10.0.0.5")
            deployment = ncpa.get_host_key_fingerprint("10.0.0.5", 22)

        assert probe == expected == deployment

    def test_unreachable_host_returns_none(self, app):
        with app.app_context(), patch("paramiko.Transport", side_effect=OSError("no route")):
            assert identity_probes.ssh_host_key_fingerprint("10.0.0.5") is None


class TestCollectIdentifiers:

    def test_probes_only_the_ports_that_are_open(self, app):
        with app.app_context(), \
             patch.object(identity_probes, "tls_certificate_fingerprint", return_value=CERT_1) as tls, \
             patch.object(identity_probes, "ssh_host_key_fingerprint", return_value=SSH_1) as ssh_probe:
            both = identity_probes.collect_identifiers("10.0.0.5", {"22": {}, "5693": {}})
            only_ssh = identity_probes.collect_identifiers("10.0.0.5", {"22": {}})
            nothing = identity_probes.collect_identifiers("10.0.0.5", {"80": {}})

        assert both == [(IdentifierKind.NCPA_CERT, CERT_1), (IdentifierKind.SSH_HOST_KEY, SSH_1)]
        assert only_ssh == [(IdentifierKind.SSH_HOST_KEY, SSH_1)]
        assert nothing == []
        assert tls.call_count == 1 and ssh_probe.call_count == 2

    def test_a_failed_probe_is_skipped(self, app):
        with app.app_context(), \
             patch.object(identity_probes, "tls_certificate_fingerprint", return_value=None), \
             patch.object(identity_probes, "ssh_host_key_fingerprint", return_value=SSH_1):
            assert identity_probes.collect_identifiers("10.0.0.5", {"22": {}, "5693": {}}) == [
                (IdentifierKind.SSH_HOST_KEY, SSH_1)]

    def test_scan_step_attaches_identifiers_to_every_host(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        db_session.session.commit()
        discovered = scan("10.0.0.5", tcp={22: "ssh"})

        with patch.object(create_host_cfg, "collect_identifiers", return_value=[(IdentifierKind.SSH_HOST_KEY, SSH_1)]) as probe:
            create_host_cfg._collect_identifiers(status, discovered, 60)

        assert discovered[NET]["10.0.0.5"]["data"]["identifiers"] == [(IdentifierKind.SSH_HOST_KEY, SSH_1)]
        probe.assert_called_once_with("10.0.0.5", {"22": {"service_name": "ssh", "identified_by": "FINGERPRINT"}})

    def test_identifiers_collected_in_a_scan_are_what_recognises_the_device_later(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        first = run_scan(db_session, status, scan("10.0.0.5", identifiers=[cert(CERT_1)]))[(NET, "10.0.0.5")]

        again = run_scan(db_session, status, scan("10.0.9.9", network="10.0.9.0/24", identifiers=[cert(CERT_1)]))[
            ("10.0.9.0/24", "10.0.9.9")]

        # Recognised across subnets where no MAC is visible.
        assert again.NetDiscoveryID == first.NetDiscoveryID
        assert again.Network == "10.0.9.0/24"


# ==========================================================
# RELOCATION JOB
# ==========================================================

def make_ncpa_device(db_session, admin_user, ip="10.0.0.5", state=HostStateType.DOWN, token="t" * 32,
                     cert_value=CERT_1, hostname="web.lan"):
    """A deployed NCPA device with a stored certificate and a Nagios host status."""
    device = make_linux_device(db_session, admin_user, ip=ip, mac=None, hostname=hostname,
                               identifiers=[cert(cert_value)])
    if token:
        deployment = db.session.scalar(sa.select(NCPADeployment).where(
            NCPADeployment.NetworkDiscoveryID == device.NetDiscoveryID))
        deployment.Token = token
    if state is not None:
        _make_host(db_session, device.Nagios_Host_Name, state=state)
    db_session.session.commit()
    return device


@pytest.fixture
def relocation(app):
    """Mock everything outside the database; yields the mocks."""
    with patched_config(app, NETWORKS=[NET]), \
         patch.object(ncpa_relocation, "discovery_is_running", return_value=False) as running, \
         patch.object(ncpa_relocation, "sweep_ncpa_port", return_value={"10.0.0.99"}) as sweep, \
         patch.object(ncpa_relocation, "tls_certificate_fingerprint", return_value=CERT_1) as probe, \
         patch.object(create_host_cfg, "regenerate_and_apply_config", return_value=(True, "applied")) as regenerate:
        yield MagicMock(running=running, sweep=sweep, probe=probe, regenerate=regenerate)


class TestFindDevicesToRelocate:

    def test_down_and_unreachable_ncpa_devices_are_candidates(self, db_session, admin_user):
        down = make_ncpa_device(db_session, admin_user, "10.0.0.1", HostStateType.DOWN, hostname="a.lan")
        unreachable = make_ncpa_device(db_session, admin_user, "10.0.0.2", HostStateType.UNREACHABLE,
                                       cert_value=CERT_2, hostname="b.lan")
        make_ncpa_device(db_session, admin_user, "10.0.0.3", HostStateType.UP, cert_value="c" * 64, hostname="c.lan")

        found = ncpa_relocation.find_devices_to_relocate()

        assert {d.NetDiscoveryID for d in found} == {down.NetDiscoveryID, unreachable.NetDiscoveryID}

    def test_device_without_a_token_or_certificate_is_not_a_candidate(self, db_session, admin_user):
        make_ncpa_device(db_session, admin_user, "10.0.0.1", token=None, hostname="a.lan")
        no_cert = make_linux_device(db_session, admin_user, ip="10.0.0.2", mac=MAC_2, hostname="b.lan")
        no_cert_deployment = db.session.scalar(sa.select(NCPADeployment).where(
            NCPADeployment.NetworkDiscoveryID == no_cert.NetDiscoveryID))
        no_cert_deployment.Token = "t" * 32
        _make_host(db_session, no_cert.Nagios_Host_Name, state=HostStateType.DOWN)
        db_session.session.commit()

        assert ncpa_relocation.find_devices_to_relocate() == []

    def test_retired_device_is_not_a_candidate(self, db_session, admin_user):
        device = make_ncpa_device(db_session, admin_user)
        device.Device_State = DeviceState.RETIRED
        db_session.session.commit()

        assert ncpa_relocation.find_devices_to_relocate() == []


class TestRelocate:

    def test_down_device_is_found_at_its_new_address(self, db_session, admin_user, relocation):
        device = make_ncpa_device(db_session, admin_user)
        name = device.Nagios_Host_Name

        moved = ncpa_relocation.relocate_ncpa_devices()

        assert moved == [device.NetDiscoveryID]
        assert device.IP_Address == "10.0.0.99"
        assert device.Nagios_Host_Name == name
        assert device.Device_State is DeviceState.ACTIVE
        rows = address_rows(device)
        assert [r.IP_Address for r in rows] == ["10.0.0.5", "10.0.0.99"]
        assert rows[1].Source is AddressSource.NCPA_RELOCATE
        assert [r.IP_Address for r in open_addresses(device)] == ["10.0.0.99"]
        relocation.regenerate.assert_called_once()

    def test_only_the_certificate_identifies_the_device(self, db_session, admin_user, relocation):
        device = make_ncpa_device(db_session, admin_user)
        relocation.probe.return_value = CERT_2  # a different machine answers on 5693

        moved = ncpa_relocation.relocate_ncpa_devices()

        assert moved == []
        assert device.IP_Address == "10.0.0.5"
        relocation.regenerate.assert_not_called()

    def test_responder_without_a_certificate_is_ignored(self, db_session, admin_user, relocation):
        device = make_ncpa_device(db_session, admin_user)
        relocation.probe.return_value = None

        assert ncpa_relocation.relocate_ncpa_devices() == []
        assert device.IP_Address == "10.0.0.5"

    def test_no_sweep_when_every_ncpa_device_is_up(self, db_session, admin_user, relocation):
        make_ncpa_device(db_session, admin_user, state=HostStateType.UP)

        assert ncpa_relocation.relocate_ncpa_devices() == []

        relocation.sweep.assert_not_called()

    def test_skipped_while_a_full_discovery_is_running(self, db_session, admin_user, relocation):
        device = make_ncpa_device(db_session, admin_user)
        relocation.running.return_value = True

        assert ncpa_relocation.relocate_ncpa_devices() == []

        relocation.sweep.assert_not_called()
        assert device.IP_Address == "10.0.0.5"

    def test_device_that_answers_at_its_own_address_is_not_moved(self, db_session, admin_user, relocation):
        device = make_ncpa_device(db_session, admin_user)
        relocation.sweep.return_value = {"10.0.0.5"}

        assert ncpa_relocation.relocate_ncpa_devices() == []
        assert len(address_rows(device)) == 1

    def test_another_device_at_the_new_address_loses_it(self, db_session, admin_user, relocation):
        device = make_ncpa_device(db_session, admin_user)
        squatter = make_linux_device(db_session, admin_user, ip="10.0.0.99", mac=MAC_2, hostname="other.lan")

        ncpa_relocation.relocate_ncpa_devices()

        assert device.IP_Address == "10.0.0.99"
        assert squatter.Device_State is DeviceState.ADDRESS_UNKNOWN

    def test_no_token_is_ever_sent_to_a_responder(self, db_session, admin_user, relocation):
        make_ncpa_device(db_session, admin_user)

        with patch.object(ncpa, "verify_ncpa_reachable") as reachable, \
             patch("requests.get") as http_get:
            ncpa_relocation.relocate_ncpa_devices()

        reachable.assert_not_called()
        http_get.assert_not_called()
        # The only thing sent to a responder is a TLS handshake for its certificate.
        relocation.probe.assert_called_once_with("10.0.0.99", "5693")

    def test_sweep_failure_on_one_network_does_not_abort(self, app, db_session, admin_user, relocation):
        device = make_ncpa_device(db_session, admin_user)
        relocation.sweep.side_effect = [RuntimeError("nmap failed"), {"10.0.1.7"}]

        with patched_config(app, NETWORKS=["10.0.9.0/24", "10.0.1.0/24"]):
            moved = ncpa_relocation.relocate_ncpa_devices()

        assert moved == [device.NetDiscoveryID]
        assert device.Network == "10.0.1.0/24"

    def test_relocated_device_keeps_matching_in_the_next_scan(self, db_session, admin_user, relocation):
        device = make_ncpa_device(db_session, admin_user)
        ncpa_relocation.relocate_ncpa_devices()

        status = make_status(db_session, admin_user)
        again = run_scan(db_session, status, scan("10.0.0.99", identifiers=[cert(CERT_1)]))[(NET, "10.0.0.99")]

        assert again.NetDiscoveryID == device.NetDiscoveryID
        assert len(address_rows(device)) == 2


class TestSweep:

    def test_parses_only_hosts_with_the_port_open(self, app):
        from xml.etree import ElementTree as ET

        xml = ET.fromstring("""
        <nmaprun>
          <host><status state="up"/><address addr="10.0.0.9" addrtype="ipv4"/>
            <ports><port protocol="tcp" portid="5693"><state state="open"/></port></ports></host>
          <host><status state="up"/><address addr="10.0.0.10" addrtype="ipv4"/>
            <ports><port protocol="tcp" portid="5693"><state state="closed"/></port></ports></host>
          <host><status state="down"/><address addr="10.0.0.11" addrtype="ipv4"/>
            <ports><port protocol="tcp" portid="5693"><state state="open"/></port></ports></host>
        </nmaprun>""")
        nmap = MagicMock()
        nmap.scan_command.return_value = xml

        with app.app_context(), patch.object(ncpa_relocation.nmap3, "Nmap", return_value=nmap):
            assert ncpa_relocation.sweep_ncpa_port(NET) == {"10.0.0.9"}

        target, flags, extra = nmap.scan_command.call_args.args
        assert target == NET
        assert "-p 5693" in flags and "-sV" not in flags and "-O" not in flags  # no service/OS detection
        assert extra == "--open"


# ==========================================================
# SCHEDULER
# ==========================================================

class TestSchedulerJob:

    def test_job_is_registered_with_the_configured_interval(self, app):
        from app import scheduler

        fake = MagicMock()
        # app.testing / app.debug are properties, so set and restore them by hand.
        was_testing, was_debug = app.testing, app.debug
        app.testing, app.debug = False, False
        try:
            with patch.object(scheduler, "_scheduler", None), \
                 patch.object(scheduler, "BackgroundScheduler", return_value=fake), \
                 patch.object(scheduler.atexit, "register"):
                scheduler.init_scheduler()
        finally:
            app.testing, app.debug = was_testing, was_debug

        jobs = {call.kwargs["id"]: call for call in fake.add_job.call_args_list}
        assert jobs["ncpa_relocation"].kwargs["minutes"] == app.config["NCPA_RELOCATE_MINUTES"]
        assert jobs["ncpa_relocation"].kwargs["max_instances"] == 1

    def test_a_failing_job_is_contained(self, app):
        from app import scheduler

        with patch.object(ncpa_relocation, "relocate_ncpa_devices", side_effect=RuntimeError("boom")):
            scheduler._relocate_ncpa_devices()  # must not raise

    def test_job_runs_the_relocation(self, app):
        from app import scheduler

        with patch.object(ncpa_relocation, "relocate_ncpa_devices", return_value=[]) as run:
            scheduler._relocate_ncpa_devices()

        run.assert_called_once()


# ==========================================================
# DISK NODE DISCOVERY (item C)
# ==========================================================

class TestDiscoverDiskNodes:

    LISTING = {"logical": {
        "|": {"fstype": "ext4"},
        "|boot|efi": {"fstype": "vfat"},
        "|run": {"fstype": "tmpfs"},
        "|mnt|gone": {"fstype": "ext4"},
    }}

    def fake_get(self, missing=()):
        def get(ip, token, path, timeout=5):
            if path == "disk/logical":
                return self.LISTING
            node = path.split("/")[2]
            return None if node in missing else {"percent": 1}
        return get

    def test_keeps_mounted_real_filesystems_that_answer(self, app):
        with app.app_context(), patch.object(ncpa, "_ncpa_get", self.fake_get(missing={"|mnt|gone"})):
            assert ncpa.discover_disk_nodes("10.0.0.5", "tok") == ["|", "|boot|efi"]

    def test_unreachable_agent_yields_nothing(self, app):
        with app.app_context(), patch.object(ncpa, "_ncpa_get", return_value=None):
            assert ncpa.discover_disk_nodes("10.0.0.5", "tok") == []

    def test_refresh_replaces_stored_nodes(self, app, db_session, admin_user):
        device = make_linux_device(db_session, admin_user)
        deployment = db.session.scalar(sa.select(NCPADeployment).where(
            NCPADeployment.NetworkDiscoveryID == device.NetDiscoveryID))
        deployment.Token = "t" * 32
        db.session.add(NCPADevicePartition(Name="vda1", NCPADeployID=deployment.NCPADeployID))
        db.session.commit()

        with patch.object(ncpa, "_ncpa_get", self.fake_get(missing={"|mnt|gone"})):
            names = ncpa.refresh_ncpa_partitions(deployment, device.IP_Address)

        stored = db.session.scalars(sa.select(NCPADevicePartition.Name).where(
            NCPADevicePartition.NCPADeployID == deployment.NCPADeployID)).all()
        assert names == stored == ["|", "|boot|efi"]
