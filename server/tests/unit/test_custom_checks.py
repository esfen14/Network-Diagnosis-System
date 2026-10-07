"""
tests/unit/test_custom_checks.py — custom checks (spec files/Custom_Checks_Plan.md).

Covers the plugin classes and argument validation (pure), the routes that add, change,
pause and remove a check, the host config they produce, and how merging devices treats them.
The single Nagios writer is replaced, so nothing is validated or reloaded.
"""
from unittest.mock import patch

import os

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
        ("check_apt", "server"), ("check_ping", "host"), ("check_dbi", "credentials"), ("check_radius", "custom"),
        ("check_cluster", "unsupported"), ("check_company", None),
    ])
    def test_plugin_class(self, name, expected):
        assert custom_checks.plugin_class(name) == expected


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
            custom_checks.clean_variables("check_apt", {})

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
        ("check_apt", "Runs on the Nagios server"),
        ("check_ssh", "does not take custom checks"),
        ("check_dbi", "cannot be passed"),
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

        note = logged_in_client.get(f"/api/plugin/{apt.PluginID}").get_json()["data"]["custom_checks"]
        assert note["supported"] is False and "Nagios server" in note["note"] and note["fields"] == []

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
# PASSWORDS
# ==========================================================

PASSWORD = "S3cret-pw_9"
RADIUS = {"user": "probe", "password": PASSWORD, "config": "/etc/radiusclient/radiusclient.conf"}


class TestSecretsStore:

    def test_a_secret_round_trips_and_is_not_stored_as_text(self, app):
        from app import secrets_store
        with app.app_context():
            stored = secrets_store.encrypt(PASSWORD)
            assert stored.startswith("v1:") and PASSWORD not in stored
            assert secrets_store.decrypt(stored) == PASSWORD
            assert secrets_store.encrypt(PASSWORD) != stored  # a fresh token each time
            assert secrets_store.is_readable(stored)

    def test_another_key_cannot_read_it(self, app, monkeypatch):
        from app import secrets_store
        with app.app_context():
            stored = secrets_store.encrypt(PASSWORD)
            monkeypatch.setenv("PINPOINT_SECRETS_KEY", "a-different-key")
            with pytest.raises(secrets_store.SecretsError) as raised:
                secrets_store.decrypt(stored)
            assert PASSWORD not in str(raised.value) and not secrets_store.is_readable(stored)

    @pytest.mark.parametrize("bad", ["", "plain", "v1:not-a-token", None])
    def test_garbage_is_unreadable(self, app, bad):
        from app import secrets_store
        with app.app_context(), pytest.raises(secrets_store.SecretsError):
            secrets_store.decrypt(bad)

    def test_nothing_is_stored_under_a_temporary_key(self, app):
        from app import secrets_store
        app.config["SECRET_KEY_IS_TEMPORARY"] = True
        try:
            with app.app_context(), pytest.raises(secrets_store.SecretsError, match="fixed SECRET_KEY"):
                secrets_store.encrypt(PASSWORD)
        finally:
            app.config["SECRET_KEY_IS_TEMPORARY"] = False

    def test_an_explicit_key_wins_over_the_secret_key(self, app, monkeypatch):
        from app import secrets_store
        with app.app_context():
            under_secret_key = secrets_store.encrypt(PASSWORD)
            monkeypatch.setenv("PINPOINT_SECRETS_KEY", "explicit")
            under_explicit = secrets_store.encrypt(PASSWORD)
            assert secrets_store.decrypt(under_explicit) == PASSWORD
            assert not secrets_store.is_readable(under_secret_key)


class TestPasswordFields:

    def test_the_plugins_that_take_a_password(self):
        names = {plugin: custom_checks.secret_names(plugin) for plugin in custom_checks.CUSTOM_CHECK_FIELDS}
        assert {p: n for p, n in names.items() if n} == {
            "check_nt": ("password",), "check_radius": ("password",),
            "check_mysql_query": ("password",), "check_disk_smb": ("password",),
        }

    def test_a_radius_password_is_required_and_a_mysql_one_is_not(self):
        with pytest.raises(PluginConfigurationError, match="Password to test with"):
            custom_checks.clean_variables("check_radius", {"user": "u", "config": "/c"})
        assert custom_checks.clean_variables("check_mysql_query", {"query": "SELECT 1", "warning": "1", "critical": "2"})

    def test_split_and_rebuild(self, app):
        public, secret = custom_checks.split_secrets("check_radius", dict(RADIUS))
        assert secret == {"password": PASSWORD} and PASSWORD not in str(public)
        from app import secrets_store
        with app.app_context():
            data = {"variables": public, "secrets": {"password": secrets_store.encrypt(PASSWORD)}}
            assert custom_checks.command_variables(data) == RADIUS

    def test_a_radius_command_carries_the_password_as_an_argument(self):
        command = custom_checks.resolve_plugin_command_for("check_radius", {**RADIUS, "port": "1812"})
        assert command == f"pinpoint_custom_check_radius!probe!{PASSWORD}!/etc/radiusclient/radiusclient.conf!-P '1812'"


class TestPasswordRoutes:

    def add(self, client, plugin, device, name="Auth probe", variables=None):
        return client.post(checks_url(plugin), json={
            "device_id": device.NetDiscoveryID, "name": name, "variables": dict(RADIUS) if variables is None else variables})

    def test_the_password_is_stored_encrypted_and_never_returned(self, logged_in_client, db_session, status, writer, caplog):
        device = new_device(status)
        radius = add_plugin("check_radius")

        resp = self.add(logged_in_client, radius, device)

        data = resp.get_json()["data"]
        assert resp.status_code == 200
        assert "password" not in data["variables"] and PASSWORD not in resp.get_data(as_text=True)
        assert data["secrets_set"] == ["password"] and data["secrets_readable"] is True
        row, = rows()
        assert row.Configuration_Data["secrets"]["password"].startswith("v1:")
        assert PASSWORD not in str(row.Configuration_Data)
        assert row.Configuration_Data["variables"] == {"user": "probe", "config": RADIUS["config"]}
        history = db.session.scalar(sa.select(PluginHistory))
        assert PASSWORD not in (history.Message or "") and PASSWORD not in caplog.text

        listed = logged_in_client.get(checks_url(radius))
        assert PASSWORD not in listed.get_data(as_text=True)
        assert listed.get_json()["data"]["items"][0]["secrets_set"] == ["password"]

    def test_the_plugin_details_mark_password_fields(self, logged_in_client, db_session):
        radius = add_plugin("check_radius")
        fields = logged_in_client.get(f"/api/plugin/{radius.PluginID}").get_json()["data"]["custom_checks"]["fields"]
        assert {f["name"]: f["secret"] for f in fields} == {"user": False, "password": True, "config": False, "port": False}

    def test_a_missing_required_password_is_refused(self, logged_in_client, db_session, status, writer):
        device = new_device(status)
        resp = self.add(logged_in_client, add_plugin("check_radius"), device, variables={"user": "u", "config": "/c"})
        assert resp.status_code == 400 and "Password to test with" in resp.get_json()["message"] and rows() == []

    def test_an_unsafe_password_is_refused_without_echoing_it(self, logged_in_client, db_session, status, writer):
        device = new_device(status)
        bad = "pa'ss;word"
        resp = self.add(logged_in_client, add_plugin("check_radius"), device, variables={**RADIUS, "password": bad})
        assert resp.status_code == 400 and bad not in resp.get_data(as_text=True) and rows() == []

    def test_the_command_in_hosts_cfg_uses_the_decrypted_password(self, app, logged_in_client, db_session, status, writer, tmp_path):
        from app.network_discovery.create_host_cfg import _create_host_cfg_file, _load_monitored_hosts, load_custom_checks
        device = new_device(status)
        self.add(logged_in_client, add_plugin("check_radius"), device)

        [(name, command, plugin)] = load_custom_checks()[device.NetDiscoveryID]
        assert PASSWORD in command and plugin == "check_radius"
        original = app.config["HOST_CONFIG_DIR"]
        app.config["HOST_CONFIG_DIR"] = tmp_path
        try:
            text = _create_host_cfg_file(_load_monitored_hosts()).read_text()
        finally:
            app.config["HOST_CONFIG_DIR"] = original
        assert f"pinpoint_custom_check_radius!probe!{PASSWORD}!" in text

    def test_changing_a_check_keeps_the_password_when_it_is_left_blank(self, logged_in_client, db_session, status, writer):
        from app import secrets_store
        device = new_device(status)
        radius = add_plugin("check_radius")
        check = self.add(logged_in_client, radius, device).get_json()["data"]

        resp = logged_in_client.put(f"{checks_url(radius)}/{check['id']}", json={
            "name": "Auth probe", "variables": {"user": "other", "config": RADIUS["config"], "password": ""}})

        assert resp.status_code == 200
        data = rows()[0].Configuration_Data
        assert data["variables"]["user"] == "other"
        with logged_in_client.application.app_context():
            assert secrets_store.decrypt(data["secrets"]["password"]) == PASSWORD

    def test_a_new_password_replaces_the_old_one(self, logged_in_client, db_session, status, writer):
        from app import secrets_store
        device = new_device(status)
        radius = add_plugin("check_radius")
        check = self.add(logged_in_client, radius, device).get_json()["data"]

        logged_in_client.put(f"{checks_url(radius)}/{check['id']}", json={
            "name": "Auth probe", "variables": {**RADIUS, "password": "N3w-pass"}})

        with logged_in_client.application.app_context():
            assert secrets_store.decrypt(rows()[0].Configuration_Data["secrets"]["password"]) == "N3w-pass"

    def test_a_required_password_cannot_be_cleared_but_an_optional_one_can(self, logged_in_client, db_session, status, writer):
        device = new_device(status)
        radius, mysql = add_plugin("check_radius"), add_plugin("check_mysql_query")
        radius_check = self.add(logged_in_client, radius, device).get_json()["data"]
        refused = logged_in_client.put(f"{checks_url(radius)}/{radius_check['id']}", json={
            "name": "Auth probe", "variables": {"user": "probe", "config": RADIUS["config"]}, "clear_secrets": ["password"]})
        assert refused.status_code == 400 and "required" in refused.get_json()["message"]

        mysql_check = logged_in_client.post(checks_url(mysql), json={
            "device_id": device.NetDiscoveryID, "name": "Orders", "variables": {
                "query": "SELECT COUNT(*) FROM orders", "warning": "1", "critical": "5", "password": "dbpass"}}).get_json()["data"]
        assert mysql_check["secrets_set"] == ["password"]
        cleared = logged_in_client.put(f"{checks_url(mysql)}/{mysql_check['id']}", json={
            "name": "Orders", "variables": {"query": "SELECT COUNT(*) FROM orders", "warning": "1", "critical": "5"},
            "clear_secrets": ["password"]}).get_json()["data"]
        assert cleared["secrets_set"] == []

    def test_an_unknown_name_to_clear_is_refused(self, logged_in_client, db_session, status, writer):
        device = new_device(status)
        radius = add_plugin("check_radius")
        check = self.add(logged_in_client, radius, device).get_json()["data"]
        resp = logged_in_client.put(f"{checks_url(radius)}/{check['id']}", json={
            "name": "Auth probe", "variables": {}, "clear_secrets": ["user"]})
        assert resp.status_code == 400 and "not a password" in resp.get_json()["message"]
        assert logged_in_client.put(f"{checks_url(radius)}/{check['id']}", json={
            "name": "x", "variables": {}, "clear_secrets": "password"}).status_code == 400

    def test_a_password_that_can_no_longer_be_read_is_reported_and_left_out_of_the_file(
            self, app, logged_in_client, db_session, status, writer, monkeypatch, caplog):
        from app.network_discovery.create_host_cfg import load_custom_checks
        device = new_device(status)
        radius = add_plugin("check_radius")
        check = self.add(logged_in_client, radius, device).get_json()["data"]

        monkeypatch.setenv("PINPOINT_SECRETS_KEY", "rotated")
        listed = logged_in_client.get(checks_url(radius)).get_json()["data"]["items"][0]
        assert listed["secrets_readable"] is False and PASSWORD not in str(listed)
        assert load_custom_checks() == {}
        assert PASSWORD not in caplog.text

        # Without typing the password again the change is refused; with it, the check works again.
        refused = logged_in_client.put(f"{checks_url(radius)}/{check['id']}", json={
            "name": "Auth probe", "variables": {"user": "probe", "config": RADIUS["config"]}})
        assert refused.status_code == 400 and "Password to test with" in refused.get_json()["message"]
        fixed = logged_in_client.put(f"{checks_url(radius)}/{check['id']}", json={
            "name": "Auth probe", "variables": dict(RADIUS)})
        assert fixed.status_code == 200 and fixed.get_json()["data"]["secrets_readable"] is True
        assert load_custom_checks()

    def test_no_password_is_stored_without_a_fixed_key(self, app, logged_in_client, db_session, status, writer):
        device = new_device(status)
        app.config["SECRET_KEY_IS_TEMPORARY"] = True
        try:
            resp = self.add(logged_in_client, add_plugin("check_radius"), device)
        finally:
            app.config["SECRET_KEY_IS_TEMPORARY"] = False
        assert resp.status_code == 400 and "fixed SECRET_KEY" in resp.get_json()["message"] and rows() == []

    def test_a_check_without_passwords_never_needs_the_key(self, app, logged_in_client, db_session, status, writer):
        device = new_device(status)
        app.config["SECRET_KEY_IS_TEMPORARY"] = True
        try:
            resp = self.add(logged_in_client, add_plugin("check_ups"), device, variables={"ups": "nut1"})
        finally:
            app.config["SECRET_KEY_IS_TEMPORARY"] = False
        assert resp.status_code == 200


class TestWorldReadableWarning:

    def test_a_host_file_with_a_password_that_everyone_can_read_is_reported(self, app, caplog, tmp_path):
        from app.network_discovery.create_host_cfg import warn_if_world_readable
        if os.name != "posix":
            pytest.skip("POSIX file modes only")
        path = tmp_path / "hosts.cfg"
        path.write_text("x")
        path.chmod(0o644)
        with app.app_context():
            warn_if_world_readable(path)
        assert "readable by every user" in caplog.text
        caplog.clear()
        path.chmod(0o640)
        with app.app_context():
            warn_if_world_readable(path)
        assert "readable by every user" not in caplog.text
