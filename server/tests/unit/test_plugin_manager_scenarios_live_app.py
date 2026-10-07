"""
tests/unit/test_plugin_manager_scenarios_live_app.py — the e2e Plugin Manager scenarios run against the real app.

The scenarios in tests/e2e/network_discovery/runner/scenarios.py talk to Pinpoint over HTTP. Their own
self-tests use a scripted Pinpoint, which can drift from the real API. Here the real Flask app is served on a
local port, the harness's PinpointClient logs in to it, and the scenarios run unchanged. Only what is outside
the app is replaced: Nagios (the shared writer writes the generated file to a temporary hosts.cfg instead of
validating and reloading it) and the lab fixtures.
"""
import json
import os
import shutil
import sys
import threading
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import sqlalchemy as sa
from werkzeug.serving import make_server

HARNESS = Path(__file__).resolve().parents[1] / "e2e" / "network_discovery"
sys.path.insert(0, str(HARNESS))

from runner import scenarios  # noqa: E402
from runner.pinpoint import PinpointClient  # noqa: E402

from app import db  # noqa: E402
from app.network_discovery.create_host_cfg import _create_host_cfg_file, _load_monitored_hosts  # noqa: E402
from app.plugin_models import (  # noqa: E402
    Plugin, PluginConfiguration, PluginConfigurationOrigin, PluginSource, PluginStatus, PluginType,
)
from tests.support.identity_helpers import MAC_1, NET, make_status, run_scan, scan  # noqa: E402

DEVICE_IP = "192.168.130.2"
ADMIN = ("admin@example.com", "AdminPass1!")
NEW_REGISTRY_PLUGINS = ["check_pgsql", "check_ldap", "check_ldaps", "check_rpc", "check_ircd", "check_time", "check_ntp_peer"]
PLUGIN_NAMES = [
    "check_ssh", "check_ncpa.py", "check_by_ssh", "check_ping", "check_radius", "check_mysql_query", "check_apt",
    "check_uptime", "check_load", "check_dhcp", "check_dbi", "check_cluster", "check_ntp", *NEW_REGISTRY_PLUGINS,
]


@pytest.fixture
def lab(app, db_session, admin_user, tmp_path):
    """The real app on a local port, a device at the lab address, the plugins, and a temporary hosts.cfg."""
    hosts = tmp_path / "hosts.cfg"
    config_dir = tmp_path / "hosts-dir"
    config_dir.mkdir()

    for name in PLUGIN_NAMES:
        db.session.add(Plugin(Name=name, Plugin_Type=PluginType.NAGIOS, Source=PluginSource.BASELINE_ISO,
                              Status=PluginStatus.READY, Category="Agents" if "ncpa" in name else None))
    db.session.commit()
    status = make_status(db_session, admin_user)
    device = run_scan(db, status, scan(DEVICE_IP, mac=MAC_1, tcp={22: "ssh"}))[(NET, DEVICE_IP)]
    device.Nagios_Host_Name = "rack-01"
    db.session.commit()

    def apply():
        """What the shared writer does, minus Nagios: generate the file and make it the live hosts.cfg."""
        generated = _create_host_cfg_file(_load_monitored_hosts())
        shutil.copy(generated, hosts)
        if os.name == "posix":
            hosts.chmod(0o640)
        return "applied", "scripted"

    original_dir = app.config["HOST_CONFIG_DIR"]
    app.config["HOST_CONFIG_DIR"] = config_dir
    apply()
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    with patch("app.api.plugin.custom_checks.regenerate_and_apply_config_status", side_effect=apply), \
            patch("app.api.plugin.reconcile.regenerate_and_apply_config_status", side_effect=apply), \
            patch("app.api.plugin.service.validate_nagios_configuration", return_value=(True, "ok")), \
            patch("runner.scenarios.nagios.validate"):
        try:
            yield {"url": f"http://127.0.0.1:{server.server_port}", "hosts": hosts, "tmp": tmp_path}
        finally:
            server.shutdown()
            thread.join(timeout=5)
            app.config["HOST_CONFIG_DIR"] = original_dir


def make_client(url, email=ADMIN[0], password=ADMIN[1]):
    client = PinpointClient(url)
    client.login(email, password)
    return client


def make_context(lab, client, **params):
    config = {
        "targets": {"target01": {"address": DEVICE_IP}},
        "nagios": {"host_config": str(lab["hosts"])},
        "discovery": {"tcp_ports": [22]},
        "databases": {"system": str(lab["tmp"] / "unused.db")},
    }
    run_dir = lab["tmp"] / "run"
    (run_dir / "evidence").mkdir(parents=True, exist_ok=True)
    return scenarios.Context(client=client, config=config, run_dir=run_dir, params=params, fixtures=Mock(),
                             admin_password=ADMIN[1],
                             login=lambda email, password: make_client(lab["url"], email, password))


def run(scenario, ctx):
    scenario(ctx)
    problems = ctx.run_teardown()
    assert ctx.failures == [], ctx.failures
    assert problems == [], problems


def no_checks_left():
    return db.session.scalar(sa.select(sa.func.count()).select_from(PluginConfiguration).where(
        PluginConfiguration.Origin == PluginConfigurationOrigin.CUSTOM)) == 0


def test_a_device_check_goes_through_the_whole_lifecycle(lab):
    client = make_client(lab["url"])
    ctx = make_context(lab, client, target="target01", plugin="check_by_ssh", name="e2e ssh true",
                       variables={"command": "/bin/true", "user": "pinpoint-test"},
                       expect_state="waiting", status_timeout=0, status_interval=0)
    run(scenarios.custom_device, ctx)
    assert no_checks_left()
    assert "custom-" not in lab["hosts"].read_text()


def test_a_server_check_goes_through_the_whole_lifecycle(lab):
    ctx = make_context(lab, make_client(lab["url"]), target="target01", plugin="check_uptime", name="e2e uptime",
                       variables={}, expect_state="waiting", status_timeout=0, status_interval=0)
    run(scenarios.custom_server, ctx)
    assert no_checks_left()


def test_the_rules_case_agrees_with_the_real_validation(lab):
    ctx = make_context(lab, make_client(lab["url"]), target="target01", device_plugin="check_by_ssh",
                       server_plugin="check_uptime", unsupported_plugin="check_load",
                       variables={"command": "/bin/true"}, name="e2e duplicate")
    run(scenarios.custom_rules, ctx)
    assert no_checks_left()


def test_the_permission_case_agrees_with_the_real_permissions(lab):
    ctx = make_context(lab, make_client(lab["url"]), plugin="check_by_ssh", domain="example.com")
    run(scenarios.custom_permissions, ctx)


def test_the_password_case_agrees_with_the_real_storage(lab, monkeypatch):
    monkeypatch.setenv("E2E_CHECK_PASSWORD", "Lab-Pw_1")

    def stored(ctx, service):
        row = db.session.scalar(sa.select(PluginConfiguration).where(
            PluginConfiguration.Nagios_Service_Name == service, PluginConfiguration.Origin == PluginConfigurationOrigin.CUSTOM))
        return None if row is None else json.dumps(row.Configuration_Data)

    ctx = make_context(lab, make_client(lab["url"]), target="target01", plugin="check_mysql_query", name="e2e password",
                       password_env="E2E_CHECK_PASSWORD", password_field="password", password_required=False,
                       variables={"query": "SELECT 1", "warning": "1", "critical": "2", "user": "pinpoint_e2e"})
    with patch("runner.scenarios._stored_configuration", side_effect=stored):
        run(scenarios.custom_password, ctx)
    assert no_checks_left()
    assert "Lab-Pw_1" not in lab["hosts"].read_text()


def test_the_password_case_with_a_required_password(lab, monkeypatch):
    monkeypatch.setenv("E2E_CHECK_PASSWORD", "Lab-Pw_1")

    def stored(ctx, service):
        row = db.session.scalar(sa.select(PluginConfiguration).where(PluginConfiguration.Nagios_Service_Name == service))
        return None if row is None else json.dumps(row.Configuration_Data)

    ctx = make_context(lab, make_client(lab["url"]), target="target01", plugin="check_radius", name="e2e radius",
                       password_env="E2E_CHECK_PASSWORD", password_field="password", password_required=True,
                       variables={"user": "probe", "config": "/etc/radius.conf"})
    with patch("runner.scenarios._stored_configuration", side_effect=stored):
        run(scenarios.custom_password, ctx)


def test_the_new_registry_plugins_enable_and_disable(lab):
    ctx = make_context(lab, make_client(lab["url"]), plugins=NEW_REGISTRY_PLUGINS)
    run(scenarios.registry_enable, ctx)
    after = {item["name"]: item["status"] for item in make_client(lab["url"]).get_data("/api/plugin?per_page=100")["items"]}
    # Disabling leaves a plugin Disabled (it was Ready before), but never on.
    assert all(after[name] not in {"Enabled", "Active"} for name in NEW_REGISTRY_PLUGINS), after


def test_check_ncpa_stored_as_a_py_file_is_recognised(lab):
    ctx = make_context(lab, make_client(lab["url"]), plugin="check_ncpa", expect_services=False)
    run(scenarios.ncpa_name, ctx)


def test_every_plugin_kind_reports_its_class(lab):
    classes = {"check_ssh": "service", "check_ncpa": "service", "check_by_ssh": "custom", "check_ping": "custom",
               "check_radius": "custom", "check_apt": "server", "check_uptime": "server", "check_load": "stock",
               "check_dhcp": "advanced", "check_dbi": "credentials", "check_cluster": "unsupported", "check_ntp": "replaced"}
    ctx = make_context(lab, make_client(lab["url"]), classes=classes)
    run(scenarios.plugin_classes, ctx)


def test_the_manifest_example_scenarios_have_the_parameters_they_use():
    manifest = json.loads((HARNESS / "config" / "plugin-scenarios.example.json").read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in manifest["scenarios"]}
    assert {"target", "plugin", "name", "variables"} <= set(by_id["CUSTOM-DEVICE"])
    assert {"target", "plugin", "name", "variables"} <= set(by_id["CUSTOM-SERVER"])
    assert {"password_env", "password_field", "variables", "plugin", "target", "name"} <= set(by_id["CUSTOM-PASSWORD"])
    assert set(by_id["REGISTRY-ENABLE"]["plugins"]) == set(NEW_REGISTRY_PLUGINS)
