"""
tests/test_network_hosts.py
===========================
Tests for app/api/system/network_hosts.py.

Routes tested:
  GET    /api/system/network-health/hosts
  GET    /api/system/network-health/hosts/<hostname>/detail
  POST   /api/system/network-health/hosts/acknowledge
  DELETE /api/system/network-health/hosts/acknowledge
"""

import pytest

from app.history_models import HostStateType, ServiceStateType

from tests.seed_helpers import (
    _ts,
    _make_host, _make_host_perf,
    _make_service,
    _seed_realistic_network,
)


# ==========================================================
# Auth / permission guards
# ==========================================================

class TestNetworkHostsAuthGuards:

    def test_list_requires_login(self, client, db_session):
        assert client.get("/api/system/network-health/hosts").status_code in (401, 302)

    def test_detail_requires_login(self, client, db_session):
        assert client.get("/api/system/network-health/hosts/h1/detail").status_code in (401, 302)

    def test_ack_requires_login(self, client, db_session):
        assert client.post(
            "/api/system/network-health/hosts/acknowledge",
            json={"hostname": "h1", "comment": "x"},
        ).status_code in (401, 302)

    def test_unack_requires_login(self, client, db_session):
        assert client.delete(
            "/api/system/network-health/hosts/acknowledge",
            json={"hostname": "h1"},
        ).status_code in (401, 302)

    def test_list_requires_permission(self, limited_client, db_session):
        assert limited_client.get("/api/system/network-health/hosts").status_code == 403

    def test_detail_requires_permission(self, limited_client, db_session):
        assert limited_client.get("/api/system/network-health/hosts/h1/detail").status_code == 403

    def test_ack_requires_permission(self, limited_client, db_session):
        assert limited_client.post(
            "/api/system/network-health/hosts/acknowledge",
            json={"hostname": "h1", "comment": "x"},
        ).status_code == 403

    def test_unack_requires_permission(self, limited_client, db_session):
        assert limited_client.delete(
            "/api/system/network-health/hosts/acknowledge",
            json={"hostname": "h1"},
        ).status_code == 403


# ==========================================================
# GET /api/system/network-health/hosts  (list)
# ==========================================================

class TestListHosts:

    def test_empty_db(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/network-health/hosts")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["items"] == []
        assert data["total"] == 0

    def test_returns_all_hosts(self, logged_in_client, db_session):
        _seed_realistic_network(db_session)
        resp = logged_in_client.get("/api/system/network-health/hosts?per_page=100")
        assert resp.get_json()["data"]["total"] == 5

    def test_latest_snapshot_only(self, logged_in_client, db_session):
        """Older rows must not be returned — only the most recent per host."""
        _make_host(db_session, "h1", HostStateType.DOWN, ts=_ts(-7200))
        _make_host(db_session, "h1", HostStateType.UP, ts=_ts(-60))
        db_session.session.commit()
        data = logged_in_client.get("/api/system/network-health/hosts").get_json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["state"] == HostStateType.UP.value

    def test_filter_by_state_down(self, logged_in_client, db_session):
        _make_host(db_session, "h-up", HostStateType.UP)
        _make_host(db_session, "h-down", HostStateType.DOWN)
        db_session.session.commit()
        data = logged_in_client.get("/api/system/network-health/hosts?state=DOWN").get_json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["hostname"] == "h-down"

    def test_filter_by_state_up(self, logged_in_client, db_session):
        _make_host(db_session, "h-up", HostStateType.UP)
        _make_host(db_session, "h-down", HostStateType.DOWN)
        db_session.session.commit()
        assert logged_in_client.get("/api/system/network-health/hosts?state=UP").get_json()["data"]["total"] == 1

    def test_filter_by_state_unreachable(self, logged_in_client, db_session):
        _make_host(db_session, "h1", HostStateType.UNREACHABLE)
        _make_host(db_session, "h2", HostStateType.UP)
        db_session.session.commit()
        data = logged_in_client.get("/api/system/network-health/hosts?state=UNREACHABLE").get_json()["data"]
        assert data["total"] == 1

    def test_filter_invalid_state_returns_400(self, logged_in_client, db_session):
        assert logged_in_client.get("/api/system/network-health/hosts?state=NONSENSE").status_code == 400

    def test_search_partial_match(self, logged_in_client, db_session):
        _make_host(db_session, "webserver01")
        _make_host(db_session, "dbserver01")
        db_session.session.commit()
        data = logged_in_client.get("/api/system/network-health/hosts?search=web").get_json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["hostname"] == "webserver01"

    def test_search_case_insensitive(self, logged_in_client, db_session):
        _make_host(db_session, "WebServer")
        db_session.session.commit()
        data = logged_in_client.get("/api/system/network-health/hosts?search=webserver").get_json()["data"]
        assert data["total"] == 1

    def test_pagination(self, logged_in_client, db_session):
        for i in range(10):
            _make_host(db_session, f"host{i:02d}")
        db_session.session.commit()
        data = logged_in_client.get("/api/system/network-health/hosts?page=2&per_page=3").get_json()["data"]
        assert data["page"] == 2
        assert len(data["items"]) == 3

    def test_sort_hostname_asc(self, logged_in_client, db_session):
        for name in ["charlie", "alpha", "bravo"]:
            _make_host(db_session, name)
        db_session.session.commit()
        names = [h["hostname"] for h in logged_in_client.get(
            "/api/system/network-health/hosts?sort_by=hostname&order=asc"
        ).get_json()["data"]["items"]]
        assert names == sorted(names)

    def test_sort_hostname_desc(self, logged_in_client, db_session):
        for name in ["charlie", "alpha", "bravo"]:
            _make_host(db_session, name)
        db_session.session.commit()
        names = [h["hostname"] for h in logged_in_client.get(
            "/api/system/network-health/hosts?sort_by=hostname&order=desc"
        ).get_json()["data"]["items"]]
        assert names == sorted(names, reverse=True)

    def test_invalid_page_returns_400(self, logged_in_client, db_session):
        assert logged_in_client.get("/api/system/network-health/hosts?page=0").status_code == 400

    def test_invalid_per_page_returns_400(self, logged_in_client, db_session):
        assert logged_in_client.get("/api/system/network-health/hosts?per_page=0").status_code == 400

    def test_invalid_order_returns_400(self, logged_in_client, db_session):
        assert logged_in_client.get("/api/system/network-health/hosts?order=sideways").status_code == 400

    def test_invalid_sort_returns_400(self, logged_in_client, db_session):
        assert logged_in_client.get("/api/system/network-health/hosts?sort_by=badfield").status_code == 400

    def test_invalid_ack_filter_returns_400(self, logged_in_client, db_session):
        assert logged_in_client.get("/api/system/network-health/hosts?ack_filter=nope").status_code == 400

    def test_response_item_shape(self, logged_in_client, db_session):
        _make_host(db_session, "h1")
        db_session.session.commit()
        item = logged_in_client.get("/api/system/network-health/hosts").get_json()["data"]["items"][0]
        for key in ("hostname", "state", "state_type", "last_check",
                    "check_latency", "plugin_output", "is_flapping",
                    "in_downtime", "nagios_ack", "ack"):
            assert key in item

    def test_ack_filter_unacknowledged(self, logged_in_client, db_session):
        _make_host(db_session, "h1", HostStateType.DOWN)
        _make_host(db_session, "h2", HostStateType.DOWN)
        db_session.session.commit()
        logged_in_client.post(
            "/api/system/network-health/hosts/acknowledge",
            json={"hostname": "h1", "comment": "acked"},
        )
        data = logged_in_client.get(
            "/api/system/network-health/hosts?ack_filter=unacknowledged"
        ).get_json()["data"]
        hostnames = {h["hostname"] for h in data["items"]}
        assert "h1" not in hostnames
        assert "h2" in hostnames

    def test_ack_filter_acknowledged(self, logged_in_client, db_session):
        _make_host(db_session, "h1", HostStateType.DOWN)
        _make_host(db_session, "h2", HostStateType.DOWN)
        db_session.session.commit()
        logged_in_client.post(
            "/api/system/network-health/hosts/acknowledge",
            json={"hostname": "h1", "comment": "acked"},
        )
        data = logged_in_client.get(
            "/api/system/network-health/hosts?ack_filter=acknowledged"
        ).get_json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["hostname"] == "h1"
        assert data["items"][0]["ack"] is not None


# ==========================================================
# GET /api/system/network-health/hosts/<hostname>/detail
# ==========================================================

class TestHostDetail:

    def test_not_found_returns_404(self, logged_in_client, db_session):
        assert logged_in_client.get("/api/system/network-health/hosts/ghost/detail").status_code == 404

    def test_returns_detail(self, logged_in_client, db_session):
        h = _make_host(db_session, "router", HostStateType.UP)
        _make_host_perf(db_session, h, "rta", 2.5, "ms", 100.0, 200.0)
        _make_host_perf(db_session, h, "pl", 0.0, "%", 20.0, 60.0)
        db_session.session.commit()
        resp = logged_in_client.get("/api/system/network-health/hosts/router/detail")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["hostname"] == "router"
        assert data["state"] == HostStateType.UP.value
        assert len(data["perf_data"]) == 2

    def test_perf_data_shape(self, logged_in_client, db_session):
        h = _make_host(db_session, "h1")
        _make_host_perf(db_session, h, "rta", 3.0, "ms", 100.0, 200.0, 0.0, 1000.0)
        db_session.session.commit()
        perf = logged_in_client.get(
            "/api/system/network-health/hosts/h1/detail"
        ).get_json()["data"]["perf_data"][0]
        assert perf["metric"] == "rta"
        assert perf["value"] == pytest.approx(3.0)
        assert perf["unit"] == "ms"
        assert perf["warn"] == pytest.approx(100.0)
        assert perf["crit"] == pytest.approx(200.0)
        assert perf["min"] == pytest.approx(0.0)

    def test_includes_associated_services(self, logged_in_client, db_session):
        _make_host(db_session, "h1")
        _make_service(db_session, "h1", "http-80-TCP", ServiceStateType.OK)
        _make_service(db_session, "h1", "ssh-22-TCP", ServiceStateType.WARNING)
        db_session.session.commit()
        svcs = {s["service"] for s in logged_in_client.get(
            "/api/system/network-health/hosts/h1/detail"
        ).get_json()["data"]["services"]}
        assert "http-80-TCP" in svcs
        assert "ssh-22-TCP" in svcs

    def test_latest_snapshot_only(self, logged_in_client, db_session):
        _make_host(db_session, "h1", HostStateType.DOWN, ts=_ts(-7200))
        _make_host(db_session, "h1", HostStateType.UP, ts=_ts(-60))
        db_session.session.commit()
        state = logged_in_client.get(
            "/api/system/network-health/hosts/h1/detail"
        ).get_json()["data"]["state"]
        assert state == HostStateType.UP.value

    def test_response_shape(self, logged_in_client, db_session):
        _make_host(db_session, "h1")
        db_session.session.commit()
        data = logged_in_client.get(
            "/api/system/network-health/hosts/h1/detail"
        ).get_json()["data"]
        for key in (
            "hostname", "state", "state_type", "plugin_output", "last_check",
            "last_state_change", "last_hard_state_change", "last_time_up",
            "last_time_down", "last_time_unreachable", "check_latency",
            "check_execution_time", "is_flapping", "in_downtime",
            "nagios_ack", "ack", "perf_data", "services",
        ):
            assert key in data


# ==========================================================
# POST /api/system/network-health/hosts/acknowledge
# DELETE /api/system/network-health/hosts/acknowledge
# ==========================================================

class TestHostAck:

    def test_acknowledge_down_host(self, logged_in_client, db_session):
        _make_host(db_session, "dbserver", HostStateType.DOWN)
        db_session.session.commit()
        resp = logged_in_client.post(
            "/api/system/network-health/hosts/acknowledge",
            json={"hostname": "dbserver", "comment": "investigating"},
        )
        assert resp.status_code == 201
        assert resp.get_json()["success"] is True

    def test_acknowledge_unreachable_host(self, logged_in_client, db_session):
        _make_host(db_session, "h1", HostStateType.UNREACHABLE)
        db_session.session.commit()
        resp = logged_in_client.post(
            "/api/system/network-health/hosts/acknowledge",
            json={"hostname": "h1", "comment": "unreachable"},
        )
        assert resp.status_code == 201

    def test_acknowledge_up_host_returns_409(self, logged_in_client, db_session):
        _make_host(db_session, "alive", HostStateType.UP)
        db_session.session.commit()
        resp = logged_in_client.post(
            "/api/system/network-health/hosts/acknowledge",
            json={"hostname": "alive", "comment": "x"},
        )
        assert resp.status_code == 409

    def test_acknowledge_not_found_returns_404(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/api/system/network-health/hosts/acknowledge",
            json={"hostname": "ghost", "comment": "x"},
        )
        assert resp.status_code == 404

    def test_missing_hostname_returns_400(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/api/system/network-health/hosts/acknowledge",
            json={"hostname": "", "comment": "x"},
        )
        assert resp.status_code == 400

    def test_missing_comment_returns_400(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/api/system/network-health/hosts/acknowledge",
            json={"hostname": "h1", "comment": ""},
        )
        assert resp.status_code == 400

    def test_ack_appears_in_detail_panel(self, logged_in_client, db_session):
        _make_host(db_session, "h1", HostStateType.DOWN)
        db_session.session.commit()
        logged_in_client.post(
            "/api/system/network-health/hosts/acknowledge",
            json={"hostname": "h1", "comment": "looking into it"},
        )
        ack = logged_in_client.get(
            "/api/system/network-health/hosts/h1/detail"
        ).get_json()["data"]["ack"]
        assert ack is not None
        assert ack["comment"] == "looking into it"
        assert "acknowledged_by" in ack
        assert "acknowledged_at" in ack

    def test_unacknowledge_host(self, logged_in_client, db_session):
        _make_host(db_session, "h1", HostStateType.DOWN)
        db_session.session.commit()
        logged_in_client.post(
            "/api/system/network-health/hosts/acknowledge",
            json={"hostname": "h1", "comment": "ack"},
        )
        resp = logged_in_client.delete(
            "/api/system/network-health/hosts/acknowledge",
            json={"hostname": "h1"},
        )
        assert resp.status_code == 200

    def test_unacknowledge_clears_ack_in_detail(self, logged_in_client, db_session):
        _make_host(db_session, "h1", HostStateType.DOWN)
        db_session.session.commit()
        logged_in_client.post(
            "/api/system/network-health/hosts/acknowledge",
            json={"hostname": "h1", "comment": "ack"},
        )
        logged_in_client.delete(
            "/api/system/network-health/hosts/acknowledge",
            json={"hostname": "h1"},
        )
        ack = logged_in_client.get(
            "/api/system/network-health/hosts/h1/detail"
        ).get_json()["data"]["ack"]
        assert ack is None

    def test_unacknowledge_not_found_returns_404(self, logged_in_client, db_session):
        resp = logged_in_client.delete(
            "/api/system/network-health/hosts/acknowledge",
            json={"hostname": "nobody"},
        )
        assert resp.status_code == 404

    def test_unacknowledge_missing_hostname_returns_400(self, logged_in_client, db_session):
        resp = logged_in_client.delete(
            "/api/system/network-health/hosts/acknowledge",
            json={"hostname": ""},
        )
        assert resp.status_code == 400
