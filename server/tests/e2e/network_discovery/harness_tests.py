"""Standard-library self-tests for the opt-in live harness."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from types import SimpleNamespace
from pathlib import Path

from runner.common import CaseResult, HarnessError, append_result, validate_lab_config, write_checksums
from runner.discovery import compare_inventory, compare_skipped_services
from runner.report import write_report
from runner.pinpoint import PinpointClient, executed_check
from runner.run_tests import cmd_discover
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

    def test_apply_checks_configuration_and_running_target(self):
        client = PinpointClient("http://example.invalid")
        client.request = Mock(return_value={"data": {"success": True, "status": "Applied", "configuration_id": 10}})
        client.get_data = Mock(side_effect=[
            [{"id": 3, "ip_address": "192.168.130.2"}],
            [{"id": 10, "status": "Applied", "target": {"id": 3}, "service_description": "e2e-dummy"}],
            {"items": [{"id": 10, "plugin": {"id": 2}, "target": {"id": 3, "hostname": "device1"}, "service_description": "e2e-dummy"}], "pages": 1},
        ])
        result = client.apply_monitoring(2, "192.168.130.2", "e2e-dummy")
        self.assertEqual(result["hostname"], "device1")
        client.request.assert_called_once_with("POST", "/api/plugin/2/configurations",
                                              {"net_discovery_id": 3, "service_description": "e2e-dummy"})

    def test_apply_rejects_nested_failure_in_successful_http_response(self):
        client = PinpointClient("http://example.invalid")
        client.get_data = Mock(return_value=[{"id": 3, "ip_address": "192.168.130.2"}])
        client.request = Mock(return_value={"success": True, "data": {"success": False, "status": "Failed"}})
        with self.assertRaisesRegex(HarnessError, "not applied"):
            client.apply_monitoring(2, "192.168.130.2", "e2e-dummy")

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

    def test_host_preparation_is_preview_only_by_default(self):
        script = Path(__file__).parent / "provision" / "prepare_test_host.sh"
        result = subprocess.run(
            ["bash", str(script)], capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Preview only", result.stdout)
        self.assertIn("no files, permissions, services", result.stdout)
        self.assertIn("Plugin installation", result.stdout)


if __name__ == "__main__":
    unittest.main()
