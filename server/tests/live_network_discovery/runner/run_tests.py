#!/usr/bin/env python3
"""Command-line entry point for the opt-in live Network Discovery harness."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from runner import discovery, nagios, report
    from runner.common import (
        CaseResult, HarnessError, append_result, existing_run_directory,
        load_json, make_run_directory, require_environment, utc_now,
        validate_lab_config, write_checksums,
    )
    from runner.pinpoint import PinpointClient
else:
    from . import discovery, nagios, report
    from .common import (
        CaseResult, HarnessError, append_result, existing_run_directory,
        load_json, make_run_directory, require_environment, utc_now,
        validate_lab_config, write_checksums,
    )
    from .pinpoint import PinpointClient


def client_from(config: dict, secrets: dict[str, str]) -> PinpointClient:
    """Build and authenticate a client without persisting credentials."""
    pinpoint = config["pinpoint"]
    client = PinpointClient(pinpoint["base_url"])
    client.login(secrets[pinpoint["email_env"]], secrets[pinpoint["password_env"]])
    return client


def cmd_preflight(args, config_path: Path, config: dict) -> int:
    """Perform read-only safety, secret, executable, and path checks."""
    network = validate_lab_config(config)
    secrets = require_environment(config)
    checks = {
        "network": str(network),
        "nagios_binary": Path(config["nagios"]["binary"]).is_file(),
        "nagios_config": Path(config["nagios"]["main_config"]).is_file(),
        "nmap_sudo": Path("/usr/local/bin/nmap-sudo").is_file(),
        "ssh": bool(shutil.which("ssh")),
        "systemctl": bool(shutil.which("systemctl")),
        "database": discovery.resolve_config_path(config_path, config["databases"]["system"]).is_file(),
    }
    if all(value for key, value in checks.items() if key != "network"):
        client = client_from(config, secrets)
        identity = client.get_data("/api/user/me")
        checks["pinpoint_api"] = isinstance(identity, dict)
    else:
        checks["pinpoint_api"] = False
    print(json.dumps(checks, indent=2, sort_keys=True))
    return 0 if all(value for key, value in checks.items() if key != "network") else 1


def cmd_init(args, config: dict) -> int:
    """Create a new result directory after validating the approved config."""
    validate_lab_config(config)
    run_dir = make_run_directory(config, args.run_id)
    append_result(run_dir, CaseResult(
        test_id="TIER1", result="Previously verified",
        summary="Plugin inventory coverage was completed before this live run.",
        started_at=utc_now(), completed_at=utc_now(), evidence=[],
    ))
    print(run_dir.name)
    return 0


def cmd_discover(args, config_path: Path, config: dict) -> int:
    """Run approved discovery, persist evidence, and compare the live inventory."""
    validate_lab_config(config)
    secrets = require_environment(config)
    run_dir = existing_run_directory(config, args.run_id)
    started = utc_now()
    client = client_from(config, secrets)
    try:
        status = discovery.run_discovery(client, config, args.apply_settings)
        status_path = run_dir / "evidence" / "discovery-status.json"
        status_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        inventory = discovery.read_inventory(config_path, config)
        inventory_path = run_dir / "evidence" / "discovered-services.json"
        discovery.write_inventory(inventory_path, inventory)
        errors = discovery.compare_inventory(config, inventory)
        skipped = discovery.read_skipped_services(config_path, config, int(status["id"]))
        skipped_path = run_dir / "evidence" / "skipped-services.json"
        skipped_path.write_text(json.dumps(skipped, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        errors.extend(discovery.compare_skipped_services(config, skipped))
        passed = status.get("status") == "Success" and not errors
        summary = "Discovery matched the approved target manifest." if passed else "; ".join(errors) or str(status)
        append_result(run_dir, CaseResult(
            test_id="ND-LIVE", result="Pass" if passed else "Fail", summary=summary,
            started_at=started, completed_at=utc_now(),
            evidence=[
                str(status_path.relative_to(run_dir)),
                str(inventory_path.relative_to(run_dir)),
                str(skipped_path.relative_to(run_dir)),
            ],
        ))
        print(summary)
        return 0 if passed else 1
    except HarnessError as exc:
        append_result(run_dir, CaseResult(
            test_id="ND-LIVE", result="Blocked", summary=str(exc),
            started_at=started, completed_at=utc_now(), evidence=[],
        ))
        raise


def cmd_nagios(args, config: dict) -> int:
    """Validate Nagios, optionally reload it, and require it to be active."""
    validate_lab_config(config)
    run_dir = existing_run_directory(config, args.run_id)
    started = utc_now()
    validate_path = run_dir / "evidence" / "nagios-validation.txt"
    active_path = run_dir / "evidence" / "nagios-active.txt"
    nagios.validate(config, validate_path)
    evidence = [str(validate_path.relative_to(run_dir))]
    if args.reload:
        reload_path = run_dir / "evidence" / "nagios-reload.txt"
        nagios.reload_service(config, reload_path)
        evidence.append(str(reload_path.relative_to(run_dir)))
    nagios.assert_active(config, active_path)
    evidence.append(str(active_path.relative_to(run_dir)))
    append_result(run_dir, CaseResult(
        test_id="CFG-LIVE", result="Pass", summary="Nagios configuration is valid and the service is active.",
        started_at=started, completed_at=utc_now(), evidence=evidence,
    ))
    return 0


def _find_case(cases: dict, case_id: str) -> dict:
    for case in cases.get("cases", []):
        if case.get("id") == case_id:
            return case
    raise HarnessError(f"Unknown plugin case: {case_id}")


def cmd_service_case(args, config: dict, cases: dict) -> int:
    """Verify visibility, then safely stop/recover an allow-listed remote unit."""
    validate_lab_config(config)
    secrets = require_environment(config)
    run_dir = existing_run_directory(config, args.run_id)
    case = _find_case(cases, args.case_id)
    target = config["targets"][case["target"]]
    hostname = target["hostname"]
    service = case.get("service")
    prefix = case.get("service_prefix")
    timeout = args.timeout
    started = utc_now()
    client = client_from(config, secrets)
    evidence_path = run_dir / "evidence" / f"{case['id']}.json"
    helper = Path(__file__).resolve().parents[1] / "services" / "remote_service.py"

    try:
        initial = client.wait_for_service(hostname, service, prefix, {"OK"}, timeout, 5)
        evidence = {"initial": initial}
        if case.get("visibility_only"):
            outcome = "Pass"
            summary = "Service is visible in Pinpoint; disruptive cycle intentionally omitted."
        else:
            command = [
                sys.executable, str(helper), "--config", str(args.config), "--target", case["target"],
                "--unit", case["remote_unit"], "--action", "stop",
            ]
            if subprocess.run(command, check=False).returncode != 0:
                raise HarnessError(f"Could not stop {case['remote_unit']} on {case['target']}.")
            try:
                failed = client.wait_for_service(
                    hostname, service, prefix, {"WARNING", "CRITICAL", "UNKNOWN"}, timeout, 5,
                )
                evidence["failed"] = failed
            finally:
                command[-1] = "start"
                if subprocess.run(command, check=False).returncode != 0:
                    raise HarnessError(f"Could not restore {case['remote_unit']} on {case['target']}.")
            recovered = client.wait_for_service(hostname, service, prefix, {"OK"}, timeout, 5)
            evidence["recovered"] = recovered
            outcome = "Pass"
            summary = "Pinpoint displayed the live failure and recovery."
        evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        append_result(run_dir, CaseResult(
            test_id=case["id"], result=outcome, summary=summary, plugin=case["plugin"],
            target=case["target"], service=service or prefix or "", started_at=started,
            completed_at=utc_now(), evidence=[str(evidence_path.relative_to(run_dir))],
        ))
        return 0
    except HarnessError as exc:
        append_result(run_dir, CaseResult(
            test_id=case["id"], result="Fail", summary=str(exc), plugin=case.get("plugin", ""),
            target=case.get("target", ""), service=service or prefix or "", started_at=started,
            completed_at=utc_now(), evidence=[],
        ))
        raise


def cmd_finalize(args, config: dict) -> int:
    """Generate the Markdown/CSV reports and checksums for SCP retrieval."""
    run_dir = existing_run_directory(config, args.run_id)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False,
        cwd=Path(__file__).resolve().parents[4],
    ).stdout.strip() or "unknown"
    path = report.write_report(run_dir, config, commit)
    write_checksums(run_dir)
    print(path)
    return 0


def parser() -> argparse.ArgumentParser:
    """Build the harness command-line parser."""
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--config", required=True, type=Path)
    root.add_argument("--cases", type=Path)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight")
    init = commands.add_parser("init-run")
    init.add_argument("--run-id")
    discover_cmd = commands.add_parser("discover")
    discover_cmd.add_argument("--run-id", required=True)
    discover_cmd.add_argument("--apply-settings", action="store_true")
    nagios_cmd = commands.add_parser("nagios-check")
    nagios_cmd.add_argument("--run-id", required=True)
    nagios_cmd.add_argument("--reload", action="store_true")
    service = commands.add_parser("service-case")
    service.add_argument("--run-id", required=True)
    service.add_argument("--case-id", required=True)
    service.add_argument("--timeout", type=int, default=300)
    finalize = commands.add_parser("finalize")
    finalize.add_argument("--run-id", required=True)
    return root


def main() -> int:
    """Dispatch a reviewed, explicitly selected live-harness command."""
    args = parser().parse_args()
    try:
        config = load_json(args.config)
        cases = load_json(args.cases) if args.cases else {"cases": []}
        if args.command == "preflight":
            return cmd_preflight(args, args.config, config)
        if args.command == "init-run":
            return cmd_init(args, config)
        if args.command == "discover":
            return cmd_discover(args, args.config, config)
        if args.command == "nagios-check":
            return cmd_nagios(args, config)
        if args.command == "service-case":
            if not args.cases:
                raise HarnessError("service-case requires --cases.")
            return cmd_service_case(args, config, cases)
        if args.command == "finalize":
            return cmd_finalize(args, config)
        raise HarnessError(f"Unknown command: {args.command}")
    except HarnessError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
