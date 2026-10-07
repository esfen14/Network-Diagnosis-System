"""
tests/unit/test_device_identity_routes.py — Phase 4 routes of
"spec files/DHCP_Device_Identity_Plan.md" (section 11), in
app/api/system/device_identity.py:

  GET  /api/system/hosts/<id>/addresses
  GET  /api/system/hosts/<id>/identifiers
  PUT  /api/system/hosts/<id>
  POST /api/system/hosts/<id>/merge
  POST /api/system/hosts/<id>/retire
  PUT  /api/system/hosts/<id>/ports/<proto>/<port>
  GET  /api/system/discover/review
  POST /api/system/discover/review/<id>/resolve

Regenerating the Nagios config is mocked: no Nagios runs.
"""
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from app import db
from app.plugin_models import Plugin, PluginConfiguration, PluginSource, PluginStatus, PluginType
from app.system_models import (
    ActivityLog,
    AddressingMode,
    DeviceAddressHistory,
    DeviceIdentifier,
    DeviceReviewItem,
    DeviceState,
    IdentifierKind,
    NCPADeployment,
    Open_TCP_Services,
    PortSource,
    PortState,
    ReviewKind,
    ServiceIdentification,
)
from tests.support.identity_helpers import (
    MAC_1, MAC_2, NET, SSH_1, SSH_2, all_devices, identifier_values, make_status, open_addresses,
    review_items, run_scan, scan, ssh,
)

# Ports are monitored only when their plugin is enabled in Plugin Manager.
pytestmark = pytest.mark.usefixtures("monitoring_plugins")

BASE = "/api/system"


@pytest.fixture(autouse=True)
def regenerate():
    """Every route that touches the Nagios config calls the reconciler; no Nagios here."""
    with patch("app.api.system.device_identity.reconcile_plugin_monitoring",
               return_value={"success": True, "changed": True, "message": "applied"}) as mock:
        yield mock


@pytest.fixture
def status(db_session, admin_user):
    return make_status(db_session, admin_user)


def new_device(db_session, status, ip="10.0.0.5", **kwargs):
    return run_scan(db_session, status, scan(ip, **kwargs))[(NET, ip)]


def log_actions():
    return [row.Action_Type for row in db.session.scalars(sa.select(ActivityLog).order_by(ActivityLog.LogID)).all()]


# ==========================================================
# AUTH
# ==========================================================

class TestAuth:

    @pytest.mark.parametrize("method, path", [
        ("get", "/hosts/1/addresses"),
        ("get", "/hosts/1/identifiers"),
        ("put", "/hosts/1"),
        ("post", "/hosts/1/merge"),
        ("post", "/hosts/1/retire"),
        ("post", "/hosts/1/pause"),
        ("post", "/hosts/1/resume"),
        ("put", "/hosts/1/ports/tcp/22"),
        ("get", "/discover/review"),
        ("post", "/discover/review/1/resolve"),
    ])
    def test_requires_login(self, client, db_session, method, path):
        resp = getattr(client, method)(BASE + path, json={})
        assert resp.status_code in (401, 302)

    @pytest.mark.parametrize("method, path", [
        ("get", "/hosts/1/addresses"),
        ("get", "/hosts/1/identifiers"),
        ("put", "/hosts/1"),
        ("post", "/hosts/1/merge"),
        ("post", "/hosts/1/retire"),
        ("post", "/hosts/1/pause"),
        ("post", "/hosts/1/resume"),
        ("put", "/hosts/1/ports/tcp/22"),
        ("get", "/discover/review"),
        ("post", "/discover/review/1/resolve"),
    ])
    def test_requires_permission(self, limited_client, db_session, method, path):
        resp = getattr(limited_client, method)(BASE + path, json={"state": "MONITORED"})
        assert resp.status_code == 403

    def test_read_permission_alone_cannot_edit(self, client, db_session, status, seeded_permissions):
        from app.system_models import Role, RolePermission, User, UserStatus
        role = Role(Name="Reader", Is_Active=True, Description="r")
        db_session.session.add(role)
        db_session.session.flush()
        db_session.session.add(RolePermission(
            RoleID=role.RoleID, PermissionID=seeded_permissions["system.hosts"].PermissionID))
        user = User(First_Name="R", Last_Name="R", Email="reader@example.com", Status=UserStatus.ACTIVE,
                    RoleID=role.RoleID)
        user.set_password("ReaderPass1!")
        db_session.session.add(user)
        db_session.session.commit()
        device = new_device(db_session, status)
        client.post("/api/user/login", json={"email": "reader@example.com", "password": "ReaderPass1!"})

        assert client.get(f"{BASE}/hosts/{device.NetDiscoveryID}/addresses").status_code == 200
        assert client.put(f"{BASE}/hosts/{device.NetDiscoveryID}", json={"display_name": "x"}).status_code == 403
        assert client.post(f"{BASE}/hosts/{device.NetDiscoveryID}/retire").status_code == 403
        assert client.post(f"{BASE}/hosts/{device.NetDiscoveryID}/pause").status_code == 403


# ==========================================================
# ADDRESSES AND IDENTIFIERS
# ==========================================================

class TestAddresses:

    def test_unknown_device_is_404(self, logged_in_client, db_session):
        assert logged_in_client.get(BASE + "/hosts/999/addresses").status_code == 404

    def test_lists_history_newest_first_with_the_current_row_marked(self, logged_in_client, db_session, status):
        device = new_device(db_session, status, mac=MAC_1)
        new_device(db_session, status, ip="10.0.0.9", mac=MAC_1)

        resp = logged_in_client.get(f"{BASE}/hosts/{device.NetDiscoveryID}/addresses")

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["device"]["ip_address"] == "10.0.0.9"
        rows = data["addresses"]
        assert [r["ip_address"] for r in rows] == ["10.0.0.9", "10.0.0.5"]
        assert [r["current"] for r in rows] == [True, False]
        assert rows[0]["source"] == "SCAN" and rows[1]["closed_at"] is not None


class TestIdentifiers:

    def test_unverified_device_gets_a_recommendation(self, logged_in_client, db_session, status):
        device = new_device(db_session, status)

        data = logged_in_client.get(f"{BASE}/hosts/{device.NetDiscoveryID}/identifiers").get_json()["data"]

        assert data["confidence"] == "UNVERIFIED"
        assert data["identifiers"] == []
        assert "DHCP reservation" in data["recommendation"]

    def test_verified_device_lists_its_evidence(self, logged_in_client, db_session, status):
        device = new_device(db_session, status, mac=MAC_1, identifiers=[ssh(SSH_1)])

        data = logged_in_client.get(f"{BASE}/hosts/{device.NetDiscoveryID}/identifiers").get_json()["data"]

        assert data["confidence"] == "VERIFIED"
        assert data["recommendation"] is None
        assert {(i["kind"], i["value"], i["strong"]) for i in data["identifiers"]} == {
            ("MAC", MAC_1, True), ("SSH_HOST_KEY", SSH_1, True)}
        assert data["mac_address"] == MAC_1

    def test_machine_id_is_masked(self, logged_in_client, db_session, status):
        device = new_device(db_session, status, identifiers=[(IdentifierKind.MACHINE_ID, "0123456789abcdef0123456789abcdef")])

        data = logged_in_client.get(f"{BASE}/hosts/{device.NetDiscoveryID}/identifiers").get_json()["data"]

        values = [i["value"] for i in data["identifiers"] if i["kind"] == "MACHINE_ID"]
        assert values == ["01234567..."]

    def test_unknown_device_is_404(self, logged_in_client, db_session):
        assert logged_in_client.get(BASE + "/hosts/999/identifiers").status_code == 404


# ==========================================================
# EDIT
# ==========================================================

class TestEdit:

    def test_sets_display_name_and_addressing_without_touching_nagios(self, logged_in_client, db_session, status, regenerate):
        device = new_device(db_session, status, hostname="printer.lan")
        name = device.Nagios_Host_Name

        resp = logged_in_client.put(f"{BASE}/hosts/{device.NetDiscoveryID}",
                                    json={"display_name": "  Front desk printer ", "addressing": "static"})

        assert resp.status_code == 200
        db_session.session.refresh(device)
        assert device.Display_Name == "Front desk printer"
        assert device.Addressing is AddressingMode.STATIC
        assert device.Nagios_Host_Name == name
        regenerate.assert_not_called()
        assert log_actions()[-1] == f"Edited device {name}"

    def test_display_name_can_be_cleared(self, logged_in_client, db_session, status):
        device = new_device(db_session, status)
        logged_in_client.put(f"{BASE}/hosts/{device.NetDiscoveryID}", json={"display_name": "x"})

        logged_in_client.put(f"{BASE}/hosts/{device.NetDiscoveryID}", json={"display_name": None})

        db_session.session.refresh(device)
        assert device.Display_Name is None

    def test_fields_not_sent_are_left_alone(self, logged_in_client, db_session, status):
        device = new_device(db_session, status)
        logged_in_client.put(f"{BASE}/hosts/{device.NetDiscoveryID}", json={"display_name": "keep"})

        logged_in_client.put(f"{BASE}/hosts/{device.NetDiscoveryID}", json={"addressing": "DHCP"})

        db_session.session.refresh(device)
        assert device.Display_Name == "keep" and device.Addressing is AddressingMode.DHCP

    @pytest.mark.parametrize("body", [
        {"addressing": "sometimes"},
        {"display_name": "x" * 101},
        {"display_name": 5},
        {},
    ])
    def test_invalid_bodies_are_rejected(self, logged_in_client, db_session, status, body):
        device = new_device(db_session, status)

        resp = logged_in_client.put(f"{BASE}/hosts/{device.NetDiscoveryID}", json=body)

        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_unknown_device_is_404(self, logged_in_client, db_session):
        assert logged_in_client.put(BASE + "/hosts/999", json={"display_name": "x"}).status_code == 404


# ==========================================================
# RETIRE
# ==========================================================

class TestRetire:

    def test_retires_closes_the_address_and_regenerates_the_config(self, logged_in_client, db_session, status, regenerate):
        device = new_device(db_session, status, mac=MAC_1)

        resp = logged_in_client.post(f"{BASE}/hosts/{device.NetDiscoveryID}/retire")

        assert resp.status_code == 200
        assert resp.get_json()["data"] == {"config_applied": True, "config_ok": True, "config_message": "applied"}
        db_session.session.refresh(device)
        assert device.Device_State is DeviceState.RETIRED
        assert open_addresses(device) == []
        assert identifier_values(device, IdentifierKind.MAC) == {MAC_1}  # kept for recognition later
        regenerate.assert_called_once()
        assert log_actions()[-1] == f"Retired device {device.Nagios_Host_Name}"

    def test_cannot_retire_twice(self, logged_in_client, db_session, status):
        device = new_device(db_session, status)
        logged_in_client.post(f"{BASE}/hosts/{device.NetDiscoveryID}/retire")

        assert logged_in_client.post(f"{BASE}/hosts/{device.NetDiscoveryID}/retire").status_code == 400

    def test_unknown_device_is_404(self, logged_in_client, db_session):
        assert logged_in_client.post(BASE + "/hosts/999/retire").status_code == 404

    def test_a_config_failure_is_reported_but_the_change_is_kept(self, logged_in_client, db_session, status, regenerate):
        device = new_device(db_session, status)
        regenerate.side_effect = RuntimeError("nagios exploded")

        resp = logged_in_client.post(f"{BASE}/hosts/{device.NetDiscoveryID}/retire")

        assert resp.status_code == 200
        assert resp.get_json()["data"]["config_applied"] is False
        assert resp.get_json()["data"]["config_ok"] is False         # saved, but Nagios was not updated
        db_session.session.refresh(device)
        assert device.Device_State is DeviceState.RETIRED

    def test_nothing_to_reload_is_ok_but_not_applied(self, logged_in_client, db_session, status, regenerate):
        device = new_device(db_session, status)
        regenerate.return_value = {"success": True, "changed": False, "message": "Host configuration unchanged; Nagios was not reloaded."}

        data = logged_in_client.post(f"{BASE}/hosts/{device.NetDiscoveryID}/retire").get_json()["data"]

        assert (data["config_applied"], data["config_ok"]) == (False, True)

    def test_a_config_nagios_rejects_is_not_ok(self, logged_in_client, db_session, status, regenerate):
        device = new_device(db_session, status)
        regenerate.return_value = {"success": False, "changed": False, "message": "Config failed to validate: bad directive"}

        data = logged_in_client.post(f"{BASE}/hosts/{device.NetDiscoveryID}/retire").get_json()["data"]

        assert (data["config_applied"], data["config_ok"]) == (False, False)
        assert "bad directive" in data["config_message"]

    def test_retired_device_can_return_through_a_scan(self, logged_in_client, db_session, status):
        device = new_device(db_session, status, mac=MAC_1)
        logged_in_client.post(f"{BASE}/hosts/{device.NetDiscoveryID}/retire")

        back = new_device(db_session, status, ip="10.0.0.80", mac=MAC_1)

        assert back.NetDiscoveryID == device.NetDiscoveryID
        assert back.Device_State is DeviceState.ACTIVE


# ==========================================================
# MERGE
# ==========================================================

class TestMerge:

    def two_devices(self, db_session, status):
        target = new_device(db_session, status, ip="10.0.0.1", mac=MAC_1, hostname="target.lan",
                            identifiers=[ssh(SSH_1)], tcp={22: "ssh"})
        source = new_device(db_session, status, ip="10.0.0.2", mac=MAC_2, hostname="dup.lan",
                            tcp={22: "ssh", 80: "http"})
        return source, target

    def merge(self, client, source, target_id):
        return client.post(f"{BASE}/hosts/{source.NetDiscoveryID}/merge", json={"target_id": target_id})

    def test_moves_identifiers_address_history_and_ports_to_the_target(self, logged_in_client, db_session, status, regenerate):
        source, target = self.two_devices(db_session, status)

        resp = self.merge(logged_in_client, source, target.NetDiscoveryID)

        assert resp.status_code == 200
        db_session.session.refresh(source)
        db_session.session.refresh(target)
        assert source.Device_State is DeviceState.MERGED
        assert source.Merged_Into_ID == target.NetDiscoveryID
        assert identifier_values(target, IdentifierKind.MAC) == {MAC_1, MAC_2}
        assert identifier_values(source, IdentifierKind.MAC) == set()
        assert target.IP_Address == "10.0.0.1"  # the target keeps its own address
        assert [r.IP_Address for r in open_addresses(target)] == ["10.0.0.1"]
        history = db.session.scalars(sa.select(DeviceAddressHistory).where(
            DeviceAddressHistory.NetDiscoveryID == target.NetDiscoveryID)).all()
        assert sorted(r.IP_Address for r in history) == ["10.0.0.1", "10.0.0.2"]
        ports = db.session.scalars(sa.select(Open_TCP_Services).where(
            Open_TCP_Services.NetDiscoveryID == target.NetDiscoveryID)).all()
        assert sorted(p.Port_Number for p in ports) == [22, 80]  # no duplicate 22
        regenerate.assert_called_once()
        assert log_actions()[-1] == "Merged device dup.lan into target.lan"

    def test_merged_device_leaves_the_loaded_config(self, logged_in_client, db_session, status):
        from app.network_discovery.create_host_cfg import _load_monitored_hosts
        source, target = self.two_devices(db_session, status)

        self.merge(logged_in_client, source, target.NetDiscoveryID)

        hosts = _load_monitored_hosts()[NET]
        assert [h["data"]["hostname"] for h in hosts.values()] == ["target.lan"]

    def test_target_confidence_is_recomputed(self, logged_in_client, db_session, status):
        target = new_device(db_session, status, ip="10.0.0.1")
        source = new_device(db_session, status, ip="10.0.0.2", identifiers=[ssh(SSH_2)])
        assert target.Identity_Confidence.name == "UNVERIFIED"

        self.merge(logged_in_client, source, target.NetDiscoveryID)

        db_session.session.refresh(target)
        assert target.Identity_Confidence.name == "VERIFIED"

    def test_re_points_plugin_configurations_at_the_target(self, logged_in_client, db_session, status):
        source, target = self.two_devices(db_session, status)
        plugin = Plugin(Name="check_x", Plugin_Type=PluginType.CUSTOM, Source=PluginSource.ADMINISTRATOR_ADDED,
                        Status=PluginStatus.READY)
        db_session.session.add(plugin)
        db_session.session.flush()
        config = PluginConfiguration(PluginID=plugin.PluginID, NetDiscoveryID=source.NetDiscoveryID,
                                     Service_Description="x")
        db_session.session.add(config)
        db_session.session.commit()

        self.merge(logged_in_client, source, target.NetDiscoveryID)

        db_session.session.refresh(config)
        assert config.NetDiscoveryID == target.NetDiscoveryID

    def test_ncpa_records_move_only_if_the_target_has_none(self, logged_in_client, db_session, status):
        source, target = self.two_devices(db_session, status)
        target_deployment = db.session.scalar(sa.select(NCPADeployment).where(
            NCPADeployment.NetworkDiscoveryID == target.NetDiscoveryID))

        self.merge(logged_in_client, source, target.NetDiscoveryID)

        db_session.session.refresh(target_deployment)
        # The target kept its own record; the duplicate's stays with the merged row.
        assert target_deployment.NetworkDiscoveryID == target.NetDiscoveryID
        assert db.session.scalar(sa.select(sa.func.count()).select_from(NCPADeployment).where(
            NCPADeployment.NetworkDiscoveryID == target.NetDiscoveryID)) == 1

    def test_review_items_about_the_duplicate_are_resolved(self, logged_in_client, db_session, status):
        source, target = self.two_devices(db_session, status)
        db_session.session.add(DeviceReviewItem(
            Kind=ReviewKind.CONFLICT, IP_Address="10.0.0.2", Message="m",
            Candidate_Device_IDs=[source.NetDiscoveryID, target.NetDiscoveryID]))
        db_session.session.commit()

        self.merge(logged_in_client, source, target.NetDiscoveryID)

        assert review_items()[0].Resolved_At is not None

    def test_a_later_scan_of_the_merged_devices_evidence_lands_on_the_target(self, logged_in_client, db_session, status):
        source, target = self.two_devices(db_session, status)
        self.merge(logged_in_client, source, target.NetDiscoveryID)

        seen = new_device(db_session, status, ip="10.0.0.60", mac=MAC_2)

        assert seen.NetDiscoveryID == target.NetDiscoveryID
        assert len([d for d in all_devices() if d.Device_State is not DeviceState.MERGED]) == 1

    @pytest.mark.parametrize("body, code", [
        ({"target_id": "x"}, 400),
        ({"target_id": True}, 400),
        ({}, 400),
        ({"target_id": 999}, 404),
    ])
    def test_invalid_bodies(self, logged_in_client, db_session, status, body, code):
        device = new_device(db_session, status)

        resp = logged_in_client.post(f"{BASE}/hosts/{device.NetDiscoveryID}/merge", json=body)

        assert resp.status_code == code

    def test_cannot_merge_into_itself(self, logged_in_client, db_session, status):
        device = new_device(db_session, status)

        assert self.merge(logged_in_client, device, device.NetDiscoveryID).status_code == 400

    def test_cannot_merge_twice_or_into_a_retired_or_merged_target(self, logged_in_client, db_session, status):
        source, target = self.two_devices(db_session, status)
        third = new_device(db_session, status, ip="10.0.0.3", mac="00:11:22:33:44:03")
        assert self.merge(logged_in_client, source, target.NetDiscoveryID).status_code == 200

        assert self.merge(logged_in_client, source, third.NetDiscoveryID).status_code == 400  # already merged
        assert self.merge(logged_in_client, third, source.NetDiscoveryID).status_code == 400  # merged target
        target.Device_State = DeviceState.RETIRED
        db_session.session.commit()
        assert self.merge(logged_in_client, third, target.NetDiscoveryID).status_code == 400  # retired target

    def test_unknown_source_is_404(self, logged_in_client, db_session, status):
        target = new_device(db_session, status)

        assert logged_in_client.post(BASE + "/hosts/999/merge",
                                     json={"target_id": target.NetDiscoveryID}).status_code == 404


# ==========================================================
# PORT STATE
# ==========================================================

class TestPortState:

    def put(self, client, device, proto, port, body):
        return client.put(f"{BASE}/hosts/{device.NetDiscoveryID}/ports/{proto}/{port}", json=body)

    def test_monitoring_a_suggestion_freezes_its_plugin_and_regenerates(self, logged_in_client, db_session, status, regenerate):
        device = new_device(db_session, status, tcp={3306: "mysql"})

        resp = self.put(logged_in_client, device, "tcp", 3306, {"state": "monitored"})

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["port"] == {"number": 3306, "protocol": "tcp", "service_name": "mysql",
                                "plugin_name": "mysql", "state": "MONITORED", "identified_by": "FINGERPRINT",
                                "pinned": False, "expected_service_name": None, "mismatch_acknowledged": False, "promotion_held": False}
        assert data["config_applied"] is True
        regenerate.assert_called_once()
        assert log_actions()[-1] == f"Set tcp port 3306 on {device.Nagios_Host_Name} to Monitored"

    def flagged_port(self, db_session, status, port=22, found="http", expected="ssh"):
        """A device whose port 22 answers as http while the table expects ssh."""
        device = new_device(db_session, status)
        row = Open_TCP_Services(
            NetDiscoveryID=device.NetDiscoveryID, Port_Number=port, Service_Name=found,
            Observed_Service_Name=found, Port_State=PortState.SUGGESTED, Expected_Service_Name=expected,
            Identified_By=ServiceIdentification.FINGERPRINT,
        )
        db_session.session.add(row)
        db_session.session.commit()
        return device, row

    def test_acknowledging_a_mismatch_monitors_the_service_nmap_found(self, logged_in_client, db_session, status, regenerate):
        device, row = self.flagged_port(db_session, status)

        resp = self.put(logged_in_client, device, "tcp", 22, {"acknowledge_mismatch": True})

        assert resp.status_code == 200
        port = resp.get_json()["data"]["port"]
        assert port["service_name"] == "http"
        assert port["state"] == "MONITORED"
        assert port["expected_service_name"] == "ssh"
        assert port["mismatch_acknowledged"] is True
        regenerate.assert_called_once()
        assert log_actions()[-1] == (
            f"Acknowledged tcp port 22 on {device.Nagios_Host_Name} as http, not the expected ssh")

    def test_acknowledging_twice_is_refused(self, logged_in_client, db_session, status, regenerate):
        device, row = self.flagged_port(db_session, status)
        assert self.put(logged_in_client, device, "tcp", 22, {"acknowledge_mismatch": True}).status_code == 200

        resp = self.put(logged_in_client, device, "tcp", 22, {"acknowledge_mismatch": True})

        assert resp.status_code == 400
        assert "no unacknowledged mismatch" in resp.get_json()["message"]

    def test_acknowledging_a_port_that_is_not_flagged_is_refused(self, logged_in_client, db_session, status, regenerate):
        device = new_device(db_session, status, tcp={3306: "mysql"})

        resp = self.put(logged_in_client, device, "tcp", 3306, {"acknowledge_mismatch": True})

        assert resp.status_code == 400

    def test_acknowledge_must_be_a_boolean(self, logged_in_client, db_session, status, regenerate):
        device, row = self.flagged_port(db_session, status)
        assert self.put(logged_in_client, device, "tcp", 22, {"acknowledge_mismatch": "yes"}).status_code == 400

    def test_choosing_to_monitor_a_flagged_port_acknowledges_it(self, logged_in_client, db_session, status, regenerate):
        device, row = self.flagged_port(db_session, status)

        resp = self.put(logged_in_client, device, "tcp", 22, {"state": "MONITORED"})

        assert resp.status_code == 200
        assert resp.get_json()["data"]["port"]["mismatch_acknowledged"] is True

    def test_ignoring_and_restoring_a_port(self, logged_in_client, db_session, status):
        device = new_device(db_session, status, tcp={3306: "mysql"})

        assert self.put(logged_in_client, device, "tcp", 3306, {"state": "IGNORED"}).status_code == 200
        port = db_session.session.scalar(sa.select(Open_TCP_Services).where(Open_TCP_Services.Port_Number == 3306))
        assert port.Port_State is PortState.IGNORED
        assert self.put(logged_in_client, device, "tcp", 3306, {"state": "SUGGESTED"}).status_code == 200
        db_session.session.refresh(port)
        assert port.Port_State is PortState.SUGGESTED

    def test_ncpa_port_is_protected_while_a_token_is_deployed(self, logged_in_client, db_session, status):
        device = new_device(db_session, status, tcp={5693: "ncpa"})
        deployment = db.session.scalar(sa.select(NCPADeployment).where(
            NCPADeployment.NetworkDiscoveryID == device.NetDiscoveryID))
        deployment.Token = "t" * 32
        port = db.session.scalar(sa.select(Open_TCP_Services).where(Open_TCP_Services.Port_Number == 5693))
        port.Source = PortSource.NCPA
        db_session.session.commit()

        resp = self.put(logged_in_client, device, "tcp", 5693, {"state": "ARCHIVED"})

        assert resp.status_code == 400
        assert "NCPA" in resp.get_json()["message"]
        db_session.session.refresh(port)
        assert port.Port_State is PortState.MONITORED

    def test_user_can_add_an_ephemeral_range_port(self, logged_in_client, db_session, status):
        device = new_device(db_session, status)

        resp = self.put(logged_in_client, device, "tcp", 40000, {"state": "MONITORED", "service_name": "http"})

        assert resp.status_code == 200
        port = db_session.session.scalar(sa.select(Open_TCP_Services).where(Open_TCP_Services.Port_Number == 40000))
        assert port.Source is PortSource.USER
        assert port.Port_State is PortState.MONITORED
        assert port.Plugin_Name == "http"

    def test_missing_port_without_a_service_name_is_404(self, logged_in_client, db_session, status):
        device = new_device(db_session, status)

        assert self.put(logged_in_client, device, "tcp", 8080, {"state": "MONITORED"}).status_code == 404
        assert self.put(logged_in_client, device, "tcp", 8080, {"state": "IGNORED"}).status_code == 404

    @pytest.mark.parametrize("proto, port, body", [
        ("icmp", 22, {"state": "MONITORED"}),
        ("tcp", 0, {"state": "MONITORED"}),
        ("tcp", 70000, {"state": "MONITORED"}),
        ("tcp", 22, {"state": "MISSING"}),
        ("tcp", 22, {"state": "bogus"}),
        ("tcp", 22, {}),
    ])
    def test_invalid_requests(self, logged_in_client, db_session, status, proto, port, body):
        device = new_device(db_session, status, tcp={22: "ssh"})

        assert self.put(logged_in_client, device, proto, port, body).status_code == 400

    def test_unknown_device_is_404(self, logged_in_client, db_session):
        assert logged_in_client.put(BASE + "/hosts/999/ports/tcp/22", json={"state": "MONITORED"}).status_code == 404

    def test_udp_ports_are_supported(self, logged_in_client, db_session, status):
        device = new_device(db_session, status, udp={514: "syslog"})

        resp = self.put(logged_in_client, device, "udp", 514, {"state": "monitored"})

        assert resp.status_code == 200
        assert resp.get_json()["data"]["port"]["protocol"] == "udp"

    def test_pinning_a_service_without_a_state(self, logged_in_client, db_session, status, regenerate):
        device = new_device(db_session, status, tcp={8080: "http"})

        resp = self.put(logged_in_client, device, "tcp", 8080, {"service_name": "NCPA"})

        assert resp.status_code == 200
        port = resp.get_json()["data"]["port"]
        assert (port["service_name"], port["plugin_name"], port["identified_by"]) == ("ncpa", "ncpa", "USER")
        assert port["state"] == "MONITORED"
        regenerate.assert_called_once()
        assert log_actions()[-1] == f"Pinned tcp port 8080 on {device.Nagios_Host_Name} as ncpa"

    def test_pinning_and_monitoring_a_suggestion_uses_the_pinned_plugin(self, logged_in_client, db_session, status):
        device = new_device(db_session, status, tcp={2222: "EtherNetIP-1"})

        resp = self.put(logged_in_client, device, "tcp", 2222, {"service_name": "ssh", "state": "MONITORED"})

        port = resp.get_json()["data"]["port"]
        assert (port["plugin_name"], port["state"], port["identified_by"]) == ("ssh", "MONITORED", "USER")
        assert log_actions()[-1] == (
            f"Pinned tcp port 2222 on {device.Nagios_Host_Name} as ssh and set it to Monitored"
        )

    def test_a_pinned_port_survives_the_next_scan(self, logged_in_client, db_session, status):
        device = new_device(db_session, status, tcp={8080: "http"})
        self.put(logged_in_client, device, "tcp", 8080, {"service_name": "ncpa"})

        new_device(db_session, status, tcp={8080: "http"}, mac=device.MAC_Address)

        port = db_session.session.scalar(sa.select(Open_TCP_Services).where(Open_TCP_Services.Port_Number == 8080))
        assert (port.Service_Name, port.Plugin_Name) == ("ncpa", "ncpa")

    @pytest.mark.parametrize("name", ["bad name", "x;rm", "", 7, "a" * 40])
    def test_unsafe_service_names_are_rejected(self, logged_in_client, db_session, status, name):
        device = new_device(db_session, status, tcp={8080: "http"})

        assert self.put(logged_in_client, device, "tcp", 8080, {"service_name": name}).status_code == 400

    def test_pinning_a_port_the_device_does_not_have_is_404(self, logged_in_client, db_session, status):
        device = new_device(db_session, status, tcp={8080: "http"})

        assert self.put(logged_in_client, device, "tcp", 9090, {"service_name": "http"}).status_code == 404


# ==========================================================
# REVIEW LIST
# ==========================================================

class TestReview:

    def test_empty(self, logged_in_client, db_session):
        resp = logged_in_client.get(BASE + "/discover/review")

        assert resp.status_code == 200
        assert resp.get_json()["data"] == {"items": []}

    def test_lists_unresolved_items_with_their_devices(self, logged_in_client, db_session, status):
        old = new_device(db_session, status, mac=MAC_1, hostname="old.lan")
        new_device(db_session, status, mac=MAC_2)  # IP reuse -> review item

        items = logged_in_client.get(BASE + "/discover/review").get_json()["data"]["items"]

        assert len(items) == 1
        item = items[0]
        assert item["kind"] == "IP_REUSE"
        assert item["ip_address"] == "10.0.0.5"
        assert item["mac_address"] == MAC_2
        assert [d["id"] for d in item["devices"]] == [old.NetDiscoveryID]
        assert item["devices"][0]["state"] == "ADDRESS_UNKNOWN"
        assert item["devices"][0]["nagios_host_name"] == "old.lan"

    def test_resolving_removes_it_from_the_list(self, logged_in_client, db_session, status):
        new_device(db_session, status, mac=MAC_1)
        new_device(db_session, status, mac=MAC_2)
        item_id = review_items()[0].ReviewID

        resp = logged_in_client.post(f"{BASE}/discover/review/{item_id}/resolve")

        assert resp.status_code == 200
        assert logged_in_client.get(BASE + "/discover/review").get_json()["data"]["items"] == []
        assert log_actions()[-1] == f"Resolved device review item {item_id}"

    def test_resolving_twice_is_harmless(self, logged_in_client, db_session, status):
        new_device(db_session, status, mac=MAC_1)
        new_device(db_session, status, mac=MAC_2)
        item_id = review_items()[0].ReviewID
        logged_in_client.post(f"{BASE}/discover/review/{item_id}/resolve")
        count = len(log_actions())

        assert logged_in_client.post(f"{BASE}/discover/review/{item_id}/resolve").status_code == 200
        assert len(log_actions()) == count

    def test_unknown_item_is_404(self, logged_in_client, db_session):
        assert logged_in_client.post(BASE + "/discover/review/999/resolve").status_code == 404

    def test_resolved_items_do_not_come_back_on_the_next_scan(self, logged_in_client, db_session, status):
        new_device(db_session, status, mac=MAC_1)
        new_device(db_session, status, mac=MAC_2)
        item_id = review_items()[0].ReviewID
        logged_in_client.post(f"{BASE}/discover/review/{item_id}/resolve")

        new_device(db_session, status, mac=MAC_2)  # the same situation, rescanned

        # Nothing new to review: the reused-IP device now simply matches.
        assert logged_in_client.get(BASE + "/discover/review").get_json()["data"]["items"] == []
