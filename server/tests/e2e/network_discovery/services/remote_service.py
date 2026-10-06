#!/usr/bin/env python3
"""Control an allow-listed systemd unit or fixture listener on a configured disposable target."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

ALLOWED_ACTIONS = {"start", "stop", "restart", "is-active"}
ALLOWED_UNITS = {
    "bind9", "chrony", "mariadb", "nginx", "postfix", "rpcbind", "slapd",
    "smbd", "snmpd", "vsftpd", "pinpoint-test-tcp", "pinpoint-test-udp",
}

FIXTURE_ACTIONS = {"start", "stop", "is-listening"}
_SILENT_LISTENER = (
    "import socket;s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);"
    's.bind(("",9100));s.listen(5);c=[]\nwhile True: c.append(s.accept()[0])'
)


def _background(command: str, pidfile: str) -> str:
    """Start a fixed command detached from the SSH session and remember its pid."""
    return f"setsid nohup {command} >/dev/null 2>&1 < /dev/null & echo $! > {pidfile}"


def _kill(pidfile: str) -> str:
    return f"if [ -f {pidfile} ]; then kill $(cat {pidfile}) 2>/dev/null; rm -f {pidfile}; fi"


# Every fixture is a fixed command with a fixed port: nothing from the caller reaches the remote shell.
FIXTURES = {
    "sshd-80": {
        "port": 80,
        "start": "/usr/sbin/sshd -p 80 -o PidFile=/run/pdm-sshd-80.pid",
        "stop": _kill("/run/pdm-sshd-80.pid"),
    },
    "http-80": {
        "port": 80,
        "start": _background("python3 -m http.server 80 --directory /tmp", "/run/pdm-http-80.pid"),
        "stop": _kill("/run/pdm-http-80.pid"),
    },
    "http-8080": {
        "port": 8080,
        "start": _background("python3 -m http.server 8080 --directory /tmp", "/run/pdm-http-8080.pid"),
        "stop": _kill("/run/pdm-http-8080.pid"),
    },
    "http-8081": {
        "port": 8081,
        "start": _background("python3 -m http.server 8081 --directory /tmp", "/run/pdm-http-8081.pid"),
        "stop": _kill("/run/pdm-http-8081.pid"),
    },
    "silent-9100": {
        "port": 9100,
        "start": _background(f"python3 -c {shlex.quote(_SILENT_LISTENER)}", "/run/pdm-silent-9100.pid"),
        "stop": _kill("/run/pdm-silent-9100.pid"),
    },
}


def remote_command(args: argparse.Namespace) -> list[str]:
    """Build the fixed remote command for a unit action or a fixture action."""
    if args.fixture:
        if args.fixture not in FIXTURES or args.action not in FIXTURE_ACTIONS:
            raise ValueError("Unknown fixture or action.")
        fixture = FIXTURES[args.fixture]
        if args.action == "is-listening":
            return ["ss", "-lnt", f"sport = :{fixture['port']}"]
        return ["sudo", "-n", "sh", "-c", shlex.quote(fixture[args.action])]
    if args.unit not in ALLOWED_UNITS or args.action not in ALLOWED_ACTIONS:
        raise ValueError("Unknown unit or action.")
    return ["sudo", "-n", "systemctl", args.action, args.unit]


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    root.add_argument("--config", required=True, type=Path)
    root.add_argument("--target", required=True)
    group = root.add_mutually_exclusive_group(required=True)
    group.add_argument("--unit", choices=sorted(ALLOWED_UNITS))
    group.add_argument("--fixture", choices=sorted(FIXTURES))
    root.add_argument("--action", required=True, choices=sorted(ALLOWED_ACTIONS | FIXTURE_ACTIONS))
    return root


def main() -> int:
    """Validate the target and execute one non-interactive remote action."""
    args = parser().parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    try:
        target = config["targets"][args.target]
        key = os.environ[target["ssh_key_env"]]
    except KeyError as exc:
        parser().error(f"Missing target configuration or SSH key environment variable: {exc}")
    try:
        network = ipaddress.ip_network(config["lab_network"], strict=True)
        address = ipaddress.ip_address(target["address"])
    except ValueError as exc:
        parser().error(f"Invalid lab network or target address: {exc}")
    if (
        not isinstance(network, ipaddress.IPv4Network)
        or not network.is_private
        or network.prefixlen < 28
        or address not in network
    ):
        parser().error("Refusing remote control outside the approved private /28 lab.")
    try:
        remote = remote_command(args)
    except ValueError as exc:
        parser().error(str(exc))
    command = [
        "ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-i", key, f"{target['ssh_user']}@{target['address']}", *remote,
    ]
    result = subprocess.run(command, check=False, capture_output=args.action == "is-listening", text=True)
    if args.action == "is-listening":
        # exit 0 only when a socket is listening on the fixture's port (the header line has no port)
        return 0 if f":{FIXTURES[args.fixture]['port']}" in result.stdout else 1
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
