"""
tests/test_management.py — Tests for user management and role management endpoints.

Endpoints tested:
  GET  /api/user/permissions/options
  GET  /api/user/roles
  GET  /api/user/roles/options
  GET  /api/user/roles/<id>
  POST /api/user/roles
  PUT  /api/user/roles/<id>
  PUT  /api/user/roles/<id>/status
  GET  /api/user/accounts
  GET  /api/user/accounts/<id>
  POST /api/user/accounts
  PUT  /api/user/accounts/<id>
  GET  /api/user/me
"""
import pytest
from app.system_models import Role, RolePermission, User, UserStatus, Permission


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_role(db_session, name, is_active=True):
    """Create and persist a bare role (no permissions)."""
    role = Role(Name=name, Is_Active=is_active, Description=f"Role: {name}")
    db_session.session.add(role)
    db_session.session.commit()
    return role


def _make_user(db_session, role, email, first_name="Test", last_name="User",
               status=UserStatus.ACTIVE, password="TestPass1!abc"):
    """Create and persist a user with the given role."""
    user = User(
        First_Name=first_name,
        Last_Name=last_name,
        Email=email,
        Status=status,
        RoleID=role.RoleID,
    )
    user.set_password(password)
    db_session.session.add(user)
    db_session.session.commit()
    return user


# ─── Permissions Options ──────────────────────────────────────────────────────

class TestPermissionsOptions:
    def test_permissions_options_requires_login(self, client, db_session):
        resp = client.get("/api/user/permissions/options")
        assert resp.status_code in (401, 302)

    def test_permissions_options_returns_list(self, logged_in_client, db_session, seeded_permissions):
        resp = logged_in_client.get("/api/user/permissions/options")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "items" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) > 0
        for item in data["items"]:
            assert "id" in item
            assert "name" in item

    def test_permissions_options_requires_role_edit_permission(self, limited_client, db_session, seeded_permissions):
        resp = limited_client.get("/api/user/permissions/options")
        assert resp.status_code == 403


# ─── Roles List ──────────────────────────────────────────────────────────────

class TestRolesList:
    def test_roles_list_requires_login(self, client, db_session):
        resp = client.get("/api/user/roles")
        assert resp.status_code in (401, 302)

    def test_roles_list_returns_empty(self, logged_in_client, db_session, admin_role):
        # Only the admin_role exists; the list should still return it
        resp = logged_in_client.get("/api/user/roles")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "items" in data
        assert "total" in data

    def test_roles_list_returns_roles(self, logged_in_client, db_session, admin_role):
        extra = _make_role(db_session, "SupportRole")
        resp = logged_in_client.get("/api/user/roles")
        assert resp.status_code == 200
        data = resp.get_json()
        names = [item["name"] for item in data["items"]]
        assert "SupportRole" in names

    def test_roles_list_pagination(self, logged_in_client, db_session, admin_role):
        # Seed 12 extra roles so we have enough to paginate
        for i in range(12):
            _make_role(db_session, f"PaginationRole{i:02d}")

        resp = logged_in_client.get("/api/user/roles?page=2&per_page=5")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["page"] == 2
        assert data["per_page"] == 5
        assert len(data["items"]) <= 5

    def test_roles_list_search(self, logged_in_client, db_session, admin_role):
        _make_role(db_session, "NetworkManager")
        _make_role(db_session, "SystemViewer")

        resp = logged_in_client.get("/api/user/roles?search=NetworkMan")
        assert resp.status_code == 200
        data = resp.get_json()
        names = [item["name"] for item in data["items"]]
        assert "NetworkManager" in names
        assert "SystemViewer" not in names

    def test_roles_list_invalid_sort(self, logged_in_client, db_session, admin_role):
        resp = logged_in_client.get("/api/user/roles?sort_by=invalid_field")
        assert resp.status_code == 400

    def test_roles_list_invalid_order(self, logged_in_client, db_session, admin_role):
        resp = logged_in_client.get("/api/user/roles?order=sideways")
        assert resp.status_code == 400

    def test_roles_list_requires_role_view_permission(self, limited_client, db_session, admin_role):
        resp = limited_client.get("/api/user/roles")
        assert resp.status_code == 403


# ─── Roles Options ────────────────────────────────────────────────────────────

class TestRolesOptions:
    def test_roles_options_returns_active_only(self, logged_in_client, db_session, admin_role):
        _make_role(db_session, "InactiveRole", is_active=False)
        _make_role(db_session, "ActiveRole", is_active=True)

        resp = logged_in_client.get("/api/user/roles/options")
        assert resp.status_code == 200
        data = resp.get_json()
        names = [item["name"] for item in data["items"]]
        assert "InactiveRole" not in names
        assert "ActiveRole" in names

    def test_roles_options_requires_role_list_permission(self, limited_client, db_session, admin_role):
        resp = limited_client.get("/api/user/roles/options")
        assert resp.status_code == 403


# ─── Role Info ────────────────────────────────────────────────────────────────

class TestRoleInfo:
    def test_role_info_not_found(self, logged_in_client, db_session, admin_role):
        resp = logged_in_client.get("/api/user/roles/99999")
        assert resp.status_code == 404

    def test_role_info_returns_data(self, logged_in_client, db_session, admin_role, seeded_permissions):
        resp = logged_in_client.get(f"/api/user/roles/{admin_role.RoleID}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == admin_role.RoleID
        assert data["name"] == admin_role.Name
        assert "description" in data
        assert "is_active" in data
        assert isinstance(data["permissions"], list)

    def test_role_info_requires_role_info_permission(self, limited_client, db_session, admin_role):
        resp = limited_client.get(f"/api/user/roles/{admin_role.RoleID}")
        assert resp.status_code == 403


# ─── Create Role ──────────────────────────────────────────────────────────────

class TestCreateRole:
    def test_create_role_success(self, logged_in_client, db_session, seeded_permissions):
        perm_id = list(seeded_permissions.values())[0].PermissionID
        resp = logged_in_client.post(
            "/api/user/roles",
            json={
                "role_name": "NewRole",
                "description": "A new test role",
                "permissions": [perm_id],
            },
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert "message" in data

    def test_create_role_duplicate_name(self, logged_in_client, db_session, seeded_permissions, admin_role):
        perm_id = list(seeded_permissions.values())[0].PermissionID
        resp = logged_in_client.post(
            "/api/user/roles",
            json={
                "role_name": admin_role.Name,  # already exists
                "description": "Duplicate",
                "permissions": [perm_id],
            },
        )
        assert resp.status_code == 409

    def test_create_role_missing_fields(self, logged_in_client, db_session, seeded_permissions):
        # Missing 'permissions' field
        resp = logged_in_client.post(
            "/api/user/roles",
            json={"role_name": "MissingPerms", "description": "desc"},
        )
        assert resp.status_code == 400

    def test_create_role_invalid_permission_id(self, logged_in_client, db_session, seeded_permissions):
        resp = logged_in_client.post(
            "/api/user/roles",
            json={
                "role_name": "BadPermRole",
                "description": "desc",
                "permissions": [999999],
            },
        )
        assert resp.status_code == 404

    def test_create_role_requires_login(self, client, db_session, seeded_permissions):
        perm_id = list(seeded_permissions.values())[0].PermissionID
        resp = client.post(
            "/api/user/roles",
            json={
                "role_name": "UnauthRole",
                "description": "desc",
                "permissions": [perm_id],
            },
        )
        assert resp.status_code in (401, 302)

    def test_create_role_requires_role_edit_permission(self, limited_client, db_session, seeded_permissions):
        perm_id = list(seeded_permissions.values())[0].PermissionID
        resp = limited_client.post(
            "/api/user/roles",
            json={
                "role_name": "UnauthorizedRole",
                "description": "desc",
                "permissions": [perm_id],
            },
        )
        assert resp.status_code == 403


# ─── Edit Role ────────────────────────────────────────────────────────────────

class TestEditRole:
    def test_edit_role_success(self, logged_in_client, db_session, seeded_permissions):
        role = _make_role(db_session, "EditableRole")
        perm_id = list(seeded_permissions.values())[0].PermissionID
        resp = logged_in_client.put(
            f"/api/user/roles/{role.RoleID}",
            json={
                "name": "EditableRoleUpdated",
                "description": "Updated description",
                "permissions": [perm_id],
            },
        )
        assert resp.status_code == 200

    def test_edit_role_not_found(self, logged_in_client, db_session, seeded_permissions):
        perm_id = list(seeded_permissions.values())[0].PermissionID
        resp = logged_in_client.put(
            "/api/user/roles/99999",
            json={
                "name": "DoesNotExist",
                "description": "desc",
                "permissions": [perm_id],
            },
        )
        assert resp.status_code == 404

    def test_edit_role_duplicate_name(self, logged_in_client, db_session, seeded_permissions):
        role_a = _make_role(db_session, "RoleAlpha")
        role_b = _make_role(db_session, "RoleBeta")
        perm_id = list(seeded_permissions.values())[0].PermissionID
        # Rename role_b to role_a's name — should conflict
        resp = logged_in_client.put(
            f"/api/user/roles/{role_b.RoleID}",
            json={
                "name": role_a.Name,
                "description": "desc",
                "permissions": [perm_id],
            },
        )
        assert resp.status_code == 409

    def test_edit_role_same_name_ok(self, logged_in_client, db_session, seeded_permissions):
        role = _make_role(db_session, "SameNameRole")
        perm_id = list(seeded_permissions.values())[0].PermissionID
        # Updating with the same name should not trigger a 409
        resp = logged_in_client.put(
            f"/api/user/roles/{role.RoleID}",
            json={
                "name": role.Name,
                "description": "Updated description",
                "permissions": [perm_id],
            },
        )
        assert resp.status_code == 200


# ─── Role Status Toggle ───────────────────────────────────────────────────────

class TestRoleStatusToggle:
    def test_role_status_toggle(self, logged_in_client, db_session):
        role = _make_role(db_session, "ToggleRole", is_active=True)
        resp = logged_in_client.put(f"/api/user/roles/{role.RoleID}/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["previous_status"] is True
        assert data["current_status"] is False

    def test_role_status_not_found(self, logged_in_client, db_session, admin_role):
        resp = logged_in_client.put("/api/user/roles/99999/status")
        assert resp.status_code == 404


# ─── Accounts List ────────────────────────────────────────────────────────────

class TestAccountsList:
    def test_accounts_list_requires_login(self, client, db_session):
        resp = client.get("/api/user/accounts")
        assert resp.status_code in (401, 302)

    def test_accounts_list_returns_users(self, logged_in_client, db_session, admin_user, admin_role):
        extra = _make_user(db_session, admin_role, "extra@example.com", first_name="Extra")
        resp = logged_in_client.get("/api/user/accounts")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "items" in data
        emails = [u["email"] for u in data["items"]]
        assert "extra@example.com" in emails

    def test_accounts_list_search(self, logged_in_client, db_session, admin_user, admin_role):
        _make_user(db_session, admin_role, "uniquefirst@example.com", first_name="Zephyr")
        resp = logged_in_client.get("/api/user/accounts?search=Zephyr")
        assert resp.status_code == 200
        data = resp.get_json()
        names = [u["first_name"] for u in data["items"]]
        assert "Zephyr" in names

    def test_accounts_list_invalid_sort(self, logged_in_client, db_session, admin_user):
        resp = logged_in_client.get("/api/user/accounts?sort_by=nonexistent_field")
        assert resp.status_code == 400

    def test_accounts_list_requires_account_view_permission(self, limited_client, db_session, admin_user):
        resp = limited_client.get("/api/user/accounts")
        assert resp.status_code == 403


# ─── Account Info ─────────────────────────────────────────────────────────────

class TestAccountInfo:
    def test_account_info_not_found(self, logged_in_client, db_session, admin_user):
        resp = logged_in_client.get("/api/user/accounts/99999")
        assert resp.status_code == 404

    def test_account_info_returns_data(self, logged_in_client, db_session, admin_user):
        resp = logged_in_client.get(f"/api/user/accounts/{admin_user.UserID}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == admin_user.UserID
        assert "first_name" in data
        assert "last_name" in data
        assert "email" in data
        assert "role" in data
        assert "status" in data

    def test_account_info_requires_account_info_permission(self, limited_client, db_session, admin_user):
        resp = limited_client.get(f"/api/user/accounts/{admin_user.UserID}")
        assert resp.status_code == 403


# ─── Create Account ───────────────────────────────────────────────────────────

class TestCreateAccount:
    def _payload(self, admin_role, **overrides):
        base = {
            "first_name": "New",
            "last_name": "Account",
            "email": "newaccount@example.com",
            "password": "StrongPass1!abc",
            "confirm_password": "StrongPass1!abc",
            "status": "Active",
            "role_id": admin_role.RoleID,
        }
        base.update(overrides)
        return base

    def test_create_account_success(self, logged_in_client, db_session, admin_role):
        resp = logged_in_client.post(
            "/api/user/accounts",
            json=self._payload(admin_role),
        )
        assert resp.status_code == 201

    def test_create_account_duplicate_email(self, logged_in_client, db_session, admin_user, admin_role):
        resp = logged_in_client.post(
            "/api/user/accounts",
            json=self._payload(admin_role, email=admin_user.Email),
        )
        assert resp.status_code == 409

    def test_create_account_password_mismatch(self, logged_in_client, db_session, admin_role):
        resp = logged_in_client.post(
            "/api/user/accounts",
            json=self._payload(admin_role,
                               email="mismatch@example.com",
                               confirm_password="DifferentPass1!abc"),
        )
        assert resp.status_code == 400

    def test_create_account_weak_password(self, logged_in_client, db_session, admin_role):
        resp = logged_in_client.post(
            "/api/user/accounts",
            json=self._payload(admin_role,
                               email="weak@example.com",
                               password="weak",
                               confirm_password="weak"),
        )
        assert resp.status_code == 400

    def test_create_account_invalid_email(self, logged_in_client, db_session, admin_role):
        resp = logged_in_client.post(
            "/api/user/accounts",
            json=self._payload(admin_role, email="not-an-email"),
        )
        assert resp.status_code == 400

    def test_create_account_invalid_role(self, logged_in_client, db_session, admin_role):
        resp = logged_in_client.post(
            "/api/user/accounts",
            json=self._payload(admin_role,
                               email="badrole@example.com",
                               role_id=99999),
        )
        assert resp.status_code == 404

    def test_create_account_invalid_status(self, logged_in_client, db_session, admin_role):
        resp = logged_in_client.post(
            "/api/user/accounts",
            json=self._payload(admin_role,
                               email="badstatus@example.com",
                               status="Nonexistent"),
        )
        assert resp.status_code == 400

    def test_create_account_requires_account_edit_permission(self, limited_client, db_session, admin_role):
        resp = limited_client.post(
            "/api/user/accounts",
            json={
                "first_name": "Ltd",
                "last_name": "User",
                "email": "ltd@example.com",
                "password": "StrongPass1!abc",
                "confirm_password": "StrongPass1!abc",
                "status": "Active",
                "role_id": admin_role.RoleID,
            },
        )
        assert resp.status_code == 403


# ─── Edit Account ─────────────────────────────────────────────────────────────

class TestEditAccount:
    def _payload(self, admin_role, **overrides):
        base = {
            "first_name": "Updated",
            "last_name": "Name",
            "email": "updated@example.com",
            "password": "UpdatedPass1!abc",
            "confirm_password": "UpdatedPass1!abc",
            "role_id": admin_role.RoleID,
            "status": "Active",
        }
        base.update(overrides)
        return base

    def test_edit_account_success(self, logged_in_client, db_session, admin_user, admin_role):
        resp = logged_in_client.put(
            f"/api/user/accounts/{admin_user.UserID}",
            json=self._payload(admin_role, email=admin_user.Email),
        )
        assert resp.status_code == 200

    def test_edit_account_not_found(self, logged_in_client, db_session, admin_role):
        resp = logged_in_client.put(
            "/api/user/accounts/99999",
            json=self._payload(admin_role),
        )
        assert resp.status_code == 404

    def test_edit_account_email_conflict(self, logged_in_client, db_session, admin_user, admin_role):
        other = _make_user(db_session, admin_role, "other@example.com")
        # Try to change other's email to admin's email
        resp = logged_in_client.put(
            f"/api/user/accounts/{other.UserID}",
            json=self._payload(admin_role, email=admin_user.Email),
        )
        assert resp.status_code == 409

    def test_edit_account_same_email_ok(self, logged_in_client, db_session, admin_user, admin_role):
        # Keeping the same email should not produce a 409
        resp = logged_in_client.put(
            f"/api/user/accounts/{admin_user.UserID}",
            json=self._payload(admin_role, email=admin_user.Email),
        )
        assert resp.status_code == 200


# ─── /me Endpoint ────────────────────────────────────────────────────────────

class TestMeEndpoint:
    def test_me_returns_user_data(self, logged_in_client, db_session, admin_user):
        resp = logged_in_client.get("/api/user/me")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["first_name"] == admin_user.First_Name
        assert data["last_name"] == admin_user.Last_Name
        assert "role" in data
        assert isinstance(data["permissions"], list)

    def test_me_requires_login(self, client, db_session):
        resp = client.get("/api/user/me")
        assert resp.status_code in (401, 302)
