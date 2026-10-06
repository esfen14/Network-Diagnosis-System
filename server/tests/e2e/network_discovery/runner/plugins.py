"""Plugin-driven monitoring checks that compare what Pinpoint promised with what exists."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import guards, nagios
from .common import BlockedError, HarnessError
from .pinpoint import PinpointClient


def enable_and_verify(
    client: PinpointClient, config: dict[str, Any], run_dir: Path, plugin_name: str,
) -> dict[str, Any]:
    """
    Enable one plugin and prove the preview told the truth (O-2, F-01): the
    preview counts equal the services Pinpoint lists, equal the new service
    blocks in hosts.cfg, and Nagios accepts the result. Returns evidence.
    """
    plugin = client.plugin_by_name(plugin_name)
    preview = client.enable_preview(plugin["id"])
    if preview.get("already_enabled"):
        raise BlockedError(
            f"{plugin_name} is already enabled, so its preview cannot be compared with a new enable; disable it first.")
    hosts_config = config["nagios"].get("host_config")
    before = guards.count_services(Path(hosts_config)) if hosts_config else None
    outcome = client.enable_plugin(plugin["id"])
    apply = outcome.get("auto_apply") or {}
    if apply.get("success") is not True:
        raise HarnessError(f"Nagios was not updated after enabling {plugin_name}: {apply.get('message')}")
    services = client.plugin_services(plugin["id"])
    problems = []
    if len(services) != preview.get("matched_services"):
        problems.append(f"preview said {preview.get('matched_services')} services, Pinpoint lists {len(services)}")
    devices = {(item.get("device") or {}).get("id") for item in services}
    if len(devices) != preview.get("matched_devices"):
        problems.append(f"preview said {preview.get('matched_devices')} devices, Pinpoint lists {len(devices)}")
    delta = None
    if before is not None:
        delta = guards.count_services(Path(hosts_config)) - before
        if delta != preview.get("matched_services"):
            problems.append(f"hosts.cfg gained {delta} services, preview said {preview.get('matched_services')}")
    nagios.validate(config, run_dir / "evidence" / f"nagios-validate-{plugin_name}.txt")
    evidence = {"plugin": plugin_name, "preview": preview, "listed": len(services),
                "devices": len(devices), "hosts_cfg_delta": delta, "problems": problems}
    if problems:
        raise HarnessError(f"Enable preview did not match the result for {plugin_name}: " + "; ".join(problems))
    return evidence
