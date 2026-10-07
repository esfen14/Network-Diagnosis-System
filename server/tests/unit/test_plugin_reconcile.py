"""
tests/unit/test_plugin_reconcile.py — The plugin reconciler
(app/api/plugin/reconcile.py).

Plugin Manager is the on/off switch and Network Discovery supplies devices and
ports, so enabling a plugin attaches its discovered ports with no device
picking. The reconciler promotes identified ports, makes the AUTO
PluginConfiguration rows match the services the planner would generate, calls
the one Nagios writer, and sets each plugin Active or Enabled. Nagios itself is
never run: regenerate_and_apply_config_status is mocked at the module boundary.
"""
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from app import db
from app.api.plugin.reconcile import desired_services, reconcile_plugin_monitoring
from app.plugin_models import (
    Plugin,
    PluginActionResult,
    PluginConfiguration,
    PluginConfigurationOrigin,
    PluginConfigurationStatus,
    PluginHistory,
    PluginHistoryAction,
    PluginSource,
    PluginStatus,
    PluginType,
)
from app.system_models import Open_TCP_Services, PortState
from tests.support.identity_helpers import MAC_1, MAC_2, NET, make_status, run_scan, scan

APPLIED = ("applied", "New host.cfg applied.")


@pytest.fixture
def status(db_session, admin_user):
    return make_status(db_session, admin_user)


@pytest.fixture
def writer():
    """The single Nagios writer, replaced so no config is validated or reloaded."""
    with patch("app.api.plugin.reconcile.regenerate_and_apply_config_status", return_value=APPLIED) as mock:
        yield mock


def add_plugin(name, plugin_status=PluginStatus.ENABLED):
    plugin = Plugin(Name=name, Plugin_Type=PluginType.NAGIOS, Source=PluginSource.BASELINE_ISO, Status=plugin_status)
    db.session.add(plugin)
    db.session.commit()
    return plugin


def new_device(status, ip="10.0.0.5", mac=MAC_1, **services):
    return run_scan(db, status, scan(ip, mac=mac, **services))[(NET, ip)]


def rows(origin=PluginConfigurationOrigin.AUTO):
    return db.session.scalars(
        sa.select(PluginConfiguration).where(PluginConfiguration.Origin == origin)
        .order_by(PluginConfiguration.PluginConfigurationID)
    ).all()


def names():
    return sorted(row.Nagios_Service_Name for row in rows())


def port(device, number):
    return db.session.scalar(sa.select(Open_TCP_Services).where(
        Open_TCP_Services.NetDiscoveryID == device.NetDiscoveryID, Open_TCP_Services.Port_Number == number))


# ==========================================================
# ENABLING ATTACHES DISCOVERED PORTS
# ==========================================================

class TestAttach:

    def test_enabling_a_plugin_monitors_its_discovered_ports_and_records_them(self, db_session, admin_user, status, writer):
        device = new_device(status, tcp={22: "ssh", 80: "http"})
        assert port(device, 22).Port_State is PortState.SUGGESTED     # nothing enabled yet
        ssh = add_plugin("check_ssh")

        result = reconcile_plugin_monitoring(admin_user.UserID)

        assert result == {"success": True, "changed": True, "applied": 1, "removed": 0, "promoted": 1, "message": APPLIED[1]}
        assert port(device, 22).Port_State is PortState.MONITORED
        assert port(device, 80).Port_State is PortState.SUGGESTED       # check_http is not enabled
        (row,) = rows()
        assert (row.PluginID, row.NetDiscoveryID) == (ssh.PluginID, device.NetDiscoveryID)
        assert (row.Port_Number, row.Protocol, row.Metric) == (22, "tcp", None)
        assert row.Nagios_Service_Name == "ssh-22-tcp" == row.Service_Description
        assert row.Status is PluginConfigurationStatus.APPLIED
        assert row.Applied_At is not None
        assert db_session.session.get(Plugin, ssh.PluginID).Status is PluginStatus.ACTIVE
        writer.assert_called_once()

    def test_a_plugin_with_no_matching_port_stays_enabled(self, db_session, admin_user, status, writer):
        new_device(status, tcp={22: "ssh"})
        snmp = add_plugin("check_snmp")

        result = reconcile_plugin_monitoring(admin_user.UserID)

        assert result["applied"] == 0 and rows() == []
        assert db_session.session.get(Plugin, snmp.PluginID).Status is PluginStatus.ENABLED

    def test_nothing_is_attached_until_a_plugin_is_enabled(self, db_session, admin_user, status, writer):
        new_device(status, tcp={22: "ssh"})
        add_plugin("check_ssh", PluginStatus.INSTALLED)

        reconcile_plugin_monitoring(admin_user.UserID)

        assert rows() == []

    def test_every_device_with_the_port_is_attached_without_picking(self, db_session, admin_user, status, writer):
        new_device(status, "10.0.0.5", MAC_1, tcp={22: "ssh"})
        new_device(status, "10.0.0.6", MAC_2, tcp={22: "ssh"})
        add_plugin("check_ssh")

        reconcile_plugin_monitoring(admin_user.UserID)

        assert len(rows()) == 2

    def test_a_device_found_later_is_attached_by_the_next_run(self, db_session, admin_user, status, writer):
        new_device(status, "10.0.0.5", MAC_1, tcp={22: "ssh"})
        add_plugin("check_ssh")
        reconcile_plugin_monitoring(admin_user.UserID)
        first_applied_at = rows()[0].Applied_At

        new_device(status, "10.0.0.6", MAC_2, tcp={22: "ssh"})
        result = reconcile_plugin_monitoring(admin_user.UserID)

        assert result["applied"] == 1 and len(rows()) == 2
        assert rows()[0].Applied_At == first_applied_at

    def test_plugins_with_several_metrics_get_one_row_per_check(self, app, db_session, admin_user, status, writer):
        new_device(status, udp={161: "snmp"})
        add_plugin("check_snmp")

        reconcile_plugin_monitoring(admin_user.UserID)

        configured = len(app.config["SNMP_OIDS"])
        assert configured > 1 and len(rows()) == configured
        assert all(name.startswith("snmp-") and name.endswith("-161-udp") for name in names())
        assert all(row.Metric and row.Metric in row.Nagios_Service_Name for row in rows())
        assert {row.Protocol for row in rows()} == {"udp"}

    def test_the_generic_tcp_plugin_picks_up_identified_ports_with_no_plugin_of_their_own(self, db_session, admin_user, status, writer):
        device = new_device(status, tcp={9100: "printer", 22: "ssh"})
        add_plugin("check_tcp")

        reconcile_plugin_monitoring(admin_user.UserID)

        assert names() == ["printer-9100-tcp"]       # ssh has check_ssh, which is not enabled
        assert port(device, 22).Port_State is PortState.SUGGESTED

    def test_a_port_flagged_not_used_as_intended_waits_for_acknowledgement(self, db_session, admin_user, status, writer):
        device = new_device(status, tcp={22: "http"})
        row = port(device, 22)
        row.Expected_Service_Name = "ssh"
        db_session.session.commit()
        add_plugin("check_http")

        reconcile_plugin_monitoring(admin_user.UserID)

        assert rows() == [] and port(device, 22).Port_State is PortState.SUGGESTED

    def test_an_ignored_port_is_left_out_and_its_row_removed(self, db_session, admin_user, status, writer):
        device = new_device(status, tcp={22: "ssh"})
        add_plugin("check_ssh")
        reconcile_plugin_monitoring(admin_user.UserID)
        assert len(rows()) == 1

        port(device, 22).Port_State = PortState.IGNORED
        db_session.session.commit()
        result = reconcile_plugin_monitoring(admin_user.UserID)

        assert rows() == [] and result["removed"] == 1


# ==========================================================
# IDEMPOTENCE, DISABLE AND ENABLE AGAIN
# ==========================================================

class TestStateChanges:

    def test_running_twice_changes_nothing(self, db_session, admin_user, status, writer):
        new_device(status, tcp={22: "ssh"}, udp={161: "snmp"})
        add_plugin("check_ssh")
        add_plugin("check_snmp")
        reconcile_plugin_monitoring(admin_user.UserID)
        before = [(r.PluginConfigurationID, r.Applied_At) for r in rows()]

        again = reconcile_plugin_monitoring(admin_user.UserID)

        assert (again["applied"], again["removed"], again["promoted"]) == (0, 0, 0)
        assert [(r.PluginConfigurationID, r.Applied_At) for r in rows()] == before

    def test_disabling_removes_the_services_but_keeps_the_ports_and_enabling_restores_them(self, db_session, admin_user, status, writer):
        device = new_device(status, tcp={22: "ssh"})
        ssh = add_plugin("check_ssh")
        reconcile_plugin_monitoring(admin_user.UserID)
        assert len(rows()) == 1

        ssh.Status = PluginStatus.DISABLED
        db_session.session.commit()
        result = reconcile_plugin_monitoring(admin_user.UserID)

        assert rows() == [] and result["removed"] == 1
        assert port(device, 22).Port_State is PortState.MONITORED       # not demoted
        assert port(device, 22).Plugin_Name == "ssh"                    # still frozen
        assert db_session.session.get(Plugin, ssh.PluginID).Status is PluginStatus.DISABLED

        ssh.Status = PluginStatus.ENABLED
        db_session.session.commit()
        reconcile_plugin_monitoring(admin_user.UserID)

        assert names() == ["ssh-22-tcp"]
        assert db_session.session.get(Plugin, ssh.PluginID).Status is PluginStatus.ACTIVE

    def test_an_active_plugin_with_nothing_left_goes_back_to_enabled(self, db_session, admin_user, status, writer):
        device = new_device(status, tcp={22: "ssh"})
        ssh = add_plugin("check_ssh")
        reconcile_plugin_monitoring(admin_user.UserID)
        port(device, 22).Port_State = PortState.ARCHIVED
        db_session.session.commit()

        reconcile_plugin_monitoring(admin_user.UserID)

        assert db_session.session.get(Plugin, ssh.PluginID).Status is PluginStatus.ENABLED

    def test_plugins_in_other_states_are_not_touched(self, db_session, admin_user, status, writer):
        new_device(status, tcp={22: "ssh"})
        failed = add_plugin("check_ssh", PluginStatus.VALIDATION_FAILED)

        reconcile_plugin_monitoring(admin_user.UserID)

        assert db_session.session.get(Plugin, failed.PluginID).Status is PluginStatus.VALIDATION_FAILED

    def test_a_missing_port_keeps_its_service(self, db_session, admin_user, status, writer):
        device = new_device(status, tcp={22: "ssh"})
        add_plugin("check_ssh")
        reconcile_plugin_monitoring(admin_user.UserID)
        port(device, 22).Port_State = PortState.MISSING
        db_session.session.commit()

        reconcile_plugin_monitoring(admin_user.UserID)

        assert names() == ["ssh-22-tcp"]        # CRITICAL in Nagios is the right signal

    def test_manual_rows_are_never_touched(self, db_session, admin_user, status, writer):
        device = new_device(status, tcp={22: "ssh"})
        ping = add_plugin("check_ping", PluginStatus.ENABLED)
        manual = PluginConfiguration(
            PluginID=ping.PluginID, NetDiscoveryID=device.NetDiscoveryID, Service_Description="Ping",
            Status=PluginConfigurationStatus.APPLIED,
        )
        db_session.session.add(manual)
        db_session.session.commit()

        reconcile_plugin_monitoring(admin_user.UserID)
        reconcile_plugin_monitoring(admin_user.UserID)

        assert [r.Service_Description for r in rows(PluginConfigurationOrigin.MANUAL)] == ["Ping"]
        assert rows() == []
        assert db_session.session.get(Plugin, ping.PluginID).Status is PluginStatus.ACTIVE   # backed by the manual row


# ==========================================================
# THE MONITORING SERVER AND RETIRED DEVICES
# ==========================================================

class TestWhatIsNeverAttached:

    def test_nothing_is_generated_for_the_monitoring_server(self, db_session, admin_user, status, writer):
        # The scan skips the server's own addresses, so it never becomes a device.
        devices = run_scan(db, status, scan("10.0.0.9", mac=MAC_1, tcp={22: "ssh"}), skip_ips={"10.0.0.9"})
        add_plugin("check_ssh")

        reconcile_plugin_monitoring(admin_user.UserID)

        assert devices == {} and rows() == [] and desired_services() == []

    def test_a_device_excluded_from_scanning_is_not_attached(self, db_session, admin_user, status, writer):
        device = new_device(status, tcp={22: "ssh"})
        device.Include_Device_In_Scanning = False
        db_session.session.commit()
        add_plugin("check_ssh")

        reconcile_plugin_monitoring(admin_user.UserID)

        assert rows() == []


# ==========================================================
# THE WRITER AND ITS FAILURES
# ==========================================================

class TestWriter:

    def test_the_shared_writer_is_called_once_even_when_nothing_changed(self, db_session, admin_user, status, writer):
        add_plugin("check_ssh")
        reconcile_plugin_monitoring(admin_user.UserID)
        writer.assert_called_once()

    def test_unchanged_host_config_still_counts_as_success(self, db_session, admin_user, status):
        new_device(status, tcp={22: "ssh"})
        add_plugin("check_ssh")
        with patch("app.api.plugin.reconcile.regenerate_and_apply_config_status",
                   return_value=("unchanged", "Host configuration unchanged; Nagios was not reloaded.")):
            result = reconcile_plugin_monitoring(admin_user.UserID)

        assert result["success"] is True
        assert [r.Status for r in rows()] == [PluginConfigurationStatus.APPLIED]

    def test_a_rejected_config_changes_nothing_and_is_recorded(self, db_session, admin_user, status):
        device = new_device(status, tcp={22: "ssh"})
        ssh = add_plugin("check_ssh")
        with patch("app.api.plugin.reconcile.regenerate_and_apply_config_status",
                   return_value=("failed", "Config failed to validate: bad directive")):
            result = reconcile_plugin_monitoring(admin_user.UserID)

        assert result["success"] is False and "bad directive" in result["message"]
        assert rows() == []
        assert port(device, 22).Port_State is PortState.SUGGESTED        # the promotion was undone too
        assert db_session.session.get(Plugin, ssh.PluginID).Status is PluginStatus.ENABLED
        (history,) = db_session.session.scalars(sa.select(PluginHistory)).all()
        assert history.Action is PluginHistoryAction.CONFIGURE and history.Result is PluginActionResult.FAILED
        assert "bad directive" in history.Message

    def test_an_exception_rolls_back_and_is_raised(self, db_session, admin_user, status):
        new_device(status, tcp={22: "ssh"})
        add_plugin("check_ssh")
        with patch("app.api.plugin.reconcile.regenerate_and_apply_config_status", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                reconcile_plugin_monitoring(admin_user.UserID)

        assert rows() == []

    def test_a_successful_attach_is_written_to_the_plugin_history(self, db_session, admin_user, status, writer):
        new_device(status, tcp={22: "ssh"})
        add_plugin("check_ssh")

        reconcile_plugin_monitoring(admin_user.UserID)

        (history,) = db_session.session.scalars(sa.select(PluginHistory)).all()
        assert history.Action is PluginHistoryAction.CONFIGURE and history.Result is PluginActionResult.SUCCESS
        assert "1 service(s)" in history.Message

    def test_no_history_without_a_user(self, db_session, admin_user, status, writer):
        new_device(status, tcp={22: "ssh"})
        add_plugin("check_ssh")

        reconcile_plugin_monitoring(None)

        assert db_session.session.scalars(sa.select(PluginHistory)).all() == [] and len(rows()) == 1


# ==========================================================
# CALLERS
# ==========================================================

class TestTriggers:

    def test_enabling_a_plugin_through_the_api_attaches_its_ports(self, logged_in_client, db_session, admin_user, status, writer):
        device = new_device(status, tcp={22: "ssh"})
        ssh = add_plugin("check_ssh", PluginStatus.INSTALLED)

        with patch("app.api.plugin.service.validate_nagios_configuration", return_value=(True, "ok")):
            resp = logged_in_client.post(f"/api/plugin/{ssh.PluginID}/enable")

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["auto_apply"]["success"] is True and data["auto_apply"]["applied"] == 1
        assert data["status"] == "Active"
        assert names() == ["ssh-22-tcp"]
        assert port(device, 22).Port_State is PortState.MONITORED

    def test_disabling_a_plugin_through_the_api_removes_its_services(self, logged_in_client, db_session, admin_user, status, writer):
        new_device(status, tcp={22: "ssh"})
        ssh = add_plugin("check_ssh")
        reconcile_plugin_monitoring(admin_user.UserID)

        with patch("app.api.plugin.service.validate_nagios_configuration", return_value=(True, "ok")):
            resp = logged_in_client.post(f"/api/plugin/{ssh.PluginID}/disable")

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["status"] == "Disabled" and data["auto_apply"]["removed"] == 1
        assert rows() == []

    def test_a_failed_attach_does_not_fail_the_enable(self, logged_in_client, db_session, admin_user, status):
        new_device(status, tcp={22: "ssh"})
        ssh = add_plugin("check_ssh", PluginStatus.INSTALLED)

        with patch("app.api.plugin.service.validate_nagios_configuration", return_value=(True, "ok")), \
             patch("app.api.plugin.reconcile.reconcile_plugin_monitoring", side_effect=RuntimeError("boom")):
            resp = logged_in_client.post(f"/api/plugin/{ssh.PluginID}/enable")

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["auto_apply"]["success"] is False and data["status"] == "Enabled"

    def test_discovery_reconciles_after_a_scan_and_never_raises(self, app, db_session, admin_user):
        from app.network_discovery.create_host_cfg import _sync_running_plugins
        with patch("app.api.plugin.reconcile.reconcile_plugin_monitoring", return_value={"success": True}) as ok:
            _sync_running_plugins(app, admin_user.UserID)
        ok.assert_called_once_with(admin_user.UserID)

        with patch("app.api.plugin.reconcile.reconcile_plugin_monitoring", side_effect=RuntimeError("boom")):
            _sync_running_plugins(app, admin_user.UserID)       # logged, not raised

    def test_merging_devices_drops_the_sources_auto_rows(self, logged_in_client, db_session, admin_user, status, writer):
        source = new_device(status, "10.0.0.5", MAC_1, tcp={22: "ssh"})
        target = new_device(status, "10.0.0.6", MAC_2, tcp={22: "ssh"})
        add_plugin("check_ssh")
        reconcile_plugin_monitoring(admin_user.UserID)
        assert len(rows()) == 2

        with patch("app.api.system.device_identity.apply_config_change", return_value={}):
            resp = logged_in_client.post(f"/api/system/hosts/{source.NetDiscoveryID}/merge",
                                         json={"target_id": target.NetDiscoveryID})

        assert resp.status_code == 200
        assert [row.NetDiscoveryID for row in rows()] == [target.NetDiscoveryID]


# ==========================================================
# NCPA DEPLOYMENT AND THE EMPTY INVENTORY
# ==========================================================

class TestNcpaAndInventory:

    def run_add_ncpa_port(self, app, admin_user, device, applied=True):
        import threading
        from app.logging.deployment_history import create_ncpa_deployment_status
        from app.network_discovery import create_host_cfg

        run = create_ncpa_deployment_status(admin_user.UserID)
        with patch.object(create_host_cfg, "_validate_config", return_value=(True, "ok")), \
             patch.object(create_host_cfg, "_create_host_cfg_file"), \
             patch.object(create_host_cfg, "_apply_new_host_cfg", return_value=(applied, "applied")), \
             patch.object(create_host_cfg, "_sync_running_plugins") as reconcile:
            create_host_cfg.add_ncpa_port(app, [device.NetDiscoveryID], run.NCPADeployStatusID, threading.Event())
        return reconcile

    def test_a_finished_ncpa_deployment_reconciles_plugins(self, app, db_session, admin_user, status):
        device = new_device(status, tcp={22: "ssh"})
        reconcile = self.run_add_ncpa_port(app, admin_user, device)
        reconcile.assert_called_once_with(app, None)
        assert port(device, int(app.config["NCPA_PORT"])).Port_State is PortState.MONITORED

    def test_a_config_that_was_not_applied_does_not_reconcile(self, app, db_session, admin_user, status):
        device = new_device(status, tcp={22: "ssh"})
        reconcile = self.run_add_ncpa_port(app, admin_user, device, applied=False)
        reconcile.assert_not_called()

    def test_the_ncpa_service_exists_only_while_check_ncpa_is_enabled(self, app, db_session, admin_user, status, writer):
        from app.system_models import AgentStatus, NCPADeployment
        device = new_device(status, tcp={22: "ssh"})
        db_session.session.add(NCPADeployment(
            Token="t" * 32, Agent_Status=AgentStatus.DEPLOYED, NetworkDiscoveryID=device.NetDiscoveryID))
        db_session.session.commit()
        from app.network_discovery.port_lifecycle import mark_ncpa_port
        mark_ncpa_port(device.NetDiscoveryID)
        db_session.session.commit()
        ncpa = add_plugin("check_ncpa", PluginStatus.INSTALLED)

        reconcile_plugin_monitoring(admin_user.UserID)
        assert rows() == []                                  # monitored port, but its plugin is off

        ncpa.Status = PluginStatus.ENABLED
        db_session.session.commit()
        reconcile_plugin_monitoring(admin_user.UserID)
        assert names() and all(n.startswith("ncpa-") and n.endswith("-5693-tcp") for n in names())

    def test_an_empty_inventory_is_scanned_before_discovery(self, app, db_session):
        from app.network_discovery import create_host_cfg
        with patch("app.api.plugin.scanner.scan_plugin_directory", return_value=[]) as scan_dir, \
             patch("app.api.plugin.scanner.sync_plugin_inventory",
                   return_value={"created": 0, "updated": 0, "unchanged": 0}) as sync:
            assert create_host_cfg.ensure_plugin_inventory(app) is True
        scan_dir.assert_called_once()
        sync.assert_called_once()

    def test_an_existing_inventory_is_not_rescanned(self, app, db_session):
        from app.network_discovery import create_host_cfg
        add_plugin("check_ssh")
        with patch("app.api.plugin.scanner.scan_plugin_directory") as scan_dir:
            assert create_host_cfg.ensure_plugin_inventory(app) is False
        scan_dir.assert_not_called()

    def test_a_failing_inventory_scan_does_not_stop_discovery(self, app, db_session):
        from app.network_discovery import create_host_cfg
        with patch("app.api.plugin.scanner.scan_plugin_directory", side_effect=OSError("no such directory")):
            assert create_host_cfg.ensure_plugin_inventory(app) is False


# ==========================================================
# AN INSTALL THAT WAS MONITORING BEFORE ITS PLUGINS WERE SCANNED
# ==========================================================

def scanned(*names):
    from datetime import datetime, timezone
    from app.api.plugin.scanner import ScannedPlugin
    return [ScannedPlugin(name=n, path=f"/usr/local/nagios/libexec/{n}", size=1,
                          modified_at=datetime.now(timezone.utc), is_executable=True, version="2.4.12",
                          version_raw_output=None) for n in names]


class TestContinuityWhenTheInventoryIsFirstCreated:
    """
    The upgrade migration cannot enable plugins that do not exist yet. An install that never
    scanned its plugins but already monitors ports gets them enabled by the first scan, so its
    services do not silently drop out of Nagios; a fresh install enables nothing.
    """

    ALL = ("check_ssh", "check_http", "check_tcp", "check_snmp", "check_ping", "check_mysql")

    def first_scan(self, app):
        from app.network_discovery import create_host_cfg
        with patch("app.api.plugin.scanner.scan_plugin_directory", return_value=scanned(*self.ALL)):
            return create_host_cfg.ensure_plugin_inventory(app)

    def statuses(self, db_session):
        return {p.Name: p.Status for p in db_session.session.scalars(sa.select(Plugin)).all()}

    def test_plugins_behind_monitored_ports_are_enabled_so_the_services_keep_running(self, app, db_session, admin_user, status):
        device = new_device(status, tcp={22: "ssh", 80: "http", 3306: "mysql"}, udp={161: "snmp"})
        for number in (22, 80):
            port(device, number).Port_State = PortState.MONITORED
            port(device, number).Plugin_Name = "ssh" if number == 22 else "http"
        from app.system_models import Open_UDP_Services
        snmp = db_session.session.scalars(sa.select(Open_UDP_Services)).one()
        snmp.Port_State, snmp.Plugin_Name = PortState.MONITORED, "snmp"
        db_session.session.commit()

        assert self.first_scan(app) is True

        statuses = self.statuses(db_session)
        assert statuses["check_ssh"] is PluginStatus.ENABLED
        assert statuses["check_http"] is PluginStatus.ENABLED
        assert statuses["check_snmp"] is PluginStatus.ENABLED
        assert statuses["check_mysql"] is PluginStatus.READY       # only a suggested port
        assert statuses["check_ping"] is PluginStatus.READY        # checks no port
        assert statuses["check_tcp"] is PluginStatus.READY         # nothing is monitored generically

    def test_a_port_monitored_by_the_generic_check_enables_check_tcp(self, app, db_session, admin_user, status):
        device = new_device(status, tcp={9100: "printer"})
        port(device, 9100).Port_State = PortState.MONITORED
        port(device, 9100).Plugin_Name = "tcp"
        db_session.session.commit()

        self.first_scan(app)

        assert self.statuses(db_session)["check_tcp"] is PluginStatus.ENABLED

    def test_a_missing_port_still_counts_because_nagios_is_still_checking_it(self, app, db_session, admin_user, status):
        device = new_device(status, tcp={22: "ssh"})
        port(device, 22).Port_State = PortState.MISSING
        port(device, 22).Plugin_Name = "ssh"
        db_session.session.commit()

        self.first_scan(app)

        assert self.statuses(db_session)["check_ssh"] is PluginStatus.ENABLED

    def test_a_port_without_a_frozen_plugin_is_resolved_from_its_service_name(self, app, db_session, admin_user, status):
        device = new_device(status, tcp={80: "http"})
        port(device, 80).Port_State = PortState.MONITORED
        port(device, 80).Plugin_Name = None
        db_session.session.commit()

        self.first_scan(app)

        assert self.statuses(db_session)["check_http"] is PluginStatus.ENABLED

    def test_a_fresh_install_enables_nothing(self, app, db_session, admin_user, status):
        new_device(status, tcp={22: "ssh", 80: "http"})        # discovered, only suggested

        assert self.first_scan(app) is True

        assert set(self.statuses(db_session).values()) == {PluginStatus.READY}

    def test_an_empty_network_enables_nothing(self, app, db_session):
        self.first_scan(app)
        assert set(self.statuses(db_session).values()) == {PluginStatus.READY}

    def test_an_existing_inventory_is_never_touched(self, app, db_session, admin_user, status):
        device = new_device(status, tcp={22: "ssh"})
        port(device, 22).Port_State = PortState.MONITORED
        port(device, 22).Plugin_Name = "ssh"
        add_plugin("check_ssh", PluginStatus.DISABLED)        # an admin switched it off on purpose
        db_session.session.commit()

        from app.network_discovery import create_host_cfg
        assert create_host_cfg.ensure_plugin_inventory(app) is False

        assert self.statuses(db_session)["check_ssh"] is PluginStatus.DISABLED

    def test_a_plugin_in_a_failure_state_is_not_switched_on(self, db_session, admin_user, status):
        from app.network_discovery.port_lifecycle import enable_plugins_backing_monitored_ports
        device = new_device(status, tcp={22: "ssh"})
        port(device, 22).Port_State = PortState.MONITORED
        port(device, 22).Plugin_Name = "ssh"
        add_plugin("check_ssh", PluginStatus.VALIDATION_FAILED)
        db_session.session.commit()

        assert enable_plugins_backing_monitored_ports() == []
        assert self.statuses(db_session)["check_ssh"] is PluginStatus.VALIDATION_FAILED

    def test_an_unmatched_udp_port_backs_no_plugin(self, db_session, admin_user, status):
        from app.network_discovery.port_lifecycle import plugins_backing_monitored_ports
        from app.system_models import Open_UDP_Services
        device = new_device(status, udp={9999: "mystery"})
        row = db_session.session.scalars(sa.select(Open_UDP_Services)).one()
        row.Port_State = PortState.MONITORED
        db_session.session.commit()

        assert plugins_backing_monitored_ports() == set()


class TestPluginStoredWithScriptExtension:
    def test_check_ncpa_py_gates_the_ncpa_service(self, app, db_session, admin_user, status, writer):
        from app.system_models import AgentStatus, NCPADeployment
        from app.network_discovery.port_lifecycle import enabled_plugin_names, mark_ncpa_port
        device = new_device(status, tcp={22: "ssh"})
        db_session.session.add(NCPADeployment(
            Token="t" * 32, Agent_Status=AgentStatus.DEPLOYED, NetworkDiscoveryID=device.NetDiscoveryID))
        db_session.session.commit()
        mark_ncpa_port(device.NetDiscoveryID)
        db_session.session.commit()
        ncpa = add_plugin("check_ncpa.py", PluginStatus.INSTALLED)

        reconcile_plugin_monitoring(admin_user.UserID)
        assert rows() == []

        ncpa.Status = PluginStatus.ENABLED
        db_session.session.commit()
        assert "check_ncpa" in enabled_plugin_names()
        reconcile_plugin_monitoring(admin_user.UserID)
        assert names() and all(n.startswith("ncpa-") for n in names())
