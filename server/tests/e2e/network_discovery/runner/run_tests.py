#!/usr/bin/env python3
"""Command-line entry point for the opt-in live Network Discovery harness."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from runner import discovery, guards, nagios, plugins, report, scenarios
    from runner.common import (
        BlockedError, CaseResult, HarnessError, append_result, existing_run_directory, replace_result,
        load_json, make_run_directory, require_environment, utc_now,
        required_environment_names, validate_lab_config, write_checksums,
    )
    from runner.pinpoint import PinpointClient
else:
    from . import discovery, guards, nagios, plugins, report, scenarios
    from .common import (
        BlockedError, CaseResult, HarnessError, append_result, existing_run_directory, replace_result,
        load_json, make_run_directory, require_environment, utc_now,
        required_environment_names, validate_lab_config, write_checksums,
    )
    from .pinpoint import PinpointClient


def client_from(config: dict, secrets: dict[str, str]) -> PinpointClient:
    """Build and authenticate a client without persisting credentials."""
    pinpoint = config["pinpoint"]
    client = PinpointClient(pinpoint["base_url"])
    client.login(secrets[pinpoint["email_env"]], secrets[pinpoint["password_env"]])
    return client


def _probe(argv: list[str], timeout: int = 30) -> bool:
    """Return whether a read-only command probe exits successfully."""
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, check=False,
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _nmap_sudo_works() -> bool:
    """Run the scan wrapper itself; a file that exists may still be unusable by this account."""
    wrapper = "/usr/local/bin/nmap-sudo"
    return Path(wrapper).is_file() and _probe([wrapper, "--version"], timeout=20)


def _ssh_keys_work(config: dict) -> bool:
    """
    Log in to every target that names a key with strict, pinned host-key
    checking (known_hosts next to the key). Existing key files are not enough:
    the NCPA deployment key exists but is rejected by the test guests.
    """
    checked = 0
    for target in config["targets"].values():
        reference = target.get("ssh_key_env")
        if not reference:
            continue
        key_path = os.environ.get(reference)
        if not key_path:
            return False
        key = Path(key_path)
        known_hosts = key.parent / "known_hosts"
        if not key.is_file() or not known_hosts.is_file():
            return False
        argv = [
            "ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", f"UserKnownHostsFile={known_hosts}", "-o", "ConnectTimeout=5",
            "-i", str(key), f"{target['ssh_user']}@{target['address']}", "true",
        ]
        if not _probe(argv, timeout=20):
            return False
        checked += 1
    return checked > 0


def _readable(path: Path) -> bool:
    """True when the file exists and this account can read it."""
    return path.is_file() and os.access(path, os.R_OK)


def _network_visible(config: dict) -> bool:
    """Confirm the lab CIDR is on a non-default local interface."""
    ip = shutil.which("ip")
    if ip is None:
        return False
    try:
        result = subprocess.run(
            [ip, "-json", "address", "show"], capture_output=True,
            text=True, timeout=15, check=False,
        )
        if result.returncode != 0:
            return False
        interfaces = json.loads(result.stdout)
        routes_result = subprocess.run(
            [ip, "-json", "route", "show"], capture_output=True,
            text=True, timeout=15, check=False,
        )
        if routes_result.returncode != 0:
            return False
        routes = json.loads(routes_result.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return False
    expected_address = config["pinpoint"]["address"]
    expected_prefix = int(config["lab_network"].split("/", 1)[1])
    lab_interfaces = {
        interface.get("ifname")
        for interface in interfaces
        for address in interface.get("addr_info", [])
        if address.get("family") == "inet"
        and address.get("local") == expected_address
        and address.get("prefixlen") == expected_prefix
    }
    if not lab_interfaces:
        return False
    has_lab_route = any(
        route.get("dst") == config["lab_network"] and route.get("dev") in lab_interfaces
        for route in routes
    )
    default_interfaces = {
        route.get("dev") for route in routes if route.get("dst") == "default"
    }
    return has_lab_route and lab_interfaces.isdisjoint(default_interfaces)


def cmd_preflight(args, config_path: Path, config: dict) -> int:
    """Perform read-only safety, secret, executable, and path checks."""
    network = validate_lab_config(config)
    names = required_environment_names(config)
    missing = [name for name in names if not os.environ.get(name)]
    pinpoint = config["pinpoint"]
    api_names = {pinpoint["email_env"], pinpoint["password_env"]}
    api_environment = not any(name in api_names for name in missing)
    ssh_environment = not any(name not in api_names for name in missing)
    nagios_binary = Path(config["nagios"]["binary"])
    nagios_config = Path(config["nagios"]["main_config"])
    checks = {
        "network": str(network),
        "network_interface_visible": _network_visible(config),
        "api_environment": api_environment,
        "ssh_environment": ssh_environment,
        "nagios_binary": nagios_binary.is_file() and os.access(nagios_binary, os.X_OK),
        "nagios_config": nagios_config.is_file() and os.access(nagios_config, os.R_OK),
        "nmap_sudo": _nmap_sudo_works(),
        "ssh": bool(shutil.which("ssh")) and ssh_environment and _ssh_keys_work(config),
        "systemctl": bool(shutil.which("systemctl")),
        "database": discovery.resolve_config_path(config_path, config["databases"]["system"]).is_file(),
    }
    checks["nagios_validation"] = checks["nagios_binary"] and checks["nagios_config"] and _probe(
        [str(nagios_binary), "-v", str(nagios_config)], timeout=120,
    )
    checks["nagios_service_access"] = checks["systemctl"] and _probe(
        ["systemctl", "is-active", config["nagios"]["service_name"]],
    )
    # The app under test must be the checked-out branch: its database sits at the checkout's migration head.
    checks["app_revision"] = guards.app_revision_matches(
        discovery.resolve_config_path(config_path, config["databases"]["system"]),
    )
    checks["localhost_cfg_readable"] = _readable(guards.localhost_config_path(config))
    checks["pinpoint_api"] = False
    checks["status_feed"] = None
    if api_environment:
        try:
            secrets = {name: os.environ[name] for name in api_names}
            client = client_from(config, secrets)
            identity = client.get_data("/api/user/me")
            checks["pinpoint_api"] = isinstance(identity, dict)
            checks["status_feed"] = guards.status_feed_state(client.list_services())
        except HarnessError:
            pass
    checks["missing_environment"] = missing
    hints = []
    if not checks["ssh"]:
        hints.append("SSH failed: PINPOINT_TEST_SSH_KEY must be the dedicated test key, not the NCPA deployment key.")
    if not checks["nagios_binary"]:
        hints.append("Nagios binary is not executable by this account: apply the setfacl commands in the README.")
    if not checks["app_revision"]:
        hints.append("The app database is not at the checkout's migration head: test the branch app on its own port and database.")
    if checks["status_feed"] is False:
        hints.append("Services show no check results: start the app with PINPOINT_SCHEDULER=1 and a Nagios API account; status cases will be Blocked.")
    checks["hints"] = hints
    print(json.dumps(checks, indent=2, sort_keys=True))
    advisory = {"network", "missing_environment", "status_feed", "hints"}
    required = [value for key, value in checks.items() if key not in advisory]
    return 0 if all(required) else 1


def cmd_init(args, config: dict) -> int:
    """Create a new result directory after validating the approved config."""
    validate_lab_config(config)
    run_dir = make_run_directory(config, args.run_id)
    guards.record_localhost_hash(config, run_dir)
    print(run_dir.name)
    return 0


def cmd_discover(args, config_path: Path, config: dict, cases: dict) -> int:
    """Run approved discovery, persist evidence, and compare the live inventory."""
    validate_lab_config(config)
    secrets = require_environment(config)
    run_dir = existing_run_directory(config, args.run_id)
    started = utc_now()
    client = client_from(config, secrets)
    enable_path = run_dir / "evidence" / "plugin-enabling.json"
    enable_evidence = json.loads(enable_path.read_text(encoding="utf-8")) if enable_path.exists() else []
    if not isinstance(enable_evidence, list):
        raise HarnessError("Existing plugin enable evidence must be a list.")
    try:
        names = [case["plugin"] for case in cases.get("cases", [])]
        if not names:
            raise HarnessError("Discovery requires a non-empty reviewed plugin case manifest.")
        try:
            client.enable_plugins(names, enable_evidence)
        finally:
            enable_path.write_text(json.dumps(enable_evidence, indent=2) + "\n", encoding="utf-8")
        baseline = discovery.read_inventory(config_path, config)
        baseline_path = run_dir / "evidence" / "inventory-before-discovery.json"
        discovery.write_inventory(baseline_path, baseline)
        status = discovery.run_discovery(client, config, args.apply_settings)
        status_path = run_dir / "evidence" / "discovery-status.json"
        status_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        inventory = discovery.read_inventory(config_path, config)
        inventory_path = run_dir / "evidence" / "discovered-services.json"
        discovery.write_inventory(inventory_path, inventory)
        errors = discovery.compare_inventory(config, inventory, baseline)
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
                str(enable_path.relative_to(run_dir)),
                str(baseline_path.relative_to(run_dir)),
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
            started_at=started, completed_at=utc_now(),
            evidence=[str(enable_path.relative_to(run_dir))] if enable_path.exists() else [],
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


def cmd_enable_check(args, config: dict) -> int:
    """Enable a plugin and prove the preview equals the result (O-2, F-01)."""
    validate_lab_config(config)
    secrets = require_environment(config)
    run_dir = existing_run_directory(config, args.run_id)
    started = utc_now()
    client = client_from(config, secrets)
    case_id = args.case_id or f"PREVIEW-{args.plugin}"
    evidence_path = run_dir / "evidence" / f"{case_id}.json"
    evidence: dict = {}
    try:
        evidence = plugins.enable_and_verify(client, config, run_dir, args.plugin)
        guards.assert_localhost_unchanged(config, run_dir)
        outcome, summary = "Pass", f"Preview matched the result for {args.plugin}."
    except BlockedError as exc:
        outcome, summary = "Blocked", str(exc)
    except HarnessError as exc:
        outcome, summary = "Fail", str(exc)
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_result(run_dir, CaseResult(
        test_id=case_id, result=outcome, summary=summary, plugin=args.plugin,
        started_at=started, completed_at=utc_now(), evidence=[str(evidence_path.relative_to(run_dir))],
    ))
    print(summary)
    return 0 if outcome == "Pass" else 1


def _find_scenario(manifest: dict, scenario_id: str) -> dict:
    for item in manifest.get("scenarios", []):
        if item.get("id") == scenario_id:
            return item
    raise HarnessError(f"Unknown scenario: {scenario_id}")


def cmd_prepare_rejection(args, config: dict) -> int:
    """Write the NAGIOS_BIN wrapper the REJECT-CONFIG scenario needs, and print its path."""
    validate_lab_config(config)
    run_dir = existing_run_directory(config, args.run_id)
    nagios_config = config["nagios"]
    wrapper = scenarios.write_rejection_wrapper(
        run_dir, scenarios.rejection_flag(run_dir), nagios_config["binary"],
        nagios_config["main_config"], nagios_config["host_config"],
    )
    print(wrapper)
    return 0


def cmd_scenario(args, config_path: Path, config: dict, manifest: dict) -> int:
    """Run (or, with --dry-run, describe) one reviewed scenario and record its result."""
    validate_lab_config(config)
    params = _find_scenario(manifest, args.scenario)
    if args.scenario not in scenarios.SCENARIOS:
        raise HarnessError(f"Scenario {args.scenario} has no implementation.")
    if args.dry_run:
        print(json.dumps({"scenario": args.scenario, "parameters": params,
                          "steps": (scenarios.SCENARIOS[args.scenario].__doc__ or "").strip()}, indent=2))
        return 0
    secrets = require_environment(config)
    run_dir = existing_run_directory(config, args.run_id)
    client = client_from(config, secrets)
    base_url = config["pinpoint"]["base_url"]

    def login(email: str, password: str) -> PinpointClient:
        other = PinpointClient(base_url)
        other.login(email, password)
        return other

    result = scenarios.run_scenario(
        args.scenario, params, client, config, run_dir, scenarios.Fixtures(config_path),
        admin_password=secrets[config["pinpoint"]["password_env"]], login=login,
    )
    append_result(run_dir, result)
    print(f"{result.test_id}: {result.result}: {result.summary}")
    return 0 if result.result == "Pass" else 1


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

    evidence = {}
    try:
        enabling = []
        evidence["plugin_enabling"] = enabling
        client.enable_plugins([case["plugin"]], enabling)
        if case.get("apply_monitoring"):
            raise HarnessError(
                "apply_monitoring was removed: monitoring follows from enabling the plugin. "
                "Delete the key from the case."
            )
        initial_after = datetime.now(timezone.utc)
        expected_command = case.get("expected_check_command")
        if not expected_command:
            raise HarnessError("Service acceptance requires expected_check_command in the reviewed manifest.")
        evidence["plugin_services"] = client.wait_for_plugin_service(
            enabling[0]["id"], service, prefix, timeout, 5,
        )
        try:
            initial = client.wait_for_service(
                hostname, service, prefix, {"OK"}, timeout, 5,
                checked_after=initial_after,
            )
        except BlockedError:
            raise
        except HarnessError:
            # Timed out: tell "no status feed" (Blocked) apart from a real failure.
            client.require_status_feed(enabling[0]["id"], service, prefix)
            raise
        evidence["initial"] = initial
        evidence["nagios_initial"] = nagios.verify_services(config, hostname, initial, expected_command, initial_after)
        if case.get("visibility_only"):
            outcome = "Pass"
            summary = "Service is visible in Pinpoint; disruptive cycle intentionally omitted."
        else:
            command = [
                sys.executable, str(helper), "--config", str(args.config), "--target", case["target"],
                "--unit", case["remote_unit"], "--action", "stop",
            ]
            stopped_after = datetime.now(timezone.utc)
            try:
                if subprocess.run(command, check=False).returncode != 0:
                    raise HarnessError(f"Could not stop {case['remote_unit']} on {case['target']}.")
                failed = client.wait_for_service(
                    hostname, service, prefix, {"WARNING", "CRITICAL"}, timeout, 5,
                    checked_after=stopped_after,
                )
                evidence["failed"] = failed
                evidence["nagios_failed"] = nagios.verify_services(config, hostname, failed, expected_command, stopped_after)
            finally:
                recovered_after = datetime.now(timezone.utc)
                command[-1] = "start"
                if subprocess.run(command, check=False).returncode != 0:
                    raise HarnessError(f"Could not restore {case['remote_unit']} on {case['target']}.")
            recovered = client.wait_for_service(
                hostname, service, prefix, {"OK"}, timeout, 5, checked_after=recovered_after,
            )
            evidence["recovered"] = recovered
            evidence["nagios_recovered"] = nagios.verify_services(config, hostname, recovered, expected_command, recovered_after)
            outcome = "Pass"
            summary = "Pinpoint displayed the live failure and recovery."
        evidence["localhost_cfg_sha256"] = guards.assert_localhost_unchanged(config, run_dir)
        evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        append_result(run_dir, CaseResult(
            test_id=case["id"], result=outcome, summary=summary, plugin=case["plugin"],
            target=case["target"], service=service or prefix or "", started_at=started,
            completed_at=utc_now(), evidence=[str(evidence_path.relative_to(run_dir))],
        ))
        return 0
    except HarnessError as exc:
        evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        append_result(run_dir, CaseResult(
            test_id=case["id"], result="Blocked" if isinstance(exc, BlockedError) else "Fail",
            summary=str(exc), plugin=case.get("plugin", ""),
            target=case.get("target", ""), service=service or prefix or "", started_at=started,
            completed_at=utc_now(), evidence=[str(evidence_path.relative_to(run_dir))],
        ))
        raise


def cmd_finalize(args, config: dict) -> int:
    """Generate the Markdown/CSV reports and checksums for SCP retrieval."""
    run_dir = existing_run_directory(config, args.run_id)
    repository = Path(__file__).resolve().parents[5]
    commit = subprocess.run(
        ["git", "-c", f"safe.directory={repository}", "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False, cwd=repository,
    ).stdout.strip() or "unknown"
    traceability = load_json(args.traceability) if getattr(args, "traceability", None) else None
    if (run_dir / "evidence" / "localhost-cfg.sha256").is_file():
        started = utc_now()
        try:
            guards.assert_localhost_unchanged(config, run_dir)
            outcome, summary = "Pass", "localhost.cfg is identical to the run baseline."
        except BlockedError as exc:
            outcome, summary = "Blocked", str(exc)
        except HarnessError as exc:
            outcome, summary = "Fail", str(exc)
        replace_result(run_dir, CaseResult(
            test_id="O-04", result=outcome, summary=summary, started_at=started, completed_at=utc_now(),
            evidence=["evidence/localhost-cfg.sha256"],
        ))
    path = report.write_report(run_dir, config, commit, traceability)
    write_checksums(run_dir)
    print(path)
    return 0


def parser() -> argparse.ArgumentParser:
    """Build the harness command-line parser."""
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--config", required=True, type=Path)
    root.add_argument("--cases", type=Path)
    root.add_argument("--scenarios", type=Path, help="Reviewed scenario manifest (plugin-scenarios.json).")
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
    prepare = commands.add_parser("prepare-rejection")
    prepare.add_argument("--run-id", required=True)
    scenario_cmd = commands.add_parser("scenario")
    scenario_cmd.add_argument("--run-id")
    scenario_cmd.add_argument("--scenario", required=True)
    scenario_cmd.add_argument("--dry-run", action="store_true")
    enable_check = commands.add_parser("enable-check")
    enable_check.add_argument("--run-id", required=True)
    enable_check.add_argument("--plugin", required=True)
    enable_check.add_argument("--case-id")
    finalize = commands.add_parser("finalize")
    finalize.add_argument("--run-id", required=True)
    finalize.add_argument("--traceability", type=Path, help="Objective-to-case manifest to add to the report.")
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
            return cmd_discover(args, args.config, config, cases)
        if args.command == "nagios-check":
            return cmd_nagios(args, config)
        if args.command == "service-case":
            if not args.cases:
                raise HarnessError("service-case requires --cases.")
            return cmd_service_case(args, config, cases)
        if args.command == "prepare-rejection":
            return cmd_prepare_rejection(args, config)
        if args.command == "scenario":
            if not args.scenarios:
                raise HarnessError("scenario requires --scenarios.")
            if not args.dry_run and not args.run_id:
                raise HarnessError("scenario requires --run-id unless --dry-run is given.")
            return cmd_scenario(args, args.config, config, load_json(args.scenarios))
        if args.command == "enable-check":
            return cmd_enable_check(args, config)
        if args.command == "finalize":
            return cmd_finalize(args, config)
        raise HarnessError(f"Unknown command: {args.command}")
    except HarnessError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
