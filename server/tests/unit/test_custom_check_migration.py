"""
tests/unit/test_custom_check_migration.py — The custom check origin migration
(migrations/versions/b4e8d1a7c629_custom_check_origin.py).

Runs it on throwaway SQLite files (in a subprocess, see
tests/support/custom_check_migration_runner.py) with automatic and manual rows, and checks that
they survive, that a CUSTOM row can then be stored, and that downgrading removes only the CUSTOM rows.
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
        [sys.executable, "tests/support/custom_check_migration_runner.py"],
        cwd=SERVER_DIR, capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, (result.stdout + result.stderr)[-3000:]
    body = result.stdout.split("REPORT_BEGIN")[1].split("REPORT_END")[0]
    return json.loads(body)


def test_upgrade_reaches_the_new_revision(report):
    assert report["version"] == [["b4e8d1a7c629"]]
    assert report["version_after_reupgrade"] == [["b4e8d1a7c629"]]


def test_existing_rows_keep_their_origin_and_a_custom_row_can_be_stored(report):
    assert report["origins_after_upgrade"] == [["AUTO"], ["MANUAL"]]
    assert report["origins_with_custom"] == [["AUTO"], ["MANUAL"], ["CUSTOM"]]


def test_the_one_service_per_name_rule_survives(report):
    assert report["unique_constraint_kept"] is True


def test_downgrade_removes_only_the_custom_rows(report):
    assert report["version_after_downgrade"] == [["f3a8c1d6b2e9"]]
    assert report["origins_after_downgrade"] == [["AUTO"], ["MANUAL"]]
    assert report["origins_after_reupgrade"] == [["AUTO"], ["MANUAL"]]
