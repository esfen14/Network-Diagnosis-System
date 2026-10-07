"""
tests/unit/test_custom_checks.py — custom checks (spec files/Custom_Checks_Plan.md).

Covers the plugin classes and argument validation (pure), the routes that add, change,
pause and remove a check, the host config they produce, and how merging devices treats them.
The single Nagios writer is replaced, so nothing is validated or reloaded.
"""
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from app import db
from app.network_discovery import custom_checks
from app.network_discovery.plugin_registry import PluginConfigurationError, service_driven_plugin_names
from app.plugin_models import (
    Plugin, PluginConfiguration, PluginConfigurationOrigin, PluginConfigurationStatus, PluginHistory,
    PluginActionResult, PluginSource, PluginStatus, PluginType,
)
from tests.support.identity_helpers import MAC_1, NET, make_status, run_scan, scan

APPLIED = ("applied", "New host.cfg applied.")
WRITER = "app.api.plugin.custom_checks.regenerate_and_apply_config_status"


@pytest.fixture
def status(db_session, admin_user):
    return make_status(db_session, admin_user)


@pytest.fixture
def writer():
    with patch(WRITER, return_value=APPLIED) as mock:
        yield mock


def add_plugin(name, plugin_status=PluginStatus.READY):
    plugin = Plugin(Name=name, Plugin_Type=PluginType.NAGIOS, Source=PluginSource.BASELINE_ISO, Status=plugin_status)
    db.session.add(plugin)
    db.session.commit()
    return plugin


def new_device(status, ip="10.0.0.5", mac=MAC_1):
    device = run_scan(db, status, scan(ip, mac=mac, tcp={22: "ssh"}))[(NET, ip)]
    return device


def checks_url(plugin):
    return f"/api/plugin/{plugin.PluginID}/custom-checks"


def rows():
    return db.session.scalars(
        sa.select(PluginConfiguration).where(PluginConfiguration.Origin == PluginConfigurationOrigin.CUSTOM)
    ).all()


# ==========================================================
# CLASSES AND ARGUMENTS
# ==========================================================

class TestPluginClasses:

    def test_every_catalog_plugin_outside_the_registry_has_a_class(self):
        from app.api.plugin.plugin_catalog_data import PLUGIN_CATALOG
        missing = sorted(
            name for name in PLUGIN_CATALOG
            if name not in service_driven_plugin_names() and name not in custom_checks.PLUGIN_CLASSES
        )
        assert missing == []

    def test_a_plugin_is_never_both_service_driven_and_custom(self):
        assert not set(custom_checks.CUSTOM_CHECK_FIELDS) & service_driven_plugin_names()

    def test_every_custom_plugin_takes_the_device_address(self):
        from app.api.plugin.plugin_command_defaults import PLUGIN_COMMAND_DEFAULTS
        for name in custom_checks.CUSTOM_CHECK_FIELDS:
            default = PLUGIN_COMMAND_DEFAULTS.get(name, f"{name} -H $HOSTADDRESS$")  # as the scanner falls back
            assert "$HOSTADDRESS$" in default, name

    @pytest.mark.parametrize("name, expected", [
        ("check_ssh", "service"), ("check_ncpa.py", "service"), ("check_by_ssh", "custom"),
        ("check_apt", "server"), ("check_load", "stock"), ("check_dhcp", "advanced"), ("check_ping", "custom"), ("check_dig", "custom"), ("check_radius", "credentials"),
        ("check_cluster", "unsupported"), ("check_company", None),
    ])
    def test_plugin_class(self, name, expected):
        assert custom_checks.plugin_class(name) == expected


class TestPingFamily:
    """check_ping, check_icmp, check_fping and check_dig take custom checks (Q-C7)."""

    @pytest.mark.parametrize("plugin, warning, critical", [
        ("check_ping", "100.0,20%", "500.0,60%"),
        ("check_icmp", "100.0,20%", "200.0,40%"),
        ("check_fping", "20%,100", "40%,200"),
    ])
    def test_thresholds_are_required_and_passed_as_given(self, plugin, warning, critical):
        with pytest.raises(PluginConfigurationError, match="Warning"):
            custom_checks.clean_variables(plugin, {})
        command = custom_checks.resolve_plugin_command_for(plugin, {"warning": warning, "critical": critical})
        assert command == f"pinpoint_custom_{plugin}!{warning}!{critical}!"

    def test_a_ping_command_runs_the_plugin_against_the_device(self):
        assert "$USER1$/check_ping -H $HOSTADDRESS$ -w '$ARG1$' -c '$ARG2$' $ARG3$" in (
            custom_checks.render_command_definition("check_ping"))

    def test_check_dig_needs_nothing_and_takes_what_it_is_given(self):
        assert custom_checks.clean_variables("check_dig", {}) == {}
        command = custom_checks.resolve_plugin_command_for("check_dig", {"lookup": "example.com", "port": "5353"})
        assert command == "pinpoint_custom_check_dig!-l 'example.com' -p '5353'"

    def test_every_catalog_plugin_still_has_one_class(self):
        from app.api.plugin.plugin_catalog_data import PLUGIN_CATALOG
        assert [name for name in PLUGIN_CATALOG if custom_checks.plugin_class(name) is None] == []


class TestArguments:

    def test_a_check_builds_its_command(self):
        command = custom_checks.resolve_plugin_command_for("check_ups", {"ups": "nut1", "warning": "50"})
        assert command == "pinpoint_custom_check_ups!nut1!-w '50'"

    def test_the_command_definition_runs_the_plugin(self):
        text = custom_checks.render_command_definition("check_ups")
        assert "command_name    pinpoint_custom_check_ups" in text
        assert "$USER1$/check_ups -H $HOSTADDRESS$ -u '$ARG1$' $ARG2$" in text

    def test_blank_optional_arguments_are_dropped(self):
        assert custom_checks.clean_variables("check_by_ssh", {"command": " check_apt ", "port": "", "user": None}) == {
            "command": "check_apt"
        }

    @pytest.mark.parametrize("bad", ["a'b", 'a"b', "a`b", "a!b", "a$b", "a;b", "a\\b", "a\nb"])
    def test_forbidden_characters_are_refused_without_echoing_the_value(self, bad):
        with pytest.raises(PluginConfigurationError) as raised:
            custom_checks.clean_variables("check_ups", {"ups": bad})
        assert "forbidden" in str(raised.value) and bad not in str(raised.value)

    def test_a_missing_required_argument_is_refused(self):
        with pytest.raises(PluginConfigurationError, match="UPS name"):
            custom_checks.clean_variables("check_ups", {})

    def test_an_unknown_argument_and_a_bad_port_are_refused(self):
        with pytest.raises(PluginConfigurationError, match="Unknown argument 'password'"):
            custom_checks.clean_variables("check_by_ssh", {"command": "x", "password": "secret"})
        with pytest.raises(PluginConfigurationError, match="port"):
            custom_checks.clean_variables("check_by_ssh", {"command": "x", "port": "70000"})

    def test_a_plugin_that_takes_no_custom_check_is_refused(self):
        with pytest.raises(PluginConfigurationError):
            custom_checks.clean_variables("check_load", {})

    def test_check_names(self):
        assert custom_checks.validate_check_name("  Weekly updates ") == "Weekly updates"
        assert custom_checks.service_name("check_by_ssh", "Weekly updates") == "custom-by_ssh-weekly_updates"
        for bad in ("", "   ", "x" * 61, "no/slash", "-leading"):
            with pytest.raises(PluginConfigurationError):
                custom_checks.validate_check_name(bad)

    def test_the_plugin_behind_a_custom_command(self):
        assert custom_checks.plugin_for_custom_command("pinpoint_custom_check_ups!nut1!") == "check_ups"
        assert custom_checks.plugin_for_custom_command("pinpoint_nd_ssh") is None
        assert custom_checks.plugin_for_custom_command(None) is None

    def test_statistics_group_a_custom_service_under_its_plugin(self, app):
        from app.api.system.statistics import _plugin_key
        with app.app_context():
            assert _plugin_key("custom-ups-rack", "pinpoint_custom_check_ups!nut1!") == "check_ups"


# ==========================================================
# ROUTES
# ==========================================================

class TestRoutes:

    def add(self, client, plugin, device, name="Rack UPS", variables=None, **extra):
        body = {"device_id": device.NetDiscoveryID, "name": name, "variables": {"ups": "nut1"} if variables is None else variables}
        body.update(extra)
        return client.post(checks_url(plugin), json=body)

    def test_adding_a_check_saves_applies_and_records_it(self, logged_in_client, db_session, status, writer):
        device = new_device(status)
        ups = add_plugin("check_ups")

        resp = self.add(logged_in_client, ups, device)

        data = resp.get_json()["data"]
        assert resp.status_code == 200
        assert data["service"] == "custom-ups-rack_ups" and data["variables"] == {"ups": "nut1"}
        assert data["changed"] is True and data["paused"] is False
        row, = rows()
        assert (row.Status, row.Port_Number, row.Protocol) == (PluginConfigurationStatus.APPLIED, None, None)
        assert row.Applied_At is not None and row.NetDiscoveryID == device.NetDiscoveryID
        writer.assert_called_once()
        history = db.session.scalar(sa.select(PluginHistory))
        assert history.Result is PluginActionResult.SUCCESS and "Rack UPS" in history.Message

    def test_a_rejected_config_saves_nothing_and_is_recorded(self, logged_in_client, db_session, status):
        device = new_device(status)
        ups = add_plugin("check_ups")

        with patch(WRITER, return_value=("failed", "Config failed to validate: bad")):
            resp = self.add(logged_in_client, ups, device)

        assert resp.status_code == 409 and "bad" in resp.get_json()["message"]
        assert rows() == []
        assert db.session.scalar(sa.select(PluginHistory)).Result is PluginActionResult.FAILED

    @pytest.mark.parametrize("plugin_name, message", [
        ("check_load", "Not managed here"),
        ("check_dhcp", "cannot build yet"),
        ("check_ssh", "does not take custom checks"),
        ("check_radius", "password"),
    ])
    def test_plugins_that_take_no_custom_check_are_refused(self, logged_in_client, db_session, status, writer,
                                                           plugin_name, message):
        device = new_device(status)
        plugin = add_plugin(plugin_name)

        resp = self.add(logged_in_client, plugin, device)

        assert resp.status_code == 400 and message in resp.get_json()["message"]
        assert rows() == []
        writer.assert_not_called()

    def test_a_failed_plugin_is_refused(self, logged_in_client, db_session, status, writer):
        device = new_device(status)
        ups = add_plugin("check_ups", PluginStatus.VALIDATION_FAILED)
        assert self.add(logged_in_client, ups, device).status_code == 400

    @pytest.mark.parametrize("extra, message", [
        ({"name": ""}, "name is required"),
        ({"variables": {}}, "required"),
        ({"variables": {"ups": "a'b"}}, "forbidden"),
        ({"variables": {"ups": "x", "password": "p"}}, "Unknown argument"),
        ({"device_id": 99999}, "Device not found"),
    ])
    def test_invalid_requests_are_refused(self, logged_in_client, db_session, status, writer, extra, message):
        device = new_device(status)
        ups = add_plugin("check_ups")

        resp = self.add(logged_in_client, ups, device, **extra)

        assert resp.status_code == 400 and message.lower() in resp.get_json()["message"].lower()
        assert rows() == []

    def test_a_retired_device_takes_no_check(self, logged_in_client, db_session, status, writer):
        from app.system_models import DeviceState
        device = new_device(status)
        device.Device_State = DeviceState.RETIRED
        db_session.session.commit()
        assert self.add(logged_in_client, add_plugin("check_ups"), device).status_code == 400

    def test_a_name_can_be_used_once_per_device_but_on_many_devices(self, logged_in_client, db_session, status, writer):
        first, second = new_device(status), new_device(status, "10.0.0.6", "aa:aa:aa:aa:aa:02")
        ups = add_plugin("check_ups")

        assert self.add(logged_in_client, ups, first).status_code == 200
        assert self.add(logged_in_client, ups, first).status_code == 400
        assert self.add(logged_in_client, ups, second).status_code == 200

    def test_changing_a_check_replaces_its_arguments_and_name(self, logged_in_client, db_session, status, writer):
        device = new_device(status)
        ups = add_plugin("check_ups")
        check = self.add(logged_in_client, ups, device).get_json()["data"]

        resp = logged_in_client.put(f"{checks_url(ups)}/{check['id']}",
                                    json={"name": "Server room UPS", "variables": {"ups": "nut2", "warning": "40"}})

        assert resp.status_code == 200
        row, = rows()
        assert (row.Service_Description, row.Nagios_Service_Name) == ("Server room UPS", "custom-ups-server_room_ups")
        assert row.Configuration_Data["variables"] == {"ups": "nut2", "warning": "40"}

    def test_pausing_removes_the_service_and_resuming_restores_it(self, logged_in_client, db_session, status, writer):
        device = new_device(status)
        ups = add_plugin("check_ups")
        check = self.add(logged_in_client, ups, device).get_json()["data"]
        url = f"{checks_url(ups)}/{check['id']}"

        paused = logged_in_client.post(f"{url}/pause").get_json()["data"]
        assert paused["paused"] is True and paused["status"]["kind"] == "paused"
        assert logged_in_client.post(f"{url}/pause").get_json()["data"]["changed"] is False

        resumed = logged_in_client.post(f"{url}/resume").get_json()["data"]
        assert resumed["paused"] is False

    def test_removing_a_check_deletes_it(self, logged_in_client, db_session, status, writer):
        device = new_device(status)
        ups = add_plugin("check_ups")
        check = self.add(logged_in_client, ups, device).get_json()["data"]

        resp = logged_in_client.delete(f"{checks_url(ups)}/{check['id']}")

        assert resp.status_code == 200 and rows() == []

    def test_a_rejected_removal_keeps_the_check(self, logged_in_client, db_session, status, writer):
        device = new_device(status)
        ups = add_plugin("check_ups")
        check = self.add(logged_in_client, ups, device).get_json()["data"]

        with patch(WRITER, return_value=("failed", "nope")):
            resp = logged_in_client.delete(f"{checks_url(ups)}/{check['id']}")

        assert resp.status_code == 409 and len(rows()) == 1

    def test_a_check_of_another_plugin_is_not_found(self, logged_in_client, db_session, status, writer):
        device = new_device(status)
        ups, wave = add_plugin("check_ups"), add_plugin("check_wave")
        check = self.add(logged_in_client, ups, device).get_json()["data"]

        assert logged_in_client.delete(f"{checks_url(wave)}/{check['id']}").status_code == 404
        assert logged_in_client.delete(f"{checks_url(ups)}/99999").status_code == 404
        assert logged_in_client.get("/api/plugin/99999/custom-checks").status_code == 404

    def test_the_list_shows_checks_with_status_and_filters(self, logged_in_client, db_session, status, writer):
        device = new_device(status)
        device.Nagios_Host_Name = "rack-01"
        db_session.session.commit()
        ups = add_plugin("check_ups")
        self.add(logged_in_client, ups, device, name="Rack UPS")
        self.add(logged_in_client, ups, device, name="Spare UPS")

        data = logged_in_client.get(checks_url(ups)).get_json()["data"]
        assert data["total"] == 2 and data["items"][0]["device"]["hostname"] == "rack-01"
        assert data["items"][0]["status"]["kind"] == "waiting"
        found = logged_in_client.get(f"{checks_url(ups)}?search=spare").get_json()["data"]
        assert [item["name"] for item in found["items"]] == ["Spare UPS"]
        assert logged_in_client.get(f"{checks_url(ups)}?page=0").status_code == 400

    def test_the_plugin_details_say_how_a_plugin_takes_checks(self, logged_in_client, db_session):
        ups, apt = add_plugin("check_ups"), add_plugin("check_apt")

        details = logged_in_client.get(f"/api/plugin/{ups.PluginID}").get_json()["data"]["custom_checks"]
        assert details["supported"] is True and details["class"] == "custom"
        assert [f["name"] for f in details["fields"]][0] == "ups" and details["fields"][0]["required"] is True

        assert details["target"] == "device"
        server = logged_in_client.get(f"/api/plugin/{apt.PluginID}").get_json()["data"]["custom_checks"]
        assert (server["supported"], server["class"], server["target"]) == (True, "server", "server")
        stock = add_plugin("check_load")
        note = logged_in_client.get(f"/api/plugin/{stock.PluginID}").get_json()["data"]["custom_checks"]
        assert note["supported"] is False and "Nagios Core" in note["note"] and note["fields"] == []
        assert note["target"] is None

    def test_the_permission_is_required(self, client, db_session, seeded_permissions, regular_role, status):
        from app.system_models import User, UserStatus
        user = User(First_Name="V", Last_Name="W", Email="v@example.com", Status=UserStatus.ACTIVE,
                    RoleID=regular_role.RoleID)
        user.set_password("ViewerPass1!")
        db_session.session.add(user)
        db_session.session.commit()
        ups = add_plugin("check_ups")
        with client.session_transaction() as session:
            session["_user_id"] = str(user.UserID)
            session["_fresh"] = True

        assert client.get(checks_url(ups)).status_code == 403
        assert client.post(checks_url(ups), json={}).status_code == 403


# ==========================================================
# HOST CONFIG AND MERGES
# ==========================================================

class TestHostConfig:

    def test_a_custom_check_is_written_under_its_host_with_its_command(self, app, db_session, status, writer, tmp_path):
        from app.network_discovery.create_host_cfg import _create_host_cfg_file, load_custom_checks
        device = new_device(status)
        ups = add_plugin("check_ups")
        db.session.add(PluginConfiguration(
            PluginID=ups.PluginID, NetDiscoveryID=device.NetDiscoveryID, Service_Description="Rack UPS",
            Nagios_Service_Name="custom-ups-rack_ups", Origin=PluginConfigurationOrigin.CUSTOM,
            Configuration_Data={"variables": {"ups": "nut1"}, "paused": False},
        ))
        db.session.add(PluginConfiguration(
            PluginID=ups.PluginID, NetDiscoveryID=device.NetDiscoveryID, Service_Description="Paused one",
            Nagios_Service_Name="custom-ups-paused_one", Origin=PluginConfigurationOrigin.CUSTOM,
            Configuration_Data={"variables": {"ups": "nut2"}, "paused": True},
        ))
        db.session.commit()

        assert load_custom_checks() == {
            device.NetDiscoveryID: [("custom-ups-rack_ups", "pinpoint_custom_check_ups!nut1!", "check_ups")]
        }

        from app.network_discovery.create_host_cfg import _load_monitored_hosts
        original = app.config["HOST_CONFIG_DIR"]
        app.config["HOST_CONFIG_DIR"] = tmp_path
        try:
            text = _create_host_cfg_file(_load_monitored_hosts()).read_text()
        finally:
            app.config["HOST_CONFIG_DIR"] = original

        assert "custom-ups-rack_ups" in text and "pinpoint_custom_check_ups!nut1!" in text
        assert "custom-ups-paused_one" not in text
        assert text.count("command_name    pinpoint_custom_check_ups") == 1
        assert "$USER1$/check_ups -H $HOSTADDRESS$" in text

    def test_a_check_with_arguments_that_no_longer_build_is_skipped(self, app, db_session, status):
        from app.network_discovery.create_host_cfg import load_custom_checks
        device = new_device(status)
        ups = add_plugin("check_ups")
        db.session.add(PluginConfiguration(
            PluginID=ups.PluginID, NetDiscoveryID=device.NetDiscoveryID, Service_Description="Broken",
            Nagios_Service_Name="custom-ups-broken", Origin=PluginConfigurationOrigin.CUSTOM,
            Configuration_Data={"variables": {"ups": "a'b"}},
        ))
        db.session.commit()
        assert load_custom_checks() == {}

    def test_the_reconciler_leaves_custom_checks_alone(self, app, db_session, status, writer):
        from app.api.plugin.reconcile import reconcile_plugin_monitoring
        device = new_device(status)
        ups = add_plugin("check_ups", PluginStatus.ENABLED)
        db.session.add(PluginConfiguration(
            PluginID=ups.PluginID, NetDiscoveryID=device.NetDiscoveryID, Service_Description="Rack UPS",
            Nagios_Service_Name="custom-ups-rack_ups", Origin=PluginConfigurationOrigin.CUSTOM,
            Status=PluginConfigurationStatus.APPLIED, Configuration_Data={"variables": {"ups": "nut1"}},
        ))
        db.session.commit()

        with patch("app.api.plugin.reconcile.regenerate_and_apply_config_status", return_value=APPLIED):
            reconcile_plugin_monitoring()

        assert [row.Nagios_Service_Name for row in rows()] == ["custom-ups-rack_ups"]

    def test_merging_moves_a_check_unless_the_target_has_one_of_that_name(self, logged_in_client, db_session, status, writer):
        from app.system_models import DeviceState
        source, target = new_device(status), new_device(status, "10.0.0.6", "aa:aa:aa:aa:aa:02")
        ups = add_plugin("check_ups")
        for device, name in ((source, "rack_ups"), (source, "spare_ups"), (target, "spare_ups")):
            db.session.add(PluginConfiguration(
                PluginID=ups.PluginID, NetDiscoveryID=device.NetDiscoveryID, Service_Description=name,
                Nagios_Service_Name=f"custom-ups-{name}", Origin=PluginConfigurationOrigin.CUSTOM,
                Configuration_Data={"variables": {"ups": "nut1"}},
            ))
        db.session.commit()

        with patch("app.api.system.device_identity.apply_config_change",
                   return_value={"config_applied": True, "config_ok": True, "config_message": ""}):
            resp = logged_in_client.post(
                f"/api/system/hosts/{source.NetDiscoveryID}/merge", json={"target_id": target.NetDiscoveryID})

        assert resp.status_code == 200
        assert sorted((r.NetDiscoveryID, r.Nagios_Service_Name) for r in rows()) == sorted([
            (target.NetDiscoveryID, "custom-ups-rack_ups"), (target.NetDiscoveryID, "custom-ups-spare_ups"),
        ])
        assert db.session.get(type(source), source.NetDiscoveryID).Device_State is DeviceState.MERGED


class TestDeviceSearch:

    def test_the_picker_lists_monitored_devices_by_name_and_filters(self, logged_in_client, db_session, status):
        from app.system_models import DeviceState
        first, second, retired = (new_device(status), new_device(status, "10.0.0.6", "aa:aa:aa:aa:aa:02"),
                                  new_device(status, "10.0.0.7", "aa:aa:aa:aa:aa:03"))
        first.Nagios_Host_Name, second.Nagios_Host_Name, retired.Nagios_Host_Name = "web-01", "db-01", "old-01"
        retired.Device_State = DeviceState.RETIRED
        db_session.session.commit()

        everything = logged_in_client.get("/api/plugin/custom-check-devices").get_json()["data"]
        assert [d["hostname"] for d in everything] == ["db-01", "web-01"]
        assert everything[0]["ip_address"] == "10.0.0.6"
        found = logged_in_client.get("/api/plugin/custom-check-devices?search=10.0.0.5").get_json()["data"]
        assert [d["hostname"] for d in found] == ["web-01"]


# ==========================================================
# SERVER CHECKS (checks that run on the Nagios server)
# ==========================================================

class TestServerCheckArguments:

    def test_a_server_plugin_runs_without_a_target_host(self):
        text = custom_checks.render_command_definition("check_apt")
        assert "command_line    $USER1$/check_apt $ARG1$" in text
        assert "-H" not in text
        assert "-H $HOSTADDRESS$" in custom_checks.render_command_definition("check_ups")

    def test_where_each_plugin_runs(self):
        assert custom_checks.check_target("check_apt") == "server"
        assert custom_checks.check_target("check_ups") == "device"
        assert custom_checks.check_target("check_ssh") is None
        assert custom_checks.check_target("check_load") is None

    def test_arguments_are_validated_like_a_device_checks(self):
        assert custom_checks.clean_variables("check_apt", {}) == {}
        assert custom_checks.clean_variables("check_sensors", {}) == {}
        with pytest.raises(PluginConfigurationError, match="File to check"):
            custom_checks.clean_variables("check_file_age", {})
        with pytest.raises(PluginConfigurationError, match="forbidden"):
            custom_checks.clean_variables("check_file_age", {"file": "/tmp/a;b"})
        command = custom_checks.resolve_plugin_command_for("check_file_age", {"file": "/var/backups/db.sql", "warning": "86400"})
        assert command == "pinpoint_custom_check_file_age!/var/backups/db.sql!-w '86400'"

    def test_service_names_say_they_are_the_servers(self):
        assert custom_checks.service_name("check_apt", "Weekly updates") == "server-apt-weekly_updates"
        assert custom_checks.service_name("check_ups", "Weekly updates") == "custom-ups-weekly_updates"

    def test_check_log_is_not_offered_because_it_writes_a_file(self):
        assert custom_checks.plugin_class("check_log") == "advanced"
        assert not custom_checks.is_custom_checkable("check_log")

    def test_the_five_stock_checks_stay_with_nagios_core(self):
        for name in ("check_load", "check_disk", "check_swap", "check_procs", "check_users"):
            assert custom_checks.plugin_class(name) == "stock" and not custom_checks.is_custom_checkable(name)


class TestServerCheckRoutes:

    def add(self, client, plugin, name="Package updates", variables=None, **extra):
        body = {"name": name, "variables": {} if variables is None else variables}
        body.update(extra)
        return client.post(checks_url(plugin), json=body)

    def test_adding_a_server_check_needs_no_device(self, logged_in_client, db_session, writer):
        apt = add_plugin("check_apt")

        resp = self.add(logged_in_client, apt, variables={"warning": "5"})

        data = resp.get_json()["data"]
        assert resp.status_code == 200 and data["service"] == "server-apt-package_updates"
        assert data["device"] == {"id": None, "hostname": "Nagios server", "ip_address": ""}
        row, = rows()
        assert row.NetDiscoveryID is None and row.Status is PluginConfigurationStatus.APPLIED
        assert row.Configuration_Data["variables"] == {"warning": "5"}
        history = db.session.scalar(sa.select(PluginHistory))
        assert "localhost" in history.Message

    def test_a_device_cannot_be_given_to_a_server_check(self, logged_in_client, db_session, status, writer):
        device = new_device(status)
        resp = self.add(logged_in_client, add_plugin("check_apt"), device_id=device.NetDiscoveryID)
        assert resp.status_code == 400 and "takes no device" in resp.get_json()["message"]

    def test_a_device_check_still_needs_a_device(self, logged_in_client, db_session, writer):
        resp = self.add(logged_in_client, add_plugin("check_ups"), variables={"ups": "nut1"})
        assert resp.status_code == 400 and "Choose a device" in resp.get_json()["message"]

    def test_a_name_is_used_once_on_the_server(self, logged_in_client, db_session, writer):
        apt = add_plugin("check_apt")
        assert self.add(logged_in_client, apt).status_code == 200
        second = self.add(logged_in_client, apt)
        assert second.status_code == 400 and "Nagios server already has a check named" in second.get_json()["message"]

    def test_a_server_check_may_share_a_name_with_a_device_check(self, logged_in_client, db_session, status, writer):
        device = new_device(status)
        assert self.add(logged_in_client, add_plugin("check_apt"), name="Rack UPS").status_code == 200
        ups = add_plugin("check_ups")
        resp = logged_in_client.post(checks_url(ups), json={
            "device_id": device.NetDiscoveryID, "name": "Rack UPS", "variables": {"ups": "nut1"}})
        assert resp.status_code == 200

    def test_listing_changing_pausing_and_removing_a_server_check(self, logged_in_client, db_session, writer):
        apt = add_plugin("check_apt")
        check = self.add(logged_in_client, apt).get_json()["data"]
        url = f"{checks_url(apt)}/{check['id']}"

        listed = logged_in_client.get(checks_url(apt)).get_json()["data"]
        assert listed["total"] == 1 and listed["items"][0]["device"]["hostname"] == "Nagios server"
        assert logged_in_client.get(f"{checks_url(apt)}?search=nagios server").get_json()["data"]["total"] == 1

        changed = logged_in_client.put(url, json={"name": "Updates", "variables": {"warning": "3"}}).get_json()["data"]
        assert changed["service"] == "server-apt-updates" and changed["variables"] == {"warning": "3"}

        assert logged_in_client.post(f"{url}/pause").get_json()["data"]["paused"] is True
        assert logged_in_client.post(f"{url}/resume").get_json()["data"]["paused"] is False
        assert logged_in_client.delete(url).status_code == 200 and rows() == []

    def test_a_rejected_config_saves_nothing(self, logged_in_client, db_session):
        with patch(WRITER, return_value=("failed", "bad")):
            resp = self.add(logged_in_client, add_plugin("check_apt"))
        assert resp.status_code == 409 and rows() == []

    def test_stock_and_advanced_plugins_are_refused(self, logged_in_client, db_session, writer):
        for name in ("check_load", "check_log"):
            assert self.add(logged_in_client, add_plugin(name)).status_code == 400


class TestServerChecksInHostConfig:

    def make(self, plugin, name, variables, paused=False):
        db.session.add(PluginConfiguration(
            PluginID=plugin.PluginID, NetDiscoveryID=None, Service_Description=name,
            Nagios_Service_Name=custom_checks.service_name(plugin.Name, name), Origin=PluginConfigurationOrigin.CUSTOM,
            Configuration_Data={"variables": variables, "paused": paused},
        ))

    def test_they_are_loaded_in_order_and_paused_ones_are_left_out(self, app, db_session):
        from app.network_discovery.create_host_cfg import load_custom_checks, load_server_checks
        apt, uptime = add_plugin("check_apt"), add_plugin("check_uptime")
        self.make(apt, "Updates", {"warning": "5"})
        self.make(uptime, "Uptime", {}, paused=True)
        self.make(uptime, "Reboot", {"warning": "1"})
        db.session.commit()

        assert load_server_checks() == [
            ("server-apt-updates", "pinpoint_custom_check_apt!-w '5'", "check_apt"),
            ("server-uptime-reboot", "pinpoint_custom_check_uptime!-w '1'", "check_uptime"),
        ]
        assert load_custom_checks() == {}

    def test_the_file_has_the_services_on_the_servers_host_and_never_the_host_itself(self, app, db_session, status, tmp_path):
        from app.network_discovery.create_host_cfg import _create_host_cfg_file, _load_monitored_hosts
        new_device(status)
        apt = add_plugin("check_apt")
        self.make(apt, "Updates", {"warning": "5"})
        db.session.commit()

        original = app.config["HOST_CONFIG_DIR"]
        app.config["HOST_CONFIG_DIR"] = tmp_path
        try:
            text = _create_host_cfg_file(_load_monitored_hosts()).read_text()
        finally:
            app.config["HOST_CONFIG_DIR"] = original

        assert "# Define Server Checks (Nagios server: localhost)" in text
        block = text.split("define service {")
        server_service = next(b for b in block if "server-apt-updates" in b)
        assert "host_name" in server_service and "localhost" in server_service
        assert "pinpoint_custom_check_apt!-w '5'" in server_service
        assert text.count("command_name    pinpoint_custom_check_apt") == 1
        assert "$USER1$/check_apt $ARG1$" in text
        # The host object itself is localhost.cfg's, never written here.
        import re
        assert not re.search(r"define host \{[^}]*host_name\s+localhost\b", text)

    def test_a_file_without_server_checks_has_no_section(self, app, db_session, status, tmp_path):
        from app.network_discovery.create_host_cfg import _create_host_cfg_file, _load_monitored_hosts
        new_device(status)
        original = app.config["HOST_CONFIG_DIR"]
        app.config["HOST_CONFIG_DIR"] = tmp_path
        try:
            text = _create_host_cfg_file(_load_monitored_hosts()).read_text()
        finally:
            app.config["HOST_CONFIG_DIR"] = original
        assert "Define Server Checks" not in text

    def test_merging_devices_leaves_them_alone(self, logged_in_client, db_session, status, writer):
        source, target = new_device(status), new_device(status, "10.0.0.6", "aa:aa:aa:aa:aa:02")
        self.make(add_plugin("check_apt"), "Updates", {})
        db.session.commit()

        with patch("app.api.system.device_identity.apply_config_change",
                   return_value={"config_applied": True, "config_ok": True, "config_message": ""}):
            resp = logged_in_client.post(
                f"/api/system/hosts/{source.NetDiscoveryID}/merge", json={"target_id": target.NetDiscoveryID})

        assert resp.status_code == 200
        row, = rows()
        assert row.NetDiscoveryID is None

    def test_the_reconciler_leaves_them_alone(self, app, db_session, writer):
        from app.api.plugin.reconcile import reconcile_plugin_monitoring
        self.make(add_plugin("check_apt", PluginStatus.ENABLED), "Updates", {})
        db.session.commit()
        with patch("app.api.plugin.reconcile.regenerate_and_apply_config_status", return_value=APPLIED):
            reconcile_plugin_monitoring()
        assert len(rows()) == 1
