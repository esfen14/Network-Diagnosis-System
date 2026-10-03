"""Nagios validation and controlled service reload helpers."""

from __future__ import annotations

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
