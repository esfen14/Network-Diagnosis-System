"""
tests/unit/test_port_service_map_migration.py — The Port -> Service map
migration (migrations/versions/b9d5f2a7c3e4_port_service_map.py).

Runs the migration on throwaway SQLite files (in a subprocess, see
tests/support/port_service_map_migration_runner.py) with both old tables
populated, and checks the merge (the "always treat port as" entry wins), the
new mismatch columns, and that it downgrades and upgrades again cleanly.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).resolve().parents[2]
OLD_COLUMNS = ("TCP_Service_Overrides", "UDP_Service_Overrides", "TCP_Forced_Services", "UDP_Forced_Services")
MISMATCH_COLUMNS = ("Expected_Service_Name", "Mismatch_Acknowledged_At")


@pytest.fixture(scope="module")
def report():
    result = subprocess.run(
        [sys.executable, "tests/support/port_service_map_migration_runner.py"],
        cwd=SERVER_DIR, capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    body = result.stdout.split("REPORT_BEGIN")[1].split("REPORT_END")[0]
    return json.loads(body)


def test_upgrade_reaches_the_new_revision(report):
    assert report["version"] == [["b9d5f2a7c3e4"]]
    assert report["version_after_reupgrade"] == [["b9d5f2a7c3e4"]]


def test_the_four_old_columns_become_two(report):
    for column in OLD_COLUMNS:
        assert column not in report["settings_columns"]
    assert "TCP_Port_Services" in report["settings_columns"]
    assert "UDP_Port_Services" in report["settings_columns"]


def test_entries_from_both_tables_are_kept_and_forced_wins(report):
    assert report["tcp_port_services"] == {"22": "sshd", "80": "http", "5693": "ncpa"}
    assert report["udp_port_services"] == {"161": "snmp"}


def test_other_settings_are_untouched(report):
    assert report["settings_kept"] == [['["10.0.0.0/24"]', 3]]


def test_never_saved_tables_stay_unsaved(report):
    assert report["unsaved_tables"] == [None, None]


def test_port_tables_have_the_mismatch_columns(report):
    for table, columns in report["port_columns"].items():
        for column in MISMATCH_COLUMNS:
            assert column in columns, (table, column)


def test_downgrade_restores_the_old_columns_with_everything_as_forced(report):
    for column in OLD_COLUMNS:
        assert column in report["settings_columns_after_downgrade"]
    assert "TCP_Port_Services" not in report["settings_columns_after_downgrade"]
    assert report["forced_after_downgrade"] == {"22": "sshd", "80": "http", "5693": "ncpa"}
    assert report["overrides_after_downgrade"] == {}
    for columns in report["port_columns_after_downgrade"].values():
        for column in MISMATCH_COLUMNS:
            assert column not in columns


def test_a_round_trip_keeps_the_table(report):
    assert report["tcp_after_reupgrade"] == {"22": "sshd", "80": "http", "5693": "ncpa"}
