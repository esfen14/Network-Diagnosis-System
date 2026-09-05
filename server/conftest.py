"""
conftest.py — pytest fixtures for the Flask app test suite.

The app is a module-level singleton (not a factory).  Flask-SQLAlchemy 3.x
binds engines at first access, not at import time, so we can override the
DATABASE_URL *before* any request/engine is used by setting environment
variables and updating app.config before any engine is touched.

We inject sqlite:///:memory: via environment variables so the Config class
picks them up before the engine is ever created.
"""
import sys
import os

# ── Inject test DB config BEFORE app is imported so Config picks them up ──────
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["HISTORY_DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key"

# Ensure the server/ directory is on sys.path so "from app import ..." works
sys.path.insert(0, os.path.dirname(__file__))

import pytest

# ── Patch Config BEFORE flask app is instantiated ────────────────────────────
# Config reads DATABASE_URL from env — but SQLALCHEMY_BINDS doesn't have an
# env var check. We monkey-patch the class before import.
import config as _cfg_module

_cfg_module.Config.SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
_cfg_module.Config.SQLALCHEMY_BINDS = {"history": "sqlite:///:memory:"}
_cfg_module.Config.TESTING = True
_cfg_module.Config.SECRET_KEY = "test-secret-key"
_cfg_module.Config.WTF_CSRF_ENABLED = False

from app import app as flask_app, db as _db
from app.system_models import (
    User, Role, Permission, RolePermission, UserStatus
)


# ─── App & client fixtures ────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def app():
    """Return the configured singleton Flask app."""
    # Belt-and-suspenders: also set on app.config in case anything reads it later
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_BINDS={"history": "sqlite:///:memory:"},
    )
    yield flask_app


@pytest.fixture()
def client(app):
    """A test client for the app."""
    return app.test_client()


# ─── Database fixtures ────────────────────────────────────────────────────────

@pytest.fixture()
def db_session(app):
    """
    Create all tables in the in-memory database, yield db, then drop all tables.
    Function-scoped so each test gets a clean database state.
    """
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.remove()
        _db.drop_all()


# ─── Seed / helper fixtures ───────────────────────────────────────────────────

PERMISSION_NAMES = [
    "system.inventory",
    "system.discover",
    "network.discovery",
    "role.edit",
    "role.view",
    "role.list",
    "role.info",
    "account.edit",
    "account.view",
    "account.info",
    "system.deploy.ncpa",
    # monitoring permissions
    "monitoring.alerts",
    "monitoring.notifications",
    "monitoring.dashboard",
    "monitoring.network_health",
    "system.notifications",
    "system.report",
    # dashboard / network health / ack permissions
    "system.dashboard",
    "system.network_health",
    "system.acknowledge_alerts",
    "system.history",
    "plugin.scan",
    "plugin.view",
    ]


@pytest.fixture()
def seeded_permissions(db_session):
    """Insert all four known permissions and return a name→obj dict."""
    perms = {}
    for name in PERMISSION_NAMES:
        p = Permission(Name=name, Description=f"Permission: {name}")
        db_session.session.add(p)
        perms[name] = p
    db_session.session.commit()
    return perms


@pytest.fixture()
def admin_role(db_session, seeded_permissions):
    """An active role that has ALL permissions."""
    role = Role(Name="Admin", Is_Active=True, Description="Administrator")
    db_session.session.add(role)
    db_session.session.flush()  # get role.RoleID

    for perm in seeded_permissions.values():
        rp = RolePermission(RoleID=role.RoleID, PermissionID=perm.PermissionID)
        db_session.session.add(rp)

    db_session.session.commit()
    return role


@pytest.fixture()
def regular_role(db_session, seeded_permissions):
    """An active role that only has 'system.inventory' permission."""
    role = Role(Name="Viewer", Is_Active=True, Description="Read-only viewer")
    db_session.session.add(role)
    db_session.session.flush()

    inv_perm = seeded_permissions["system.inventory"]
    rp = RolePermission(RoleID=role.RoleID, PermissionID=inv_perm.PermissionID)
    db_session.session.add(rp)

    db_session.session.commit()
    return role


@pytest.fixture()
def admin_user(db_session, admin_role):
    """An active user with the Admin role."""
    user = User(
        First_Name="Admin",
        Last_Name="User",
        Email="admin@example.com",
        Status=UserStatus.ACTIVE,
        RoleID=admin_role.RoleID,
    )
    user.set_password("AdminPass1!")
    db_session.session.add(user)
    db_session.session.commit()
    return user


@pytest.fixture()
def regular_user(db_session, regular_role):
    """An active user with the Viewer (limited) role."""
    user = User(
        First_Name="Regular",
        Last_Name="User",
        Email="regular@example.com",
        Status=UserStatus.ACTIVE,
        RoleID=regular_role.RoleID,
    )
    user.set_password("RegularPass1!")
    db_session.session.add(user)
    db_session.session.commit()
    return user


@pytest.fixture()
def inactive_user(db_session, admin_role):
    """An inactive user — should receive 403 on login."""
    user = User(
        First_Name="Inactive",
        Last_Name="User",
        Email="inactive@example.com",
        Status=UserStatus.INACTIVE,
        RoleID=admin_role.RoleID,
    )
    user.set_password("InactivePass1!")
    db_session.session.add(user)
    db_session.session.commit()
    return user


@pytest.fixture()
def logged_in_client(client, db_session, admin_user):
    """
    A test client that is already logged in as admin_user.
    The db_session fixture ensures the user exists for the duration of the test.
    """
    resp = client.post(
        "/api/user/login",
        json={"email": "admin@example.com", "password": "AdminPass1!"},
    )
    assert resp.status_code == 200, (
        f"logged_in_client: login failed with {resp.status_code}: {resp.get_json()}"
    )
    return client


@pytest.fixture()
def limited_client(client, db_session, regular_user):
    """
    A test client that is already logged in as regular_user.
    regular_user only has 'system.inventory' permission, so any endpoint
    requiring a different permission should return 403.
    """
    resp = client.post(
        "/api/user/login",
        json={"email": "regular@example.com", "password": "RegularPass1!"},
    )
    assert resp.status_code == 200, (
        f"limited_client: login failed with {resp.status_code}: {resp.get_json()}"
    )
    return client
