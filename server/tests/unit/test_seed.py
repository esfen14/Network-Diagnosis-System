"""
tests/unit/test_seed.py — Tests for the `flask seed` and `flask init-production`
CLI commands in app/api/commands/seed.py.
"""
import sqlalchemy as sa

from app.api.commands.seed import (
    PERMISSIONS,
    init_production_command,
    missing_permissions,
    seed_command,
    seed_system_settings,
    sync_permissions,
    sync_permissions_command,
    warn_if_permissions_missing,
)
from app.system_models import (
    Permission, Role, RolePermission, SystemSettings, User, UserStatus,
)


class TestSeedSystemSettings:

    def test_creates_singleton_row_with_defaults(self, db_session):
        seed_system_settings()

        row = db_session.session.get(SystemSettings, 1)
        assert row is not None
        assert row.Scan_Frequency == 6
        assert row.Log_Retention_Days == 30
        assert row.Diagnostic_History_Retention_Days == 90

    def test_does_not_overwrite_existing_row(self, db_session):
        db_session.session.add(SystemSettings(Id=1, Scan_Frequency=12))
        db_session.session.commit()

        seed_system_settings()

        assert db_session.session.get(SystemSettings, 1).Scan_Frequency == 12
        count = db_session.session.scalar(sa.select(sa.func.count()).select_from(SystemSettings))
        assert count == 1

    def test_seed_command_creates_settings(self, app, db_session):
        result = app.test_cli_runner().invoke(seed_command)

        assert "Seed failed" not in result.output
        assert db_session.session.get(SystemSettings, 1) is not None


class TestInitProductionCommand:

    ADMIN_EMAIL = "admin-7f3a2@pinpoint.lan"
    PASSWORD = "S3cure-Passw0rd!"

    def invoke(self, app, password=PASSWORD, email=ADMIN_EMAIL):
        return app.test_cli_runner().invoke(
            init_production_command,
            ["--admin-email", email, "--password-stdin"],
            input=password,
        )

    def test_creates_single_active_admin_and_reference_data(self, app, db_session):
        result = self.invoke(app, password=self.PASSWORD + "\n")

        assert result.exit_code == 0, result.output
        users = db_session.session.scalars(sa.select(User)).all()
        assert len(users) == 1
        admin = users[0]
        assert admin.Email == self.ADMIN_EMAIL
        assert admin.Status == UserStatus.ACTIVE
        assert admin.Role.Name == "Administrator"
        # Trailing newline from the pipe is not part of the password.
        assert admin.check_password(self.PASSWORD)

        assert db_session.session.scalar(sa.select(sa.func.count()).select_from(Permission)) == len(PERMISSIONS)
        assert db_session.session.get(SystemSettings, 1) is not None

    def test_creates_no_test_users(self, app, db_session):
        self.invoke(app)

        emails = db_session.session.scalars(sa.select(User.Email)).all()
        assert not any(email.endswith("@test.com") for email in emails)

    def test_refuses_when_users_exist(self, app, db_session):
        assert self.invoke(app).exit_code == 0

        result = self.invoke(app, email="second@pinpoint.lan")

        assert result.exit_code != 0
        assert "already exist" in result.output
        count = db_session.session.scalar(sa.select(sa.func.count()).select_from(User))
        assert count == 1

    def test_rejects_short_password(self, app, db_session):
        result = self.invoke(app, password="short")

        assert result.exit_code != 0
        assert db_session.session.scalar(sa.select(sa.func.count()).select_from(User)) == 0

    def test_rejects_invalid_email(self, app, db_session):
        result = self.invoke(app, email="not-an-email")

        assert result.exit_code != 0
        assert db_session.session.scalar(sa.select(sa.func.count()).select_from(User)) == 0

    def test_requires_password_stdin_flag(self, app, db_session):
        result = app.test_cli_runner().invoke(
            init_production_command, ["--admin-email", self.ADMIN_EMAIL], input=self.PASSWORD
        )

        assert result.exit_code != 0
        assert db_session.session.scalar(sa.select(sa.func.count()).select_from(User)) == 0


class TestSyncPermissions:

    def _seed_old_install(self, db_session):
        """An install whose permission list predates system.hosts.edit."""
        from app.api.commands.seed import seed_permissions, seed_roles
        seed_permissions()
        seed_roles()
        perm = db_session.session.scalar(
            sa.select(Permission).where(Permission.Name == "system.hosts.edit")
        )
        db_session.session.execute(
            sa.delete(RolePermission).where(RolePermission.PermissionID == perm.PermissionID)
        )
        db_session.session.execute(
            sa.delete(Permission).where(Permission.PermissionID == perm.PermissionID)
        )
        db_session.session.commit()

    def test_adds_missing_permission_and_grants_administrator(self, app, db_session):
        self._seed_old_install(db_session)
        assert missing_permissions() == ["system.hosts.edit"]

        added, granted = sync_permissions()

        assert added == ["system.hosts.edit"]
        assert granted == ["system.hosts.edit"]
        assert missing_permissions() == []

    def test_second_run_changes_nothing(self, app, db_session):
        self._seed_old_install(db_session)
        sync_permissions()

        assert sync_permissions() == ([], [])

    def test_does_not_grant_other_roles(self, app, db_session):
        self._seed_old_install(db_session)
        sync_permissions()

        holders = db_session.session.scalars(
            sa.select(Role.Name)
            .join(RolePermission, RolePermission.RoleID == Role.RoleID)
            .join(Permission, Permission.PermissionID == RolePermission.PermissionID)
            .where(Permission.Name == "system.hosts.edit")
        ).all()
        assert holders == ["Administrator"]

    def test_cli_command_reports_changes(self, app, db_session):
        self._seed_old_install(db_session)

        result = app.test_cli_runner().invoke(sync_permissions_command)

        assert result.exit_code == 0, result.output
        assert "Permissions added: system.hosts.edit" in result.output

    def test_startup_warning_names_missing_permission(self, app, db_session):
        self._seed_old_install(db_session)
        messages = []

        class Log:
            def error(self, msg, *args): messages.append(msg % args)
            def warning(self, msg, *args): messages.append(msg % args)

        warn_if_permissions_missing(Log())

        assert any("system.hosts.edit" in m and "sync-permissions" in m for m in messages)
