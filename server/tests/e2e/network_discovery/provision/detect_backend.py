#!/usr/bin/env python3
"""Read-only detection of supported disposable-target backends."""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
import shutil
import subprocess
from pathlib import Path


def command_path(name: str, fallbacks: tuple[str, ...] = ()) -> str | None:
    """Return a PATH command or an existing explicit fallback."""
    found = shutil.which(name)
    if found:
        return found
    for candidate in fallbacks:
        if Path(candidate).is_file():
            return candidate
    return None


def probe(argv: list[str]) -> bool:
    """Return whether a read-only backend probe completes successfully."""
    if not argv[0]:
        return False
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, timeout=10, check=False,
        ).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def domain_type(domain_xml: str) -> str | None:
    """Return a libvirt domain's accelerator ("kvm", "qemu", ...) from its XML."""
    try:
        return ET.fromstring(domain_xml).get("type")
    except ET.ParseError:
        return None


def guest_accelerators(virsh: str) -> dict[str, str | None]:
    """Map every libvirt domain name to its accelerator type (read-only)."""
    try:
        names = subprocess.run(
            [virsh, "list", "--all", "--name"], capture_output=True, text=True, timeout=10, check=False,
        ).stdout.split()
        return {
            name: domain_type(subprocess.run(
                [virsh, "dumpxml", name], capture_output=True, text=True, timeout=10, check=False,
            ).stdout)
            for name in names
        }
    except (OSError, subprocess.TimeoutExpired):
        return {}


def env01_failures(kvm_device: bool, accelerators: dict[str, str | None]) -> list[str]:
    """ENV-01: /dev/kvm must exist and no guest may run under software emulation."""
    failures = [] if kvm_device else ["/dev/kvm is missing"]
    failures += [
        f"guest {name} uses '{kind}' instead of 'kvm'"
        for name, kind in sorted(accelerators.items()) if kind != "kvm"
    ]
    return failures


def detect() -> dict[str, object]:
    """Return backend command presence separately from usable daemon access."""
    virsh = command_path("virsh")
    virt_install = command_path("virt-install")
    incus = command_path("incus")
    lxc = command_path("lxc", ("/snap/bin/lxc",))
    docker = command_path("docker")
    accelerators = guest_accelerators(virsh) if virsh else {}
    return {
        "guest_accelerators": accelerators,
        "kvm_device": Path("/dev/kvm").exists(),
        "virsh": {"path": virsh, "usable": probe([virsh, "list"]) if virsh else False},
        "virt_install": {"path": virt_install},
        "incus": {"path": incus, "usable": probe([incus, "info"]) if incus else False},
        "lxc": {"path": lxc, "usable": probe([lxc, "info"]) if lxc else False},
        "docker": {"path": docker, "usable": probe([docker, "info"]) if docker else False},
        "preprovisioned_supported": True,
    }


if __name__ == "__main__":
    result = detect()
    print(json.dumps(result, indent=2, sort_keys=True))
    if "--require-kvm" in sys.argv:
        problems = env01_failures(result["kvm_device"], result["guest_accelerators"])
        for problem in problems:
            print(f"ENV-01 FAIL: {problem}", file=sys.stderr)
        sys.exit(1 if problems else 0)
