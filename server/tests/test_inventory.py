"""
tests/test_inventory.py — Tests for the device-inventory endpoints.

Endpoints tested:
  GET /api/system/inventory
  GET /api/system/inventory/<device_id>/ports/tcp
  GET /api/system/inventory/<device_id>/ports/udp
"""
import pytest
from datetime import datetime, timezone

from app.system_models import (
    NetworkDiscovery,
    NetworkDiscoveryStatus,
    DiscoveryStatus,
    Open_TCP_Services,
    Open_UDP_Services,
    ActivityLog,
)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_activity_log(db_session, admin_user):
    log = ActivityLog(
        Action_Type="test",
        UserID=admin_user.UserID,
    )
    db_session.session.add(log)
    db_session.session.flush()
    return log


def _make_discovery_status(db_session, admin_user):
    log = _make_activity_log(db_session, admin_user)
    status = NetworkDiscoveryStatus(
        Status=DiscoveryStatus.SUCCESS,
        Progress=100,
        Message="Done",
        LogID=log.LogID,
    )
    db_session.session.add(status)
    db_session.session.flush()
    return status


def _make_device(db_session, status_id, *, hostname="host1", ip="192.168.1.1", network="192.168.1.0"):
    device = NetworkDiscovery(
        Hostname=hostname,
        IP_Address=ip,
        Network=network,
        DiscoveryStatusID=status_id,
    )
    db_session.session.add(device)
    db_session.session.flush()
    return device


# ─── auth guard ───────────────────────────────────────────────────────────────

class TestInventoryAuth:
    def test_inventory_requires_login(self, client, db_session):
        resp = client.get("/api/system/inventory")
        assert resp.status_code in (401, 302)


# ─── basic queries ────────────────────────────────────────────────────────────

class TestInventoryList:
    def test_inventory_returns_empty_list(self, logged_in_client, db_session, admin_user):
        resp = logged_in_client.get("/api/system/inventory")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_inventory_returns_devices(self, logged_in_client, db_session, admin_user):
        status = _make_discovery_status(db_session, admin_user)
        for i in range(3):
            _make_device(
                db_session,
                status.DiscoveryStatusID,
                hostname=f"host{i}",
                ip=f"10.0.0.{i}",
                network="10.0.0.0",
            )
        db_session.session.commit()

        resp = logged_in_client.get("/api/system/inventory")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 3
        assert len(data["items"]) == 3
        assert data["page"] == 1

    def test_inventory_pagination(self, logged_in_client, db_session, admin_user):
        status = _make_discovery_status(db_session, admin_user)
        for i in range(15):
            _make_device(
                db_session,
                status.DiscoveryStatusID,
                hostname=f"host{i:02d}",
                ip=f"10.0.1.{i}",
                network="10.0.1.0",
            )
        db_session.session.commit()

        resp = logged_in_client.get("/api/system/inventory?page=2&per_page=5")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["page"] == 2
        assert data["per_page"] == 5
        assert len(data["items"]) == 5
        assert data["total"] == 15


# ─── sorting ──────────────────────────────────────────────────────────────────

class TestInventorySort:
    def _seed_devices(self, db_session, admin_user):
        status = _make_discovery_status(db_session, admin_user)
        for name in ["charlie", "alpha", "bravo"]:
            _make_device(
                db_session,
                status.DiscoveryStatusID,
                hostname=name,
                ip=f"10.0.2.{ord(name[0])}",
                network="10.0.2.0",
            )
        db_session.session.commit()

    def test_inventory_sort_by_hostname_asc(self, logged_in_client, db_session, admin_user):
        self._seed_devices(db_session, admin_user)
        resp = logged_in_client.get("/api/system/inventory?sort_by=hostname&order=asc")
        assert resp.status_code == 200
        names = [d["hostname"] for d in resp.get_json()["items"]]
        assert names == sorted(names)

    def test_inventory_sort_by_hostname_desc(self, logged_in_client, db_session, admin_user):
        self._seed_devices(db_session, admin_user)
        resp = logged_in_client.get("/api/system/inventory?sort_by=hostname&order=desc")
        assert resp.status_code == 200
        names = [d["hostname"] for d in resp.get_json()["items"]]
        assert names == sorted(names, reverse=True)

    def test_inventory_invalid_sort_field(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/inventory?sort_by=nonexistent_field")
        assert resp.status_code == 400
        assert "message" in resp.get_json()

    def test_inventory_invalid_order(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/inventory?order=sideways")
        assert resp.status_code == 400
        assert "message" in resp.get_json()


# ─── pagination validation ────────────────────────────────────────────────────

class TestInventoryPaginationValidation:
    def test_inventory_page_less_than_one(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/inventory?page=0")
        assert resp.status_code == 400
        assert "message" in resp.get_json()

    def test_inventory_per_page_exceeds_100(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/inventory?per_page=101")
        assert resp.status_code == 400
        assert "message" in resp.get_json()


# ─── search ───────────────────────────────────────────────────────────────────

class TestInventorySearch:
    def test_inventory_search_by_hostname(self, logged_in_client, db_session, admin_user):
        status = _make_discovery_status(db_session, admin_user)
        _make_device(db_session, status.DiscoveryStatusID, hostname="webserver01", ip="10.0.3.1", network="10.0.3.0")
        _make_device(db_session, status.DiscoveryStatusID, hostname="dbserver01", ip="10.0.3.2", network="10.0.3.0")
        db_session.session.commit()

        resp = logged_in_client.get("/api/system/inventory?search=webserver")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 1
        assert data["items"][0]["hostname"] == "webserver01"

    def test_inventory_search_no_results(self, logged_in_client, db_session, admin_user):
        status = _make_discovery_status(db_session, admin_user)
        _make_device(db_session, status.DiscoveryStatusID, hostname="routerA", ip="10.0.4.1", network="10.0.4.0")
        db_session.session.commit()

        resp = logged_in_client.get("/api/system/inventory?search=zzz_no_match")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 0
        assert data["items"] == []


# ─── TCP port endpoints ────────────────────────────────────────────────────────

class TestTCPPorts:
    def test_tcp_ports_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/inventory/99999/ports/tcp")
        assert resp.status_code == 404
        assert "message" in resp.get_json()

    def test_tcp_ports_returns_ports(self, logged_in_client, db_session, admin_user):
        status = _make_discovery_status(db_session, admin_user)
        device = _make_device(db_session, status.DiscoveryStatusID, hostname="tcp-host", ip="10.0.5.1", network="10.0.5.0")

        for port_num, svc in [(80, "http"), (443, "https")]:
            tcp = Open_TCP_Services(
                Port_Number=port_num,
                Service_Name=svc,
                NetDiscoveryID=device.NetDiscoveryID,
            )
            db_session.session.add(tcp)
        db_session.session.commit()

        resp = logged_in_client.get(f"/api/system/inventory/{device.NetDiscoveryID}/ports/tcp")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["protocol"] == "TCP"
        assert len(data["ports"]) == 2
        port_numbers = {p["port"] for p in data["ports"]}
        assert port_numbers == {80, 443}


# ─── UDP port endpoints ────────────────────────────────────────────────────────

class TestUDPPorts:
    def test_udp_ports_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/inventory/99999/ports/udp")
        assert resp.status_code == 404
        assert "message" in resp.get_json()

    def test_udp_ports_returns_ports(self, logged_in_client, db_session, admin_user):
        status = _make_discovery_status(db_session, admin_user)
        device = _make_device(db_session, status.DiscoveryStatusID, hostname="udp-host", ip="10.0.6.1", network="10.0.6.0")

        for port_num, svc in [(53, "dns"), (123, "ntp")]:
            udp = Open_UDP_Services(
                Port_Number=port_num,
                Service_Name=svc,
                NetDiscoveryID=device.NetDiscoveryID,
            )
            db_session.session.add(udp)
        db_session.session.commit()

        resp = logged_in_client.get(f"/api/system/inventory/{device.NetDiscoveryID}/ports/udp")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["protocol"] == "UDP"
        assert len(data["ports"]) == 2
        port_numbers = {p["port"] for p in data["ports"]}
        assert port_numbers == {53, 123}
