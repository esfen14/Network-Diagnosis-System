"""
tests/unit/test_custom_checks_config_structure.py — the host file with every kind of custom check.

Nagios itself is not run. This renders the whole file with a device check, a ping check, a check with
a password, and server checks, and checks what `nagios -v` would trip over: unbalanced braces, a service
whose command is not defined, a command defined twice, unfilled $ARGn$ placeholders in a service, and
a host or service name used twice.
"""
import re
from unittest.mock import patch

import pytest

from app import db
from app.network_discovery.create_host_cfg import _create_host_cfg_file, _load_monitored_hosts
from app.plugin_models import (
    Plugin, PluginConfiguration, PluginConfigurationOrigin, PluginConfigurationStatus,
    PluginSource, PluginStatus, PluginType,
)
from app import secrets_store
from app.network_discovery import custom_checks
from tests.support.identity_helpers import MAC_1, NET, make_status, run_scan, scan


@pytest.fixture
def status(db_session, admin_user):
    return make_status(db_session, admin_user)


def plugin(name):
    row = Plugin(Name=name, Plugin_Type=PluginType.NAGIOS, Source=PluginSource.BASELINE_ISO, Status=PluginStatus.READY)
    db.session.add(row)
    db.session.flush()
    return row


def add_check(name, check_name, variables, device=None, secrets=None):
    row = plugin(name)
    public, secret = custom_checks.split_secrets(name, variables)
    db.session.add(PluginConfiguration(
        PluginID=row.PluginID, NetDiscoveryID=None if device is None else device.NetDiscoveryID,
        Service_Description=check_name, Nagios_Service_Name=custom_checks.service_name(name, check_name),
        Origin=PluginConfigurationOrigin.CUSTOM, Status=PluginConfigurationStatus.APPLIED,
        Configuration_Data={"variables": public, "secrets": {k: secrets_store.encrypt(v) for k, v in secret.items()},
                            "paused": False},
    ))


def blocks(text, kind):
    return re.findall(r"define %s \{(.*?)\n\s*\}" % kind, text, flags=re.S)


def field(block, key):
    match = re.search(r"^\s*%s\s+(.+?)\s*$" % key, block, flags=re.M)
    return match.group(1) if match else None


def test_the_whole_file_is_consistent(app, db_session, status, tmp_path):
    device = run_scan(db, status, scan("10.0.0.5", mac=MAC_1, tcp={22: "ssh"}))[(NET, "10.0.0.5")]
    device.Nagios_Host_Name = "rack-01"
    add_check("check_by_ssh", "Disk test", {"command": "/bin/true", "user": "pinpoint-test"}, device)
    add_check("check_ping", "Uplink", {"warning": "100.0,20%", "critical": "500.0,60%"}, device)
    add_check("check_radius", "Auth", {"user": "probe", "password": "Lab-Pw_1", "config": "/etc/radius.conf"}, device)
    add_check("check_apt", "Updates", {"warning": "5"})
    add_check("check_uptime", "Reboot", {})
    add_check("check_file_age", "Backup", {"file": "/var/backups/db.sql", "critical": "90000"})
    db.session.commit()

    original = app.config["HOST_CONFIG_DIR"]
    app.config["HOST_CONFIG_DIR"] = tmp_path
    try:
        text = _create_host_cfg_file(_load_monitored_hosts()).read_text()
    finally:
        app.config["HOST_CONFIG_DIR"] = original

    assert text.count("{") == text.count("}")

    commands = [field(block, "command_name") for block in blocks(text, "command")]
    assert len(commands) == len(set(commands)), "a command is defined twice"
    defined = set(commands)

    services = blocks(text, "service")
    names = [(field(s, "host_name"), field(s, "service_description")) for s in services]
    assert len(names) == len(set(names)), "a service is defined twice on a host"
    for service in services:
        command = field(service, "check_command").split("!")[0]
        assert command in defined, f"{command} is not defined"
        assert "$ARG" not in field(service, "check_command")

    custom = {field(s, "service_description"): s for s in services if field(s, "service_description").startswith(("custom-", "server-"))}
    assert set(custom) == {
        "custom-by_ssh-disk_test", "custom-ping-uplink", "custom-radius-auth",
        "server-apt-updates", "server-uptime-reboot", "server-file_age-backup",
    }
    assert {field(custom[name], "host_name") for name in custom if name.startswith("custom-")} == {"rack-01"}
    assert {field(custom[name], "host_name") for name in custom if name.startswith("server-")} == {"localhost"}

    for command in blocks(text, "command"):
        line = field(command, "command_line")
        assert line.startswith("$USER1$/check_")
        for placeholder in re.findall(r"\$ARG(\d+)\$", line):
            assert int(placeholder) >= 1
        if field(command, "command_name").startswith("pinpoint_custom_check_apt"):
            assert "-H" not in line
        if field(command, "command_name") in ("pinpoint_custom_check_by_ssh", "pinpoint_custom_check_ping"):
            assert "-H $HOSTADDRESS$" in line
    assert "Lab-Pw_1" in text  # Nagios needs it in the command: this is the documented trade-off
    assert "localhost.cfg" not in text
