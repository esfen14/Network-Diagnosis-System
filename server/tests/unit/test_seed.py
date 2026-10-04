"""
tests/unit/test_seed.py — Tests for the `flask seed` and `flask init-production`
CLI commands in app/api/commands/seed.py.
"""
import sqlalchemy as sa

from app.api.commands.seed import (
    PERMISSIONS,
    init_production_command,
    seed_command,
    seed_system_settings,
)
from app.system_models import Permission, SystemSettings, User, UserStatus


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
