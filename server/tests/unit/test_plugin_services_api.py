"""
tests/unit/test_plugin_services_api.py — Phase 4 of plugin-driven monitoring:
the service-driven Plugin Manager API.

Covers which plugins can be enabled, the enable preview, the inventory's
service_driven and usage fields, the per-plugin list of monitored services with
live status, stopping and resuming one port, the disable rollback, and that the
manual apply routes and the Currently Running route are gone. Nagios is never
run: the reconciler is replaced at its module boundary unless a test needs the
real one with its single writer mocked.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from app import db
from app.api.plugin import service
from app.api.plugin.reconcile import reconcile_plugin_monitoring
from app.nagios.status import insert_service_status_data
from app.network_discovery.plugin_registry import is_service_driven, service_driven_plugin_names
from app.plugin_models import (
    Plugin,
    PluginActionResult,
    PluginConfiguration,
    PluginConfigurationOrigin,
    PluginHistory,
    PluginHistoryAction,
    PluginSource,
    PluginStatus,
    PluginType,
)
from app.system_models import Open_TCP_Services, PortState
from tests.support.identity_helpers import MAC_1, MAC_2, NET, make_status, run_scan, scan

APPLIED = ("applied", "New host.cfg applied.")


@pytest.fixture
def status(db_session, admin_user):
    return make_status(db_session, admin_user)


@pytest.fixture
def writer():
    """The single Nagios writer, replaced so no config is validated or reloaded."""
    with patch("app.api.plugin.reconcile.regenerate_and_apply_config_status", return_value=APPLIED) as mock:
        yield mock


@pytest.fixture
def nagios_valid():
    with patch("app.api.plugin.service.validate_nagios_configuration", return_value=(True, "ok")):
        yield


def add_plugin(name, plugin_status=PluginStatus.INSTALLED):
    plugin = Plugin(Name=name, Plugin_Type=PluginType.NAGIOS, Source=PluginSource.BASELINE_ISO, Status=plugin_status)
    db.session.add(plugin)
    db.session.commit()
    return plugin


def new_device(status, ip="10.0.0.5", mac=MAC_1, **services):
    return run_scan(db, status, scan(ip, mac=mac, **services))[(NET, ip)]


def port(device, number):
    return db.session.scalar(sa.select(Open_TCP_Services).where(
        Open_TCP_Services.NetDiscoveryID == device.NetDiscoveryID, Open_TCP_Services.Port_Number == number))


def auto_rows():
    return db.session.scalars(sa.select(PluginConfiguration).where(
        PluginConfiguration.Origin == PluginConfigurationOrigin.AUTO)).all()


def record_result(hostname, service_name, *, status="0", output="SSH OK - 0.012s response", checked_ago=timedelta(minutes=1),
                  interval=timedelta(minutes=5)):
    """Store a Nagios result for a service as the poller would, checked checked_ago before now."""
    now = datetime.now(timezone.utc)
    last = now - checked_ago

    def ms(moment):
        return int(moment.timestamp() * 1000)

    insert_service_status_data(hostname, service_name, {
        "check_command": "pinpoint_nd_ssh!22!", "status": status, "plugin_output": output, "state_type": "1",
        "last_update": ms(last), "last_check": ms(last), "next_check": ms(last + interval),
        "current_attempt": 1, "max_attempts": 3, "acknowledgement_type": "none",
        "is_flapping": False, "notifications_enabled": True,
    })
    db.session.commit()


# ==========================================================
# WHICH PLUGINS ARE SERVICE-DRIVEN
# ==========================================================

class TestServiceDriven:

    def test_the_plugins_that_check_a_discovered_service_are_service_driven(self):
        assert {"check_ssh", "check_http", "check_snmp", "check_ncpa", "check_tcp", "check_dns",
                "check_ntp_time", "check_ftp", "check_smtp", "check_mysql", "check_udp"} <= service_driven_plugin_names()

    @pytest.mark.parametrize("name", ["check_ping", "check_load", "check_disk", "check_dummy", "check_custom"])
    def test_plugins_that_check_no_port_are_not(self, name):
        assert is_service_driven(name) is False

    def test_enabling_a_plugin_that_checks_no_port_is_refused_and_changes_nothing(self, logged_in_client, db_session, nagios_valid):
        ping = add_plugin("check_ping", PluginStatus.READY)

        resp = logged_in_client.post(f"/api/plugin/{ping.PluginID}/enable")

        assert resp.status_code == 409
        assert "does not check a discovered service" in resp.get_json()["message"]
        db_session.session.refresh(ping)
        assert ping.Status is PluginStatus.READY
        assert db_session.session.scalars(sa.select(PluginHistory)).all() == []

    def test_a_plugin_enabled_before_this_rule_can_still_be_disabled(self, logged_in_client, db_session, nagios_valid, writer):
        ping = add_plugin("check_ping", PluginStatus.ACTIVE)

        resp = logged_in_client.post(f"/api/plugin/{ping.PluginID}/disable")

        assert resp.status_code == 200
        db_session.session.refresh(ping)
        assert ping.Status is PluginStatus.DISABLED

    def test_inventory_and_details_say_whether_a_plugin_is_service_driven(self, logged_in_client, db_session):
        ssh, ping = add_plugin("check_ssh"), add_plugin("check_ping")

        items = {item["name"]: item for item in logged_in_client.get("/api/plugin").get_json()["data"]["items"]}
        details = logged_in_client.get(f"/api/plugin/{ping.PluginID}").get_json()["data"]

        assert items["check_ssh"]["service_driven"] is True
        assert items["check_ping"]["service_driven"] is False
        assert details["service_driven"] is False
        assert logged_in_client.get(f"/api/plugin/{ssh.PluginID}").get_json()["data"]["service_driven"] is True

    def test_inventory_rows_count_the_services_and_devices_behind_a_plugin(self, logged_in_client, db_session, admin_user, status, writer):
        new_device(status, "10.0.0.5", MAC_1, tcp={22: "ssh"})
        new_device(status, "10.0.0.6", MAC_2, tcp={22: "ssh"})
        add_plugin("check_ssh", PluginStatus.ENABLED)
        add_plugin("check_http", PluginStatus.ENABLED)
        reconcile_plugin_monitoring(admin_user.UserID)

        items = {item["name"]: item for item in logged_in_client.get("/api/plugin").get_json()["data"]["items"]}

        assert items["check_ssh"]["monitoring_usage"] == {"services": 2, "devices": 2}
        assert items["check_http"]["monitoring_usage"] == {"services": 0, "devices": 0}


# ==========================================================
# ENABLE PREVIEW
# ==========================================================

class TestEnablePreview:

    def get(self, client, plugin):
        return client.get(f"/api/plugin/{plugin.PluginID}/enable-preview")

    def test_requires_login_and_permission(self, client, limited_client, db_session):
        ssh = add_plugin("check_ssh")
        assert limited_client.get(f"/api/plugin/{ssh.PluginID}/enable-preview").status_code == 403

    def test_requires_login(self, client, db_session):
        ssh = add_plugin("check_ssh")
        assert client.get(f"/api/plugin/{ssh.PluginID}/enable-preview").status_code in (401, 302)

    def test_unknown_plugin(self, logged_in_client, db_session):
        assert logged_in_client.get("/api/plugin/999999/enable-preview").status_code == 404

    def test_counts_the_services_and_devices_it_would_attach(self, logged_in_client, db_session, status):
        new_device(status, "10.0.0.5", MAC_1, tcp={22: "ssh", 80: "http"})
        new_device(status, "10.0.0.6", MAC_2, tcp={22: "ssh"})
        ssh = add_plugin("check_ssh")

        data = self.get(logged_in_client, ssh).get_json()["data"]

        assert (data["matched_services"], data["matched_devices"]) == (2, 2)
        assert data["service_driven"] is True and data["already_enabled"] is False
        assert data["message"] == "Enabling will monitor 2 service(s) on 2 device(s)."

    def test_it_is_read_only(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={22: "ssh"})
        ssh = add_plugin("check_ssh")

        self.get(logged_in_client, ssh)

        db_session.session.refresh(ssh)
        assert ssh.Status is PluginStatus.INSTALLED
        assert port(device, 22).Port_State is PortState.SUGGESTED       # not promoted by looking
        assert auto_rows() == []

    def test_a_plugin_with_nothing_to_match_says_so(self, logged_in_client, db_session, status):
        new_device(status, tcp={22: "ssh"})
        snmp = add_plugin("check_snmp")

        data = self.get(logged_in_client, snmp).get_json()["data"]

        assert (data["matched_services"], data["matched_devices"]) == (0, 0)
        assert data["message"].startswith("No matching services yet")

    def test_multi_metric_plugins_count_every_service(self, app, logged_in_client, db_session, status):
        new_device(status, udp={161: "snmp"})
        snmp = add_plugin("check_snmp")

        data = self.get(logged_in_client, snmp).get_json()["data"]

        assert data["matched_services"] == len(app.config["SNMP_OIDS"]) and data["matched_devices"] == 1

    def test_already_monitored_ports_are_counted_too(self, logged_in_client, db_session, status, admin_user, writer):
        new_device(status, tcp={22: "ssh"})
        ssh = add_plugin("check_ssh", PluginStatus.ENABLED)
        reconcile_plugin_monitoring(admin_user.UserID)

        data = self.get(logged_in_client, ssh).get_json()["data"]

        assert data["already_enabled"] is True and data["matched_services"] == 1

    def test_a_flagged_or_guessed_port_is_not_counted(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={22: "http"})
        port(device, 22).Expected_Service_Name = "ssh"
        db_session.session.commit()
        http = add_plugin("check_http")

        assert self.get(logged_in_client, http).get_json()["data"]["matched_services"] == 0

    def test_the_generic_tcp_plugin_counts_every_identified_port_without_a_plugin_of_its_own(self, logged_in_client, db_session, status):
        new_device(status, tcp={9100: "printer", 22: "ssh"})
        tcp = add_plugin("check_tcp")

        assert self.get(logged_in_client, tcp).get_json()["data"]["matched_services"] == 1

    def test_a_plugin_that_checks_no_port_reports_zero(self, logged_in_client, db_session, status):
        new_device(status, tcp={22: "ssh"})
        ping = add_plugin("check_ping")

        data = self.get(logged_in_client, ping).get_json()["data"]

        assert data["service_driven"] is False and data["matched_services"] == 0


# ==========================================================
# MONITORED SERVICES WITH LIVE STATUS
# ==========================================================

class TestPluginServices:

    @pytest.fixture
    def attached(self, db_session, admin_user, status, writer):
        device = new_device(status, "10.0.0.5", MAC_1, tcp={22: "ssh"})
        device.Nagios_Host_Name = "web-01"
        db_session.session.commit()
        ssh = add_plugin("check_ssh", PluginStatus.ENABLED)
        reconcile_plugin_monitoring(admin_user.UserID)
        return device, ssh

    def listing(self, client, plugin, **params):
        resp = client.get(f"/api/plugin/{plugin.PluginID}/services", query_string=params)
        assert resp.status_code == 200, resp.get_json()
        return resp.get_json()["data"]

    def test_requires_login_and_permission(self, client, limited_client, db_session):
        ssh = add_plugin("check_ssh")
        assert limited_client.get(f"/api/plugin/{ssh.PluginID}/services").status_code == 403

    def test_unknown_plugin_and_bad_paging(self, logged_in_client, db_session):
        ssh = add_plugin("check_ssh")
        assert logged_in_client.get("/api/plugin/999999/services").status_code == 404
        assert logged_in_client.get(f"/api/plugin/{ssh.PluginID}/services?page=0").status_code == 400
        assert logged_in_client.get(f"/api/plugin/{ssh.PluginID}/services?per_page=500").status_code == 400

    def test_a_row_names_the_service_device_port_and_running_since(self, logged_in_client, attached):
        device, ssh = attached

        data = self.listing(logged_in_client, ssh)

        (item,) = data["items"]
        assert item["service"] == "ssh-22-tcp"
        assert item["device"] == {"id": device.NetDiscoveryID, "hostname": "web-01", "ip_address": "10.0.0.5"}
        assert (item["port"], item["protocol"], item["metric"], item["monitored"]) == (22, "tcp", None, True)
        assert item["running_since"] is not None
        assert data["total"] == 1 and data["pages"] == 1

    def test_before_the_first_check_the_row_is_waiting(self, logged_in_client, attached):
        _, ssh = attached
        status = self.listing(logged_in_client, ssh)["items"][0]["status"]
        assert status["kind"] == "waiting" and status["state"] is None
        assert "Waiting for first check" in status["output"] and "every 5 minutes" in status["output"]

    def test_a_fresh_result_shows_its_state_and_output(self, logged_in_client, attached):
        _, ssh = attached
        record_result("web-01", "ssh-22-tcp")

        status = self.listing(logged_in_client, ssh)["items"][0]["status"]

        assert status["kind"] == "ok" and status["state"] == "OK"
        assert status["output"] == "SSH OK - 0.012s response" and status["last_check"]

    def test_a_critical_result_is_reported(self, logged_in_client, attached):
        _, ssh = attached
        record_result("web-01", "ssh-22-tcp", status="2", output="Connection refused")

        status = self.listing(logged_in_client, ssh)["items"][0]["status"]

        assert (status["kind"], status["state"], status["output"]) == ("critical", "CRITICAL", "Connection refused")

    def test_the_latest_result_wins(self, logged_in_client, attached):
        _, ssh = attached
        record_result("web-01", "ssh-22-tcp", status="2", output="old", checked_ago=timedelta(minutes=4))
        record_result("web-01", "ssh-22-tcp", status="0", output="new", checked_ago=timedelta(minutes=1))

        assert self.listing(logged_in_client, ssh)["items"][0]["status"]["output"] == "new"

    def test_a_result_older_than_three_check_intervals_is_stale(self, logged_in_client, attached):
        _, ssh = attached
        record_result("web-01", "ssh-22-tcp", checked_ago=timedelta(minutes=20))

        status = self.listing(logged_in_client, ssh)["items"][0]["status"]

        assert status["kind"] == "stale" and "No recent data" in status["output"]
        assert "Nagios may be down or paused" in status["output"]

    def test_a_result_just_inside_three_intervals_is_still_fresh(self, logged_in_client, attached):
        _, ssh = attached
        record_result("web-01", "ssh-22-tcp", checked_ago=timedelta(minutes=14))
        assert self.listing(logged_in_client, ssh)["items"][0]["status"]["kind"] == "ok"

    def test_other_hosts_and_services_do_not_leak_into_the_status(self, logged_in_client, attached):
        _, ssh = attached
        record_result("other-host", "ssh-22-tcp", output="not this one")
        record_result("web-01", "http-80-tcp", output="nor this")

        assert self.listing(logged_in_client, ssh)["items"][0]["status"]["kind"] == "waiting"

    def test_search_matches_service_device_and_ip(self, logged_in_client, db_session, admin_user, status, attached):
        _, ssh = attached
        other = new_device(status, "10.0.0.6", MAC_2, tcp={22: "ssh"})
        other.Nagios_Host_Name = "db-01"
        db_session.session.commit()
        reconcile_plugin_monitoring(admin_user.UserID)

        assert self.listing(logged_in_client, ssh)["total"] == 2
        assert [i["device"]["hostname"] for i in self.listing(logged_in_client, ssh, search="db-")["items"]] == ["db-01"]
        assert [i["device"]["hostname"] for i in self.listing(logged_in_client, ssh, search="10.0.0.5")["items"]] == ["web-01"]
        assert self.listing(logged_in_client, ssh, search="ssh-22")["total"] == 2
        assert self.listing(logged_in_client, ssh, search="nothing")["total"] == 0

    def test_pagination(self, logged_in_client, db_session, admin_user, status, attached):
        _, ssh = attached
        for i in range(2, 6):
            new_device(status, f"10.0.0.{i + 10}", f"00:11:22:33:44:{i:02x}", tcp={22: "ssh"})
        reconcile_plugin_monitoring(admin_user.UserID)

        first = self.listing(logged_in_client, ssh, per_page=2, page=1)
        last = self.listing(logged_in_client, ssh, per_page=2, page=3)

        assert (first["total"], first["pages"], first["has_next"], first["has_prev"]) == (5, 3, True, False)
        assert (len(last["items"]), last["has_next"], last["has_prev"]) == (1, False, True)

    def test_multi_metric_services_show_their_metric(self, app, logged_in_client, db_session, admin_user, status, writer):
        new_device(status, udp={161: "snmp"})
        snmp = add_plugin("check_snmp", PluginStatus.ENABLED)
        reconcile_plugin_monitoring(admin_user.UserID)

        items = self.listing(logged_in_client, snmp, per_page=100)["items"]

        assert len(items) == len(app.config["SNMP_OIDS"])
        assert all(item["metric"] and item["protocol"] == "udp" for item in items)

    def test_a_plugin_with_nothing_attached_lists_nothing(self, logged_in_client, db_session):
        ssh = add_plugin("check_ssh", PluginStatus.ENABLED)
        data = self.listing(logged_in_client, ssh)
        assert data["items"] == [] and data["total"] == 0 and data["pages"] == 1

    def test_a_stopped_port_is_listed_as_not_monitored(self, logged_in_client, attached, db_session, admin_user):
        device, ssh = attached
        port(device, 22).Port_State = PortState.IGNORED
        db_session.session.commit()
        reconcile_plugin_monitoring(admin_user.UserID)

        (item,) = self.listing(logged_in_client, ssh)["items"]

        assert item["monitored"] is False and item["id"] is None and item["port"] == 22
        assert item["status"] == {"kind": "stopped", "state": None, "last_check": None,
                                  "output": "Monitoring stopped for this device."}

    def test_a_port_ignored_before_it_was_ever_monitored_is_not_listed(self, logged_in_client, db_session, status):
        device = new_device(status, tcp={22: "ssh"})
        port(device, 22).Port_State = PortState.IGNORED
        db_session.session.commit()
        ssh = add_plugin("check_ssh", PluginStatus.ENABLED)

        assert self.listing(logged_in_client, ssh)["items"] == []

    def test_another_plugins_services_are_not_listed(self, logged_in_client, db_session, admin_user, status, writer):
        new_device(status, tcp={22: "ssh", 80: "http"})
        add_plugin("check_ssh", PluginStatus.ENABLED)
        http = add_plugin("check_http", PluginStatus.ENABLED)
        reconcile_plugin_monitoring(admin_user.UserID)

        assert [i["service"] for i in self.listing(logged_in_client, http)["items"]] == ["http-80-tcp"]


# ==========================================================
# STOP AND RESUME ONE PORT
# ==========================================================

class TestStopAndResume:

    @pytest.fixture
    def attached(self, db_session, admin_user, status, writer):
        device = new_device(status, tcp={22: "ssh"})
        ssh = add_plugin("check_ssh", PluginStatus.ENABLED)
        reconcile_plugin_monitoring(admin_user.UserID)
        return device, ssh

    def post(self, client, plugin, action, device, protocol="tcp", port_number=22):
        return client.post(f"/api/plugin/{plugin.PluginID}/services/{action}", json={
            "device_id": device.NetDiscoveryID, "protocol": protocol, "port": port_number,
        })

    def test_stop_ignores_the_port_removes_the_service_and_writes_history(self, logged_in_client, attached, db_session):
        device, ssh = attached

        resp = self.post(logged_in_client, ssh, "stop", device)

        assert resp.status_code == 200
        assert resp.get_json()["data"]["changed"] is True
        assert port(device, 22).Port_State is PortState.IGNORED
        assert auto_rows() == []
        history = db_session.session.scalars(
            sa.select(PluginHistory).where(PluginHistory.Action == PluginHistoryAction.CONFIGURE)
            .order_by(PluginHistory.PluginHistoryID.desc())).first()
        assert history.Result is PluginActionResult.SUCCESS and history.Message.startswith("Stopped monitoring tcp port 22 on")

    def test_resume_brings_the_service_back_with_its_frozen_plugin(self, logged_in_client, attached, db_session):
        device, ssh = attached
        self.post(logged_in_client, ssh, "stop", device)

        resp = self.post(logged_in_client, ssh, "resume", device)

        assert resp.status_code == 200 and resp.get_json()["data"]["changed"] is True
        assert port(device, 22).Port_State is PortState.MONITORED
        assert port(device, 22).Plugin_Name == "ssh"
        assert [row.Nagios_Service_Name for row in auto_rows()] == ["ssh-22-tcp"]

    def test_repeating_a_change_reports_no_change_and_does_not_touch_nagios(self, logged_in_client, attached, writer):
        device, ssh = attached
        self.post(logged_in_client, ssh, "stop", device)
        writer.reset_mock()

        again = self.post(logged_in_client, ssh, "stop", device)

        assert again.get_json()["data"]["changed"] is False
        writer.assert_not_called()
        assert self.post(logged_in_client, ssh, "resume", device).status_code == 200
        writer.reset_mock()
        assert self.post(logged_in_client, ssh, "resume", device).get_json()["data"]["changed"] is False

    def test_only_one_device_is_affected(self, logged_in_client, attached, db_session, admin_user, status):
        device, ssh = attached
        other = new_device(status, "10.0.0.6", MAC_2, tcp={22: "ssh"})
        reconcile_plugin_monitoring(admin_user.UserID)

        self.post(logged_in_client, ssh, "stop", device)

        assert [row.NetDiscoveryID for row in auto_rows()] == [other.NetDiscoveryID]

    def test_a_port_this_plugin_does_not_check_is_refused(self, logged_in_client, db_session, status, attached):
        device, ssh = attached
        new_device(status, "10.0.0.7", "00:11:22:33:44:77", tcp={80: "http"})
        other = db_session.session.scalars(sa.select(Open_TCP_Services).where(Open_TCP_Services.Port_Number == 80)).one()

        resp = logged_in_client.post(f"/api/plugin/{ssh.PluginID}/services/stop", json={
            "device_id": other.NetDiscoveryID, "protocol": "tcp", "port": 80})

        assert resp.status_code == 404
        assert "does not monitor" in resp.get_json()["message"]

    def test_a_missing_port_is_a_404(self, logged_in_client, attached):
        device, ssh = attached
        assert self.post(logged_in_client, ssh, "stop", device, port_number=2222).status_code == 404

    def test_an_unknown_plugin_is_a_404(self, logged_in_client, attached):
        device, _ = attached
        resp = logged_in_client.post("/api/plugin/999999/services/stop", json={
            "device_id": device.NetDiscoveryID, "protocol": "tcp", "port": 22})
        assert resp.status_code == 404

    def test_a_port_that_was_not_stopped_cannot_be_resumed_into_a_new_state(self, logged_in_client, attached, db_session):
        device, ssh = attached
        port(device, 22).Port_State = PortState.ARCHIVED
        db_session.session.commit()

        assert self.post(logged_in_client, ssh, "resume", device).status_code == 404

    @pytest.mark.parametrize("body", [
        {}, {"device_id": "x", "protocol": "tcp", "port": 22}, {"device_id": 1, "protocol": "icmp", "port": 22},
        {"device_id": 1, "protocol": "tcp", "port": 0}, {"device_id": 1, "protocol": "tcp", "port": "22"},
        {"device_id": True, "protocol": "tcp", "port": 22},
    ])
    def test_a_bad_body_is_a_400(self, logged_in_client, attached, body):
        _, ssh = attached
        assert logged_in_client.post(f"/api/plugin/{ssh.PluginID}/services/stop", json=body).status_code == 400

    def test_the_ncpa_port_of_a_deployed_agent_cannot_be_stopped(self, logged_in_client, db_session, admin_user, status, writer):
        from app.network_discovery.port_lifecycle import mark_ncpa_port
        from app.system_models import AgentStatus, NCPADeployment
        device = new_device(status, tcp={22: "ssh"})
        db_session.session.add(NCPADeployment(
            Token="t" * 32, Agent_Status=AgentStatus.DEPLOYED, NetworkDiscoveryID=device.NetDiscoveryID))
        mark_ncpa_port(device.NetDiscoveryID)
        db_session.session.commit()
        ncpa = add_plugin("check_ncpa", PluginStatus.ENABLED)
        reconcile_plugin_monitoring(admin_user.UserID)

        resp = logged_in_client.post(f"/api/plugin/{ncpa.PluginID}/services/stop", json={
            "device_id": device.NetDiscoveryID, "protocol": "tcp", "port": 5693})

        assert resp.status_code == 409 and "NCPA port" in resp.get_json()["message"]
        assert port(device, 5693).Port_State is PortState.MONITORED

    def test_permissions_stop_needs_disable_and_resume_needs_enable(self, limited_client, attached):
        device, ssh = attached
        assert self.post(limited_client, ssh, "stop", device).status_code == 403
        assert self.post(limited_client, ssh, "resume", device).status_code == 403

    def test_requires_login(self, client, attached):
        device, ssh = attached
        assert self.post(client, ssh, "stop", device).status_code in (401, 302)

    def test_a_config_nagios_rejects_puts_the_port_back_and_says_so(self, logged_in_client, attached, db_session):
        device, ssh = attached
        with patch("app.api.plugin.reconcile.regenerate_and_apply_config_status",
                   return_value=("failed", "Config failed to validate: bad directive")):
            resp = self.post(logged_in_client, ssh, "stop", device)

        assert resp.status_code == 409 and "bad directive" in resp.get_json()["message"]
        assert port(device, 22).Port_State is PortState.MONITORED
        assert len(auto_rows()) == 1
        last = db_session.session.scalars(
            sa.select(PluginHistory).order_by(PluginHistory.PluginHistoryID.desc())).first()
        assert last.Result is PluginActionResult.FAILED and "Could not stop monitoring" in last.Message

    def test_a_rejected_resume_leaves_the_port_stopped(self, logged_in_client, attached, db_session):
        device, ssh = attached
        self.post(logged_in_client, ssh, "stop", device)
        with patch("app.api.plugin.reconcile.regenerate_and_apply_config_status",
                   return_value=("failed", "nagios exploded")):
            resp = self.post(logged_in_client, ssh, "resume", device)

        assert resp.status_code == 409
        assert port(device, 22).Port_State is PortState.IGNORED
        assert auto_rows() == []


# ==========================================================
# ENABLE AND DISABLE ROLL BACK ON A REJECTED CONFIG
# ==========================================================

class TestEnableDisableWithNagios:

    def test_disable_that_nagios_rejects_leaves_the_plugin_on(self, logged_in_client, db_session, admin_user, status, nagios_valid, writer):
        new_device(status, tcp={22: "ssh"})
        ssh = add_plugin("check_ssh", PluginStatus.ENABLED)
        reconcile_plugin_monitoring(admin_user.UserID)
        assert ssh.Status is PluginStatus.ACTIVE

        with patch("app.api.plugin.reconcile.regenerate_and_apply_config_status",
                   return_value=("failed", "Config failed to validate: bad directive")):
            resp = logged_in_client.post(f"/api/plugin/{ssh.PluginID}/disable")

        assert resp.status_code == 409
        assert "still on" in resp.get_json()["message"] and "bad directive" in resp.get_json()["message"]
        db_session.session.refresh(ssh)
        assert ssh.Status is PluginStatus.ACTIVE
        assert len(auto_rows()) == 1
        last = db_session.session.scalars(
            sa.select(PluginHistory).order_by(PluginHistory.PluginHistoryID.desc())).first()
        assert last.Action is PluginHistoryAction.DISABLE and last.Result is PluginActionResult.FAILED

    def test_disable_removes_the_services_and_reports_it(self, logged_in_client, db_session, admin_user, status, nagios_valid, writer):
        new_device(status, tcp={22: "ssh"})
        ssh = add_plugin("check_ssh", PluginStatus.ENABLED)
        reconcile_plugin_monitoring(admin_user.UserID)

        resp = logged_in_client.post(f"/api/plugin/{ssh.PluginID}/disable")

        data = resp.get_json()["data"]
        assert resp.status_code == 200 and data["status"] == "Disabled" and data["auto_apply"]["removed"] == 1
        assert auto_rows() == []

    def test_disabling_an_already_disabled_plugin_does_not_touch_nagios(self, logged_in_client, db_session, nagios_valid, writer):
        ssh = add_plugin("check_ssh", PluginStatus.DISABLED)

        resp = logged_in_client.post(f"/api/plugin/{ssh.PluginID}/disable")

        assert resp.status_code == 200 and resp.get_json()["data"]["changed"] is False
        writer.assert_not_called()

    def test_enable_attaches_and_reports_the_counts(self, logged_in_client, db_session, status, nagios_valid, writer):
        new_device(status, "10.0.0.5", MAC_1, tcp={22: "ssh"})
        new_device(status, "10.0.0.6", MAC_2, tcp={22: "ssh"})
        ssh = add_plugin("check_ssh", PluginStatus.READY)

        data = logged_in_client.post(f"/api/plugin/{ssh.PluginID}/enable").get_json()["data"]

        assert data["status"] == "Active"
        assert (data["auto_apply"]["applied"], data["auto_apply"]["promoted"]) == (2, 2)

    def test_enable_that_nagios_rejects_keeps_the_plugin_enabled_and_says_why(self, logged_in_client, db_session, status, nagios_valid):
        new_device(status, tcp={22: "ssh"})
        ssh = add_plugin("check_ssh", PluginStatus.READY)

        with patch("app.api.plugin.reconcile.regenerate_and_apply_config_status",
                   return_value=("failed", "Config failed to validate: bad directive")):
            resp = logged_in_client.post(f"/api/plugin/{ssh.PluginID}/enable")

        data = resp.get_json()["data"]
        assert resp.status_code == 200 and data["status"] == "Enabled"
        assert data["auto_apply"]["success"] is False and "bad directive" in data["auto_apply"]["message"]
        assert auto_rows() == []


# ==========================================================
# THE MANUAL PATH IS GONE
# ==========================================================

class TestRemovedRoutes:

    @pytest.mark.parametrize("method, path", [
        ("get", "/api/plugin/running"),
        ("get", "/api/plugin/targets"),
        ("get", "/api/plugin/{id}/configurations"),
        ("post", "/api/plugin/{id}/configurations"),
    ])
    def test_the_manual_apply_and_running_routes_no_longer_exist(self, logged_in_client, db_session, method, path):
        ssh = add_plugin("check_ssh", PluginStatus.ENABLED)
        resp = getattr(logged_in_client, method)(path.format(id=ssh.PluginID), json={})
        assert resp.status_code in (404, 405)

    def test_the_manual_module_and_its_settings_are_gone(self, app):
        import importlib.util
        assert importlib.util.find_spec("app.api.plugin.monitoring_config") is None
        for key in ("PLUGIN_SERVICE_CFG", "PLUGIN_SERVICE_STAGING_DIR", "PLUGIN_SERVICE_BACKUP_DIR"):
            assert key not in app.config
        assert not hasattr(service, "apply_plugin_configuration")
        assert not hasattr(service, "get_running_checks")
