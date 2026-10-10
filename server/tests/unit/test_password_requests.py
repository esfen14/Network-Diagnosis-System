from app.system_models import PasswordResetRequest, UserStatus
from tests.unit.test_management import _make_user

NEW_PASSWORD = "BrandNewPass1!xyz"


def _request(client, email):
    return client.post("/api/user/forgot-password", json={"email": email})


def _pending(db_session):
    return db_session.session.scalars(
        db_session.select(PasswordResetRequest).where(PasswordResetRequest.Status == "Pending")
    ).all()


class TestForgotPassword:
    def test_creates_pending_request_without_login(self, client, db_session, admin_role):
        _make_user(db_session, admin_role, "forgetful@example.com")
        resp = _request(client, "Forgetful@Example.com")
        assert resp.status_code == 200
        assert len(_pending(db_session)) == 1

    def test_repeat_request_is_not_duplicated(self, client, db_session, admin_role):
        _make_user(db_session, admin_role, "forgetful@example.com")
        _request(client, "forgetful@example.com")
        _request(client, "forgetful@example.com")
        assert len(_pending(db_session)) == 1

    def test_unknown_and_inactive_emails_look_identical(self, client, db_session, admin_role):
        _make_user(db_session, admin_role, "off@example.com", status=UserStatus.INACTIVE)
        known = _request(client, "off@example.com")
        unknown = _request(client, "nobody@example.com")
        assert known.status_code == unknown.status_code == 200
        assert known.get_json() == unknown.get_json()
        assert _pending(db_session) == []

    def test_invalid_email_rejected(self, client):
        assert _request(client, "not-an-email").status_code == 400


class TestAdminHandling:
    def test_list_requires_login(self, client):
        assert client.get("/api/user/password-requests").status_code == 401

    def test_non_admin_cannot_list_or_resolve(self, client, db_session, regular_user):
        client.post("/api/user/login", json={"email": regular_user.Email, "password": "RegularPass1!"})
        assert client.get("/api/user/password-requests").status_code == 403
        assert client.post("/api/user/password-requests/1/resolve", json={}).status_code == 403

    def test_admin_lists_then_resolves(self, logged_in_client, db_session, admin_role):
        target = _make_user(db_session, admin_role, "forgetful@example.com", password="OldPass1!abcd")
        _request(logged_in_client, "forgetful@example.com")

        listed = logged_in_client.get("/api/user/password-requests").get_json()["data"]
        assert listed["count"] == 1
        assert listed["items"][0]["email"] == "forgetful@example.com"

        req_id = listed["items"][0]["id"]
        resp = logged_in_client.post(
            f"/api/user/password-requests/{req_id}/resolve",
            json={"password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
        )
        assert resp.status_code == 200
        db_session.session.refresh(target)
        assert target.check_password(NEW_PASSWORD)
        assert target.Must_Change_Password is True
        assert _pending(db_session) == []

    def test_resolve_validates_password(self, logged_in_client, db_session, admin_role):
        target = _make_user(db_session, admin_role, "forgetful@example.com", password="OldPass1!abcd")
        _request(logged_in_client, "forgetful@example.com")
        req_id = _pending(db_session)[0].RequestID
        resp = logged_in_client.post(
            f"/api/user/password-requests/{req_id}/resolve",
            json={"password": "weak", "confirm_password": "weak"},
        )
        assert resp.status_code == 400
        db_session.session.refresh(target)
        assert target.check_password("OldPass1!abcd")
        assert len(_pending(db_session)) == 1

    def test_handled_request_cannot_be_reused(self, logged_in_client, db_session, admin_role):
        _make_user(db_session, admin_role, "forgetful@example.com")
        _request(logged_in_client, "forgetful@example.com")
        req_id = _pending(db_session)[0].RequestID
        assert logged_in_client.post(f"/api/user/password-requests/{req_id}/dismiss").status_code == 200
        assert logged_in_client.post(f"/api/user/password-requests/{req_id}/dismiss").status_code == 409
        resp = logged_in_client.post(
            f"/api/user/password-requests/{req_id}/resolve",
            json={"password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
        )
        assert resp.status_code == 409
