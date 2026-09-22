"""
tests/test_plugin_command_management.py — Tests for Phase 6 (Command
Management): override_command and restore_default_command.
"""
import pytest

from app.plugin_models import (
    Plugin, PluginType, PluginSource, PluginStatus,
    PluginCommand, PluginCommandOverride, PluginHistory,
)


def _make_plugin_with_command(db_session, plugin_name="check_snmp",
                               default_command="check_snmp -H $HOSTADDRESS$ -o $ARG1$"):
    plugin = Plugin(
        Name=plugin_name, Plugin_Type=PluginType.NAGIOS,
        Source=PluginSource.BASELINE_ISO, Status=PluginStatus.READY,
    )
    db_session.session.add(plugin)
    db_session.session.flush()
    command = PluginCommand(
        PluginID=plugin.PluginID, Command_Name=plugin_name,
        Command_Definition=default_command, Is_Default=True,
    )
    db_session.session.add(command)
    db_session.session.commit()
    return plugin, command


class TestOverrideCommand:
    def test_requires_login(self, client, db_session):
        plugin, command = _make_plugin_with_command(db_session)
        resp = client.post(
            f"/api/plugin/{plugin.PluginID}/commands/{command.PluginCommandID}/override",
            json={"override_command": "x"},
        )
        assert resp.status_code in (401, 302)

    def test_requires_permission(self, limited_client, db_session):
        plugin, command = _make_plugin_with_command(db_session)
        resp = limited_client.post(
            f"/api/plugin/{plugin.PluginID}/commands/{command.PluginCommandID}/override",
            json={"override_command": "x"},
        )
        assert resp.status_code == 403

    def test_plugin_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/api/plugin/999999/commands/1/override",
            json={"override_command": "x"},
        )
        assert resp.status_code == 404

    def test_command_not_found(self, logged_in_client, db_session):
        plugin, command = _make_plugin_with_command(db_session)
        resp = logged_in_client.post(
            f"/api/plugin/{plugin.PluginID}/commands/999999/override",
            json={"override_command": "x"},
        )
        assert resp.status_code == 404

    def test_missing_body_rejected(self, logged_in_client, db_session):
        plugin, command = _make_plugin_with_command(db_session)
        resp = logged_in_client.post(
            f"/api/plugin/{plugin.PluginID}/commands/{command.PluginCommandID}/override",
            json={},
        )
        assert resp.status_code == 400

    def test_successful_override(self, logged_in_client, db_session):
        plugin, command = _make_plugin_with_command(db_session)
        override_text = "check_snmp -H $HOSTADDRESS$ -o $ARG1$ -w 80 -c 90"

        resp = logged_in_client.post(
            f"/api/plugin/{plugin.PluginID}/commands/{command.PluginCommandID}/override",
            json={"override_command": override_text},
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["active_command"] == override_text
        assert data["default_command"] == command.Command_Definition
        assert data["is_overridden"] is True

    def test_override_preserves_original_command(self, logged_in_client, db_session):
        plugin, command = _make_plugin_with_command(db_session)

        logged_in_client.post(
            f"/api/plugin/{plugin.PluginID}/commands/{command.PluginCommandID}/override",
            json={"override_command": "check_snmp -H $HOSTADDRESS$ -o $ARG1$ -w 80"},
        )

        override_row = db_session.session.execute(
            db_session.select(PluginCommandOverride).where(
                PluginCommandOverride.PluginCommandID == command.PluginCommandID
            )
        ).scalar_one()
        assert override_row.Original_Command == command.Command_Definition
        assert override_row.Is_Active is True

    def test_second_override_deactivates_first(self, logged_in_client, db_session):
        plugin, command = _make_plugin_with_command(db_session)

        logged_in_client.post(
            f"/api/plugin/{plugin.PluginID}/commands/{command.PluginCommandID}/override",
            json={"override_command": "check_snmp -w 80"},
        )
        logged_in_client.post(
            f"/api/plugin/{plugin.PluginID}/commands/{command.PluginCommandID}/override",
            json={"override_command": "check_snmp -w 90"},
        )

        overrides = db_session.session.execute(
            db_session.select(PluginCommandOverride).where(
                PluginCommandOverride.PluginCommandID == command.PluginCommandID
            )
        ).scalars().all()
        assert len(overrides) == 2
        active = [o for o in overrides if o.Is_Active]
        assert len(active) == 1
        assert active[0].Override_Command == "check_snmp -w 90"

    def test_override_records_history(self, logged_in_client, db_session):
        plugin, command = _make_plugin_with_command(db_session)

        logged_in_client.post(
            f"/api/plugin/{plugin.PluginID}/commands/{command.PluginCommandID}/override",
            json={"override_command": "check_snmp -w 80"},
        )

        history = db_session.session.execute(
            db_session.select(PluginHistory).where(PluginHistory.PluginID == plugin.PluginID)
        ).scalar_one()
        assert history.Action.value == "Command Override"
        assert history.Result.value == "Success"
        assert history.Old_Value == command.Command_Definition
        assert history.New_Value == "check_snmp -w 80"

    @pytest.mark.parametrize("dangerous", [
        "check_snmp; rm -rf /",
        "check_snmp `whoami`",
        "check_snmp $(whoami)",
        "check_snmp && rm -rf /",
        "check_snmp || rm -rf /",
        "check_snmp\nrm -rf /",
    ])
    def test_dangerous_commands_rejected(self, logged_in_client, db_session, dangerous):
        plugin, command = _make_plugin_with_command(db_session)
        resp = logged_in_client.post(
            f"/api/plugin/{plugin.PluginID}/commands/{command.PluginCommandID}/override",
            json={"override_command": dangerous},
        )
        assert resp.status_code == 400

    def test_pipe_is_allowed(self, logged_in_client, db_session):
        plugin, command = _make_plugin_with_command(db_session)
        resp = logged_in_client.post(
            f"/api/plugin/{plugin.PluginID}/commands/{command.PluginCommandID}/override",
            json={"override_command": "check_snmp -H $HOSTADDRESS$ | grep OK"},
        )
        assert resp.status_code == 200

    def test_empty_command_rejected(self, logged_in_client, db_session):
        plugin, command = _make_plugin_with_command(db_session)
        resp = logged_in_client.post(
            f"/api/plugin/{plugin.PluginID}/commands/{command.PluginCommandID}/override",
            json={"override_command": "   "},
        )
        assert resp.status_code == 400

    def test_command_belonging_to_different_plugin_rejected(self, logged_in_client, db_session):
        plugin1, command1 = _make_plugin_with_command(db_session, "check_a")
        plugin2, command2 = _make_plugin_with_command(db_session, "check_b")

        # Try to override plugin2's command via plugin1's id.
        resp = logged_in_client.post(
            f"/api/plugin/{plugin1.PluginID}/commands/{command2.PluginCommandID}/override",
            json={"override_command": "check_a -w 80"},
        )
        assert resp.status_code == 404


class TestRestoreDefaultCommand:
    def test_requires_permission(self, limited_client, db_session):
        plugin, command = _make_plugin_with_command(db_session)
        resp = limited_client.post(
            f"/api/plugin/{plugin.PluginID}/commands/{command.PluginCommandID}/restore-default"
        )
        assert resp.status_code == 403

    def test_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.post("/api/plugin/999999/commands/1/restore-default")
        assert resp.status_code == 404

    def test_noop_when_no_active_override(self, logged_in_client, db_session):
        plugin, command = _make_plugin_with_command(db_session)
        resp = logged_in_client.post(
            f"/api/plugin/{plugin.PluginID}/commands/{command.PluginCommandID}/restore-default"
        )
        assert resp.status_code == 200
        assert resp.get_json()["data"]["changed"] is False

    def test_restores_default_after_override(self, logged_in_client, db_session):
        plugin, command = _make_plugin_with_command(db_session)

        logged_in_client.post(
            f"/api/plugin/{plugin.PluginID}/commands/{command.PluginCommandID}/override",
            json={"override_command": "check_snmp -w 80"},
        )

        resp = logged_in_client.post(
            f"/api/plugin/{plugin.PluginID}/commands/{command.PluginCommandID}/restore-default"
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["changed"] is True
        assert data["is_overridden"] is False
        assert data["active_command"] == command.Command_Definition

    def test_restore_deactivates_override_without_deleting_it(self, logged_in_client, db_session):
        """History (the deactivated override row) is preserved, not deleted."""
        plugin, command = _make_plugin_with_command(db_session)

        logged_in_client.post(
            f"/api/plugin/{plugin.PluginID}/commands/{command.PluginCommandID}/override",
            json={"override_command": "check_snmp -w 80"},
        )
        logged_in_client.post(
            f"/api/plugin/{plugin.PluginID}/commands/{command.PluginCommandID}/restore-default"
        )

        override_row = db_session.session.execute(
            db_session.select(PluginCommandOverride).where(
                PluginCommandOverride.PluginCommandID == command.PluginCommandID
            )
        ).scalar_one()
        assert override_row.Is_Active is False
        assert override_row.Override_Command == "check_snmp -w 80"  # still there

    def test_restore_records_history_as_rollback(self, logged_in_client, db_session):
        plugin, command = _make_plugin_with_command(db_session)

        logged_in_client.post(
            f"/api/plugin/{plugin.PluginID}/commands/{command.PluginCommandID}/override",
            json={"override_command": "check_snmp -w 80"},
        )
        logged_in_client.post(
            f"/api/plugin/{plugin.PluginID}/commands/{command.PluginCommandID}/restore-default"
        )

        history_rows = db_session.session.execute(
            db_session.select(PluginHistory)
            .where(PluginHistory.PluginID == plugin.PluginID)
            .order_by(PluginHistory.PluginHistoryID)
        ).scalars().all()

        assert len(history_rows) == 2
        assert history_rows[0].Action.value == "Command Override"
        assert history_rows[1].Action.value == "Rollback"
        assert history_rows[1].Old_Value == "check_snmp -w 80"
        assert history_rows[1].New_Value == command.Command_Definition


class TestCommandValidator:
    def test_valid_command_passes(self):
        from app.api.plugin.command_validator import validate_command_definition
        is_valid, reason = validate_command_definition("check_snmp -H $HOSTADDRESS$ -o $ARG1$")
        assert is_valid is True
        assert reason is None

    def test_empty_rejected(self):
        from app.api.plugin.command_validator import validate_command_definition
        is_valid, reason = validate_command_definition("")
        assert is_valid is False

    def test_none_rejected(self):
        from app.api.plugin.command_validator import validate_command_definition
        is_valid, reason = validate_command_definition(None)
        assert is_valid is False

    def test_too_long_rejected(self):
        from app.api.plugin.command_validator import validate_command_definition, MAX_COMMAND_LENGTH
        is_valid, reason = validate_command_definition("a" * (MAX_COMMAND_LENGTH + 1))
        assert is_valid is False

    def test_pipe_allowed(self):
        from app.api.plugin.command_validator import validate_command_definition
        is_valid, reason = validate_command_definition("check_x | grep OK")
        assert is_valid is True
