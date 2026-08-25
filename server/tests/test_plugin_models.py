"""
tests/test_plugin_models.py — Model-level tests for the Plugin Manager
database models (Phase 1).

These are unit tests on the ORM layer only — no HTTP routes exist yet
(that's Phase 3). They verify: table creation, relationships resolve,
enums round-trip, and the ActivityLog-linked audit pattern works the
same way it does for ConfigurationChanges/NCPADeploymentStatus/ExportLog.
"""
import pytest

from app.plugin_models import (
    Plugin, PluginType, PluginSource, PluginStatus,
    PluginVersion,
    PluginCommand, PluginCommandOverride,
    PluginDependency, DependencyType, DependencyStatus,
    PluginConfiguration,
    PluginHistory, PluginHistoryAction, PluginActionResult,
)
from app.system_models import ActivityLog


def _make_activity_log(db_session, admin_user, action="test.plugin.action"):
    log = ActivityLog(Action_Type=action, UserID=admin_user.UserID)
    db_session.session.add(log)
    db_session.session.flush()
    return log


def _make_plugin(db_session, name="check_company", plugin_type=PluginType.CUSTOM,
                  source=PluginSource.ADMINISTRATOR_ADDED, status=PluginStatus.READY):
    plugin = Plugin(
        Name=name,
        Display_Name="Check Company",
        Plugin_Type=plugin_type,
        Source=source,
        Status=status,
        Executable_Path=f"/usr/local/nagios/libexec/{name}",
    )
    db_session.session.add(plugin)
    db_session.session.flush()
    return plugin


class TestPlugin:
    def test_create_plugin(self, db_session):
        plugin = _make_plugin(db_session)
        db_session.session.commit()

        fetched = db_session.session.get(Plugin, plugin.PluginID)
        assert fetched is not None
        assert fetched.Name == "check_company"
        assert fetched.Plugin_Type == PluginType.CUSTOM
        assert fetched.Source == PluginSource.ADMINISTRATOR_ADDED
        assert fetched.Status == PluginStatus.READY

    def test_name_unique(self, db_session):
        _make_plugin(db_session, name="check_snmp")
        db_session.session.commit()

        dup = Plugin(
            Name="check_snmp",
            Plugin_Type=PluginType.NAGIOS,
            Source=PluginSource.BASELINE_ISO,
            Status=PluginStatus.READY,
        )
        db_session.session.add(dup)
        with pytest.raises(Exception):
            db_session.session.commit()
        db_session.session.rollback()


class TestPluginVersion:
    def test_version_linked_to_plugin(self, db_session):
        plugin = _make_plugin(db_session, name="check_http")
        version = PluginVersion(
            PluginID=plugin.PluginID,
            Version="2.4.13",
            Is_Current=True,
        )
        db_session.session.add(version)
        db_session.session.commit()

        assert version.Plugin_Version.Name == "check_http"

    def test_duplicate_plugin_version_rejected(self, db_session):
        plugin = _make_plugin(db_session, name="check_disk")
        db_session.session.add(PluginVersion(PluginID=plugin.PluginID, Version="1.0.0"))
        db_session.session.commit()

        db_session.session.add(PluginVersion(PluginID=plugin.PluginID, Version="1.0.0"))
        with pytest.raises(Exception):
            db_session.session.commit()
        db_session.session.rollback()


class TestPluginCommandOverride:
    def test_override_preserves_original_and_links_activity_log(self, db_session, admin_user):
        plugin = _make_plugin(db_session, name="check_snmp", plugin_type=PluginType.NAGIOS,
                               source=PluginSource.BASELINE_ISO)
        command = PluginCommand(
            PluginID=plugin.PluginID,
            Command_Name="check_snmp",
            Command_Definition="check_snmp -H $HOSTADDRESS$ -o $ARG1$",
            Is_Default=True,
        )
        db_session.session.add(command)
        db_session.session.flush()

        log = _make_activity_log(db_session, admin_user, action="plugin.command_override")

        override = PluginCommandOverride(
            PluginCommandID=command.PluginCommandID,
            Original_Command=command.Command_Definition,
            Override_Command="check_snmp -H $HOSTADDRESS$ -o $ARG1$ -w 80 -c 90",
            LogID=log.LogID,
        )
        db_session.session.add(override)
        db_session.session.commit()

        assert override.Command.Command_Name == "check_snmp"
        assert override.Original_Command == "check_snmp -H $HOSTADDRESS$ -o $ARG1$"
        assert override.Logs.UserID == admin_user.UserID

        # Confirm the reverse side (ActivityLog -> overrides) also resolves.
        # Plugin_Override_Logs is WriteOnlyMapped, so it exposes .select()
        # rather than loading eagerly.
        result = db_session.session.execute(log.Plugin_Override_Logs.select()).scalars().all()
        assert len(result) == 1
        assert result[0].PluginCommandOverrideID == override.PluginCommandOverrideID


class TestPluginDependency:
    def test_dependency_status(self, db_session):
        plugin = _make_plugin(db_session, name="check_snmp2")
        dep = PluginDependency(
            PluginID=plugin.PluginID,
            Dependency_Name="snmp",
            Dependency_Type=DependencyType.PACKAGE,
            Status=DependencyStatus.MISSING,
        )
        db_session.session.add(dep)
        db_session.session.commit()

        assert dep.Plugin_Dependency.PluginID == plugin.PluginID
        assert dep.Status == DependencyStatus.MISSING


class TestPluginConfiguration:
    def test_configuration_json_roundtrip(self, db_session):
        plugin = _make_plugin(db_session, name="check_snmp3")
        cfg = PluginConfiguration(
            PluginID=plugin.PluginID,
            Configuration_Data={"OID": "1.3.6.1", "Warning": "80", "Critical": "90"},
        )
        db_session.session.add(cfg)
        db_session.session.commit()

        db_session.session.expire_all()
        fetched = db_session.session.get(PluginConfiguration, cfg.PluginConfigurationID)
        assert fetched.Configuration_Data["OID"] == "1.3.6.1"


class TestPluginHistory:
    def test_history_records_action_with_activity_log(self, db_session, admin_user):
        plugin = _make_plugin(db_session, name="check_company2")
        log = _make_activity_log(db_session, admin_user, action="plugin.install")

        hist = PluginHistory(
            PluginID=plugin.PluginID,
            Action=PluginHistoryAction.INSTALL,
            New_Value="1.0.0",
            Result=PluginActionResult.SUCCESS,
            Message="Custom plugin registered.",
            LogID=log.LogID,
        )
        db_session.session.add(hist)
        db_session.session.commit()

        assert hist.Plugin_History.Name == "check_company2"
        assert hist.Logs.UserID == admin_user.UserID
        assert hist.Action == PluginHistoryAction.INSTALL
        assert hist.Result == PluginActionResult.SUCCESS
