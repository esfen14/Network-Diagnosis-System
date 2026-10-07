import ipaddress
import subprocess

import sqlalchemy as sa
from flask import request, current_app
from flask_login import login_required, current_user

from app import db
from app.api.system import system_bp
from app.api.helper import success, error, validate_json_data
from app.api.helper.database_access.permissions import require_permission
from app.network_discovery.discovery_settings import get_discovery_setting
from app.system_models import (
    DeviceState, NetworkDiscovery, NetworkProfile, Open_TCP_Services, Open_UDP_Services, PortState,
)
from app.logging.user_activity import create_user_log
from app.api.helper.settings_flags import is_audit_logging_enabled

DEFAULT_NAME = "CICT Network"
DEFAULT_REFERENCE = ""
DETAIL_LABELS = ("IP Range", "Gateway Device", "Subnet Mask", "DNS Server", "ISP", "Location")
# Only these are typed in by an administrator; the rest are derived from the
# scanned networks and discovered devices every time the profile is read.
EDITABLE_DETAILS = ("ISP", "Location")
DERIVED_DETAILS = tuple(label for label in DETAIL_LABELS if label not in EDITABLE_DETAILS)
NOT_DETECTED = "Not detected"
DNS_PORT = 53
DEFAULT_DETAILS = {label: "" for label in DETAIL_LABELS}
MAX_NAME = 100
MAX_REFERENCE = 50
MAX_DETAIL = 100


def _scanned_networks():
    """The configured scan networks as IPv4Network objects; entries that do not parse are skipped."""
    networks = []
    for entry in get_discovery_setting("NETWORKS") or []:
        try:
            network = ipaddress.ip_network(str(entry).strip(), strict=False)
        except ValueError:
            continue
        if network.version == 4:
            networks.append(network)
    return networks


def _usable_range(network):
    hosts = list(network.hosts()) if network.num_addresses > 2 else []
    first, last = (hosts[0], hosts[-1]) if hosts else (network.network_address, network.broadcast_address)
    return first, last


def _local_default_gateway():
    """IPv4 default gateway of the machine running Pinpoint, or None when it cannot be read."""
    try:
        with open("/proc/net/route") as route_table:
            for line in list(route_table)[1:]:
                fields = line.split()
                if len(fields) > 2 and fields[1] == "00000000" and int(fields[3], 16) & 2:
                    return ipaddress.ip_address(int(fields[2], 16).to_bytes(4, "little"))
    except (OSError, ValueError):
        pass
    try:
        output = subprocess.run(
            ["route", "-n", "get", "default"], capture_output=True, text=True, timeout=3
        ).stdout
        for line in output.splitlines():
            if line.strip().startswith("gateway:"):
                return ipaddress.ip_address(line.split(":", 1)[1].strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None


def _device_label(device):
    name = device.Display_Name or device.Hostname
    return f"{name} - {device.IP_Address}" if name else device.IP_Address


def _active_devices():
    return db.session.scalars(
        sa.select(NetworkDiscovery).where(NetworkDiscovery.Device_State == DeviceState.ACTIVE)
    ).all()


def _gateway_device(networks, devices):
    """
    The router: the machine's own default gateway when it is inside a scanned
    network, otherwise the discovered device sitting on the first or last
    usable address of one (the usual router addresses).
    """
    by_ip = {d.IP_Address: d for d in devices}
    candidates = []
    local = _local_default_gateway()
    if local is not None and any(local in network for network in networks):
        candidates.append(str(local))
    for network in networks:
        first, last = _usable_range(network)
        candidates += [str(first), str(last)]
    for ip in candidates:
        if ip in by_ip:
            return _device_label(by_ip[ip])
    if candidates and local is not None and str(local) == candidates[0]:
        return str(local)
    return NOT_DETECTED


def _dns_servers(devices):
    """Discovered devices that answer on port 53, as hostname - ip (comma separated)."""
    ids = set()
    for model in (Open_UDP_Services, Open_TCP_Services):
        ids.update(db.session.scalars(
            sa.select(model.NetDiscoveryID).where(
                model.Port_Number == DNS_PORT, model.Port_State == PortState.MONITORED
            )
        ))
    found = sorted(
        (d for d in devices if d.NetDiscoveryID in ids),
        key=lambda d: ipaddress.ip_address(d.IP_Address),
    )
    return ", ".join(_device_label(d) for d in found) or NOT_DETECTED


def derived_details():
    """IP Range, Subnet Mask, Gateway Device and DNS Server, worked out from the scan settings and discovered devices."""
    networks = _scanned_networks()
    devices = _active_devices()
    if not networks:
        return {label: NOT_DETECTED for label in DERIVED_DETAILS}
    ranges = [_usable_range(network) for network in networks]
    return {
        "IP Range": ", ".join(f"{first} - {last}" for first, last in ranges),
        "Subnet Mask": ", ".join(dict.fromkeys(str(network.netmask) for network in networks)),
        "Gateway Device": _gateway_device(networks, devices),
        "DNS Server": _dns_servers(devices),
    }


def _serialize(row):
    details = dict(DEFAULT_DETAILS)
    if row is not None and row.Details:
        details.update({k: v for k, v in row.Details.items() if k in EDITABLE_DETAILS})
    details.update(derived_details())
    return {
        "name": row.Name if row is not None else DEFAULT_NAME,
        "reference": (row.Reference or "") if row is not None else DEFAULT_REFERENCE,
        "details": [
            {"label": label, "value": details[label], "derived": label in DERIVED_DETAILS}
            for label in DETAIL_LABELS
        ],
    }


@system_bp.get('/network-profile')
@login_required
@require_permission('system.network_health')
def get_network_profile():
    try:
        return success(_serialize(db.session.get(NetworkProfile, 1)))
    except Exception:
        current_app.logger.exception("An unexpected error occurred while fetching the network profile.")
        return error("An unexpected error occurred.", 500)


@system_bp.put('/network-profile')
@login_required
@require_permission('settings.discovery')
def update_network_profile():
    data = request.get_json(silent=True)
    err = validate_json_data(data)
    if err is not None:
        return err

    name = data.get("name")
    reference = data.get("reference", "")
    details = data.get("details")
    if not isinstance(name, str) or not name.strip():
        return error("Network name is required.", 400)
    if len(name.strip()) > MAX_NAME:
        return error(f"Network name must be {MAX_NAME} characters or fewer.", 400)
    if not isinstance(reference, str) or len(reference.strip()) > MAX_REFERENCE:
        return error(f"Reference must be {MAX_REFERENCE} characters or fewer.", 400)
    if not isinstance(details, list):
        return error("Details must be a list.", 400)

    cleaned = {}
    for item in details:
        if not isinstance(item, dict) or item.get("label") not in DETAIL_LABELS:
            return error("Unknown detail field.", 400)
        if item["label"] in DERIVED_DETAILS:
            continue  # worked out automatically; never stored
        value = item.get("value", "")
        if not isinstance(value, str) or len(value.strip()) > MAX_DETAIL:
            return error(f"{item['label']} must be {MAX_DETAIL} characters or fewer.", 400)
        cleaned[item["label"]] = value.strip()

    try:
        row = db.session.get(NetworkProfile, 1)
        if row is None:
            row = NetworkProfile(Id=1, Name=name.strip())
            db.session.add(row)
        row.Name = name.strip()
        row.Reference = reference.strip()
        row.Details = cleaned
        row.Updated_By = current_user.UserID
        if is_audit_logging_enabled():
            create_user_log(current_user.UserID, f"Updated network profile '{row.Name}'")
        db.session.commit()
        return success(_serialize(row), message="Network profile saved.")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("An unexpected error occurred while saving the network profile.")
        return error("An unexpected error occurred.", 500)
