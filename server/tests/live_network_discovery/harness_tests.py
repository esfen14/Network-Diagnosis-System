"""Explicitly invoked unit tests for the live harness; not normal pytest collection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from runner.common import CaseResult, HarnessError, append_result, validate_lab_config, write_checksums
from runner.discovery import compare_inventory, compare_skipped_services
from runner.report import write_report


def sample_config(tmp_path: Path) -> dict:
    """Return a minimal safe harness configuration."""
    return {
        "schema_version": 1,
        "lab_network": "192.168.130.0/28",
        "pinpoint": {"address": "192.168.130.1"},
        "targets": {
            "target01": {
                "address": "192.168.130.2", "expected_tcp_ports": [22, 80],
                "expected_udp_ports": [161],
            }
        },
        "output_root": str(tmp_path / "results"),
    }


def test_rejects_broad_network(tmp_path):
    config = sample_config(tmp_path)
    config["lab_network"] = "192.168.0.0/16"
    with pytest.raises(HarnessError, match="broader than /28"):
        validate_lab_config(config)


def test_rejects_target_outside_network(tmp_path):
    config = sample_config(tmp_path)
    config["targets"]["target01"]["address"] = "192.168.131.2"
    with pytest.raises(HarnessError, match="outside the lab"):
        validate_lab_config(config)


def test_inventory_comparison(tmp_path):
    config = sample_config(tmp_path)
    inventory = [{
        "address": "192.168.130.2",
        "tcp": [{"port": 22}, {"port": 80}],
        "udp": [{"port": 161}],
    }]
    assert compare_inventory(config, inventory) == []


def test_skipped_service_comparison(tmp_path):
    config = sample_config(tmp_path)
    config["targets"]["target01"]["expected_skipped_udp_ports"] = [69]
    skipped = [{"IP_Address": "192.168.130.2", "Port_Number": 69, "Protocol": "UDP"}]
    assert compare_skipped_services(config, skipped) == []


def test_report_and_checksums(tmp_path):
    config = sample_config(tmp_path)
    run_dir = tmp_path / "run"
    (run_dir / "evidence").mkdir(parents=True)
    append_result(run_dir, CaseResult("ND-01", "Pass", "Worked"))
    report = write_report(run_dir, config, "abc123")
    checksum = write_checksums(run_dir)
    assert "ND-01" in report.read_text(encoding="utf-8")
    assert "Network_Discovery_Extended_Test_Report.md" in checksum.read_text(encoding="utf-8")
