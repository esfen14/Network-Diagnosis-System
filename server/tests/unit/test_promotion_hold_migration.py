"""
tests/unit/test_promotion_hold_migration.py — The port promotion hold migration
(migrations/versions/e9b4c2f7a105_port_promotion_hold.py).

Runs it on throwaway SQLite files (in a subprocess, see
tests/support/promotion_hold_migration_runner.py) with a mix of Suggested, Monitored,
Ignored and Archived ports, flagged and guessed ports, and plugins in several states, and
checks that exactly the ports the first reconcile would otherwise have promoted are held.
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
        [sys.executable, "tests/support/promotion_hold_migration_runner.py"],
        cwd=SERVER_DIR, capture_output=True, text=True, timeout=180,
    )
    assert result.returncode == 0, (result.stdout + result.stderr)[-3000:]
    body = result.stdout.split("REPORT_BEGIN")[1].split("REPORT_END")[0]
    return json.loads(body)


def test_upgrade_reaches_the_new_revision(report):
    assert report["version"] == [["e9b4c2f7a105"]]
    assert report["version_after_reupgrade"] == [["e9b4c2f7a105"]]


def test_both_port_tables_get_the_column(report):
    assert report["columns"] == {"OPEN_TCP_Services": True, "OPEN_UDP_Services": True}


def test_suggested_ports_an_enabled_plugin_would_promote_are_held(report):
    held = report["held"]
    assert ["tcp", 22] in held          # check_ssh is enabled
    assert ["tcp", 80] in held          # pinned by an operator, check_http is Active
    assert ["tcp", 9100] in held        # no plugin of its own, so the enabled generic check_tcp
    assert ["tcp", 8443] in held        # flagged, but the flag was acknowledged
    assert ["udp", 53] in held          # check_dns speaks the protocol
    assert ["udp", 5353] in held        # "domain" is an alias of dns: resolved through the registry


def test_nothing_else_is_held(report):
    assert report["held"] == [["tcp", 22], ["tcp", 80], ["tcp", 8443], ["tcp", 9100], ["udp", 53], ["udp", 5353]]


def test_suggestions_whose_plugin_was_never_enabled_stay_free_to_attach_later(report):
    held = report["held"]
    assert ["tcp", 3306] not in held    # check_mysql is only Ready: enabling it later is the admin's consent
    assert ["udp", 161] not in held     # check_snmp is Disabled


def test_guesses_flagged_ports_and_other_states_are_not_held(report):
    held = report["held"]
    assert ["tcp", 8080] not in held    # only a guess from the port number
    assert ["tcp", 443] not in held     # flagged "not used as intended" and not acknowledged
    for number in (5000, 2222, 2223):   # monitored, ignored, archived
        assert ["tcp", number] not in held
    assert ["udp", 9999] not in held    # no plugin can check that UDP service


def test_nothing_is_held_when_no_plugin_is_enabled(report):
    assert report["held_when_nothing_is_enabled"] == []


def test_downgrade_drops_the_column_and_keeps_every_port(report):
    assert report["columns_after_downgrade"] == {"OPEN_TCP_Services": False, "OPEN_UDP_Services": False}
    assert report["ports_after_downgrade"] == [[10]]
