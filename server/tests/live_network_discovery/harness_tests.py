"""Standard-library self-tests for the opt-in live harness."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runner.common import CaseResult, HarnessError, append_result, validate_lab_config, write_checksums
from runner.discovery import compare_inventory, compare_skipped_services
from runner.report import write_report


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


if __name__ == "__main__":
    unittest.main()
