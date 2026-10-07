"""Reviewed plugin-driven monitoring scenarios: fixtures, steps, assertions, guaranteed teardown."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import accounts, discovery, guards, nagios
from .common import BlockedError, CaseResult, HarnessError, utc_now
from .pinpoint import PinpointClient

HELPER = Path(__file__).resolve().parents[1] / "services" / "remote_service.py"
REMOVED_ROUTES = (("GET", "/api/plugin/targets"), ("GET", "/api/plugin/running"),
                  ("POST", "/api/plugin/1/configurations"))


class Fixtures:
    """Start and stop allow-listed fixture listeners on a target through remote_service.py."""

    def __init__(self, config_path: Path):
        self.config_path = config_path

    def _run(self, target: str, fixture: str, action: str) -> int:
        command = [sys.executable, "-I", str(HELPER), "--config", str(self.config_path),
                   "--target", target, "--fixture", fixture, "--action", action]
        return subprocess.run(command, check=False).returncode

    def start(self, target: str, fixture: str) -> None:
        if self._run(target, fixture, "start") != 0:
            raise HarnessError(f"Could not start fixture {fixture} on {target}.")
        for _ in range(10):
            if self._run(target, fixture, "is-listening") == 0:
                return
            time.sleep(1)
        raise HarnessError(f"Fixture {fixture} on {target} is not listening.")

    def stop(self, target: str, fixture: str) -> None:
        if self._run(target, fixture, "stop") != 0:
            raise HarnessError(f"Could not stop fixture {fixture} on {target}.")


@dataclass
class Context:
    """Everything a scenario needs; scenarios only talk to Pinpoint and fixtures through it."""

    client: PinpointClient
    config: dict[str, Any]
    run_dir: Path
    params: dict[str, Any]
    fixtures: Any
    failures: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    cleanups: list[tuple[str, Callable[[], None]]] = field(default_factory=list)
    scans: int = 0
    admin_password: str = ""
    login: Callable[[str, str], PinpointClient] | None = None

    def check(self, condition: bool, message: str) -> None:
        """Record a failed assertion and keep going so one run shows every problem."""
        if not condition:
            self.failures.append(message)

    def on_cleanup(self, label: str, action: Callable[[], None]) -> None:
        self.cleanups.append((label, action))

    def device(self, target: str) -> int:
        return self.client.device_id(self.config["targets"][target]["address"])

    def discover(self) -> None:
        """Run one scan and require it to succeed."""
        status = discovery.run_discovery(self.client, self.config, False)
        self.scans += 1
        if status.get("status") != "Success":
            raise HarnessError(f"Discovery did not succeed: {status.get('message')}")

    def require_scanned(self, port: int) -> None:
        """Block when the configured scan would not see a fixture's port."""
        scanned = self.config["discovery"]["tcp_ports"]
        covered = any(
            (isinstance(item, int) and item == port)
            or (isinstance(item, str) and "-" in item and int(item.split("-")[0]) <= port <= int(item.split("-")[1]))
            or (isinstance(item, str) and item.isdigit() and int(item) == port)
            for item in scanned
        )
        if not covered:
            raise BlockedError(f"discovery.tcp_ports does not include {port}; add it to lab.json and apply the settings.")

    def validate_nagios(self, label: str) -> None:
        nagios.validate(self.config, self.run_dir / "evidence" / f"scenario-{label}.txt")

    def enable(self, plugin_name: str) -> int:
        """Enable a plugin if needed and restore its previous state in teardown."""
        plugin = self.client.plugin_by_name(plugin_name)
        was_on = plugin.get("status") in {"Enabled", "Active"}
        outcome = self.client.enable_plugin(plugin["id"])
        apply = outcome.get("auto_apply") or {}
        if apply.get("success") is False:
            raise HarnessError(f"Nagios was not updated after enabling {plugin_name}: {apply.get('message')}")
        if not was_on:
            self.on_cleanup(f"disable {plugin_name}", lambda: self.client.disable_plugin(plugin["id"]))
        return int(plugin["id"])

    def row(self, device: int, protocol: str, port: int) -> dict[str, Any]:
        return self.client.port(device, protocol, port)

    def row_or_none(self, device: int, protocol: str, port: int) -> dict[str, Any] | None:
        try:
            return self.client.port(device, protocol, port)
        except HarnessError:
            return None

    def run_teardown(self) -> list[str]:
        """Run every cleanup in reverse order; one failing cleanup never stops the rest."""
        problems = []
        for label, action in reversed(self.cleanups):
            try:
                action()
            except Exception as exc:  # noqa: BLE001 - teardown must continue and report
                problems.append(f"cleanup '{label}' failed: {exc}")
        self.cleanups.clear()
        return problems


# ---------------------------------------------------------------- scenarios

def port_flag(ctx: Context) -> None:
    """L-03, L-04: a port not used as intended is flagged, acknowledged, and re-checked."""
    p = ctx.params
    target, port = p["target"], int(p["port"])
    ctx.require_scanned(port)
    device = ctx.device(target)
    existing = ctx.row_or_none(device, "tcp", port)
    if existing is not None and existing["state"] != "SUGGESTED":
        raise BlockedError(
            f"tcp/{port} on {target} is already {existing['state']}; the mismatch case needs a port with no monitoring history (use a fresh database).")
    ctx.fixtures.start(target, p["mismatch_fixture"])
    ctx.on_cleanup("stop mismatch fixture", lambda: ctx.fixtures.stop(target, p["mismatch_fixture"]))
    ctx.on_cleanup("stop replacement fixture", lambda: ctx.fixtures.stop(target, p["replacement_fixture"]))
    plugin_id = ctx.enable(p["plugin"])
    ctx.discover()
    row = ctx.row(device, "tcp", port)
    ctx.check(row["service_name"] == p["found_service"], f"port {port} recorded as {row['service_name']}, expected {p['found_service']}")
    ctx.check(row["state"] != "MONITORED", "a mismatched port must not be monitored before acknowledgement")
    ctx.check((row.get("reason") or {}).get("code") == "not_used_as_intended", "reason code is not 'not_used_as_intended'")
    ctx.check(row.get("expected_service_name") == p["expected_service"], f"expected service is {row.get('expected_service_name')}")
    ctx.check(not any(item.get("port") == port for item in ctx.client.plugin_services(plugin_id)),
              "the plugin lists the mismatched port before acknowledgement")
    reply = ctx.client.set_port(device, "tcp", port, {"acknowledge_mismatch": True})
    ctx.check(reply.get("config_ok") is True, f"Nagios was not updated after acknowledging: {reply.get('config_message')}")
    row = ctx.row(device, "tcp", port)
    ctx.check(row["state"] == "MONITORED", "acknowledged port is not monitored")
    ctx.check(any(item.get("port") == port for item in ctx.client.plugin_services(plugin_id)),
              "acknowledged port is not listed by its plugin")
    ctx.validate_nagios("port-flag-acknowledged")
    # L-04: change what is on the port; the acknowledgement must clear and a review item must be raised.
    ctx.fixtures.stop(target, p["mismatch_fixture"])
    ctx.fixtures.start(target, p["replacement_fixture"])
    ctx.discover()
    row = ctx.row(device, "tcp", port)
    ctx.check(row.get("mismatch_acknowledged") is False, "acknowledgement was not cleared after the service changed")
    changed = [i for i in ctx.client.review_items() if i.get("kind") == "SERVICE_CHANGED" and f"tcp/{port}" in str(i.get("message"))]
    ctx.check(bool(changed), "no SERVICE_CHANGED review item for the monitored port")
    ctx.evidence["review_items"] = changed


def port_held(ctx: Context) -> None:
    """L-05: an admin's 'leave suggested' beats automatic promotion everywhere."""
    p = ctx.params
    target, port = p["target"], int(p["port"])
    device = ctx.device(target)
    plugin_id = ctx.enable(p["plugin"])
    ctx.discover()
    before = ctx.row(device, "tcp", port)
    if before.get("check_plugin") != p["plugin"]:
        raise BlockedError(
            f"tcp/{port} on {target} is checked by {before.get('check_plugin')}, not {p['plugin']}; the held-port case needs a port that plugin monitors.")
    ctx.check(before["state"] == "MONITORED", f"port {port} is not monitored before the test")
    ctx.on_cleanup("release held port", lambda: ctx.client.set_port(device, "tcp", port, {"state": "MONITORED"}))
    ctx.client.set_port(device, "tcp", port, {"state": "SUGGESTED"})
    row = ctx.row(device, "tcp", port)
    ctx.check(row["state"] == "SUGGESTED" and row.get("promotion_held") is True, "port is not Suggested and held")
    ctx.check((row.get("reason") or {}).get("code") == "held", "reason code is not 'held'")
    ctx.discover()
    ctx.check(ctx.row(device, "tcp", port)["state"] == "SUGGESTED", "discovery promoted a held port")
    ctx.client.disable_plugin(plugin_id)
    ctx.client.enable_plugin(plugin_id)
    ctx.check(ctx.row(device, "tcp", port)["state"] == "SUGGESTED", "disable/enable promoted a held port")
    preview = ctx.client.enable_preview(plugin_id)
    ctx.check(int(preview.get("held_ports", 0)) >= 1, "the enable preview does not report the held port")
    ctx.client.set_port(device, "tcp", port, {"state": "MONITORED"})
    row = ctx.row(device, "tcp", port)
    ctx.check(row["state"] == "MONITORED" and row.get("promotion_held") is False, "Monitor did not release the held port")


def port_guess(ctx: Context) -> None:
    """L-01, L-02, L-07: guesses never start monitoring, and TCP checks never touch UDP."""
    p = ctx.params
    target, port = p["target"], int(p["port"])
    ctx.require_scanned(port)
    device = ctx.device(target)
    ctx.fixtures.start(target, p["fixture"])
    ctx.on_cleanup("stop guess fixture", lambda: ctx.fixtures.stop(target, p["fixture"]))
    plugin_id = ctx.enable(p["plugin"])
    ctx.discover()
    row = ctx.row(device, "tcp", port)
    ctx.check(row.get("identified_by") == "PORT_HINT", f"port {port} is identified by {row.get('identified_by')}, expected a port-hint guess")
    ctx.check(row["state"] == "SUGGESTED", "a guessed port must stay Suggested")
    ctx.check((row.get("reason") or {}).get("code") == "guessed", "reason code is not 'guessed'")
    listed = ctx.client.plugin_services(plugin_id)
    ctx.check(not any(item.get("port") == port for item in listed), "the generic check attached a guessed port")
    ctx.check(not any(item.get("protocol") == "udp" for item in listed), "the TCP check attached a UDP port")


def port_pin(ctx: Context) -> None:
    """L-06: pin a service name, survive a rescan, reject bad names, remove the pin."""
    p = ctx.params
    target, port = p["target"], int(p["port"])
    ctx.require_scanned(port)
    device = ctx.device(target)
    ctx.fixtures.start(target, p["fixture"])
    ctx.on_cleanup("stop pin fixture", lambda: ctx.fixtures.stop(target, p["fixture"]))
    ctx.enable(p["plugin"])
    ctx.discover()
    ctx.check(ctx.row(device, "tcp", port)["state"] == "MONITORED", "port is not monitored before pinning")
    ctx.on_cleanup("remove pin", lambda: ctx.client.set_port(device, "tcp", port, {"unpin": True})
                   if (ctx.row_or_none(device, "tcp", port) or {}).get("pinned") else None)
    ctx.client.set_port(device, "tcp", port, {"service_name": p["pin_name"]})
    row = ctx.row(device, "tcp", port)
    ctx.check(row.get("pinned") is True and row["service_name"] == p["pin_name"], "port is not pinned to the requested name")
    ctx.validate_nagios("port-pin")
    ctx.discover()
    ctx.check(ctx.row(device, "tcp", port).get("pinned") is True, "a rescan removed the pin")
    for bad in ("a b", "a" * 33, ""):
        status, _ = ctx.client.call("PUT", f"/api/system/hosts/{device}/ports/tcp/{port}", {"service_name": bad})
        ctx.check(status == 400, f"service name {bad!r} was not rejected (HTTP {status})")
    ctx.client.set_port(device, "tcp", port, {"unpin": True})
    ctx.check(ctx.row(device, "tcp", port).get("pinned") is False, "unpin did not clear the pin")


def stop_resume(ctx: Context) -> None:
    """F-06, C-14: stop one device, discovery does not re-attach it, resume, repeats are safe."""
    p = ctx.params
    target, port = p["target"], int(p["port"])
    device = ctx.device(target)
    plugin_id = ctx.enable(p["plugin"])
    ctx.discover()
    ctx.on_cleanup("resume stopped service", lambda: ctx.client.resume_service(plugin_id, device, "tcp", port))
    again = ctx.client.enable_plugin(plugin_id)
    ctx.check(again.get("changed") is False, "enabling an enabled plugin reported a change")
    ctx.client.stop_service(plugin_id, device, "tcp", port)
    ctx.check(ctx.row(device, "tcp", port)["state"] == "IGNORED", "stopped port is not Ignored")
    stopped = [i for i in ctx.client.plugin_services(plugin_id) if i["device"]["id"] == device and i.get("port") == port]
    ctx.check(bool(stopped) and not stopped[0].get("monitored"), "the stopped service is still listed as monitored")
    ctx.discover()
    ctx.check(ctx.row(device, "tcp", port)["state"] == "IGNORED", "discovery re-attached a stopped port")
    ctx.client.resume_service(plugin_id, device, "tcp", port)
    ctx.check(ctx.row(device, "tcp", port)["state"] == "MONITORED", "resume did not restore monitoring")
    ctx.validate_nagios("stop-resume")


def localhost_scope(ctx: Context) -> None:
    """O-04, C-12, C-13: Nagios Core's checks are untouched and removed routes stay removed."""
    for name in ctx.params["not_service_driven"]:
        status, _ = ctx.client.call("POST", f"/api/plugin/{ctx.client.plugin_by_name(name)['id']}/enable")
        ctx.check(status == 409, f"enabling {name} returned HTTP {status}, expected 409")
    for method, path in REMOVED_ROUTES:
        status, _ = ctx.client.call(method, path, {} if method == "POST" else None)
        ctx.check(status in (404, 405), f"{method} {path} returned HTTP {status}, expected 404/405")
    ctx.evidence["localhost_cfg_sha256"] = guards.assert_localhost_unchanged(ctx.config, ctx.run_dir)


def rejection_flag(run_dir: Path) -> Path:
    """The file whose presence makes the wrapper reject candidate configs."""
    return run_dir / "reject-config.flag"


def reject_config(ctx: Context) -> None:
    """R-01..R-03, PM-07, PM-08: a Nagios rejection leaves the running config and states as they were."""
    p = ctx.params
    flag = rejection_flag(ctx.run_dir)
    hosts_config = Path(ctx.config["nagios"]["host_config"])
    flag.unlink(missing_ok=True)
    ctx.on_cleanup("remove rejection flag", lambda: flag.unlink(missing_ok=True))
    stable_plugin = ctx.enable(p["stable_plugin"])
    device = ctx.device(p["target"])
    port = int(p["port"])
    ctx.on_cleanup("restore stopped port", lambda: ctx.client.set_port(device, "tcp", port, {"state": "MONITORED"}))
    live_before = guards.sha256_of(hosts_config)
    flag.write_text("reject\n", encoding="utf-8")
    # R-01: a port edit is saved, and the screen is told Nagios was not updated.
    reply = ctx.client.set_port(device, "tcp", port, {"state": "IGNORED"})
    if reply.get("config_ok") is True:
        raise BlockedError("The app accepted the change, so it is not running with the rejection wrapper as NAGIOS_BIN (see README).")
    ctx.check(bool(reply.get("config_message")), "no reason was given for the rejected Nagios update")
    ctx.check(ctx.row(device, "tcp", port)["state"] == "IGNORED", "the port edit was not saved")
    # PM-07: disabling is refused and the plugin stays on.
    status, body = ctx.client.call("POST", f"/api/plugin/{stable_plugin}/disable")
    ctx.check(status == 409, f"a rejected disable returned HTTP {status}, expected 409")
    ctx.check("still on" in str(body.get("message", "")), "the rejected disable does not say the plugin is still on")
    ctx.check(ctx.client.get_data(f"/api/plugin/{stable_plugin}").get("status") in {"Enabled", "Active"},
              "a rejected disable turned the plugin off")
    # PM-08a: enabling keeps the plugin Enabled, attaches nothing, and says why.
    other = ctx.client.plugin_by_name(p["other_plugin"])
    was_on = other.get("status") in {"Enabled", "Active"}
    outcome = ctx.client.enable_plugin(other["id"])
    if not was_on:
        ctx.on_cleanup(f"disable {p['other_plugin']}", lambda: ctx.client.disable_plugin(other["id"]))
    apply = outcome.get("auto_apply") or {}
    ctx.check(apply.get("success") is False and bool(apply.get("message")), "a rejected enable did not report Nagios as not updated")
    ctx.check(not was_on and not ctx.client.plugin_services(other["id"]), "a rejected enable kept service rows")
    # PM-08b: stopping through the plugin route fails and the port goes back.
    ctx.client.set_port(device, "tcp", port, {"state": "MONITORED"})
    status, _ = ctx.client.call("POST", f"/api/plugin/{stable_plugin}/services/stop",
                                {"device_id": device, "protocol": "tcp", "port": port})
    ctx.check(status == 409, f"a rejected stop returned HTTP {status}, expected 409")
    ctx.check(ctx.row(device, "tcp", port)["state"] == "MONITORED", "a rejected stop left the port stopped")
    # The running Nagios config never changed while the wrapper rejected every change.
    ctx.check(guards.sha256_of(hosts_config) == live_before, "the live hosts.cfg changed during rejected updates")
    flag.unlink(missing_ok=True)
    ctx.validate_nagios("reject-config-recovered")


def port_lifecycle(ctx: Context) -> None:
    """L-08: missing after N unseen scans, reopened without a duplicate, archived after the configured time."""
    p = ctx.params
    target, port = p["target"], int(p["port"])
    ctx.require_scanned(port)
    device = ctx.device(target)
    ctx.on_cleanup("stop lifecycle fixture", lambda: ctx.fixtures.stop(target, p["fixture"]))
    plugin_id = ctx.enable(p["plugin"])
    ctx.fixtures.start(target, p["fixture"])
    ctx.discover()
    before = ctx.row(device, "tcp", port)
    if before.get("check_plugin") != p["plugin"]:
        raise BlockedError(
            f"tcp/{port} on {target} is checked by {before.get('check_plugin')}, not {p['plugin']}; use a port with no earlier history.")
    ctx.check(before["state"] == "MONITORED", "port is not monitored before closing it")
    missing_after = int(p.get("missing_after_scans", 5))

    def close_until_missing() -> None:
        ctx.fixtures.stop(target, p["fixture"])
        for _ in range(missing_after):
            ctx.discover()
        ctx.check(ctx.row(device, "tcp", port)["state"] == "MISSING", f"port is not MISSING after {missing_after} scans")

    close_until_missing()
    ctx.check(any(i.get("port") == port for i in ctx.client.plugin_services(plugin_id)), "a MISSING port left Nagios early")
    ctx.fixtures.start(target, p["fixture"])
    ctx.discover()
    ctx.check(ctx.row(device, "tcp", port)["state"] == "MONITORED", "a reopened port did not return to MONITORED")
    ctx.check(sum(1 for i in ctx.client.plugin_services(plugin_id) if i.get("port") == port) == 1, "reopening duplicated the service")
    archive_seconds = p.get("archive_after_seconds")
    if archive_seconds is None:
        ctx.evidence["archive"] = "Skipped: archive_after_seconds not set (the app must run with PINPOINT_PORT_ARCHIVE_AFTER_DAYS)."
        return
    close_until_missing()
    time.sleep(float(archive_seconds))
    ctx.discover()
    ctx.check(ctx.row(device, "tcp", port)["state"] == "ARCHIVED", "port was not archived after the configured time")
    ctx.check(not any(i.get("port") == port and i.get("monitored") for i in ctx.client.plugin_services(plugin_id)),
              "an archived port is still monitored")
    ctx.validate_nagios("port-lifecycle-archived")


MATRIX_VIEW = ["system.hosts", "plugin.view"]
MATRIX_ROLES = {
    "viewer": ["system.hosts"],
    "operator": MATRIX_VIEW + ["system.hosts.edit"],
    "enable-only": MATRIX_VIEW + ["system.hosts.edit", "plugin.enable"],
    "disable-only": MATRIX_VIEW + ["system.hosts.edit", "plugin.disable"],
}


def permissions_matrix(ctx: Context) -> None:
    """P-01..P-06: what each permission allows, through real sessions of harness-owned accounts."""
    p = ctx.params
    if not ctx.admin_password or ctx.login is None:
        raise BlockedError("The permission matrix needs the admin password and a login factory.")
    manager = accounts.AccountManager(ctx.client, p.get("domain", "example.com"))
    ctx.on_cleanup("deactivate matrix accounts", lambda: _raise_problems(manager.deactivate()))
    for key, permissions in MATRIX_ROLES.items():
        manager.ensure_role(key, permissions)
        manager.ensure_account(key, ctx.admin_password)
    device = ctx.device(p["target"])
    plugin_id = ctx.client.plugin_by_name(p["plugin"])["id"]
    current = ctx.row(device, "tcp", int(p["port"]))["state"]
    ports_url = f"/api/system/hosts/{device}/ports"
    port_url = f"{ports_url}/tcp/{int(p['port'])}"
    nothing = {"device_id": device, "protocol": "tcp", "port": 1}     # a port that does not exist: harmless

    def session(key: str) -> PinpointClient:
        email = manager.email(key)
        return ctx.login(email, accounts.derived_password(ctx.admin_password, email))

    def expect(label: str, client: PinpointClient, method: str, path: str, body: Any, allowed: set[int] | None, denied: bool) -> None:
        status, _ = client.call(method, path, body)
        if denied:
            ctx.check(status == 403, f"{label}: HTTP {status}, expected 403")
        elif allowed is not None:
            ctx.check(status in allowed, f"{label}: HTTP {status}, expected one of {sorted(allowed)}")
        else:
            ctx.check(status != 403, f"{label}: denied (403) though the permission is held")

    viewer = session("viewer")
    expect("P-01 viewer reads ports", viewer, "GET", ports_url, None, {200}, False)
    expect("P-01 viewer cannot change a port", viewer, "PUT", port_url, {"state": current}, None, True)
    expect("P-01 viewer cannot open Plugin Manager", viewer, "GET", "/api/plugin", None, None, True)
    operator = session("operator")
    expect("P-04 operator changes a port", operator, "PUT", port_url, {"state": current}, {200}, False)
    expect("P-04 operator cannot enable", operator, "POST", f"/api/plugin/{plugin_id}/enable", None, None, True)
    manager.set_permissions("operator", MATRIX_VIEW)
    expect("P-02 operator without edit reads ports", operator, "GET", ports_url, None, {200}, False)
    expect("P-02 operator without edit cannot change a port", operator, "PUT", port_url, {"state": current}, None, True)
    enable_only = session("enable-only")
    expect("P-05 enable-only cannot stop", enable_only, "POST", f"/api/plugin/{plugin_id}/services/stop", nothing, None, True)
    expect("P-05 enable-only may resume", enable_only, "POST", f"/api/plugin/{plugin_id}/services/resume", nothing, None, False)
    disable_only = session("disable-only")
    expect("P-06 disable-only cannot resume", disable_only, "POST", f"/api/plugin/{plugin_id}/services/resume", nothing, None, True)
    expect("P-06 disable-only may stop", disable_only, "POST", f"/api/plugin/{plugin_id}/services/stop", nothing, None, False)
    ctx.evidence["accounts"] = sorted(manager.accounts)


def _raise_problems(problems: list[str]) -> None:
    if problems:
        raise HarnessError("; ".join(problems))


SCENARIOS: dict[str, Callable[[Context], None]] = {
    "PERMISSIONS": permissions_matrix,
    "PORT-FLAG": port_flag, "PORT-HELD": port_held, "PORT-GUESS": port_guess, "PORT-PIN": port_pin,
    "STOP-RESUME": stop_resume, "LOCALHOST": localhost_scope, "REJECT-CONFIG": reject_config,
    "PORT-LIFECYCLE": port_lifecycle,
}


def write_rejection_wrapper(
    run_dir: Path, flag_file: Path, real_binary: str, main_config: str, live_hosts: str,
) -> Path:
    """
    Write the NAGIOS_BIN wrapper. While the flag file exists it fails `nagios -v` for a
    *candidate* hosts file (a cfg_file passed to -v that is not in the real nagios.cfg) whose
    content differs from the live hosts.cfg. The enable pre-check validates the live config,
    so it still passes and the rejection reaches the attach, disable and stop paths.
    """
    for value in (str(flag_file), real_binary, main_config, live_hosts):
        if any(char in value for char in "'\"\n$`\\"):
            raise HarnessError("Wrapper values must not contain quotes, newlines or shell metacharacters.")
    script = run_dir / "nagios-reject-wrapper.sh"
    script.write_text(
        "#!/bin/bash\n"
        f"if [ -f '{flag_file}' ]; then\n"
        "  for f in $(grep -E '^cfg_file' \"$2\" 2>/dev/null | cut -d= -f2); do\n"
        f"    if ! grep -qxF \"cfg_file=$f\" '{main_config}'; then\n"
        f"      if ! cmp -s \"$f\" '{live_hosts}'; then echo 'Error: rejected by the test wrapper'; exit 1; fi\n"
        "    fi\n"
        "  done\n"
        "fi\n"
        f"exec '{real_binary}' \"$@\"\n",
        encoding="utf-8",
    )
    script.chmod(0o700)
    return script


def run_scenario(
    scenario_id: str, params: dict[str, Any], client: PinpointClient, config: dict[str, Any],
    run_dir: Path, fixtures: Any, admin_password: str = "",
    login: Callable[[str, str], PinpointClient] | None = None,
) -> CaseResult:
    """Run one scenario, always tear down, and return its result (Pass, Fail or Blocked)."""
    if scenario_id not in SCENARIOS:
        raise HarnessError(f"Unknown scenario: {scenario_id}")
    started = utc_now()
    ctx = Context(client=client, config=config, run_dir=run_dir, params=params, fixtures=fixtures,
                  admin_password=admin_password, login=login)
    result, summary = "Pass", ""
    try:
        SCENARIOS[scenario_id](ctx)
        guards.assert_localhost_unchanged(config, run_dir)
    except BlockedError as exc:
        result, summary = "Blocked", str(exc)
    except HarnessError as exc:
        result, summary = "Fail", str(exc)
    problems = ctx.run_teardown()
    if ctx.failures:
        result, summary = "Fail", "; ".join(ctx.failures + ([summary] if summary else []))
    if problems:
        summary = "; ".join(filter(None, [summary] + problems))
        if result == "Pass":
            result = "Fail"
    if result == "Pass":
        summary = f"{scenario_id} passed ({ctx.scans} scans)."
    evidence_path = run_dir / "evidence" / f"scenario-{scenario_id}.json"
    evidence_path.write_text(json.dumps(
        {"result": result, "summary": summary, "failures": ctx.failures, "teardown_problems": problems,
         "evidence": ctx.evidence}, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return CaseResult(
        test_id=params.get("case_id", scenario_id), result=result, summary=summary, plugin=params.get("plugin", ""),
        target=params.get("target", ""), started_at=started, completed_at=utc_now(),
        evidence=[str(evidence_path.relative_to(run_dir))],
    )
