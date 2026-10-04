"""
tests/unit/test_device_migration.py — The device-identity Alembic migration
(migrations/versions/d41f7a2b9e10_device_identity_and_port_lifecycle.py).

Runs the migration on throwaway SQLite files seeded with pre-migration rows
(tests/support/migration_runner.py, in a subprocess), then checks that existing data
keeps its meaning: host names stay what Nagios already uses (so history and
acknowledgements stay attached), ports stay monitored, evidence PinPoint
already had becomes identifiers, constraints are enforced, history.db is not
touched, and the migration downgrades and upgrades again cleanly.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def report():
    result = subprocess.run(
        [sys.executable, "tests/support/migration_runner.py"],
        cwd=SERVER_DIR, capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    body = result.stdout.split("REPORT_BEGIN")[1].split("REPORT_END")[0]
    return json.loads(body)


def test_upgrade_reaches_the_new_revision(report):
    assert report["version"] == [["d41f7a2b9e10"]]
    assert report["version_after_reupgrade"] == [["d41f7a2b9e10"]]


def test_existing_host_names_are_kept_and_made_unique(report):
    names = {row[0]: row[1] for row in report["devices"]}

    # The name Nagios already uses; the duplicate gets a suffix, never merged.
    assert names[1] == "web.test.local"
    assert names[2] == "web.test.local-2"
    # IP-derived names are kept as they are so history.db rows stay attached.
    assert names[3] == "10.0.0.3.test.local"
    # A row without a usable name gets the name the old code would have given it.
    assert names[4] == "10.0.0.4.test.local"


def test_existing_devices_start_active_with_computed_confidence(report):
    by_id = {row[0]: row for row in report["devices"]}

    assert {row[3] for row in report["devices"]} == {"ACTIVE"}
    assert {row[4] for row in report["devices"]} == {"UNKNOWN"}
    assert {row[5] for row in report["devices"]} == {0}
    assert by_id[1][2] == "VERIFIED"      # has an SSH host key fingerprint
    assert by_id[4][2] == "LIKELY"        # hardware MAC only
    assert by_id[2][2] == "UNVERIFIED"    # randomized MAC
    assert by_id[3][2] == "UNVERIFIED"    # nothing
    assert all(row[6] for row in report["devices"])  # First_Seen_At filled


def test_existing_evidence_becomes_identifiers(report):
    identifiers = {(r[0], r[1], r[2], r[3]) for r in report["identifiers"]}

    assert identifiers == {
        (1, "MAC", "00:bb:cc:00:00:01", 1),
        (1, "SSH_HOST_KEY", "FPRINT1", 1),
        (4, "MAC", "00:bb:cc:00:00:04", 1),
    }  # the randomized MAC is not kept


def test_each_device_gets_one_open_address_row(report):
    assert report["addresses"] == [[1, "10.0.0.1", None], [2, "10.0.0.2", None],
                                   [3, "10.0.0.3", None], [4, "10.0.0.4", None]]


def test_ports_stay_monitored_and_duplicates_collapse(report):
    tcp = {(r[0], r[1]): r for r in report["tcp"]}

    assert sorted(tcp) == [(1, 22), (1, 5693), (2, 5693)]
    assert {r[2] for r in report["tcp"]} == {"MONITORED"}
    assert {r[4] for r in report["tcp"]} == {0}
    assert tcp[(1, 5693)][3] == "NCPA"   # device 1 has a deployed token
    assert tcp[(2, 5693)][3] == "SCAN"
    assert tcp[(1, 22)][5] == "ssh"      # Observed_Service_Name starts as the service name
    assert report["udp"] == [[1, 22, "MONITORED"]]


def test_constraints_are_enforced(report):
    errors = report["integrity_errors"]

    assert errors["duplicate_host_name"] and "UNIQUE" in errors["duplicate_host_name"]
    assert errors["duplicate_port"] and "UNIQUE" in errors["duplicate_port"]
    assert errors["duplicate_strong_identifier"] and "UNIQUE" in errors["duplicate_strong_identifier"]


def test_history_database_is_not_changed(report):
    assert report["history_tables"] == [
        "HOST_PERF_DATA", "HOST_STATUS", "PROGRAM_STATUS", "SERVICE_PERF_DATA", "SERVICE_STATUS", "alembic_version"]


def test_downgrade_restores_the_old_schema_and_keeps_devices(report):
    for table in ("DEVICE_IDENTIFIER", "DEVICE_ADDRESS_HISTORY", "DEVICE_REVIEW_ITEM"):
        assert table not in report["tables_after_downgrade"]
    assert "Nagios_Host_Name" not in report["device_columns_after_downgrade"]
    assert "Device_State" not in report["device_columns_after_downgrade"]
    assert [row[0] for row in report["devices_after_downgrade"]] == [1, 2, 3, 4]
