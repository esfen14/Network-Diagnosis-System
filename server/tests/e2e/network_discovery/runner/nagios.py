"""Nagios validation and controlled service reload helpers."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .common import HarnessError, run_command


def validate(config: dict[str, Any], evidence: Path) -> None:
    """Run Nagios verification and require an exit code of zero."""
    nagios = config["nagios"]
    result = run_command([nagios["binary"], "-v", nagios["main_config"]], evidence, timeout=120)
    if result.returncode != 0:
        raise HarnessError("Nagios configuration validation failed.")


def reload_service(config: dict[str, Any], evidence: Path) -> None:
    """Reload Nagios non-interactively and require success."""
    service = config["nagios"]["service_name"]
    result = run_command(["sudo", "-n", "systemctl", "reload", service], evidence, timeout=60)
    if result.returncode != 0:
        raise HarnessError("Nagios reload failed.")


def assert_active(config: dict[str, Any], evidence: Path) -> None:
    """Require the Nagios systemd service to be active."""
    service = config["nagios"]["service_name"]
    result = run_command(["systemctl", "is-active", service], evidence, timeout=30)
    if result.returncode != 0 or result.stdout.strip() != "active":
        raise HarnessError("Nagios is not active.")


def verify_services(
    config: dict[str, Any], hostname: str, services: list[dict[str, Any]],
    expected_command: str, checked_after: datetime,
) -> list[dict[str, Any]]:
    """Verify loaded Nagios command/state/execution without exporting command arguments."""
    from .pinpoint import executed_check

    main = Path(config["nagios"]["main_config"])
    try:
        directives = {}
        for line in main.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.strip().partition("=")
            if separator and key == "status_file":
                directives[key] = value.strip()
        if not directives.get("status_file"):
            raise HarnessError("Nagios main configuration has no status_file directive.")
        status_path = Path(directives["status_file"])
        if not status_path.is_absolute():
            status_path = main.parent / status_path
        text = status_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HarnessError("Cannot read Nagios runtime status for acceptance.") from exc

    by_service = {}
    for block in re.findall(r"servicestatus\s*\{(.*?)\}", text, re.S):
        fields = {}
        for line in block.splitlines():
            key, separator, value = line.strip().partition("=")
            if separator and key in {"host_name", "service_description", "check_command", "last_check", "current_state"}:
                fields[key] = value
        if fields.get("host_name") == hostname:
            by_service[fields.get("service_description")] = fields
    evidence = []
    states = {"0": "OK", "1": "WARNING", "2": "CRITICAL", "3": "UNKNOWN"}
    for service in services:
        name = service["service"]
        fields = by_service.get(name, {})
        command = fields.get("check_command", "").split("!", 1)[0]
        if command != expected_command:
            raise HarnessError(f"Nagios {hostname}/{name} does not use the required command.")
        try:
            last_check = int(fields.get("last_check", "0"))
        except ValueError:
            last_check = 0
        state = states.get(fields.get("current_state"))
        if not executed_check(last_check, checked_after) or state != str(service.get("state", "")).upper():
            raise HarnessError(f"Nagios {hostname}/{name} has no fresh execution matching Pinpoint.")
        evidence.append({"hostname": hostname, "service": name, "command": command,
                         "last_check": last_check, "state": state})
    return evidence
