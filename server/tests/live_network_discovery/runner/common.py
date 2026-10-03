"""Shared validation, command, evidence, and result helpers for the live lab."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class HarnessError(RuntimeError):
    """Raised when a live test cannot proceed safely or deterministically."""


@dataclass
class CaseResult:
    """One compact, serializable live-test outcome."""

    test_id: str
    result: str
    summary: str
    plugin: str = ""
    target: str = ""
    service: str = ""
    started_at: str = ""
    completed_at: str = ""
    evidence: list[str] | None = None


ALLOWED_RESULTS = {
    "Pass", "Fail", "Blocked", "Not Applicable",
    "Skipped due to resource limit", "Previously verified",
}


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    """Load and return a JSON object from path."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessError(f"Cannot load JSON configuration {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise HarnessError(f"Configuration {path} must contain a JSON object.")
    return value


def resolve_config_path(config_path: Path, value: str) -> Path:
    """Resolve an absolute or config-relative filesystem value."""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (config_path.parent / path).resolve()
    return path


def validate_lab_config(config: dict[str, Any]) -> ipaddress.IPv4Network:
    """Validate the lab's private CIDR, targets, credentials, and scan scope."""
    if config.get("schema_version") != 1:
        raise HarnessError("lab configuration schema_version must be 1.")
    try:
        network = ipaddress.ip_network(config["lab_network"], strict=True)
    except (KeyError, ValueError) as exc:
        raise HarnessError("lab_network must be a canonical IPv4 CIDR.") from exc
    if not isinstance(network, ipaddress.IPv4Network):
        raise HarnessError("Only IPv4 lab networks are supported.")
    if not network.is_private or network.is_loopback or network.is_multicast:
        raise HarnessError("lab_network must be a private, non-loopback IPv4 network.")
    if network.prefixlen < 28:
        raise HarnessError("Refusing a lab network broader than /28.")

    try:
        pinpoint_address = ipaddress.ip_address(config["pinpoint"]["address"])
        targets = config["targets"]
    except (KeyError, ValueError, TypeError) as exc:
        raise HarnessError("Pinpoint and target addresses are required.") from exc
    if pinpoint_address not in network:
        raise HarnessError("Pinpoint address is outside lab_network.")
    if not isinstance(targets, dict) or not targets:
        raise HarnessError("At least one target is required.")

    seen = {str(pinpoint_address)}
    for name, target in targets.items():
        try:
            address = ipaddress.ip_address(target["address"])
        except (KeyError, ValueError, TypeError) as exc:
            raise HarnessError(f"Target {name} has an invalid address.") from exc
        if address not in network or str(address) in seen:
            raise HarnessError(f"Target {name} is outside the lab or duplicates an address.")
        seen.add(str(address))
        for key in ("expected_tcp_ports", "expected_udp_ports"):
            ports = target.get(key, [])
            if not isinstance(ports, list) or any(
                isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535
                for port in ports
            ):
                raise HarnessError(f"Target {name} has invalid {key}.")
        skipped = target.get("expected_skipped_udp_ports", [])
        if not isinstance(skipped, list) or any(
            isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535
            for port in skipped
        ):
            raise HarnessError(f"Target {name} has invalid expected_skipped_udp_ports.")

    output_root = Path(config.get("output_root", ""))
    if not output_root.is_absolute() or str(output_root) in {"/", "/home", "/tmp"}:
        raise HarnessError("output_root must be a specific absolute directory.")
    return network


def require_environment(config: dict[str, Any]) -> dict[str, str]:
    """Read required secret values from environment variables without logging them."""
    pinpoint = config["pinpoint"]
    names = [pinpoint["email_env"], pinpoint["password_env"]]
    for target in config["targets"].values():
        if target.get("ssh_key_env"):
            names.append(target["ssh_key_env"])
    missing = sorted({name for name in names if not os.environ.get(name)})
    if missing:
        raise HarnessError(f"Missing required environment variables: {', '.join(missing)}")
    return {name: os.environ[name] for name in set(names)}


def make_run_directory(config: dict[str, Any], run_id: str | None = None) -> Path:
    """Create a specific run and evidence directory beneath output_root."""
    safe_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", safe_id):
        raise HarnessError("run_id may contain only letters, digits, dot, underscore, and hyphen.")
    run_dir = Path(config["output_root"]) / safe_id
    (run_dir / "evidence").mkdir(parents=True, exist_ok=False)
    return run_dir


def existing_run_directory(config: dict[str, Any], run_id: str) -> Path:
    """Return an existing validated run directory."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_id):
        raise HarnessError("Invalid run_id.")
    run_dir = Path(config["output_root"]) / run_id
    if not run_dir.is_dir():
        raise HarnessError(f"Run directory does not exist: {run_dir}")
    return run_dir


def run_command(argv: list[str], evidence_path: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """Run an argument-list command, capture output, and write bounded evidence."""
    if not argv or any(not isinstance(item, str) or "\x00" in item for item in argv):
        raise HarnessError("Command arguments must be non-empty strings.")
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        evidence_path.write_text(f"Command failed to execute: {exc}\n", encoding="utf-8")
        raise HarnessError(f"Command failed to execute: {argv[0]}") from exc
    evidence_path.write_text(
        f"exit_code={result.returncode}\n\nSTDOUT\n{result.stdout}\n\nSTDERR\n{result.stderr}",
        encoding="utf-8",
    )
    return result


def append_result(run_dir: Path, result: CaseResult) -> None:
    """Append one case result to the run's JSON Lines result ledger."""
    if result.result not in ALLOWED_RESULTS:
        raise HarnessError(f"Invalid result label: {result.result}")
    ledger = run_dir / "results.jsonl"
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(result), sort_keys=True) + "\n")


def read_results(run_dir: Path) -> list[dict[str, Any]]:
    """Read the result ledger, rejecting malformed rows."""
    ledger = run_dir / "results.jsonl"
    if not ledger.exists():
        return []
    rows = []
    for number, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HarnessError(f"Malformed result ledger line {number}.") from exc
        rows.append(row)
    return rows


def write_checksums(run_dir: Path) -> Path:
    """Write SHA-256 checksums for regular report/evidence files, excluding itself."""
    destination = run_dir / "checksums.sha256"
    lines = []
    for path in sorted(item for item in run_dir.rglob("*") if item.is_file() and item != destination):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(run_dir)}")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination
