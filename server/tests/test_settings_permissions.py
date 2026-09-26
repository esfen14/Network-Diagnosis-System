"""
Tests for per-tab settings permissions (PUT /api/system) and for
/api/user/me hiding permissions when the user's role is inactive.

General settings are open to every logged-in user. Security fields need
"settings.security" and System fields need "settings.system".
limited_client's role has neither; logged_in_client's role has all.
"""
import pytest

from app.system_models import Permission, RolePermission, SystemSettings


def current_settings(client):
    resp = client.get("/api/system")
    assert resp.status_code == 200
    return resp.get_json()["data"]


def save(client, **changes):
    payload = current_settings(client)
    payload.update(changes)
    return client.put("/api/system", json=payload)


def stored(db_session):
    db_session.session.expire_all()
    return db_session.session.get(SystemSettings, 1)


def grant(db_session, role, permission_name):
    permission = db_session.session.query(Permission).filter_by(Name=permission_name).one()
    db_session.session.add(RolePermission(RoleID=role.RoleID, PermissionID=permission.PermissionID))
    db_session.session.commit()


class TestSettingsPermissions:
    def test_any_user_can_change_general_settings(self, limited_client, db_session):
        resp = save(limited_client, scanFrequency=12, notifications=False)

        assert resp.status_code == 200
        assert stored(db_session).Scan_Frequency == 12
        assert stored(db_session).Notifications is False

    @pytest.mark.parametrize("field, value, tab", [
        ("sessionTimeout", 60, "Security"),
        ("auditLogging", False, "Security"),
        ("maintenanceMode", True, "System"),
        ("logRetentionDays", 7, "System"),
    ])
    def test_restricted_field_needs_permission(self, limited_client, db_session, field, value, tab):
        before = current_settings(limited_client)

        resp = save(limited_client, **{field: value})

        assert resp.status_code == 403
        assert f"{tab} settings" in resp.get_json()["message"]
        assert current_settings(limited_client)[field] == before[field]
        assert current_settings(limited_client)["version"] == before["version"]

    def test_denied_save_changes_nothing_else(self, limited_client, db_session):
        resp = save(limited_client, scanFrequency=12, sessionTimeout=60)

        assert resp.status_code == 403
        assert stored(db_session).Scan_Frequency != 12

    def test_names_both_tabs_when_both_denied(self, limited_client, db_session):
        resp = save(limited_client, sessionTimeout=60, maintenanceMode=True)

        assert resp.status_code == 403
        assert "Security and System settings" in resp.get_json()["message"]

    def test_security_permission_allows_security_only(self, limited_client, db_session, regular_role):
        grant(db_session, regular_role, "settings.security")

        allowed = save(limited_client, sessionTimeout=60)
        denied = save(limited_client, maintenanceMode=True)

        assert allowed.status_code == 200
        assert stored(db_session).Session_Timeout == 60
        assert denied.status_code == 403

    def test_system_permission_allows_system_only(self, limited_client, db_session, regular_role):
        grant(db_session, regular_role, "settings.system")

        allowed = save(limited_client, maintenanceMode=True)
        denied = save(limited_client, sessionTimeout=60)

        assert allowed.status_code == 200
        assert stored(db_session).Maintenance_Mode is True
        assert denied.status_code == 403

    def test_admin_can_change_everything(self, logged_in_client, db_session):
        resp = save(logged_in_client, scanFrequency=3, sessionTimeout=60, maintenanceMode=True)

        assert resp.status_code == 200
        settings = stored(db_session)
        assert (settings.Scan_Frequency, settings.Session_Timeout, settings.Maintenance_Mode) == (3, 60, True)

    def test_inactive_role_loses_restricted_tabs(self, logged_in_client, db_session, admin_role):
        admin_role.Is_Active = False
        db_session.session.commit()

        resp = save(logged_in_client, sessionTimeout=60)

        assert resp.status_code == 403


class TestMePermissions:
    def test_me_lists_role_permissions(self, logged_in_client, db_session):
        permissions = logged_in_client.get("/api/user/me").get_json()["data"]["permissions"]

        assert "settings.security" in permissions
        assert "settings.system" in permissions

    def test_me_has_no_permissions_when_role_inactive(self, logged_in_client, db_session, admin_role):
        admin_role.Is_Active = False
        db_session.session.commit()

        data = logged_in_client.get("/api/user/me").get_json()["data"]

        assert data["permissions"] == []
        assert data["role"] == admin_role.Name
