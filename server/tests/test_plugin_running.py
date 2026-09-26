"""
Tests for GET /api/plugin/running — the monitoring checks currently live
in Nagios (applied PluginConfiguration rows), shown on the Plugin
Manager's "Currently Running" tab.
"""
from app.logging.user_activity import create_user_log
from app.plugin_models import (
    Plugin,
    PluginConfiguration,
    PluginConfigurationStatus,
    PluginSource,
    PluginStatus,
    PluginType,
)
from app.system_models import DiscoveryStatus, NetworkDiscovery, NetworkDiscoveryStatus


def make_target(db_session, user, hostname, ip):
    log = create_user_log(user.UserID, "Discovering Network Hosts")
    status = NetworkDiscoveryStatus(Status=DiscoveryStatus.SUCCESS, Progress=100, Message="done", LogID=log.LogID)
    db_session.session.add(status)
    db_session.session.flush()
    device = NetworkDiscovery(
        Hostname=hostname, IP_Address=ip, Network="192.168.130.0/24", DiscoveryStatusID=status.DiscoveryStatusID,
    )
    db_session.session.add(device)
    db_session.session.flush()
    return device


def make_plugin(db_session, name, status=PluginStatus.ACTIVE):
    plugin = Plugin(Name=name, Plugin_Type=PluginType.NAGIOS, Source=PluginSource.BASELINE_ISO, Status=status)
    db_session.session.add(plugin)
    db_session.session.flush()
    return plugin


def make_config(db_session, plugin, target, service, status=PluginConfigurationStatus.APPLIED):
    config = PluginConfiguration(
        PluginID=plugin.PluginID,
        NetDiscoveryID=target.NetDiscoveryID,
        Service_Description=service,
        Status=status,
    )
    db_session.session.add(config)
    db_session.session.commit()
    return config


def running(client, **params):
    resp = client.get("/api/plugin/running", query_string=params)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["data"]


class TestRunningChecks:
    def test_requires_login(self, client, db_session):
        assert client.get("/api/plugin/running").status_code == 401

    def test_requires_plugin_view_permission(self, limited_client, db_session):
        assert limited_client.get("/api/plugin/running").status_code == 403

    def test_empty_when_nothing_applied(self, logged_in_client, db_session):
        data = running(logged_in_client)

        assert data["items"] == []
        assert data["total"] == 0

    def test_lists_only_applied_checks(self, logged_in_client, db_session, admin_user):
        router = make_target(db_session, admin_user, "router-01", "192.168.130.1")
        snmp = make_plugin(db_session, "check_snmp")
        tcp = make_plugin(db_session, "check_tcp", status=PluginStatus.ENABLED)
        make_config(db_session, snmp, router, "Uptime")
        make_config(db_session, tcp, router, "NCPA port", status=PluginConfigurationStatus.PENDING)
        make_config(db_session, tcp, router, "SSH port", status=PluginConfigurationStatus.FAILED)

        data = running(logged_in_client)

        assert data["total"] == 1
        item = data["items"][0]
        assert item["plugin"]["name"] == "check_snmp"
        assert item["plugin"]["status"] == "Active"
        assert item["target"] == {"id": router.NetDiscoveryID, "hostname": "router-01", "ip_address": "192.168.130.1"}
        assert item["service_description"] == "Uptime"
        assert item["applied_at"]

    def test_one_row_per_target(self, logged_in_client, db_session, admin_user):
        router = make_target(db_session, admin_user, "router-01", "192.168.130.1")
        switch = make_target(db_session, admin_user, "switch-01", "192.168.130.2")
        snmp = make_plugin(db_session, "check_snmp")
        make_config(db_session, snmp, router, "Uptime")
        make_config(db_session, snmp, switch, "Uptime")

        data = running(logged_in_client)

        assert [item["target"]["hostname"] for item in data["items"]] == ["router-01", "switch-01"]

    def test_search_matches_plugin_device_and_service(self, logged_in_client, db_session, admin_user):
        router = make_target(db_session, admin_user, "router-01", "192.168.130.1")
        switch = make_target(db_session, admin_user, "switch-01", "192.168.130.2")
        snmp = make_plugin(db_session, "check_snmp")
        ping = make_plugin(db_session, "check_ping")
        make_config(db_session, snmp, router, "Uptime")
        make_config(db_session, ping, switch, "Latency")

        assert running(logged_in_client, search="snmp")["total"] == 1
        assert running(logged_in_client, search="switch")["items"][0]["plugin"]["name"] == "check_ping"
        assert running(logged_in_client, search="130.1")["items"][0]["target"]["hostname"] == "router-01"
        assert running(logged_in_client, search="latency")["total"] == 1
        assert running(logged_in_client, search="nothing-matches")["total"] == 0

    def test_paginates(self, logged_in_client, db_session, admin_user):
        router = make_target(db_session, admin_user, "router-01", "192.168.130.1")
        for i in range(3):
            make_config(db_session, make_plugin(db_session, f"check_{i}"), router, "Check")

        data = running(logged_in_client, page=2, per_page=2)

        assert data["total"] == 3
        assert data["pages"] == 2
        assert len(data["items"]) == 1
        assert data["has_prev"] is True

    def test_rejects_bad_pagination(self, logged_in_client, db_session):
        assert logged_in_client.get("/api/plugin/running?page=0").status_code == 400
        assert logged_in_client.get("/api/plugin/running?per_page=500").status_code == 400
