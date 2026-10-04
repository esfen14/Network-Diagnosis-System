"""Live discovery settings, run orchestration, and SQLite inventory checks."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .common import HarnessError, resolve_config_path
from .pinpoint import PinpointClient


def desired_settings(config: dict[str, Any]) -> dict[str, Any]:
    """Build the exact Pinpoint discovery-settings API payload."""
    discovery = config["discovery"]
    return {
        "networks": [config["lab_network"]],
        "tcpPorts": discovery["tcp_ports"],
        "udpPorts": discovery["udp_ports"],
        "tcpServiceOverrides": discovery["tcp_service_overrides"],
        "udpServiceOverrides": discovery["udp_service_overrides"],
    }


def run_discovery(client: PinpointClient, config: dict[str, Any], apply_settings: bool) -> dict[str, Any]:
    """Optionally apply approved settings, start a run, and wait for completion."""
    desired = desired_settings(config)
    current = client.discovery_settings()["settings"]
    comparable = {key: current.get(key) for key in desired}
    if comparable != desired:
        if not apply_settings:
            raise HarnessError("Discovery settings differ; rerun with --apply-settings after review.")
        client.update_discovery_settings(desired)

    previous = client.discovery_status()
    previous_id = int(previous["id"]) if previous and previous.get("id") is not None else 0
    client.start_discovery()

    discovery = config["discovery"]
    # The status record is created by the background thread, so wait briefly
    # for a new id before beginning terminal-state polling.
    import time
    deadline = time.monotonic() + 30
    new_status = None
    while time.monotonic() < deadline:
        candidate = client.discovery_status()
        if candidate and int(candidate.get("id", 0)) > previous_id:
            new_status = candidate
            break
        time.sleep(1)
    if new_status is None:
        raise HarnessError("Discovery started but no new status record appeared.")

    return client.wait_for_discovery(
        int(new_status["id"]),
        int(discovery["timeout_seconds"]),
        int(discovery["poll_seconds"]),
    )


def read_inventory(config_path: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    """Read discovered hosts and open services from the application database."""
    database = resolve_config_path(config_path, config["databases"]["system"])
    if not database.is_file():
        raise HarnessError(f"System database not found: {database}")
    uri = f"file:{database}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            'SELECT NetDiscoveryID, Hostname, IP_Address, Network, OS_Type, NCPA_Eligible '
            'FROM NETWORK_DISCOVERY ORDER BY IP_Address'
        ).fetchall()
        inventory = []
        for row in rows:
            tcp = connection.execute(
                'SELECT Port_Number, Service_Name FROM OPEN_TCP_Services '
                'WHERE NetDiscoveryID = ? ORDER BY Port_Number',
                (row["NetDiscoveryID"],),
            ).fetchall()
            udp = connection.execute(
                'SELECT Port_Number, Service_Name FROM OPEN_UDP_Services '
                'WHERE NetDiscoveryID = ? ORDER BY Port_Number',
                (row["NetDiscoveryID"],),
            ).fetchall()
            inventory.append({
                "id": row["NetDiscoveryID"],
                "hostname": row["Hostname"],
                "address": row["IP_Address"],
                "network": row["Network"],
                "os": row["OS_Type"],
                "ncpa_eligible": bool(row["NCPA_Eligible"]),
                "tcp": [{"port": item["Port_Number"], "service": item["Service_Name"]} for item in tcp],
                "udp": [{"port": item["Port_Number"], "service": item["Service_Name"]} for item in udp],
            })
        return inventory
    except sqlite3.Error as exc:
        raise HarnessError(f"Cannot read discovery inventory: {exc}") from exc
    finally:
        if "connection" in locals():
            connection.close()


def compare_inventory(
    config: dict[str, Any], inventory: list[dict[str, Any]],
    baseline: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Compare targets while distinguishing retained baseline inventory from new rows."""
    by_address = {item["address"]: item for item in inventory}
    baseline_by_address = {item["address"]: item for item in (baseline or [])}
    errors = []
    expected_addresses = {target["address"] for target in config["targets"].values()}
    unexpected = sorted(
        set(by_address) - expected_addresses - set(baseline_by_address)
        - {config["pinpoint"]["address"]}
    )
    if unexpected:
        errors.append(f"Unexpected discovered addresses: {', '.join(unexpected)}")
    for name, target in config["targets"].items():
        item = by_address.get(target["address"])
        if item is None:
            errors.append(f"{name} ({target['address']}) was not discovered")
            continue
        actual_tcp = {entry["port"] for entry in item["tcp"]}
        actual_udp = {entry["port"] for entry in item["udp"]}
        for protocol, actual, key in (
            ("TCP", actual_tcp, "expected_tcp_ports"),
            ("UDP", actual_udp, "expected_udp_ports"),
        ):
            expected = set(target.get(key, []))
            missing = sorted(expected - actual)
            retained = {
                entry["port"] for entry in baseline_by_address.get(target["address"], {}).get(protocol.lower(), [])
            }
            extra = sorted(actual - expected - retained)
            if missing:
                errors.append(f"{name} missing {protocol} ports: {missing}")
            if extra:
                errors.append(f"{name} unexpected {protocol} ports: {extra}")
    return errors


def read_skipped_services(
    config_path: Path,
    config: dict[str, Any],
    discovery_status_id: int,
) -> list[dict[str, Any]]:
    """Return skipped services recorded for one discovery run."""
    database = resolve_config_path(config_path, config["databases"]["system"])
    uri = f"file:{database}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            'SELECT Hostname, IP_Address, Port_Number, Protocol, Service_Name, Reason '
            'FROM SKIPPED_SERVICE WHERE DiscoveryStatusID = ? '
            'ORDER BY IP_Address, Port_Number',
            (discovery_status_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    except sqlite3.Error as exc:
        raise HarnessError(f"Cannot read skipped-service evidence: {exc}") from exc
    finally:
        if "connection" in locals():
            connection.close()


def compare_skipped_services(config: dict[str, Any], skipped: list[dict[str, Any]]) -> list[str]:
    """Return mismatches for explicitly expected skipped UDP ports."""
    actual = {
        (str(item.get("IP_Address")), int(item.get("Port_Number")), str(item.get("Protocol")))
        for item in skipped
    }
    errors = []
    for name, target in config["targets"].items():
        for port in target.get("expected_skipped_udp_ports", []):
            if (target["address"], port, "UDP") not in actual:
                errors.append(f"{name} UDP port {port} was not recorded as skipped")
    return errors


def write_inventory(path: Path, inventory: list[dict[str, Any]]) -> None:
    """Write sanitized discovery inventory evidence."""
    path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
