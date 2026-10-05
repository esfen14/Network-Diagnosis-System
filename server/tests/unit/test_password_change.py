from app.system_models import User, UserStatus
from tests.unit.test_management import _make_user

NEW_PASSWORD = "BrandNewPass1!xyz"


def _edit(client, user, **overrides):
    body = {
        "first_name": user.First_Name,
        "last_name": user.Last_Name,
        "email": user.Email,
        "role_id": user.RoleID,
        "status": user.Status.value,
    }
    body.update(overrides)
    return client.put(f"/api/user/accounts/{user.UserID}", json=body)


class TestSuspendWithoutPassword:
    def test_suspend_needs_no_password_and_keeps_it(self, logged_in_client, db_session, admin_role):
        target = _make_user(db_session, admin_role, "t1@example.com", password="OldPass1!abcd")
        resp = _edit(logged_in_client, target, status="Suspended")
        assert resp.status_code == 200
        db_session.session.refresh(target)
        assert target.Status == UserStatus.SUSPENDED
        assert target.check_password("OldPass1!abcd")
        assert target.Must_Change_Password is False

    def test_blank_password_fields_mean_unchanged(self, logged_in_client, db_session, admin_role):
        target = _make_user(db_session, admin_role, "t2@example.com", password="OldPass1!abcd")
        resp = _edit(logged_in_client, target, password="", confirm_password="", status="Inactive")
        assert resp.status_code == 200
        db_session.session.refresh(target)
        assert target.check_password("OldPass1!abcd")

    def test_mismatched_password_is_still_rejected(self, logged_in_client, db_session, admin_role):
        target = _make_user(db_session, admin_role, "t3@example.com")
        resp = _edit(logged_in_client, target, password=NEW_PASSWORD, confirm_password="different")
        assert resp.status_code == 400


class TestMustChangePasswordFlag:
    def test_reactivation_sets_flag(self, logged_in_client, db_session, admin_role):
        target = _make_user(db_session, admin_role, "t4@example.com", status=UserStatus.SUSPENDED)
        assert _edit(logged_in_client, target, status="Active").status_code == 200
        db_session.session.refresh(target)
        assert target.Must_Change_Password is True

    def test_editing_an_active_user_does_not_set_flag(self, logged_in_client, db_session, admin_role):
        target = _make_user(db_session, admin_role, "t5@example.com")
        assert _edit(logged_in_client, target, first_name="Renamed").status_code == 200
        db_session.session.refresh(target)
        assert target.Must_Change_Password is False

    def test_admin_password_reset_sets_flag(self, logged_in_client, db_session, admin_role):
        target = _make_user(db_session, admin_role, "t6@example.com")
        resp = _edit(logged_in_client, target, password=NEW_PASSWORD, confirm_password=NEW_PASSWORD)
        assert resp.status_code == 200
        db_session.session.refresh(target)
        assert target.check_password(NEW_PASSWORD)
        assert target.Must_Change_Password is True

    def test_own_password_change_via_edit_does_not_set_flag(self, logged_in_client, db_session, admin_user):
        resp = _edit(logged_in_client, admin_user, password=NEW_PASSWORD, confirm_password=NEW_PASSWORD)
        assert resp.status_code == 200
        db_session.session.refresh(admin_user)
        assert admin_user.Must_Change_Password is False


class TestForcedChange:
    def _flagged_client(self, client, db_session, admin_role):
        user = _make_user(db_session, admin_role, "forced@example.com", password="TempPass1!abcd")
        user.Must_Change_Password = True
        db_session.session.commit()
        resp = client.post("/api/user/login", json={"email": user.Email, "password": "TempPass1!abcd"})
        assert resp.status_code == 200
        assert resp.get_json()["data"]["must_change_password"] is True
        return user

    def test_me_reports_flag_and_other_routes_are_locked(self, client, db_session, admin_role):
        self._flagged_client(client, db_session, admin_role)
        assert client.get("/api/user/me").get_json()["data"]["must_change_password"] is True
        assert client.get("/api/user/roles").status_code == 403

    def test_change_password_unlocks(self, client, db_session, admin_role):
        user = self._flagged_client(client, db_session, admin_role)
        resp = client.post("/api/user/change-password", json={
            "current_password": "TempPass1!abcd",
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
        })
        assert resp.status_code == 200
        db_session.session.refresh(user)
        assert user.Must_Change_Password is False
        assert user.check_password(NEW_PASSWORD)
        assert client.get("/api/user/roles").status_code == 200

    def test_wrong_current_password_rejected(self, client, db_session, admin_role):
        self._flagged_client(client, db_session, admin_role)
        resp = client.post("/api/user/change-password", json={
            "current_password": "nope", "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD,
        })
        assert resp.status_code == 400

    def test_same_password_rejected(self, client, db_session, admin_role):
        self._flagged_client(client, db_session, admin_role)
        resp = client.post("/api/user/change-password", json={
            "current_password": "TempPass1!abcd",
            "new_password": "TempPass1!abcd",
            "confirm_password": "TempPass1!abcd",
        })
        assert resp.status_code == 400

    def test_mismatch_rejected(self, client, db_session, admin_role):
        self._flagged_client(client, db_session, admin_role)
        resp = client.post("/api/user/change-password", json={
            "current_password": "TempPass1!abcd", "new_password": NEW_PASSWORD, "confirm_password": "other",
        })
        assert resp.status_code == 400

    def test_requires_login(self, client, db_session):
        resp = client.post("/api/user/change-password", json={})
        assert resp.status_code in (401, 302)


class TestSuspendedSessionEnds:
    def test_open_session_is_ended_when_account_is_suspended(self, logged_in_client, db_session, admin_user):
        admin_user.Status = UserStatus.SUSPENDED
        db_session.session.commit()
        assert logged_in_client.get("/api/user/me").status_code == 401
