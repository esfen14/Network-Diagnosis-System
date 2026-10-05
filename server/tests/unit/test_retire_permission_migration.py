"""
tests/unit/test_retire_permission_migration.py — The migration that retires the
plugin.configure permission
(migrations/versions/d2f6a1c8e507_retire_plugin_configure_permission.py).

Runs it on throwaway SQLite files (in a subprocess, see
tests/support/retire_permission_migration_runner.py) with the permission granted
to two roles, and checks that the permission and its grants go, that other
permissions are untouched, and that it downgrades and upgrades again cleanly.
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
        [sys.executable, "tests/support/retire_permission_migration_runner.py"],
        cwd=SERVER_DIR, capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    body = result.stdout.split("REPORT_BEGIN")[1].split("REPORT_END")[0]
    return json.loads(body)


def test_upgrade_reaches_the_new_revision(report):
    assert report["version"] == [["d2f6a1c8e507"]]
    assert report["version_after_reupgrade"] == [["d2f6a1c8e507"]]


def test_the_permission_and_every_grant_of_it_are_removed(report):
    assert "plugin.configure" in report["permissions_before"]
    assert "plugin.configure" not in report["permissions_after"]
    assert all(permission != "plugin.configure" for _, permission in report["grants_after"])


def test_other_permissions_and_their_grants_are_untouched(report):
    assert report["permissions_after"] == ["plugin.disable", "plugin.enable"]
    assert report["grants_after"] == [["Administrator", "plugin.disable"], ["Administrator", "plugin.enable"]]


def test_downgrade_restores_the_permission_but_not_the_grants(report):
    assert "plugin.configure" in report["permissions_after_downgrade"]
    assert all(permission != "plugin.configure" for _, permission in report["grants_after_downgrade"])


def test_a_round_trip_removes_it_again(report):
    assert "plugin.configure" not in report["permissions_after_reupgrade"]
