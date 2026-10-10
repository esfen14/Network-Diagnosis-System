"""
tests/unit/test_network_discovery.py — Tests for the network-discovery endpoints.

Endpoints tested:
  POST /api/system/discover/start
  POST /api/system/network-discovery/stop
  GET  /api/system/discover/status
"""
import pytest
from threading import Event, Thread
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

    def test_simultaneous_starts_reserve_one_scan(self, app):
        """Two requests that both see an idle worker must not launch two scans."""
        import app.api.system.network_discovery as nd_module

        entered = Event()
        release = Event()
        results = []
        old_thread = nd_module.discovery_thread
        existing = MagicMock()

        def check_idle():
            entered.set()
            assert release.wait(timeout=5)
            return False

        existing.is_alive.side_effect = check_idle
        nd_module.discovery_thread = existing

        def start():
            with app.app_context():
                results.append(nd_module.start_discovery_thread(1))

        try:
            with patch.object(nd_module.threading, "Thread") as worker_cls:
                worker_cls.return_value.is_alive.return_value = True
                workers = [Thread(target=start) for _ in range(2)]
                workers[0].start()
                assert entered.wait(timeout=5)
                workers[1].start()
                release.set()
                for worker in workers:
                    worker.join(timeout=5)
                assert all(not worker.is_alive() for worker in workers)
                assert sorted(results) == [False, True]
                assert worker_cls.call_count == 1
        finally:
            release.set()
            nd_module.discovery_thread = old_thread

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

    def test_discover_stop_running_sets_event(self, logged_in_client, db_session):
        """A running scan gets its stop event set and the route returns 200."""
        import app.api.system.network_discovery as nd_module
        fake_thread = MagicMock()
        fake_thread.is_alive.return_value = True
        nd_module.discovery_thread = fake_thread
        nd_module.discovery_thread_stop_event.clear()

        try:
            resp = logged_in_client.post("/api/system/network-discovery/stop")
            assert resp.status_code == 200
            assert nd_module.discovery_thread_stop_event.is_set()
        finally:
            nd_module.discovery_thread = None
            nd_module.discovery_thread_stop_event.clear()


# ─── cancelled scans ─────────────────────────────────────────────────────────

class TestDiscoveryCancelled:
    def test_mark_interrupted_keeps_progress(self, db_session, admin_user):
        """A cancelled run leaves "Running" and keeps the progress it reached."""
        from app.network_discovery.create_host_cfg import mark_discovery_interrupted
        ds = _seed_discovery_status(db_session, admin_user, status=DiscoveryStatus.RUNNING)
        ds.Progress = 40
        db_session.session.commit()

        mark_discovery_interrupted(ds.DiscoveryStatusID)

        refreshed = db_session.session.get(NetworkDiscoveryStatus, ds.DiscoveryStatusID)
        assert refreshed.Status == DiscoveryStatus.INTERRUPTED
        assert refreshed.Progress == 40
        assert refreshed.Completed_At is not None

    def test_stop_before_scan_marks_interrupted(self, app, db_session, admin_user):
        """Stopping before nmap runs records the run as Interrupted, not Running."""
        import threading
        from app.network_discovery import create_host_cfg
        stop_event = threading.Event()
        stop_event.set()

        with patch.object(create_host_cfg, "discover_network") as fake_discover:
            create_host_cfg.discover_network_create_hosts(app, admin_user.UserID, stop_event)
            fake_discover.assert_not_called()

        latest = db_session.session.scalars(
            db_session.select(NetworkDiscoveryStatus)
            .order_by(NetworkDiscoveryStatus.DiscoveryStatusID.desc())
        ).first()
        assert latest.Status == DiscoveryStatus.INTERRUPTED


# ─── /discover/status ────────────────────────────────────────────────────────

class TestDiscoverStatus:
    def test_discover_status_no_records(self, logged_in_client, db_session):
        """When no discovery has run yet, return 200 with an informational message."""
        resp = logged_in_client.get("/api/system/discover/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "message" in data
