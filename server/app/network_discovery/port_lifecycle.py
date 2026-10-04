"""
Port lifecycle for Network Discovery.

A scan used to delete any port it did not see and turn every new port into a
Nagios service. Here a port instead moves through states (plan section 9):

    SUGGESTED  seen, not monitored yet           -> not in Nagios
    MONITORED  becomes a Nagios service          -> in Nagios
    MISSING    monitored but not seen lately     -> still in Nagios (CRITICAL is the right signal)
    ARCHIVED   gone for good                     -> not in Nagios
    IGNORED    hidden by a user                  -> not in Nagios

Rules: a miss only counts when the device itself was seen in that scan; a port
must be missed PORT_MISSING_AFTER_SCANS times in a row before its state
changes and any sighting resets the count; a monitored port is never deleted
automatically; NCPA's own port is protected while a token is deployed; a
monitored port's plugin is frozen so a changed nmap guess cannot rename its
Nagios service; ports in the ephemeral ranges are never suggested.

Service identification (Identified_By, see ServiceIdentification): a port only
guessed from its number (PORT_HINT) is never monitored automatically; a port
whose service an operator pinned (USER) is never renamed by a scan; and a
monitored port that now fingerprints as a different service raises a
SERVICE_CHANGED review item instead of being renamed.

Nothing here commits; the caller owns the transaction.
"""

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from flask import current_app

from app import db
from app.network_discovery.plugin_registry import Transport, resolve_plugin_name
from app.system_models import (
    DeviceReviewItem,
    NCPADeployment,
    NetworkDiscovery,
    Open_TCP_Services,
    Open_UDP_Services,
    PortSource,
    PortState,
    ReviewKind,
    ServiceIdentification,
)

# States whose ports produce Nagios services.
CONFIG_STATES = (PortState.MONITORED, PortState.MISSING)


def utcnow():
    return datetime.now(timezone.utc)


def port_model(protocol):
    """Return the port table for "tcp" / "udp" (case-insensitive)."""
    return Open_UDP_Services if str(protocol).lower() == "udp" else Open_TCP_Services


def transport_for(protocol):
    return Transport.UDP if str(protocol).lower() == "udp" else Transport.TCP


def is_ephemeral_port(port):
    """True if the port falls inside any configured EPHEMERAL_PORT_RANGES."""
    for low, high in current_app.config["EPHEMERAL_PORT_RANGES"]:
        if low <= port <= high:
            return True
    return False


def device_has_ncpa_token(device_id):
    """True if the device has a deployed NCPA token."""
    token = db.session.scalar(
        sa.select(NCPADeployment.Token).where(
            NCPADeployment.NetworkDiscoveryID == device_id,
            NCPADeployment.Token.is_not(None),
        )
    )
    return token is not None


def is_protected_ncpa_port(port, device_id):
    """NCPA's port with Source NCPA is never demoted while a token is deployed."""
    return (
        port.Source is PortSource.NCPA
        and port.Port_Number == int(current_app.config["NCPA_PORT"])
        and device_has_ncpa_token(device_id)
    )


def start_monitoring(port, protocol):
    """Make a port MONITORED and freeze its plugin from its current service name."""
    port.Port_State = PortState.MONITORED
    port.Closed_At = None
    port.Plugin_Name = resolve_plugin_name(port.Service_Name, transport_for(protocol))


def identification_from(value):
    """
    Turn a scan's "identified_by" (a ServiceIdentification name) into the
    enum. Anything missing or unknown is a PORT_HINT: never trust more than
    the scan proved.
    """
    if isinstance(value, ServiceIdentification):
        return value
    try:
        return ServiceIdentification[str(value)]
    except KeyError:
        return ServiceIdentification.PORT_HINT


def upsert_scanned_port(model, protocol, device_id, port_number, service_name, now,
                        identified_by=ServiceIdentification.PORT_HINT):
    """
    Create or refresh one port the scan saw. A new port is MONITORED when its
    service is in AUTO_MONITOR_SERVICES and was not just guessed from the port
    number, otherwise SUGGESTED; a port in an ephemeral range is not recorded
    at all. A port seen again resets its missed count, MISSING returns to
    MONITORED, ARCHIVED returns to SUGGESTED, IGNORED stays ignored. A
    monitored port keeps its Service_Name and Plugin_Name, and a port an
    operator pinned keeps its Service_Name in every state; the new guess is
    only stored in Observed_Service_Name. A suggested port that was only a
    guess and now fingerprints as an auto-monitored service starts being
    monitored. Returns the port, or None if it was not recorded. Does not
    commit.
    """
    identified_by = identification_from(identified_by)
    port = db.session.scalar(
        sa.select(model).where(
            model.NetDiscoveryID == device_id, model.Port_Number == port_number
        )
    )

    if port is None:
        if is_ephemeral_port(port_number):
            return None
        port = model(
            NetDiscoveryID=device_id, Port_Number=port_number, Service_Name=service_name,
            Observed_Service_Name=service_name, Source=PortSource.SCAN,
            Port_State=PortState.SUGGESTED, First_Seen_At=now, Last_Seen_At=now, Missed_Scans=0,
            Identified_By=identified_by,
        )
        db.session.add(port)
        if should_auto_monitor(service_name, identified_by):
            start_monitoring(port, protocol)
        db.session.flush()
        return port

    port.Last_Seen_At = now
    port.Missed_Scans = 0
    port.Observed_Service_Name = service_name
    pinned = port.Identified_By is ServiceIdentification.USER
    was_guess = port.Identified_By is ServiceIdentification.PORT_HINT

    if port.Port_State is PortState.MISSING:
        port.Port_State = PortState.MONITORED
        port.Closed_At = None
    elif port.Port_State is PortState.ARCHIVED:
        port.Port_State = PortState.SUGGESTED
        port.Closed_At = None
        if not pinned:
            port.Service_Name = service_name
            port.Identified_By = identified_by
    elif port.Port_State in (PortState.SUGGESTED, PortState.IGNORED):
        if not pinned:
            port.Service_Name = service_name
            port.Identified_By = identified_by
        if (port.Port_State is PortState.SUGGESTED and was_guess
                and should_auto_monitor(service_name, identified_by)):
            start_monitoring(port, protocol)
    elif port.Port_State is PortState.MONITORED and port.Plugin_Name is None:
        # Ports that predate the lifecycle: freeze what they are monitored as today.
        port.Plugin_Name = resolve_plugin_name(port.Service_Name, transport_for(protocol))

    if port.Port_State is PortState.MONITORED and not pinned:
        flag_service_change(port, protocol, device_id, service_name, identified_by)
    return port


def should_auto_monitor(service_name, identified_by):
    """
    True if a newly seen service is monitored without a user asking: it is in
    AUTO_MONITOR_SERVICES and was identified by more than its port number.
    """
    if identified_by is ServiceIdentification.PORT_HINT:
        return False
    auto_services = []
    for name in current_app.config["AUTO_MONITOR_SERVICES"]:
        auto_services.append(name.lower())
    return str(service_name).lower() in auto_services


def flag_service_change(port, protocol, device_id, service_name, identified_by):
    """
    Raise a SERVICE_CHANGED review item when a monitored port now
    fingerprints (or is ruled) as a service its frozen plugin does not match,
    e.g. a port monitored as http that now answers as ssh. The port is not
    renamed; an operator decides. Guesses from the port number never raise
    one, and an unresolved item with the same message is not repeated.
    Does not commit.
    """
    if identified_by is ServiceIdentification.PORT_HINT or port.Plugin_Name is None:
        return None
    # The agent PinPoint deployed was verified by deployment itself.
    if is_protected_ncpa_port(port, device_id):
        return None
    observed_plugin = resolve_plugin_name(service_name, transport_for(protocol))
    if observed_plugin == port.Plugin_Name:
        return None

    device = db.session.get(NetworkDiscovery, device_id)
    host = str(device_id)
    if device is not None:
        host = device.Nagios_Host_Name or device.Hostname or device.IP_Address
    message = (
        f"{protocol.lower()}/{port.Port_Number} on {host} is monitored as {port.Plugin_Name} "
        f"but now identifies as {service_name}."
    )[:255]

    existing = db.session.scalar(
        sa.select(DeviceReviewItem).where(
            DeviceReviewItem.Kind == ReviewKind.SERVICE_CHANGED,
            DeviceReviewItem.Message == message,
            DeviceReviewItem.Resolved_At.is_(None),
        )
    )
    if existing is not None:
        return existing

    item = DeviceReviewItem(
        Kind=ReviewKind.SERVICE_CHANGED,
        IP_Address=device.IP_Address if device is not None else None,
        MAC_Address=device.MAC_Address if device is not None else None,
        Message=message,
        Candidate_Device_IDs=[device_id],
    )
    db.session.add(item)
    return item


def age_unseen_port(port, protocol, device_id, now):
    """
    Count one missed scan against a port that was not seen while its device
    was, and apply the state rules once PORT_MISSING_AFTER_SCANS is reached.
    Does not commit.
    """
    missing_after = current_app.config["PORT_MISSING_AFTER_SCANS"]
    archive_after = timedelta(days=current_app.config["PORT_ARCHIVE_AFTER_DAYS"])

    if port.Port_State in (PortState.ARCHIVED, PortState.IGNORED):
        return

    if port.Port_State is PortState.MISSING:
        closed = port.Closed_At
        if closed is not None and closed.tzinfo is None:
            closed = closed.replace(tzinfo=timezone.utc)
        if closed is not None and now - closed > archive_after:
            port.Port_State = PortState.ARCHIVED
        return

    port.Missed_Scans = (port.Missed_Scans or 0) + 1
    if port.Missed_Scans < missing_after:
        return

    if port.Port_State is PortState.SUGGESTED:
        port.Port_State = PortState.ARCHIVED
        port.Closed_At = now
    elif port.Port_State is PortState.MONITORED:
        if is_protected_ncpa_port(port, device_id):
            return
        port.Port_State = PortState.MISSING
        port.Closed_At = now


def process_device_ports(device, services, host_seen=True):
    """
    Apply one scan's results for a device. services is
    {"tcp": {port: {"service_name": ..., "identified_by": ...}}, "udp": {...}} as
    discover_network() builds it after the port rules are applied. Ports not in the results are
    aged only when host_seen is True (a miss on a host that was not found
    proves nothing). Never deletes a row. Does not commit.
    """
    now = utcnow()
    for protocol in ("tcp", "udp"):
        model = port_model(protocol)
        scanned = {}
        for port_number, service_data in (services.get(protocol) or {}).items():
            service_data = service_data or {}
            scanned[int(port_number)] = (
                service_data.get("service_name") or "unknown",
                service_data.get("identified_by"),
            )

        for port_number, (service_name, identified_by) in scanned.items():
            upsert_scanned_port(
                model, protocol, device.NetDiscoveryID, port_number, service_name, now, identified_by
            )

        if not host_seen:
            continue

        stored = db.session.scalars(
            sa.select(model).where(model.NetDiscoveryID == device.NetDiscoveryID)
        ).all()
        for port in stored:
            if port.Port_Number not in scanned:
                age_unseen_port(port, protocol, device.NetDiscoveryID, now)


def mark_ncpa_port(device_id):
    """
    Record NCPA's port as MONITORED with Source NCPA after a successful
    deployment (called from add_ncpa_port). Reuses an existing row for the
    port so nothing is duplicated. Does not commit.
    """
    port_number = int(current_app.config["NCPA_PORT"])
    now = utcnow()
    port = db.session.scalar(
        sa.select(Open_TCP_Services).where(
            Open_TCP_Services.NetDiscoveryID == device_id,
            Open_TCP_Services.Port_Number == port_number,
        )
    )
    if port is None:
        port = Open_TCP_Services(
            NetDiscoveryID=device_id, Port_Number=port_number, Service_Name="ncpa",
            First_Seen_At=now,
        )
        db.session.add(port)

    port.Service_Name = "ncpa"
    port.Observed_Service_Name = "ncpa"
    port.Source = PortSource.NCPA
    # Deployment reached the agent with an authenticated request.
    port.Identified_By = ServiceIdentification.FINGERPRINT
    port.Last_Seen_At = now
    port.Missed_Scans = 0
    start_monitoring(port, "tcp")
    return port


def is_ssh_port(port):
    """True if a port row is SSH by its frozen plugin or its service name."""
    for name in (port.Plugin_Name, port.Service_Name):
        if name and name.strip().lower() == "ssh":
            return True
    return False


def device_ssh_port(device_id):
    """
    The TCP port a device answers SSH on, read from its recorded ports, so a
    device running SSH on e.g. 2222 is reached there. MISSING and ARCHIVED
    ports are not answering and are passed over. When several ports are SSH,
    a hand-added or operator-pinned port wins, then a monitored one, then the standard SSH_PORT,
    then the lowest number. Returns SSH_PORT when the device has no SSH port
    on record.
    """
    default_port = int(current_app.config["SSH_PORT"])
    ports = db.session.scalars(
        sa.select(Open_TCP_Services).where(
            Open_TCP_Services.NetDiscoveryID == device_id,
            Open_TCP_Services.Port_State.not_in((PortState.MISSING, PortState.ARCHIVED)),
        )
    ).all()

    candidates = []
    for port in ports:
        if not is_ssh_port(port):
            continue
        by_user = port.Source is PortSource.USER or port.Identified_By is ServiceIdentification.USER
        rank = (
            not by_user,
            port.Port_State is not PortState.MONITORED,
            port.Port_Number != default_port,
            port.Port_Number,
        )
        candidates.append((rank, port.Port_Number))

    if not candidates:
        return default_port
    candidates.sort()
    return candidates[0][1]


def add_user_port(device_id, protocol, port_number, service_name):
    """
    Add a port by hand and monitor it (Source USER), whatever range it is in.
    The caller checks the device has no such port yet. Does not commit.
    """
    now = utcnow()
    model = port_model(protocol)
    port = model(
        NetDiscoveryID=device_id, Port_Number=port_number, Service_Name=service_name,
        Observed_Service_Name=service_name, Source=PortSource.USER,
        First_Seen_At=now, Last_Seen_At=now, Missed_Scans=0,
        Identified_By=ServiceIdentification.USER,
    )
    db.session.add(port)
    start_monitoring(port, protocol)
    db.session.flush()
    return port


def pin_port_service(device_id, protocol, port_number, service_name):
    """
    Pin an existing port's service on an operator's request ("always treat
    this device's port X as Y"): Service_Name becomes service_name,
    Identified_By USER so no scan renames it, and a monitored port's plugin is
    frozen again from the new name. Returns the port, or None if the device
    has no such port. Does not commit.
    """
    model = port_model(protocol)
    port = db.session.scalar(
        sa.select(model).where(
            model.NetDiscoveryID == device_id, model.Port_Number == port_number
        )
    )
    if port is None:
        return None

    port.Service_Name = service_name
    port.Identified_By = ServiceIdentification.USER
    if port.Port_State in CONFIG_STATES:
        port.Plugin_Name = resolve_plugin_name(service_name, transport_for(protocol))
    db.session.flush()
    return port


def set_port_state(device_id, protocol, port_number, state):
    """
    Change a port's state on a user's request. MONITORED freezes the plugin.
    Returns the port, or None if the device has no such port. The NCPA port
    cannot be archived or ignored while a token is deployed (raises ValueError).
    Does not commit.
    """
    model = port_model(protocol)
    port = db.session.scalar(
        sa.select(model).where(model.NetDiscoveryID == device_id, model.Port_Number == port_number)
    )
    if port is None:
        return None

    if state in (PortState.ARCHIVED, PortState.IGNORED) and is_protected_ncpa_port(port, device_id):
        raise ValueError("The NCPA port cannot be removed while an NCPA token is deployed.")

    if state is PortState.MONITORED:
        if port.Port_State in CONFIG_STATES and port.Plugin_Name:
            # Already monitored (or missing): keep the frozen plugin.
            port.Port_State = PortState.MONITORED
            port.Closed_At = None
        else:
            start_monitoring(port, protocol)
        port.Missed_Scans = 0
    else:
        port.Port_State = state
        port.Closed_At = utcnow() if state is PortState.ARCHIVED else None
    return port
