"""
tests/unit/test_email_alerts.py — The per-user "Receive email alerts" setting.

Covers the account routes (POST/PUT /api/user/accounts, GET account info/list):
the field, the account.alerts permission, and the Nagios config rebuild an
account change triggers. The Nagios writer is always faked.
"""
import pytest
import sqlalchemy as sa

from app import db
from app.system_models import Permission, Role, RolePermission, User, UserStatus
from tests.unit.test_management import _make_role, _make_user


@pytest.fixture
def writer(monkeypatch):
    """Fake the shared writer; `result` is what it returns, `calls` counts rebuilds."""
    state = {"calls": 0, "result": ("applied", "Applied.")}

    def fake():
        state["calls"] += 1
        return state["result"]

    monkeypatch.setattr("app.api.user.management.regenerate_and_apply_config_status", fake)
    return state


def _payload(role, **overrides):
    body = {
        "first_name": "New",
        "last_name": "Account",
        "email": "newaccount@example.com",
        "password": "StrongPass1!abc",
        "confirm_password": "StrongPass1!abc",
        "status": "Active",
        "role_id": role.RoleID,
    }
    body.update(overrides)
    return body


def _edit_body(user, role, **overrides):
    body = {
        "first_name": user.First_Name,
        "last_name": user.Last_Name,
        "email": user.Email,
        "role_id": role.RoleID,
        "status": user.Status.value,
    }
    body.update(overrides)
    return body


def _client_without_alerts_permission(client, db_session, seeded_permissions):
    """Logged in as a user who may edit accounts but not email alerts."""
    role = _make_role(db_session, "AccountEditor")
    for name in ("account.edit", "account.view", "account.info"):
        db_session.session.add(
            RolePermission(RoleID=role.RoleID, PermissionID=seeded_permissions[name].PermissionID)
        )
    db_session.session.commit()
    _make_user(db_session, role, "editor@example.com", password="EditorPass1!abc")
    resp = client.post(
        "/api/user/login", json={"email": "editor@example.com", "password": "EditorPass1!abc"}
    )
    assert resp.status_code == 200
    return client, role


class TestCreate:
    def test_defaults_to_on(self, logged_in_client, db_session, admin_role, writer):
        resp = logged_in_client.post("/api/user/accounts", json=_payload(admin_role))
        assert resp.status_code == 201
        user = db_session.session.scalar(sa.select(User).where(User.Email == "newaccount@example.com"))
        assert user.Receive_Email_Alerts is True

    def test_active_alert_user_rebuilds_config(self, logged_in_client, db_session, admin_role, writer):
        resp = logged_in_client.post("/api/user/accounts", json=_payload(admin_role))
        assert writer["calls"] == 1
        assert resp.get_json()["data"]["config_ok"] is True

    def test_user_who_is_not_a_contact_does_not_rebuild(self, logged_in_client, db_session, admin_role, writer):
        logged_in_client.post(
            "/api/user/accounts", json=_payload(admin_role, receive_email_alerts=False)
        )
        logged_in_client.post(
            "/api/user/accounts",
            json=_payload(admin_role, email="inactive@example.com", status="Inactive"),
        )
        assert writer["calls"] == 0

    def test_can_create_opted_out(self, logged_in_client, db_session, admin_role, writer):
        logged_in_client.post("/api/user/accounts", json=_payload(admin_role, receive_email_alerts=False))
        user = db_session.session.scalar(sa.select(User).where(User.Email == "newaccount@example.com"))
        assert user.Receive_Email_Alerts is False

    def test_rejects_non_boolean(self, logged_in_client, db_session, admin_role, writer):
        resp = logged_in_client.post(
            "/api/user/accounts", json=_payload(admin_role, receive_email_alerts="no")
        )
        assert resp.status_code == 400

    def test_opting_out_needs_the_permission(self, client, db_session, seeded_permissions, writer):
        client, role = _client_without_alerts_permission(client, db_session, seeded_permissions)
        resp = client.post("/api/user/accounts", json=_payload(role, receive_email_alerts=False))
        assert resp.status_code == 403
        assert db_session.session.scalar(sa.select(User).where(User.Email == "newaccount@example.com")) is None

    def test_default_needs_no_permission(self, client, db_session, seeded_permissions, writer):
        client, role = _client_without_alerts_permission(client, db_session, seeded_permissions)
        resp = client.post("/api/user/accounts", json=_payload(role))
        assert resp.status_code == 201


class TestEdit:
    def test_turning_off_removes_contact_and_rebuilds(self, logged_in_client, db_session, admin_role, writer):
        user = _make_user(db_session, admin_role, "member@example.com")
        resp = logged_in_client.put(
            f"/api/user/accounts/{user.UserID}",
            json=_edit_body(user, admin_role, receive_email_alerts=False),
        )
        assert resp.status_code == 200
        db_session.session.refresh(user)
        assert user.Receive_Email_Alerts is False
        assert writer["calls"] == 1

    def test_turning_on_rebuilds(self, logged_in_client, db_session, admin_role, writer):
        user = _make_user(db_session, admin_role, "member@example.com")
        user.Receive_Email_Alerts = False
        db_session.session.commit()
        logged_in_client.put(
            f"/api/user/accounts/{user.UserID}",
            json=_edit_body(user, admin_role, receive_email_alerts=True),
        )
        assert writer["calls"] == 1

    def test_deactivating_an_alert_user_rebuilds(self, logged_in_client, db_session, admin_role, writer):
        user = _make_user(db_session, admin_role, "member@example.com")
        logged_in_client.put(
            f"/api/user/accounts/{user.UserID}", json=_edit_body(user, admin_role, status="Inactive")
        )
        assert writer["calls"] == 1

    def test_reactivating_rebuilds(self, logged_in_client, db_session, admin_role, writer):
        user = _make_user(db_session, admin_role, "member@example.com", status=UserStatus.INACTIVE)
        logged_in_client.put(
            f"/api/user/accounts/{user.UserID}", json=_edit_body(user, admin_role, status="Active")
        )
        assert writer["calls"] == 1

    def test_email_change_of_an_alert_user_rebuilds(self, logged_in_client, db_session, admin_role, writer):
        user = _make_user(db_session, admin_role, "member@example.com")
        logged_in_client.put(
            f"/api/user/accounts/{user.UserID}",
            json=_edit_body(user, admin_role, email="renamed@example.com"),
        )
        assert writer["calls"] == 1

    def test_change_that_does_not_touch_contacts_does_not_rebuild(
        self, logged_in_client, db_session, admin_role, writer
    ):
        opted_out = _make_user(db_session, admin_role, "out@example.com")
        opted_out.Receive_Email_Alerts = False
        inactive = _make_user(db_session, admin_role, "idle@example.com", status=UserStatus.INACTIVE)
        db_session.session.commit()
        other_role = _make_role(db_session, "Other")

        logged_in_client.put(
            f"/api/user/accounts/{opted_out.UserID}",
            json=_edit_body(opted_out, other_role, email="out2@example.com"),
        )
        logged_in_client.put(
            f"/api/user/accounts/{inactive.UserID}",
            json=_edit_body(inactive, other_role, email="idle2@example.com"),
        )
        assert writer["calls"] == 0

    def test_failed_apply_is_reported_and_keeps_the_change(self, logged_in_client, db_session, admin_role, writer):
        writer["result"] = ("failed", "nagios -v failed")
        user = _make_user(db_session, admin_role, "member@example.com")
        resp = logged_in_client.put(
            f"/api/user/accounts/{user.UserID}",
            json=_edit_body(user, admin_role, receive_email_alerts=False),
        )
        data = resp.get_json()["data"]
        assert resp.status_code == 200
        assert data["config_ok"] is False
        assert data["config_message"] == "nagios -v failed"
        db_session.session.refresh(user)
        assert user.Receive_Email_Alerts is False

    def test_writer_exception_is_reported_and_keeps_the_change(
        self, logged_in_client, db_session, admin_role, monkeypatch
    ):
        def boom():
            raise RuntimeError("no nagios")

        monkeypatch.setattr("app.api.user.management.regenerate_and_apply_config_status", boom)
        user = _make_user(db_session, admin_role, "member@example.com")
        resp = logged_in_client.put(
            f"/api/user/accounts/{user.UserID}",
            json=_edit_body(user, admin_role, receive_email_alerts=False),
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["config_ok"] is False
        db_session.session.refresh(user)
        assert user.Receive_Email_Alerts is False

    def test_changing_it_needs_the_permission(self, client, db_session, seeded_permissions, writer):
        client, role = _client_without_alerts_permission(client, db_session, seeded_permissions)
        user = _make_user(db_session, role, "member@example.com")
        resp = client.put(
            f"/api/user/accounts/{user.UserID}",
            json=_edit_body(user, role, receive_email_alerts=False),
        )
        assert resp.status_code == 403
        db_session.session.refresh(user)
        assert user.Receive_Email_Alerts is True
        assert writer["calls"] == 0

    def test_resending_the_current_value_needs_no_permission(
        self, client, db_session, seeded_permissions, writer
    ):
        client, role = _client_without_alerts_permission(client, db_session, seeded_permissions)
        user = _make_user(db_session, role, "member@example.com")
        resp = client.put(
            f"/api/user/accounts/{user.UserID}",
            json=_edit_body(user, role, receive_email_alerts=True),
        )
        assert resp.status_code == 200

    def test_rejects_non_boolean(self, logged_in_client, db_session, admin_role, writer):
        user = _make_user(db_session, admin_role, "member@example.com")
        resp = logged_in_client.put(
            f"/api/user/accounts/{user.UserID}",
            json=_edit_body(user, admin_role, receive_email_alerts="off"),
        )
        assert resp.status_code == 400


class TestRead:
    def test_info_and_list_report_the_setting(self, logged_in_client, db_session, admin_user, admin_role):
        user = _make_user(db_session, admin_role, "member@example.com")
        user.Receive_Email_Alerts = False
        db_session.session.commit()

        info = logged_in_client.get(f"/api/user/accounts/{user.UserID}").get_json()["data"]
        assert info["receive_email_alerts"] is False

        items = logged_in_client.get("/api/user/accounts").get_json()["data"]["items"]
        by_email = {item["email"]: item for item in items}
        assert by_email["member@example.com"]["receive_email_alerts"] is False
        assert by_email[admin_user.Email]["receive_email_alerts"] is True


class TestPermissionAndColumn:
    def test_permission_is_seeded_for_new_installs(self):
        from app.api.commands.seed import PERMISSIONS

        assert "account.alerts" in PERMISSIONS

    def test_column_defaults_on_for_a_user_created_without_it(self, db_session, admin_role):
        user = User(
            First_Name="A", Last_Name="B", Email="plain@example.com",
            Status=UserStatus.ACTIVE, RoleID=admin_role.RoleID,
        )
        user.set_password("TestPass1!abc")
        db_session.session.add(user)
        db_session.session.commit()
        assert user.Receive_Email_Alerts is True


class TestAuditEntry:
    """Changing the setting is written to the activity log (when audit logging is on)."""

    def _actions(self, db_session):
        from app.system_models import ActivityLog

        return [row.Action_Type for row in db_session.session.scalars(sa.select(ActivityLog))]

    def test_edit_logs_the_new_setting(self, logged_in_client, db_session, admin_role, writer):
        user = _make_user(db_session, admin_role, "member@example.com")
        logged_in_client.put(
            f"/api/user/accounts/{user.UserID}",
            json=_edit_body(user, admin_role, receive_email_alerts=False),
        )
        assert any("email alerts off" in action for action in self._actions(db_session))

        logged_in_client.put(
            f"/api/user/accounts/{user.UserID}",
            json=_edit_body(user, admin_role, receive_email_alerts=True),
        )
        assert any("email alerts on" in action for action in self._actions(db_session))

    def test_edit_that_leaves_it_alone_logs_no_alert_text(self, logged_in_client, db_session, admin_role, writer):
        user = _make_user(db_session, admin_role, "member@example.com")
        logged_in_client.put(
            f"/api/user/accounts/{user.UserID}",
            json=_edit_body(user, admin_role, receive_email_alerts=True),
        )
        assert not any("email alerts" in action for action in self._actions(db_session))


@pytest.fixture(scope="module")
def migration_report():
    import json
    import subprocess
    import sys
    from pathlib import Path

    server_dir = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "tests/support/email_alert_migration_runner.py"],
        cwd=server_dir, capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, (result.stdout + result.stderr)[-3000:]
    body = result.stdout.split("REPORT_BEGIN")[1].split("REPORT_END")[0]
    return json.loads(body)


class TestMigration:
    def test_existing_users_stay_on(self, migration_report):
        assert migration_report["column_before"] is False
        assert migration_report["version"] == [["a4c8e1f6d392"]]
        assert migration_report["alerts_after_upgrade"] == [
            ["active@example.com", 1],
            ["inactive@example.com", 1],
        ]

    def test_a_row_inserted_without_the_column_defaults_to_on(self, migration_report):
        assert migration_report["alerts_with_new_user"][-1] == ["later@example.com", 1]

    def test_downgrade_drops_only_the_column(self, migration_report):
        assert migration_report["column_after_downgrade"] is False
        assert migration_report["users_after_downgrade"] == [
            ["active@example.com"],
            ["inactive@example.com"],
            ["later@example.com"],
        ]
        assert migration_report["version_after_downgrade"] == [["b6e1d4a8c2f9"]]

    def test_reupgrade_keeps_everyone_on(self, migration_report):
        assert [row[1] for row in migration_report["alerts_after_reupgrade"]] == [1, 1, 1]
