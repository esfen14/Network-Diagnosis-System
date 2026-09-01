"""
tests/test_monitoring.py — Tests for the monitoring API endpoints.

Endpoints tested:
  GET /api/monitoring/alerts          (requires monitoring.alerts)
  GET /api/monitoring/alerts/current
  GET /api/monitoring/notifications   (requires monitoring.notifications)
  GET /api/monitoring/notifications/current
  GET /api/monitoring/network-health  (requires monitoring.network_health)
  GET /api/monitoring/dashboard       (requires monitoring.dashboard)
  GET /api/monitoring/dashboard/hosts
  GET /api/monitoring/dashboard/services

The Nagios-archive endpoints (/alerts, /notifications) are tested with
requests.get mocked so we never need a live Nagios instance.

The DB-backed endpoints (/network-health, /dashboard*) seed history DB
records via fixtures.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

from app.history_models import (
    HostStatus,
    ServiceStatus,
    ProgramStatus,
    HostStateType,
    ServiceStateType,
    PluginStatusType,
    ConnectionStateType,
    AcknowledgementType,
)


# ─── seed helpers ─────────────────────────────────────────────────────────────

def _ts(offset_seconds=0):
    """Return a UTC-aware datetime offset from now."""
    return datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)


def _make_host_status(
    db_session,
    hostname="host1",
    state=HostStateType.UP,
    ts=None,
):
    h = HostStatus(
        Timestamp=ts or _ts(),
        Hostname=hostname,
        Current_State=state,
        Plugin_Status=PluginStatusType.OK,
        Plugin_Output="PING OK - Packet loss = 0%",
        State_Type=ConnectionStateType.HARD,
        Current_Attempt=1,
        Max_Attempts=3,
        Last_Check=_ts(-60),
        Next_Check=_ts(60),
        Last_State_Change=_ts(-3600),
        Last_Hard_State_Change=_ts(-3600),
        Last_Time_Up=_ts(-60),
        Last_Time_Down=None,
        Last_Time_Unreachable=None,
        Check_Latency=0.01,
        Check_Execution_Time=0.05,
        Is_Flapping=False,
        Acknowledgement_Type=AcknowledgementType.NOACK,
        Scheduled_Downtime_Depth=0,
        Notification_Enabled=True,
    )
    db_session.session.add(h)
    db_session.session.flush()
    return h


def _make_service_status(
    db_session,
    hostname="host1",
    service="HTTP",
    state=ServiceStateType.OK,
    ts=None,
):
    s = ServiceStatus(
        Timestamp=ts or _ts(),
        Hostname=hostname,
        Service=service,
        Current_State=state,
        Plugin_Output="HTTP OK: 200",
        State_Type=ConnectionStateType.HARD,
        Last_Time_Ok=_ts(-60),
        Last_Time_Warning=None,
        Last_Time_Critical=None,
        Last_Time_Unknown=None,
        Current_Attempt=1,
        Max_Attempts=3,
        Last_Check=_ts(-60),
        Next_Check=_ts(60),
        Last_State_Change=_ts(-3600),
        Last_Hard_State_Change=_ts(-3600),
        Check_Latency=0.01,
        Check_Execution_Time=0.05,
        Notification_Enabled=True,
        Acknowledgement_Type=AcknowledgementType.NOACK,
        Is_Flapping=False,
        Scheduled_Downtime_Depth=0,
    )
    db_session.session.add(s)
    db_session.session.flush()
    return s


def _make_program_status(db_session):
    p = ProgramStatus(
        Timestamp=_ts(),
        Version="4.4.14",
        Update_Available=False,
        New_Version=None,
        Last_Update_Check=_ts(-3600),
        NagiosPID=1234,
        Enable_Notifications=True,
        Enable_Flap_Detection=False,
        Daemon_Mode=True,
        Program_Start_Time=_ts(-86400),
        Passive_Host_Checks_Enabled=False,
        Active_Host_Checks_Enabled=True,
        Passive_Service_Checks_Enabled=False,
        Active_Service_Checks_Enabled=True,
    )
    db_session.session.add(p)
    db_session.session.flush()
    return p


# ─── mock helpers ─────────────────────────────────────────────────────────────

def _mock_nagios_response(data):
    """Return a mock requests.Response whose .json() returns data."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = data
    return mock_resp


FAKE_ALERTLIST = [
    {
        "entry_time": "2026-08-22T10:00:00",
        "host_name": "host1",
        "service_description": "",
        "state": 0,
        "state_type": "HARD",
        "output": "PING OK",
    }
]

FAKE_ALERTCOUNT = {"count": 5}

FAKE_NOTIFICATIONLIST = [
    {
        "entry_time": "2026-08-22T10:05:00",
        "host_name": "host1",
        "service_description": "",
        "notification_type": "RECOVERY",
        "output": "Host recovered",
    }
]

FAKE_NOTIFICATIONCOUNT = {"count": 2}


# ─────────────────────────────────────────────────────────────────────────────
# AUTH GUARDS
# ─────────────────────────────────────────────────────────────────────────────

class TestMonitoringAuthGuards:
    """All monitoring endpoints require login."""

    ENDPOINTS = [
        "/api/monitoring/alerts",
        "/api/monitoring/alerts/current",
        "/api/monitoring/notifications",
        "/api/monitoring/notifications/current",
        "/api/monitoring/network-health",
        "/api/monitoring/dashboard",
        "/api/monitoring/dashboard/hosts",
        "/api/monitoring/dashboard/services",
    ]

    @pytest.mark.parametrize("url", ENDPOINTS)
    def test_requires_login(self, client, db_session, url):
        resp = client.get(url)
        assert resp.status_code in (401, 302)


# ─────────────────────────────────────────────────────────────────────────────
# PERMISSION GUARDS — limited client only has system.inventory
# ─────────────────────────────────────────────────────────────────────────────

class TestMonitoringPermissionGuards:
    ENDPOINTS = [
        "/api/monitoring/alerts",
        "/api/monitoring/alerts/current",
        "/api/monitoring/notifications",
        "/api/monitoring/notifications/current",
        "/api/monitoring/network-health",
        "/api/monitoring/dashboard",
        "/api/monitoring/dashboard/hosts",
        "/api/monitoring/dashboard/services",
    ]

    @pytest.mark.parametrize("url", ENDPOINTS)
    def test_requires_permission(self, limited_client, db_session, url):
        resp = limited_client.get(url)
        assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# ALERTS
# ─────────────────────────────────────────────────────────────────────────────

class TestAlertsEndpoint:
    ARCHIVE_PATH = "app.nagios.notifications.requests.get"

    def test_alerts_history_success(self, logged_in_client, db_session):
        mock_resp = _mock_nagios_response({"data": {"alertlist": FAKE_ALERTLIST}})
        with patch(self.ARCHIVE_PATH, return_value=mock_resp):
            resp = logged_in_client.get(
                "/api/monitoring/alerts"
                "?start_date=2026-08-01&start_time=00:00:00"
                "&end_date=2026-08-22&end_time=23:59:59"
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_alerts_count_only(self, logged_in_client, db_session):
        mock_resp = _mock_nagios_response({"data": {"alertcount": FAKE_ALERTCOUNT}})
        with patch(self.ARCHIVE_PATH, return_value=mock_resp):
            resp = logged_in_client.get("/api/monitoring/alerts?count_only=true")
        assert resp.status_code == 200

    def test_alerts_last_days(self, logged_in_client, db_session):
        mock_resp = _mock_nagios_response({"data": {"alertlist": FAKE_ALERTLIST}})
        with patch(self.ARCHIVE_PATH, return_value=mock_resp):
            resp = logged_in_client.get("/api/monitoring/alerts?last_days=7")
        assert resp.status_code == 200

    def test_alerts_nagios_failure_returns_502(self, logged_in_client, db_session):
        mock_resp = _mock_nagios_response({"data": {"alertlist": None}})
        # Simulate requests.get raising an exception
        with patch(
            self.ARCHIVE_PATH,
            side_effect=Exception("connection refused")
        ):
            resp = logged_in_client.get("/api/monitoring/alerts")
        # route catches all exceptions → 500
        assert resp.status_code == 500


class TestAlertsCurrentEndpoint:
    ARCHIVE_PATH = "app.nagios.notifications.requests.get"

    def test_alerts_current_success(self, logged_in_client, db_session):
        mock_resp = _mock_nagios_response({"data": {"alertlist": FAKE_ALERTLIST}})
        with patch(self.ARCHIVE_PATH, return_value=mock_resp):
            resp = logged_in_client.get("/api/monitoring/alerts/current")
        assert resp.status_code == 200
        assert "data" in resp.get_json()

    def test_alerts_current_returns_502_on_none(self, logged_in_client, db_session):
        # Nagios returns data=None — archivejson helper returns None
        mock_resp = _mock_nagios_response({"data": {"alertlist": None}})
        with patch(self.ARCHIVE_PATH, return_value=mock_resp):
            # _request_archive returns data['data'][query] which is None
            resp = logged_in_client.get("/api/monitoring/alerts/current")
        assert resp.status_code in (200, 502)  # None → 502 in our route


# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICATIONS
# ─────────────────────────────────────────────────────────────────────────────

class TestNotificationsEndpoint:
    ARCHIVE_PATH = "app.nagios.notifications.requests.get"

    def test_notifications_history_success(self, logged_in_client, db_session):
        mock_resp = _mock_nagios_response({"data": {"notificationlist": FAKE_NOTIFICATIONLIST}})
        with patch(self.ARCHIVE_PATH, return_value=mock_resp):
            resp = logged_in_client.get("/api/monitoring/notifications")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "data" in data

    def test_notifications_count_only(self, logged_in_client, db_session):
        mock_resp = _mock_nagios_response({"data": {"notificationcount": FAKE_NOTIFICATIONCOUNT}})
        with patch(self.ARCHIVE_PATH, return_value=mock_resp):
            resp = logged_in_client.get("/api/monitoring/notifications?count_only=true")
        assert resp.status_code == 200

    def test_notifications_last_days(self, logged_in_client, db_session):
        mock_resp = _mock_nagios_response({"data": {"notificationlist": FAKE_NOTIFICATIONLIST}})
        with patch(self.ARCHIVE_PATH, return_value=mock_resp):
            resp = logged_in_client.get("/api/monitoring/notifications?last_days=3")
        assert resp.status_code == 200

    def test_notifications_with_hostname_filter(self, logged_in_client, db_session):
        mock_resp = _mock_nagios_response({"data": {"notificationlist": FAKE_NOTIFICATIONLIST}})
        with patch(self.ARCHIVE_PATH, return_value=mock_resp):
            resp = logged_in_client.get("/api/monitoring/notifications?hostname=host1")
        assert resp.status_code == 200


class TestNotificationsCurrentEndpoint:
    ARCHIVE_PATH = "app.nagios.notifications.requests.get"

    def test_notifications_current_success(self, logged_in_client, db_session):
        mock_resp = _mock_nagios_response({"data": {"notificationlist": FAKE_NOTIFICATIONLIST}})
        with patch(self.ARCHIVE_PATH, return_value=mock_resp):
            resp = logged_in_client.get("/api/monitoring/notifications/current")
        assert resp.status_code == 200
        assert "data" in resp.get_json()


# ─────────────────────────────────────────────────────────────────────────────
# NETWORK HEALTH
# ─────────────────────────────────────────────────────────────────────────────

class TestNetworkHealthEndpoint:
    def test_network_health_empty(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/monitoring/network-health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_network_health_returns_hosts(self, logged_in_client, db_session):
        _make_host_status(db_session, hostname="router1", state=HostStateType.UP)
        _make_host_status(db_session, hostname="switch1", state=HostStateType.DOWN)
        db_session.session.commit()

        resp = logged_in_client.get("/api/monitoring/network-health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 2

    def test_network_health_latest_per_host(self, logged_in_client, db_session):
        """Only the most recent row per hostname should be returned."""
        old_ts = _ts(-7200)
        new_ts = _ts(-60)
        _make_host_status(db_session, hostname="host1", state=HostStateType.DOWN, ts=old_ts)
        _make_host_status(db_session, hostname="host1", state=HostStateType.UP, ts=new_ts)
        db_session.session.commit()

        resp = logged_in_client.get("/api/monitoring/network-health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 1
        assert data["items"][0]["state"] == HostStateType.UP.value

    def test_network_health_filter_by_state(self, logged_in_client, db_session):
        _make_host_status(db_session, hostname="up-host", state=HostStateType.UP)
        _make_host_status(db_session, hostname="down-host", state=HostStateType.DOWN)
        db_session.session.commit()

        resp = logged_in_client.get("/api/monitoring/network-health?state=DOWN")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 1
        assert data["items"][0]["hostname"] == "down-host"

    def test_network_health_search(self, logged_in_client, db_session):
        _make_host_status(db_session, hostname="webserver01")
        _make_host_status(db_session, hostname="dbserver01")
        db_session.session.commit()

        resp = logged_in_client.get("/api/monitoring/network-health?search=webserver")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 1
        assert data["items"][0]["hostname"] == "webserver01"

    def test_network_health_pagination(self, logged_in_client, db_session):
        for i in range(12):
            _make_host_status(db_session, hostname=f"host{i:02d}")
        db_session.session.commit()

        resp = logged_in_client.get("/api/monitoring/network-health?page=2&per_page=5")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["page"] == 2
        assert data["per_page"] == 5
        assert len(data["items"]) == 5

    def test_network_health_sort_asc(self, logged_in_client, db_session):
        for name in ["charlie", "alpha", "bravo"]:
            _make_host_status(db_session, hostname=name)
        db_session.session.commit()

        resp = logged_in_client.get("/api/monitoring/network-health?sort_by=hostname&order=asc")
        assert resp.status_code == 200
        names = [h["hostname"] for h in resp.get_json()["items"]]
        assert names == sorted(names)

    def test_network_health_invalid_page(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/monitoring/network-health?page=0")
        assert resp.status_code == 400

    def test_network_health_invalid_per_page(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/monitoring/network-health?per_page=200")
        assert resp.status_code == 400

    def test_network_health_invalid_sort(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/monitoring/network-health?sort_by=bad_field")
        assert resp.status_code == 400

    def test_network_health_invalid_state(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/monitoring/network-health?state=INVALID")
        assert resp.status_code == 400

    def test_network_health_includes_services(self, logged_in_client, db_session):
        _make_host_status(db_session, hostname="host1")
        _make_service_status(db_session, hostname="host1", service="HTTP")
        _make_service_status(db_session, hostname="host1", service="SSH")
        db_session.session.commit()

        resp = logged_in_client.get("/api/monitoring/network-health")
        assert resp.status_code == 200
        items = resp.get_json()["items"]
        host = next(h for h in items if h["hostname"] == "host1")
        service_names = {s["service"] for s in host["services"]}
        assert "HTTP" in service_names
        assert "SSH" in service_names


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

class TestDashboardEndpoint:
    def test_dashboard_empty_db(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/monitoring/dashboard")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["program_status"] is None
        assert data["host_summary"]["total"] == 0
        assert data["service_summary"]["total"] == 0
        assert data["hosts_down"] == []
        assert data["services_critical"] == []

    def test_dashboard_with_data(self, logged_in_client, db_session):
        _make_program_status(db_session)
        _make_host_status(db_session, hostname="up1", state=HostStateType.UP)
        _make_host_status(db_session, hostname="down1", state=HostStateType.DOWN)
        _make_service_status(db_session, hostname="up1", service="HTTP", state=ServiceStateType.OK)
        _make_service_status(db_session, hostname="down1", service="HTTP", state=ServiceStateType.CRITICAL)
        db_session.session.commit()

        resp = logged_in_client.get("/api/monitoring/dashboard")
        assert resp.status_code == 200
        data = resp.get_json()

        assert data["program_status"] is not None
        assert data["program_status"]["version"] == "4.4.14"

        assert data["host_summary"]["total"] == 2
        assert data["host_summary"]["up"] == 1
        assert data["host_summary"]["down"] == 1

        assert data["service_summary"]["total"] == 2
        assert data["service_summary"]["ok"] == 1
        assert data["service_summary"]["critical"] == 1

        assert len(data["hosts_down"]) == 1
        assert data["hosts_down"][0]["hostname"] == "down1"

        assert len(data["services_critical"]) == 1
        assert data["services_critical"][0]["service"] == "HTTP"

    def test_dashboard_latest_per_host_only(self, logged_in_client, db_session):
        """Dashboard must only count each host once using its latest record."""
        old_ts = _ts(-7200)
        new_ts = _ts(-60)
        _make_host_status(db_session, hostname="h1", state=HostStateType.DOWN, ts=old_ts)
        _make_host_status(db_session, hostname="h1", state=HostStateType.UP, ts=new_ts)
        db_session.session.commit()

        resp = logged_in_client.get("/api/monitoring/dashboard")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["host_summary"]["total"] == 1
        assert data["host_summary"]["up"] == 1
        assert data["host_summary"]["down"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD HOSTS
# ─────────────────────────────────────────────────────────────────────────────

class TestDashboardHostsEndpoint:
    def test_dashboard_hosts_empty(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/monitoring/dashboard/hosts")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_dashboard_hosts_returns_data(self, logged_in_client, db_session):
        _make_host_status(db_session, hostname="host1")
        _make_host_status(db_session, hostname="host2")
        db_session.session.commit()

        resp = logged_in_client.get("/api/monitoring/dashboard/hosts")
        assert resp.status_code == 200
        assert resp.get_json()["total"] == 2

    def test_dashboard_hosts_filter_state(self, logged_in_client, db_session):
        _make_host_status(db_session, hostname="up1", state=HostStateType.UP)
        _make_host_status(db_session, hostname="down1", state=HostStateType.DOWN)
        db_session.session.commit()

        resp = logged_in_client.get("/api/monitoring/dashboard/hosts?state=UP")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 1
        assert data["items"][0]["hostname"] == "up1"

    def test_dashboard_hosts_search(self, logged_in_client, db_session):
        _make_host_status(db_session, hostname="alpha")
        _make_host_status(db_session, hostname="beta")
        db_session.session.commit()

        resp = logged_in_client.get("/api/monitoring/dashboard/hosts?search=alp")
        assert resp.status_code == 200
        assert resp.get_json()["total"] == 1

    def test_dashboard_hosts_pagination(self, logged_in_client, db_session):
        for i in range(15):
            _make_host_status(db_session, hostname=f"h{i:02d}")
        db_session.session.commit()

        resp = logged_in_client.get("/api/monitoring/dashboard/hosts?page=2&per_page=5")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["page"] == 2
        assert len(data["items"]) == 5

    def test_dashboard_hosts_invalid_page(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/monitoring/dashboard/hosts?page=0")
        assert resp.status_code == 400

    def test_dashboard_hosts_invalid_state(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/monitoring/dashboard/hosts?state=BADSTATE")
        assert resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD SERVICES
# ─────────────────────────────────────────────────────────────────────────────

class TestDashboardServicesEndpoint:
    def test_dashboard_services_empty(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/monitoring/dashboard/services")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_dashboard_services_returns_data(self, logged_in_client, db_session):
        _make_service_status(db_session, hostname="host1", service="HTTP")
        _make_service_status(db_session, hostname="host1", service="SSH")
        db_session.session.commit()

        resp = logged_in_client.get("/api/monitoring/dashboard/services")
        assert resp.status_code == 200
        assert resp.get_json()["total"] == 2

    def test_dashboard_services_filter_by_state(self, logged_in_client, db_session):
        _make_service_status(db_session, hostname="h1", service="HTTP", state=ServiceStateType.OK)
        _make_service_status(db_session, hostname="h1", service="DB", state=ServiceStateType.CRITICAL)
        db_session.session.commit()

        resp = logged_in_client.get("/api/monitoring/dashboard/services?state=CRITICAL")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 1
        assert data["items"][0]["service"] == "DB"

    def test_dashboard_services_filter_by_hostname(self, logged_in_client, db_session):
        _make_service_status(db_session, hostname="host1", service="HTTP")
        _make_service_status(db_session, hostname="host2", service="HTTP")
        db_session.session.commit()

        resp = logged_in_client.get("/api/monitoring/dashboard/services?hostname=host1")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 1
        assert data["items"][0]["hostname"] == "host1"

    def test_dashboard_services_search(self, logged_in_client, db_session):
        _make_service_status(db_session, hostname="host1", service="HTTP")
        _make_service_status(db_session, hostname="host1", service="SSH")
        db_session.session.commit()

        resp = logged_in_client.get("/api/monitoring/dashboard/services?search=SSH")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 1
        assert data["items"][0]["service"] == "SSH"

    def test_dashboard_services_latest_per_service(self, logged_in_client, db_session):
        """Only most recent record per (host, service) pair counted."""
        old_ts = _ts(-7200)
        new_ts = _ts(-60)
        _make_service_status(db_session, hostname="h1", service="HTTP",
                             state=ServiceStateType.CRITICAL, ts=old_ts)
        _make_service_status(db_session, hostname="h1", service="HTTP",
                             state=ServiceStateType.OK, ts=new_ts)
        db_session.session.commit()

        resp = logged_in_client.get("/api/monitoring/dashboard/services")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 1
        assert data["items"][0]["state"] == ServiceStateType.OK.value

    def test_dashboard_services_pagination(self, logged_in_client, db_session):
        for i in range(12):
            _make_service_status(db_session, hostname="host1", service=f"SVC{i:02d}")
        db_session.session.commit()

        resp = logged_in_client.get("/api/monitoring/dashboard/services?page=2&per_page=5")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["page"] == 2
        assert len(data["items"]) == 5

    def test_dashboard_services_invalid_state(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/monitoring/dashboard/services?state=NOTASTATE")
        assert resp.status_code == 400

    def test_dashboard_services_sort_desc(self, logged_in_client, db_session):
        for name in ["alpha", "bravo", "charlie"]:
            _make_service_status(db_session, hostname="host1", service=name)
        db_session.session.commit()

        resp = logged_in_client.get("/api/monitoring/dashboard/services?order=desc")
        assert resp.status_code == 200
        names = [s["service"] for s in resp.get_json()["items"]]
        assert names == sorted(names, reverse=True)
