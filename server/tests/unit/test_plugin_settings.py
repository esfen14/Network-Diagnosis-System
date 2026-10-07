"""
Tests for Settings -> Plugins: the SNMP OID and NCPA metric validators in
app/network_discovery/plugin_settings.py, the GET /api/system/plugin-settings and
PUT /api/system/plugin-settings/<plugin> routes, and that saved tables replace the
config.py SNMP_OIDS / NCPA_METRICS when the Nagios services are planned.

Nagios is never touched: the config writer behind the reconciler is mocked.
"""
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from app import db
from app.network_discovery.create_host_cfg import plan_plugin_services
from app.network_discovery.plugin_registry import Transport
from app.network_discovery.plugin_settings import (
    PluginSettingsError,
    plugin_config,
    validate_ncpa_metrics,
    validate_snmp_oids,
)
from app.plugin_models import (
    Plugin,
    PluginConfiguration,
    PluginConfigurationOrigin,
    PluginSource,
    PluginStatus,
    PluginType,
)
from app.system_models import ConfigurationChanges, Permission, PluginSettings, RolePermission
from tests.support.identity_helpers import MAC_1, NET, make_status, run_scan, scan

URL = "/api/system/plugin-settings"
SNMP_URL = f"{URL}/snmp"
NEW_OIDS = [{"metric": "cpu_load", "oid": "1.3.6.1.4.1.2021.10.1.3.1"}]
NCPA_URL = f"{URL}/ncpa"
NEW_METRICS = [
    {"metric": "load", "path": "cpu/percent", "warning": "60", "critical": "90", "queryargs": "aggregate=avg"},
    {"metric": "disk", "path": "disk/logical/{partition}/used_percent", "critical": "95"},
]


@pytest.fixture
def writer():
    """The single Nagios writer, replaced so no config is validated or reloaded."""
    with patch("app.api.plugin.reconcile.regenerate_and_apply_config_status",
               return_value=("applied", "New host.cfg applied.")) as mock:
        yield mock


def add_plugin(name, status=PluginStatus.ENABLED):
    db.session.add(Plugin(Name=name, Plugin_Type=PluginType.NAGIOS,
                          Source=PluginSource.BASELINE_ISO, Status=status))
    db.session.commit()


def add_snmp(status=PluginStatus.ENABLED):
    add_plugin("check_snmp", status)


def grant(db_session, role, permission_name):
    permission = db_session.session.query(Permission).filter_by(Name=permission_name).one()
    db_session.session.add(RolePermission(RoleID=role.RoleID, PermissionID=permission.PermissionID))
    db_session.session.commit()


def snmp_section(client):
    return client.get(URL).get_json()["data"]["snmp"]


def save(client, oids=NEW_OIDS, version=0):
    return client.put(SNMP_URL, json={"version": version, "oids": oids})


def service_names():
    return sorted(db.session.scalars(
        sa.select(PluginConfiguration.Nagios_Service_Name)
        .where(PluginConfiguration.Origin == PluginConfigurationOrigin.AUTO)
    ).all())


# ==========================================================
# VALIDATION
# ==========================================================

class TestValidateSnmpOids:

    def test_cleans_up_a_valid_list(self):
        cleaned = validate_snmp_oids([{"metric": " Uptime ", "oid": " .1.3.6.1.2.1.1.3.0 ", "extra": 1}])

        assert cleaned == [{"metric": "uptime", "oid": ".1.3.6.1.2.1.1.3.0"}]

    @pytest.mark.parametrize("oids", [
        [],
        "1.3.6",
        [{"metric": "uptime"}],
        [{"metric": "up time", "oid": "1.3.6.1"}],
        [{"metric": "uptime-1", "oid": "1.3.6.1"}],
        [{"metric": "_uptime", "oid": "1.3.6.1"}],
        [{"metric": "uptime", "oid": "1.3.six.1"}],
        [{"metric": "uptime", "oid": "1"}],
        [{"metric": "uptime", "oid": "1.3.6.1'; reboot"}],
        [{"metric": "a", "oid": "1.3.6.1"}, {"metric": "a", "oid": "1.3.6.2"}],
        [{"metric": "a", "oid": "1.3.6.1"}, {"metric": "b", "oid": ".1.3.6.1"}],
        [{"metric": f"m{i}", "oid": f"1.3.6.{i}"} for i in range(51)],
    ])
    def test_rejects(self, oids):
        with pytest.raises(PluginSettingsError):
            validate_snmp_oids(oids)


# ==========================================================
# GET /api/system/plugin-settings
# ==========================================================

class TestGetPluginSettings:

    def test_requires_login(self, client, db_session):
        assert client.get(URL).status_code in (401, 302)

    def test_requires_the_plugins_permission(self, limited_client, db_session, regular_role):
        grant(db_session, regular_role, "settings.system")

        assert limited_client.get(URL).status_code == 403

    def test_the_plugins_permission_grants_access(self, limited_client, db_session, regular_role, writer):
        grant(db_session, regular_role, "settings.plugins")
        add_snmp()

        assert limited_client.get(URL).status_code == 200
        assert save(limited_client).status_code == 200

    def test_snmp_is_not_installed_without_its_plugin(self, logged_in_client, db_session):
        section = snmp_section(logged_in_client)

        assert (section["plugin"], section["installed"], section["status"]) == ("check_snmp", False, None)

    def test_defaults_come_from_config(self, logged_in_client, db_session, app):
        add_snmp(PluginStatus.ACTIVE)

        section = snmp_section(logged_in_client)

        assert section["installed"] is True and section["status"] == "Active"
        assert section["settings"]["oids"] == app.config["SNMP_OIDS"]
        assert section["defaults"]["oids"] == app.config["SNMP_OIDS"]
        assert section["version"] == 0


# ==========================================================
# PUT /api/system/plugin-settings/snmp
# ==========================================================

class TestSaveSnmpSettings:

    def test_saves_logs_and_rebuilds_the_config(self, logged_in_client, db_session, app, writer):
        add_snmp()

        resp = save(logged_in_client)

        data = resp.get_json()["data"]
        assert resp.status_code == 200
        assert data["settings"]["oids"] == NEW_OIDS and data["version"] == 1
        assert data["config_ok"] is True
        assert snmp_section(logged_in_client)["defaults"]["oids"] == app.config["SNMP_OIDS"]
        assert db.session.scalar(sa.select(PluginSettings)).Variables == {"oids": NEW_OIDS}
        log = db.session.scalar(sa.select(ConfigurationChanges))
        assert (log.Conf_Type, log.Parameter_Name) == ("plugin_settings", "snmp_oids")
        writer.assert_called_once()

    def test_refused_when_snmp_is_not_installed(self, logged_in_client, db_session, writer):
        assert save(logged_in_client).status_code == 400
        assert db.session.scalar(sa.select(PluginSettings)) is None

    def test_a_stale_version_is_refused(self, logged_in_client, db_session, writer):
        add_snmp()
        save(logged_in_client)

        assert save(logged_in_client, [{"metric": "other", "oid": "1.3.6.1"}], version=0).status_code == 409

    def test_an_invalid_entry_is_refused(self, logged_in_client, db_session, writer):
        add_snmp()

        resp = save(logged_in_client, [{"metric": "bad name", "oid": "1.3.6.1"}])

        assert resp.status_code == 400
        assert db.session.scalar(sa.select(PluginSettings)) is None

    def test_missing_oids_is_refused(self, logged_in_client, db_session):
        add_snmp()

        assert logged_in_client.put(SNMP_URL, json={"version": 0}).status_code == 400

    def test_saving_the_same_table_changes_nothing(self, logged_in_client, db_session, app, writer):
        add_snmp()

        resp = save(logged_in_client, app.config["SNMP_OIDS"])

        assert resp.status_code == 200 and resp.get_json()["data"]["version"] == 0
        assert db.session.scalar(sa.select(PluginSettings)) is None
        writer.assert_not_called()


# ==========================================================
# SAVED OIDS DRIVE THE NAGIOS SERVICES
# ==========================================================

class TestSavedOidsAreUsed:

    def test_plugin_config_uses_saved_oids_and_falls_back_to_config(self, app, db_session):
        assert plugin_config()["SNMP_OIDS"] == app.config["SNMP_OIDS"]

        db.session.add(PluginSettings(Plugin_Name="snmp", Variables={"oids": NEW_OIDS}, Version=1))
        db.session.commit()

        assert plugin_config()["SNMP_OIDS"] == NEW_OIDS
        assert app.config["SNMP_OIDS"] != NEW_OIDS

    def test_every_snmp_device_gets_one_service_per_saved_oid(self, logged_in_client, db_session, admin_user, writer):
        run_scan(db, make_status(db_session, admin_user), scan("10.0.0.5", mac=MAC_1, udp={161: "snmp"}))[(NET, "10.0.0.5")]
        add_snmp()

        save(logged_in_client, NEW_OIDS + [{"metric": "uptime", "oid": "1.3.6.1.2.1.1.3.0"}])

        assert service_names() == ["snmp-cpu_load-161-udp", "snmp-uptime-161-udp"]



# ==========================================================
# NCPA METRICS
# ==========================================================

class TestValidateNcpaMetrics:

    def test_cleans_up_a_valid_list_and_drops_empty_options(self):
        cleaned = validate_ncpa_metrics([{
            "metric": " CPU ", "path": "/cpu/percent/", "warning": "50", "critical": "",
            "units": " Gi ", "queryargs": "aggregate=avg", "extra": "x",
        }])

        assert cleaned == [{"metric": "cpu", "path": "cpu/percent", "warning": "50", "units": "Gi",
                            "queryargs": "aggregate=avg"}]

    @pytest.mark.parametrize("threshold", ["80", "10:", "~:20", "10:20", "@10:20", "-5:5", "0.5"])
    def test_accepts_nagios_thresholds(self, threshold):
        assert validate_ncpa_metrics([{"metric": "cpu", "path": "cpu/percent", "warning": threshold}])

    @pytest.mark.parametrize("metrics", [
        [],
        "cpu/percent",
        [{"metric": "cpu"}],
        [{"metric": "cpu load", "path": "cpu/percent"}],
        [{"metric": "cpu", "path": "cpu//percent"}],
        [{"metric": "cpu", "path": "cpu/{part}/percent"}],
        [{"metric": "cpu", "path": "cpu/percent'; reboot"}],
        [{"metric": "cpu", "path": "cpu/percent", "warning": "high"}],
        [{"metric": "cpu", "path": "cpu/percent", "critical": "80;"}],
        [{"metric": "cpu", "path": "cpu/percent", "units": "G b"}],
        [{"metric": "cpu", "path": "cpu/percent", "queryargs": "aggregate=avg&x=$(id)"}],
        [{"metric": "cpu", "path": "cpu/percent"}, {"metric": "cpu", "path": "memory/virtual/percent"}],
        [{"metric": f"m{i}", "path": "cpu/percent"} for i in range(51)],
    ])
    def test_rejects(self, metrics):
        with pytest.raises(PluginSettingsError):
            validate_ncpa_metrics(metrics)


class TestNcpaSettings:

    def test_ncpa_is_not_installed_without_its_plugin(self, logged_in_client, db_session, app):
        section = logged_in_client.get(URL).get_json()["data"]["ncpa"]

        assert (section["plugin"], section["installed"]) == ("check_ncpa", False)
        assert section["settings"]["metrics"] == app.config["NCPA_METRICS"]
        assert section["defaults"]["metrics"] == app.config["NCPA_METRICS"]

    def test_saves_and_rebuilds_the_config(self, logged_in_client, db_session, writer):
        add_plugin("check_ncpa")

        resp = logged_in_client.put(NCPA_URL, json={"version": 0, "metrics": NEW_METRICS})

        data = resp.get_json()["data"]
        assert resp.status_code == 200
        assert data["settings"]["metrics"] == NEW_METRICS and data["version"] == 1
        assert db.session.scalar(sa.select(PluginSettings)).Plugin_Name == "ncpa"
        assert db.session.scalar(sa.select(ConfigurationChanges)).Parameter_Name == "ncpa_metrics"
        writer.assert_called_once()

    def test_refused_when_ncpa_is_not_installed(self, logged_in_client, db_session, writer):
        assert logged_in_client.put(NCPA_URL, json={"version": 0, "metrics": NEW_METRICS}).status_code == 400

    def test_an_invalid_entry_is_refused(self, logged_in_client, db_session, writer):
        add_plugin("check_ncpa")

        resp = logged_in_client.put(NCPA_URL, json={"version": 0, "metrics": [{"metric": "cpu", "path": "cpu percent"}]})

        assert resp.status_code == 400
        assert db.session.scalar(sa.select(PluginSettings)) is None

    def test_snmp_and_ncpa_are_saved_separately(self, logged_in_client, db_session, app, writer):
        add_snmp()
        add_plugin("check_ncpa")

        save(logged_in_client)
        logged_in_client.put(NCPA_URL, json={"version": 0, "metrics": NEW_METRICS})

        sections = logged_in_client.get(URL).get_json()["data"]
        assert sections["snmp"]["settings"]["oids"] == NEW_OIDS and sections["snmp"]["version"] == 1
        assert sections["ncpa"]["settings"]["metrics"] == NEW_METRICS and sections["ncpa"]["version"] == 1

    def test_saving_the_defaults_resets_the_table(self, logged_in_client, db_session, app, writer):
        add_plugin("check_ncpa")
        logged_in_client.put(NCPA_URL, json={"version": 0, "metrics": NEW_METRICS})

        resp = logged_in_client.put(NCPA_URL, json={"version": 1, "metrics": app.config["NCPA_METRICS"]})

        data = resp.get_json()["data"]
        assert resp.status_code == 200 and data["version"] == 2
        assert data["settings"]["metrics"] == app.config["NCPA_METRICS"] == data["defaults"]["metrics"]
        assert plugin_config()["NCPA_METRICS"] == app.config["NCPA_METRICS"]
        assert writer.call_count == 2

    def test_an_unknown_plugin_is_404(self, logged_in_client, db_session):
        assert logged_in_client.put(f"{URL}/ssh", json={"version": 0}).status_code == 404

    def test_saved_metrics_drive_the_planned_services(self, logged_in_client, db_session, writer):
        add_plugin("check_ncpa")
        logged_in_client.put(NCPA_URL, json={"version": 0, "metrics": NEW_METRICS})
        facts = {"ncpa": {"token": "tok", "partitions": ["|", "|boot"]}}

        planned = plan_plugin_services("ncpa", "ncpa", 5693, Transport.TCP, facts, {}, plugin_config())

        assert [service["metric"] for service in planned] == ["load", "disk_root", "disk_boot"]
        assert "cpu/percent" in planned[0]["check_command"] and "-q 'aggregate=avg'" in planned[0]["check_command"]
        assert "disk/logical/|boot/used_percent" in planned[2]["check_command"]
