#!/usr/bin/env python3
"""Control an allow-listed systemd unit on a configured disposable target."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import subprocess
import sys
from pathlib import Path

ALLOWED_ACTIONS = {"start", "stop", "restart", "is-active"}
ALLOWED_UNITS = {
    "bind9", "chrony", "mariadb", "nginx", "postfix", "rpcbind", "slapd",
    "smbd", "snmpd", "vsftpd", "pinpoint-test-tcp", "pinpoint-test-udp",
}


def main() -> int:
    """Validate the target and execute one non-interactive remote systemctl action."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--target", required=True)
    parser.add_argument("--unit", required=True, choices=sorted(ALLOWED_UNITS))
    parser.add_argument("--action", required=True, choices=sorted(ALLOWED_ACTIONS))
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    try:
        target = config["targets"][args.target]
        key = os.environ[target["ssh_key_env"]]
    except KeyError as exc:
        parser.error(f"Missing target configuration or SSH key environment variable: {exc}")
    try:
        network = ipaddress.ip_network(config["lab_network"], strict=True)
        address = ipaddress.ip_address(target["address"])
    except ValueError as exc:
        parser.error(f"Invalid lab network or target address: {exc}")
    if (
        not isinstance(network, ipaddress.IPv4Network)
        or not network.is_private
        or network.prefixlen < 28
        or address not in network
    ):
        parser.error("Refusing remote control outside the approved private /28 lab.")
    command = [
        "ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-i", key, f"{target['ssh_user']}@{target['address']}",
        "sudo", "-n", "systemctl", args.action, args.unit,
    ]
    result = subprocess.run(command, check=False)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
