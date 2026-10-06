#!/usr/bin/env python3
"""Restore allow-listed remote services and remove fixture listeners after an interrupted live run."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Start each unique remote unit declared by the approved case manifest."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--no-fixtures", action="store_true", help="Do not stop the scenario fixture listeners.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))["cases"]
    helper = Path(__file__).resolve().parents[1] / "services" / "remote_service.py"
    commands = []
    for case in cases:
        if case.get("remote_unit"):
            commands.append((case["target"], case["remote_unit"]))
    failed = False
    for target, unit in sorted(set(commands)):
        command = [
            sys.executable, str(helper), "--config", str(args.config),
            "--target", target, "--unit", unit, "--action", "start",
        ]
        if args.dry_run:
            print(json.dumps(command))
        elif subprocess.run(command, check=False).returncode != 0:
            failed = True
    if not args.no_fixtures:
        # Stopping a fixture that is not running is a no-op, so this is safe to repeat.
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services"))
        from remote_service import FIXTURES
        config = json.loads(args.config.read_text(encoding="utf-8"))
        for target in sorted(config["targets"]):
            for fixture in sorted(FIXTURES):
                command = [
                    sys.executable, str(helper), "--config", str(args.config),
                    "--target", target, "--fixture", fixture, "--action", "stop",
                ]
                if args.dry_run:
                    print(json.dumps(command))
                elif subprocess.run(command, check=False).returncode != 0:
                    failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
