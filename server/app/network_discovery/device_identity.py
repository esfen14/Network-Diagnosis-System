"""
Device identity and reconciliation for Network Discovery.

A scan only OBSERVES: it reports an IP, maybe a MAC, open ports and some
identity evidence (SSH host key, NCPA certificate). This module DECIDES which
known device each observation belongs to, so a DHCP lease change moves a
device instead of duplicating it, and one device's history is never attached
to another. See "docs/plans/DHCP_Device_Identity_Plan.md" sections 4, 6 and 8.

How it works
------------
reconcile_scan() runs in two passes. Pass one resolves every observation to a
Decision without touching the database, so the outcome cannot depend on the
order hosts were scanned in. Pass two applies the decisions: it creates
devices, records address changes, stores identifiers, marks IP reuse, and
finally updates the lifecycle (MISSING / RETIRED) of devices the scan did not
see. Nothing here commits; the caller owns the transaction.

Identity evidence, strongest first: NCPA certificate, machine-id and SSH host
key ("strong"), then a hardware MAC ("likely"), then the IP. A strong
identifier can only belong to one device. Two devices are never merged
automatically; anything ambiguous becomes a DeviceReviewItem.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import re
import uuid

import sqlalchemy as sa
from flask import current_app

from app import db
from app.system_models import (
    AddressSource,
    AddressingMode,
    AgentStatus,
    DeviceAddressHistory,
    DeviceIdentifier,
    DeviceReviewItem,
    DeviceState,
    IdentifierKind,
    IdentityConfidence,
    NCPADeployment,
    NetworkDiscovery,
    ReviewKind,
    SSHCredentials,
)

# Kinds that identify a device on their own. A MAC is deliberately not in
# this set: it only gives "Likely" confidence.
STRONG_KINDS = (
    IdentifierKind.NCPA_CERT,
    IdentifierKind.MACHINE_ID,
    IdentifierKind.SSH_HOST_KEY,
)

# Device states in which an IP may still be treated as "this device's address".
IP_MATCHABLE_STATES = (DeviceState.ACTIVE, DeviceState.MISSING, DeviceState.ADDRESS_UNKNOWN)


def utcnow():
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Evidence:
    """One identifier observed for a host. Strong kinds are unique per device."""
    kind: IdentifierKind
    value: str
    strong: bool = True


@dataclass
class Decision:
    """
    What to do with one observation. action is "match" (device is set),
    "new" (create a device) or "conflict"/"changed"/"reuse" which also create
    a device but carry a review item. For "match", confidence is None when the
    device's stored confidence should be kept.
    """
    action: str
    ip: str
    network: str
    evidence: list
    device: object = None
    confidence: object = None
    review_kind: object = None
    review_message: str = None
    candidates: list = field(default_factory=list)
    displaced: object = None  # device whose address was taken by this one


# ==========================================================
# EVIDENCE
# ==========================================================

def normalize_mac(mac):
    """Return the MAC lower-cased with colons, or None if it is not a valid MAC."""
    if not mac:
        return None
    text = str(mac).strip().lower().replace("-", ":")
    if not re.fullmatch(r"([0-9a-f]{2}:){5}[0-9a-f]{2}", text):
        return None
    return text


def is_hardware_mac(mac):
    """
    True for a universally administered MAC. A set locally-administered bit
    (second-lowest bit of the first octet) means the MAC is randomized, as on
    phones and some laptops, and is treated as if there were no MAC.
    """
    text = normalize_mac(mac)
    if text is None:
        return False
    return (int(text[:2], 16) & 0x02) == 0


def build_evidence(mac=None, identifiers=None, dns_name=None):
    """
    Turn what a scan saw into a list of Evidence. identifiers is an optional
    list of (IdentifierKind, value) pairs from probes (SSH host key, NCPA
    certificate, machine-id). A randomized MAC is dropped. A reverse-DNS name
    is kept as weak evidence only.
    """
    evidence = []
    seen = set()

    def add(kind, value, strong):
        if not value:
            return
        key = (kind, value)
        if key in seen:
            return
        seen.add(key)
        evidence.append(Evidence(kind, value, strong))

    if is_hardware_mac(mac):
        add(IdentifierKind.MAC, normalize_mac(mac), True)

    for kind, value in identifiers or []:
        add(kind, value, kind in STRONG_KINDS)

    if dns_name and dns_name != "Unknown":
        add(IdentifierKind.DNS_NAME, dns_name.lower(), False)

    return evidence


def confidence_from_evidence(evidence):
    """VERIFIED with any strong identifier, LIKELY with a hardware MAC, else UNVERIFIED."""
    if any(item.kind in STRONG_KINDS for item in evidence):
        return IdentityConfidence.VERIFIED
    if any(item.kind is IdentifierKind.MAC for item in evidence):
        return IdentityConfidence.LIKELY
    return IdentityConfidence.UNVERIFIED


def device_identifier_values(device_id, kind):
    """Return the set of stored identifier values of one kind for a device."""
    rows = db.session.scalars(
        sa.select(DeviceIdentifier.Value).where(
            DeviceIdentifier.NetDiscoveryID == device_id,
            DeviceIdentifier.Kind == kind,
        )
    ).all()
    return set(rows)


def contradicts(device, evidence, check_mac=False):
    """
    True when the observation carries a strong identifier of a kind the device
    already has, and none of the observed values match what is stored.
    Same-kind agreement is not required to be total: a device only needs one
    stored value to equal one observed value. With check_mac the hardware MAC
    is compared the same way (used for IP matches, where a different MAC means
    a different machine).
    """
    kinds = list(STRONG_KINDS) + ([IdentifierKind.MAC] if check_mac else [])
    for kind in kinds:
        observed = {item.value for item in evidence if item.kind is kind}
        if not observed:
            continue
        stored = device_identifier_values(device.NetDiscoveryID, kind)
        if stored and not (stored & observed):
            return True
    return False


def final_device(device):
    """Follow Merged_Into_ID to the device that now owns this record."""
    seen = set()
    while device is not None and device.Merged_Into_ID is not None and device.NetDiscoveryID not in seen:
        seen.add(device.NetDiscoveryID)
        device = db.session.get(NetworkDiscovery, device.Merged_Into_ID)
    return device


def devices_by_host_name(names=None):
    """
    Return {Nagios host name: NetworkDiscovery row} for the given host names, using the same naming
    rule as nagios_host_name(). A name with no device (for example "localhost") is simply absent. If
    a retired or merged device once had the same name as a current one, the current device wins.
    names=None returns every device, for callers that filter on a device property.
    """
    wanted = None if names is None else set(names)
    if wanted is not None and not wanted:
        return {}

    found = {}
    ended = (DeviceState.RETIRED, DeviceState.MERGED)
    devices = db.session.scalars(sa.select(NetworkDiscovery).order_by(NetworkDiscovery.NetDiscoveryID)).all()
    for device in sorted(devices, key=lambda d: d.Device_State in ended, reverse=True):
        name = nagios_host_name(device)
        if wanted is None or name in wanted:
            found[name] = device
    return found


def device_ids_by_host_name(names):
    """
    Return {Nagios host name: device id} for the given host names. The Device Inventory host list is
    keyed by that name, so this is how it reaches a device's id. See devices_by_host_name().
    """
    return {name: device.NetDiscoveryID for name, device in devices_by_host_name(names).items()}


# One label per device saying whether Nagios is checking it and, if not, why. The first match wins,
# so a paused device that is also missing is "paused". See Device_Monitoring_State_Plan.md.
MONITORING_STATES = ("monitored", "missing", "address_unknown", "paused", "retired", "merged")


def monitoring_state(device):
    """The device's monitoring label, one of MONITORING_STATES."""
    if device.Device_State is DeviceState.MERGED:
        return "merged"
    if device.Device_State is DeviceState.RETIRED:
        return "retired"
    if not device.Include_Device_In_Scanning:
        return "paused"
    if device.Device_State is DeviceState.ADDRESS_UNKNOWN:
        return "address_unknown"
    if device.Device_State is DeviceState.MISSING:
        return "missing"
    return "monitored"


# Labels of devices that are out of the Nagios config. Their last history.db snapshot is stale and
# must not count as a live host or service.
UNCHECKED_STATES = ("paused", "retired", "merged")


def unchecked_host_names():
    """
    Return the set of Nagios host names whose device is paused, retired or merged, so it is not in
    the Nagios config. Hosts with no device record (for example localhost) are never included.
    """
    return {
        name for name, device in devices_by_host_name().items()
        if monitoring_state(device) in UNCHECKED_STATES
    }


def nagios_host_name(device):
    """
    The name Nagios, history.db and acknowledgements know this device by:
    the stable Nagios_Host_Name, falling back to the DNS name and then the IP
    for rows that predate stable names. Use this instead of reading Hostname.
    """
    if device.Nagios_Host_Name:
        return device.Nagios_Host_Name
    if device.Hostname and device.Hostname != "Unknown":
        return device.Hostname
    return device.IP_Address


# ==========================================================
# PASS ONE — RESOLVE (read only)
# ==========================================================

def find_identifier_owners(evidence, kinds):
    """Return {device_id: device} for devices owning any evidence of the given kinds."""
    owners = {}
    for item in evidence:
        if item.kind not in kinds:
            continue
        rows = db.session.scalars(
            sa.select(DeviceIdentifier).where(
                DeviceIdentifier.Kind == item.kind,
                DeviceIdentifier.Value == item.value,
            )
        ).all()
        for row in rows:
            device = final_device(db.session.get(NetworkDiscovery, row.NetDiscoveryID))
            if device is not None:
                owners[device.NetDiscoveryID] = device
    return owners


def find_ip_holder(ip, network, exclude_ids=()):
    """Return the device currently recorded at (ip, network) in a matchable state, if any."""
    order_clause = sa.case(
        (NetworkDiscovery.Device_State == DeviceState.ACTIVE, 1),
        (NetworkDiscovery.Device_State == DeviceState.MISSING, 2),
        (NetworkDiscovery.Device_State == DeviceState.ADDRESS_UNKNOWN, 3),
        else_=4,
    )
    return db.session.scalar(
        sa.select(NetworkDiscovery).where(
            NetworkDiscovery.IP_Address == ip,
            NetworkDiscovery.Network == network,
            NetworkDiscovery.Device_State.in_(IP_MATCHABLE_STATES),
            NetworkDiscovery.NetDiscoveryID.not_in(list(exclude_ids) or [-1]),
        ).order_by(order_clause, NetworkDiscovery.NetDiscoveryID)
    )


def resolve_observation(ip, network, evidence):
    """
    Decide which device one observation belongs to (plan section 4 table).
    Pure: reads the database, writes nothing.

    1. Strong identifiers point to one device -> same device, VERIFIED, unless
       another strong identifier contradicts it (-> conflict).
    2. They point to two devices -> conflict, no merge.
    3. Only a hardware MAC matches one device -> same device, LIKELY, unless a
       strong identifier contradicts it (-> identity changed).
    4. Same IP as a known device whose identifiers contradict the observation
       -> IP reuse: a new device, and the old one loses its address.
    5. Same IP, nothing contradicting -> same device, confidence unchanged.
    6. Nothing matches -> new device.
    """
    owners = find_identifier_owners(evidence, STRONG_KINDS)

    if len(owners) > 1:
        return Decision(
            "conflict", ip, network, evidence,
            device=find_ip_holder(ip, network, exclude_ids=owners),
            review_kind=ReviewKind.CONFLICT,
            review_message=f"{ip}: identifiers belong to {len(owners)} different devices. "
                           "Nothing was merged; review and merge manually if they are the same device.",
            candidates=sorted(owners),
        )

    if len(owners) == 1:
        device = next(iter(owners.values()))
        # Cloned hosts can share an SSH key across different networks. When a
        # different known device already holds this IP in this network and does
        # not contradict the observation, keep its ports and history on that
        # device instead of moving the key owner from another network.
        if device.Network != network:
            holder = find_ip_holder(ip, network, exclude_ids=[device.NetDiscoveryID])
            if holder is not None and not contradicts(holder, evidence, check_mac=True):
                return Decision(
                    "match", ip, network, evidence, device=holder,
                    review_kind=ReviewKind.DUPLICATE_IDENTITY,
                    review_message=f"{ip}: SSH identity is shared with {device.Nagios_Host_Name}; "
                                   f"kept the known device {holder.Nagios_Host_Name} by address.",
                    candidates=sorted((device.NetDiscoveryID, holder.NetDiscoveryID)),
                )
        # Cloned hosts can share an SSH key. When a different known device at
        # this very address owns the observed hardware MAC, keep its ports and
        # history on that device instead of treating it as a second NIC of the
        # key owner. Do not prefer a MAC at another address over the key: the
        # original device may simply have changed its NIC.
        mac_owners = find_identifier_owners(evidence, (IdentifierKind.MAC,))
        mac_holder = next(iter(mac_owners.values()), None)
        if (mac_holder is not None and mac_holder.NetDiscoveryID != device.NetDiscoveryID
                and mac_holder.IP_Address == ip and mac_holder.Network == network):
            return Decision(
                "match", ip, network, evidence, device=mac_holder,
                review_kind=ReviewKind.DUPLICATE_IDENTITY,
                review_message=f"{ip}: SSH identity is shared with {device.Nagios_Host_Name}; "
                               f"kept the known device {mac_holder.Nagios_Host_Name} by address and MAC.",
                candidates=sorted((device.NetDiscoveryID, mac_holder.NetDiscoveryID)),
            )
        if contradicts(device, evidence):
            return Decision(
                "conflict", ip, network, evidence,
                device=find_ip_holder(ip, network, exclude_ids=owners),
                review_kind=ReviewKind.CONFLICT,
                review_message=f"{ip}: matches {device.Nagios_Host_Name} on one identifier but "
                               "another identifier differs. Nothing was merged.",
                candidates=[device.NetDiscoveryID],
            )
        return Decision("match", ip, network, evidence, device=device,
                        confidence=IdentityConfidence.VERIFIED)

    mac_owners = find_identifier_owners(evidence, (IdentifierKind.MAC,))
    if mac_owners:
        device = next(iter(mac_owners.values()))
        if contradicts(device, evidence):
            return Decision(
                "changed", ip, network, evidence,
                device=find_ip_holder(ip, network, exclude_ids=mac_owners),
                review_kind=ReviewKind.IDENTITY_CHANGED,
                review_message=f"{ip}: hardware matches {device.Nagios_Host_Name} but its SSH/NCPA identity "
                               "changed (OS reinstall?). Recorded as a new device; merge it if it is the same machine.",
                candidates=[device.NetDiscoveryID],
            )
        return Decision("match", ip, network, evidence, device=device,
                        confidence=IdentityConfidence.LIKELY)

    holder = find_ip_holder(ip, network)
    if holder is not None:
        if contradicts(holder, evidence, check_mac=True):
            return Decision(
                "reuse", ip, network, evidence,
                review_kind=ReviewKind.IP_REUSE,
                review_message=f"{ip} now belongs to a different device than {holder.Nagios_Host_Name}. "
                               f"{holder.Nagios_Host_Name} is marked 'address unknown' until it is found again.",
                candidates=[holder.NetDiscoveryID],
                displaced=holder,
            )
        return Decision("match", ip, network, evidence, device=holder)

    return Decision("new", ip, network, evidence)


# ==========================================================
# STABLE NAGIOS HOST NAMES
# ==========================================================

def sanitize_host_label(name):
    """Make a DNS-ish name safe for a Nagios host_name; returns '' if nothing usable is left."""
    cleaned = re.sub(r"[^a-z0-9.\-]", "-", (name or "").strip().lower())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-.")
    return cleaned[:90]


def host_name_in_use(name):
    return db.session.scalar(
        sa.select(NetworkDiscovery.NetDiscoveryID).where(NetworkDiscovery.Nagios_Host_Name == name)
    ) is not None


def create_stable_host_name(dns_name=None, ncpa_node_name=None):
    """
    Pick the Nagios host_name for a new device, once, never from its IP:
    the NCPA node name or reverse DNS name if usable and free, else
    dev-<6 hex>. A collision gets -2, -3, ... appended.
    """
    for candidate in (ncpa_node_name, dns_name):
        label = sanitize_host_label(candidate)
        # A name that merely embeds an IP would change with the lease.
        if label and label != "unknown" and not re.match(r"^\d{1,3}(\.\d{1,3}){3}(\.|$)", label):
            base = label
            break
    else:
        base = f"dev-{uuid.uuid4().hex[:6]}"

    name = base
    counter = 2
    while host_name_in_use(name):
        name = f"{base}-{counter}"
        counter += 1
    return name


# ==========================================================
# APPLY — devices, identifiers and addresses
# ==========================================================

def open_address(device, ip, network, mac, source=AddressSource.SCAN):
    """
    Close the device's open address row (if any) and open a new one for ip.
    No-op when the open row already holds this address (just refreshes its
    Last_Seen_At). Does not commit.
    """
    now = utcnow()
    current = db.session.scalar(
        sa.select(DeviceAddressHistory).where(
            DeviceAddressHistory.NetDiscoveryID == device.NetDiscoveryID,
            DeviceAddressHistory.Closed_At.is_(None),
        )
    )
    if current is not None and current.IP_Address == ip:
        current.Last_Seen_At = now
        if mac:
            current.MAC_Address = mac
        return False

    if current is not None:
        current.Closed_At = now
    db.session.add(DeviceAddressHistory(
        NetDiscoveryID=device.NetDiscoveryID, IP_Address=ip, Network=network,
        MAC_Address=mac, Source=source, First_Seen_At=now, Last_Seen_At=now,
    ))
    return True


def close_address(device):
    """Close the device's open address row, e.g. when its IP now belongs to another device."""
    now = utcnow()
    rows = db.session.scalars(
        sa.select(DeviceAddressHistory).where(
            DeviceAddressHistory.NetDiscoveryID == device.NetDiscoveryID,
            DeviceAddressHistory.Closed_At.is_(None),
        )
    ).all()
    for row in rows:
        row.Closed_At = now


def record_secondary_address(device, ip, network, mac):
    """
    Remember an extra address a multi-NIC device was seen on, as an already
    closed history row, so it never competes with the primary address.
    """
    now = utcnow()
    existing = db.session.scalar(
        sa.select(DeviceAddressHistory).where(
            DeviceAddressHistory.NetDiscoveryID == device.NetDiscoveryID,
            DeviceAddressHistory.IP_Address == ip,
        )
    )
    if existing is not None:
        existing.Last_Seen_At = now
        return
    db.session.add(DeviceAddressHistory(
        NetDiscoveryID=device.NetDiscoveryID, IP_Address=ip, Network=network,
        MAC_Address=mac, Source=AddressSource.SCAN, First_Seen_At=now, Last_Seen_At=now, Closed_At=now,
    ))


def attach_identifiers(device, evidence):
    """
    Store the observation's evidence on the device. An identifier already
    owned by another device is skipped (strong identifiers are unique), never
    reassigned. Returns the evidence that could not be attached. Does not commit.
    """
    now = utcnow()
    rejected = []
    for item in evidence:
        existing = db.session.scalar(
            sa.select(DeviceIdentifier).where(
                DeviceIdentifier.Kind == item.kind,
                DeviceIdentifier.Value == item.value,
                DeviceIdentifier.NetDiscoveryID == device.NetDiscoveryID,
            )
        )
        if existing is not None:
            existing.Last_Seen_At = now
            continue

        if item.strong:
            owner = db.session.scalar(
                sa.select(DeviceIdentifier).where(
                    DeviceIdentifier.Kind == item.kind,
                    DeviceIdentifier.Value == item.value,
                    DeviceIdentifier.Is_Strong.is_(True),
                )
            )
            if owner is not None:
                rejected.append(item)
                continue

        db.session.add(DeviceIdentifier(
            NetDiscoveryID=device.NetDiscoveryID, Kind=item.kind, Value=item.value,
            Is_Strong=item.strong, First_Seen_At=now, Last_Seen_At=now,
        ))
    db.session.flush()
    return rejected


def recompute_confidence(device):
    """
    Set the device's confidence from the identifiers it now owns: VERIFIED
    with any strong identifier, LIKELY with only a hardware MAC, else
    UNVERIFIED. Does not commit.
    """
    kinds = set(db.session.scalars(
        sa.select(DeviceIdentifier.Kind).where(DeviceIdentifier.NetDiscoveryID == device.NetDiscoveryID)
    ).all())
    if kinds & set(STRONG_KINDS):
        device.Identity_Confidence = IdentityConfidence.VERIFIED
    elif IdentifierKind.MAC in kinds:
        device.Identity_Confidence = IdentityConfidence.LIKELY
    else:
        device.Identity_Confidence = IdentityConfidence.UNVERIFIED
    return device.Identity_Confidence


def record_device_evidence(device, evidence, discovery_status_id=None):
    """
    Attach evidence learned outside a scan (SSH trust confirmation, NCPA
    deployment) to a device and refresh its confidence. Evidence that already
    belongs to a different device is NOT moved: a review item is raised
    instead (typically a cloned VM sharing a machine-id or host key).
    Returns the list of evidence that could not be attached. Does not commit.
    """
    rejected = attach_identifiers(device, evidence)

    if rejected:
        owner_ids = set()
        for item in rejected:
            owner = db.session.scalar(
                sa.select(DeviceIdentifier.NetDiscoveryID).where(
                    DeviceIdentifier.Kind == item.kind,
                    DeviceIdentifier.Value == item.value,
                    DeviceIdentifier.Is_Strong.is_(True),
                )
            )
            if owner is not None and owner != device.NetDiscoveryID:
                owner_ids.add(owner)
        add_review_item(
            Decision(
                "conflict", device.IP_Address, device.Network, list(rejected),
                review_kind=ReviewKind.CONFLICT,
                review_message=f"{device.Nagios_Host_Name or device.IP_Address} reports an identifier that "
                               "another device already owns (cloned VM?). Nothing was merged.",
                candidates=sorted(owner_ids | {device.NetDiscoveryID}),
            ),
            discovery_status_id,
        )

    recompute_confidence(device)
    return rejected


def add_review_item(decision, discovery_status_id):
    """
    Record a DeviceReviewItem for a decision, unless an unresolved item with
    the same kind, IP and candidates already exists (so a rescan does not
    pile up duplicates). Does not commit.
    """
    existing = db.session.scalars(
        sa.select(DeviceReviewItem).where(
            DeviceReviewItem.Kind == decision.review_kind,
            DeviceReviewItem.IP_Address == decision.ip,
            DeviceReviewItem.Resolved_At.is_(None),
        )
    ).all()
    for item in existing:
        if sorted(item.Candidate_Device_IDs or []) == sorted(decision.candidates):
            return item

    mac = next((e.value for e in decision.evidence if e.kind is IdentifierKind.MAC), None)
    item = DeviceReviewItem(
        Kind=decision.review_kind, IP_Address=decision.ip, MAC_Address=mac,
        Message=decision.review_message[:255], Candidate_Device_IDs=sorted(decision.candidates),
        DiscoveryStatusID=discovery_status_id,
    )
    db.session.add(item)
    current_app.logger.warning("Device review item: %s", decision.review_message)
    return item


def create_device(decision, observation, discovery_status_id):
    """
    Create a NetworkDiscovery row for a "new"/"conflict"/"changed"/"reuse"
    decision, with its stable Nagios host name, evidence and first address
    row. Evidence owned by another device is not attached. Does not commit.
    """
    now = utcnow()
    dns_name = observation.get("hostname")
    device = NetworkDiscovery(
        Hostname=dns_name,
        Nagios_Host_Name=create_stable_host_name(dns_name, observation.get("ncpa_node_name")),
        IP_Address=decision.ip,
        Network=decision.network,
        MAC_Address=observation.get("mac_address"),
        OS_Type=observation.get("os"),
        Identity_Confidence=confidence_from_evidence(decision.evidence),
        Device_State=DeviceState.ACTIVE,
        Addressing=AddressingMode.UNKNOWN,
        First_Seen_At=now, Last_Seen_At=now, Missed_Scans=0,
        DiscoveryStatusID=discovery_status_id,
    )
    db.session.add(device)
    db.session.flush()

    rejected = attach_identifiers(device, decision.evidence)
    if rejected:
        # Whatever could not be attached belongs to someone else, so this
        # device is not verified by it.
        device.Identity_Confidence = confidence_from_evidence(
            [e for e in decision.evidence if e not in rejected]
        )
    open_address(device, decision.ip, decision.network, observation.get("mac_address"))
    if observation.get("os") == "Linux":
        ensure_ncpa_records(device)
    return device


def ensure_ncpa_records(device):
    """
    Give a Linux device the SSH credential and NCPA deployment placeholders
    used by the deployment flow, once. Does nothing for a device that already
    has a deployment record, so a rescan never resets NCPA state. The SSH port
    starts as the standard one, never the port of a previously scanned host;
    trust confirmation replaces it with the port SSH was found on. Does not
    commit.
    """
    has_deployment = db.session.scalar(
        sa.select(NCPADeployment.NCPADeployID).where(
            NCPADeployment.NetworkDiscoveryID == device.NetDiscoveryID
        )
    )
    if has_deployment is not None:
        return False

    device.NCPA_Eligible = True
    db.session.add(SSHCredentials(
        SSH_Port=int(current_app.config["SSH_PORT"]),
        Key_Installed=False, Key_Fingerprint=None, Created_At=None,
        NetworkDiscoveryID=device.NetDiscoveryID,
    ))
    db.session.add(NCPADeployment(
        Agent_Status=AgentStatus.PENDING_NCPA,
        NetworkDiscoveryID=device.NetDiscoveryID,
    ))
    db.session.flush()
    return True


def apply_match(device, decision, observation, discovery_status_id):
    """
    Update a matched device from an observation: record an address change,
    refresh what the scan saw, store new evidence, reactivate it if it was
    MISSING / ADDRESS_UNKNOWN / RETIRED. Does not commit.
    """
    ip, network = decision.ip, decision.network
    mac = observation.get("mac_address")
    old_ip = device.IP_Address

    if old_ip != ip or device.Network != network:
        current_app.logger.info(
            "Device %s moved from %s to %s", device.Nagios_Host_Name, old_ip, ip
        )
        if device.Addressing is AddressingMode.STATIC:
            moved = Decision("static", ip, network, decision.evidence,
                             review_kind=ReviewKind.STATIC_MOVED,
                             review_message=f"{device.Nagios_Host_Name} is marked static but moved from {old_ip} to {ip}.",
                             candidates=[device.NetDiscoveryID])
            add_review_item(moved, discovery_status_id)
        elif device.Addressing is AddressingMode.UNKNOWN:
            # An observed change is the evidence that the device is on DHCP.
            device.Addressing = AddressingMode.DHCP
        device.IP_Address = ip
        device.Network = network

    open_address(device, ip, network, mac)

    if observation.get("hostname") and observation["hostname"] != "Unknown":
        device.Hostname = observation["hostname"]
    if mac:
        device.MAC_Address = mac

    os_type = observation.get("os")
    previous_os = device.OS_Type
    # A failed OS detection must not erase a known OS.
    if os_type and (os_type != "Unknown" or not previous_os):
        device.OS_Type = os_type
    if os_type == "Linux" and previous_os != "Linux":
        ensure_ncpa_records(device)

    if decision.confidence is not None:
        device.Identity_Confidence = decision.confidence
    attach_identifiers(device, decision.evidence)

    if device.Device_State is not DeviceState.ACTIVE:
        current_app.logger.info("Device %s is active again", device.Nagios_Host_Name)
    device.Device_State = DeviceState.ACTIVE
    device.Last_Seen_At = utcnow()
    device.Missed_Scans = 0
    device.DiscoveryStatusID = discovery_status_id


def mark_address_unknown(device):
    """The device's IP now belongs to a different device; stop checking that address."""
    device.Device_State = DeviceState.ADDRESS_UNKNOWN
    close_address(device)


# ==========================================================
# RECONCILE A WHOLE SCAN
# ==========================================================

def reconcile_scan(discovered_hosts, discovery_status_id, skip_ips=()):
    """
    Reconcile every observation of a scan against the known devices.

    discovered_hosts is discover_network()'s dict ({network: {ip: {"data":
    {...}, "services": {...}}}}); each host's data may carry "identifiers" (a
    list of (IdentifierKind, value) from probes). skip_ips are never saved
    (the PinPoint server itself).

    Returns {(network, ip): device} for every observation that became or
    matched a device; secondary addresses of a multi-NIC device are not
    included. Updates device lifecycle for devices the scan did not see.
    Does not commit.
    """
    observations = []
    for network, hosts in discovered_hosts.items():
        for ip, host_data in hosts.items():
            if ip in skip_ips:
                continue
            data = host_data["data"]
            evidence = build_evidence(data.get("mac_address"), data.get("identifiers"), data.get("hostname"))
            observations.append((network, ip, data, evidence))

    # Pass one: read-only resolution.
    decisions = [
        (resolve_observation(ip, network, evidence), data)
        for network, ip, data, evidence in observations
    ]

    # Several observations resolving to one device (multi-NIC, or a clone):
    # keep one primary address, record the rest as secondary.
    by_device = {}
    for decision, data in decisions:
        if decision.action == "match":
            by_device.setdefault(decision.device.NetDiscoveryID, []).append((decision, data))

    secondary = set()
    for group in by_device.values():
        if len(group) < 2:
            continue
        device = group[0][0].device
        primary = next((g for g in group if g[0].ip == device.IP_Address), None)
        if primary is None:
            primary = group[0]
        for member in group:
            if member is not primary:
                secondary.add(id(member[0]))

    result = {}
    matched_ids = set()
    matched_in_scan = set(by_device)

    # Pass two: apply.
    for decision, data in decisions:
        if id(decision) in secondary:
            device = decision.device
            mac = data.get("mac_address")
            record_secondary_address(device, decision.ip, decision.network, mac)
            known_macs = device_identifier_values(device.NetDiscoveryID, IdentifierKind.MAC)
            new_mac = normalize_mac(mac) if is_hardware_mac(mac) else None
            if new_mac and new_mac not in known_macs:
                dup = Decision("dup", decision.ip, decision.network, decision.evidence,
                               review_kind=ReviewKind.DUPLICATE_IDENTITY,
                               review_message=f"{device.Nagios_Host_Name} was seen on {decision.ip} as well as "
                                              f"{device.IP_Address}: a second network card or a cloned VM. "
                                              "Only the first address is monitored.",
                               candidates=[device.NetDiscoveryID])
                add_review_item(dup, discovery_status_id)
                attach_identifiers(device, [e for e in decision.evidence if e.kind is IdentifierKind.MAC])
            matched_ids.add(device.NetDiscoveryID)
            continue

        if decision.action == "match":
            apply_match(decision.device, decision, data, discovery_status_id)
            device = decision.device
            if decision.review_kind is not None:
                add_review_item(decision, discovery_status_id)
        else:
            # A displaced device that this same scan matched elsewhere simply
            # moved; it must not be marked unknown after it was reactivated.
            if decision.action == "reuse" and decision.displaced.NetDiscoveryID not in matched_in_scan:
                mark_address_unknown(decision.displaced)
            # An earlier scan may already have created this device; a repeat
            # conflict must not create it again.
            device = decision.device
            if device is not None:
                apply_match(device, decision, data, discovery_status_id)
            else:
                device = create_device(decision, data, discovery_status_id)
            # Only decisions the reconciler refused to make on its own are
            # reviewed; a plain new device is not.
            if decision.review_kind is not None:
                add_review_item(decision, discovery_status_id)

        matched_ids.add(device.NetDiscoveryID)
        result[(decision.network, decision.ip)] = device

    update_unseen_devices(matched_ids, set(discovered_hosts))
    return result


def update_unseen_devices(matched_ids, scanned_networks):
    """
    Lifecycle for devices the scan did not match (plan section 6):
    - a device whose IP was taken over by a device that WAS matched becomes
      ADDRESS_UNKNOWN, so checks stop hitting the wrong machine;
    - otherwise it counts a missed scan, and becomes MISSING after
      DEVICE_MISSING_AFTER_SCANS;
    - MISSING / ADDRESS_UNKNOWN for DEVICE_RETIRE_AFTER_DAYS becomes RETIRED.
    Devices on networks that were not scanned are left alone. Does not commit.
    """
    missing_after = current_app.config["DEVICE_MISSING_AFTER_SCANS"]
    retire_after = timedelta(days=current_app.config["DEVICE_RETIRE_AFTER_DAYS"])
    now = utcnow()

    holders = {}
    if matched_ids:
        for device in db.session.scalars(
            sa.select(NetworkDiscovery).where(NetworkDiscovery.NetDiscoveryID.in_(list(matched_ids)))
        ).all():
            holders[(device.Network, device.IP_Address)] = device.NetDiscoveryID

    unseen = db.session.scalars(
        sa.select(NetworkDiscovery).where(
            NetworkDiscovery.Device_State.in_(
                (DeviceState.ACTIVE, DeviceState.MISSING, DeviceState.ADDRESS_UNKNOWN)
            ),
            NetworkDiscovery.NetDiscoveryID.not_in(list(matched_ids) or [-1]),
        )
    ).all()

    for device in unseen:
        if device.Network not in scanned_networks:
            continue

        if device.Device_State is DeviceState.ACTIVE:
            if holders.get((device.Network, device.IP_Address), device.NetDiscoveryID) != device.NetDiscoveryID:
                mark_address_unknown(device)
                continue
            device.Missed_Scans = (device.Missed_Scans or 0) + 1
            if device.Missed_Scans >= missing_after:
                device.Device_State = DeviceState.MISSING

        last_seen = device.Last_Seen_At
        if last_seen is not None and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        if (
            device.Device_State in (DeviceState.MISSING, DeviceState.ADDRESS_UNKNOWN)
            and last_seen is not None
            and now - last_seen > retire_after
        ):
            device.Device_State = DeviceState.RETIRED
            close_address(device)
