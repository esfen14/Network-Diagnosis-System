"""
tests/test_auth.py — Tests for login / logout endpoints.

Endpoints tested:
  POST /api/user/login
  POST /api/user/logout
"""
import pytest


class TestLogin:
    # ── happy path ────────────────────────────────────────────────────────────

    def test_login_success(self, client, db_session, admin_user):
        resp = client.post(
            "/api/user/login",
            json={"email": "admin@example.com", "password": "AdminPass1!"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "logged in" in data["message"].lower()

    def test_login_already_logged_in(self, client, db_session, admin_user):
        # First login
        client.post(
            "/api/user/login",
            json={"email": "admin@example.com", "password": "AdminPass1!"},
        )
        # Second login attempt while still authenticated
        resp = client.post(
            "/api/user/login",
            json={"email": "admin@example.com", "password": "AdminPass1!"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "already" in data["message"].lower()

    # ── wrong credentials ─────────────────────────────────────────────────────

    def test_login_wrong_password(self, client, db_session, admin_user):
        resp = client.post(
            "/api/user/login",
            json={"email": "admin@example.com", "password": "WrongPass99!"},
        )
        assert resp.status_code == 401
        data = resp.get_json()
        assert "message" in data

    # ── validation errors ─────────────────────────────────────────────────────

    def test_login_invalid_email_format(self, client, db_session, admin_user):
        resp = client.post(
            "/api/user/login",
            json={"email": "not-an-email", "password": "AdminPass1!"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "message" in data

    def test_login_missing_fields(self, client, db_session):
        resp = client.post(
            "/api/user/login",
            json={"email": "admin@example.com"},
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert "message" in data

    def test_login_no_json(self, client, db_session):
        """
        Sending non-JSON body should result in an error response.
        Flask 3.x returns 415 (Unsupported Media Type) when Content-Type is
        not application/json; the endpoint also returns 400 when get_json()
        returns None.  Accept both.
        """
        resp = client.post(
            "/api/user/login",
            data="not json",
            content_type="text/plain",
        )
        assert resp.status_code in (400, 415)

    # ── account status ────────────────────────────────────────────────────────

    def test_login_inactive_user(self, client, db_session, inactive_user):
        resp = client.post(
            "/api/user/login",
            json={"email": "inactive@example.com", "password": "InactivePass1!"},
        )
        assert resp.status_code == 403
        data = resp.get_json()
        assert "message" in data


class TestLogout:
    def test_logout_success(self, client, db_session, admin_user):
        # Log in first
        client.post(
            "/api/user/login",
            json={"email": "admin@example.com", "password": "AdminPass1!"},
        )
        resp = client.post("/api/user/logout")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "logged out" in data["message"].lower()

    def test_logout_requires_login(self, client, db_session):
        """Unauthenticated logout should return 401 (or redirect)."""
        resp = client.post("/api/user/logout")
        # Flask-Login with login_view=None returns 401
        assert resp.status_code in (401, 302)
