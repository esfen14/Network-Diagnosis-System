"""
tests/test_ncpa.py — Tests for NCPA deployment endpoints.

Endpoints tested (all under /api/system/deployment/ncpa/):
  GET  /devices
  GET  /<device_id>/fingerprint
  POST /<device_id>/confirm-trust
  POST /start
  POST /stop
  GET  /status
  GET  /devices/trusted
"""
import pytest
from unittest.mock import patch, MagicMock

from app.system_models import (
    NetworkDiscovery,
    NetworkDiscoveryStatus,
    DiscoveryStatus,
    ActivityLog,
    SSHCredentials,
    NCPADeployment,
    AgentStatus,
)


# ─── Seeding helper ───────────────────────────────────────────────────────────

def _make_ncpa_device(db_session, admin_user, trusted=False, ncpa_eligible=True):
    """Create a NetworkDiscovery device with an ActivityLog and SSHCredentials."""
    log = ActivityLog(Action_Type="test", UserID=admin_user.UserID)
    db_session.session.add(log)
    db_session.session.flush()

    ds = NetworkDiscoveryStatus(
        Status=DiscoveryStatus.SUCCESS,
        Progress=100,
        Message="Done",
        LogID=log.LogID,
    )
    db_session.session.add(ds)
    db_session.session.flush()

    device = NetworkDiscovery(
        Hostname="ncpa-host",
        IP_Address="10.99.0.1",
        Network="10.99.0.0",
        NCPA_Eligible=ncpa_eligible,
        DiscoveryStatusID=ds.DiscoveryStatusID,
    )
    db_session.session.add(device)
    db_session.session.flush()

    creds = SSHCredentials(
        SSH_Port=22,
        Key_Installed=False,
        Key_Fingerprint="abc:123" if trusted else None,
        NetworkDiscoveryID=device.NetDiscoveryID,
    )
    db_session.session.add(creds)
    db_session.session.commit()
    return device, creds


# ─── GET /api/system/deployment/ncpa/devices ──────────────────────────────────

class TestNcpaEligibleDevices:
    def test_ncpa_eligible_devices_requires_login(self, client, db_session):
        resp = client.get("/api/system/deployment/ncpa/devices")
        assert resp.status_code in (401, 302)

    def test_ncpa_eligible_devices_empty(self, logged_in_client, db_session, admin_user):
        # No devices seeded — should return an empty list
        resp = logged_in_client.get("/api/system/deployment/ncpa/devices")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["devices"] == []

    def test_ncpa_eligible_devices_returns_eligible(self, logged_in_client, db_session, admin_user):
        eligible, _ = _make_ncpa_device(db_session, admin_user, ncpa_eligible=True)
        non_eligible, _ = _make_ncpa_device(db_session, admin_user, ncpa_eligible=False)

        resp = logged_in_client.get("/api/system/deployment/ncpa/devices")
        assert resp.status_code == 200
        data = resp.get_json()
        device_ids = [d["device_id"] for d in data["devices"]]
        assert eligible.NetDiscoveryID in device_ids
        assert non_eligible.NetDiscoveryID not in device_ids

    def test_ncpa_eligible_devices_requires_permission(self, limited_client, db_session, admin_user):
        resp = limited_client.get("/api/system/deployment/ncpa/devices")
        assert resp.status_code == 403


# ─── GET /api/system/deployment/ncpa/<device_id>/fingerprint ─────────────────

class TestGetFingerprint:
    def test_get_fingerprint_device_not_found(self, logged_in_client, db_session, admin_user):
        resp = logged_in_client.get("/api/system/deployment/ncpa/99999/fingerprint")
        assert resp.status_code == 404

    def test_get_fingerprint_unreachable_device(self, logged_in_client, db_session, admin_user):
        device, _ = _make_ncpa_device(db_session, admin_user)

        with patch("app.api.system.ncpa_deployment.get_host_key_fingerprint") as mock_fp:
            mock_fp.side_effect = Exception("Connection refused")
            resp = logged_in_client.get(
                f"/api/system/deployment/ncpa/{device.NetDiscoveryID}/fingerprint"
            )
        assert resp.status_code == 502


# ─── POST /api/system/deployment/ncpa/<device_id>/confirm-trust ───────────────

class TestConfirmTrust:
    def test_confirm_trust_device_not_found(self, logged_in_client, db_session, admin_user):
        with patch("app.api.system.ncpa_deployment.get_host_key_fingerprint") as mock_fp:
            mock_fp.return_value = "fp:123"
            resp = logged_in_client.post(
                "/api/system/deployment/ncpa/99999/confirm-trust"
            )
        assert resp.status_code == 404

    def test_confirm_trust_no_ssh_creds(self, logged_in_client, db_session, admin_user):
        """Device exists but has no SSHCredentials row — should return 404."""
        log = ActivityLog(Action_Type="test", UserID=admin_user.UserID)
        db_session.session.add(log)
        db_session.session.flush()

        ds = NetworkDiscoveryStatus(
            Status=DiscoveryStatus.SUCCESS,
            Progress=100,
            Message="Done",
            LogID=log.LogID,
        )
        db_session.session.add(ds)
        db_session.session.flush()

        device = NetworkDiscovery(
            Hostname="no-creds-host",
            IP_Address="10.99.0.2",
            Network="10.99.0.0",
            NCPA_Eligible=True,
            DiscoveryStatusID=ds.DiscoveryStatusID,
        )
        db_session.session.add(device)
        db_session.session.commit()

        with patch("app.api.system.ncpa_deployment.get_host_key_fingerprint") as mock_fp:
            mock_fp.return_value = "fp:123"
            resp = logged_in_client.post(
                f"/api/system/deployment/ncpa/{device.NetDiscoveryID}/confirm-trust"
            )
        assert resp.status_code == 404

    def test_confirm_trust_success(self, logged_in_client, db_session, admin_user):
        device, creds = _make_ncpa_device(db_session, admin_user, trusted=False)
        assert creds.Key_Fingerprint is None

        with patch("app.api.system.ncpa_deployment.get_host_key_fingerprint") as mock_fp:
            mock_fp.return_value = "fp:123"
            resp = logged_in_client.post(
                f"/api/system/deployment/ncpa/{device.NetDiscoveryID}/confirm-trust"
            )

        assert resp.status_code == 200
        db_session.session.refresh(creds)
        assert creds.Key_Fingerprint == "fp:123"


# ─── POST /api/system/deployment/ncpa/start ───────────────────────────────────

class TestDeployNcpaStart:
    def test_deploy_ncpa_requires_login(self, client, db_session):
        resp = client.post(
            "/api/system/deployment/ncpa/start",
            json={"devices": []},
        )
        assert resp.status_code in (401, 302)

    def test_deploy_ncpa_no_devices_provided(self, logged_in_client, db_session, admin_user):
        resp = logged_in_client.post(
            "/api/system/deployment/ncpa/start",
            json={"devices": []},
        )
        assert resp.status_code == 400

    def test_deploy_ncpa_already_running(self, logged_in_client, db_session, admin_user):
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True

        with patch("app.api.system.ncpa_deployment.deploy_ncpa_thread", mock_thread):
            resp = logged_in_client.post(
                "/api/system/deployment/ncpa/start",
                json={"devices": [{"device_id": 1, "username": "u", "password": "p"}]},
            )
        assert resp.status_code == 400

    def test_deploy_ncpa_device_not_found_rejected(self, logged_in_client, db_session, admin_user):
        """Device 99999 doesn't exist — should be in the rejected list; response is 202."""
        with patch("app.api.system.ncpa_deployment.deploy_ncpa_thread", None), \
             patch("app.api.system.ncpa_deployment.threading.Thread") as mock_thread_cls:
            mock_thread_instance = MagicMock()
            mock_thread_cls.return_value = mock_thread_instance

            resp = logged_in_client.post(
                "/api/system/deployment/ncpa/start",
                json={"devices": [{"device_id": 99999, "username": "u", "password": "p"}]},
            )

        assert resp.status_code == 202
        data = resp.get_json()
        assert len(data["rejected"]) > 0
        rejected_ids = [r["device_id"] for r in data["rejected"]]
        assert 99999 in rejected_ids

    def test_deploy_ncpa_untrusted_device_rejected(self, logged_in_client, db_session, admin_user):
        """Device exists but has no Key_Fingerprint (not trust-confirmed) — should be rejected."""
        device, creds = _make_ncpa_device(db_session, admin_user, trusted=False)
        assert creds.Key_Fingerprint is None

        with patch("app.api.system.ncpa_deployment.deploy_ncpa_thread", None), \
             patch("app.api.system.ncpa_deployment.threading.Thread") as mock_thread_cls:
            mock_thread_instance = MagicMock()
            mock_thread_cls.return_value = mock_thread_instance

            resp = logged_in_client.post(
                "/api/system/deployment/ncpa/start",
                json={"devices": [
                    {"device_id": device.NetDiscoveryID, "username": "u", "password": "p"}
                ]},
            )

        assert resp.status_code == 202
        data = resp.get_json()
        assert len(data["rejected"]) > 0
        rejected_ids = [r["device_id"] for r in data["rejected"]]
        assert device.NetDiscoveryID in rejected_ids


# ─── POST /api/system/deployment/ncpa/stop ────────────────────────────────────

class TestDeployNcpaStop:
    def test_stop_ncpa_not_running(self, logged_in_client, db_session, admin_user):
        """Stopping when no deployment is running should return 400."""
        with patch("app.api.system.ncpa_deployment.deploy_ncpa_thread", None):
            resp = logged_in_client.post("/api/system/deployment/ncpa/stop")
        assert resp.status_code == 400


# ─── GET /api/system/deployment/ncpa/status ───────────────────────────────────

class TestDeployNcpaStatus:
    def test_ncpa_status_no_records(self, logged_in_client, db_session, admin_user):
        """When no deployment has occurred, should return 200 with a message."""
        resp = logged_in_client.get("/api/system/deployment/ncpa/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "message" in data


# ─── GET /api/system/deployment/ncpa/devices/trusted ─────────────────────────

class TestTrustedDevices:
    def test_trusted_devices_empty(self, logged_in_client, db_session, admin_user):
        """When no devices are trusted (no NCPADeployment rows with PENDING_NCPA), return empty list."""
        resp = logged_in_client.get("/api/system/deployment/ncpa/devices/trusted")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["devices"] == []
