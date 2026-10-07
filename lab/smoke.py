"""Smoke checks for the local lab (scripts/lab smoke).

Logs in, runs Network Discovery against the lab network, and waits until
Pinpoint shows every target as monitored and up. Standard library only; talks
to http://127.0.0.1:8000. Exit status 0 when every check passes.

    scripts/lab smoke [--base-url URL] [--discovery-timeout S] [--hosts-timeout S]
"""
import argparse
import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.request

TARGETS = ["web01", "web02", "app01", "snmp01", "legacy01"]
ADMIN = {"email": "admin@test.com", "password": "Password123!"}


class Client:
    """A tiny cookie-keeping JSON client for the Pinpoint API."""

    def __init__(self, base):
        self.base = base.rstrip("/")
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with self.opener.open(request, timeout=30) as response:
                return response.status, json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.loads(error.read() or b"{}")
            except ValueError:
                return error.code, {}


results = []


def check(name, ok, detail=""):
    """Record and print one PASS/FAIL line."""
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    return ok


def wait_for(predicate, timeout, interval=5):
    """Poll predicate() until it returns a truthy value or the timeout passes."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--discovery-timeout", type=int, default=300)
    parser.add_argument("--hosts-timeout", type=int, default=240)
    args = parser.parse_args()
    api = Client(args.base_url)

    status, body = api.call("POST", "/api/user/login", ADMIN)
    if not check("log in as the seeded administrator", status == 200 and body.get("success"), f"HTTP {status}"):
        print("Is the lab running? Try: scripts/lab up")
        return 1

    status, body = api.call("POST", "/api/system/discover/start")
    if not check("start Network Discovery", status in (200, 202) and body.get("success"), f"HTTP {status}: {body.get('message')}"):
        return 1

    def discovery_finished():
        _, current = api.call("GET", "/api/system/discover/status")
        data = current.get("data") or {}
        return data if str(data.get("status")).lower() in {"success", "failed", "error", "cancelled", "stopped"} else None

    started = time.time()
    outcome = wait_for(discovery_finished, args.discovery_timeout, interval=4)
    took = int(time.time() - started)
    check(
        "discovery finishes and applies the Nagios config",
        bool(outcome) and str(outcome.get("status")).lower() == "success",
        f"{outcome.get('status')}, {took}s, {outcome.get('message')}" if outcome else f"no result after {took}s",
    )

    def hosts_up():
        _, summary = api.call("GET", "/api/system/network-health/summary")
        hosts = (summary.get("data") or {}).get("hosts") or {}
        return hosts if hosts.get("up", 0) >= len(TARGETS) + 1 else None

    hosts = wait_for(hosts_up, args.hosts_timeout, interval=10)
    check(
        "Pinpoint shows the targets and localhost as up",
        bool(hosts),
        f"{hosts['up']} up of {hosts['total']}" if hosts else "not all hosts up in time",
    )

    _, listing = api.call("GET", "/api/system/network-health/hosts?per_page=50")
    data = listing.get("data") or {}
    names = [str(item.get("hostname") or item.get("host_name") or "") for item in (data.get("items") or data.get("hosts") or [])]
    for target in TARGETS:
        check(f"host table lists {target}", any(target in name for name in names))

    failed = results.count(False)
    print(f"\n{len(results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
