"""
tests/test_plugin_service.py — Tests for the Plugin Manager read
endpoints (Phase 3): GET /plugin, /plugin/summary, /plugin/<id>,
/plugin/history, /plugin/<id>/commands, /plugin/<id>/dependencies.
"""
import pytest

from app.plugin_models import (
    Plugin, PluginType, PluginSource, PluginStatus,
    PluginCommand, PluginCommandOverride,
    PluginDependency, DependencyType, DependencyStatus,
    PluginHistory, PluginHistoryAction, PluginActionResult,
)
from app.system_models import ActivityLog


def _make_plugin(db_session, name, plugin_type=PluginType.NAGIOS,
                  source=PluginSource.BASELINE_ISO, status=PluginStatus.READY,
                  version=None):
    plugin = Plugin(
        Name=name, Plugin_Type=plugin_type, Source=source,
        Status=status, Current_Version=version,
    )
    db_session.session.add(plugin)
    db_session.session.flush()
    return plugin


def _make_history(db_session, admin_user, plugin, action=PluginHistoryAction.INSTALL,
                   result=PluginActionResult.SUCCESS):
    log = ActivityLog(Action_Type="test.plugin.action", UserID=admin_user.UserID)
    db_session.session.add(log)
    db_session.session.flush()
    hist = PluginHistory(PluginID=plugin.PluginID, Action=action, Result=result, LogID=log.LogID)
    db_session.session.add(hist)
    db_session.session.commit()
    return hist


class TestPluginInventory:
    def test_requires_login(self, client, db_session):
        resp = client.get("/api/plugin")
        assert resp.status_code in (401, 302)

    def test_requires_permission(self, limited_client, db_session):
        resp = limited_client.get("/api/plugin")
        assert resp.status_code == 403

    def test_returns_empty_list(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/plugin")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["items"] == []
        assert data["total"] == 0

    def test_returns_plugins(self, logged_in_client, db_session):
        _make_plugin(db_session, "check_ping")
        _make_plugin(db_session, "check_snmp")
        db_session.session.commit()

        resp = logged_in_client.get("/api/plugin")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["total"] == 2
        names = sorted(item["name"] for item in data["items"])
        assert names == ["check_ping", "check_snmp"]

    def test_search_filters_by_name(self, logged_in_client, db_session):
        _make_plugin(db_session, "check_ping")
        _make_plugin(db_session, "check_snmp")
        db_session.session.commit()

        resp = logged_in_client.get("/api/plugin?search=snmp")
        data = resp.get_json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["name"] == "check_snmp"

    def test_type_filter(self, logged_in_client, db_session):
        _make_plugin(db_session, "check_ping", plugin_type=PluginType.NAGIOS)
        _make_plugin(db_session, "check_company", plugin_type=PluginType.CUSTOM)
        db_session.session.commit()

        resp = logged_in_client.get("/api/plugin?type=Custom")
        data = resp.get_json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["name"] == "check_company"

    def test_invalid_type_filter_rejected(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/plugin?type=NotARealType")
        assert resp.status_code == 400

    def test_failed_status_matches_any_failed_variant(self, logged_in_client, db_session):
        _make_plugin(db_session, "a", status=PluginStatus.VALIDATION_FAILED)
        _make_plugin(db_session, "b", status=PluginStatus.DEPENDENCY_FAILED)
        _make_plugin(db_session, "c", status=PluginStatus.READY)
        db_session.session.commit()

        resp = logged_in_client.get("/api/plugin?status=Failed")
        data = resp.get_json()["data"]
        assert data["total"] == 2

    def test_pagination_params(self, logged_in_client, db_session):
        for i in range(15):
            _make_plugin(db_session, f"check_{i}")
        db_session.session.commit()

        resp = logged_in_client.get("/api/plugin?page=2&per_page=10")
        data = resp.get_json()["data"]
        assert data["page"] == 2
        assert len(data["items"]) == 5
        assert data["total"] == 15

    def test_invalid_page_rejected(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/plugin?page=0")
        assert resp.status_code == 400

    def test_invalid_per_page_rejected(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/plugin?per_page=101")
        assert resp.status_code == 400

    def test_invalid_sort_field_rejected(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/plugin?sort_by=not_a_field")
        assert resp.status_code == 400

    def test_invalid_order_rejected(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/plugin?order=sideways")
        assert resp.status_code == 400


class TestPluginSummary:
    def test_requires_permission(self, limited_client, db_session):
        resp = limited_client.get("/api/plugin/summary")
        assert resp.status_code == 403

    def test_counts(self, logged_in_client, db_session):
        _make_plugin(db_session, "a", plugin_type=PluginType.CUSTOM)
        _make_plugin(db_session, "b", status=PluginStatus.UPDATE_AVAILABLE)
        _make_plugin(db_session, "c", status=PluginStatus.VALIDATION_FAILED)
        _make_plugin(db_session, "d", status=PluginStatus.ACTIVE)
        db_session.session.commit()

        resp = logged_in_client.get("/api/plugin/summary")
        data = resp.get_json()["data"]
        assert data["installed_plugins"] == 4
        assert data["custom_plugins"] == 1
        assert data["updates_available"] == 1
        assert data["validation_issues"] == 1
        assert data["active_capabilities"] == 1


class TestPluginDetails:
    def test_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/plugin/999999")
        assert resp.status_code == 404

    def test_returns_details(self, logged_in_client, db_session):
        plugin = _make_plugin(db_session, "check_snmp", version="2.4.12")
        db_session.session.commit()

        resp = logged_in_client.get(f"/api/plugin/{plugin.PluginID}")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["name"] == "check_snmp"
        assert data["current_version"] == "2.4.12"
        assert data["commands_count"] == 0
        assert data["dependencies_count"] == 0
        assert data["monitoring_usage"]["placeholder"] is True

    def test_counts_reflect_related_rows(self, logged_in_client, db_session):
        plugin = _make_plugin(db_session, "check_snmp")
        db_session.session.add(PluginCommand(
            PluginID=plugin.PluginID, Command_Name="check_snmp",
            Command_Definition="check_snmp -H $HOSTADDRESS$", Is_Default=True,
        ))
        db_session.session.add(PluginDependency(
            PluginID=plugin.PluginID, Dependency_Name="net-snmp",
            Dependency_Type=DependencyType.PACKAGE, Status=DependencyStatus.OK,
        ))
        db_session.session.commit()

        resp = logged_in_client.get(f"/api/plugin/{plugin.PluginID}")
        data = resp.get_json()["data"]
        assert data["commands_count"] == 1
        assert data["dependencies_count"] == 1


class TestPluginHistory:
    def test_global_listing(self, logged_in_client, db_session, admin_user):
        p1 = _make_plugin(db_session, "check_ping")
        p2 = _make_plugin(db_session, "check_snmp")
        _make_history(db_session, admin_user, p1)
        _make_history(db_session, admin_user, p2)

        resp = logged_in_client.get("/api/plugin/history")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["total"] == 2
        names = sorted(item["plugin_name"] for item in data["items"])
        assert names == ["check_ping", "check_snmp"]

    def test_filtered_by_plugin_id(self, logged_in_client, db_session, admin_user):
        p1 = _make_plugin(db_session, "check_ping")
        p2 = _make_plugin(db_session, "check_snmp")
        _make_history(db_session, admin_user, p1)
        _make_history(db_session, admin_user, p2)

        resp = logged_in_client.get(f"/api/plugin/history?plugin_id={p1.PluginID}")
        data = resp.get_json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["plugin_name"] == "check_ping"

    def test_administrator_field_populated(self, logged_in_client, db_session, admin_user):
        plugin = _make_plugin(db_session, "check_ping")
        _make_history(db_session, admin_user, plugin)

        resp = logged_in_client.get("/api/plugin/history")
        data = resp.get_json()["data"]
        assert data["items"][0]["administrator"] == f"{admin_user.First_Name} {admin_user.Last_Name}"


class TestPluginCommands:
    def test_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/plugin/999999/commands")
        assert resp.status_code == 404

    def test_no_override(self, logged_in_client, db_session):
        plugin = _make_plugin(db_session, "check_ping")
        db_session.session.add(PluginCommand(
            PluginID=plugin.PluginID, Command_Name="check_ping",
            Command_Definition="check_ping -H $HOSTADDRESS$", Is_Default=True,
        ))
        db_session.session.commit()

        resp = logged_in_client.get(f"/api/plugin/{plugin.PluginID}/commands")
        data = resp.get_json()["data"]
        assert len(data) == 1
        assert data[0]["is_overridden"] is False
        assert data[0]["active_command"] == data[0]["default_command"]

    def test_active_override_merged_in(self, logged_in_client, db_session, admin_user):
        plugin = _make_plugin(db_session, "check_snmp")
        command = PluginCommand(
            PluginID=plugin.PluginID, Command_Name="check_snmp",
            Command_Definition="check_snmp -H $HOSTADDRESS$", Is_Default=True,
        )
        db_session.session.add(command)
        db_session.session.flush()
        log = ActivityLog(Action_Type="plugin.command_override", UserID=admin_user.UserID)
        db_session.session.add(log)
        db_session.session.flush()
        db_session.session.add(PluginCommandOverride(
            PluginCommandID=command.PluginCommandID,
            Original_Command=command.Command_Definition,
            Override_Command=command.Command_Definition + " -w 80 -c 90",
            LogID=log.LogID,
        ))
        db_session.session.commit()

        resp = logged_in_client.get(f"/api/plugin/{plugin.PluginID}/commands")
        data = resp.get_json()["data"]
        assert data[0]["is_overridden"] is True
        assert data[0]["active_command"] == "check_snmp -H $HOSTADDRESS$ -w 80 -c 90"
        assert data[0]["default_command"] == "check_snmp -H $HOSTADDRESS$"


class TestPluginDependencies:
    def test_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/plugin/999999/dependencies")
        assert resp.status_code == 404

    def test_returns_dependencies(self, logged_in_client, db_session):
        plugin = _make_plugin(db_session, "check_dhcp")
        db_session.session.add(PluginDependency(
            PluginID=plugin.PluginID, Dependency_Name="CAP_NET_RAW",
            Dependency_Type=DependencyType.CAPABILITY, Status=DependencyStatus.OK,
        ))
        db_session.session.commit()

        resp = logged_in_client.get(f"/api/plugin/{plugin.PluginID}/dependencies")
        data = resp.get_json()["data"]
        assert len(data) == 1
        assert data[0]["type"] == "Capability"
        assert data[0]["status"] == "Ok"
