import pytest

from app.system_models import ActivityLog, User
from tests.unit.test_management import _make_user

OLD = "InstallerPass1!abc"
NEW = "BrandNewPass1!xyz"


@pytest.fixture(autouse=True)
def nagios(monkeypatch):
    """Fake the shared Nagios writer; the tests never touch a real config."""
    calls = []

    def fake():
        calls.append(1)
        return "applied", "Applied."

    monkeypatch.setattr("app.api.user.management.regenerate_and_apply_config_status", fake)
    return calls


def _bootstrap_admin(db_session, admin_role):
    user = _make_user(db_session, admin_role, "admin-ab12cd@pinpoint.lan", password=OLD)
    user.Needs_Setup = True
    db_session.session.commit()
    return user


def _login(client, user, password=OLD):
    resp = client.post("/api/user/login", json={"email": user.Email, "password": password})
    assert resp.status_code == 200
    return resp


def _setup(client, **overrides):
    body = {
        "current_password": OLD,
        "new_email": "ops@company.com",
        "new_password": NEW,
        "confirm_password": NEW,
    }
    body.update(overrides)
    return client.post("/api/user/complete-setup", json=body)


class TestGate:
    def test_login_and_me_report_needs_setup(self, client, db_session, admin_role):
        user = _bootstrap_admin(db_session, admin_role)
        assert _login(client, user).get_json()["data"]["needs_setup"] is True
        assert client.get("/api/user/me").get_json()["data"]["needs_setup"] is True

    def test_everything_else_is_blocked(self, client, db_session, admin_role):
        _login(client, _bootstrap_admin(db_session, admin_role))
        assert client.get("/api/user/roles").status_code == 403
        assert client.get("/api/user/accounts").status_code == 403

    def test_change_password_cannot_skip_the_email_step(self, client, db_session, admin_role):
        user = _bootstrap_admin(db_session, admin_role)
        _login(client, user)
        resp = client.post("/api/user/change-password", json={
            "current_password": OLD, "new_password": NEW, "confirm_password": NEW,
        })
        assert resp.status_code == 403
        db_session.session.refresh(user)
        assert user.Needs_Setup is True

    def test_later_created_administrator_has_no_setup(self, client, db_session, admin_role):
        user = _make_user(db_session, admin_role, "second@company.com", password=OLD)
        assert _login(client, user).get_json()["data"]["needs_setup"] is False
        assert client.get("/api/user/roles").status_code == 200
        assert _setup(client).status_code == 400

    def test_setup_requires_login(self, client):
        assert _setup(client).status_code == 401


class TestCompleteSetup:
    def test_success_saves_both_clears_flags_logs_and_updates_nagios(
        self, client, db_session, admin_role, nagios
    ):
        user = _bootstrap_admin(db_session, admin_role)
        _login(client, user)
        resp = _setup(client, new_email="ops@Company.com")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["config_ok"] is True and data["config_applied"] is True
        db_session.session.refresh(user)
        assert user.Email == "ops@company.com"
        assert user.check_password(NEW)
        assert user.Needs_Setup is False and user.Must_Change_Password is False
        assert len(nagios) == 1
        assert client.get("/api/user/roles").status_code == 200
        logs = db_session.session.scalars(db_session.select(ActivityLog)).all()
        assert any("first-run setup" in (log.Action_Type or "") for log in logs)

    def test_wrong_current_password(self, client, db_session, admin_role, nagios):
        user = _bootstrap_admin(db_session, admin_role)
        _login(client, user)
        assert _setup(client, current_password="WrongPass1!abc").status_code == 400
        db_session.session.refresh(user)
        assert user.Needs_Setup is True and user.Email.endswith("@pinpoint.lan")
        assert nagios == []

    def test_duplicate_email(self, client, db_session, admin_role):
        _make_user(db_session, admin_role, "taken@company.com")
        _login(client, _bootstrap_admin(db_session, admin_role))
        assert _setup(client, new_email="taken@company.com").status_code == 409

    @pytest.mark.parametrize("email", [
        "x@pinpoint.lan", "x@mail.pinpoint.lan", "x@corp.lan", "x@host.local",
        "x@site.test", "x@site.example", "x@site.invalid", "x@box.localhost",
        "x@corp.internal", "x@home.arpa", "x@sub.home.arpa",
    ])
    def test_placeholder_and_reserved_domains(self, client, db_session, admin_role, email):
        user = _bootstrap_admin(db_session, admin_role)
        _login(client, user)
        assert _setup(client, new_email=email).status_code == 400
        db_session.session.refresh(user)
        assert user.Needs_Setup is True

    def test_invalid_email(self, client, db_session, admin_role):
        _login(client, _bootstrap_admin(db_session, admin_role))
        assert _setup(client, new_email="not-an-email").status_code == 400

    def test_password_policy_and_confirmation(self, client, db_session, admin_role):
        _login(client, _bootstrap_admin(db_session, admin_role))
        assert _setup(client, new_password="weak", confirm_password="weak").status_code == 400
        assert _setup(client, confirm_password="different").status_code == 400

    def test_new_password_must_differ(self, client, db_session, admin_role):
        _login(client, _bootstrap_admin(db_session, admin_role))
        assert _setup(client, new_password=OLD, confirm_password=OLD).status_code == 400

    def test_failed_nagios_apply_keeps_account_change_and_reports(
        self, client, db_session, admin_role, monkeypatch
    ):
        monkeypatch.setattr(
            "app.api.user.management.regenerate_and_apply_config_status",
            lambda: ("failed", "Config failed to validate"),
        )
        user = _bootstrap_admin(db_session, admin_role)
        _login(client, user)
        resp = _setup(client)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["config_ok"] is False
        db_session.session.refresh(user)
        assert user.Email == "ops@company.com" and user.Needs_Setup is False

    def test_nagios_exception_keeps_account_change_and_reports(
        self, client, db_session, admin_role, monkeypatch
    ):
        def boom():
            raise RuntimeError("nagios down")

        monkeypatch.setattr("app.api.user.management.regenerate_and_apply_config_status", boom)
        user = _bootstrap_admin(db_session, admin_role)
        _login(client, user)
        resp = _setup(client)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["config_ok"] is False
        db_session.session.refresh(user)
        assert user.Needs_Setup is False


class TestRequirePasswordChange:
    def _create(self, client, role, **extra):
        body = {
            "first_name": "New", "last_name": "Person", "email": "newperson@example.com",
            "password": NEW, "confirm_password": NEW, "status": "Active", "role_id": role.RoleID,
        }
        body.update(extra)
        return client.post("/api/user/accounts", json=body)

    def _created(self, db_session):
        return db_session.session.scalar(
            db_session.select(User).where(User.Email == "newperson@example.com")
        )

    def test_default_forces_change(self, logged_in_client, db_session, admin_role):
        assert self._create(logged_in_client, admin_role).status_code == 201
        assert self._created(db_session).Must_Change_Password is True

    def test_ticked_forces_change(self, logged_in_client, db_session, admin_role):
        assert self._create(logged_in_client, admin_role, require_password_change=True).status_code == 201
        assert self._created(db_session).Must_Change_Password is True

    def test_unticked_does_not_force_change(self, logged_in_client, db_session, admin_role):
        assert self._create(logged_in_client, admin_role, require_password_change=False).status_code == 201
        assert self._created(db_session).Must_Change_Password is False

    def test_non_boolean_rejected(self, logged_in_client, admin_role):
        assert self._create(logged_in_client, admin_role, require_password_change="no").status_code == 400

    def test_admin_reset_forces_change_even_if_created_unforced(
        self, logged_in_client, db_session, admin_role
    ):
        target = _make_user(db_session, admin_role, "unforced@example.com")
        assert target.Must_Change_Password is False
        resp = logged_in_client.put(f"/api/user/accounts/{target.UserID}", json={
            "first_name": "T", "last_name": "U", "email": target.Email,
            "role_id": target.RoleID, "status": "Active",
            "password": NEW, "confirm_password": NEW,
        })
        assert resp.status_code == 200
        db_session.session.refresh(target)
        assert target.Must_Change_Password is True
