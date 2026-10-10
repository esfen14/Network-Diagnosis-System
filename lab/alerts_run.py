"""Alert lifecycle run against the lab: take a target down, watch the alert appear,
acknowledge it, unacknowledge it, bring the target back and watch the alert clear.

Pinpoint names discovered hosts `dev-xxxxxx`, so the alert is found by comparing the
active alerts before and after the target goes down, not by name. The target is always
started again at the end, even when a check fails. Standard library only; needs the
lab's `demo/demo_lab.py` and VirtualBox. Run it after discovery (scripts/vmlab smoke).

    SMOKE_PASSWORD=... python3 lab/alerts_run.py --email ADMIN --target web01

Exit status 0 when every check passes.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smoke  # noqa: E402  (shares the API client and the PASS/FAIL printer)

DEMO_LAB = Path(__file__).resolve().parent.parent / "demo" / "demo_lab.py"
ALERTS = "/api/system/dashboard/alerts"
ACK = "/api/system/dashboard/alerts/acknowledge"


def alert_key(alert):
    return (alert["hostname"], alert["service_name"])


def fetch_alerts(api, ack_filter="all"):
    status, body = api.call("GET", f"{ALERTS}?limit=100&ack_filter={ack_filter}")
    if status != 200:
        return []
    return (body.get("data") or {}).get("alerts") or []


def alert_keys(api, ack_filter="all"):
    keys = set()
    for alert in fetch_alerts(api, ack_filter):
        keys.add(alert_key(alert))
    return keys


def demo(*arguments):
    return subprocess.run([sys.executable, str(DEMO_LAB), *arguments], capture_output=True, text=True)


def wait_for(condition, seconds, step=10):
    """Return the first truthy result of condition(), or None after `seconds`."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        result = condition()
        if result:
            return result
        time.sleep(step)
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18080")
    parser.add_argument("--email", required=True, help="Pinpoint administrator email")
    parser.add_argument("--target", default="web01", help="demo target to take down (web01, web02, app01, snmp01, legacy01)")
    parser.add_argument("--timeout", type=int, default=400, help="seconds to wait for the alert to appear and to clear")
    args = parser.parse_args()

    password = os.environ.get("SMOKE_PASSWORD")
    if not password:
        print("set SMOKE_PASSWORD to the Pinpoint administrator password")
        return 1
    check = smoke.check
    api = smoke.Client(args.base_url)

    status, body = api.call("POST", "/api/user/login", {"email": args.email, "password": password})
    if not check("log in as the administrator", status == 200 and body.get("success"), f"HTTP {status}"):
        return 1
    if (body.get("data") or {}).get("needs_setup"):
        check("administrator has completed first-run setup", False, "run: scripts/vmlab setup-admin")
        return 1

    before = alert_keys(api)
    print(f"alerts before: {len(before)}")
    result = demo("break", args.target, "host")
    if not check(f"take {args.target} down", result.returncode == 0, result.stdout.strip()[:80]):
        return 1

    try:
        def new_alert():
            for alert in fetch_alerts(api):
                if alert_key(alert) not in before:
                    return alert
            return None

        alert = wait_for(new_alert, args.timeout)
        if not check("a new alert appears in the active alerts feed", alert is not None,
                     alert["plugin_output"] if alert else f"none in {args.timeout}s"):
            return 1
        who = {"hostname": alert["hostname"], "service_name": alert["service_name"]}
        key = alert_key(alert)

        check("the alert starts unacknowledged", alert["ack"] is None)
        status, body = api.call("POST", ACK, {**who, "comment": "vm lab test"})
        check("acknowledge it", status in (200, 201), f"HTTP {status}: {body.get('message')}")
        check("it is listed as acknowledged", key in alert_keys(api, "acknowledged"))
        check("it is not listed as unacknowledged", key not in alert_keys(api, "unacknowledged"))
        status, body = api.call("DELETE", ACK, who)
        check("unacknowledge it", status == 200, f"HTTP {status}: {body.get('message')}")
        check("it is listed as unacknowledged again", key in alert_keys(api, "unacknowledged"))
    finally:
        result = demo("fix", args.target, "host")
        check(f"bring {args.target} back", result.returncode == 0, result.stdout.strip()[:80])

    cleared = wait_for(lambda: key not in alert_keys(api), args.timeout)
    check("the alert clears after the target is back", cleared is not None)
    status, body = api.call("GET", "/api/system/history/alerts")
    check("state changes appear in the alert history", status == 200, f"HTTP {status}")

    failed = smoke.results.count(False)
    print(f"\n{len(smoke.results) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
