"""
tests/unit/test_ncpa_results_migration.py — The NCPA deployment results
migration (migrations/versions/e5c1a9d3f7b2_ncpa_deployment_results_and_review.py).

Runs the migration on throwaway SQLite files (in a subprocess, see
tests/support/ncpa_results_migration_runner.py) and checks that it adds the
result table and review columns, keeps existing runs, and downgrades and
upgrades again cleanly.
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
        [sys.executable, "tests/support/ncpa_results_migration_runner.py"],
        cwd=SERVER_DIR, capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    body = result.stdout.split("REPORT_BEGIN")[1].split("REPORT_END")[0]
    return json.loads(body)


def test_upgrade_reaches_the_new_revision(report):
    assert report["version"] == [["e5c1a9d3f7b2"]]
    assert report["version_after_reupgrade"] == [["e5c1a9d3f7b2"]]


def test_result_table_has_every_column(report):
    assert report["result_columns"] == [
        "NCPADeployResultID", "Hostname", "IP_Address", "Outcome", "Error",
        "Started_At", "Completed_At", "NCPADeploymentStatusID", "NetworkDiscoveryID",
    ]
    assert "ix_NCPA_DEPLOYMENT_RESULT_NCPADeploymentStatusID" in report["result_indexes"]
    assert "ix_NCPA_DEPLOYMENT_RESULT_NetworkDiscoveryID" in report["result_indexes"]


def test_existing_runs_are_kept_and_not_reviewed(report):
    assert "Reviewed_At" in report["status_columns"]
    assert "Reviewed_By" in report["status_columns"]
    assert report["existing_run"] == [[1, "SUCCESS", None, None]]


def test_downgrade_removes_only_the_new_schema(report):
    assert "NCPA_DEPLOYMENT_RESULT" not in report["tables_after_downgrade"]
    assert "Reviewed_At" not in report["status_columns_after_downgrade"]
    assert "Reviewed_By" not in report["status_columns_after_downgrade"]
    assert report["run_after_downgrade"] == [[1, "SUCCESS"]]
