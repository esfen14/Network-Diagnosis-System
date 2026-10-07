"""Reviewed plugin-driven monitoring scenarios: fixtures, steps, assertions, guaranteed teardown."""

from __future__ import annotations

import json
import os
import re
import sqlite3
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


# ---------------------------------------------------------------- Plugin Manager: custom checks, server checks, registry

CUSTOM_ROLES = {
    "custom-viewer": MATRIX_VIEW,
    "custom-admin": MATRIX_VIEW + ["plugin.custom_check"],
}


def hosts_text(ctx: Context) -> str:
    """The live hosts.cfg Nagios reads (config nagios.host_config)."""
    path = Path(ctx.config["nagios"]["host_config"])
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BlockedError(f"Cannot read {path}: {exc.strerror}") from exc


def service_block(text: str, service: str) -> str | None:
    """The `define service` block whose service_description is `service`, or None."""
    for block in re.findall(r"define service\s*\{(.*?)\n\s*\}", text, flags=re.S):
        match = re.search(r"^\s*service_description\s+(.+?)\s*$", block, flags=re.M)
        if match and match.group(1) == service:
            return block
    return None


def command_line(text: str, command: str) -> str | None:
    """The command_line of the `define command` block named `command`, or None."""
    for block in re.findall(r"define command\s*\{(.*?)\n\s*\}", text, flags=re.S):
        name = re.search(r"^\s*command_name\s+(\S+)", block, flags=re.M)
        if name and name.group(1) == command:
            line = re.search(r"^\s*command_line\s+(.+?)\s*$", block, flags=re.M)
            return line.group(1) if line else ""
    return None


def field_of(block: str, key: str) -> str:
    match = re.search(rf"^\s*{key}\s+(.+?)\s*$", block, flags=re.M)
    return match.group(1) if match else ""


def remove_check_named(ctx: Context, plugin_id: int, name: str) -> None:
    """Remove a leftover check with this name (an earlier run that did not finish) so a run starts clean."""
    for item in ctx.client.custom_checks(plugin_id):
        if item.get("name") == name:
            ctx.client.remove_custom_check(plugin_id, int(item["id"]))


def listed_check(ctx: Context, plugin_id: int, name: str) -> dict[str, Any] | None:
    return next((item for item in ctx.client.custom_checks(plugin_id) if item.get("name") == name), None)


def run_check_lifecycle(ctx: Context, plugin_name: str, device_id: int | None, label: str) -> dict[str, Any]:
    """
    Add one check, prove it reached hosts.cfg and Nagios, wait for a real state, then pause, resume
    and remove it. Used by the device and the server scenarios. Returns the added check.
    """
    p = ctx.params
    plugin = ctx.client.plugin_by_name(plugin_name)
    plugin_id = int(plugin["id"])
    name, variables = p["name"], dict(p.get("variables", {}))
    remove_check_named(ctx, plugin_id, name)
    created: dict[str, Any] = {}

    def cleanup() -> None:
        if created.get("id") is not None and listed_check(ctx, plugin_id, name):
            ctx.client.remove_custom_check(plugin_id, int(created["id"]))

    ctx.on_cleanup(f"remove {label} check", cleanup)
    created.update(ctx.client.add_custom_check(plugin_id, name, variables, device_id))
    ctx.check(created.get("id") is not None, "the add reply has no check id")
    ctx.check(created.get("paused") is False, "a new check is paused")
    service = str(created.get("service", ""))
    block = service_block(hosts_text(ctx), service)
    ctx.check(block is not None, f"{service} is not in hosts.cfg after adding it")
    if block is not None:
        expected_host = "localhost" if device_id is None else (created.get("device") or {}).get("hostname")
        ctx.check(field_of(block, "host_name") == expected_host,
                  f"{service} is on host {field_of(block, 'host_name')!r}, expected {expected_host!r}")
        ctx.check(field_of(block, "check_command").startswith(f"pinpoint_custom_{plugin_name}"),
                  f"{service} does not use the pinpoint_custom command")
    ctx.validate_nagios(f"{label}-added")

    waited = ctx.client.wait_for_custom_check_status(
        plugin_id, int(created["id"]), int(p.get("status_timeout", 420)), int(p.get("status_interval", 15)))
    kind = (waited.get("status") or {}).get("kind")
    ctx.evidence[f"{label}_status"] = {"kind": kind, "output": (waited.get("status") or {}).get("output")}
    ctx.check(kind == p.get("expect_state", "ok"),
              f"{label} check is {kind}, expected {p.get('expect_state', 'ok')}: {(waited.get('status') or {}).get('output')}")

    paused = ctx.client.pause_custom_check(plugin_id, int(created["id"]))
    ctx.check(paused.get("paused") is True, "pause did not pause the check")
    ctx.check(service_block(hosts_text(ctx), service) is None, "a paused check is still in hosts.cfg")
    ctx.check(ctx.client.pause_custom_check(plugin_id, int(created["id"])).get("changed") is False,
              "pausing twice reported a change")
    resumed = ctx.client.resume_custom_check(plugin_id, int(created["id"]))
    ctx.check(resumed.get("paused") is False, "resume did not resume the check")
    ctx.check(service_block(hosts_text(ctx), service) is not None, "a resumed check is missing from hosts.cfg")
    ctx.validate_nagios(f"{label}-resumed")

    ctx.client.remove_custom_check(plugin_id, int(created["id"]))
    ctx.check(listed_check(ctx, plugin_id, name) is None, "a removed check is still listed")
    ctx.check(service_block(hosts_text(ctx), service) is None, "a removed check is still in hosts.cfg")
    ctx.validate_nagios(f"{label}-removed")
    return created


def custom_device(ctx: Context) -> None:
    """CK-01..CK-05: a device check is added, written to hosts.cfg, run by Nagios, paused, resumed and removed."""
    p = ctx.params
    plugin_name = p["plugin"]
    plugin = ctx.client.plugin_by_name(plugin_name)
    details = ctx.client.plugin_details(int(plugin["id"]))
    support = details.get("custom_checks") or {}
    ctx.check(details.get("service_driven") is False, f"{plugin_name} is service-driven")
    if not (support.get("supported") is True and support.get("target") == "device"):
        raise HarnessError(f"{plugin_name} does not offer device checks: {support}")
    status, _ = ctx.client.call("POST", f"/api/plugin/{plugin['id']}/enable")
    ctx.check(status == 409, f"enabling {plugin_name} returned HTTP {status}, expected 409")
    device = ctx.device(p["target"])
    created = run_check_lifecycle(ctx, plugin_name, device, "device")
    ctx.check((created.get("device") or {}).get("id") == device, "the check is on another device")


def custom_survives(ctx: Context) -> None:
    """CK-06: a rescan, enabling and disabling a port plugin, and a port edit leave a custom check alone."""
    p = ctx.params
    plugin = ctx.client.plugin_by_name(p["plugin"])
    plugin_id = int(plugin["id"])
    device = ctx.device(p["target"])
    remove_check_named(ctx, plugin_id, p["name"])
    created = ctx.client.add_custom_check(plugin_id, p["name"], dict(p.get("variables", {})), device)
    ctx.on_cleanup("remove surviving check", lambda: ctx.client.remove_custom_check(plugin_id, int(created["id"]))
                   if listed_check(ctx, plugin_id, p["name"]) else None)
    service = created["service"]
    ctx.discover()
    ctx.check(listed_check(ctx, plugin_id, p["name"]) is not None, "a rescan removed the custom check")
    ctx.check(service_block(hosts_text(ctx), service) is not None, "a rescan removed the service from hosts.cfg")
    other_id = ctx.enable(p["port_plugin"])
    ctx.check(service_block(hosts_text(ctx), service) is not None, "enabling a port plugin removed the custom check")
    ctx.client.disable_plugin(other_id)
    ctx.client.enable_plugin(other_id)
    ctx.check(service_block(hosts_text(ctx), service) is not None, "disabling a port plugin removed the custom check")
    ctx.validate_nagios("custom-survives")


def custom_server(ctx: Context) -> None:
    """CK-10..CK-13: a server check needs no device, is written on localhost, and never touches localhost.cfg."""
    p = ctx.params
    plugin_name = p["plugin"]
    plugin = ctx.client.plugin_by_name(plugin_name)
    plugin_id = int(plugin["id"])
    support = ctx.client.plugin_details(plugin_id).get("custom_checks") or {}
    ctx.check(support.get("supported") is True and support.get("target") == "server",
              f"{plugin_name} does not offer server checks: {support}")
    status, _ = ctx.client.call("POST", f"/api/plugin/{plugin_id}/custom-checks",
                                {"name": "e2e with device", "variables": {}, "device_id": ctx.device(p["target"])})
    ctx.check(status == 400, f"a server check with a device returned HTTP {status}, expected 400")
    created = run_check_lifecycle(ctx, plugin_name, None, "server")
    ctx.check((created.get("device") or {}).get("id") is None, "a server check shows a device")
    ctx.check(str(created.get("service", "")).startswith("server-"), f"service name is {created.get('service')}")


def custom_rules(ctx: Context) -> None:
    """CK-20..CK-27: bad requests are refused with a clear message, nothing is saved and hosts.cfg does not change."""
    p = ctx.params
    hosts_config = Path(ctx.config["nagios"]["host_config"])
    before = guards.sha256_of(hosts_config)
    device_plugin = ctx.client.plugin_by_name(p["device_plugin"])
    server_plugin = ctx.client.plugin_by_name(p["server_plugin"])
    stock_plugin = ctx.client.plugin_by_name(p["unsupported_plugin"])
    device = ctx.device(p["target"])
    dp, sp = device_plugin["id"], server_plugin["id"]
    count_before = len(ctx.client.custom_checks(int(dp))) + len(ctx.client.custom_checks(int(sp)))

    def refuse(label: str, plugin_id: int, body: dict[str, Any], must_not_echo: str | None = None) -> None:
        status, reply = ctx.client.call("POST", f"/api/plugin/{plugin_id}/custom-checks", body)
        ctx.check(status == 400, f"{label}: HTTP {status}, expected 400")
        if must_not_echo:
            ctx.check(must_not_echo not in json.dumps(reply), f"{label}: the reply repeats the rejected value")

    good = dict(p.get("variables", {"command": "/bin/true"}))
    refuse("unsupported plugin", stock_plugin["id"], {"name": "x", "variables": {}, "device_id": device})
    refuse("missing required argument", dp, {"name": "x", "variables": {}, "device_id": device})
    refuse("forbidden character", dp, {"name": "x", "variables": {**good, "command": "a'b"}, "device_id": device}, "a'b")
    refuse("unknown argument", dp, {"name": "x", "variables": {**good, "password": "p"}, "device_id": device})
    refuse("device plugin without a device", dp, {"name": "x", "variables": good})
    refuse("server plugin with a device", sp, {"name": "x", "variables": {}, "device_id": device})
    refuse("unknown device", dp, {"name": "x", "variables": good, "device_id": 99999999})
    refuse("name with a slash", dp, {"name": "no/slash", "variables": good, "device_id": device})
    refuse("name too long", dp, {"name": "n" * 61, "variables": good, "device_id": device})
    refuse("empty name", dp, {"name": "", "variables": good, "device_id": device})
    status, _ = ctx.client.call("GET", f"/api/plugin/{dp}/custom-checks?page=0")
    ctx.check(status == 400, f"page=0 returned HTTP {status}, expected 400")
    status, _ = ctx.client.call("PUT", f"/api/plugin/{dp}/custom-checks/99999999", {"name": "x", "variables": good})
    ctx.check(status == 404, f"changing an unknown check returned HTTP {status}, expected 404")
    status, _ = ctx.client.call("DELETE", f"/api/plugin/{dp}/custom-checks/99999999")
    ctx.check(status == 404, f"removing an unknown check returned HTTP {status}, expected 404")
    # A name is unique per device.
    name = p.get("name", "e2e duplicate")
    remove_check_named(ctx, int(dp), name)
    first = ctx.client.add_custom_check(int(dp), name, good, device)
    ctx.on_cleanup("remove duplicate-test check", lambda: ctx.client.remove_custom_check(int(dp), int(first["id"]))
                   if listed_check(ctx, int(dp), name) else None)
    refuse("duplicate name", dp, {"name": name, "variables": good, "device_id": device})
    ctx.client.remove_custom_check(int(dp), int(first["id"]))
    after_sha = guards.sha256_of(hosts_config)
    ctx.check(after_sha == before, "hosts.cfg differs after adding and removing one check and refusing the rest")
    ctx.check(len(ctx.client.custom_checks(int(dp))) + len(ctx.client.custom_checks(int(sp))) == count_before,
              "a refused request left a check behind")


def custom_permissions(ctx: Context) -> None:
    """CK-30..CK-32: only plugin.custom_check opens the routes; plugin.view does not, and it grants no right to enable."""
    p = ctx.params
    if not ctx.admin_password or ctx.login is None:
        raise BlockedError("The custom check permission case needs the admin password and a login factory.")
    manager = accounts.AccountManager(ctx.client, p.get("domain", "example.com"))
    ctx.on_cleanup("deactivate custom-check accounts", lambda: _raise_problems(manager.deactivate()))
    for key, permissions in CUSTOM_ROLES.items():
        manager.ensure_role(key, permissions)
        manager.ensure_account(key, ctx.admin_password)
    plugin_id = ctx.client.plugin_by_name(p["plugin"])["id"]
    base = f"/api/plugin/{plugin_id}/custom-checks"

    def session(key: str) -> PinpointClient:
        email = manager.email(key)
        return ctx.login(email, accounts.derived_password(ctx.admin_password, email))

    viewer = session("custom-viewer")
    ctx.check(viewer.call("GET", base)[0] == 403, "CK-30 a viewer listed custom checks")
    ctx.check(viewer.call("POST", base, {"name": "x", "variables": {}})[0] == 403, "CK-30 a viewer added a custom check")
    ctx.check(viewer.call("GET", "/api/plugin/custom-check-devices")[0] == 403, "CK-30 a viewer searched devices")
    ctx.check(viewer.call("DELETE", f"{base}/1")[0] == 403, "CK-30 a viewer removed a custom check")
    ctx.check(viewer.call("GET", f"/api/plugin/{plugin_id}")[0] == 200, "CK-30 plugin.view no longer shows the plugin")
    admin = session("custom-admin")
    ctx.check(admin.call("GET", base)[0] == 200, "CK-31 the permission holder cannot list custom checks")
    ctx.check(admin.call("GET", "/api/plugin/custom-check-devices")[0] == 200, "CK-31 the permission holder cannot search devices")
    ctx.check(admin.call("POST", base, {"name": "x", "variables": {}})[0] == 400,
              "CK-31 a bad request from the permission holder was not refused with 400")
    ctx.check(admin.call("POST", f"/api/plugin/{plugin_id}/enable")[0] == 403,
              "CK-32 plugin.custom_check alone allows enabling a plugin (it must not grant plugin.enable)")
    ctx.evidence["accounts"] = sorted(manager.accounts)


def custom_password(ctx: Context) -> None:
    """CK-40..CK-45: a password is encrypted at rest, never returned, kept on a blank change, and removed with the check."""
    p = ctx.params
    password = os.environ.get(p["password_env"], "")
    if not password:
        raise BlockedError(f"Set the environment variable {p['password_env']} to a throwaway password for this case.")
    field_name = p.get("password_field", "password")
    plugin = ctx.client.plugin_by_name(p["plugin"])
    plugin_id = int(plugin["id"])
    support = ctx.client.plugin_details(plugin_id).get("custom_checks") or {}
    ctx.check(any(f.get("name") == field_name and f.get("secret") for f in support.get("fields", [])),
              f"{p['plugin']} has no password field named {field_name}")
    device = ctx.device(p["target"])
    name = p["name"]
    remove_check_named(ctx, plugin_id, name)
    variables = {**p.get("variables", {}), field_name: password}
    created: dict[str, Any] = {}
    ctx.on_cleanup("remove password check", lambda: ctx.client.remove_custom_check(plugin_id, int(created["id"]))
                   if created.get("id") is not None and listed_check(ctx, plugin_id, name) else None)
    reply = ctx.client.add_custom_check(plugin_id, name, variables, device)
    created.update(reply)
    listing = json.dumps(ctx.client.custom_checks(plugin_id))
    ctx.check(password not in json.dumps(reply), "the add reply repeats the password")
    ctx.check(password not in listing, "the list repeats the password")
    ctx.check(reply.get("secrets_set") == [field_name], f"secrets_set is {reply.get('secrets_set')}")
    ctx.check(reply.get("secrets_readable") is True, "the stored password cannot be read back")
    stored = _stored_configuration(ctx, str(reply.get("service", "")))
    ctx.check(stored is not None, "the check is not in the database")
    if stored is not None:
        ctx.check(password not in stored, "the database holds the password in plain text")
        ctx.check('"v1:' in stored or "v1:" in stored, "the database does not hold an encrypted value")
    block = service_block(hosts_text(ctx), str(reply.get("service", "")))
    ctx.check(block is not None and password in field_of(block, "check_command"),
              "hosts.cfg does not carry the password Nagios needs (documented trade-off)")
    if os.name == "posix":
        mode = Path(ctx.config["nagios"]["host_config"]).stat().st_mode & 0o777
        ctx.evidence["hosts_cfg_mode"] = oct(mode)
        ctx.check(not mode & 0o004, f"hosts.cfg is readable by every user (mode {oct(mode)}) while it holds a password")
    ctx.validate_nagios("password-added")

    kept = ctx.client.change_custom_check(plugin_id, int(created["id"]), name, p.get("variables", {}))
    ctx.check(kept.get("secrets_set") == [field_name], "a blank password on a change dropped the stored one")
    ctx.check(password in field_of(service_block(hosts_text(ctx), str(kept.get("service"))) or "", "check_command"),
              "a blank password on a change removed it from the command")
    if p.get("password_required", True):
        status, _ = ctx.client.call("PUT", f"/api/plugin/{plugin_id}/custom-checks/{created['id']}",
                                    {"name": name, "variables": p.get("variables", {}), "clear_secrets": [field_name]})
        ctx.check(status == 400, f"clearing a required password returned HTTP {status}, expected 400")
    ctx.client.remove_custom_check(plugin_id, int(created["id"]))
    ctx.check(_stored_configuration(ctx, str(reply.get("service", ""))) is None, "a removed check is still in the database")
    ctx.check(password not in hosts_text(ctx), "the password is still in hosts.cfg after removing the check")
    ctx.validate_nagios("password-removed")


def _stored_configuration(ctx: Context, service: str) -> str | None:
    """The stored Configuration_Data of a custom check read straight from the system database."""
    database = ctx.config.get("databases", {}).get("system")
    if not database:
        raise BlockedError("config databases.system is not set, so the stored value cannot be inspected.")
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise BlockedError(f"Cannot open {database}: {exc}") from exc
    try:
        row = connection.execute(
            "select Configuration_Data from PLUGIN_CONFIGURATION where Nagios_Service_Name = ? and Origin = 'CUSTOM'",
            (service,)).fetchone()
    finally:
        connection.close()
    return None if row is None else str(row[0])


def registry_enable(ctx: Context) -> None:
    """CK-50: the plugins added to the registry are recognised, previewed, enabled and disabled."""
    for name in ctx.params["plugins"]:
        plugin = ctx.client.plugin_matching(name)
        plugin_id = int(plugin["id"])
        details = ctx.client.plugin_details(plugin_id)
        ctx.check(details.get("service_driven") is True, f"{name} is not service-driven")
        preview = ctx.client.enable_preview(plugin_id)
        ctx.check(preview.get("service_driven") is True, f"{name}: the enable preview says it is not service-driven")
        ctx.enable(plugin["name"])
        status = ctx.client.plugin_details(plugin_id).get("status")
        ctx.check(status in {"Enabled", "Active"}, f"{name} is {status} after enabling")
    ctx.validate_nagios("registry-enable")


def ncpa_name(ctx: Context) -> None:
    """CK-51: check_ncpa stored under its filename is recognised, enabled, disabled and runs the .py file."""
    p = ctx.params
    plugin = ctx.client.plugin_matching(p.get("plugin", "check_ncpa"))
    plugin_id = int(plugin["id"])
    details = ctx.client.plugin_details(plugin_id)
    ctx.check(details.get("service_driven") is True, f"{plugin['name']} shows as not service-driven")
    ctx.check((details.get("custom_checks") or {}).get("class") == "service",
              f"{plugin['name']} is class {(details.get('custom_checks') or {}).get('class')}, expected service")
    ctx.check(bool(details.get("category")), "the plugin has no category (catalog lookup missed the filename)")
    was_on = plugin.get("status") in {"Enabled", "Active"}
    outcome = ctx.client.enable_plugin(plugin_id)
    apply = outcome.get("auto_apply") or {}
    ctx.check(apply.get("success") is not False, f"Nagios was not updated after enabling: {apply.get('message')}")
    if not was_on:
        ctx.on_cleanup(f"disable {plugin['name']}", lambda: ctx.client.disable_plugin(plugin_id))
    ctx.check(ctx.client.plugin_details(plugin_id).get("status") in {"Enabled", "Active"}, "check_ncpa did not become enabled")
    services = ctx.client.plugin_services(plugin_id)
    if p.get("expect_services"):
        ctx.check(bool(services), "no NCPA services were attached (is an agent deployed?)")
        ctx.check(all(str(item.get("service", "")).startswith("ncpa-") for item in services), "an NCPA service is misnamed")
        line = command_line(hosts_text(ctx), "pinpoint_nd_ncpa")
        ctx.check(line is not None and "check_ncpa.py" in line, f"the NCPA command does not run check_ncpa.py: {line}")
    ctx.validate_nagios("ncpa-enabled")


def plugin_classes(ctx: Context) -> None:
    """CK-60: every plugin kind reports the class and note the drawer shows."""
    for name, expected in ctx.params["classes"].items():
        plugin = ctx.client.plugin_matching(name)
        details = ctx.client.plugin_details(int(plugin["id"]))
        support = details.get("custom_checks") or {}
        ctx.check(support.get("class") == expected, f"{name} is class {support.get('class')}, expected {expected}")
        ctx.check(support.get("supported") is (expected in {"custom", "server"}), f"{name}: supported is {support.get('supported')}")
        if expected == "service":
            ctx.check(details.get("service_driven") is True, f"{name} is not service-driven")
        else:
            ctx.check(details.get("service_driven") is False, f"{name} is service-driven")
        if expected in {"stock", "advanced", "credentials", "unsupported", "replaced"}:
            ctx.check(bool(support.get("note")), f"{name} has no explanation")
        if expected == "custom":
            ctx.check(support.get("target") == "device" and bool(support.get("fields")), f"{name} lists no device fields")
        if expected == "server":
            ctx.check(support.get("target") == "server", f"{name} does not target the server")


SCENARIOS: dict[str, Callable[[Context], None]] = {
    "PERMISSIONS": permissions_matrix,
    "PORT-FLAG": port_flag, "PORT-HELD": port_held, "PORT-GUESS": port_guess, "PORT-PIN": port_pin,
    "STOP-RESUME": stop_resume, "LOCALHOST": localhost_scope, "REJECT-CONFIG": reject_config,
    "PORT-LIFECYCLE": port_lifecycle,
    "CUSTOM-DEVICE": custom_device, "CUSTOM-SURVIVES": custom_survives, "CUSTOM-SERVER": custom_server,
    "CUSTOM-RULES": custom_rules, "CUSTOM-PERMISSIONS": custom_permissions, "CUSTOM-PASSWORD": custom_password,
    "REGISTRY-ENABLE": registry_enable, "NCPA-NAME": ncpa_name, "PLUGIN-CLASSES": plugin_classes,
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
