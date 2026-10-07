"""Standard-library self-tests for the opt-in live harness."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from types import SimpleNamespace
from pathlib import Path

from runner.common import (
    BlockedError, CaseResult, HarnessError, append_result, read_results, validate_lab_config, write_checksums,
)
from runner.discovery import compare_inventory, compare_skipped_services
from runner.report import write_report
from runner.pinpoint import PinpointClient, executed_check
from runner.run_tests import _nmap_sudo_works, _ssh_keys_work, cmd_discover, cmd_service_case
from runner.nagios import verify_services


def sample_config(root: Path) -> dict:
    """Return a minimal safe harness configuration."""
    return {
        "schema_version": 1,
        "lab_network": "192.168.130.0/28",
        "pinpoint": {
            "address": "192.168.130.1",
            "email_env": "PINPOINT_TEST_EMAIL",
            "password_env": "PINPOINT_TEST_PASSWORD",
        },
        "targets": {
            "target01": {
                "address": "192.168.130.2",
                "ssh_key_env": "PINPOINT_TEST_SSH_KEY",
                "expected_tcp_ports": [22, 80],
                "expected_udp_ports": [161],
            }
        },
        "output_root": str(root / "results"),
    }


class HarnessSelfTests(unittest.TestCase):
    """Exercise safety validation, comparison, reporting, and checksums."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_rejects_broad_network(self):
        config = sample_config(self.root)
        config["lab_network"] = "192.168.0.0/16"
        with self.assertRaisesRegex(HarnessError, "broader than /28"):
            validate_lab_config(config)

    def test_rejects_target_outside_network(self):
        config = sample_config(self.root)
        config["targets"]["target01"]["address"] = "192.168.131.2"
        with self.assertRaisesRegex(HarnessError, "outside the lab"):
            validate_lab_config(config)

    def test_rejects_credential_value_without_echoing_it(self):
        config = sample_config(self.root)
        secret = "person@example.invalid"
        config["pinpoint"]["email_env"] = secret
        with self.assertRaises(HarnessError) as caught:
            validate_lab_config(config)
        self.assertNotIn(secret, str(caught.exception))
        self.assertIn("environment-variable name", str(caught.exception))

    def test_accepts_user_relative_output_root(self):
        config = sample_config(self.root)
        config["output_root"] = "~/pinpoint-test-results"
        self.assertEqual(str(validate_lab_config(config)), "192.168.130.0/28")

    def test_inventory_comparison(self):
        config = sample_config(self.root)
        inventory = [{
            "address": "192.168.130.2",
            "tcp": [{"port": 22}, {"port": 80}],
            "udp": [{"port": 161}],
        }]
        self.assertEqual(compare_inventory(config, inventory), [])

    def test_skipped_service_comparison(self):
        config = sample_config(self.root)
        config["targets"]["target01"]["expected_skipped_udp_ports"] = [69]
        skipped = [{"IP_Address": "192.168.130.2", "Port_Number": 69, "Protocol": "UDP"}]
        self.assertEqual(compare_skipped_services(config, skipped), [])

    def test_retained_inventory_and_monitoring_server_are_not_new_targets(self):
        config = sample_config(self.root)
        baseline = [{"address": "192.168.131.15", "tcp": [], "udp": []}]
        inventory = baseline + [
            {"address": "192.168.130.1", "tcp": [], "udp": []},
            {"address": "192.168.130.2", "tcp": [{"port": 22}, {"port": 80}], "udp": [{"port": 161}]},
        ]
        self.assertEqual(compare_inventory(config, inventory, baseline), [])
        inventory.append({"address": "192.168.130.4", "tcp": [], "udp": []})
        self.assertIn("Unexpected discovered addresses", compare_inventory(config, inventory, baseline)[0])

    def test_enable_exact_plugins_once_and_verify_status(self):
        client = PinpointClient("http://example.invalid")
        client.get_data = Mock(side_effect=[
            {"items": [{"id": 9, "name": "check_http_extra", "status": "Ready"}], "pages": 2},
            {"items": [{"id": 2, "name": "check_http", "status": "Ready"}], "pages": 2},
            {"status": "Enabled"},
        ])
        client.request = Mock(return_value={"success": True})
        evidence = []
        client.enable_plugins(["check_http", "check_http"], evidence)
        client.request.assert_called_once_with("POST", "/api/plugin/2/enable")
        self.assertEqual(evidence, [{"id": 2, "name": "check_http", "before": "Ready", "after": "Enabled"}])

    def test_enable_response_must_be_verified(self):
        client = PinpointClient("http://example.invalid")
        client.get_data = Mock(side_effect=[
            {"items": [{"id": 2, "name": "check_http", "status": "Ready"}], "pages": 1},
            {"status": "Disabled"},
        ])
        client.request = Mock(return_value={"success": True})
        with self.assertRaisesRegex(HarnessError, "did not become enabled"):
            client.enable_plugins(["check_http"], [])

    def test_apply_monitoring_flow_is_gone(self):
        self.assertFalse(hasattr(PinpointClient, "apply_monitoring"))

    def test_service_case_rejects_the_removed_apply_flag(self):
        config = sample_config(self.root)
        config["targets"]["target01"]["hostname"] = "target01.test.local"
        run_dir = self.root / "run"
        (run_dir / "evidence").mkdir(parents=True)
        client = Mock()
        client.enable_plugins.side_effect = lambda names, evidence: evidence.append({"id": 2})
        case = {"id": "X", "plugin": "check_http", "target": "target01", "service": "http-80",
                "apply_monitoring": True, "expected_check_command": "pinpoint_nd_http"}
        with patch("runner.run_tests.require_environment", return_value={}), patch(
            "runner.run_tests.existing_run_directory", return_value=run_dir
        ), patch("runner.run_tests.client_from", return_value=client):
            with self.assertRaisesRegex(HarnessError, "apply_monitoring was removed"):
                cmd_service_case(SimpleNamespace(run_id="run", case_id="X", config=self.root / "lab.json",
                                                 timeout=1), config, {"cases": [case]})
        row = read_results(run_dir)[0]
        self.assertEqual((row["test_id"], row["result"]), ("X", "Fail"))
        client.wait_for_plugin_service.assert_not_called()

    def test_service_case_with_no_status_feed_is_blocked_not_failed(self):
        config = sample_config(self.root)
        config["targets"]["target01"]["hostname"] = "target01.test.local"
        run_dir = self.root / "run"
        (run_dir / "evidence").mkdir(parents=True)
        client = Mock()
        client.enable_plugins.side_effect = lambda names, evidence: evidence.append({"id": 2})
        client.wait_for_plugin_service.return_value = [{"service": "http-80"}]
        client.wait_for_service.side_effect = HarnessError("did not reach OK")
        client.require_status_feed.side_effect = BlockedError("every service is waiting")
        case = {"id": "X", "plugin": "check_http", "target": "target01", "service": "http-80",
                "expected_check_command": "pinpoint_nd_http"}
        with patch("runner.run_tests.require_environment", return_value={}), patch(
            "runner.run_tests.existing_run_directory", return_value=run_dir
        ), patch("runner.run_tests.client_from", return_value=client):
            with self.assertRaises(BlockedError):
                cmd_service_case(SimpleNamespace(run_id="run", case_id="X", config=self.root / "lab.json",
                                                 timeout=1), config, {"cases": [case]})
        self.assertEqual(read_results(run_dir)[0]["result"], "Blocked")

    def test_call_returns_status_without_raising_on_http_errors(self):
        from urllib.error import HTTPError
        from io import BytesIO
        client = PinpointClient("http://example.invalid")
        error = HTTPError("http://example.invalid/x", 403, "Forbidden", {}, BytesIO(b'{"success": false}'))
        client.opener = Mock()
        client.opener.open.side_effect = error
        self.assertEqual(client.call("GET", "/x"), (403, {"success": False}))

    def test_plugin_services_reads_every_page(self):
        client = PinpointClient("http://example.invalid")
        client.get_data = Mock(side_effect=[
            {"items": [{"service": "a"}], "pages": 2}, {"items": [{"service": "b"}], "pages": 2},
        ])
        self.assertEqual([i["service"] for i in client.plugin_services(5)], ["a", "b"])

    def test_device_id_matches_the_reported_address_and_skips_missing_ids(self):
        client = PinpointClient("http://example.invalid")
        client.call = Mock(side_effect=[
            (404, {}), (200, {"data": {"device": {"ip_address": "10.0.0.9"}}}),
            (200, {"data": {"device": {"ip_address": "10.0.0.2"}}}),
        ])
        self.assertEqual(client.device_id("10.0.0.2"), 3)
        client.call = Mock(return_value=(404, {}))
        with self.assertRaisesRegex(HarnessError, "No device record"):
            client.device_id("10.0.0.2", search_limit=3)

    def test_wait_for_plugin_service_requires_a_monitored_match(self):
        client = PinpointClient("http://example.invalid")
        client.plugin_services = Mock(side_effect=[
            [{"service": "ssh-22-tcp", "monitored": False}],
            [{"service": "ssh-22-tcp", "monitored": True}],
        ])
        with patch("runner.pinpoint.time.sleep"):
            found = client.wait_for_plugin_service(7, "ssh-22-tcp", None, 30, 1)
        self.assertEqual(len(found), 1)

    def test_status_feed_blocks_only_when_every_service_is_waiting(self):
        client = PinpointClient("http://example.invalid")
        waiting = {"service": "ssh-22-tcp", "status": {"kind": "waiting"}}
        client.plugin_services = Mock(return_value=[waiting])
        with self.assertRaises(BlockedError):
            client.require_status_feed(7, "ssh-22-tcp", None)
        client.plugin_services = Mock(return_value=[waiting, {"service": "ssh-22-tcp", "status": {"kind": "critical"}}])
        client.require_status_feed(7, "ssh-22-tcp", None)

    def test_missing_plugin_never_enables_a_partial_manifest(self):
        client = PinpointClient("http://example.invalid")
        client.get_data = Mock(return_value={"items": [{"id": 2, "name": "check_http", "status": "Ready"}], "pages": 1})
        client.request = Mock()
        with self.assertRaises(HarnessError):
            client.enable_plugins(["check_http", "check_ssh"], [])
        client.request.assert_not_called()

    def test_enable_failure_prevents_discovery(self):
        config = sample_config(self.root)
        run_dir = self.root / "run"
        (run_dir / "evidence").mkdir(parents=True)
        client = Mock()
        client.enable_plugins.side_effect = HarnessError("Enable rejected")
        with patch("runner.run_tests.require_environment", return_value={}), patch(
            "runner.run_tests.existing_run_directory", return_value=run_dir
        ), patch("runner.run_tests.client_from", return_value=client), patch(
            "runner.run_tests.discovery.run_discovery"
        ) as scan:
            with self.assertRaisesRegex(HarnessError, "Enable rejected"):
                cmd_discover(SimpleNamespace(run_id="run", apply_settings=False), self.root / "lab.json",
                             config, {"cases": [{"plugin": "check_http"}]})
            scan.assert_not_called()
        self.assertTrue((run_dir / "evidence" / "plugin-enabling.json").is_file())

    def test_runtime_rejects_fallback_and_exports_no_command_arguments(self):
        status = self.root / "status.dat"
        main = self.root / "nagios.cfg"
        main.write_text(f"status_file={status}\n")
        status.write_text("servicestatus {\nhost_name=device1\nservice_description=mysql-3306\n"
                          "check_command=pinpoint_nd_mysql!3306!private-user!private-secret\n"
                          "last_check=1791028801\ncurrent_state=0\n}\n")
        config = {"nagios": {"main_config": str(main)}}
        services = [{"service": "mysql-3306", "state": "Ok"}]
        after = datetime(2026, 10, 3, 11, tzinfo=timezone.utc)
        evidence = verify_services(config, "device1", services, "pinpoint_nd_mysql", after)
        self.assertNotIn("private-secret", str(evidence))
        self.assertNotIn("private-user", str(evidence))
        status.write_text(status.read_text().replace("pinpoint_nd_mysql", "pinpoint_nd_tcp"))
        with self.assertRaisesRegex(HarnessError, "required command"):
            verify_services(config, "device1", services, "pinpoint_nd_mysql", after)

    def test_pending_and_stale_checks_do_not_count(self):
        after = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
        for value in (None, 0, "1970-01-01T00:00:00", "invalid", "2026-10-03T11:00:00Z"):
            self.assertFalse(executed_check(value, after))
        self.assertTrue(executed_check("2026-10-03T12:00:01", after))

    def test_titlecase_state_requires_executed_check(self):
        client = PinpointClient("http://example.invalid")
        client.list_services = Mock(side_effect=[
            [{"service": "http-80", "state": "Ok", "last_check": None}],
            [{"service": "http-80", "state": "Ok", "last_check": "2026-10-03T12:00:01Z"}],
        ])
        with patch("runner.pinpoint.time.sleep"):
            result = client.wait_for_service("device1", "http-80", None, {"OK"}, 10, 1)
        self.assertEqual(client.list_services.call_count, 2)
        self.assertEqual(result[0]["state"], "Ok")

    def test_report_and_checksums(self):
        config = sample_config(self.root)
        run_dir = self.root / "run"
        (run_dir / "evidence").mkdir(parents=True)
        append_result(run_dir, CaseResult("ND-01", "Pass", "Worked"))
        report = write_report(run_dir, config, "abc123")
        checksum = write_checksums(run_dir)
        self.assertIn("ND-01", report.read_text(encoding="utf-8"))
        self.assertIn(
            "Network_Discovery_Extended_Test_Report.md",
            checksum.read_text(encoding="utf-8"),
        )

    def test_report_title_name_and_traceability_are_configurable(self):
        config = sample_config(self.root)
        config["report_title"] = "Plugin Report"
        config["report_name"] = "Plugin_Report.md"
        run_dir = self.root / "run"
        (run_dir / "evidence").mkdir(parents=True)
        for case_id, result in (("A", "Pass"), ("B", "Pass"), ("C", "Fail"), ("D", "Blocked"), ("E", "Not Applicable")):
            append_result(run_dir, CaseResult(case_id, result, "x"))
        (run_dir / "evidence" / "findings.md").write_text("# findings\n", encoding="utf-8")
        traceability = {"objectives": {
            "O-1": {"title": "all pass", "cases": ["A", "B", "E"]},
            "O-2": {"title": "one failed", "cases": ["A", "C"]},
            "O-3": {"title": "one blocked", "cases": ["A", "D"]},
            "O-4": {"title": "none passed", "cases": ["C", "D"]},
            "O-5": {"title": "unrun", "cases": ["Z"]},
        }, "blocking": ["A", "C"]}
        text = write_report(run_dir, config, "abc123", traceability).read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Plugin Report"))
        self.assertTrue((run_dir / "Plugin_Report.md").is_file())
        self.assertFalse((run_dir / "Network_Discovery_Extended_Test_Report.md").exists())
        for expected in ("| O-1 | all pass | A (Pass), B (Pass), E (Not Applicable) | Met |",
                         "| Not fully met |", "| Partly verified |", "| Not met |",
                         "- A: Pass", "- C: Fail", "evidence/findings.md"):
            self.assertIn(expected, text)
        self.assertEqual(text.count("| Not met |"), 2)

    def test_report_rejects_a_path_as_report_name(self):
        config = sample_config(self.root)
        config["report_name"] = "../escape.md"
        run_dir = self.root / "run"
        (run_dir / "evidence").mkdir(parents=True)
        with self.assertRaises(ValueError):
            write_report(run_dir, config, "abc123")

    def test_default_report_has_no_traceability_section(self):
        config = sample_config(self.root)
        run_dir = self.root / "run"
        (run_dir / "evidence").mkdir(parents=True)
        text = write_report(run_dir, config, "abc123").read_text(encoding="utf-8")
        self.assertIn("# Network Discovery Extended Test Report", text)
        self.assertNotIn("Objective traceability", text)

    def test_localhost_guard_detects_any_change(self):
        from runner import guards
        localhost = self.root / "objects" / "localhost.cfg"
        localhost.parent.mkdir()
        localhost.write_text("define host {}\n")
        config = {"nagios": {"main_config": str(self.root / "nagios.cfg")}}
        run_dir = self.root / "run"
        (run_dir / "evidence").mkdir(parents=True)
        baseline = guards.record_localhost_hash(config, run_dir)
        self.assertEqual(guards.record_localhost_hash(config, run_dir), baseline)
        self.assertEqual(guards.assert_localhost_unchanged(config, run_dir), baseline)
        localhost.write_text("define host {}\n# edited\n")
        with self.assertRaisesRegex(HarnessError, "localhost.cfg changed"):
            guards.assert_localhost_unchanged(config, run_dir)

    def test_unreadable_localhost_config_blocks(self):
        from runner import guards
        config = {"nagios": {"main_config": str(self.root / "nagios.cfg"), "localhost_config": str(self.root / "none.cfg")}}
        with self.assertRaises(BlockedError):
            guards.sha256_of(guards.localhost_config_path(config))

    def test_count_services_and_migration_heads(self):
        from runner import guards
        hosts = self.root / "hosts.cfg"
        hosts.write_text("define service {\n    service_description   ssh-22-tcp\n}\ndefine service {\n"
                         "    service_description   http-80-tcp\n}\ndefine command {\n command_name x\n}\n")
        self.assertEqual(guards.count_services(hosts), 2)
        versions = self.root / "versions"
        versions.mkdir()
        (versions / "a_first.py").write_text("revision = 'aa11'\ndown_revision = None\n")
        (versions / "b_second.py").write_text("revision = 'bb22'\ndown_revision = 'aa11'\n")
        (versions / "c_merge.py").write_text("revision = 'cc33'\ndown_revision = ('bb22', 'aa11')\n")
        self.assertEqual(guards.migration_heads(versions), {"cc33"})
        (versions / "d_fork.py").write_text("revision = 'dd44'\ndown_revision = 'bb22'\n")
        self.assertEqual(guards.migration_heads(versions), {"cc33", "dd44"})
        self.assertFalse(guards.app_revision_matches(self.root / "missing.db", versions))

    def test_app_revision_compares_database_to_the_single_head(self):
        import sqlite3
        from runner import guards
        versions = self.root / "versions"
        versions.mkdir()
        (versions / "a.py").write_text("revision = 'aa11'\ndown_revision = None\n")
        database = self.root / "system.db"
        connection = sqlite3.connect(database)
        connection.execute("create table alembic_version (version_num text)")
        connection.execute("insert into alembic_version values ('aa11')")
        connection.commit()
        self.assertTrue(guards.app_revision_matches(database, versions))
        connection.execute("update alembic_version set version_num = 'old0'")
        connection.commit()
        connection.close()
        self.assertFalse(guards.app_revision_matches(database, versions))

    def test_status_feed_state(self):
        from runner import guards
        self.assertIsNone(guards.status_feed_state([]))
        self.assertFalse(guards.status_feed_state([{"last_check": None}]))
        self.assertTrue(guards.status_feed_state([{"last_check": None}, {"last_check": "2026-10-06T10:00:00"}]))

    def _preview_client(self, listed, preview):
        client = Mock()
        client.plugin_by_name.return_value = {"id": 7}
        client.enable_preview.return_value = preview
        client.enable_plugin.return_value = {"auto_apply": {"success": True}}
        client.plugin_services.return_value = listed
        return client

    def test_enable_and_verify_accepts_matching_counts(self):
        from runner import plugins
        hosts = self.root / "hosts.cfg"
        hosts.write_text("")
        config = {"nagios": {"host_config": str(hosts)}}
        listed = [{"device": {"id": 1}}, {"device": {"id": 2}}]
        client = self._preview_client(listed, {"matched_services": 2, "matched_devices": 2})

        def enable(_id):
            hosts.write_text("service_description a\nservice_description b\n")
            return {"auto_apply": {"success": True}}
        client.enable_plugin.side_effect = enable
        (self.root / "evidence").mkdir()
        with patch("runner.plugins.nagios.validate"):
            evidence = plugins.enable_and_verify(client, config, self.root, "check_ssh")
        self.assertEqual((evidence["listed"], evidence["devices"], evidence["hosts_cfg_delta"]), (2, 2, 2))

    def test_enable_and_verify_reports_every_mismatch(self):
        from runner import plugins
        hosts = self.root / "hosts.cfg"
        hosts.write_text("")
        config = {"nagios": {"host_config": str(hosts)}}
        client = self._preview_client([{"device": {"id": 1}}], {"matched_services": 2, "matched_devices": 2})
        with patch("runner.plugins.nagios.validate"):
            with self.assertRaisesRegex(HarnessError, "preview said 2 services.*preview said 2 devices.*gained 0"):
                plugins.enable_and_verify(client, config, self.root, "check_ssh")

    def test_enable_and_verify_fails_when_nagios_was_not_updated(self):
        from runner import plugins
        client = self._preview_client([], {"matched_services": 1, "matched_devices": 1})
        client.enable_plugin.return_value = {"auto_apply": {"success": False, "message": "Config failed"}}
        with self.assertRaisesRegex(HarnessError, "Nagios was not updated.*Config failed"):
            plugins.enable_and_verify(client, {"nagios": {}}, self.root, "check_ssh")

    def test_finalize_records_the_localhost_guard_and_replaces_it_on_rerun(self):
        from runner.run_tests import cmd_finalize
        localhost = self.root / "objects" / "localhost.cfg"
        localhost.parent.mkdir()
        localhost.write_text("a")
        config = sample_config(self.root)
        config["nagios"] = {"main_config": str(self.root / "nagios.cfg")}
        run_dir = self.root / "run"
        (run_dir / "evidence").mkdir(parents=True)
        from runner import guards
        guards.record_localhost_hash(config, run_dir)
        with patch("runner.run_tests.existing_run_directory", return_value=run_dir):
            cmd_finalize(SimpleNamespace(run_id="run", traceability=None), config)
            localhost.write_text("changed")
            cmd_finalize(SimpleNamespace(run_id="run", traceability=None), config)
        guard_rows = [row for row in read_results(run_dir) if row["test_id"] == "O-04"]
        self.assertEqual([row["result"] for row in guard_rows], ["Fail"])

    # ------------------------------------------------------------ scenarios

    def test_rejection_wrapper_rejects_only_changed_candidates_while_flagged(self):
        from runner import scenarios
        real = self.root / "real-nagios"
        real.write_text("#!/bin/bash\necho REAL-RAN\n")
        real.chmod(0o755)
        main = self.root / "nagios.cfg"
        live = self.root / "hosts.cfg"
        commands = self.root / "commands.cfg"
        live.write_text("define service {}\n")
        commands.write_text("x\n")
        main.write_text(f"cfg_file={commands}\ncfg_file={live}\n")
        candidate = self.root / "host-new.cfg"
        candidate.write_text("define service {}\ndefine service {}\n")
        temp_main = self.root / "temp.cfg"
        run_dir = self.root / "run"
        run_dir.mkdir()
        flag = scenarios.rejection_flag(run_dir)
        wrapper = scenarios.write_rejection_wrapper(run_dir, flag, str(real), str(main), str(live))

        def run(cfg_files):
            temp_main.write_text("".join(f"cfg_file={name}\n" for name in cfg_files))
            return subprocess.run([str(wrapper), "-v", str(temp_main)], capture_output=True, text=True)

        self.assertIn("REAL-RAN", run([commands, candidate]).stdout)      # no flag: always real
        flag.write_text("reject\n")
        rejected = run([commands, candidate])
        self.assertEqual(rejected.returncode, 1)
        self.assertIn("rejected by the test wrapper", rejected.stdout)
        self.assertIn("REAL-RAN", run([commands, live]).stdout)            # the live config still validates
        candidate.write_text("define service {}\n")                        # identical candidate: accepted
        self.assertIn("REAL-RAN", run([commands, candidate]).stdout)

    def test_rejection_wrapper_refuses_unsafe_values(self):
        from runner import scenarios
        with self.assertRaises(HarnessError):
            scenarios.write_rejection_wrapper(self.root, self.root / "f", "/bin/x'; rm -rf /", "m", "l")

    def _context(self, client=None, **params):
        from runner import scenarios
        config = sample_config(self.root)
        config["discovery"] = {"tcp_ports": [22, "80", "8000-9000"]}
        run_dir = self.root / "run"
        (run_dir / "evidence").mkdir(parents=True, exist_ok=True)
        return scenarios.Context(client=client or Mock(), config=config, run_dir=run_dir,
                                 params=params, fixtures=Mock())

    def test_teardown_runs_in_reverse_and_survives_a_failing_cleanup(self):
        ctx = self._context()
        order = []
        ctx.on_cleanup("first", lambda: order.append("first"))
        ctx.on_cleanup("broken", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        ctx.on_cleanup("last", lambda: order.append("last"))
        problems = ctx.run_teardown()
        self.assertEqual(order, ["last", "first"])
        self.assertEqual(len(problems), 1)
        self.assertIn("boom", problems[0])

    def test_require_scanned_accepts_lists_ranges_and_digit_strings_and_blocks_otherwise(self):
        ctx = self._context()
        for port in (22, 80, 8080):
            ctx.require_scanned(port)
        with self.assertRaises(BlockedError):
            ctx.require_scanned(9100)

    def test_run_scenario_always_tears_down_and_reports_failures(self):
        from runner import scenarios
        torn = []

        def failing(ctx):
            ctx.on_cleanup("undo", lambda: torn.append("undone"))
            ctx.check(False, "first problem")
            ctx.check(False, "second problem")

        run_dir = self.root / "run"
        (run_dir / "evidence").mkdir(parents=True)
        localhost = self.root / "objects" / "localhost.cfg"
        localhost.parent.mkdir()
        localhost.write_text("a")
        config = sample_config(self.root)
        config["nagios"] = {"main_config": str(self.root / "nagios.cfg")}
        with patch.dict(scenarios.SCENARIOS, {"T-FAIL": failing}):
            result = scenarios.run_scenario("T-FAIL", {"case_id": "X-1"}, Mock(), config, run_dir, Mock())
        self.assertEqual((result.test_id, result.result), ("X-1", "Fail"))
        self.assertIn("first problem; second problem", result.summary)
        self.assertEqual(torn, ["undone"])
        self.assertTrue((run_dir / "evidence" / "scenario-T-FAIL.json").is_file())

    def test_run_scenario_maps_blocked_and_unknown(self):
        from runner import scenarios

        def blocked(ctx):
            raise BlockedError("prerequisite missing")

        run_dir = self.root / "run"
        (run_dir / "evidence").mkdir(parents=True)
        with patch.dict(scenarios.SCENARIOS, {"T-BLOCK": blocked}):
            result = scenarios.run_scenario("T-BLOCK", {}, Mock(), sample_config(self.root), run_dir, Mock())
        self.assertEqual((result.result, result.summary), ("Blocked", "prerequisite missing"))
        with self.assertRaisesRegex(HarnessError, "Unknown scenario"):
            scenarios.run_scenario("NOPE", {}, Mock(), sample_config(self.root), run_dir, Mock())

    def test_port_held_scenario_against_a_scripted_pinpoint(self):
        from runner import scenarios

        class FakePinpoint:
            def __init__(self):
                self.state, self.held = "MONITORED", False
                self.calls = []

            def plugin_by_name(self, name):
                return {"id": 3, "status": "Ready"}

            def enable_plugin(self, plugin_id):
                self.calls.append("enable")
                return {"auto_apply": {"success": True}, "changed": True}

            def disable_plugin(self, plugin_id):
                self.calls.append("disable")
                return {}

            def device_id(self, address):
                return 5

            def port(self, device, protocol, number):
                reason = {"code": "held"} if self.held else None
                return {"state": self.state, "promotion_held": self.held, "reason": reason, "check_plugin": "check_tcp"}

            def set_port(self, device, protocol, number, body):
                self.state = body["state"]
                self.held = body["state"] == "SUGGESTED"
                return {"config_ok": True}

            def enable_preview(self, plugin_id):
                return {"held_ports": 1 if self.held else 0}

        client = FakePinpoint()
        ctx = self._context(client=client, target="target01", port=22, plugin="check_tcp")
        with patch("runner.scenarios.discovery.run_discovery", return_value={"status": "Success"}):
            scenarios.port_held(ctx)
        self.assertEqual(ctx.failures, [])
        self.assertEqual(ctx.scans, 2)
        self.assertEqual(client.state, "MONITORED")

    def test_port_held_scenario_reports_a_promoted_held_port(self):
        from runner import scenarios

        class PromotesHeldPorts:
            def __init__(self):
                self.state = "MONITORED"

            plugin_by_name = lambda self, name: {"id": 3, "status": "Active"}
            enable_plugin = lambda self, plugin_id: {"auto_apply": {"success": True}}
            disable_plugin = lambda self, plugin_id: {}
            device_id = lambda self, address: 5
            enable_preview = lambda self, plugin_id: {"held_ports": 0}

            def port(self, *args):
                return {"state": self.state, "promotion_held": self.state == "SUGGESTED", "check_plugin": "check_tcp"}

            def set_port(self, device, protocol, number, body):
                self.state = body["state"]
                return {}

            def disable_plugin(self, plugin_id):
                self.state = "MONITORED"      # a buggy product promotes the held port again
                return {}

        ctx = self._context(client=PromotesHeldPorts(), target="target01", port=22, plugin="check_tcp")
        with patch("runner.scenarios.discovery.run_discovery", return_value={"status": "Success"}):
            scenarios.port_held(ctx)
        self.assertTrue(any("promoted a held port" in failure for failure in ctx.failures))

    def test_reject_config_blocks_when_the_app_does_not_use_the_wrapper(self):
        from runner import scenarios
        client = Mock()
        client.plugin_by_name.return_value = {"id": 3, "status": "Active"}
        client.device_id.return_value = 5
        client.set_port.return_value = {"config_ok": True}
        ctx = self._context(client=client, target="target01", port=22, stable_plugin="check_ssh", other_plugin="check_http")
        ctx.config["nagios"] = {"host_config": str(self.root / "hosts.cfg")}
        (self.root / "hosts.cfg").write_text("x")
        with self.assertRaisesRegex(BlockedError, "rejection wrapper"):
            scenarios.reject_config(ctx)
        ctx.run_teardown()
        self.assertFalse(scenarios.rejection_flag(ctx.run_dir).exists())

    def test_remote_fixtures_are_an_allow_list_with_fixed_commands(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent / "services"))
        import remote_service
        from argparse import Namespace
        command = remote_service.remote_command(Namespace(fixture="sshd-80", unit=None, action="start"))
        self.assertEqual(command[:4], ["sudo", "-n", "sh", "-c"])
        self.assertIn("sshd -p 80", command[4])
        for bad in (Namespace(fixture="rm-rf", unit=None, action="start"),
                    Namespace(fixture="sshd-80", unit=None, action="restart"),
                    Namespace(fixture=None, unit="sshd", action="stop")):
            with self.assertRaises(ValueError):
                remote_service.remote_command(bad)

    # ------------------------------------------------------------ permission matrix

    def test_derived_password_is_strong_stable_and_per_account(self):
        from runner import accounts
        first = accounts.derived_password("admin-secret", "a@x.test")
        self.assertEqual(first, accounts.derived_password("admin-secret", "a@x.test"))
        self.assertNotEqual(first, accounts.derived_password("admin-secret", "b@x.test"))
        self.assertNotEqual(first, accounts.derived_password("other", "a@x.test"))
        self.assertTrue(len(first) >= 12 and any(c.isupper() for c in first) and any(c.islower() for c in first)
                        and any(c.isdigit() for c in first) and any(not c.isalnum() for c in first))
        self.assertNotIn("admin-secret", first)

    def _admin(self, roles=None, users=None):
        roles = {} if roles is None else roles
        users = {} if users is None else users
        admin = Mock()
        admin.requests = []

        def get_data(path):
            if path.startswith("/api/user/permissions/options"):
                return {"items": [{"id": i, "name": n} for i, n in enumerate(
                    ["system.hosts", "system.hosts.edit", "plugin.view", "plugin.enable", "plugin.disable"], 1)]}
            if path.startswith("/api/user/roles"):
                return {"items": list(roles.values())}
            if path.startswith("/api/user/accounts"):
                return {"items": list(users.values())}

        def request(method, path, body=None):
            admin.requests.append((method, path, body))
            if method == "POST" and path == "/api/user/roles":
                roles[body["role_name"]] = {"id": len(roles) + 10, "name": body["role_name"]}
            if method == "POST" and path == "/api/user/accounts":
                users[body["email"]] = {"id": len(users) + 20, "email": body["email"]}
            return {"success": True}
        admin.get_data.side_effect = get_data
        admin.request.side_effect = request
        return admin

    def test_account_manager_creates_once_and_reuses_on_the_next_run(self):
        from runner import accounts
        roles, users = {}, {}
        admin = self._admin(roles, users)
        manager = accounts.AccountManager(admin, "lab.test")
        manager.ensure_role("viewer", ["system.hosts"])
        manager.ensure_account("viewer", "admin-secret")
        self.assertEqual([r[0] for r in admin.requests], ["POST", "POST"])
        admin.requests.clear()
        again = accounts.AccountManager(admin, "lab.test")
        again.ensure_role("viewer", ["system.hosts"])
        again.ensure_account("viewer", "admin-secret")
        self.assertEqual([r[0] for r in admin.requests], ["PUT", "PUT"])      # reused, never duplicated
        self.assertEqual(len(roles), 1)
        self.assertEqual(len(users), 1)
        body = admin.requests[0][2]
        self.assertEqual(body["permissions"], [1])

    def test_account_manager_rejects_an_unknown_permission_and_deactivates_everything(self):
        from runner import accounts
        admin = self._admin()
        manager = accounts.AccountManager(admin, "lab.test")
        with self.assertRaisesRegex(HarnessError, "Unknown permissions"):
            manager.ensure_role("viewer", ["no.such.permission"])
        manager.ensure_role("viewer", ["system.hosts"])
        manager.ensure_account("viewer", "admin-secret")
        admin.requests.clear()
        self.assertEqual(manager.deactivate(), [])
        bodies = [r[2] for r in admin.requests]
        self.assertTrue(any(b.get("status") == "Inactive" for b in bodies))
        self.assertTrue(any(b.get("permissions") == [] and b.get("is_active") is False for b in bodies))

    def test_permission_matrix_passes_and_flags_a_wrong_status(self):
        from runner import scenarios

        def make_user(correct):
            def call(method, path, body=None):
                denied = {
                    ("PUT", "ports"): not correct["edit"],
                    ("GET", "plugins"): not correct["plugin_view"],
                    ("POST", "enable"): True,
                    ("POST", "stop"): not correct["stop"],
                    ("POST", "resume"): not correct["resume"],
                }
                kind = ("ports" if "/ports/" in path else "plugins" if path == "/api/plugin" else
                        "enable" if path.endswith("/enable") else "stop" if path.endswith("/stop") else
                        "resume" if path.endswith("/resume") else "read")
                if kind == "read":
                    return 200, {}
                return (403, {}) if denied[(method, kind)] else (200, {})
            user = Mock()
            user.call.side_effect = call
            return user

        users = {
            "viewer": {"edit": False, "plugin_view": False, "stop": False, "resume": False},
            "operator": {"edit": True, "plugin_view": True, "stop": False, "resume": False},
            "enable-only": {"edit": True, "plugin_view": True, "stop": False, "resume": True},
            "disable-only": {"edit": True, "plugin_view": True, "stop": True, "resume": False},
        }
        sessions = {"viewer": make_user(users["viewer"]), "operator": make_user(users["operator"]),
                    "enable-only": make_user(users["enable-only"]), "disable-only": make_user(users["disable-only"])}

        def login(email, password):
            return sessions[email.split("e2e-pdm-")[1].split("@")[0]]

        admin = self._admin()
        base_request = admin.request.side_effect

        def request(method, path, body=None):
            result = base_request(method, path, body)
            # Editing the operator role to the view-only set (no system.hosts.edit = id 2) removes its edit right.
            if method == "PUT" and path.startswith("/api/user/roles/") and body.get("permissions") == [1, 3]:
                users["operator"]["edit"] = False
            return result
        admin.request.side_effect = request
        admin.plugin_by_name.return_value = {"id": 3}
        admin.device_id.return_value = 5
        admin.port.return_value = {"state": "MONITORED"}
        ctx = self._context(client=admin, target="target01", port=22, plugin="check_ssh")
        ctx.admin_password, ctx.login = "admin-secret", login
        scenarios.permissions_matrix(ctx)
        self.assertEqual(len(sessions["operator"].call.call_args_list), 4)
        self.assertEqual(ctx.failures, [])
        ctx.run_teardown()
        # A product that lets the viewer edit ports must be reported.
        sessions["viewer"] = make_user({**users["viewer"], "edit": True})
        bad = self._context(client=admin, target="target01", port=22, plugin="check_ssh")
        bad.admin_password, bad.login = "admin-secret", login
        scenarios.permissions_matrix(bad)
        self.assertTrue(any("viewer cannot change a port" in f for f in bad.failures))

    def test_permission_matrix_blocks_without_the_admin_password(self):
        from runner import scenarios
        ctx = self._context(client=Mock(), target="target01", port=22, plugin="check_ssh")
        with self.assertRaises(BlockedError):
            scenarios.permissions_matrix(ctx)

    def test_enable_and_verify_blocks_when_the_plugin_is_already_enabled(self):
        from runner import plugins
        client = self._preview_client([], {"already_enabled": True, "matched_services": 3, "matched_devices": 2})
        with self.assertRaisesRegex(BlockedError, "already enabled"):
            plugins.enable_and_verify(client, {"nagios": {}}, self.root, "check_ssh")
        client.enable_plugin.assert_not_called()

    def test_scenarios_block_on_stale_port_history_instead_of_failing(self):
        from runner import scenarios
        client = Mock()
        client.plugin_by_name.return_value = {"id": 3, "status": "Active"}
        client.enable_plugin.return_value = {"auto_apply": {"success": True}}
        client.device_id.return_value = 5
        client.port.return_value = {"state": "MONITORED", "check_plugin": "check_http"}
        held = self._context(client=client, target="target01", port=9000, plugin="check_tcp")
        with patch("runner.scenarios.discovery.run_discovery", return_value={"status": "Success"}):
            with self.assertRaisesRegex(BlockedError, "checked by check_http, not check_tcp"):
                scenarios.port_held(held)
        flag = self._context(client=client, target="target01", port=80, plugin="check_ssh", mismatch_fixture="sshd-80",
                             replacement_fixture="http-80", found_service="ssh", expected_service="http")
        with self.assertRaisesRegex(BlockedError, "already MONITORED"):
            scenarios.port_flag(flag)
        flag.fixtures.start.assert_not_called()

    def test_lifecycle_blocks_when_the_port_belongs_to_another_plugin(self):
        from runner import scenarios
        client = Mock()
        client.plugin_by_name.return_value = {"id": 3, "status": "Active"}
        client.enable_plugin.return_value = {"auto_apply": {"success": True}}
        client.device_id.return_value = 5
        client.port.return_value = {"state": "MONITORED", "check_plugin": "check_ssh"}
        ctx = self._context(client=client, target="target01", port=8080, plugin="check_http", fixture="http-8080")
        with patch("runner.scenarios.discovery.run_discovery", return_value={"status": "Success"}):
            with self.assertRaisesRegex(BlockedError, "checked by check_ssh, not check_http"):
                scenarios.port_lifecycle(ctx)

    def test_host_preparation_is_preview_only_by_default(self):
        script = Path(__file__).parent / "provision" / "prepare_test_host.sh"
        result = subprocess.run(
            ["bash", str(script)], capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Preview only", result.stdout)
        self.assertIn("no files, permissions, services", result.stdout)
        self.assertIn("Plugin installation", result.stdout)

    def test_nmap_check_runs_the_wrapper_not_just_finds_it(self):
        with patch("runner.run_tests.Path.is_file", return_value=True), \
             patch("runner.run_tests._probe", return_value=False) as probe:
            self.assertFalse(_nmap_sudo_works())
        self.assertEqual(probe.call_args.args[0], ["/usr/local/bin/nmap-sudo", "--version"])

    def test_ssh_check_logs_in_with_strict_pinned_host_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / "test_key"
            key.write_text("key")
            (Path(directory) / "known_hosts").write_text("hosts")
            config = {"targets": {"target01": {
                "address": "192.168.130.2", "ssh_user": "pinpoint-test", "ssh_key_env": "SELFTEST_KEY"}}}
            with patch.dict("os.environ", {"SELFTEST_KEY": str(key)}):
                with patch("runner.run_tests._probe", return_value=True) as probe:
                    self.assertTrue(_ssh_keys_work(config))
                argv = probe.call_args.args[0]
                self.assertIn("StrictHostKeyChecking=yes", argv)
                self.assertIn("pinpoint-test@192.168.130.2", argv)
                with patch("runner.run_tests._probe", return_value=False):
                    self.assertFalse(_ssh_keys_work(config))

    def test_ssh_check_fails_without_pinned_known_hosts(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / "test_key"
            key.write_text("key")
            config = {"targets": {"target01": {
                "address": "192.168.130.2", "ssh_user": "pinpoint-test", "ssh_key_env": "SELFTEST_KEY"}}}
            with patch.dict("os.environ", {"SELFTEST_KEY": str(key)}), \
                 patch("runner.run_tests._probe", return_value=True) as probe:
                self.assertFalse(_ssh_keys_work(config))
            probe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
