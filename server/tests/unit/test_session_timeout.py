"""
Tests for the idle session timeout (enforce_session_timeout in
app/api/user/login.py), driven by SystemSettings.Session_Timeout.

The last-activity time lives in the signed session cookie, so tests
move it into the past with client.session_transaction() instead of
waiting for real time to pass.
"""
import time

import pytest

from app.system_models import SystemSettings


def set_session_timeout(db_session, minutes):
    db_session.session.add(SystemSettings(Id=1, Session_Timeout=minutes))
    db_session.session.commit()


def set_idle_minutes(client, minutes):
    with client.session_transaction() as sess:
        sess["last_activity"] = time.time() - minutes * 60


def get_last_activity(client):
    with client.session_transaction() as sess:
        return sess.get("last_activity")


class TestSessionTimeout:
    def test_login_records_last_activity(self, logged_in_client):
        assert get_last_activity(logged_in_client) is not None

    def test_request_within_timeout_succeeds(self, logged_in_client, db_session):
        set_session_timeout(db_session, 15)
        set_idle_minutes(logged_in_client, 10)

        resp = logged_in_client.get("/api/user/me")

        assert resp.status_code == 200

    def test_request_refreshes_last_activity(self, logged_in_client, db_session):
        set_session_timeout(db_session, 15)
        set_idle_minutes(logged_in_client, 10)
        before = get_last_activity(logged_in_client)

        logged_in_client.get("/api/user/me")

        assert get_last_activity(logged_in_client) > before

    def test_request_after_timeout_is_rejected(self, logged_in_client, db_session):
        set_session_timeout(db_session, 15)
        set_idle_minutes(logged_in_client, 16)

        resp = logged_in_client.get("/api/user/me")

        assert resp.status_code == 401
        body = resp.get_json()
        assert body["success"] is False
        assert "Session expired" in body["message"]

    def test_expired_session_stays_logged_out(self, logged_in_client, db_session):
        set_session_timeout(db_session, 15)
        set_idle_minutes(logged_in_client, 16)
        logged_in_client.get("/api/user/me")

        resp = logged_in_client.get("/api/user/me")

        assert resp.status_code == 401
        assert get_last_activity(logged_in_client) is None

    def test_longer_setting_allows_longer_idle(self, logged_in_client, db_session):
        set_session_timeout(db_session, 60)
        set_idle_minutes(logged_in_client, 40)

        resp = logged_in_client.get("/api/user/me")

        assert resp.status_code == 200

    @pytest.mark.parametrize("idle_minutes, expected_status", [(29, 200), (31, 401)])
    def test_defaults_to_30_minutes_without_settings_row(
        self, logged_in_client, idle_minutes, expected_status
    ):
        set_idle_minutes(logged_in_client, idle_minutes)

        resp = logged_in_client.get("/api/user/me")

        assert resp.status_code == expected_status

    def test_logout_clears_last_activity(self, logged_in_client):
        resp = logged_in_client.post("/api/user/logout")

        assert resp.status_code == 200
        assert get_last_activity(logged_in_client) is None

    def test_login_resets_stale_activity(self, client, db_session, admin_user):
        set_session_timeout(db_session, 15)
        set_idle_minutes(client, 120)

        login = client.post(
            "/api/user/login",
            json={"email": "admin@example.com", "password": "AdminPass1!"},
        )
        resp = client.get("/api/user/me")

        assert login.status_code == 200
        assert resp.status_code == 200
