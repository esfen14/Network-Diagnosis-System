"""
tests/unit/test_plugin_config_migration.py — The plugin configuration service
columns migration (migrations/versions/a8c4e1f6b2d3_plugin_configuration_service_columns.py).

Runs the migration on throwaway SQLite files (in a subprocess, see
tests/support/plugin_config_migration_runner.py) and checks the new columns,
that existing rows become MANUAL, that plugins backing monitored ports are
enabled so existing monitoring survives, and that it downgrades and upgrades
again cleanly.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).resolve().parents[2]
NEW_COLUMNS = ("Port_Number", "Protocol", "Metric", "Nagios_Service_Name", "Applied_At", "Origin")


@pytest.fixture(scope="module")
def report():
    result = subprocess.run(
        [sys.executable, "tests/support/plugin_config_migration_runner.py"],
        cwd=SERVER_DIR, capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    body = result.stdout.split("REPORT_BEGIN")[1].split("REPORT_END")[0]
    return json.loads(body)


def test_upgrade_reaches_the_new_revision(report):
    assert report["version"] == [["a8c4e1f6b2d3"]]
    assert report["version_after_reupgrade"] == [["a8c4e1f6b2d3"]]


def test_configuration_table_has_the_new_columns(report):
    for column in NEW_COLUMNS:
        assert column in report["config_columns"]


def test_existing_rows_are_manual_and_applied_ones_keep_a_running_since(report):
    applied, pending = report["configs"]
    assert applied[1] == "MANUAL" and pending[1] == "MANUAL"
    assert applied[2] is not None and applied[2].startswith("2026-03-01")
    assert pending[2] is None
    assert applied[3] is None and pending[3] is None


def test_plugins_backing_monitored_ports_are_enabled(report):
    after = report["states_after"]
    assert after["check_ssh"] == "ENABLED"   # port 22, frozen plugin
    assert after["check_http"] == "ENABLED"  # port 443 by service name; was DISABLED
    assert after["check_tcp"] == "ENABLED"   # MISSING port 9100 falls back to the generic plugin
    assert after["check_dns"] == "ENABLED"   # UDP 53


def test_other_plugins_are_left_alone(report):
    after = report["states_after"]
    assert after["check_snmp"] == "READY"                # backs no port
    assert after["check_ftp"] == "READY"                 # only a Suggested port
    assert after["check_udp"] == "READY"                 # discovery skips unmatched UDP
    assert after["check_mysql"] == "VALIDATION_FAILED"   # failure states are not overridden
    assert after["check_ntp_time"] == "ACTIVE"


def test_the_same_service_cannot_be_recorded_twice_for_a_device(report):
    assert report["duplicate_refused"] is True
    assert report["null_names_allowed"] is True


def test_downgrade_removes_only_the_new_columns(report):
    for column in NEW_COLUMNS:
        assert column not in report["config_columns_after_downgrade"]
    # The manual rows stay; the automatic row added before the downgrade does not.
    assert report["configs_after_downgrade"] == [[1], [2]]
