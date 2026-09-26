"""
tests/test_plugin_enable_disable.py — Tests for Phase 5 (Enable/Disable).

subprocess.run is mocked throughout — this codebase's dev/test
environment doesn't have a real Nagios installation, and Enable/Disable
should be testable regardless of platform.
"""
from unittest.mock import patch

import pytest

from app.plugin_models import Plugin, PluginType, PluginSource, PluginStatus, PluginHistory


def _make_plugin(db_session, name, status=PluginStatus.READY):
    plugin = Plugin(
        Name=name, Plugin_Type=PluginType.NAGIOS, Source=PluginSource.BASELINE_ISO,
        Status=status,
    )
    db_session.session.add(plugin)
    db_session.session.commit()
    return plugin


def _mock_nagios_valid():
    return patch(
        "app.api.plugin.nagios_validator.subprocess.run",
        return_value=type("R", (), {"returncode": 0, "stdout": "ok", "stderr": ""})(),
    )


def _mock_nagios_invalid():
    return patch(
        "app.api.plugin.nagios_validator.subprocess.run",
        return_value=type("R", (), {"returncode": 1, "stdout": "", "stderr": "config error on line 4"})(),
    )


class TestEnablePlugin:
    def test_requires_login(self, client, db_session):
        plugin = _make_plugin(db_session, "check_ping")
        resp = client.post(f"/api/plugin/{plugin.PluginID}/enable")
        assert resp.status_code in (401, 302)

    def test_requires_permission(self, limited_client, db_session):
        plugin = _make_plugin(db_session, "check_ping")
        resp = limited_client.post(f"/api/plugin/{plugin.PluginID}/enable")
        assert resp.status_code == 403

    def test_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.post("/api/plugin/999999/enable")
        assert resp.status_code == 404

    def test_enable_success(self, logged_in_client, db_session):
        plugin = _make_plugin(db_session, "check_ping", status=PluginStatus.READY)

        with _mock_nagios_valid():
            resp = logged_in_client.post(f"/api/plugin/{plugin.PluginID}/enable")

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["status"] == "Enabled"
        assert data["changed"] is True

        db_session.session.refresh(plugin)
        assert plugin.Status == PluginStatus.ENABLED

    def test_enable_records_history(self, logged_in_client, db_session):
        plugin = _make_plugin(db_session, "check_ping", status=PluginStatus.READY)

        with _mock_nagios_valid():
            logged_in_client.post(f"/api/plugin/{plugin.PluginID}/enable")

        history = db_session.session.execute(
            db_session.select(PluginHistory).where(PluginHistory.PluginID == plugin.PluginID)
        ).scalar_one()
        assert history.Action.value == "Enable"
        assert history.Result.value == "Success"
        assert history.Old_Value == "Ready"
        assert history.New_Value == "Enabled"

    def test_enable_already_enabled_is_noop(self, logged_in_client, db_session):
        plugin = _make_plugin(db_session, "check_ping", status=PluginStatus.ENABLED)

        resp = logged_in_client.post(f"/api/plugin/{plugin.PluginID}/enable")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["changed"] is False

    def test_enable_already_active_is_noop_no_downgrade(self, logged_in_client, db_session):
        plugin = _make_plugin(db_session, "check_ping", status=PluginStatus.ACTIVE)

        resp = logged_in_client.post(f"/api/plugin/{plugin.PluginID}/enable")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["changed"] is False

        db_session.session.refresh(plugin)
        assert plugin.Status == PluginStatus.ACTIVE  # not downgraded to ENABLED

    @pytest.mark.parametrize("blocked_status", [
        PluginStatus.VALIDATION_FAILED,
        PluginStatus.DEPENDENCY_FAILED,
        PluginStatus.INSTALLATION_FAILED,
        PluginStatus.CONFIGURATION_FAILED,
        PluginStatus.ROLLBACK,
    ])
    def test_enable_blocked_statuses_rejected(self, logged_in_client, db_session, blocked_status):
        plugin = _make_plugin(db_session, "check_ping", status=blocked_status)

        resp = logged_in_client.post(f"/api/plugin/{plugin.PluginID}/enable")
        assert resp.status_code == 409

        db_session.session.refresh(plugin)
        assert plugin.Status == blocked_status  # unchanged

    def test_enable_nagios_validation_failure(self, logged_in_client, db_session):
        plugin = _make_plugin(db_session, "check_ping", status=PluginStatus.READY)

        with _mock_nagios_invalid():
            resp = logged_in_client.post(f"/api/plugin/{plugin.PluginID}/enable")

        assert resp.status_code == 502
        db_session.session.refresh(plugin)
        assert plugin.Status == PluginStatus.READY  # unchanged on failure

        history = db_session.session.execute(
            db_session.select(PluginHistory).where(PluginHistory.PluginID == plugin.PluginID)
        ).scalar_one()
        assert history.Result.value == "Failed"

    def test_enable_no_nagios_binary(self, app, logged_in_client, db_session):
        """Simulates a machine without Nagios installed by patching the binary
        path to a nonexistent file. Should fail honestly, not crash."""
        plugin = _make_plugin(db_session, "check_ping", status=PluginStatus.READY)
        with patch.dict(app.config, {"NAGIOS_BIN": "/nonexistent/nagios"}):
            resp = logged_in_client.post(f"/api/plugin/{plugin.PluginID}/enable")
        assert resp.status_code == 502


class TestDisablePlugin:
    def test_requires_permission(self, limited_client, db_session):
        plugin = _make_plugin(db_session, "check_ping")
        resp = limited_client.post(f"/api/plugin/{plugin.PluginID}/disable")
        assert resp.status_code == 403

    def test_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.post("/api/plugin/999999/disable")
        assert resp.status_code == 404

    def test_disable_success(self, logged_in_client, db_session):
        plugin = _make_plugin(db_session, "check_ping", status=PluginStatus.ENABLED)

        with _mock_nagios_valid():
            resp = logged_in_client.post(f"/api/plugin/{plugin.PluginID}/disable")

        assert resp.status_code == 200
        assert resp.get_json()["data"]["status"] == "Disabled"
        db_session.session.refresh(plugin)
        assert plugin.Status == PluginStatus.DISABLED

    def test_disable_from_active(self, logged_in_client, db_session):
        """Unlike Enable, Disable IS reachable from ACTIVE."""
        plugin = _make_plugin(db_session, "check_ping", status=PluginStatus.ACTIVE)

        with _mock_nagios_valid():
            resp = logged_in_client.post(f"/api/plugin/{plugin.PluginID}/disable")

        assert resp.status_code == 200
        db_session.session.refresh(plugin)
        assert plugin.Status == PluginStatus.DISABLED

    def test_disable_already_disabled_is_noop(self, logged_in_client, db_session):
        plugin = _make_plugin(db_session, "check_ping", status=PluginStatus.DISABLED)

        resp = logged_in_client.post(f"/api/plugin/{plugin.PluginID}/disable")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["changed"] is False

    def test_disable_blocked_status_rejected(self, logged_in_client, db_session):
        plugin = _make_plugin(db_session, "check_ping", status=PluginStatus.DEPENDENCY_FAILED)

        resp = logged_in_client.post(f"/api/plugin/{plugin.PluginID}/disable")
        assert resp.status_code == 409

    def test_disable_nagios_validation_failure(self, logged_in_client, db_session):
        plugin = _make_plugin(db_session, "check_ping", status=PluginStatus.ENABLED)

        with _mock_nagios_invalid():
            resp = logged_in_client.post(f"/api/plugin/{plugin.PluginID}/disable")

        assert resp.status_code == 502
        db_session.session.refresh(plugin)
        assert plugin.Status == PluginStatus.ENABLED  # unchanged on failure


class TestNagiosValidator:
    @pytest.fixture(autouse=True)
    def app_context(self, app):
        # validate_nagios_configuration() reads NAGIOS_BIN / NAGIOS_MAIN_CFG from app config.
        with app.app_context():
            yield

    def test_returns_false_when_binary_missing(self, app):
        from app.api.plugin.nagios_validator import validate_nagios_configuration
        with patch.dict(app.config, {"NAGIOS_BIN": "/nonexistent/nagios"}):
            is_valid, output = validate_nagios_configuration()
        assert is_valid is False
        assert "not found" in output

    def test_returns_true_on_success(self):
        from app.api.plugin.nagios_validator import validate_nagios_configuration
        with _mock_nagios_valid():
            is_valid, output = validate_nagios_configuration()
        assert is_valid is True

    def test_returns_false_on_nonzero_exit(self):
        from app.api.plugin.nagios_validator import validate_nagios_configuration
        with _mock_nagios_invalid():
            is_valid, output = validate_nagios_configuration()
        assert is_valid is False
        assert "config error" in output
