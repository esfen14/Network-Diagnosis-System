"""
tests/test_network_services.py
==============================
Tests for app/api/system/network_services.py.

Routes tested:
  GET    /api/system/network-health/services
  GET    /api/system/network-health/services/<hostname>/<path:service_name>/detail
  POST   /api/system/network-health/services/acknowledge
  DELETE /api/system/network-health/services/acknowledge
"""

import pytest

from app.history_models import ServiceStateType

from tests.seed_helpers import (
    _ts,
    _make_service, _make_service_perf,
    _seed_realistic_network,
    NCPA_CPU_SERVICE,
)


# ==========================================================
# Auth / permission guards
# ==========================================================

class TestNetworkServicesAuthGuards:

    def test_list_requires_login(self, client, db_session):
        assert client.get("/api/system/network-health/services").status_code in (401, 302)

    def test_detail_requires_login(self, client, db_session):
        assert client.get(
            "/api/system/network-health/services/h1/http-80-TCP/detail"
        ).status_code in (401, 302)

    def test_ack_requires_login(self, client, db_session):
        assert client.post(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "h1", "service_name": "x", "comment": "x"},
        ).status_code in (401, 302)

    def test_unack_requires_login(self, client, db_session):
        assert client.delete(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "h1", "service_name": "x"},
        ).status_code in (401, 302)

    def test_list_requires_permission(self, limited_client, db_session):
        assert limited_client.get("/api/system/network-health/services").status_code == 403

    def test_detail_requires_permission(self, limited_client, db_session):
        assert limited_client.get(
            "/api/system/network-health/services/h1/http-80-TCP/detail"
        ).status_code == 403

    def test_ack_requires_permission(self, limited_client, db_session):
        assert limited_client.post(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "h1", "service_name": "x", "comment": "x"},
        ).status_code == 403

    def test_unack_requires_permission(self, limited_client, db_session):
        assert limited_client.delete(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "h1", "service_name": "x"},
        ).status_code == 403


# ==========================================================
# GET /api/system/network-health/services  (list)
# ==========================================================

class TestListServices:

    def test_empty_db(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/network-health/services")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["items"] == []
        assert data["total"] == 0

    def test_returns_all_services(self, logged_in_client, db_session):
        _seed_realistic_network(db_session)
        data = logged_in_client.get(
            "/api/system/network-health/services?per_page=100"
        ).get_json()["data"]
        assert data["total"] >= 5

    def test_latest_per_service_only(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "http-80-TCP", ServiceStateType.CRITICAL, ts=_ts(-7200))
        _make_service(db_session, "h1", "http-80-TCP", ServiceStateType.OK, ts=_ts(-60))
        db_session.session.commit()
        data = logged_in_client.get("/api/system/network-health/services").get_json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["state"] == ServiceStateType.OK.value

    def test_filter_by_state_critical(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "http-80-TCP", ServiceStateType.OK)
        _make_service(db_session, "h1", "mysql-3306-TCP", ServiceStateType.CRITICAL)
        db_session.session.commit()
        data = logged_in_client.get(
            "/api/system/network-health/services?state=CRITICAL"
        ).get_json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["service"] == "mysql-3306-TCP"

    def test_filter_by_state_warning(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "disk-0-TCP", ServiceStateType.WARNING)
        _make_service(db_session, "h1", "http-80-TCP", ServiceStateType.OK)
        db_session.session.commit()
        data = logged_in_client.get(
            "/api/system/network-health/services?state=WARNING"
        ).get_json()["data"]
        assert data["total"] == 1

    def test_filter_by_state_unknown(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "snmp-161-UDP", ServiceStateType.UNKNOWN)
        _make_service(db_session, "h1", "http-80-TCP", ServiceStateType.OK)
        db_session.session.commit()
        data = logged_in_client.get(
            "/api/system/network-health/services?state=UNKNOWN"
        ).get_json()["data"]
        assert data["total"] == 1

    def test_filter_invalid_state_returns_400(self, logged_in_client, db_session):
        assert logged_in_client.get(
            "/api/system/network-health/services?state=BADSTATE"
        ).status_code == 400

    def test_filter_by_hostname(self, logged_in_client, db_session):
        _make_service(db_session, "webserver", "http-80-TCP")
        _make_service(db_session, "dbserver", "mysql-3306-TCP")
        db_session.session.commit()
        data = logged_in_client.get(
            "/api/system/network-health/services?hostname=webserver"
        ).get_json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["hostname"] == "webserver"

    def test_search_by_hostname(self, logged_in_client, db_session):
        _make_service(db_session, "webserver", "http-80-TCP")
        _make_service(db_session, "dbserver", "mysql-3306-TCP")
        db_session.session.commit()
        data = logged_in_client.get(
            "/api/system/network-health/services?search=web"
        ).get_json()["data"]
        assert data["total"] == 1

    def test_search_by_service_name(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "http-80-TCP")
        _make_service(db_session, "h1", "ssh-22-TCP")
        db_session.session.commit()
        data = logged_in_client.get(
            "/api/system/network-health/services?search=ssh"
        ).get_json()["data"]
        assert data["total"] == 1

    def test_search_case_insensitive(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "HTTP-80-TCP")
        db_session.session.commit()
        assert logged_in_client.get(
            "/api/system/network-health/services?search=http"
        ).get_json()["data"]["total"] == 1

    def test_pagination(self, logged_in_client, db_session):
        for i in range(8):
            _make_service(db_session, "h1", f"http-{8000+i}-TCP")
        db_session.session.commit()
        data = logged_in_client.get(
            "/api/system/network-health/services?page=2&per_page=3"
        ).get_json()["data"]
        assert data["page"] == 2
        assert len(data["items"]) == 3

    def test_sort_by_service_asc(self, logged_in_client, db_session):
        for name in ["zz-svc", "aa-svc", "mm-svc"]:
            _make_service(db_session, "h1", name)
        db_session.session.commit()
        names = [s["service"] for s in logged_in_client.get(
            "/api/system/network-health/services?sort_by=service&order=asc"
        ).get_json()["data"]["items"]]
        assert names == sorted(names)

    def test_sort_by_service_desc(self, logged_in_client, db_session):
        for name in ["zz-svc", "aa-svc", "mm-svc"]:
            _make_service(db_session, "h1", name)
        db_session.session.commit()
        names = [s["service"] for s in logged_in_client.get(
            "/api/system/network-health/services?sort_by=service&order=desc"
        ).get_json()["data"]["items"]]
        assert names == sorted(names, reverse=True)

    def test_invalid_page_returns_400(self, logged_in_client, db_session):
        assert logged_in_client.get("/api/system/network-health/services?page=0").status_code == 400

    def test_invalid_order_returns_400(self, logged_in_client, db_session):
        assert logged_in_client.get("/api/system/network-health/services?order=sideways").status_code == 400

    def test_invalid_sort_returns_400(self, logged_in_client, db_session):
        assert logged_in_client.get("/api/system/network-health/services?sort_by=badfield").status_code == 400

    def test_invalid_ack_filter_returns_400(self, logged_in_client, db_session):
        assert logged_in_client.get("/api/system/network-health/services?ack_filter=nope").status_code == 400

    def test_response_item_shape(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "http-80-TCP")
        db_session.session.commit()
        item = logged_in_client.get(
            "/api/system/network-health/services"
        ).get_json()["data"]["items"][0]
        for key in ("hostname", "service", "state", "state_type", "last_check",
                    "check_latency", "plugin_output", "is_flapping",
                    "in_downtime", "nagios_ack", "ack"):
            assert key in item

    def test_ncpa_service_with_slash_in_name(self, logged_in_client, db_session):
        """Service names with slashes (NCPA metric paths) must round-trip correctly."""
        _make_service(db_session, "h1", "cpu/percent")
        db_session.session.commit()
        data = logged_in_client.get(
            "/api/system/network-health/services?search=cpu"
        ).get_json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["service"] == "cpu/percent"

    def test_ack_filter_acknowledged(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "mysql-3306-TCP", ServiceStateType.CRITICAL)
        _make_service(db_session, "h1", "http-80-TCP", ServiceStateType.WARNING)
        db_session.session.commit()
        logged_in_client.post(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "h1", "service_name": "mysql-3306-TCP", "comment": "ack"},
        )
        data = logged_in_client.get(
            "/api/system/network-health/services?ack_filter=acknowledged"
        ).get_json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["service"] == "mysql-3306-TCP"

    def test_ack_filter_unacknowledged(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "mysql-3306-TCP", ServiceStateType.CRITICAL)
        _make_service(db_session, "h1", "http-80-TCP", ServiceStateType.WARNING)
        db_session.session.commit()
        logged_in_client.post(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "h1", "service_name": "mysql-3306-TCP", "comment": "ack"},
        )
        data = logged_in_client.get(
            "/api/system/network-health/services?ack_filter=unacknowledged"
        ).get_json()["data"]
        services = {s["service"] for s in data["items"]}
        assert "mysql-3306-TCP" not in services
        assert "http-80-TCP" in services


# ==========================================================
# GET /api/system/network-health/services/<hostname>/<path:service_name>/detail
# ==========================================================

class TestServiceDetail:

    def test_not_found_returns_404(self, logged_in_client, db_session):
        assert logged_in_client.get(
            "/api/system/network-health/services/nohost/noservice/detail"
        ).status_code == 404

    def test_returns_detail(self, logged_in_client, db_session):
        svc = _make_service(db_session, "webserver", "http-80-TCP", ServiceStateType.OK,
                            plugin_output="HTTP OK: 200 - 0.089 s")
        _make_service_perf(db_session, svc, "time", 0.089, "s", 1.0, 5.0, 0.0)
        db_session.session.commit()
        resp = logged_in_client.get(
            "/api/system/network-health/services/webserver/http-80-TCP/detail"
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["hostname"] == "webserver"
        assert data["service"] == "http-80-TCP"
        assert len(data["perf_data"]) == 1

    def test_ncpa_path_with_slash(self, logged_in_client, db_session):
        """<path:service_name> must capture NCPA metric paths with slashes."""
        svc = _make_service(db_session, "webserver", NCPA_CPU_SERVICE)
        _make_service_perf(db_session, svc, "cpu/percent", 15.0, "%")
        db_session.session.commit()
        resp = logged_in_client.get(
            f"/api/system/network-health/services/webserver/{NCPA_CPU_SERVICE}/detail"
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["service"] == NCPA_CPU_SERVICE

    def test_perf_data_shape(self, logged_in_client, db_session):
        svc = _make_service(db_session, "h1", "http-80-TCP")
        _make_service_perf(db_session, svc, "time", 0.1, "s", 1.0, 5.0, 0.0, None)
        db_session.session.commit()
        perf = logged_in_client.get(
            "/api/system/network-health/services/h1/http-80-TCP/detail"
        ).get_json()["data"]["perf_data"][0]
        for key in ("metric", "value", "unit", "warn", "crit", "min", "max"):
            assert key in perf

    def test_response_shape(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "ssh-22-TCP")
        db_session.session.commit()
        data = logged_in_client.get(
            "/api/system/network-health/services/h1/ssh-22-TCP/detail"
        ).get_json()["data"]
        for key in (
            "hostname", "service", "state", "state_type", "plugin_output",
            "last_check", "last_state_change", "last_hard_state_change",
            "last_time_ok", "last_time_warning", "last_time_critical",
            "last_time_unknown", "check_latency", "check_execution_time",
            "is_flapping", "in_downtime", "nagios_ack", "ack", "perf_data",
        ):
            assert key in data

    def test_latest_snapshot_returned(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "http-80-TCP", ServiceStateType.CRITICAL, ts=_ts(-7200))
        _make_service(db_session, "h1", "http-80-TCP", ServiceStateType.OK, ts=_ts(-60))
        db_session.session.commit()
        state = logged_in_client.get(
            "/api/system/network-health/services/h1/http-80-TCP/detail"
        ).get_json()["data"]["state"]
        assert state == ServiceStateType.OK.value

    def test_ack_shown_in_detail(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "mysql-3306-TCP", ServiceStateType.CRITICAL)
        db_session.session.commit()
        logged_in_client.post(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "h1", "service_name": "mysql-3306-TCP", "comment": "on it"},
        )
        ack = logged_in_client.get(
            "/api/system/network-health/services/h1/mysql-3306-TCP/detail"
        ).get_json()["data"]["ack"]
        assert ack is not None
        assert ack["comment"] == "on it"


# ==========================================================
# POST /api/system/network-health/services/acknowledge
# DELETE /api/system/network-health/services/acknowledge
# ==========================================================

class TestServiceAck:

    def test_acknowledge_critical_service(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "mysql-3306-TCP", ServiceStateType.CRITICAL)
        db_session.session.commit()
        resp = logged_in_client.post(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "h1", "service_name": "mysql-3306-TCP", "comment": "on it"},
        )
        assert resp.status_code == 201

    def test_acknowledge_warning_service(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "disk-0-TCP", ServiceStateType.WARNING)
        db_session.session.commit()
        assert logged_in_client.post(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "h1", "service_name": "disk-0-TCP", "comment": "cleaning up"},
        ).status_code == 201

    def test_acknowledge_unknown_service(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "snmp-161-UDP", ServiceStateType.UNKNOWN)
        db_session.session.commit()
        assert logged_in_client.post(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "h1", "service_name": "snmp-161-UDP", "comment": "investigating"},
        ).status_code == 201

    def test_acknowledge_ok_service_returns_409(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "http-80-TCP", ServiceStateType.OK)
        db_session.session.commit()
        assert logged_in_client.post(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "h1", "service_name": "http-80-TCP", "comment": "x"},
        ).status_code == 409

    def test_acknowledge_not_found_returns_404(self, logged_in_client, db_session):
        assert logged_in_client.post(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "ghost", "service_name": "http-80-TCP", "comment": "x"},
        ).status_code == 404

    def test_missing_hostname_returns_400(self, logged_in_client, db_session):
        assert logged_in_client.post(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "", "service_name": "http-80-TCP", "comment": "x"},
        ).status_code == 400

    def test_missing_service_name_returns_400(self, logged_in_client, db_session):
        assert logged_in_client.post(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "h1", "service_name": "", "comment": "x"},
        ).status_code == 400

    def test_missing_comment_returns_400(self, logged_in_client, db_session):
        assert logged_in_client.post(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "h1", "service_name": "http-80-TCP", "comment": ""},
        ).status_code == 400

    def test_double_ack_returns_409(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "mysql-3306-TCP", ServiceStateType.CRITICAL)
        db_session.session.commit()
        logged_in_client.post(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "h1", "service_name": "mysql-3306-TCP", "comment": "first"},
        )
        assert logged_in_client.post(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "h1", "service_name": "mysql-3306-TCP", "comment": "second"},
        ).status_code == 409

    def test_unacknowledge_service(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "mysql-3306-TCP", ServiceStateType.CRITICAL)
        db_session.session.commit()
        logged_in_client.post(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "h1", "service_name": "mysql-3306-TCP", "comment": "ack"},
        )
        assert logged_in_client.delete(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "h1", "service_name": "mysql-3306-TCP"},
        ).status_code == 200

    def test_unacknowledge_clears_ack_in_detail(self, logged_in_client, db_session):
        _make_service(db_session, "h1", "mysql-3306-TCP", ServiceStateType.CRITICAL)
        db_session.session.commit()
        logged_in_client.post(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "h1", "service_name": "mysql-3306-TCP", "comment": "ack"},
        )
        logged_in_client.delete(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "h1", "service_name": "mysql-3306-TCP"},
        )
        ack = logged_in_client.get(
            "/api/system/network-health/services/h1/mysql-3306-TCP/detail"
        ).get_json()["data"]["ack"]
        assert ack is None

    def test_unacknowledge_not_found_returns_404(self, logged_in_client, db_session):
        assert logged_in_client.delete(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "h1", "service_name": "http-80-TCP"},
        ).status_code == 404

    def test_unacknowledge_missing_hostname_returns_400(self, logged_in_client, db_session):
        assert logged_in_client.delete(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "", "service_name": "http-80-TCP"},
        ).status_code == 400

    def test_unacknowledge_missing_service_name_returns_400(self, logged_in_client, db_session):
        assert logged_in_client.delete(
            "/api/system/network-health/services/acknowledge",
            json={"hostname": "h1", "service_name": ""},
        ).status_code == 400
