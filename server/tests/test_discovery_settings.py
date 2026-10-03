"""
Tests for the editable Network Discovery settings: the validators in
app/network_discovery/discovery_settings.py, the GET/PUT
/api/system/discovery-settings routes, and that the scan reads saved
values instead of config.py.

nmap is never run — the scan functions are exercised with nmap3 mocked.
"""
from unittest.mock import patch, MagicMock
import xml.etree.ElementTree as ET

import pytest

from app.system_models import DiscoverySettings, ConfigurationChanges, Permission, RolePermission
from app.network_discovery.discovery_settings import (
    DiscoverySettingsError,
    get_discovery_setting,
    validate_networks,
    validate_ports,
    validate_service_overrides,
)


VALID_PAYLOAD = {
    "networks": ["10.0.5.0/24"],
    "tcpPorts": [22, "80-443"],
    "udpPorts": [161],
    "tcpServiceOverrides": {"5693": "ncpa"},
    "udpServiceOverrides": {"161": "snmp"},
}


def grant(db_session, role, permission_name):
    permission = db_session.session.query(Permission).filter_by(Name=permission_name).one()
    db_session.session.add(RolePermission(RoleID=role.RoleID, PermissionID=permission.PermissionID))
    db_session.session.commit()


def current(client):
    resp = client.get("/api/system/discovery-settings")
    assert resp.status_code == 200
    return resp.get_json()["data"]


def save(client, **changes):
    payload = dict(VALID_PAYLOAD)
    payload["version"] = current(client)["settings"]["version"]
    payload.update(changes)
    return client.put("/api/system/discovery-settings", json=payload)


# ==========================================================
# VALIDATORS
# ==========================================================

class TestValidateNetworks:
    def test_normalizes_host_bits(self):
        assert validate_networks(["192.168.1.5/24"]) == ["192.168.1.0/24"]

    def test_single_address_allowed(self):
        assert validate_networks(["192.168.1.5"]) == ["192.168.1.5/32"]

    @pytest.mark.parametrize("value", [
        "127.0.0.0/8",          # loopback
        "127.0.0.1",
        "10.0.0.0/8",           # larger than /16
        "224.0.0.0/24",         # multicast
        "0.0.0.0/32",           # unspecified
        "fe80::/64",            # IPv6
        "not-a-network",
        "10.0.0.0/24 -p 1-65535",
        "10.0.0.0/24; rm -rf /",
    ])
    def test_rejects_unsafe_or_invalid(self, value):
        with pytest.raises(DiscoverySettingsError):
            validate_networks([value])

    def test_rejects_empty_and_duplicates(self):
        with pytest.raises(DiscoverySettingsError):
            validate_networks([])
        with pytest.raises(DiscoverySettingsError):
            validate_networks(["10.0.0.0/24", "10.0.0.7/24"])

    def test_rejects_non_list(self):
        with pytest.raises(DiscoverySettingsError):
            validate_networks("10.0.0.0/24")


class TestValidatePorts:
    def test_normalizes_ports_and_ranges(self):
        assert validate_ports([22, "80", " 1-1024 "], "TCP") == [22, 80, "1-1024"]

    def test_empty_list_allowed(self):
        assert validate_ports([], "UDP") == []

    @pytest.mark.parametrize("value", [
        0, 65536, -1, True, 1.5, "abc", "100-10", "1-70000",
        "80 --script=evil", "80,443", "22;ls",
    ])
    def test_rejects_invalid(self, value):
        with pytest.raises(DiscoverySettingsError):
            validate_ports([value], "TCP")

    def test_rejects_duplicates(self):
        with pytest.raises(DiscoverySettingsError):
            validate_ports([22, "22"], "TCP")


class TestValidateServiceOverrides:
    def test_normalizes_keys_to_strings(self):
        assert validate_service_overrides({22: "ssh", "161": "snmp"}, "UDP") == {"22": "ssh", "161": "snmp"}

    @pytest.mark.parametrize("overrides", [
        {"0": "ssh"},
        {"abc": "ssh"},
        {"22": "SSH"},
        {"22": "ssh server"},
        {"22": "ssh\ncheck_command evil"},
        {"22": ""},
        {"22": 5},
    ])
    def test_rejects_invalid(self, overrides):
        with pytest.raises(DiscoverySettingsError):
            validate_service_overrides(overrides, "TCP")

    def test_rejects_non_dict(self):
        with pytest.raises(DiscoverySettingsError):
            validate_service_overrides([["22", "ssh"]], "TCP")


# ==========================================================
# ROUTES
# ==========================================================

class TestGetDiscoverySettings:
    def test_requires_login(self, client, db_session):
        resp = client.get("/api/system/discovery-settings")
        assert resp.status_code in (401, 302)

    def test_requires_discovery_permission(self, limited_client, db_session):
        resp = limited_client.get("/api/system/discovery-settings")
        assert resp.status_code == 403

    def test_system_permission_alone_is_not_enough(self, limited_client, db_session, regular_role):
        grant(db_session, regular_role, "settings.system")

        resp = limited_client.get("/api/system/discovery-settings")

        assert resp.status_code == 403

    def test_discovery_permission_grants_access(self, limited_client, db_session, regular_role):
        grant(db_session, regular_role, "settings.discovery")

        assert limited_client.get("/api/system/discovery-settings").status_code == 200
        assert save(limited_client).status_code == 200

    def test_defaults_come_from_config(self, logged_in_client, db_session, app):
        data = current(logged_in_client)

        assert data["settings"]["networks"] == app.config["NETWORKS"]
        assert data["settings"]["tcpPorts"] == app.config["TCP_PORTS"]
        assert data["settings"]["udpServiceOverrides"] == app.config["UDP_SERVICE_OVERRIDES"]
        assert data["settings"]["version"] == 0
        assert data["defaults"]["networks"] == app.config["NETWORKS"]
        assert data["scanRunning"] is False


class TestUpdateDiscoverySettings:
    def test_saves_and_returns_new_values(self, logged_in_client, db_session):
        resp = save(logged_in_client)

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["networks"] == ["10.0.5.0/24"]
        assert data["tcpPorts"] == [22, "80-443"]
        assert data["version"] == 1

        row = db_session.session.get(DiscoverySettings, 1)
        assert row.Networks == ["10.0.5.0/24"]
        assert row.TCP_Service_Overrides == {"5693": "ncpa"}

    def test_invalid_value_rejected_and_nothing_saved(self, logged_in_client, db_session):
        resp = save(logged_in_client, networks=["127.0.0.1"])

        assert resp.status_code == 400
        assert "loopback" in resp.get_json()["message"]
        assert db_session.session.get(DiscoverySettings, 1) is None

    def test_missing_field(self, logged_in_client, db_session):
        payload = {"version": 0, "networks": ["10.0.5.0/24"]}
        resp = logged_in_client.put("/api/system/discovery-settings", json=payload)
        assert resp.status_code == 400
        assert "Missing required field" in resp.get_json()["message"]

    def test_stale_version_rejected(self, logged_in_client, db_session):
        assert save(logged_in_client).status_code == 200

        payload = dict(VALID_PAYLOAD, version=0, networks=["10.0.6.0/24"])
        resp = logged_in_client.put("/api/system/discovery-settings", json=payload)

        assert resp.status_code == 409
        assert db_session.session.get(DiscoverySettings, 1).Networks == ["10.0.5.0/24"]

    def test_rejected_while_scan_running(self, logged_in_client, db_session):
        with patch("app.api.system.discovery_settings.is_discovery_running", return_value=True):
            resp = save(logged_in_client)

        assert resp.status_code == 409
        assert db_session.session.get(DiscoverySettings, 1) is None

    def test_requires_discovery_permission(self, limited_client, db_session):
        payload = dict(VALID_PAYLOAD, version=0)
        resp = limited_client.put("/api/system/discovery-settings", json=payload)
        assert resp.status_code == 403

    def test_changes_are_logged(self, logged_in_client, db_session):
        save(logged_in_client)

        logged = {c.Parameter_Name for c in db_session.session.query(ConfigurationChanges).all()}
        assert "Networks" in logged
        assert "TCP_Ports" in logged

    def test_long_values_are_shortened_in_log(self, logged_in_client, db_session):
        many_ports = list(range(1000, 1100))
        save(logged_in_client, tcpPorts=many_ports)

        change = db_session.session.query(ConfigurationChanges).filter_by(Parameter_Name="TCP_Ports").one()
        assert len(change.New_Value) <= 100
        assert change.New_Value.endswith("...")


# ==========================================================
# SCAN USES SAVED VALUES
# ==========================================================

class TestScanReadsSavedSettings:
    def test_falls_back_to_config(self, app, db_session):
        with app.app_context():
            assert get_discovery_setting("NETWORKS") == app.config["NETWORKS"]

    def test_saved_value_wins(self, app, db_session):
        db_session.session.add(DiscoverySettings(Id=1, Networks=["10.9.9.0/24"]))
        db_session.session.commit()

        assert get_discovery_setting("NETWORKS") == ["10.9.9.0/24"]
        # Columns never saved still fall back to config.py.
        assert get_discovery_setting("UDP_PORTS") == app.config["UDP_PORTS"]

    def test_tcp_scan_uses_saved_ports(self, app, db_session):
        from app.network_discovery import network_discovery

        db_session.session.add(DiscoverySettings(Id=1, TCP_Ports=[22, "8000-8100"]))
        db_session.session.commit()

        fake_nmap = MagicMock()
        fake_nmap.scan_command.return_value = ET.fromstring("<nmaprun></nmaprun>")
        with patch.object(network_discovery.nmap3, "Nmap", return_value=fake_nmap):
            network_discovery._discover_host_tcp_port("10.0.5.1")

        args = fake_nmap.scan_command.call_args[0]
        assert args[2] == "--open -p 22,8000-8100"
