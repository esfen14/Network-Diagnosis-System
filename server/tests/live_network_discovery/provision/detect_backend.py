#!/usr/bin/env python3
"""Read-only detection of supported disposable-target backends."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


def detect() -> dict[str, object]:
    """Return available backend commands and KVM device access."""
    return {
        "kvm_device": Path("/dev/kvm").exists(),
        "virsh": shutil.which("virsh"),
        "virt_install": shutil.which("virt-install"),
        "incus": shutil.which("incus"),
        "lxc": shutil.which("lxc"),
        "docker": shutil.which("docker"),
    }


if __name__ == "__main__":
    print(json.dumps(detect(), indent=2, sort_keys=True))
