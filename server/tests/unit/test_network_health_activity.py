"""
tests/unit/test_network_health_activity.py
=====================================
Tests for app/api/system/network_health_activity.py.

Routes tested:
  GET /api/system/network-health/availability   (archivejson mocked)
  GET /api/system/network-health/system-activity
  GET /api/system/network-health/cpu
  GET /api/system/network-health/connections    (/proc/net/tcp faked)
  GET /api/system/network-health/insights
"""

from unittest.mock import patch

import pytest

from app.api.system import network_health_activity
from app.history_models import HostStateType, ServiceStateType

from tests.support.seed_helpers import (
    _ts,
    _make_host, _make_host_perf,
    _make_service, _make_service_perf,
    NCPA_CPU_SERVICE,
)

AVAILABILITY_TARGET = "app.api.system.network_health_activity.request_host_availability_range"


# ==========================================================
# Auth / permission guards
# ==========================================================

class TestActivityAuthGuards:
    ENDPOINTS = [
        "/api/system/network-health/availability",
        "/api/system/network-health/system-activity",
        "/api/system/network-health/cpu",
        "/api/system/network-health/connections",
        "/api/system/network-health/insights",
    ]

    @pytest.mark.parametrize("url", ENDPOINTS)
    def test_requires_login(self, client, db_session, url):
        assert client.get(url).status_code in (401, 302)

    @pytest.mark.parametrize("url", ENDPOINTS)
    def test_requires_permission(self, limited_client, db_session, url):
        assert limited_client.get(url).status_code == 403


# ==========================================================
# GET /api/system/network-health/availability
# ==========================================================

def host_row(up, down=0, unreachable=0, nodata=0):
    return {
        "name": "h", "time_up": up, "time_down": down, "time_unreachable": unreachable,
        "time_indeterminate_nodata": nodata, "time_indeterminate_notrunning": 0,
    }


class TestAvailability:

    def test_daily_and_overall_percentages(self, logged_in_client, db_session):
        # Day 1: 50% up; day 2: 100% up (no-data time ignored).
        days = iter([
            [host_row(up=43200, down=43200)],
            [host_row(up=40000, nodata=46400), host_row(up=86400)],
        ])
        with patch(AVAILABILITY_TARGET, side_effect=lambda s, e: next(days)) as mock:
            resp = logged_in_client.get("/api/system/network-health/availability?days=2")

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert mock.call_count == 2
        assert [d["availability_pct"] for d in data["daily"]] == [50.0, 100.0]
        assert data["change_pct"] == 50.0
        assert data["trend_pct"] == 50.0
        # 169,600 up out of 212,800 known seconds.
        assert data["availability_pct"] == 79.7

    def test_days_are_consecutive_24h_windows_ending_now(self, logged_in_client, db_session):
        with patch(AVAILABILITY_TARGET, return_value=[]) as mock:
            logged_in_client.get("/api/system/network-health/availability?days=3")
        windows = [call.args for call in mock.call_args_list]
        assert all(end - start == 86400 for start, end in windows)
        assert windows[0][1] == windows[1][0] and windows[1][1] == windows[2][0]

    def test_no_known_time_gives_null(self, logged_in_client, db_session):
        with patch(AVAILABILITY_TARGET, return_value=[host_row(up=0, nodata=86400)]):
            data = logged_in_client.get("/api/system/network-health/availability").get_json()["data"]
        assert data["days"] == 7
        assert data["availability_pct"] is None
        assert data["change_pct"] is None
        assert data["trend_pct"] is None

    def test_nagios_unreachable_returns_502(self, logged_in_client, db_session):
        with patch(AVAILABILITY_TARGET, return_value=None):
            resp = logged_in_client.get("/api/system/network-health/availability")
        assert resp.status_code == 502

    @pytest.mark.parametrize("days", [0, 31, "abc"])
    def test_invalid_days(self, logged_in_client, db_session, days):
        resp = logged_in_client.get(f"/api/system/network-health/availability?days={days}")
        assert resp.status_code == 400


# ==========================================================
# GET /api/system/network-health/system-activity
# ==========================================================

class TestSystemActivity:

    def test_null_sections_without_checks(self, logged_in_client, db_session):
        data = logged_in_client.get("/api/system/network-health/system-activity").get_json()["data"]
        assert data == {"processes": None, "users": None}

    def test_process_and_user_counts(self, logged_in_client, db_session):
        # localhost runs a total and a zombie process check; the total wins.
        total = _make_service(db_session, "localhost", "Total Processes", check_command="check_local_procs")
        _make_service_perf(db_session, total, "procs", 200)
        zombie = _make_service(db_session, "localhost", "Zombie Processes",
                               ServiceStateType.WARNING, check_command="check_local_procs")
        _make_service_perf(db_session, zombie, "procs", 3)
        web = _make_service(db_session, "web", "Total Processes", check_command="check_local_procs")
        _make_service_perf(db_session, web, "procs", 100)

        # Users: an hour ago 1 + 1, now 3 + 2.
        for host, before, now in (("localhost", 1, 3), ("web", 1, 2)):
            old = _make_service(db_session, host, "Current Users", ts=_ts(-7200), check_command="check_local_users")
            _make_service_perf(db_session, old, "users", before)
            new = _make_service(db_session, host, "Current Users", check_command="check_local_users")
            _make_service_perf(db_session, new, "users", now)
        db_session.session.commit()

        data = logged_in_client.get("/api/system/network-health/system-activity").get_json()["data"]
        procs = data["processes"]
        assert procs["device_count"] == 2
        assert procs["total"] == 300
        assert procs["avg_per_device"] == 150.0
        assert procs["state"] == "warning"
        assert procs["peak_24h"] == {"hostname": "localhost", "count": 200}

        users = data["users"]
        assert users == {
            "device_count": 2, "total": 5, "min_per_device": 2, "max_per_device": 3, "change_1h": 3,
        }

    def test_user_change_null_without_older_data(self, logged_in_client, db_session):
        svc = _make_service(db_session, "localhost", "Current Users", check_command="check_local_users")
        _make_service_perf(db_session, svc, "users", 2)
        db_session.session.commit()
        data = logged_in_client.get("/api/system/network-health/system-activity").get_json()["data"]
        assert data["users"]["change_1h"] is None


# ==========================================================
# GET /api/system/network-health/cpu
# ==========================================================

class TestCpu:

    def seed_cpu(self, db_session, hostname, value):
        svc = _make_service(db_session, hostname, NCPA_CPU_SERVICE)
        _make_service_perf(db_session, svc, "percent", value, "%")

    def test_no_ncpa_hosts(self, logged_in_client, db_session):
        data = logged_in_client.get("/api/system/network-health/cpu").get_json()["data"]
        assert data["hosts"] == []
        assert data["hostname"] is None
        assert data["points"] == []

    def test_defaults_to_localhost(self, logged_in_client, db_session):
        self.seed_cpu(db_session, "alpha", 10.0)
        self.seed_cpu(db_session, "localhost", 42.5)
        db_session.session.commit()
        data = logged_in_client.get("/api/system/network-health/cpu").get_json()["data"]
        assert data["hosts"] == ["alpha", "localhost"]
        assert data["hostname"] == "localhost"
        assert data["current_pct"] == 42.5
        assert data["max_pct"] == 42.5
        assert len(data["points"]) == 24

    def test_defaults_to_first_host_without_localhost(self, logged_in_client, db_session):
        self.seed_cpu(db_session, "beta", 5.0)
        self.seed_cpu(db_session, "alpha", 10.0)
        db_session.session.commit()
        data = logged_in_client.get("/api/system/network-health/cpu").get_json()["data"]
        assert data["hostname"] == "alpha"

    def test_selected_host(self, logged_in_client, db_session):
        self.seed_cpu(db_session, "alpha", 10.0)
        self.seed_cpu(db_session, "beta", 70.0)
        db_session.session.commit()
        data = logged_in_client.get("/api/system/network-health/cpu?hostname=beta&hours=6&buckets=6").get_json()["data"]
        assert data["hostname"] == "beta"
        assert data["current_pct"] == 70.0
        assert len(data["points"]) == 6

    def test_unknown_host_404(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/network-health/cpu?hostname=nope")
        assert resp.status_code == 404

    def test_five_minute_window(self, logged_in_client, db_session):
        resp = logged_in_client.get(f"/api/system/network-health/cpu?hostname=nope&hours={5 / 60}")
        assert resp.status_code == 404

    @pytest.mark.parametrize("query", ["hours=12", "buckets=0", "buckets=500"])
    def test_invalid_params(self, logged_in_client, db_session, query):
        assert logged_in_client.get(f"/api/system/network-health/cpu?{query}").status_code == 400


# ==========================================================
# GET /api/system/network-health/connections
# ==========================================================

PROC_TCP = """  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 00000000:0016 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 1
   1: 0100007F:1F90 0100007F:D2A4 01 00000000:00000000 00:00000000 00000000     0        0 2
   2: 0100007F:1F90 0100007F:D2A6 01 00000000:00000000 00:00000000 00000000     0        0 3
   3: 0100007F:1F90 0100007F:D2A8 06 00000000:00000000 00:00000000 00000000     0        0 4
   4: 0100007F:1F90 0100007F:D2AA 08 00000000:00000000 00:00000000 00000000     0        0 5
"""


class TestConnections:

    def test_counts_by_state(self, logged_in_client, db_session, tmp_path):
        tcp = tmp_path / "tcp"
        tcp.write_text(PROC_TCP)
        with patch.object(network_health_activity, "PROC_TCP_FILES", (tcp, tmp_path / "missing")):
            data = logged_in_client.get("/api/system/network-health/connections").get_json()["data"]
        assert data["available"] is True
        assert data["established"] == 2
        assert data["listening"] == 1
        assert data["time_wait"] == 1
        assert data["other"] == 1
        assert data["total"] == 5

    def test_unavailable_without_proc(self, logged_in_client, db_session, tmp_path):
        with patch.object(network_health_activity, "PROC_TCP_FILES", (tmp_path / "missing",)):
            data = logged_in_client.get("/api/system/network-health/connections").get_json()["data"]
        assert data["available"] is False
        assert data["total"] is None


# ==========================================================
# GET /api/system/network-health/insights
# ==========================================================

class TestInsights:

    def insights(self, client):
        return client.get("/api/system/network-health/insights").get_json()["data"]["insights"]

    def test_no_hosts(self, logged_in_client, db_session):
        insights = self.insights(logged_in_client)
        assert insights == [{"severity": "info", "message": "No devices are being monitored yet.", "at": None}]

    def test_stable_network(self, logged_in_client, db_session):
        for name in ("a", "b"):
            host = _make_host(db_session, name)
            _make_host_perf(db_session, host, "rta", 2.0, "ms")
            _make_host_perf(db_session, host, "pl", 0.0, "%")
        db_session.session.commit()
        insights = self.insights(logged_in_client)
        messages = [i["message"] for i in insights]
        assert "Average latency across online devices is 2.0 ms." in messages
        assert insights[-1]["message"] == "Overall network condition is stable."
        assert not any("packet loss" in m for m in messages)

    def test_problems_sorted_by_severity(self, logged_in_client, db_session):
        _make_host(db_session, "up1")
        _make_host(db_session, "down1", HostStateType.DOWN)
        _make_host(db_session, "down2", HostStateType.UNREACHABLE)
        _make_service(db_session, "up1", "http-80-TCP", ServiceStateType.WARNING)
        _make_service(db_session, "up1", "ssh-22-TCP", ServiceStateType.CRITICAL, is_flapping=True)
        db_session.session.commit()

        insights = self.insights(logged_in_client)
        severities = [i["severity"] for i in insights]
        messages = [i["message"] for i in insights]
        assert severities == sorted(severities, key=["critical", "warning", "info", "ok"].index)
        assert "2 devices are down or unreachable." in messages
        assert "1 service is in a critical state." in messages
        assert "1 service is in a warning state." in messages
        assert "1 host or service is flapping between states." in messages
        assert "Overall network condition is stable." not in messages
        assert all(i["at"] for i in insights)

    def test_high_latency_is_a_warning(self, logged_in_client, db_session):
        for name in ("a", "b"):
            host = _make_host(db_session, name)
            _make_host_perf(db_session, host, "rta", 250.0, "ms")
            _make_host_perf(db_session, host, "pl", 10.0, "%")
        db_session.session.commit()
        insights = {i["message"]: i["severity"] for i in self.insights(logged_in_client)}
        assert insights["Average latency across online devices is 250.0 ms."] == "warning"
        assert insights["Average packet loss is 10.0%."] == "warning"


# ==========================================================
# GET /api/system/network-health/plugin-trends
# ==========================================================

class TestPluginTrends:

    URL = "/api/system/network-health/plugin-trends"

    def add_plugin(self, db_session, name, display_name):
        from app.plugin_models import Plugin, PluginSource, PluginStatus, PluginType
        db_session.session.add(Plugin(
            Name=name, Display_Name=display_name, Plugin_Type=PluginType.NAGIOS,
            Source=PluginSource.BASELINE_ISO, Status=PluginStatus.READY,
        ))

    def test_requires_login(self, client, db_session):
        assert client.get(self.URL).status_code in (401, 302)

    def test_requires_permission(self, limited_client, db_session):
        assert limited_client.get(self.URL).status_code == 403

    def test_default_system_checks_are_left_out(self, logged_in_client, db_session):
        # Stock Nagios, Network Discovery, and uncommanded services.
        stock = _make_service(db_session, "localhost", "Current Load", check_command="check_local_load")
        _make_service_perf(db_session, stock, "load1", 0.5)
        nd = _make_service(db_session, "web", "http-80", check_command="pinpoint_nd_http")
        _make_service_perf(db_session, nd, "time", 0.1, "s")
        _make_service(db_session, "web", "ping-0-ICMP")
        db_session.session.commit()

        data = logged_in_client.get(self.URL).get_json()["data"]
        assert data == {"hours": 24, "plugins": []}

    def test_added_plugin_with_averaged_and_per_host_metrics(self, logged_in_client, db_session):
        self.add_plugin(db_session, "check_dig", "DNS Lookup (dig)")
        a = _make_service(db_session, "web", "DNS Lookup", ServiceStateType.OK, check_command="pinpoint_check_dig")
        _make_service_perf(db_session, a, "time", 0.2, "s")
        _make_service_perf(db_session, a, "size", 512, "B")
        b = _make_service(db_session, "db", "DNS Lookup", ServiceStateType.WARNING, check_command="pinpoint_check_dig")
        _make_service_perf(db_session, b, "time", 0.4, "s")
        _make_service_perf(db_session, b, "size", 1024, "B")
        db_session.session.commit()

        data = logged_in_client.get(f"{self.URL}?hours=6&buckets=6").get_json()["data"]
        assert data["hours"] == 6
        [plugin] = data["plugins"]
        assert plugin["plugin_name"] == "check_dig"
        assert plugin["display_name"] == "DNS Lookup (dig)"
        assert (plugin["total"], plugin["ok"], plugin["warning"]) == (2, 1, 1)
        assert plugin["worst_state"] == "warning"

        time_metric, size_metric = plugin["metrics"]
        assert time_metric["metric"] == "time"
        assert time_metric["averaged"] is True
        assert time_metric["current_avg"] == pytest.approx(0.3)
        assert time_metric["service_count"] == 2
        assert len(time_metric["points"]) == 6
        assert time_metric["points"][-1]["avg_value"] == pytest.approx(0.3)

        # Sizes differ per machine: per-host values only, no average or trend.
        assert size_metric["metric"] == "size"
        assert size_metric["averaged"] is False
        assert size_metric["current_avg"] is None
        assert size_metric["points"] == []
        assert [c["hostname"] for c in size_metric["current"]] == ["db", "web"]

    def test_a_custom_ping_check_gets_a_widget_though_discovery_pings_do_not(self, logged_in_client, db_session):
        self.add_plugin(db_session, "check_ping", "Ping")
        custom = _make_service(db_session, "web", "custom-ping-uplink", ServiceStateType.OK,
                               check_command="pinpoint_custom_check_ping")
        _make_service_perf(db_session, custom, "rta", 3.0, "ms")
        # A ping from discovery's own host check has a dedicated widget and none here.
        _make_service(db_session, "web", "ping-0-ICMP", check_command="check_ping")
        db_session.session.commit()

        data = logged_in_client.get(self.URL).get_json()["data"]

        assert [plugin["plugin_name"] for plugin in data["plugins"]] == ["check_ping"]
        assert data["plugins"][0]["total"] == 1

    def test_enabled_plugin_gets_widget_for_discovery_services(self, logged_in_client, db_session):
        from app.plugin_models import Plugin, PluginSource, PluginStatus, PluginType
        db_session.session.add(Plugin(
            Name="check_ssh", Display_Name="SSH", Plugin_Type=PluginType.NAGIOS,
            Source=PluginSource.BASELINE_ISO, Status=PluginStatus.ENABLED,
        ))
        svc = _make_service(db_session, "web", "ssh-22-tcp", ServiceStateType.OK, check_command="pinpoint_nd_ssh")
        _make_service_perf(db_session, svc, "time", 0.05, "s")
        # Not enabled, so no widget even though it has services.
        _make_service(db_session, "web", "http-80-tcp", check_command="pinpoint_nd_http")
        db_session.session.commit()

        [plugin] = logged_in_client.get(self.URL).get_json()["data"]["plugins"]
        assert (plugin["plugin_name"], plugin["display_name"], plugin["total"]) == ("check_ssh", "SSH", 1)
        assert plugin["metrics"][0]["current_avg"] == pytest.approx(0.05)

    def test_percent_is_averaged_and_unknown_plugin_uses_its_name(self, logged_in_client, db_session):
        svc = _make_service(db_session, "web", "Mem", check_command="pinpoint_check_mem")
        _make_service_perf(db_session, svc, "used", 40.0, "%")
        db_session.session.commit()

        [plugin] = logged_in_client.get(self.URL).get_json()["data"]["plugins"]
        assert plugin["display_name"] == "check_mem"
        assert plugin["metrics"][0]["averaged"] is True
        assert plugin["metrics"][0]["current_avg"] == 40.0

    def test_plugin_without_perf_data(self, logged_in_client, db_session):
        _make_service(db_session, "web", "Custom", ServiceStateType.CRITICAL, check_command="pinpoint_check_custom")
        db_session.session.commit()
        [plugin] = logged_in_client.get(self.URL).get_json()["data"]["plugins"]
        assert plugin["metrics"] == []
        assert plugin["worst_state"] == "critical"

    @pytest.mark.parametrize("query", ["hours=12", "buckets=0"])
    def test_invalid_params(self, logged_in_client, db_session, query):
        assert logged_in_client.get(f"{self.URL}?{query}").status_code == 400
