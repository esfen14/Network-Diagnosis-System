"""
Standard-library self-tests for the Plugin Manager scenarios (custom checks, server checks, passwords,
the new registry plugins, the check_ncpa.py name fix and the plugin classes).

Run like harness_tests.py, from server/:

    python tests/e2e/network_discovery/harness_plugin_manager_tests.py -v

Each scenario is run against a scripted Pinpoint that keeps a hosts.cfg on disk, once behaving as the
product should (the scenario must pass) and once breaking the rule under test (the scenario must say so).
Nothing here touches a lab, Nagios or the network.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_tests import sample_config  # noqa: E402
from runner import scenarios  # noqa: E402
from runner.common import BlockedError, HarnessError  # noqa: E402
from runner.pinpoint import PinpointClient  # noqa: E402

FORBIDDEN = re.compile(r"['\"`!$;\\\n\r]")
PASSWORD = "Lab-Pw_1"

# plugin name -> (id, target, required arguments, all arguments, secret arguments)
PLUGINS = {
    "check_by_ssh": (11, "device", ["command"], ["command", "port", "user", "identity"], []),
    "check_uptime": (12, "server", [], ["warning", "critical"], []),
    "check_radius": (13, "device", ["user", "password", "config"], ["user", "password", "config", "port"], ["password"]),
    "check_load": (14, None, [], [], []),
}


class FakePinpoint:
    """A scripted Pinpoint with a custom check store and a real hosts.cfg file."""

    def __init__(self, hosts: Path, *, status="ok", host_for_server="localhost", keep_on_pause=False,
                 accept_anything=False, leak_password=False, forget_password_on_change=False, mode=0o640):
        self.hosts, self.status, self.host_for_server, self.mode = hosts, status, host_for_server, mode
        self.keep_on_pause, self.accept_anything = keep_on_pause, accept_anything
        self.leak_password, self.forget_password_on_change = leak_password, forget_password_on_change
        self.checks: dict[int, dict] = {}
        self.next_id = 1
        self.enabled: set[str] = set()
        self.write()

    # ---------------------------------------------------------------- the hosts file
    def write(self) -> None:
        blocks = []
        for check in self.checks.values():
            if check["paused"] and not self.keep_on_pause:
                continue
            host = self.host_for_server if check["device"]["id"] is None else check["device"]["hostname"]
            command = f"pinpoint_custom_{check['plugin']}!" + "!".join(
                str(value) for value in {**check["variables"], **check["secrets"]}.values())
            blocks.append(
                f"define service {{\n    host_name                   {host}\n"
                f"    service_description         {check['service']}\n"
                f"    check_command               {command}\n}}\n")
        self.hosts.write_text("\n".join(blocks) + "\n", encoding="utf-8")
        if os.name == "posix":
            # The product keeps the file for the Nagios user and group; the default umask would leave it 0664.
            self.hosts.chmod(self.mode)

    # ---------------------------------------------------------------- inventory
    def plugin_by_name(self, name):
        if name not in PLUGINS and name not in {"check_ssh", "check_ncpa.py", "check_pgsql"}:
            raise HarnessError(f"Required plugin {name} must have exactly one inventory entry.")
        known = PLUGINS.get(name, (50, None, [], [], []))
        return {"id": known[0], "name": name, "status": "Enabled" if name in self.enabled else "Ready"}

    def plugin_matching(self, name):
        stem = name.lower().removesuffix(".py")
        if stem == "check_ncpa":
            return {"id": 50, "name": "check_ncpa.py", "status": "Enabled" if "service" in self.enabled else "Ready"}
        return self.plugin_by_name(name)

    def _meta(self, plugin_id):
        return next((name, meta) for name, meta in PLUGINS.items() if meta[0] == plugin_id)

    def plugin_details(self, plugin_id):
        if plugin_id == 50:
            return {"service_driven": True, "category": "Agents", "status": "Enabled" if "service" in self.enabled else "Ready",
                    "custom_checks": {"class": "service", "supported": False, "target": None, "note": None, "fields": []}}
        name, (_, target, required, allowed, secrets) = self._meta(plugin_id)
        supported = target is not None
        fields = [{"name": f, "required": f in required, "secret": f in secrets} for f in allowed]
        return {"service_driven": False, "category": None, "status": "Ready",
                "custom_checks": {"class": "custom" if target == "device" else "server" if target == "server" else "stock",
                                  "supported": supported, "target": target, "fields": fields,
                                  "note": None if supported else "Checks the Nagios server itself through Nagios Core. Not managed here."}}

    def enable_preview(self, plugin_id):
        return {"service_driven": True, "matched_services": 0}

    def enable_plugin(self, plugin_id):
        self.enabled.add("service")
        return {"auto_apply": {"success": True}, "changed": True}

    def disable_plugin(self, plugin_id):
        self.enabled.discard("service")
        return {}

    def plugin_services(self, plugin_id, search=""):
        return []

    def device_id(self, address):
        return 5

    # ---------------------------------------------------------------- custom checks
    def custom_checks(self, plugin_id, search=""):
        shown = []
        for check in self.checks.values():
            if check["plugin_id"] != plugin_id:
                continue
            item = {key: value for key, value in check.items() if key not in {"secrets", "plugin", "plugin_id"}}
            item["secrets_set"] = sorted(check["secrets"])
            item["secrets_readable"] = True
            if self.leak_password and check["secrets"]:
                item["variables"] = {**check["variables"], **check["secrets"]}
            item["status"] = {"kind": "paused" if check["paused"] else self.status, "output": "scripted"}
            shown.append(item)
        return shown

    def _refusal(self, plugin_id, body):
        if self.accept_anything:
            return None
        name, (_, target, required, allowed, _s) = self._meta(plugin_id)
        if target is None:
            return "does not take custom checks"
        text = str(body.get("name", ""))
        if not text.strip() or len(text) > 60 or "/" in text:
            return "invalid name"
        variables = body.get("variables", {})
        for key, value in variables.items():
            if key not in allowed:
                return f"Unknown argument '{key}'"
            if FORBIDDEN.search(str(value)):
                return f"Variable '{key}' contains a forbidden character."
        for key in required:
            if not str(variables.get(key, "")).strip():
                return f"'{key}' is required."
        device = body.get("device_id")
        if target == "device" and device is None:
            return "Choose a device."
        if target == "server" and device is not None:
            return "takes no device"
        if device is not None and device == 99999999:
            return "Device not found."
        if any(c["plugin_id"] == plugin_id and c["name"] == text and c["device"]["id"] == device for c in self.checks.values()):
            return f"already has a check named '{text}'"
        return None

    def add_custom_check(self, plugin_id, name, variables, device_id=None):
        message = self._refusal(plugin_id, {"name": name, "variables": variables, "device_id": device_id})
        if message:
            raise HarnessError(message)
        plugin, (_, target, _r, _a, secrets) = self._meta(plugin_id)
        short = plugin[len("check_"):]
        prefix = "server" if target == "server" else "custom"
        slug = name.strip().lower().replace(" ", "_")
        device = ({"id": None, "hostname": "Nagios server", "ip_address": ""} if device_id is None
                  else {"id": device_id, "hostname": "rack-01", "ip_address": "10.0.0.5"})
        check = {"id": self.next_id, "plugin": plugin, "plugin_id": plugin_id, "name": name,
                 "service": f"{prefix}-{short}-{slug}", "device": device, "paused": False,
                 "variables": {k: v for k, v in variables.items() if k not in secrets},
                 "secrets": {k: v for k, v in variables.items() if k in secrets}}
        self.next_id += 1
        self.checks[check["id"]] = check
        self.write()
        return {**self.custom_checks(plugin_id)[-1], "changed": True}

    def change_custom_check(self, plugin_id, check_id, name, variables, clear_secrets=None):
        check = self.checks[check_id]
        _n, (_, _t, _r, _a, secrets) = self._meta(plugin_id)
        check["name"] = name
        check["variables"] = {k: v for k, v in variables.items() if k not in secrets}
        for key, value in variables.items():
            if key in secrets and value:
                check["secrets"][key] = value
        if self.forget_password_on_change:
            check["secrets"] = {}
        for key in clear_secrets or []:
            check["secrets"].pop(key, None)
        self.write()
        return {**next(i for i in self.custom_checks(plugin_id) if i["id"] == check_id), "changed": True}

    def pause_custom_check(self, plugin_id, check_id):
        check = self.checks[check_id]
        changed = not check["paused"]
        check["paused"] = True
        self.write()
        return {"paused": True, "changed": changed}

    def resume_custom_check(self, plugin_id, check_id):
        self.checks[check_id]["paused"] = False
        self.write()
        return {"paused": False, "changed": True}

    def remove_custom_check(self, plugin_id, check_id):
        self.checks.pop(check_id, None)
        self.write()
        return {"id": check_id, "changed": True}

    def wait_for_custom_check_status(self, plugin_id, check_id, timeout=420, interval=15):
        return next(item for item in self.custom_checks(plugin_id) if item["id"] == check_id)

    def call(self, method, path, body=None):
        match = re.match(r"/api/plugin/(\d+)(/.*)?$", path)
        if match is None:
            return 404, {}
        plugin_id, rest = int(match.group(1)), match.group(2) or ""
        if rest == "/enable":
            return (409, {}) if plugin_id != 50 else (200, {})
        if rest.startswith("/custom-checks"):
            if method == "POST" and rest == "/custom-checks":
                message = self._refusal(plugin_id, body or {})
                if message:
                    return 400, {"message": message}
                self.add_custom_check(plugin_id, body["name"], body["variables"], body.get("device_id"))
                return 200, {}
            if method == "GET" and "page=0" in path:
                return 400, {}
            if method == "PUT":
                check_id = int(rest.rsplit("/", 1)[1])
                check = self.checks.get(check_id)
                if check is None:
                    return 404, {}
                _n, (_, _t, required, _a, secrets) = self._meta(plugin_id)
                cleared = (body or {}).get("clear_secrets", [])
                if any(key in required for key in cleared):
                    return 400, {"message": "'password' is required."}
                self.change_custom_check(plugin_id, check_id, body["name"], body["variables"], cleared)
                return 200, {}
            if method == "DELETE":
                return (404, {}) if int(rest.rsplit("/", 1)[1]) not in self.checks else (200, {})
        return 404, {}


class PluginManagerScenarioTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.hosts = self.root / "hosts.cfg"
        self.run_dir = self.root / "run"
        (self.run_dir / "evidence").mkdir(parents=True)
        patcher = patch("runner.scenarios.nagios.validate")
        self.validate = patcher.start()
        self.addCleanup(patcher.stop)
        sleeper = patch("runner.scenarios.time.sleep")
        sleeper.start()
        self.addCleanup(sleeper.stop)

    def tearDown(self):
        self.temporary.cleanup()

    def context(self, client, **params):
        config = sample_config(self.root)
        config["nagios"] = {"host_config": str(self.hosts)}
        config["discovery"] = {"tcp_ports": [22]}
        config["databases"] = {"system": str(self.root / "system.db")}
        return scenarios.Context(client=client, config=config, run_dir=self.run_dir, params=params, fixtures=Mock())

    # ---------------------------------------------------------------- helpers: hosts.cfg readers
    def test_service_block_and_command_line_readers(self):
        text = ("define service {\n    host_name                   rack-01\n    service_description         custom-x\n"
                "    check_command               pinpoint_custom_check_x!a!\n}\n\n"
                "define command {\n    command_name    pinpoint_custom_check_x\n    command_line    $USER1$/check_x $ARG1$\n}\n")
        block = scenarios.service_block(text, "custom-x")
        self.assertEqual(scenarios.field_of(block, "host_name"), "rack-01")
        self.assertIsNone(scenarios.service_block(text, "custom-y"))
        self.assertEqual(scenarios.command_line(text, "pinpoint_custom_check_x"), "$USER1$/check_x $ARG1$")
        self.assertIsNone(scenarios.command_line(text, "pinpoint_custom_nope"))

    # ---------------------------------------------------------------- CUSTOM-DEVICE
    def device_params(self):
        return dict(target="target01", plugin="check_by_ssh", name="e2e ssh true", variables={"command": "/bin/true"})

    def test_device_check_lifecycle_passes_and_leaves_nothing_behind(self):
        client = FakePinpoint(self.hosts)
        ctx = self.context(client, **self.device_params())
        scenarios.custom_device(ctx)
        self.assertEqual(ctx.failures, [])
        self.assertEqual(ctx.run_teardown(), [])
        self.assertEqual(client.checks, {})
        self.assertNotIn("custom-", self.hosts.read_text())
        self.assertGreaterEqual(self.validate.call_count, 3)

    def test_device_check_reports_a_paused_check_that_is_still_in_hosts_cfg(self):
        ctx = self.context(FakePinpoint(self.hosts, keep_on_pause=True), **self.device_params())
        scenarios.custom_device(ctx)
        self.assertTrue(any("paused check is still in hosts.cfg" in f for f in ctx.failures), ctx.failures)

    def test_device_check_reports_a_check_that_never_runs_ok(self):
        ctx = self.context(FakePinpoint(self.hosts, status="critical"), **self.device_params())
        scenarios.custom_device(ctx)
        self.assertTrue(any("is critical, expected ok" in f for f in ctx.failures), ctx.failures)

    def test_device_check_may_expect_another_state(self):
        ctx = self.context(FakePinpoint(self.hosts, status="warning"), expect_state="warning", **self.device_params())
        scenarios.custom_device(ctx)
        self.assertEqual(ctx.failures, [])

    def test_device_check_rejects_a_plugin_that_is_not_a_device_plugin(self):
        params = {**self.device_params(), "plugin": "check_uptime"}
        ctx = self.context(FakePinpoint(self.hosts), **params)
        with self.assertRaisesRegex(HarnessError, "does not offer device checks"):
            scenarios.custom_device(ctx)

    def test_a_leftover_check_from_an_earlier_run_is_removed_first(self):
        client = FakePinpoint(self.hosts)
        client.add_custom_check(11, "e2e ssh true", {"command": "/bin/true"}, 5)
        ctx = self.context(client, **self.device_params())
        scenarios.custom_device(ctx)
        self.assertEqual(ctx.failures, [])

    # ---------------------------------------------------------------- CUSTOM-SURVIVES
    def survive_params(self):
        return dict(target="target01", plugin="check_by_ssh", name="e2e ssh survives",
                    variables={"command": "/bin/true"}, port_plugin="check_ssh")

    def test_a_custom_check_survives_a_scan_and_a_port_plugin_toggle(self):
        client = FakePinpoint(self.hosts)
        ctx = self.context(client, **self.survive_params())
        with patch("runner.scenarios.discovery.run_discovery", return_value={"status": "Success"}):
            scenarios.custom_survives(ctx)
        self.assertEqual(ctx.failures, [])
        self.assertEqual(ctx.run_teardown(), [])
        self.assertEqual(client.checks, {})

    def test_a_scan_that_removes_the_check_is_reported(self):
        client = FakePinpoint(self.hosts)
        ctx = self.context(client, **self.survive_params())

        def scan_wipes_checks(*args, **kwargs):
            client.checks.clear()
            client.write()
            return {"status": "Success"}

        with patch("runner.scenarios.discovery.run_discovery", side_effect=scan_wipes_checks):
            scenarios.custom_survives(ctx)
        self.assertTrue(any("a rescan removed the custom check" in f for f in ctx.failures), ctx.failures)

    # ---------------------------------------------------------------- CUSTOM-SERVER
    def server_params(self):
        return dict(target="target01", plugin="check_uptime", name="e2e uptime", variables={})

    def test_server_check_lifecycle_passes(self):
        client = FakePinpoint(self.hosts)
        ctx = self.context(client, **self.server_params())
        scenarios.custom_server(ctx)
        self.assertEqual(ctx.failures, [])
        self.assertEqual(ctx.run_teardown(), [])
        self.assertEqual(client.checks, {})

    def test_server_check_on_the_wrong_host_is_reported(self):
        ctx = self.context(FakePinpoint(self.hosts, host_for_server="rack-01"), **self.server_params())
        scenarios.custom_server(ctx)
        self.assertTrue(any("is on host 'rack-01', expected 'localhost'" in f for f in ctx.failures), ctx.failures)

    def test_server_check_given_a_device_by_the_product_is_reported(self):
        ctx = self.context(FakePinpoint(self.hosts, accept_anything=True), **self.server_params())
        scenarios.custom_server(ctx)
        self.assertTrue(any("with a device returned HTTP 404" in f or "with a device returned HTTP 200" in f
                            for f in ctx.failures), ctx.failures)

    # ---------------------------------------------------------------- CUSTOM-RULES
    def rules_params(self):
        return dict(target="target01", device_plugin="check_by_ssh", server_plugin="check_uptime",
                    unsupported_plugin="check_load", variables={"command": "/bin/true"})

    def test_bad_requests_are_all_refused_and_nothing_changes(self):
        client = FakePinpoint(self.hosts)
        ctx = self.context(client, **self.rules_params())
        scenarios.custom_rules(ctx)
        self.assertEqual(ctx.failures, [])
        self.assertEqual(ctx.run_teardown(), [])
        self.assertEqual(client.checks, {})

    def test_a_product_that_accepts_a_forbidden_character_is_reported(self):
        ctx = self.context(FakePinpoint(self.hosts, accept_anything=True), **self.rules_params())
        scenarios.custom_rules(ctx)
        self.assertTrue(any("forbidden character" in f for f in ctx.failures), ctx.failures)
        self.assertTrue(any("unsupported plugin" in f for f in ctx.failures), ctx.failures)

    # ---------------------------------------------------------------- CUSTOM-PERMISSIONS
    def test_permission_case_blocks_without_the_admin_password(self):
        ctx = self.context(Mock(), plugin="check_by_ssh")
        with self.assertRaises(BlockedError):
            scenarios.custom_permissions(ctx)

    def permission_context(self, viewer_allowed=False):
        def session(allowed_custom):
            user = Mock()

            def call(method, path, body=None):
                if "custom-checks" in path or "custom-check-devices" in path:
                    if not allowed_custom:
                        return 403, {}
                    return (400, {}) if method == "POST" else (200, {})
                if path.endswith("/enable"):
                    return 403, {}
                return 200, {}
            user.call.side_effect = call
            return user

        sessions = {"custom-viewer": session(viewer_allowed), "custom-admin": session(True)}
        manager = Mock()
        manager.accounts = {"custom-viewer": 1, "custom-admin": 2}
        manager.email.side_effect = lambda key: key
        manager.deactivate.return_value = []
        client = Mock()
        client.plugin_by_name.return_value = {"id": 11}
        ctx = self.context(client, plugin="check_by_ssh")
        ctx.admin_password, ctx.login = "secret", lambda email, password: sessions[email]
        return ctx, manager

    def test_only_the_custom_check_permission_opens_the_routes(self):
        ctx, manager = self.permission_context()
        with patch("runner.scenarios.accounts.AccountManager", return_value=manager):
            scenarios.custom_permissions(ctx)
        self.assertEqual(ctx.failures, [])
        self.assertEqual({call.args[0] for call in manager.ensure_role.call_args_list}, {"custom-viewer", "custom-admin"})
        self.assertEqual(ctx.run_teardown(), [])

    def test_a_viewer_who_can_use_custom_checks_is_reported(self):
        ctx, manager = self.permission_context(viewer_allowed=True)
        with patch("runner.scenarios.accounts.AccountManager", return_value=manager):
            scenarios.custom_permissions(ctx)
        self.assertTrue(any("CK-30" in f for f in ctx.failures), ctx.failures)

    # ---------------------------------------------------------------- CUSTOM-PASSWORD
    def password_params(self):
        return dict(target="target01", plugin="check_radius", name="e2e auth", password_env="E2E_TEST_PASSWORD",
                    variables={"user": "probe", "config": "/etc/radius.conf"})

    def make_database(self, plaintext=False):
        path = self.root / "system.db"
        connection = sqlite3.connect(path)
        connection.execute("create table PLUGIN_CONFIGURATION (Nagios_Service_Name text, Origin text, Configuration_Data text)")
        connection.commit()
        connection.close()
        return path

    def run_password(self, client, plaintext=False, password=PASSWORD):
        path = self.make_database()
        original_add = client.add_custom_check
        original_remove = client.remove_custom_check

        def add(plugin_id, name, variables, device_id=None):
            reply = original_add(plugin_id, name, variables, device_id)
            stored = ('{"secrets": {"password": "v1:gAAAAAB"}}' if not plaintext
                      else json.dumps({"secrets": {"password": password}}))
            connection = sqlite3.connect(path)
            connection.execute("insert into PLUGIN_CONFIGURATION values (?, 'CUSTOM', ?)", (reply["service"], stored))
            connection.commit()
            connection.close()
            return reply

        def remove(plugin_id, check_id):
            service = client.checks[check_id]["service"]
            connection = sqlite3.connect(path)
            connection.execute("delete from PLUGIN_CONFIGURATION where Nagios_Service_Name = ?", (service,))
            connection.commit()
            connection.close()
            return original_remove(plugin_id, check_id)

        client.add_custom_check, client.remove_custom_check = add, remove
        ctx = self.context(client, **self.password_params())
        with patch.dict(os.environ, {"E2E_TEST_PASSWORD": password}):
            scenarios.custom_password(ctx)
        return ctx

    def test_password_case_passes_when_it_is_encrypted_and_never_returned(self):
        ctx = self.run_password(FakePinpoint(self.hosts))
        self.assertEqual(ctx.failures, [])
        self.assertNotIn(PASSWORD, json.dumps(ctx.evidence))
        self.assertEqual(ctx.run_teardown(), [])

    @unittest.skipUnless(os.name == "posix", "file modes are only meaningful on POSIX")
    def test_password_case_reports_a_host_file_that_everyone_can_read(self):
        ctx = self.run_password(FakePinpoint(self.hosts, mode=0o644))
        self.assertTrue(any("readable by every user (mode 0o644)" in f for f in ctx.failures), ctx.failures)

    @unittest.skipUnless(os.name == "posix", "file modes are only meaningful on POSIX")
    def test_password_case_records_the_host_file_mode_in_the_evidence(self):
        ctx = self.run_password(FakePinpoint(self.hosts, mode=0o640))
        self.assertEqual(ctx.failures, [])
        self.assertEqual(ctx.evidence.get("hosts_cfg_mode"), "0o640")

    def test_password_case_reports_a_password_in_the_list(self):
        ctx = self.run_password(FakePinpoint(self.hosts, leak_password=True))
        self.assertTrue(any("the list repeats the password" in f for f in ctx.failures), ctx.failures)

    def test_password_case_reports_plain_text_in_the_database(self):
        ctx = self.run_password(FakePinpoint(self.hosts), plaintext=True)
        self.assertTrue(any("plain text" in f for f in ctx.failures), ctx.failures)

    def test_password_case_reports_a_password_dropped_by_a_blank_change(self):
        ctx = self.run_password(FakePinpoint(self.hosts, forget_password_on_change=True))
        self.assertTrue(any("blank password on a change" in f for f in ctx.failures), ctx.failures)

    def test_password_case_blocks_without_the_password_variable(self):
        ctx = self.context(FakePinpoint(self.hosts), **self.password_params())
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("E2E_TEST_PASSWORD", None)
            with self.assertRaisesRegex(BlockedError, "E2E_TEST_PASSWORD"):
                scenarios.custom_password(ctx)

    # ---------------------------------------------------------------- REGISTRY / NCPA / CLASSES
    def test_registry_plugins_are_recognised_and_restored(self):
        client = FakePinpoint(self.hosts)
        ctx = self.context(client, plugins=["check_pgsql"])
        scenarios.registry_enable(ctx)
        self.assertEqual(ctx.failures, [])
        ctx.run_teardown()
        self.assertEqual(client.enabled, set())

    def test_ncpa_stored_as_a_py_file_is_enabled_and_restored(self):
        client = FakePinpoint(self.hosts)
        self.hosts.write_text("define command {\n    command_name    pinpoint_nd_ncpa\n"
                              "    command_line    $USER1$/check_ncpa.py -H $HOSTADDRESS$\n}\n", encoding="utf-8")
        ctx = self.context(client)
        scenarios.ncpa_name(ctx)
        self.assertEqual(ctx.failures, [])
        ctx.run_teardown()
        self.assertEqual(client.enabled, set())

    def test_plugin_classes_match_what_the_drawer_shows(self):
        ctx = self.context(FakePinpoint(self.hosts), classes={
            "check_by_ssh": "custom", "check_uptime": "server", "check_load": "stock", "check_ssh": "service"})
        scenarios.plugin_classes(ctx)
        self.assertEqual(ctx.failures, [])

    def test_a_plugin_in_the_wrong_class_is_reported(self):
        ctx = self.context(FakePinpoint(self.hosts), classes={"check_uptime": "custom"})
        scenarios.plugin_classes(ctx)
        self.assertTrue(any("expected custom" in f for f in ctx.failures), ctx.failures)

    # ---------------------------------------------------------------- the registry and the client
    def test_every_new_scenario_is_registered_and_documented(self):
        for key in ("CUSTOM-DEVICE", "CUSTOM-SURVIVES", "CUSTOM-SERVER", "CUSTOM-RULES", "CUSTOM-PERMISSIONS",
                    "CUSTOM-PASSWORD", "REGISTRY-ENABLE", "NCPA-NAME", "PLUGIN-CLASSES"):
            self.assertIn(key, scenarios.SCENARIOS)
            self.assertTrue((scenarios.SCENARIOS[key].__doc__ or "").strip(), key)

    def test_the_example_manifest_names_only_registered_scenarios(self):
        manifest = json.loads((Path(__file__).parent / "config" / "plugin-scenarios.example.json").read_text(encoding="utf-8"))
        for item in manifest["scenarios"]:
            self.assertIn(item["id"], scenarios.SCENARIOS)
            self.assertTrue(item.get("case_id"), item["id"])
        ids = [item["id"] for item in manifest["scenarios"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_plugin_matching_ignores_a_script_extension(self):
        client = PinpointClient("http://127.0.0.1:5000")
        with patch.object(client, "get_data", return_value={"items": [{"id": 3, "name": "check_ncpa.py"}], "pages": 1}):
            self.assertEqual(client.plugin_matching("check_ncpa")["id"], 3)
            self.assertEqual(client.plugin_matching("CHECK_NCPA.PY")["id"], 3)
        with patch.object(client, "get_data", return_value={"items": [{"id": 3, "name": "check_ssh"}], "pages": 1}):
            with self.assertRaises(HarnessError):
                client.plugin_matching("check_ncpa")

    def test_waiting_for_a_check_polls_until_nagios_has_run_it(self):
        client = PinpointClient("http://127.0.0.1:5000")
        replies = [[{"id": 7, "status": {"kind": "waiting"}}], [{"id": 7, "status": {"kind": "waiting"}}],
                   [{"id": 7, "status": {"kind": "ok"}}]]
        with patch.object(client, "custom_checks", side_effect=replies), patch("runner.pinpoint.time.sleep") as sleep:
            item = client.wait_for_custom_check_status(3, 7, timeout=60, interval=1)
        self.assertEqual(item["status"]["kind"], "ok")
        self.assertEqual(sleep.call_count, 2)

    def test_waiting_returns_the_last_state_when_the_time_runs_out(self):
        client = PinpointClient("http://127.0.0.1:5000")
        with patch.object(client, "custom_checks", return_value=[{"id": 7, "status": {"kind": "waiting"}}]), \
                patch("runner.pinpoint.time.sleep"), patch("runner.pinpoint.time.monotonic", side_effect=[0, 5, 99]):
            item = client.wait_for_custom_check_status(3, 7, timeout=10, interval=1)
        self.assertEqual(item["status"]["kind"], "waiting")

    def test_a_check_that_disappears_while_waiting_is_an_error(self):
        client = PinpointClient("http://127.0.0.1:5000")
        with patch.object(client, "custom_checks", return_value=[]):
            with self.assertRaisesRegex(HarnessError, "no longer listed"):
                client.wait_for_custom_check_status(3, 7)


if __name__ == "__main__":
    unittest.main()
