#!/usr/bin/env python3
"""Install pinned pytest dependencies into an isolated writable directory."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Use uv with an offline wheelhouse or explicit network authorization."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, type=Path, help="Application test interpreter")
    parser.add_argument("--target", required=True, type=Path, help="Writable dependency directory")
    parser.add_argument("--wheelhouse", type=Path, help="Directory containing offline wheels")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    uv = shutil.which("uv")
    if uv is None:
        parser.error("uv is required because the installed interpreter may not contain pip.")
    if not args.python.is_file():
        parser.error(f"Interpreter not found: {args.python}")
    if args.wheelhouse is None and not args.allow_network:
        parser.error("Provide --wheelhouse for offline installation or explicitly use --allow-network.")
    if args.wheelhouse is not None and not args.wheelhouse.is_dir():
        parser.error(f"Wheelhouse not found: {args.wheelhouse}")

    target = args.target.expanduser().resolve()
    if str(target) in {"/", "/home", "/tmp"}:
        parser.error("--target must be a specific writable dependency directory.")

    requirements = Path(__file__).resolve().parents[4] / "requirements-test.txt"
    command = [
        uv, "pip", "install", "--python", str(args.python),
        "--target", str(target), "-r", str(requirements),
    ]
    if args.wheelhouse is not None:
        command.extend(["--no-index", "--find-links", str(args.wheelhouse)])

    print("Prepared isolated dependency installation:")
    print(" ".join(command))
    if not args.apply:
        print("Preview only. Add --apply after reviewing the paths and source.")
        return 0
    target.mkdir(parents=True, exist_ok=True)
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
