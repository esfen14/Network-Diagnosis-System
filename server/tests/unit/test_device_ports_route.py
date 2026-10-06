"""
tests/unit/test_device_ports_route.py — The Device Inventory ports routes:
GET /api/system/hosts/<id>/ports and the "unpin" option of the port-edit route.

The requirement is spec files/Device_Inventory_Requirements.md. The read route lists every
port of a device with its state, how its service was decided, its check plugin, its flags and,
for Suggested and Ignored ports, the one reason it is not monitored (first match wins). Unpin
undoes a pin so scans decide the service again. Nagios is never run: the reconciler is replaced.
"""
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from app import db
from app.network_discovery.port_lifecycle import (
    port_reason,
    process_device_ports,
    set_port_state,
    unpin_port_service,
)
from app.plugin_models import Plugin, PluginSource, PluginStatus, PluginType
from app.system_models import (
    AgentStatus,
    DeviceReviewItem,
    DeviceState,
    NCPADeployment,
    Open_TCP_Services,
    Open_UDP_Services,
    PortSource,
    PortState,
    ReviewKind,
    ServiceIdentification,
)
from tests.support.identity_helpers import MAC_1, NET, make_status, run_scan, scan

BASE = "/api/system"


@pytest.fixture(autouse=True)
def reconcile():
    with patch("app.api.system.device_identity.reconcile_plugin_monitoring",
               return_value={"success": True, "changed": True, "message": "applied"}) as mock:
        yield mock


@pytest.fixture
def status(db_session, admin_user):
    return make_status(db_session, admin_user)


def new_device(status, ip="10.0.0.5", **services):
    return run_scan(db, status, scan(ip, mac=MAC_1, **services))[(NET, ip)]


def enable(*names):
    for name in names:
        db.session.add(Plugin(Name=name, Plugin_Type=PluginType.NAGIOS, Source=PluginSource.BASELINE_ISO,
                              Status=PluginStatus.ENABLED))
    db.session.commit()


def port(device, number, protocol="tcp"):
    model = Open_UDP_Services if protocol == "udp" else Open_TCP_Services
    return db.session.scalar(sa.select(model).where(
        model.NetDiscoveryID == device.NetDiscoveryID, model.Port_Number == number))


def listing(client, device):
    resp = client.get(f"{BASE}/hosts/{device.NetDiscoveryID}/ports")
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]


def by_number(data, number, protocol="tcp"):
    return next(p for p in data["ports"] if p["number"] == number and p["protocol"] == protocol)


# ==========================================================
# ACCESS
# ==========================================================

class TestAccess:

    def test_requires_login(self, client, db_session):
        assert client.get(f"{BASE}/hosts/1/ports").status_code in (401, 302)

    def test_requires_system_hosts_permission(self, limited_client, db_session, status):
        device = new_device(status, tcp={22: "ssh"})
        assert limited_client.get(f"{BASE}/hosts/{device.NetDiscoveryID}/ports").status_code == 403

    def test_unknown_device(self, logged_in_client, db_session):
        resp = logged_in_client.get(f"{BASE}/hosts/999999/ports")
        assert resp.status_code == 404 and resp.get_json()["message"] == "Device not found."


# ==========================================================
# THE LIST
# ==========================================================

class TestList:

    def test_a_device_with_no_ports(self, logged_in_client, db_session, status):
        device = new_device(status)

        data = listing(logged_in_client, device)

        assert data["ports"] == []
        assert data["counts"] == {"MONITORED": 0, "MISSING": 0, "SUGGESTED": 0, "IGNORED": 0, "ARCHIVED": 0}
        assert data["device"] == {
            "id": device.NetDiscoveryID, "nagios_host_name": device.Nagios_Host_Name,
            "ip_address": "10.0.0.5", "state": "ACTIVE", "scanned": True,
        }

    def test_a_port_carries_everything_the_screen_shows(self, logged_in_client, db_session, status):
        enable("check_ssh")
        device = new_device(status, tcp={22: "ssh"})
        row = port(device, 22)
        row.Port_State, row.Plugin_Name = PortState.MONITORED, "ssh"
        db.session.commit()

        item = by_number(listing(logged_in_client, device), 22)

        assert item["service_name"] == "ssh" and item["observed_service_name"] == "ssh"
        assert item["state"] == "MONITORED" and item["source"] == "SCAN"
        assert item["identified_by"] == "FINGERPRINT" and item["pinned"] is False
        assert item["plugin_name"] == "ssh" and item["check_plugin"] == "check_ssh" and item["plugin_enabled"] is True
        assert item["expected_service_name"] is None and item["mismatch_acknowledged"] is False
        assert item["promotion_held"] is False and item["managed_by_ncpa"] is False
        assert item["missed_scans"] == 0 and item["first_seen_at"] and item["last_seen_at"]
        assert item["reason"] is None

    def test_ports_are_ordered_by_state_then_protocol_then_number(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={443: "https", 22: "ssh", 80: "http", 8080: "http-proxy"}, udp={161: "snmp", 53: "dns"})
        port(device, 80).Port_State = PortState.MONITORED
        port(device, 443).Port_State = PortState.MISSING
        port(device, 8080).Port_State = PortState.IGNORED
        udp = port(device, 53, "udp")
        udp.Port_State = PortState.MONITORED
        db.session.commit()

        data = listing(logged_in_client, device)

        assert [(p["state"], p["protocol"], p["number"]) for p in data["ports"]] == [
            ("MONITORED", "tcp", 80), ("MONITORED", "udp", 53), ("MISSING", "tcp", 443),
            ("SUGGESTED", "tcp", 22), ("SUGGESTED", "udp", 161), ("IGNORED", "tcp", 8080),
        ]

    def test_counts_per_state(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={22: "ssh", 80: "http", 443: "https", 8080: "x"})
        port(device, 80).Port_State = PortState.MONITORED
        port(device, 443).Port_State = PortState.ARCHIVED
        port(device, 8080).Port_State = PortState.IGNORED
        db.session.commit()

        assert listing(logged_in_client, device)["counts"] == {
            "MONITORED": 1, "MISSING": 0, "SUGGESTED": 1, "IGNORED": 1, "ARCHIVED": 1}

    def test_only_this_devices_ports_are_listed(self, logged_in_client, db_session, status):
        device = new_device(status, "10.0.0.5", tcp={22: "ssh"})
        run_scan(db, status, scan("10.0.0.6", mac="00:11:22:33:44:99", tcp={80: "http"}))

        assert [p["number"] for p in listing(logged_in_client, device)["ports"]] == [22]

    def test_listing_changes_nothing(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={22: "ssh"})
        before = (port(device, 22).Port_State, port(device, 22).Promotion_Held, port(device, 22).Plugin_Name)

        listing(logged_in_client, device)
        db.session.expire_all()

        assert (port(device, 22).Port_State, port(device, 22).Promotion_Held, port(device, 22).Plugin_Name) == before

    def test_a_device_excluded_from_scanning_says_so(self, logged_in_client, db_session, status):
        device = new_device(status)
        device.Include_Device_In_Scanning = False
        db.session.commit()

        assert listing(logged_in_client, device)["device"]["scanned"] is False


# ==========================================================
# CHECK PLUGIN AND FLAGS
# ==========================================================

class TestCheckPluginAndFlags:

    def test_the_check_plugin_and_whether_it_is_enabled(self, logged_in_client, db_session, status):
        enable("check_ssh")
        device = new_device(status, tcp={22: "ssh", 3306: "mysql", 9100: "printer"})

        data = listing(logged_in_client, device)

        assert (by_number(data, 22)["check_plugin"], by_number(data, 22)["plugin_enabled"]) == ("check_ssh", True)
        assert (by_number(data, 3306)["check_plugin"], by_number(data, 3306)["plugin_enabled"]) == ("check_mysql", False)
        assert by_number(data, 9100)["check_plugin"] == "check_tcp"          # the generic check

    def test_a_udp_service_no_plugin_speaks_has_no_check_plugin(self, logged_in_client, db_session, status):
        device = new_device(status, udp={9999: "mystery", 161: "snmp"})

        data = listing(logged_in_client, device)

        assert by_number(data, 9999, "udp")["check_plugin"] is None
        assert by_number(data, 161, "udp")["check_plugin"] == "check_snmp"

    def test_a_pinned_flagged_and_held_port_says_so(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={22: "http"})
        row = port(device, 22)
        row.Expected_Service_Name, row.Promotion_Held = "ssh", True
        row.Identified_By = ServiceIdentification.USER
        db.session.commit()

        item = by_number(listing(logged_in_client, device), 22)

        assert item["pinned"] is True and item["identified_by"] == "USER"
        assert item["expected_service_name"] == "ssh" and item["promotion_held"] is True

    def test_the_ncpa_port_of_a_deployed_agent_is_marked_managed(self, app, logged_in_client, db_session, status):
        device = new_device(status, tcp={22: "ssh"})
        db.session.add(NCPADeployment(Token="t" * 32, Agent_Status=AgentStatus.DEPLOYED, NetworkDiscoveryID=device.NetDiscoveryID))
        from app.network_discovery.port_lifecycle import mark_ncpa_port
        mark_ncpa_port(device.NetDiscoveryID)
        db.session.commit()

        data = listing(logged_in_client, device)

        assert by_number(data, int(app.config["NCPA_PORT"]))["managed_by_ncpa"] is True
        assert by_number(data, 22)["managed_by_ncpa"] is False


# ==========================================================
# REASONS: one applies, first match wins
# ==========================================================

class TestReasons:

    def reason(self, client, device, number, protocol="tcp"):
        return by_number(listing(client, device), number, protocol)["reason"]

    def test_monitored_missing_and_archived_ports_have_no_reason(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={22: "ssh", 80: "http", 443: "https"})
        port(device, 22).Port_State = PortState.MONITORED
        port(device, 80).Port_State = PortState.MISSING
        port(device, 443).Port_State = PortState.ARCHIVED
        db.session.commit()

        for number in (22, 80, 443):
            assert self.reason(logged_in_client, device, number) is None

    def test_not_used_as_intended(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={22: "http"})
        port(device, 22).Expected_Service_Name = "ssh"
        db.session.commit()

        assert self.reason(logged_in_client, device, 22) == {
            "code": "not_used_as_intended",
            "text": "Not used as intended: expected ssh, found http. Not monitored until acknowledged.",
        }

    def test_an_acknowledged_flag_is_no_longer_a_reason(self, logged_in_client, db_session, status):
        from datetime import datetime, timezone
        device = new_device(status, tcp={22: "http"})
        enable("check_http")
        row = port(device, 22)
        row.Expected_Service_Name, row.Mismatch_Acknowledged_At = "ssh", datetime.now(timezone.utc)
        db.session.commit()

        assert self.reason(logged_in_client, device, 22)["code"] == "pending"

    def test_held(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={22: "ssh"})
        port(device, 22).Promotion_Held = True
        db.session.commit()

        assert self.reason(logged_in_client, device, 22) == {
            "code": "held",
            "text": "Held back: left Suggested on purpose, or at an upgrade. No plugin will monitor it until you do.",
        }

    def test_only_guessed(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={22: "ssh"})
        port(device, 22).Identified_By = ServiceIdentification.PORT_HINT
        db.session.commit()

        assert self.reason(logged_in_client, device, 22) == {
            "code": "guessed", "text": "Only guessed from the port number, so it is not monitored automatically."}

    def test_a_port_recorded_before_identification_existed_counts_as_a_guess(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={22: "ssh"})
        port(device, 22).Identified_By = None
        db.session.commit()

        assert self.reason(logged_in_client, device, 22)["code"] == "guessed"

    def test_a_udp_service_nothing_can_check(self, logged_in_client, db_session, status):
        device = new_device(status, udp={9999: "mystery"})

        assert self.reason(logged_in_client, device, 9999, "udp") == {
            "code": "no_udp_plugin", "text": "No plugin can check this UDP service."}

    def test_the_plugin_is_not_enabled(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={22: "ssh", 9100: "printer"})

        assert self.reason(logged_in_client, device, 22) == {
            "code": "plugin_not_enabled", "text": "check_ssh is not enabled in Plugin Manager."}
        assert self.reason(logged_in_client, device, 9100)["text"] == "check_tcp is not enabled in Plugin Manager."

    def test_a_device_excluded_from_scanning(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={22: "ssh"})
        enable("check_ssh")
        device.Include_Device_In_Scanning = False
        db.session.commit()

        assert self.reason(logged_in_client, device, 22) == {
            "code": "device_excluded", "text": "This device is excluded from scanning."}

    def test_a_retired_device(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={22: "ssh"})
        enable("check_ssh")
        device.Device_State = DeviceState.RETIRED
        db.session.commit()

        assert self.reason(logged_in_client, device, 22)["code"] == "device_excluded"

    def test_nothing_in_the_way_means_the_next_update_will_monitor_it(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={22: "ssh"})
        enable("check_ssh")

        assert self.reason(logged_in_client, device, 22) == {
            "code": "pending", "text": "Will be monitored by the next update."}

    def test_a_stopped_port(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={22: "ssh"})
        port(device, 22).Port_State = PortState.IGNORED
        db.session.commit()

        assert self.reason(logged_in_client, device, 22) == {
            "code": "stopped", "text": "Monitoring stopped by an administrator."}

    @pytest.mark.parametrize("held, flagged, expected", [
        (True, True, "not_used_as_intended"),     # a flag beats a hold
        (True, False, "held"),
    ])
    def test_the_first_match_wins(self, logged_in_client, db_session, status, held, flagged, expected):
        device = new_device(status, tcp={22: "http"})
        row = port(device, 22)
        row.Promotion_Held = held
        row.Expected_Service_Name = "ssh" if flagged else None
        row.Identified_By = ServiceIdentification.PORT_HINT      # also only a guess, which comes later
        db.session.commit()

        assert self.reason(logged_in_client, device, 22)["code"] == expected

    def test_a_hold_beats_a_guess_and_a_guess_beats_a_missing_plugin(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={22: "ssh", 80: "http"})
        held = port(device, 22)
        held.Promotion_Held, held.Identified_By = True, ServiceIdentification.PORT_HINT
        port(device, 80).Identified_By = ServiceIdentification.PORT_HINT
        db.session.commit()

        data = listing(logged_in_client, device)

        assert by_number(data, 22)["reason"]["code"] == "held"
        assert by_number(data, 80)["reason"]["code"] == "guessed"

    def test_the_reason_agrees_with_what_the_reconciler_does(self, db_session, status):
        """A port whose reason is "pending" is exactly one the next promotion monitors."""
        from app.network_discovery.port_lifecycle import enabled_plugin_names, promote_identified_ports
        device = new_device(status, tcp={22: "ssh", 80: "http", 3306: "mysql"})
        enable("check_ssh")
        port(device, 80).Promotion_Held = True
        db.session.commit()

        enabled = enabled_plugin_names()
        pending = {p.Port_Number for p in db.session.scalars(sa.select(Open_TCP_Services)).all()
                   if (port_reason(p, "tcp", device, enabled) or {}).get("code") == "pending"}
        promote_identified_ports()
        db.session.commit()
        promoted = {p.Port_Number for p in db.session.scalars(sa.select(Open_TCP_Services)).all()
                    if p.Port_State is PortState.MONITORED}

        assert pending == promoted == {22}


# ==========================================================
# SERVICE OPTIONS FOR THE PIN DIALOG
# ==========================================================

class TestServiceOptions:

    def test_known_names_and_aliases_with_their_check_plugin(self, logged_in_client, db_session, status):
        options = {o["name"]: o for o in listing(logged_in_client, new_device(status))["service_options"]}

        assert options["ssh"] == {"name": "ssh", "plugin": "check_ssh", "protocols": ["tcp"]}
        assert options["domain"]["plugin"] == "check_dns"                    # an alias
        assert options["dns"]["protocols"] == ["tcp", "udp"]
        assert options["snmp"] == {"name": "snmp", "plugin": "check_snmp", "protocols": ["udp"]}
        assert options["https"]["plugin"] == "check_http"                    # http and https share a plugin

    def test_the_generic_checks_are_not_offered_as_services(self, logged_in_client, db_session, status):
        names = [o["name"] for o in listing(logged_in_client, new_device(status))["service_options"]]

        assert "tcp" not in names and "udp" not in names
        assert names == sorted(names) and len(names) == len(set(names))


# ==========================================================
# UNPIN
# ==========================================================

class TestUnpinLifecycle:

    def pinned(self, status, number=8080, service="http-proxy", pin_as="ssh"):
        from app.network_discovery.port_lifecycle import pin_port_service
        device = new_device(status, tcp={number: service})
        pin_port_service(device.NetDiscoveryID, "tcp", number, pin_as)
        db.session.commit()
        return device

    def test_a_suggested_port_goes_back_to_what_the_last_scan_saw(self, db_session, status):
        device = self.pinned(status)
        assert port(device, 8080).Service_Name == "ssh" and port(device, 8080).Observed_Service_Name == "http-proxy"

        unpin_port_service(device.NetDiscoveryID, "tcp", 8080)
        db.session.commit()

        row = port(device, 8080)
        assert row.Service_Name == "http-proxy" and row.Identified_By is ServiceIdentification.PORT_HINT
        assert row.Port_State is PortState.SUGGESTED

    def test_a_monitored_port_keeps_its_service_and_its_nagios_service(self, db_session, status):
        device = self.pinned(status)
        set_port_state(device.NetDiscoveryID, "tcp", 8080, PortState.MONITORED)
        db.session.commit()
        assert port(device, 8080).Plugin_Name == "ssh"

        unpin_port_service(device.NetDiscoveryID, "tcp", 8080)
        db.session.commit()

        row = port(device, 8080)
        assert (row.Service_Name, row.Plugin_Name, row.Port_State) == ("ssh", "ssh", PortState.MONITORED)
        assert row.Identified_By is ServiceIdentification.PORT_HINT

    def test_it_never_changes_the_state_or_the_hold(self, db_session, status):
        device = self.pinned(status)
        port(device, 8080).Promotion_Held = True
        db.session.commit()

        unpin_port_service(device.NetDiscoveryID, "tcp", 8080)
        db.session.commit()

        assert port(device, 8080).Promotion_Held is True and port(device, 8080).Port_State is PortState.SUGGESTED

    def test_an_ignored_or_archived_port_follows_the_scan_again(self, db_session, status):
        device = self.pinned(status)
        set_port_state(device.NetDiscoveryID, "tcp", 8080, PortState.IGNORED)
        db.session.commit()

        unpin_port_service(device.NetDiscoveryID, "tcp", 8080)
        db.session.commit()

        assert port(device, 8080).Service_Name == "http-proxy" and port(device, 8080).Port_State is PortState.IGNORED

    def test_a_port_that_is_not_pinned_is_refused(self, db_session, status):
        device = new_device(status, tcp={22: "ssh"})
        with pytest.raises(ValueError, match="not pinned"):
            unpin_port_service(device.NetDiscoveryID, "tcp", 22)

    def test_a_missing_port_returns_none(self, db_session, status):
        device = new_device(status)
        assert unpin_port_service(device.NetDiscoveryID, "tcp", 22) is None

    def test_the_ncpa_port_of_a_deployed_agent_cannot_be_unpinned(self, app, db_session, status):
        from app.network_discovery.port_lifecycle import mark_ncpa_port, pin_port_service
        device = new_device(status)
        db.session.add(NCPADeployment(Token="t" * 32, Agent_Status=AgentStatus.DEPLOYED, NetworkDiscoveryID=device.NetDiscoveryID))
        mark_ncpa_port(device.NetDiscoveryID)
        ncpa = int(app.config["NCPA_PORT"])
        pin_port_service(device.NetDiscoveryID, "tcp", ncpa, "ncpa")
        db.session.commit()

        with pytest.raises(ValueError, match="NCPA"):
            unpin_port_service(device.NetDiscoveryID, "tcp", ncpa)

    def test_after_unpinning_a_scan_decides_a_suggested_port_again(self, db_session, status):
        device = self.pinned(status)
        unpin_port_service(device.NetDiscoveryID, "tcp", 8080)
        db.session.commit()

        process_device_ports(device, {"tcp": {"8080": {"service_name": "http", "identified_by": "FINGERPRINT"}}})
        db.session.commit()

        row = port(device, 8080)
        assert row.Service_Name == "http" and row.Identified_By is ServiceIdentification.FINGERPRINT

    def test_while_pinned_a_scan_never_changes_the_service(self, db_session, status):
        device = self.pinned(status)

        process_device_ports(device, {"tcp": {"8080": {"service_name": "http", "identified_by": "FINGERPRINT"}}})
        db.session.commit()

        assert port(device, 8080).Service_Name == "ssh"

    def test_after_unpinning_a_monitored_port_a_different_scan_raises_a_review_item_and_keeps_the_service(self, db_session, status):
        device = self.pinned(status, pin_as="http")
        set_port_state(device.NetDiscoveryID, "tcp", 8080, PortState.MONITORED)
        db.session.commit()
        unpin_port_service(device.NetDiscoveryID, "tcp", 8080)
        db.session.commit()

        process_device_ports(device, {"tcp": {"8080": {"service_name": "ssh", "identified_by": "FINGERPRINT"}}})
        db.session.commit()

        assert (port(device, 8080).Service_Name, port(device, 8080).Plugin_Name) == ("http", "http")
        items = db.session.scalars(sa.select(DeviceReviewItem).where(DeviceReviewItem.Kind == ReviewKind.SERVICE_CHANGED)).all()
        assert len(items) == 1


class TestUnpinRoute:

    def put(self, client, device, number, body, protocol="tcp"):
        return client.put(f"{BASE}/hosts/{device.NetDiscoveryID}/ports/{protocol}/{number}", json=body)

    @pytest.fixture
    def pinned(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={8080: "http-proxy"})
        assert self.put(logged_in_client, device, 8080, {"service_name": "ssh"}).status_code == 200
        return device

    def test_a_saved_change_nagios_could_not_take_is_reported_as_not_ok(self, logged_in_client, pinned, reconcile):
        reconcile.return_value = {"success": False, "changed": False, "message": "Config failed to validate: bad directive"}

        data = self.put(logged_in_client, pinned, 8080, {"state": "IGNORED"}).get_json()["data"]

        assert (data["config_applied"], data["config_ok"]) == (False, False)
        assert "bad directive" in data["config_message"]
        assert data["port"]["state"] == "IGNORED"            # the change itself is kept

    def test_a_change_that_needed_no_reload_is_ok(self, logged_in_client, pinned, reconcile):
        reconcile.return_value = {"success": True, "changed": False, "message": "Host configuration unchanged; Nagios was not reloaded."}

        data = self.put(logged_in_client, pinned, 8080, {"unpin": True}).get_json()["data"]

        assert (data["config_applied"], data["config_ok"]) == (False, True)

    def test_unpin_returns_the_port_and_says_it_is_no_longer_pinned(self, logged_in_client, pinned, reconcile):
        resp = self.put(logged_in_client, pinned, 8080, {"unpin": True})

        assert resp.status_code == 200
        port_data = resp.get_json()["data"]["port"]
        assert port_data["pinned"] is False and port_data["service_name"] == "http-proxy"
        assert port_data["state"] == "SUGGESTED" and port_data["identified_by"] == "PORT_HINT"
        assert reconcile.called

    def test_pinning_is_reported_as_pinned(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={8080: "http-proxy"})
        data = self.put(logged_in_client, device, 8080, {"service_name": "ssh"}).get_json()["data"]["port"]
        assert data["pinned"] is True and data["identified_by"] == "USER"

    def test_it_is_written_to_the_activity_log(self, logged_in_client, db_session, pinned):
        from app.system_models import ActivityLog
        self.put(logged_in_client, pinned, 8080, {"unpin": True})

        last = db.session.scalars(sa.select(ActivityLog).order_by(ActivityLog.LogID.desc())).first()
        assert last.Action_Type == (
            f"Removed the pin on tcp port 8080 on {pinned.Nagios_Host_Name}; scans decide its service again")

    def test_it_can_be_combined_with_a_state(self, logged_in_client, pinned):
        resp = self.put(logged_in_client, pinned, 8080, {"unpin": True, "state": "IGNORED"})

        assert resp.status_code == 200 and resp.get_json()["data"]["port"]["state"] == "IGNORED"

    def test_a_port_that_is_not_pinned_is_a_400(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={22: "ssh"})
        resp = self.put(logged_in_client, device, 22, {"unpin": True})

        assert resp.status_code == 400 and resp.get_json()["message"] == "This port is not pinned."

    def test_unpinning_twice_is_a_400_the_second_time(self, logged_in_client, pinned):
        assert self.put(logged_in_client, pinned, 8080, {"unpin": True}).status_code == 200
        assert self.put(logged_in_client, pinned, 8080, {"unpin": True}).status_code == 400

    def test_it_cannot_be_combined_with_service_name(self, logged_in_client, pinned):
        resp = self.put(logged_in_client, pinned, 8080, {"unpin": True, "service_name": "http"})
        assert resp.status_code == 400 and "cannot be combined" in resp.get_json()["message"]

    @pytest.mark.parametrize("value", ["yes", 1, "true"])
    def test_unpin_must_be_a_boolean(self, logged_in_client, pinned, value):
        assert self.put(logged_in_client, pinned, 8080, {"unpin": value}).status_code == 400

    def test_unpin_false_alone_is_not_a_request(self, logged_in_client, pinned):
        resp = self.put(logged_in_client, pinned, 8080, {"unpin": False})
        assert resp.status_code == 400 and "unpin" in resp.get_json()["message"]

    def test_a_missing_port_is_a_404(self, logged_in_client, db_session, status):
        device = new_device(status)
        assert self.put(logged_in_client, device, 22, {"unpin": True}).status_code == 404

    def test_it_needs_the_edit_permission(self, limited_client, db_session, status):
        device = new_device(status, tcp={8080: "http-proxy"})
        assert self.put(limited_client, device, 8080, {"unpin": True}).status_code == 403

    def test_the_ncpa_port_of_a_deployed_agent_is_a_400(self, app, logged_in_client, db_session, status):
        from app.network_discovery.port_lifecycle import mark_ncpa_port, pin_port_service
        device = new_device(status)
        db.session.add(NCPADeployment(Token="t" * 32, Agent_Status=AgentStatus.DEPLOYED, NetworkDiscoveryID=device.NetDiscoveryID))
        mark_ncpa_port(device.NetDiscoveryID)
        ncpa = int(app.config["NCPA_PORT"])
        pin_port_service(device.NetDiscoveryID, "tcp", ncpa, "ncpa")
        db.session.commit()

        resp = self.put(logged_in_client, device, ncpa, {"unpin": True})

        assert resp.status_code == 400 and "NCPA" in resp.get_json()["message"]
        assert port(device, ncpa).Identified_By is ServiceIdentification.USER

    def test_a_refused_unpin_changes_nothing(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={22: "ssh"})
        before = (port(device, 22).Service_Name, port(device, 22).Identified_By, port(device, 22).Port_State)

        self.put(logged_in_client, device, 22, {"unpin": True})
        db.session.expire_all()

        assert (port(device, 22).Service_Name, port(device, 22).Identified_By, port(device, 22).Port_State) == before
