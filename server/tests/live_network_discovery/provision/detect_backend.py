#!/usr/bin/env python3
"""Read-only detection of supported disposable-target backends."""

from __future__ import annotations

import json
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


def detect() -> dict[str, object]:
    """Return backend command presence separately from usable daemon access."""
    virsh = command_path("virsh")
    virt_install = command_path("virt-install")
    incus = command_path("incus")
    lxc = command_path("lxc", ("/snap/bin/lxc",))
    docker = command_path("docker")
    return {
        "kvm_device": Path("/dev/kvm").exists(),
        "virsh": {"path": virsh, "usable": probe([virsh, "list"]) if virsh else False},
        "virt_install": {"path": virt_install},
        "incus": {"path": incus, "usable": probe([incus, "info"]) if incus else False},
        "lxc": {"path": lxc, "usable": probe([lxc, "info"]) if lxc else False},
        "docker": {"path": docker, "usable": probe([docker, "info"]) if docker else False},
        "preprovisioned_supported": True,
    }


if __name__ == "__main__":
    print(json.dumps(detect(), indent=2, sort_keys=True))
