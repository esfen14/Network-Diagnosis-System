"""
tests/unit/test_upgrade_rehearsal.py — Upgrading an installation to plugin-driven monitoring.

Runs tests/support/upgrade_rehearsal_runner.py in a subprocess: a database as main would
have it, populated with devices, monitored and suggested ports, plugins in the states the
old code left them, old discovery settings and the plugin.configure permission, is taken
through every migration of this branch, through the first reconcile with Nagios mocked,
back down, and up again. The questions it answers are the ones an upgrade must not get
wrong: does monitoring survive, is anything lost or duplicated, and does a downgrade leave
data an older release would mishandle.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).resolve().parents[2]


def current_head():
    """The single head of the migration history, read from the scripts (raises on several heads)."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config()
    config.set_main_option("script_location", str(SERVER_DIR / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head()


HEAD = current_head()

# Services that were running before the upgrade: every Monitored or Missing port with a plugin.
RUNNING_BEFORE = {
    (1, "ssh-22-tcp"), (1, "http-80-tcp"), (1, "https-443-tcp"), (1, "http-proxy-8080-tcp"),
    (2, "ssh-22-tcp"), (2, "nrpe-5666-tcp"),
    (3, "ncpa-cpu-5693-tcp"), (3, "ncpa-memory-5693-tcp"), (3, "dns-53-udp"),
}


@pytest.fixture(scope="module")
def report():
    result = subprocess.run(
        [sys.executable, "tests/support/upgrade_rehearsal_runner.py"],
        cwd=SERVER_DIR, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, (result.stdout + result.stderr)[-3000:]
    body = result.stdout.split("REPORT_BEGIN")[1].split("REPORT_END")[0]
    return json.loads(body)


class TestUpgrade:

    def test_every_migration_applies_and_reaches_the_head(self, report):
        assert report["before"]["version"] == [["c7e3a9d1b5f2"]]
        assert report["after_upgrade"]["version"] == [[HEAD]]

    def test_plugins_that_back_monitored_ports_are_enabled_so_monitoring_survives(self, report):
        after = report["after_upgrade"]["plugins"]
        for name in ("check_ssh", "check_http", "check_tcp", "check_snmp", "check_ncpa", "check_dns"):
            assert after[name] == "ENABLED", name
        assert report["before"]["plugins"]["check_http"] == "DISABLED"     # a disabled plugin that was still running

    def test_other_plugins_are_left_alone(self, report):
        after = report["after_upgrade"]["plugins"]
        assert after["check_mysql"] == "READY"             # only a suggested port
        assert after["check_load"] == "READY"              # checks no port
        assert after["check_disk"] == "VALIDATION_FAILED"  # failure states are never overridden
        assert after["check_ping"] == "ACTIVE"             # applied by hand before; untouched

    def test_the_manual_configuration_is_kept_as_manual_with_a_running_since(self, report):
        assert report["after_upgrade"]["configs"] == [[1, "MANUAL", "APPLIED", "check_ping"]]
        assert report["manual_applied_at"] == [["2026-03-01"]]

    def test_the_two_discovery_tables_become_one_and_the_forced_entries_win(self, report):
        (networks, tcp, udp, version), = report["settings_after_upgrade"]
        assert json.loads(tcp) == {"22": "ssh", "8080": "http-proxy", "5693": "ncpa", "9100": "printer"}
        assert json.loads(udp) == {"161": "snmp"}
        assert version == 4 and json.loads(networks) == ["10.0.0.0/24"]
        assert "TCP_Forced_Services" not in report["after_upgrade"]["settings_columns"]

    def test_the_retired_permission_and_its_grant_are_gone(self, report):
        assert "plugin.configure" in report["before"]["permissions"]
        assert report["after_upgrade"]["permissions"] == ["plugin.disable", "plugin.enable", "settings.plugins"]
        # 3 is settings.plugins, which f3a8c1d6b2e9 adds and grants to Administrator.
        assert report["after_upgrade"]["grants"] == [[1], [2], [3]]

    def test_port_states_are_unchanged_by_the_migrations(self, report):
        assert report["after_upgrade"]["port_states"] == report["before"]["port_states"]


class TestFirstReconcile:

    def test_every_service_that_was_running_is_still_attached(self, report):
        attached = {(device, name) for device, name, _, _ in report["attached"]}
        assert RUNNING_BEFORE <= attached

    def test_each_service_is_attached_once(self, report):
        names = [(device, name) for device, name, _, _ in report["attached"]]
        assert len(names) == len(set(names)) == report["first_reconcile"]["applied"] == 15

    def test_a_second_reconcile_changes_nothing(self, report):
        second = report["second_reconcile"]
        assert (second["applied"], second["removed"], second["promoted"]) == (0, 0, 0)

    def test_ports_that_were_monitored_or_missing_keep_their_state(self, report):
        before = {tuple(row[:3]): row[3] for row in report["before"]["port_states"]}
        after = {tuple(row[:3]): row[3] for row in report["after_reconcile"]["port_states"]}
        for key, state in before.items():
            if state in ("MONITORED", "MISSING"):
                assert after[key] == state, key

    def test_a_missing_port_keeps_its_service_so_nagios_keeps_reporting_it(self, report):
        assert (2, "nrpe-5666-tcp") in {(device, name) for device, name, _, _ in report["attached"]}

    def test_a_suggested_port_of_a_plugin_that_was_never_enabled_stays_suggested(self, report):
        after = {tuple(row[:3]): row[3] for row in report["after_reconcile"]["port_states"]}
        assert after[("tcp", 1, 3306)] == "SUGGESTED"                    # check_mysql was never on

    def test_the_udp_port_no_plugin_can_check_is_not_attached(self, report):
        assert all(port != 9999 for _, _, _, port in report["attached"])

    def test_enabling_the_generic_tcp_plugin_for_continuity_does_not_start_monitoring_suggestions(self, report):
        """
        Gap G25: check_tcp is enabled because a port was monitored by the generic check, and an enabled
        generic check would attach every identified port with no plugin of its own. The upgrade holds the
        printer port that was only suggested, so nothing new is monitored by the upgrade itself.
        """
        after = {tuple(row[:3]): row[3] for row in report["after_reconcile"]["port_states"]}
        assert report["first_reconcile"]["promoted"] == 0
        assert after[("tcp", 2, 9100)] == "SUGGESTED"
        assert ["tcp", 2, 9100] in report["after_upgrade"]["held"]
        assert (2, "printer-9100-tcp") not in {(device, name) for device, name, _, _ in report["attached"]}

    def test_only_the_ports_the_first_reconcile_would_have_promoted_are_held(self, report):
        # mysql 3306 is Suggested but check_mysql was never enabled, so enabling it later still attaches it.
        assert report["after_upgrade"]["held"] == [["tcp", 2, 9100]]
        assert report["before"]["held"] == []

    def test_plugins_with_attached_services_become_active(self, report):
        plugins = report["after_reconcile"]["plugins"]
        for name in ("check_ssh", "check_http", "check_tcp", "check_snmp", "check_ncpa", "check_dns"):
            assert plugins[name] == "ACTIVE", name
        assert plugins["check_mysql"] == "READY" and plugins["check_ping"] == "ACTIVE"


class TestDowngradeAndUpgradeAgain:

    def test_a_downgrade_returns_to_the_previous_revision(self, report):
        assert report["after_downgrade"]["version"] == [["c7e3a9d1b5f2"]]
        assert "Origin" not in report["after_downgrade"]["config_columns"]

    def test_automatic_rows_do_not_survive_as_look_alike_manual_rows(self, report):
        """Older code would write any applied row to plugin-services.cfg, defining each service twice."""
        assert report["after_downgrade"]["configs"] == [[1, None, "APPLIED", "check_ping"]]

    def test_the_hand_made_row_and_every_port_survive_a_downgrade(self, report):
        assert report["after_downgrade"]["port_states"] == report["after_reconcile"]["port_states"]

    def test_the_old_discovery_columns_return_with_everything_as_forced(self, report):
        (forced, udp_forced), = report["settings_after_downgrade"]
        assert json.loads(forced) == {"22": "ssh", "8080": "http-proxy", "5693": "ncpa", "9100": "printer"}
        assert json.loads(udp_forced) == {"161": "snmp"}

    def test_plugin_states_are_not_reverted_by_a_downgrade(self, report):
        """Documented: the data step enabled plugins; going back leaves them enabled."""
        assert report["after_downgrade"]["plugins"]["check_ssh"] == "ACTIVE"

    def test_upgrading_again_reaches_the_head_and_removes_the_permission_again(self, report):
        again = report["after_reupgrade"]
        assert again["version"] == [[HEAD]]
        assert again["permissions"] == ["plugin.disable", "plugin.enable", "settings.plugins"]
        assert again["configs"] == [[1, "MANUAL", "APPLIED", "check_ping"]]
        assert again["port_states"] == report["after_reconcile"]["port_states"]
        assert again["held"] == [["tcp", 2, 9100]]          # recomputed: still Suggested, still held
