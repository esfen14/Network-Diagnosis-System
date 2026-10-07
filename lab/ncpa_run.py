"""NCPA deployment run against the lab (what the deployment wizard does, through the API).

For each target IP: read its SSH host key, trust it, check the SSH login and sudo, start
a deployment, wait for the run to finish, and confirm the device is "Deployed NCPA".
Standard library only. Run it after discovery has found the targets (scripts/vmlab smoke).

    SMOKE_PASSWORD=... python3 lab/ncpa_run.py --email ADMIN --ips 10.77.0.2,10.77.0.6

The targets' SSH login comes from a file (default: demo_lab.py's private password file),
never from the command line. Exit status 0 when every check passes.
"""
import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smoke  # noqa: E402  (shares the API client and the PASS/FAIL printer)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18080")
    parser.add_argument("--email", required=True, help="Pinpoint administrator email")
    parser.add_argument("--ips", required=True, help="comma-separated target IPs to deploy NCPA to")
    parser.add_argument("--ssh-user", default="demo", help="SSH account with sudo on the targets")
    parser.add_argument("--ssh-password-file", default=str(Path.home() / ".local/share/pinpoint-demo/demo-password"))
    parser.add_argument("--timeout", type=int, default=1200, help="seconds to wait for the run to finish")
    args = parser.parse_args()

    password = os.environ.get("SMOKE_PASSWORD")
    if not password:
        print("set SMOKE_PASSWORD to the Pinpoint administrator password")
        return 1
    ssh_password = Path(args.ssh_password_file).read_text().strip()
    wanted = [ip.strip() for ip in args.ips.split(",") if ip.strip()]
    check = smoke.check
    api = smoke.Client(args.base_url)

    status, body = api.call("POST", "/api/user/login", {"email": args.email, "password": password})
    if not check("log in as the administrator", status == 200 and body.get("success"), f"HTTP {status}"):
        return 1

    status, body = api.call("GET", "/api/system/deployment/ncpa/devices")
    devices = {d["ip_address"]: d for d in ((body.get("data") or {}).get("devices") or [])}
    for ip in wanted:
        device = devices.get(ip)
        check(f"{ip} is listed as an NCPA target", device is not None, "not in the device list; run discovery first" if device is None else
              f"{device['hostname']}, agent status: {device['agent_status']}")
    if not all(ip in devices for ip in wanted):
        return 1

    ids = {ip: devices[ip]["device_id"] for ip in wanted}
    for ip in wanted:
        device_id = ids[ip]
        status, body = api.call("GET", f"/api/system/deployment/ncpa/{device_id}/fingerprint")
        data = body.get("data") or {}
        if not check(f"{ip}: read the SSH host key", status == 200 and data.get("fingerprint"),
                     f"SSH port {data.get('ssh_port')}" if status == 200 else f"HTTP {status}: {body.get('message')}"):
            return 1
        status, body = api.call("POST", f"/api/system/deployment/ncpa/{device_id}/confirm-trust", {"fingerprint": data["fingerprint"]})
        if not check(f"{ip}: trust the host key", status == 200 and body.get("success"), f"HTTP {status}: {body.get('message')}"):
            return 1

    credentials = [{"device_id": ids[ip], "username": args.ssh_user, "password": ssh_password} for ip in wanted]
    status, body = api.call("POST", "/api/system/deployment/ncpa/check-credentials", {"devices": credentials})
    results = {r["device_id"]: r["result"] for r in ((body.get("data") or {}).get("results") or [])}
    for ip in wanted:
        check(f"{ip}: SSH login and sudo work", results.get(ids[ip]) == "ok", f"result: {results.get(ids[ip], 'none')}")
    if not all(results.get(ids[ip]) == "ok" for ip in wanted):
        return 1

    status, body = api.call("POST", "/api/system/deployment/ncpa/start", {"devices": credentials})
    data = body.get("data") or {}
    if not check("start the deployment", status == 202 and body.get("success"),
                 f"HTTP {status}: {body.get('message')}; rejected: {data.get('rejected')}"):
        return 1
    run_id = data.get("run_id")

    started = time.time()
    last = ""

    def finished():
        nonlocal last
        _, current = api.call("GET", "/api/system/deployment/ncpa/status")
        run = current.get("data") or {}
        line = f"{run.get('status')} {run.get('progress')}% {run.get('message')}"
        if line != last:
            print(f"      [{int(time.time() - started)}s] {line}")
            last = line
        return run if run.get("status") not in (None, "Running") else None

    run = smoke.wait_for(finished, args.timeout, interval=10)
    took = int(time.time() - started)
    check("the run finishes", bool(run), f"{run.get('status')} in {took}s" if run else f"still running after {took}s")
    if not run:
        return 1
    check("the run succeeded", run.get("status") == "Success", f"status {run.get('status')}, counts {run.get('counts')}")
    for device in run.get("devices") or []:
        check(f"{device['ip_address']}: outcome", device["outcome"] == "Success",
              f"{device['outcome']}" + (f": {device['error']}" if device.get("error") else ""))

    status, body = api.call("GET", "/api/system/deployment/ncpa/devices")
    final = {d["ip_address"]: d for d in ((body.get("data") or {}).get("devices") or [])}
    for ip in wanted:
        check(f"{ip}: device shows as Deployed NCPA", final.get(ip, {}).get("agent_status") == "Deployed NCPA",
              f"agent status: {final.get(ip, {}).get('agent_status')}")

    failed = smoke.results.count(False)
    print(f"\n{len(smoke.results) - failed} passed, {failed} failed (run id {run_id})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
