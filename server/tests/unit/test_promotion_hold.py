"""
tests/unit/test_promotion_hold.py — Holding a port back from promotion (gap G25).

An enabled plugin promotes every identified Suggested port it can check. Two kinds of port must
not be promoted that way: one an admin deliberately set to Suggested, and one that was only
Suggested at an upgrade when the upgrade itself switched a plugin on to keep existing services
running. Promotion_Held marks them; promoting a port by hand releases it. Ports that merely
have not met an enabled plugin yet are not held, so enabling a plugin later still attaches them.
Nagios is never run: the single writer is mocked.
"""
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from app import db
from app.api.plugin.reconcile import preview_enable, reconcile_plugin_monitoring
from app.network_discovery.port_lifecycle import (
    acknowledge_port_mismatch,
    enable_plugins_backing_monitored_ports,
    hold_promotable_ports,
    pin_port_service,
    process_device_ports,
    promotable_ports,
    promote_identified_ports,
    set_port_state,
    should_auto_monitor,
)
from app.plugin_models import (
    Plugin, PluginConfiguration, PluginConfigurationOrigin, PluginSource, PluginStatus, PluginType,
)
from app.system_models import Open_TCP_Services, Open_UDP_Services, PortState
from tests.support.identity_helpers import MAC_1, MAC_2, NET, make_status, run_scan, scan


@pytest.fixture
def status(db_session, admin_user):
    return make_status(db_session, admin_user)


@pytest.fixture
def writer():
    with patch("app.api.plugin.reconcile.regenerate_and_apply_config_status", return_value=("applied", "ok")) as mock:
        yield mock


def add_plugin(name, plugin_status=PluginStatus.ENABLED):
    plugin = Plugin(Name=name, Plugin_Type=PluginType.NAGIOS, Source=PluginSource.BASELINE_ISO, Status=plugin_status)
    db.session.add(plugin)
    db.session.commit()
    return plugin


def new_device(status, ip="10.0.0.5", mac=MAC_1, **services):
    return run_scan(db, status, scan(ip, mac=mac, **services))[(NET, ip)]


def port(device, number):
    return db.session.scalar(sa.select(Open_TCP_Services).where(
        Open_TCP_Services.NetDiscoveryID == device.NetDiscoveryID, Open_TCP_Services.Port_Number == number))


def udp_port(device, number):
    return db.session.scalar(sa.select(Open_UDP_Services).where(
        Open_UDP_Services.NetDiscoveryID == device.NetDiscoveryID, Open_UDP_Services.Port_Number == number))


def auto_names():
    return sorted(row.Nagios_Service_Name for row in db.session.scalars(sa.select(PluginConfiguration).where(
        PluginConfiguration.Origin == PluginConfigurationOrigin.AUTO)).all())


def monitored_before_upgrade(device, number, plugin_name):
    row = port(device, number)
    row.Port_State, row.Plugin_Name = PortState.MONITORED, plugin_name
    db.session.commit()


# ==========================================================
# AN ADMIN LEAVING A PORT SUGGESTED
# ==========================================================

class TestAdminDecision:

    def test_setting_a_port_to_suggested_holds_it(self, db_session, status):
        device = new_device(status, tcp={22: "ssh"})
        add_plugin("check_ssh")
        promote_identified_ports()
        db.session.commit()
        assert port(device, 22).Port_State is PortState.MONITORED

        set_port_state(device.NetDiscoveryID, "tcp", 22, PortState.SUGGESTED)
        db.session.commit()

        assert port(device, 22).Promotion_Held is True
        assert promote_identified_ports() == 0
        assert port(device, 22).Port_State is PortState.SUGGESTED

    def test_a_held_port_is_not_picked_up_by_the_reconciler_either(self, db_session, admin_user, status, writer):
        device = new_device(status, tcp={22: "ssh"})
        add_plugin("check_ssh")
        reconcile_plugin_monitoring(admin_user.UserID)
        set_port_state(device.NetDiscoveryID, "tcp", 22, PortState.SUGGESTED)
        db.session.commit()

        result = reconcile_plugin_monitoring(admin_user.UserID)

        assert result["promoted"] == 0 and auto_names() == []
        assert port(device, 22).Port_State is PortState.SUGGESTED

    def test_it_stays_held_through_later_scans(self, db_session, status):
        device = new_device(status, tcp={22: "ssh"})
        add_plugin("check_ssh")
        set_port_state(device.NetDiscoveryID, "tcp", 22, PortState.SUGGESTED)
        db.session.commit()

        process_device_ports(device, {"tcp": {"22": {"service_name": "ssh", "identified_by": "FINGERPRINT"}}})
        db.session.commit()

        assert port(device, 22).Port_State is PortState.SUGGESTED and port(device, 22).Promotion_Held is True

    def test_a_guess_confirmed_later_does_not_override_the_hold(self, db_session, status):
        device = new_device(status)
        add_plugin("check_ssh")
        process_device_ports(device, {"tcp": {"22": {"service_name": "ssh", "identified_by": "PORT_HINT"}}})
        db.session.commit()
        set_port_state(device.NetDiscoveryID, "tcp", 22, PortState.SUGGESTED)
        db.session.commit()

        process_device_ports(device, {"tcp": {"22": {"service_name": "ssh", "identified_by": "FINGERPRINT"}}})
        db.session.commit()

        assert port(device, 22).Port_State is PortState.SUGGESTED

    def test_monitoring_the_port_by_hand_releases_it(self, db_session, admin_user, status, writer):
        device = new_device(status, tcp={22: "ssh"})
        add_plugin("check_ssh")
        set_port_state(device.NetDiscoveryID, "tcp", 22, PortState.SUGGESTED)
        db.session.commit()

        set_port_state(device.NetDiscoveryID, "tcp", 22, PortState.MONITORED)
        db.session.commit()

        assert port(device, 22).Promotion_Held is False and port(device, 22).Port_State is PortState.MONITORED
        reconcile_plugin_monitoring(admin_user.UserID)
        assert auto_names() == ["ssh-22-tcp"]

    def test_acknowledging_a_mismatch_releases_it(self, db_session, status):
        device = new_device(status, tcp={22: "http"})
        row = port(device, 22)
        row.Expected_Service_Name, row.Promotion_Held = "ssh", True
        add_plugin("check_http")
        db.session.commit()

        acknowledge_port_mismatch(device.NetDiscoveryID, "tcp", 22)
        db.session.commit()

        assert port(device, 22).Promotion_Held is False and port(device, 22).Port_State is PortState.MONITORED

    def test_ignoring_or_archiving_does_not_change_the_hold(self, db_session, status):
        device = new_device(status, tcp={22: "ssh", 80: "http"})
        port(device, 22).Promotion_Held = True
        db.session.commit()

        set_port_state(device.NetDiscoveryID, "tcp", 22, PortState.IGNORED)
        set_port_state(device.NetDiscoveryID, "tcp", 80, PortState.ARCHIVED)
        db.session.commit()

        assert port(device, 22).Promotion_Held is True and port(device, 80).Promotion_Held is False

    def test_pinning_a_service_does_not_release_it(self, db_session, status):
        device = new_device(status, tcp={22: "ssh"})
        port(device, 22).Promotion_Held = True
        db.session.commit()

        pin_port_service(device.NetDiscoveryID, "tcp", 22, "ssh")
        db.session.commit()

        assert port(device, 22).Promotion_Held is True

    def test_a_port_in_other_states_is_never_held_by_default(self, db_session, status):
        device = new_device(status, tcp={22: "ssh"})
        assert port(device, 22).Promotion_Held is False


# ==========================================================
# PORTS NOBODY HELD STILL FOLLOW THE PLUGIN
# ==========================================================

class TestUnheldPortsKeepTheDesignedBehaviour:

    def test_a_port_found_by_a_scan_is_not_held(self, db_session, status):
        device = new_device(status, tcp={3306: "mysql"})
        assert port(device, 3306).Promotion_Held is False and port(device, 3306).Port_State is PortState.SUGGESTED

    def test_enabling_a_plugin_still_attaches_the_ports_it_checks(self, db_session, admin_user, status, writer):
        new_device(status, "10.0.0.5", MAC_1, tcp={3306: "mysql"})
        new_device(status, "10.0.0.6", MAC_2, tcp={3306: "mysql"})
        add_plugin("check_mysql")

        result = reconcile_plugin_monitoring(admin_user.UserID)

        assert result["promoted"] == 2

    def test_the_generic_check_still_picks_up_ports_nobody_held(self, db_session, admin_user, status, writer):
        device = new_device(status, tcp={9100: "printer"})
        add_plugin("check_tcp")

        reconcile_plugin_monitoring(admin_user.UserID)

        assert port(device, 9100).Port_State is PortState.MONITORED


# ==========================================================
# HOLDING WHAT AN UPGRADE WOULD PROMOTE
# ==========================================================

class TestHoldPromotablePorts:

    def test_it_holds_exactly_the_suggestions_the_enabled_plugins_would_promote(self, db_session, status):
        device = new_device(status, tcp={22: "ssh", 3306: "mysql", 9100: "printer"})
        add_plugin("check_ssh")
        add_plugin("check_tcp")                  # the generic plugin, enabled to keep something running

        held = hold_promotable_ports()
        db.session.commit()

        assert held == 2
        assert port(device, 22).Promotion_Held and port(device, 9100).Promotion_Held
        assert port(device, 3306).Promotion_Held is False       # check_mysql is not enabled

    def test_a_hint_only_port_and_a_flagged_port_are_not_held(self, db_session, status):
        device = new_device(status, tcp={22: "ssh", 80: "http"})
        port(device, 22).Identified_By = None
        process_device_ports(device, {"tcp": {"22": {"service_name": "ssh", "identified_by": "PORT_HINT"}}})
        port(device, 80).Expected_Service_Name = "ssh"
        add_plugin("check_ssh")
        add_plugin("check_http")
        db.session.commit()

        assert hold_promotable_ports() == 0

    def test_monitored_ports_are_not_held(self, db_session, status):
        device = new_device(status, tcp={22: "ssh"})
        monitored_before_upgrade(device, 22, "ssh")
        add_plugin("check_ssh")

        assert hold_promotable_ports() == 0 and port(device, 22).Promotion_Held is False

    def test_a_udp_suggestion_is_held_when_a_plugin_speaks_its_protocol(self, db_session, status):
        device = new_device(status, udp={53: "dns", 9999: "mystery"})
        add_plugin("check_dns")

        assert hold_promotable_ports() == 1
        assert udp_port(device, 53).Promotion_Held is True and udp_port(device, 9999).Promotion_Held is False

    def test_holding_twice_is_harmless(self, db_session, status):
        new_device(status, tcp={22: "ssh"})
        add_plugin("check_ssh")
        assert hold_promotable_ports() == 1
        db.session.commit()
        assert hold_promotable_ports() == 0       # already held, so no longer promotable


class TestFirstInventoryScanHolds:
    """An install that never scanned its plugins gets its backing plugins enabled; suggestions are held."""

    def test_the_continuity_step_enables_what_runs_and_holds_what_would_have_started(self, db_session, status):
        device = new_device(status, tcp={22: "ssh", 80: "http", 3306: "mysql", 9100: "printer"})
        monitored_before_upgrade(device, 22, "ssh")
        monitored_before_upgrade(device, 80, "http")
        port(device, 9100).Plugin_Name = None
        row = port(device, 80)
        row.Plugin_Name = "tcp"                   # monitored by the generic check
        for name in ("check_ssh", "check_http", "check_tcp", "check_mysql"):
            add_plugin(name, PluginStatus.READY)

        enabled = enable_plugins_backing_monitored_ports()
        db.session.commit()

        assert enabled == ["check_ssh", "check_tcp"]
        assert port(device, 9100).Promotion_Held is True          # check_tcp would have picked it up
        assert port(device, 3306).Promotion_Held is False         # check_mysql was never on
        assert port(device, 3306).Port_State is PortState.SUGGESTED

    def test_after_that_the_reconcile_starts_nothing_new_but_an_admin_can(self, db_session, admin_user, status, writer):
        device = new_device(status, tcp={22: "ssh", 9100: "printer"})
        monitored_before_upgrade(device, 22, "tcp")
        add_plugin("check_tcp", PluginStatus.READY)
        enable_plugins_backing_monitored_ports()
        db.session.commit()

        first = reconcile_plugin_monitoring(admin_user.UserID)
        assert first["promoted"] == 0 and auto_names() == ["ssh-22-tcp"]

        set_port_state(device.NetDiscoveryID, "tcp", 9100, PortState.MONITORED)
        db.session.commit()
        reconcile_plugin_monitoring(admin_user.UserID)

        assert auto_names() == ["printer-9100-tcp", "ssh-22-tcp"]


# ==========================================================
# WHAT THE ENABLE PREVIEW SAYS
# ==========================================================

class TestPreviewAndPromotable:

    def test_promotable_ports_leave_held_ones_out_unless_asked(self, db_session, status):
        device = new_device(status, tcp={22: "ssh", 80: "http"})
        port(device, 22).Promotion_Held = True
        db.session.commit()
        enabled = {"check_ssh", "check_http"}

        assert [p.Port_Number for _, p in promotable_ports(enabled)] == [80]
        assert sorted(p.Port_Number for _, p in promotable_ports(enabled, include_held=True)) == [22, 80]

    def test_should_auto_monitor_can_ignore_the_hold(self, db_session, status):
        device = new_device(status, tcp={22: "ssh"})
        port(device, 22).Promotion_Held = True
        db.session.commit()
        args = ("ssh", port(device, 22).Identified_By, "tcp", {"check_ssh"}, port(device, 22))

        assert should_auto_monitor(*args) is False
        assert should_auto_monitor(*args, ignore_hold=True) is True

    def test_the_preview_does_not_count_held_ports_and_reports_them(self, db_session, status):
        new_device(status, "10.0.0.5", MAC_1, tcp={22: "ssh"})
        held = new_device(status, "10.0.0.6", MAC_2, tcp={22: "ssh"})
        port(held, 22).Promotion_Held = True
        add_plugin("check_ssh", PluginStatus.INSTALLED)
        db.session.commit()

        result = preview_enable("check_ssh")

        assert result == {"matched_services": 1, "matched_devices": 1, "held_ports": 1}

    def test_a_held_port_of_another_plugin_is_not_reported_for_this_one(self, db_session, status):
        device = new_device(status, tcp={80: "http"})
        port(device, 80).Promotion_Held = True
        db.session.commit()

        assert preview_enable("check_ssh")["held_ports"] == 0

    def test_the_preview_does_not_change_the_hold(self, db_session, status):
        device = new_device(status, tcp={22: "ssh"})
        port(device, 22).Promotion_Held = True
        db.session.commit()

        preview_enable("check_ssh")
        db.session.commit()

        assert port(device, 22).Promotion_Held is True


class TestPreviewRoute:

    def test_the_message_says_how_many_ports_are_held_back(self, logged_in_client, db_session, status):
        new_device(status, "10.0.0.5", MAC_1, tcp={22: "ssh"})
        held = new_device(status, "10.0.0.6", MAC_2, tcp={22: "ssh"})
        port(held, 22).Promotion_Held = True
        plugin = add_plugin("check_ssh", PluginStatus.INSTALLED)
        db.session.commit()

        data = logged_in_client.get(f"/api/plugin/{plugin.PluginID}/enable-preview").get_json()["data"]

        assert (data["matched_services"], data["held_ports"]) == (1, 1)
        assert "Enabling will monitor 1 service(s) on 1 device(s)." in data["message"]
        assert "1 identified port(s) are held back" in data["message"]

    def test_no_held_ports_no_extra_sentence(self, logged_in_client, db_session, status):
        new_device(status, tcp={22: "ssh"})
        plugin = add_plugin("check_ssh", PluginStatus.INSTALLED)

        data = logged_in_client.get(f"/api/plugin/{plugin.PluginID}/enable-preview").get_json()["data"]

        assert data["held_ports"] == 0 and "held back" not in data["message"]


# ==========================================================
# THE PORT-EDIT ROUTE
# ==========================================================

class TestPortRoute:

    @pytest.fixture(autouse=True)
    def no_nagios(self):
        with patch("app.api.system.device_identity.reconcile_plugin_monitoring",
                   return_value={"success": True, "changed": True, "message": "ok"}):
            yield

    def put(self, client, device, number, body):
        return client.put(f"/api/system/hosts/{device.NetDiscoveryID}/ports/tcp/{number}", json=body)

    def test_suggested_holds_and_monitored_releases_and_the_response_says_so(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={22: "ssh"})

        held = self.put(logged_in_client, device, 22, {"state": "SUGGESTED"}).get_json()["data"]["port"]
        released = self.put(logged_in_client, device, 22, {"state": "MONITORED"}).get_json()["data"]["port"]

        assert held["promotion_held"] is True and held["state"] == "SUGGESTED"
        assert released["promotion_held"] is False and released["state"] == "MONITORED"

    def test_acknowledging_releases_it_in_the_response(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={22: "http"})
        row = port(device, 22)
        row.Expected_Service_Name, row.Promotion_Held = "ssh", True
        db.session.commit()

        result = self.put(logged_in_client, device, 22, {"acknowledge_mismatch": True}).get_json()["data"]["port"]

        assert result["promotion_held"] is False
