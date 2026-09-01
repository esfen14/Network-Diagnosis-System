"""
tests/test_network_health.py
============================
Tests for app/api/system/network_health.py.

Routes tested:
  GET /api/system/network-health/summary
  GET /api/system/network-health/trends
  GET /api/system/network-health/plugins
"""

import pytest

from app.history_models import HostStateType, ServiceStateType

from tests.seed_helpers import (
    _ts,
    _make_host, _make_host_perf,
    _make_service, _make_service_perf,
    _seed_realistic_network,
    NCPA_CPU_SERVICE, NCPA_MEMORY_SERVICE, NCPA_DISK_SERVICE,
)


# ==========================================================
# Auth / permission guards
# ==========================================================

class TestNetworkHealthAuthGuards:
    ENDPOINTS = [
        "/api/system/network-health/summary",
        "/api/system/network-health/trends",
        "/api/system/network-health/plugins",
    ]

    @pytest.mark.parametrize("url", ENDPOINTS)
    def test_requires_login(self, client, db_session, url):
        assert client.get(url).status_code in (401, 302)

    @pytest.mark.parametrize("url", ENDPOINTS)
    def test_requires_permission(self, limited_client, db_session, url):
        assert limited_client.get(url).status_code == 403


# ==========================================================
# GET /api/system/network-health/summary
# ==========================================================

class TestNetworkHealthSummary:

    def test_empty_db(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/network-health/summary")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["hosts"]["total"] == 0
        assert data["services"]["total"] == 0
        assert data["active_alerts"]["total"] == 0

    def test_response_shape(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/network-health/summary")
        data = resp.get_json()["data"]
        for key in ("total", "up", "down", "unreachable", "flapping", "in_downtime"):
            assert key in data["hosts"]
        for key in ("total", "ok", "warning", "critical", "unknown", "flapping", "in_downtime"):
            assert key in data["services"]
        for key in ("total", "critical", "warning", "unknown"):
            assert key in data["active_alerts"]

    def test_counts_with_seeded_data(self, logged_in_client, db_session):
        _seed_realistic_network(db_session)
        resp = logged_in_client.get("/api/system/network-health/summary")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["hosts"]["total"] == 5
        assert data["hosts"]["down"] == 1
        assert data["active_alerts"]["critical"] >= 1

    def test_flapping_counted(self, logged_in_client, db_session):
        _make_host(db_session, "h1", HostStateType.UP, is_flapping=True)
        _make_service(db_session, "h1", "http-80-TCP", is_flapping=True)
        db_session.session.commit()
        resp = logged_in_client.get("/api/system/network-health/summary")
        data = resp.get_json()["data"]
        assert data["hosts"]["flapping"] == 1
        assert data["services"]["flapping"] == 1


# ==========================================================
# GET /api/system/network-health/trends
# ==========================================================

class TestNetworkHealthTrends:

    def test_default_hours_is_24(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/network-health/trends")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["hours"] == 24

    @pytest.mark.parametrize("hours", [1, 6, 24, 168])
    def test_all_valid_hours(self, logged_in_client, db_session, hours):
        resp = logged_in_client.get(f"/api/system/network-health/trends?hours={hours}")
        assert resp.status_code == 200

    def test_invalid_hours_returns_400(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/network-health/trends?hours=12")
        assert resp.status_code == 400

    def test_invalid_buckets_returns_400(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/network-health/trends?buckets=0")
        assert resp.status_code == 400

    def test_response_contains_required_sections(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/network-health/trends")
        data = resp.get_json()["data"]
        assert "ping" in data
        assert "ncpa" in data
        assert "nagios_server" in data

    def test_ping_not_configured_without_ping_services(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "mysql-3306-TCP")
        db_session.session.commit()
        resp = logged_in_client.get("/api/system/network-health/trends")
        assert resp.get_json()["data"]["ping"]["configured"] is False

    def test_ping_configured_with_ping_services(self, logged_in_client, db_session):
        svc = _make_service(db_session, "h1", "ping-0-ICMP")
        _make_service_perf(db_session, svc, "rta", 2.0, "ms")
        db_session.session.commit()
        resp = logged_in_client.get("/api/system/network-health/trends")
        assert resp.get_json()["data"]["ping"]["configured"] is True

    def test_ncpa_null_without_ncpa_services(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "http-80-TCP")
        db_session.session.commit()
        resp = logged_in_client.get("/api/system/network-health/trends")
        assert resp.get_json()["data"]["ncpa"] is None

    def test_ncpa_present_with_ncpa_services(self, logged_in_client, db_session):
        ncpa = _make_service(db_session, "h1", NCPA_DISK_SERVICE)
        _make_service_perf(db_session, ncpa, "cpu/percent", 12.0, "%")
        db_session.session.commit()
        resp = logged_in_client.get("/api/system/network-health/trends")
        ncpa_data = resp.get_json()["data"]["ncpa"]
        assert ncpa_data is not None
        for key in ("cpu", "disk", "memory"):
            assert key in ncpa_data

    def test_nagios_server_load_configured(self, logged_in_client, db_session):
        svc = _make_service(db_session, "localhost", "load-0-TCP")
        _make_service_perf(db_session, svc, "load1", 0.5)
        _make_service_perf(db_session, svc, "load5", 0.4)
        _make_service_perf(db_session, svc, "load15", 0.3)
        db_session.session.commit()
        cpu = logged_in_client.get("/api/system/network-health/trends").get_json()["data"]["nagios_server"]["cpu_load"]
        assert cpu["configured"] is True
        for key in ("load1", "load5", "load15"):
            assert key in cpu

    def test_nagios_server_load_not_configured_when_absent(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/network-health/trends")
        assert resp.get_json()["data"]["nagios_server"]["cpu_load"]["configured"] is False

    def test_nagios_server_swap_configured(self, logged_in_client, db_session):
        svc = _make_service(db_session, "localhost", "swap-0-TCP")
        _make_service_perf(db_session, svc, "swap", 160.0, "MB")
        db_session.session.commit()
        swap = logged_in_client.get("/api/system/network-health/trends").get_json()["data"]["nagios_server"]["swap"]
        assert swap["configured"] is True

    def test_bucket_count_matches_request(self, logged_in_client, db_session):
        svc = _make_service(db_session, "h1", "http-80-TCP", ts=_ts(-1800))
        _make_service_perf(db_session, svc, "rta", 2.0, "ms")
        db_session.session.commit()
        resp = logged_in_client.get("/api/system/network-health/trends?hours=24&buckets=12")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["buckets"] == 12


# ==========================================================
# GET /api/system/network-health/plugins
# ==========================================================

class TestNetworkHealthPlugins:

    def test_empty_db_returns_empty_groups(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/network-health/plugins")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["groups"] == []

    def test_groups_reflect_seeded_services(self, logged_in_client, db_session):
        _seed_realistic_network(db_session)
        resp = logged_in_client.get("/api/system/network-health/plugins")
        display_names = {g["display_name"] for g in resp.get_json()["data"]["groups"]}
        assert "HTTP" in display_names
        assert "NCPA" in display_names

    def test_worst_state_first(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "http-80-TCP", ServiceStateType.OK)
        _make_service(db_session, "h1", "ssh-22-TCP", ServiceStateType.CRITICAL)
        db_session.session.commit()
        groups = logged_in_client.get("/api/system/network-health/plugins").get_json()["data"]["groups"]
        assert groups[0]["worst_state"] == "critical"

    def test_group_shape(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "http-80-TCP")
        db_session.session.commit()
        group = logged_in_client.get("/api/system/network-health/plugins").get_json()["data"]["groups"][0]
        for key in ("display_name", "total", "ok", "warning", "critical", "unknown", "worst_state"):
            assert key in group

    def test_multiple_plugins_grouped_correctly(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "http-80-TCP", ServiceStateType.OK)
        _make_service(db_session, "h2", "http-443-TCP", ServiceStateType.WARNING)
        _make_service(db_session, "h1", "ssh-22-TCP", ServiceStateType.OK)
        db_session.session.commit()
        groups = logged_in_client.get("/api/system/network-health/plugins").get_json()["data"]["groups"]
        http_group = next(g for g in groups if g["display_name"] == "HTTP")
        assert http_group["total"] == 2
        assert http_group["ok"] == 1
        assert http_group["warning"] == 1
        ssh_group = next(g for g in groups if g["display_name"] == "SSH")
        assert ssh_group["total"] == 1
        assert ssh_group["ok"] == 1

    def test_ncpa_plugin_displayed(self, logged_in_client, db_session):
        _make_service(db_session, "h1", NCPA_DISK_SERVICE, ServiceStateType.OK)
        db_session.session.commit()
        groups = logged_in_client.get("/api/system/network-health/plugins").get_json()["data"]["groups"]
        assert any(g["display_name"] == "NCPA" for g in groups)
