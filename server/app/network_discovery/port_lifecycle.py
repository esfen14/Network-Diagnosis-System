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

Plugin Manager is the switch: an identified SUGGESTED port is monitored only
when the plugin that checks its service is Enabled or Active (D2 in the
plugin-driven monitoring plan), at first sight and again whenever
promote_identified_ports() runs, e.g. after a plugin is enabled. The generic
TCP plugin picks up every identified TCP port with no plugin of its own; UDP
is monitored only through a plugin that speaks its protocol.

Not used as intended: when the Port -> Service setting expects one service on a
port and nmap fingerprinted another, the port keeps what nmap saw, records the
expected name in Expected_Service_Name and is not monitored until an admin
acknowledges it (Mismatch_Acknowledged_At). A change in what nmap sees clears
the acknowledgement.

Nothing here commits; the caller owns the transaction.
"""

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from flask import current_app

from app import db
from app.network_discovery.plugin_registry import (
    Transport,
    plugin_for_definition,
    resolve_plugin_name,
)
from app.plugin_models import Plugin, PluginStatus
from app.system_models import (
    DeviceReviewItem,
    DeviceState,
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

# Plugin states that allow monitoring (Plugin Manager's on switch).
ENABLED_PLUGIN_STATES = (PluginStatus.ENABLED, PluginStatus.ACTIVE)

# Identification that counts as knowing what a port is: an operator's pin, the
# Port -> Service table, or nmap's fingerprint. A guess from the number does not.
IDENTIFIED_BY = (
    ServiceIdentification.USER,
    ServiceIdentification.PORT_RULE,
    ServiceIdentification.FINGERPRINT,
)


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
    """
    Make a port MONITORED and freeze its plugin from its current service name. Monitoring a
    port releases any hold on promoting it.
    """
    port.Port_State = PortState.MONITORED
    port.Promotion_Held = False
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


def enabled_plugin_names():
    """The Plugin Manager plugins that are Enabled or Active, as a set of names."""
    return set(db.session.scalars(
        sa.select(Plugin.Name).where(Plugin.Status.in_(ENABLED_PLUGIN_STATES))
    ).all())


def has_unacknowledged_mismatch(port):
    """True if the port is flagged "not used as intended" and no admin has acknowledged it."""
    return port.Expected_Service_Name is not None and port.Mismatch_Acknowledged_At is None


def upsert_scanned_port(model, protocol, device_id, port_number, service_name, now,
                        identified_by=ServiceIdentification.PORT_HINT, expected_service=None,
                        enabled_plugins=None):
    """
    Create or refresh one port the scan saw. A new port is MONITORED when its
    service was identified by more than its port number and the plugin that
    checks it is enabled in Plugin Manager (should_auto_monitor), otherwise
    SUGGESTED; a port in an ephemeral range is not recorded at all.
    expected_service is the Port -> Service entry that nmap's fingerprint
    contradicted, or None: it flags the port "not used as intended" and keeps it
    from being monitored until acknowledged. enabled_plugins is the set from
    enabled_plugin_names(), looked up when not passed. A port seen again resets its missed count, MISSING returns to
    MONITORED, ARCHIVED returns to SUGGESTED, IGNORED stays ignored. A
    monitored port keeps its Service_Name and Plugin_Name, and a port an
    operator pinned keeps its Service_Name in every state; the new guess is
    only stored in Observed_Service_Name. A suggested port that was only a
    guess and now fingerprints as an auto-monitored service starts being
    monitored. Returns the port, or None if it was not recorded. Does not
    commit.
    """
    identified_by = identification_from(identified_by)
    if enabled_plugins is None:
        enabled_plugins = enabled_plugin_names()
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
            Identified_By=identified_by, Expected_Service_Name=expected_service,
        )
        db.session.add(port)
        if should_auto_monitor(service_name, identified_by, protocol, enabled_plugins, port):
            start_monitoring(port, protocol)
        db.session.flush()
        return port

    port.Last_Seen_At = now
    port.Missed_Scans = 0
    pinned = port.Identified_By is ServiceIdentification.USER
    was_guess = port.Identified_By is ServiceIdentification.PORT_HINT

    # An operator's pin outranks the table. Otherwise a changed sighting clears
    # an earlier acknowledgement, because the admin accepted something else.
    if pinned:
        expected_service = None
    if expected_service is None or port.Observed_Service_Name != service_name:
        port.Mismatch_Acknowledged_At = None
    port.Expected_Service_Name = expected_service
    port.Observed_Service_Name = service_name

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
                and should_auto_monitor(service_name, identified_by, protocol, enabled_plugins, port)):
            start_monitoring(port, protocol)
    elif port.Port_State is PortState.MONITORED and port.Plugin_Name is None:
        # Ports that predate the lifecycle: freeze what they are monitored as today.
        port.Plugin_Name = resolve_plugin_name(port.Service_Name, transport_for(protocol))

    if port.Port_State is PortState.MONITORED and not pinned:
        # A removed port rule no longer vouches for the label; the name and
        # plugin stay frozen, only how the port was identified is refreshed.
        if port.Identified_By is ServiceIdentification.PORT_RULE and identified_by is not ServiceIdentification.PORT_RULE:
            port.Identified_By = identified_by
        flag_service_change(port, protocol, device_id, service_name, identified_by)
    return port


def should_auto_monitor(service_name, identified_by, protocol="tcp", enabled_plugins=None, port=None, ignore_hold=False):
    """
    True if a SUGGESTED port should start being monitored without a user
    asking: its service was identified by more than its port number, it is not
    flagged "not used as intended" and not held back (port, when given), and the Plugin Manager
    plugin that checks it is Enabled or Active. A TCP service with no plugin
    of its own is checked by the generic TCP plugin; a UDP one is never
    monitored this way. ignore_hold answers as if the port were not held back
    (used to count held ports).
    """
    if identified_by not in IDENTIFIED_BY:
        return False
    if port is not None and has_unacknowledged_mismatch(port):
        return False
    if port is not None and port.Promotion_Held and not ignore_hold:
        return False
    transport = transport_for(protocol)
    definition_name = resolve_plugin_name(service_name, transport)
    if transport is Transport.UDP and definition_name == "udp":
        return False
    if enabled_plugins is None:
        enabled_plugins = enabled_plugin_names()
    return plugin_for_definition(definition_name) in enabled_plugins


# Plugin states from which "preserve existing monitoring" may switch a plugin on. A plugin in any
# failure state is left alone because it cannot run until that is fixed.
ENABLE_FOR_CONTINUITY_FROM = (
    PluginStatus.AVAILABLE,
    PluginStatus.READY,
    PluginStatus.INSTALLED,
    PluginStatus.DISABLED,
    PluginStatus.UPDATE_AVAILABLE,
)


def plugins_backing_monitored_ports():
    """
    The Plugin Manager plugins (e.g. "check_ssh") behind every Monitored or Missing port: the
    ones whose services are running in Nagios right now. A port uses its frozen plugin, else
    the plugin for its service name; a TCP port that matches nothing is checked by the generic
    TCP plugin, as discovery does, and an unmatched UDP port is skipped by discovery, so it
    backs nothing. Read-only.
    """
    needed = set()
    for protocol in ("tcp", "udp"):
        model = port_model(protocol)
        transport = transport_for(protocol)
        for port in db.session.scalars(sa.select(model).where(model.Port_State.in_(CONFIG_STATES))).all():
            definition_name = port.Plugin_Name or resolve_plugin_name(port.Service_Name, transport)
            plugin = plugin_for_definition(definition_name)
            if transport is Transport.UDP and definition_name == "udp":
                continue
            if plugin is not None:
                needed.add(plugin)
    return needed


def enable_plugins_backing_monitored_ports():
    """
    Switch on every plugin that backs a port already being monitored, so an install that was
    monitoring before Plugin Manager gated generation keeps its services. Used when the plugin
    inventory is first created on an install that already has monitored ports; a fresh install
    has none, so nothing is enabled and monitoring stays opt-in. Ports that were only Suggested
    and that these plugins would now pick up are held back (hold_promotable_ports), so an upgrade
    never starts monitoring something nobody chose. Returns the names enabled. Does not commit.
    """
    needed = plugins_backing_monitored_ports()
    if not needed:
        return []

    enabled = []
    for plugin in db.session.scalars(sa.select(Plugin).where(Plugin.Name.in_(needed))).all():
        if plugin.Status in ENABLE_FOR_CONTINUITY_FROM:
            plugin.Status = PluginStatus.ENABLED
            enabled.append(plugin.Name)
    db.session.flush()
    hold_promotable_ports()
    return sorted(enabled)


def promotable_ports(enabled_plugins, include_held=False):
    """
    The SUGGESTED ports that would start being monitored if exactly these Plugin
    Manager plugins were enabled: identified (pinned, from the table, or
    fingerprinted), not flagged "not used as intended", not held back, and on a
    device that is scanned and not retired or merged. With include_held the ports
    an admin (or an upgrade) is holding back are listed too. Returns a list of
    (protocol, port row). Read-only; this is also what the enable preview counts.
    """
    if not enabled_plugins:
        return []

    found = []
    for protocol in ("tcp", "udp"):
        model = port_model(protocol)
        ports = db.session.scalars(
            sa.select(model)
            .join(NetworkDiscovery, NetworkDiscovery.NetDiscoveryID == model.NetDiscoveryID)
            .where(
                model.Port_State == PortState.SUGGESTED,
                model.Identified_By.in_(IDENTIFIED_BY),
                NetworkDiscovery.Include_Device_In_Scanning.is_(True),
                NetworkDiscovery.Device_State.not_in((DeviceState.RETIRED, DeviceState.MERGED)),
            )
        ).all()
        for port in ports:
            if should_auto_monitor(
                port.Service_Name, port.Identified_By, protocol, enabled_plugins, port, ignore_hold=include_held
            ):
                found.append((protocol, port))
    return found


def hold_promotable_ports(enabled_plugins=None):
    """
    Hold back every SUGGESTED port that the enabled plugins would start monitoring, so a plugin
    that was switched on only to keep existing services running does not also pick up ports
    nobody chose to monitor. They stay Suggested until an admin promotes them. Returns how many
    were held. Does not commit.
    """
    if enabled_plugins is None:
        enabled_plugins = enabled_plugin_names()
    held = 0
    for _, port in promotable_ports(enabled_plugins):
        port.Promotion_Held = True
        held += 1
    return held


def promote_identified_ports():
    """
    Start monitoring every SUGGESTED port whose service is identified and whose
    plugin is now enabled in Plugin Manager, on devices that are scanned and not
    retired or merged. Enabling a plugin and finding a new device both lead
    here, so ports are attached without picking devices by hand. Ports flagged
    "not used as intended" wait for acknowledgement; IGNORED ports stay
    ignored (see promotable_ports). Returns the number of ports promoted. Does
    not commit.
    """
    promoted = 0
    for protocol, port in promotable_ports(enabled_plugin_names()):
        start_monitoring(port, protocol)
        promoted += 1
    return promoted


def acknowledge_port_mismatch(device_id, protocol, port_number):
    """
    Record that an admin accepts a port flagged "not used as intended" as the
    service nmap found on it. A SUGGESTED port then follows the normal rule and
    is monitored if its plugin is enabled. Returns the port, or None if the
    device has no such port. Raises ValueError if the port is not flagged or
    was already acknowledged. Does not commit.
    """
    model = port_model(protocol)
    port = db.session.scalar(
        sa.select(model).where(model.NetDiscoveryID == device_id, model.Port_Number == port_number)
    )
    if port is None:
        return None
    if not has_unacknowledged_mismatch(port):
        raise ValueError("This port has no unacknowledged mismatch.")

    port.Mismatch_Acknowledged_At = utcnow()
    port.Promotion_Held = False          # accepting the port is consent to monitor it
    if port.Port_State is PortState.SUGGESTED and should_auto_monitor(
        port.Service_Name, port.Identified_By, protocol, port=port
    ):
        start_monitoring(port, protocol)
    db.session.flush()
    return port


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
    {"tcp": {port: {"service_name": ..., "identified_by": ..., "expected_service": ...}},
    "udp": {...}} as discover_network() builds it after the port rules are
    applied ("expected_service" is only present for a mismatch). Ports not in the results are
    aged only when host_seen is True (a miss on a host that was not found
    proves nothing). Never deletes a row. Does not commit.
    """
    now = utcnow()
    enabled_plugins = enabled_plugin_names()
    for protocol in ("tcp", "udp"):
        model = port_model(protocol)
        scanned = {}
        for port_number, service_data in (services.get(protocol) or {}).items():
            service_data = service_data or {}
            scanned[int(port_number)] = (
                service_data.get("service_name") or "unknown",
                service_data.get("identified_by"),
                service_data.get("expected_service"),
            )

        for port_number, (service_name, identified_by, expected_service) in scanned.items():
            upsert_scanned_port(
                model, protocol, device.NetDiscoveryID, port_number, service_name, now, identified_by,
                expected_service, enabled_plugins,
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
    port.Expected_Service_Name = None
    port.Mismatch_Acknowledged_At = None
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
    # The operator decided; the table's expectation no longer applies.
    port.Expected_Service_Name = None
    port.Mismatch_Acknowledged_At = None
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
        port.Promotion_Held = False
        if has_unacknowledged_mismatch(port):
            # Choosing to monitor the port is accepting it as it is.
            port.Mismatch_Acknowledged_At = utcnow()
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
        if state is PortState.SUGGESTED:
            # An admin leaving a port Suggested is a decision: no plugin may promote it behind their back.
            port.Promotion_Held = True
    return port
