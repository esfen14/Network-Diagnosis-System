"""
tests/test_network_discovery.py — Tests for the network-discovery endpoints.

Endpoints tested:
  POST /api/system/discover/start
  POST /api/system/network-discovery/stop
  GET  /api/system/discover/status
"""
import pytest
from unittest.mock import patch, MagicMock

from app.system_models import (
    NetworkDiscoveryStatus,
    DiscoveryStatus,
    ActivityLog,
)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _make_activity_log(db_session, admin_user):
    log = ActivityLog(Action_Type="test", UserID=admin_user.UserID)
    db_session.session.add(log)
    db_session.session.flush()
    return log


def _seed_discovery_status(db_session, admin_user, status=DiscoveryStatus.SUCCESS):
    log = _make_activity_log(db_session, admin_user)
    ds = NetworkDiscoveryStatus(
        Status=status,
        Progress=100,
        Message="Done",
        LogID=log.LogID,
    )
    db_session.session.add(ds)
    db_session.session.commit()
    return ds


# ─── /discover/start ─────────────────────────────────────────────────────────

class TestDiscoverStart:
    def test_discover_start_requires_login(self, client, db_session):
        resp = client.post("/api/system/discover/start")
        assert resp.status_code in (401, 302)

    def test_discover_start_success(self, logged_in_client, db_session, admin_user):
        """
        Mock the thread so no real network scan runs.
        Expects 202 with a "started" message.
        """
        with patch(
            "app.api.system.network_discovery.threading.Thread"
        ) as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread.is_alive.return_value = False
            mock_thread_cls.return_value = mock_thread

            # Also patch discover_network_create_hosts to be a no-op
            with patch(
                "app.api.system.network_discovery.discover_network_create_hosts"
            ):
                # Reset the module-level discovery_thread to None
                import app.api.system.network_discovery as nd_module
                nd_module.discovery_thread = None

                resp = logged_in_client.post("/api/system/discover/start")

        assert resp.status_code == 202
        data = resp.get_json()
        assert "message" in data

    def test_discover_start_already_running(self, logged_in_client, db_session):
        """When discovery_thread.is_alive() is True, expect 400."""
        import app.api.system.network_discovery as nd_module

        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        nd_module.discovery_thread = mock_thread

        try:
            resp = logged_in_client.post("/api/system/discover/start")
            assert resp.status_code == 400
            data = resp.get_json()
            assert "message" in data
        finally:
            # Clean up so other tests start fresh
            nd_module.discovery_thread = None


# ─── /network-discovery/stop ──────────────────────────────────────────────────

class TestDiscoverStop:
    def test_discover_stop_not_running(self, logged_in_client, db_session):
        """When there is no running discovery, stop should return 400."""
        import app.api.system.network_discovery as nd_module
        nd_module.discovery_thread = None  # ensure not running

        resp = logged_in_client.post("/api/system/network-discovery/stop")
        assert resp.status_code == 400
        data = resp.get_json()
        assert "message" in data


# ─── /discover/status ────────────────────────────────────────────────────────

class TestDiscoverStatus:
    def test_discover_status_no_records(self, logged_in_client, db_session):
        """When no discovery has run yet, return 200 with an informational message."""
        resp = logged_in_client.get("/api/system/discover/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "message" in data
