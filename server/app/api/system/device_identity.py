"""
Device identity API: address history, identifiers, merge, retire, port state
and the "needs review" list produced by network discovery.

These are the routes behind the Device Inventory changes in
"spec files/DHCP_Device_Identity_Plan.md" section 11. Reading needs
``system.hosts``; anything that changes a device needs ``system.hosts.edit``
and writes an activity-log entry. Changes that affect the Nagios config
(merge, retire, a port becoming or ceasing to be monitored) regenerate
hosts.cfg and report whether Nagios was updated.

Routes
------
GET  /system/hosts/<id>/addresses
    Address history of a device (current address first).

GET  /system/hosts/<id>/identifiers
    Identity evidence and confidence of a device.

PUT  /system/hosts/<id>
    Change a device's display name and/or addressing mode.

POST /system/hosts/<id>/merge
    Merge this device into another.

POST /system/hosts/<id>/retire
    Retire a device (removed from Nagios, record and history kept).

PUT  /system/hosts/<id>/ports/<proto>/<port>
    Change a port's state, pin its service, or add a port by hand.

GET  /system/discover/review
    Conflicts and possible duplicates raised by discovery.

POST /system/discover/review/<id>/resolve
    Mark a review item as dealt with.
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from flask import current_app, request
from flask_login import current_user, login_required

from app import db
from app.api.helper import error, success, validate_json_data
from app.api.helper.database_access.permissions import require_permission
from app.api.system import system_bp
from app.logging.user_activity import create_user_log
from app.api.plugin.reconcile import reconcile_plugin_monitoring
from app.network_discovery.device_identity import (
    close_address,
    nagios_host_name,
    recompute_confidence,
)
from app.network_discovery.discovery_settings import SERVICE_NAME_PATTERN
from app.network_discovery.port_lifecycle import (
    acknowledge_port_mismatch,
    add_user_port,
    pin_port_service,
    port_model,
    set_port_state,
)
from app.plugin_models import PluginConfiguration, PluginConfigurationOrigin
from app.system_models import (
    AddressingMode,
    DeviceAddressHistory,
    DeviceIdentifier,
    DeviceReviewItem,
    DeviceState,
    IdentifierKind,
    NCPADeployment,
    NetworkDiscovery,
    PortState,
    SSHCredentials,
)

USER_PORT_STATES = {
    "MONITORED": PortState.MONITORED,
    "SUGGESTED": PortState.SUGGESTED,
    "IGNORED": PortState.IGNORED,
    "ARCHIVED": PortState.ARCHIVED,
}


# ==========================================================
# HELPERS
# ==========================================================

def get_device_or_404(id):
    """Return (device, None), or (None, error response) if there is no such device."""
    device = db.session.get(NetworkDiscovery, id)
    if device is None:
        return None, error("Device not found.", 404)
    return device, None


def apply_config_change():
    """
    Bring Nagios in line after a change that affects it (a port edit, merge or
    retire): the plugin reconciler promotes and attaches ports, then regenerates
    and applies hosts.cfg through the shared writer. Never raises: returns
    {"config_applied": bool, "config_message": str} so the caller can report it
    next to a database change that has already been saved.
    """
    try:
        result = reconcile_plugin_monitoring(current_user.UserID)
    except Exception:
        current_app.logger.exception("Could not regenerate the Nagios config.")
        return {"config_applied": False, "config_message": "The change was saved but the Nagios config could not be updated."}
    return {"config_applied": result["changed"], "config_message": result["message"]}


def serialize_device_summary(device):
    return {
        "id": device.NetDiscoveryID,
        "nagios_host_name": nagios_host_name(device),
        "display_name": device.Display_Name,
        "ip_address": device.IP_Address,
        "state": device.Device_State.name,
    }


# ==========================================================
# READ
# ==========================================================

@system_bp.get('/hosts/<int:id>/addresses')
@login_required
@require_permission('system.hosts')
def get_device_addresses(id):
    """
    Return every address the device has been seen at, newest first. The row
    with "current": true (Closed_At is null) is where Nagios checks it now;
    the UI shows the latest closed row as "IP changed from X to Y".
    """
    device, err = get_device_or_404(id)
    if err is not None:
        return err

    rows = db.session.scalars(
        sa.select(DeviceAddressHistory)
        .where(DeviceAddressHistory.NetDiscoveryID == id)
        .order_by(DeviceAddressHistory.First_Seen_At.desc(), DeviceAddressHistory.AddressID.desc())
    ).all()

    items = []
    for row in rows:
        items.append({
            "id": row.AddressID,
            "ip_address": row.IP_Address,
            "network": row.Network,
            "mac_address": row.MAC_Address,
            "source": row.Source.name,
            "first_seen_at": row.First_Seen_At.isoformat(),
            "last_seen_at": row.Last_Seen_At.isoformat(),
            "closed_at": row.Closed_At.isoformat() if row.Closed_At else None,
            "current": row.Closed_At is None,
        })

    return success({"device": serialize_device_summary(device), "addresses": items})


@system_bp.get('/hosts/<int:id>/identifiers')
@login_required
@require_permission('system.hosts')
def get_device_identifiers(id):
    """
    Return the device's identity confidence and the evidence behind it, plus
    its addressing mode, so the UI can show a badge with an explanation. A
    machine-id is shown masked. For an Unverified device "recommendation" suggests a DHCP reservation or NCPA.
    """
    device, err = get_device_or_404(id)
    if err is not None:
        return err

    rows = db.session.scalars(
        sa.select(DeviceIdentifier)
        .where(DeviceIdentifier.NetDiscoveryID == id)
        .order_by(DeviceIdentifier.Kind, DeviceIdentifier.IdentifierID)
    ).all()

    items = []
    for row in rows:
        value = row.Value
        if row.Kind is IdentifierKind.MACHINE_ID:
            # /etc/machine-id is meant to stay semi-confidential; enough to
            # tell devices apart, not enough to reuse.
            value = value[:8] + "..."
        items.append({
            "id": row.IdentifierID,
            "kind": row.Kind.name,
            "value": value,
            "strong": row.Is_Strong,
            "first_seen_at": row.First_Seen_At.isoformat(),
            "last_seen_at": row.Last_Seen_At.isoformat(),
        })

    recommendation = None
    if device.Identity_Confidence.name == "UNVERIFIED":
        recommendation = "Set a DHCP reservation for this device, or deploy NCPA, so it can be followed if its IP changes."

    return success({
        "device": serialize_device_summary(device),
        "confidence": device.Identity_Confidence.name,
        "addressing": device.Addressing.name,
        "mac_address": device.MAC_Address,
        "identifiers": items,
        "recommendation": recommendation,
    })


@system_bp.get('/discover/review')
@login_required
@require_permission('system.discover')
def get_discovery_review():
    """
    Return the unresolved review items raised by discovery: conflicting
    identifiers, identity changes, IP reuse, duplicate identities and static
    devices that moved. Each lists the devices involved so the UI can offer
    Merge or Retire. Newest first.
    """
    rows = db.session.scalars(
        sa.select(DeviceReviewItem)
        .where(DeviceReviewItem.Resolved_At.is_(None))
        .order_by(DeviceReviewItem.Created_At.desc(), DeviceReviewItem.ReviewID.desc())
    ).all()

    items = []
    for row in rows:
        devices = []
        for device_id in row.Candidate_Device_IDs or []:
            device = db.session.get(NetworkDiscovery, device_id)
            if device is not None:
                devices.append(serialize_device_summary(device))

        items.append({
            "id": row.ReviewID,
            "kind": row.Kind.name,
            "ip_address": row.IP_Address,
            "mac_address": row.MAC_Address,
            "message": row.Message,
            "devices": devices,
            "created_at": row.Created_At.isoformat(),
        })

    return success({"items": items})


# ==========================================================
# EDIT
# ==========================================================

@system_bp.put('/hosts/<int:id>')
@login_required
@require_permission('system.hosts.edit')
def edit_device(id):
    """
    Change the device's display name and/or addressing mode. The display name
    is only a label: it never changes the Nagios host_name. Fields that are
    not sent are left alone.

    JSON Format
    {
        "display_name": "Front desk printer",
        "addressing": "DHCP"
    }
    "addressing" is one of DHCP, STATIC, UNKNOWN. "display_name" may be null
    to clear it.
    """
    data = request.get_json()
    err = validate_json_data(data)
    if err is not None:
        return err

    device, err = get_device_or_404(id)
    if err is not None:
        return err

    if "display_name" in data:
        name = data["display_name"]
        if name is not None and (not isinstance(name, str) or len(name.strip()) > 100):
            return error("display_name must be text of at most 100 characters.", 400)
        device.Display_Name = (name.strip() or None) if name is not None else None

    if "addressing" in data:
        mode = AddressingMode.__members__.get(str(data["addressing"]).upper())
        if mode is None:
            return error("addressing must be DHCP, STATIC or UNKNOWN.", 400)
        device.Addressing = mode

    create_user_log(current_user.UserID, f"Edited device {nagios_host_name(device)}")
    db.session.commit()
    return success({"device": serialize_device_summary(device)}, message="Device updated.")


@system_bp.post('/hosts/<int:id>/retire')
@login_required
@require_permission('system.hosts.edit')
def retire_device(id):
    """
    Retire a device: it is removed from the Nagios config but its record,
    identifiers, address history and monitoring history are kept, and it
    comes back automatically if a later scan recognises it. No body.
    """
    device, err = get_device_or_404(id)
    if err is not None:
        return err

    if device.Device_State in (DeviceState.RETIRED, DeviceState.MERGED):
        return error("Device is already retired or merged.", 400)

    device.Device_State = DeviceState.RETIRED
    close_address(device)
    create_user_log(current_user.UserID, f"Retired device {nagios_host_name(device)}")
    db.session.commit()

    return success(apply_config_change(), message="Device retired.")


@system_bp.post('/hosts/<int:id>/merge')
@login_required
@require_permission('system.hosts.edit')
def merge_device(id):
    """
    Merge this device (the duplicate) into another. The duplicate's
    identifiers, address history and ports move to the target, plugin
    configurations are re-pointed at the target, and the duplicate becomes
    MERGED and leaves the Nagios config. Monitoring history stored under the
    duplicate's old Nagios host name is not carried over. Ports the target
    already has are kept as they are.

    JSON Format
    {
        "target_id": 12
    }
    """
    data = request.get_json()
    err = validate_json_data(data)
    if err is not None:
        return err

    target_id = data.get("target_id")
    if not isinstance(target_id, int) or isinstance(target_id, bool):
        return error("target_id must be an integer.", 400)
    if target_id == id:
        return error("A device cannot be merged into itself.", 400)

    source, err = get_device_or_404(id)
    if err is not None:
        return err
    target = db.session.get(NetworkDiscovery, target_id)
    if target is None:
        return error("Target device not found.", 404)

    if source.Device_State is DeviceState.MERGED:
        return error("Device is already merged.", 400)
    if target.Device_State in (DeviceState.MERGED, DeviceState.RETIRED):
        return error("The target device is retired or merged.", 400)

    source_name = nagios_host_name(source)
    target_name = nagios_host_name(target)

    # Identifiers: strong ones are unique, so they move as they are; a weak
    # one the target already has is dropped.
    target_identifiers = {
        (row.Kind, row.Value)
        for row in db.session.scalars(
            sa.select(DeviceIdentifier).where(DeviceIdentifier.NetDiscoveryID == target_id)
        ).all()
    }
    for row in db.session.scalars(
        sa.select(DeviceIdentifier).where(DeviceIdentifier.NetDiscoveryID == id)
    ).all():
        if (row.Kind, row.Value) in target_identifiers:
            db.session.delete(row)
        else:
            row.NetDiscoveryID = target_id

    # Address history: the target keeps its own open row; moved rows are closed.
    now = datetime.now(timezone.utc)
    for row in db.session.scalars(
        sa.select(DeviceAddressHistory).where(DeviceAddressHistory.NetDiscoveryID == id)
    ).all():
        row.NetDiscoveryID = target_id
        if row.Closed_At is None:
            row.Closed_At = now

    # Ports: keep the target's row when both have the port.
    for protocol in ("tcp", "udp"):
        model = port_model(protocol)
        target_ports = {
            port for port in db.session.scalars(
                sa.select(model.Port_Number).where(model.NetDiscoveryID == target_id)
            ).all()
        }
        for port in db.session.scalars(
            sa.select(model).where(model.NetDiscoveryID == id)
        ).all():
            if port.Port_Number in target_ports:
                db.session.delete(port)
            else:
                port.NetDiscoveryID = target_id

    # NCPA records move only if the target has none of its own.
    for model, column in (
        (SSHCredentials, SSHCredentials.NetworkDiscoveryID),
        (NCPADeployment, NCPADeployment.NetworkDiscoveryID),
    ):
        target_has = db.session.scalar(sa.select(model).where(column == target_id)) is not None
        if not target_has:
            for row in db.session.scalars(sa.select(model).where(column == id)).all():
                row.NetworkDiscoveryID = target_id
    if source.NCPA_Eligible and not target.NCPA_Eligible:
        target.NCPA_Eligible = True

    for config in db.session.scalars(
        sa.select(PluginConfiguration).where(PluginConfiguration.NetDiscoveryID == id)
    ).all():
        if config.Origin is PluginConfigurationOrigin.AUTO:
            # Derived from ports: the reconciler rebuilds it for the target, and
            # moving it could collide with the target's own row for that service.
            db.session.delete(config)
        else:
            config.NetDiscoveryID = target_id

    # Review items about the duplicate are settled by merging it.
    for item in db.session.scalars(
        sa.select(DeviceReviewItem).where(DeviceReviewItem.Resolved_At.is_(None))
    ).all():
        if id in (item.Candidate_Device_IDs or []):
            item.Resolved_At = now

    source.Device_State = DeviceState.MERGED
    source.Merged_Into_ID = target_id
    db.session.flush()
    recompute_confidence(target)

    create_user_log(current_user.UserID, f"Merged device {source_name} into {target_name}")
    db.session.commit()

    return success(apply_config_change(), message="Devices merged.")


@system_bp.put('/hosts/<int:id>/ports/<proto>/<int:port>')
@login_required
@require_permission('system.hosts.edit')
def edit_device_port(id, proto, port):
    """
    Change one of the device's ports: its state, its service, or both.

    "service_name" pins the port's service on this device ("always treat
    this port as ..."): scans never rename it again, and a monitored port is
    re-frozen to the plugin for the new name. Making a port MONITORED
    freezes the plugin it is monitored with. If the device has no such port
    and the new state is MONITORED, the port is added by hand (this is how an
    ephemeral-range port gets monitored); "service_name" is then required.
    The NCPA port cannot be ignored or archived while an NCPA token is
    deployed. <proto> is tcp or udp.

    Setting a port to SUGGESTED holds it: no plugin promotes it until an admin
    makes it MONITORED. Ports Suggested at an upgrade that an enabled plugin
    would have picked up are held the same way (response "promotion_held").

    A port flagged "not used as intended" (the Port -> Service setting expects
    another service than nmap found) is not monitored until acknowledged:
    "acknowledge_mismatch": true accepts it as the service nmap found, and the
    port is then monitored if that service's plugin is enabled. Pinning a
    service or choosing MONITORED also settles the flag.

    JSON Format
    {
        "state": "MONITORED",
        "service_name": "http",
        "acknowledge_mismatch": true
    }
    "state" is one of MONITORED, SUGGESTED, IGNORED, ARCHIVED and may be
    left out when "service_name" or "acknowledge_mismatch" is sent.
    "service_name" is lowercase letters, digits, "-" or "_".
    """
    if proto.lower() not in ("tcp", "udp"):
        return error("Protocol must be tcp or udp.", 400)
    if not 1 <= port <= 65535:
        return error("Port must be between 1 and 65535.", 400)

    data = request.get_json()
    err = validate_json_data(data)
    if err is not None:
        return err

    state = None
    if data.get("state") is not None:
        state = USER_PORT_STATES.get(str(data.get("state")).upper())
        if state is None:
            return error("state must be MONITORED, SUGGESTED, IGNORED or ARCHIVED.", 400)

    service_name = data.get("service_name")
    if service_name is not None:
        if not isinstance(service_name, str) or not SERVICE_NAME_PATTERN.match(service_name.strip().lower()):
            return error("service_name must be lowercase letters, digits, '-' or '_'.", 400)
        service_name = service_name.strip().lower()

    acknowledge = data.get("acknowledge_mismatch")
    if acknowledge is not None and not isinstance(acknowledge, bool):
        return error("acknowledge_mismatch must be true or false.", 400)

    if state is None and service_name is None and not acknowledge:
        return error("Send a state, a service_name, acknowledge_mismatch, or a combination.", 400)

    device, err = get_device_or_404(id)
    if err is not None:
        return err

    model = port_model(proto)
    port_row = db.session.scalar(
        sa.select(model).where(model.NetDiscoveryID == id, model.Port_Number == port)
    )

    if port_row is None:
        if state is not PortState.MONITORED or service_name is None:
            return error("Device has no such port. To add one, set state MONITORED and send service_name.", 404)
        port_row = add_user_port(id, proto, port, service_name)
        action = f"Added {proto.lower()} port {port} on {nagios_host_name(device)} as {service_name}"
    else:
        # Pin first so a port made MONITORED below freezes the pinned service's plugin.
        port_label = f"{proto.lower()} port {port} on {nagios_host_name(device)}"
        if acknowledge:
            expected = port_row.Expected_Service_Name
            try:
                acknowledge_port_mismatch(id, proto, port)
            except ValueError as e:
                db.session.rollback()
                return error(str(e), 400)
        if service_name is not None:
            pin_port_service(id, proto, port, service_name)
        if state is not None:
            try:
                set_port_state(id, proto, port, state)
            except ValueError as e:
                db.session.rollback()
                return error(str(e), 400)

        if acknowledge:
            action = f"Acknowledged {port_label} as {port_row.Service_Name}, not the expected {expected}"
        elif service_name is None:
            action = f"Set {port_label} to {state.value}"
        elif state is None:
            action = f"Pinned {port_label} as {service_name}"
        else:
            action = f"Pinned {port_label} as {service_name} and set it to {state.value}"

    create_user_log(current_user.UserID, action)
    db.session.commit()

    result = apply_config_change()
    result["port"] = {
        "number": port_row.Port_Number,
        "protocol": proto.lower(),
        "service_name": port_row.Service_Name,
        "plugin_name": port_row.Plugin_Name,
        "state": port_row.Port_State.name,
        "identified_by": port_row.Identified_By.name if port_row.Identified_By else None,
        "expected_service_name": port_row.Expected_Service_Name,
        "mismatch_acknowledged": port_row.Mismatch_Acknowledged_At is not None,
        "promotion_held": port_row.Promotion_Held,
    }
    return success(result, message="Port updated.")


# ==========================================================
# REVIEW ITEMS
# ==========================================================

@system_bp.post('/discover/review/<int:id>/resolve')
@login_required
@require_permission('system.hosts.edit')
def resolve_review_item(id):
    """
    Mark a review item as dealt with so it leaves the "needs review" list.
    It does not change any device; use merge or retire for that. No body.
    """
    item = db.session.get(DeviceReviewItem, id)
    if item is None:
        return error("Review item not found.", 404)

    if item.Resolved_At is None:
        item.Resolved_At = datetime.now(timezone.utc)
        create_user_log(current_user.UserID, f"Resolved device review item {id}")
        db.session.commit()

    return success(message="Review item resolved.")
