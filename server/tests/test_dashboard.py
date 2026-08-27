"""
tests/test_dashboard.py
=======================
Tests for app/api/system/dashboard.py.

Routes tested:
  GET  /api/system/dashboard/status
  GET  /api/system/dashboard/summary
  GET  /api/system/dashboard/alerts          (history.db snapshots — seeded)
  GET  /api/system/dashboard/notifications   (Nagios archivejson — mocked)
  POST /api/system/dashboard/alerts/acknowledge
  POST /api/system/dashboard/alerts/acknowledge-all
  DELETE /api/system/dashboard/alerts/acknowledge
"""

import pytest
from unittest.mock import patch

from app.history_models import HostStateType, ServiceStateType

from tests.seed_helpers import (
    _ts,
    _make_host, _make_host_perf,
    _make_service, _make_service_perf,
    _make_program_status,
    _seed_realistic_network,
    NCPA_CPU_SERVICE, NCPA_MEMORY_SERVICE, NCPA_DISK_SERVICE,
)

# Patch target for the Nagios helper used inside dashboard.py
_NOTIFS_PATH = "app.api.system.dashboard.request_notifications_last"


def _seed_active_alerts(db_session):
    """Seed the three active alerts used by the alerts-feed tests directly
    into history.db, mirroring the old FAKE_ACTIVE_ALERTS fixture."""
    _make_host(db_session, "dbserver", HostStateType.DOWN,
               plugin_output="PING CRITICAL - Packet loss = 100%")
    _make_service(db_session, "webserver", "mysql-3306-TCP", ServiceStateType.CRITICAL,
                  plugin_output="CRITICAL: Cannot connect to MySQL on port 3306")
    _make_service(db_session, "fileserver", "disk-0-TCP", ServiceStateType.WARNING,
                  plugin_output="DISK WARNING - free space: / 512 MiB (8%)")
    db_session.session.commit()


FAKE_NOTIFICATIONS = [
    {"timestamp": 1700009000, "notificationtype": "PROBLEM",
     "hostname": "dbserver", "servicedesc": None,
     "notificationreason": "DOWN", "contact": "admin", "output": "PING CRITICAL"},
    {"timestamp": 1700008000, "notificationtype": "RECOVERY",
     "hostname": "webserver", "servicedesc": "http-80-TCP",
     "notificationreason": "OK", "contact": "admin", "output": "HTTP OK"},
]


# ==========================================================
# Auth / permission guards
# ==========================================================

class TestDashboardAuthGuards:
    READ_ENDPOINTS = [
        "/api/system/dashboard/status",
        "/api/system/dashboard/summary",
        "/api/system/dashboard/alerts",
        "/api/system/dashboard/notifications",
    ]

    @pytest.mark.parametrize("url", READ_ENDPOINTS)
    def test_requires_login(self, client, db_session, url):
        assert client.get(url).status_code in (401, 302)

    def test_acknowledge_requires_login(self, client, db_session):
        resp = client.post(
            "/api/system/dashboard/alerts/acknowledge",
            json={"hostname": "h1", "service_name": None, "comment": "x"},
        )
        assert resp.status_code in (401, 302)

    def test_unacknowledge_requires_login(self, client, db_session):
        resp = client.delete(
            "/api/system/dashboard/alerts/acknowledge",
            json={"hostname": "h1", "service_name": None},
        )
        assert resp.status_code in (401, 302)

    def test_acknowledge_all_requires_login(self, client, db_session):
        resp = client.post(
            "/api/system/dashboard/alerts/acknowledge-all",
            json={"comment": "x", "alerts": [{"hostname": "h1", "service_name": None}]},
        )
        assert resp.status_code in (401, 302)

    @pytest.mark.parametrize("url", READ_ENDPOINTS)
    def test_requires_permission(self, limited_client, db_session, url):
        assert limited_client.get(url).status_code == 403

    def test_acknowledge_requires_permission(self, limited_client, db_session):
        resp = limited_client.post(
            "/api/system/dashboard/alerts/acknowledge",
            json={"hostname": "h1", "service_name": None, "comment": "x"},
        )
        assert resp.status_code == 403

    def test_unacknowledge_requires_permission(self, limited_client, db_session):
        resp = limited_client.delete(
            "/api/system/dashboard/alerts/acknowledge",
            json={"hostname": "h1", "service_name": None},
        )
        assert resp.status_code == 403


# ==========================================================
# GET /api/system/dashboard/status
# ==========================================================

class TestDashboardStatus:

    def test_empty_db_nagios_not_running(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/dashboard/status")
        assert resp.status_code == 200
        nagios = resp.get_json()["data"]["nagios"]
        assert nagios["running"] is False
        assert nagios["pid"] is None
        assert nagios["version"] is None

    def test_with_program_status(self, logged_in_client, db_session):
        _make_program_status(db_session)
        db_session.session.commit()
        resp = logged_in_client.get("/api/system/dashboard/status")
        assert resp.status_code == 200
        nagios = resp.get_json()["data"]["nagios"]
        assert nagios["running"] is True
        assert nagios["pid"] == 1234
        assert nagios["version"] == "4.4.14"
        assert nagios["active_host_checks"] is True
        assert nagios["active_service_checks"] is True
        assert nagios["notifications_enabled"] is True
        assert nagios["enable_flap_detection"] is True

    def test_server_resources_not_configured_when_empty(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/dashboard/status")
        resources = resp.get_json()["data"]["server_resources"]
        assert resources["cpu_load"]["configured"] is False
        assert resources["disk"]["configured"] is False
        assert resources["swap"]["configured"] is False

    def test_server_resources_populated_with_realistic_data(self, logged_in_client, db_session):
        _seed_realistic_network(db_session)
        resp = logged_in_client.get("/api/system/dashboard/status")
        assert resp.status_code == 200
        resources = resp.get_json()["data"]["server_resources"]
        assert resources["cpu_load"]["configured"] is True
        assert resources["cpu_load"]["load1"] == pytest.approx(0.42)
        assert resources["swap"]["configured"] is True
        assert resources["swap"]["swap_used_mb"] == pytest.approx(160.0)
        assert resources["disk"]["configured"] is True
        assert len(resources["disk"]["mounts"]) >= 1

    def test_response_shape(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/dashboard/status")
        data = resp.get_json()["data"]
        assert "nagios" in data
        assert "server_resources" in data
        for key in ("running", "pid", "version", "program_start_time",
                    "last_status_update", "active_host_checks",
                    "active_service_checks", "notifications_enabled",
                    "enable_flap_detection"):
            assert key in data["nagios"]


# ==========================================================
# GET /api/system/dashboard/summary
# ==========================================================

class TestDashboardSummary:

    def test_empty_db(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/dashboard/summary")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["hosts"]["total"] == 0
        assert data["services"]["total"] == 0
        assert data["active_alerts"]["total"] == 0
        assert data["ping_metrics"]["configured"] is False
        assert data["ncpa_metrics"] is None

    def test_host_and_service_counts(self, logged_in_client, db_session):
        _make_host(db_session, "h1", HostStateType.UP)
        _make_host(db_session, "h2", HostStateType.DOWN)
        _make_service(db_session, "h1", "http-80-TCP", ServiceStateType.OK)
        _make_service(db_session, "h2", "ssh-22-TCP", ServiceStateType.CRITICAL)
        db_session.session.commit()
        resp = logged_in_client.get("/api/system/dashboard/summary")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["hosts"]["total"] == 2
        assert data["hosts"]["up"] == 1
        assert data["hosts"]["down"] == 1
        assert data["services"]["total"] == 2
        assert data["services"]["ok"] == 1
        assert data["services"]["critical"] == 1

    def test_ping_metrics_with_two_hosts(self, logged_in_client, db_session):
        h1 = _make_host(db_session, "h1")
        _make_host_perf(db_session, h1, "rta", 4.0, "ms")
        _make_host_perf(db_session, h1, "pl", 0.0, "%")
        h2 = _make_host(db_session, "h2")
        _make_host_perf(db_session, h2, "rta", 6.0, "ms")
        _make_host_perf(db_session, h2, "pl", 2.0, "%")
        db_session.session.commit()
        ping = logged_in_client.get("/api/system/dashboard/summary").get_json()["data"]["ping_metrics"]
        assert ping["configured"] is True
        assert ping["avg_rta_ms"] == pytest.approx(5.0)
        assert ping["avg_packet_loss_pct"] == pytest.approx(1.0)

    def test_ping_metrics_insufficient_data(self, logged_in_client, db_session):
        h1 = _make_host(db_session, "h1")
        _make_host_perf(db_session, h1, "rta", 5.0, "ms")
        _make_host_perf(db_session, h1, "pl", 0.0, "%")
        db_session.session.commit()
        ping = logged_in_client.get("/api/system/dashboard/summary").get_json()["data"]["ping_metrics"]
        assert ping["configured"] is True
        assert ping.get("insufficient_data") is True

    def test_ncpa_absent_without_ncpa_services(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "http-80-TCP")
        db_session.session.commit()
        assert logged_in_client.get("/api/system/dashboard/summary").get_json()["data"]["ncpa_metrics"] is None

    def test_ncpa_present_with_two_ncpa_hosts(self, logged_in_client, db_session):
        cpu1 = _make_service(db_session, "h1", NCPA_CPU_SERVICE)
        _make_service_perf(db_session, cpu1, "cpu/percent", 10.0, "%")
        mem1 = _make_service(db_session, "h1", NCPA_MEMORY_SERVICE)
        _make_service_perf(db_session, mem1, "memory/virtual/percent", 30.0, "%")
        disk1 = _make_service(db_session, "h1", NCPA_DISK_SERVICE)
        _make_service_perf(db_session, disk1, "disk/logical/|/used_percent", 20.0, "%")

        cpu2 = _make_service(db_session, "h2", NCPA_CPU_SERVICE)
        _make_service_perf(db_session, cpu2, "cpu/percent", 20.0, "%")
        mem2 = _make_service(db_session, "h2", NCPA_MEMORY_SERVICE)
        _make_service_perf(db_session, mem2, "memory/virtual/percent", 50.0, "%")
        disk2 = _make_service(db_session, "h2", NCPA_DISK_SERVICE)
        _make_service_perf(db_session, disk2, "disk/logical/|/used_percent", 40.0, "%")

        db_session.session.commit()
        ncpa = logged_in_client.get("/api/system/dashboard/summary").get_json()["data"]["ncpa_metrics"]
        assert ncpa is not None
        assert ncpa["avg_cpu_pct"] == pytest.approx(15.0)

    def test_realistic_network(self, logged_in_client, db_session):
        _seed_realistic_network(db_session)
        resp = logged_in_client.get("/api/system/dashboard/summary")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["hosts"]["total"] == 5
        assert data["hosts"]["down"] == 1
        assert data["active_alerts"]["critical"] >= 1


# ==========================================================
# GET /api/system/dashboard/alerts
# ==========================================================

class TestDashboardAlerts:

    def test_returns_alerts(self, logged_in_client, db_session):
        _seed_active_alerts(db_session)
        resp = logged_in_client.get("/api/system/dashboard/alerts")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "alerts" in data
        assert data["total_shown"] == 3

    def test_empty_db_returns_no_alerts(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/dashboard/alerts")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["total_shown"] == 0

    def test_ok_and_up_states_excluded(self, logged_in_client, db_session):
        _seed_active_alerts(db_session)
        _make_host(db_session, "h-up", HostStateType.UP)
        _make_service(db_session, "h-up", "http-80-TCP", ServiceStateType.OK)
        db_session.session.commit()
        states = {a["state"] for a in
                  logged_in_client.get("/api/system/dashboard/alerts").get_json()["data"]["alerts"]}
        assert "OK" not in states
        assert "UP" not in states

    def test_ack_filter_invalid_returns_400(self, logged_in_client, db_session):
        _seed_active_alerts(db_session)
        resp = logged_in_client.get("/api/system/dashboard/alerts?ack_filter=badvalue")
        assert resp.status_code == 400

    def test_limit_param(self, logged_in_client, db_session):
        _seed_active_alerts(db_session)
        resp = logged_in_client.get("/api/system/dashboard/alerts?limit=1")
        assert resp.get_json()["data"]["total_shown"] == 1

    def test_ack_filter_acknowledged(self, logged_in_client, db_session):
        _seed_active_alerts(db_session)
        logged_in_client.post(
            "/api/system/dashboard/alerts/acknowledge",
            json={"hostname": "dbserver", "service_name": None, "comment": "on it"},
        )
        resp = logged_in_client.get("/api/system/dashboard/alerts?ack_filter=acknowledged")
        acked = [a for a in resp.get_json()["data"]["alerts"] if a["hostname"] == "dbserver"]
        assert len(acked) == 1
        assert acked[0]["ack"] is not None
        assert acked[0]["ack"]["comment"] == "on it"

    def test_ack_filter_unacknowledged_excludes_acked(self, logged_in_client, db_session):
        _seed_active_alerts(db_session)
        logged_in_client.post(
            "/api/system/dashboard/alerts/acknowledge",
            json={"hostname": "dbserver", "service_name": None, "comment": "ack"},
        )
        resp = logged_in_client.get(
            "/api/system/dashboard/alerts?ack_filter=unacknowledged"
        )
        hostnames = {a["hostname"] for a in resp.get_json()["data"]["alerts"]}
        assert "dbserver" not in hostnames

    def test_in_downtime_sorted_last(self, logged_in_client, db_session):
        _make_host(db_session, "down-in-downtime", HostStateType.DOWN, downtime_depth=1)
        _make_host(db_session, "down-not-in-downtime", HostStateType.DOWN)
        db_session.session.commit()
        alerts = logged_in_client.get("/api/system/dashboard/alerts").get_json()["data"]["alerts"]
        assert alerts[-1]["hostname"] == "down-in-downtime"
        assert alerts[-1]["in_downtime"] is True

    def test_alert_item_shape(self, logged_in_client, db_session):
        _seed_active_alerts(db_session)
        alert = logged_in_client.get("/api/system/dashboard/alerts").get_json()["data"]["alerts"][0]
        for key in ("type", "hostname", "service_name", "state", "state_type",
                    "timestamp", "duration_seconds", "plugin_output",
                    "in_downtime", "ack"):
            assert key in alert


# ==========================================================
# POST /api/system/dashboard/alerts/acknowledge
# DELETE /api/system/dashboard/alerts/acknowledge
# POST /api/system/dashboard/alerts/acknowledge-all
# ==========================================================

class TestDashboardAcknowledge:

    def test_acknowledge_host_alert(self, logged_in_client, db_session):
        _make_host(db_session, "dbserver", HostStateType.DOWN)
        db_session.session.commit()
        resp = logged_in_client.post(
            "/api/system/dashboard/alerts/acknowledge",
            json={"hostname": "dbserver", "service_name": None, "comment": "on it"},
        )
        assert resp.status_code == 201

    def test_acknowledge_service_alert(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "mysql-3306-TCP", ServiceStateType.CRITICAL)
        db_session.session.commit()
        resp = logged_in_client.post(
            "/api/system/dashboard/alerts/acknowledge",
            json={"hostname": "h1", "service_name": "mysql-3306-TCP", "comment": "checking"},
        )
        assert resp.status_code == 201

    def test_missing_hostname_returns_400(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/api/system/dashboard/alerts/acknowledge",
            json={"hostname": "", "service_name": None, "comment": "x"},
        )
        assert resp.status_code == 400

    def test_missing_comment_returns_400(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/api/system/dashboard/alerts/acknowledge",
            json={"hostname": "dbserver", "service_name": None, "comment": ""},
        )
        assert resp.status_code == 400

    def test_nonexistent_alert_returns_404(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/api/system/dashboard/alerts/acknowledge",
            json={"hostname": "ghost", "service_name": None, "comment": "x"},
        )
        assert resp.status_code == 404

    def test_up_host_returns_404(self, logged_in_client, db_session):
        """A UP host has no active alert."""
        _make_host(db_session, "alive", HostStateType.UP)
        db_session.session.commit()
        resp = logged_in_client.post(
            "/api/system/dashboard/alerts/acknowledge",
            json={"hostname": "alive", "service_name": None, "comment": "x"},
        )
        assert resp.status_code == 404

    def test_double_ack_service_returns_409(self, logged_in_client, db_session):
        """Duplicate ack on the same (host, service) pair → 409.
        Uses a non-null service_name because SQLite NULL != NULL in unique constraints."""
        _make_service(db_session, "h1", "mysql-3306-TCP", ServiceStateType.CRITICAL)
        db_session.session.commit()
        logged_in_client.post(
            "/api/system/dashboard/alerts/acknowledge",
            json={"hostname": "h1", "service_name": "mysql-3306-TCP", "comment": "first"},
        )
        resp = logged_in_client.post(
            "/api/system/dashboard/alerts/acknowledge",
            json={"hostname": "h1", "service_name": "mysql-3306-TCP", "comment": "second"},
        )
        assert resp.status_code == 409

    def test_unacknowledge_removes_ack(self, logged_in_client, db_session):
        _make_host(db_session, "dbserver", HostStateType.DOWN)
        db_session.session.commit()
        logged_in_client.post(
            "/api/system/dashboard/alerts/acknowledge",
            json={"hostname": "dbserver", "service_name": None, "comment": "first"},
        )
        resp = logged_in_client.delete(
            "/api/system/dashboard/alerts/acknowledge",
            json={"hostname": "dbserver", "service_name": None},
        )
        assert resp.status_code == 200

    def test_unacknowledge_nonexistent_returns_404(self, logged_in_client, db_session):
        resp = logged_in_client.delete(
            "/api/system/dashboard/alerts/acknowledge",
            json={"hostname": "nohost", "service_name": None},
        )
        assert resp.status_code == 404

    def test_acknowledge_all_creates_multiple(self, logged_in_client, db_session):
        _make_host(db_session, "h1", HostStateType.DOWN)
        _make_host(db_session, "h2", HostStateType.UNREACHABLE)
        db_session.session.commit()
        resp = logged_in_client.post(
            "/api/system/dashboard/alerts/acknowledge-all",
            json={
                "comment": "mass ack",
                "alerts": [
                    {"hostname": "h1", "service_name": None},
                    {"hostname": "h2", "service_name": None},
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["acknowledged"] == 2
        assert data["skipped"] == 0

    def test_acknowledge_all_skips_already_acked(self, logged_in_client, db_session):
        _make_host(db_session, "h1", HostStateType.DOWN)
        db_session.session.commit()
        logged_in_client.post(
            "/api/system/dashboard/alerts/acknowledge-all",
            json={"comment": "first", "alerts": [{"hostname": "h1", "service_name": None}]},
        )
        resp = logged_in_client.post(
            "/api/system/dashboard/alerts/acknowledge-all",
            json={"comment": "second", "alerts": [{"hostname": "h1", "service_name": None}]},
        )
        data = resp.get_json()["data"]
        assert data["acknowledged"] == 0
        assert data["skipped"] == 1

    def test_acknowledge_all_missing_comment_returns_400(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/api/system/dashboard/alerts/acknowledge-all",
            json={"comment": "", "alerts": [{"hostname": "h1", "service_name": None}]},
        )
        assert resp.status_code == 400

    def test_acknowledge_all_empty_list_returns_400(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/api/system/dashboard/alerts/acknowledge-all",
            json={"comment": "x", "alerts": []},
        )
        assert resp.status_code == 400


# ==========================================================
# GET /api/system/dashboard/notifications
# ==========================================================

class TestDashboardNotifications:

    def test_returns_notifications(self, logged_in_client, db_session):
        with patch(_NOTIFS_PATH, return_value=FAKE_NOTIFICATIONS):
            resp = logged_in_client.get("/api/system/dashboard/notifications")
        assert resp.status_code == 200
        notifs = resp.get_json()["data"]["notifications"]
        assert len(notifs) == 2

    def test_nagios_unavailable_returns_empty_list(self, logged_in_client, db_session):
        """When Nagios times out or returns None, the route returns 200 with
        an empty notifications list instead of a 502 error."""
        with patch(_NOTIFS_PATH, return_value=None):
            resp = logged_in_client.get("/api/system/dashboard/notifications")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["notifications"] == []

    def test_capped_at_five(self, logged_in_client, db_session):
        many = [
            {"timestamp": 1700000000 + i, "notificationtype": "PROBLEM",
             "hostname": f"host{i}", "servicedesc": None,
             "notificationreason": "DOWN", "contact": "admin", "output": "down"}
            for i in range(10)
        ]
        with patch(_NOTIFS_PATH, return_value=many):
            resp = logged_in_client.get("/api/system/dashboard/notifications")
        assert len(resp.get_json()["data"]["notifications"]) <= 5

    def test_sorted_newest_first(self, logged_in_client, db_session):
        with patch(_NOTIFS_PATH, return_value=FAKE_NOTIFICATIONS):
            resp = logged_in_client.get("/api/system/dashboard/notifications")
        timestamps = [n["timestamp"] for n in resp.get_json()["data"]["notifications"]]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_notification_item_shape(self, logged_in_client, db_session):
        with patch(_NOTIFS_PATH, return_value=FAKE_NOTIFICATIONS):
            resp = logged_in_client.get("/api/system/dashboard/notifications")
        n = resp.get_json()["data"]["notifications"][0]
        for key in ("timestamp", "type", "hostname", "service_name", "state",
                    "contact", "message"):
            assert key in n
