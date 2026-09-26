"""
tests/test_seed.py — Tests for the `flask seed` CLI command in
app/api/commands/seed.py.
"""
import sqlalchemy as sa

from app.api.commands.seed import seed_command, seed_system_settings
from app.system_models import SystemSettings


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
