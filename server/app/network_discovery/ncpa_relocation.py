"""
NCPA relocation: find NCPA devices that changed IP between full scans.

A full discovery runs every few hours (scanFrequency), so a DHCP device whose
lease changed would be checked at the wrong address for that long. This job
runs every few minutes and, only when an NCPA device is DOWN or UNREACHABLE:

1. runs a fast "nmap -p <NCPA port> --open" sweep of the configured networks
   (no service or OS detection) - skipped while a full discovery is running;
2. reads the TLS certificate fingerprint of each responder - no NCPA token
   is ever sent, so an unknown host on a reused IP learns nothing;
3. matches fingerprints to the stored NCPA_CERT identifiers of the down
   devices and, on a match, moves the device to its new address
   (DeviceAddressHistory source NCPA_RELOCATE) and regenerates the Nagios
   config.

Only devices that PinPoint deployed NCPA to (a stored certificate fingerprint
and a token) can be relocated this way.
"""

import nmap3
import sqlalchemy as sa
from flask import current_app

from app import db
from app.network_discovery.device_identity import (
    mark_address_unknown,
    open_address,
    utcnow,
)
from app.network_discovery.identity_probes import tls_certificate_fingerprint
from app.system_models import (
    AddressSource,
    DeviceIdentifier,
    DeviceState,
    IdentifierKind,
    NCPADeployment,
    NetworkDiscovery,
)


def find_devices_to_relocate():
    """
    Return the NCPA devices worth looking for: ACTIVE or MISSING, with a
    deployed token and a stored NCPA certificate fingerprint, whose latest
    Nagios host status is DOWN or UNREACHABLE. Read-only.
    """
    from app.api.system.statistics import get_latest_hosts
    from app.history_models import HostStateType
    from app.network_discovery.device_identity import nagios_host_name

    candidates = db.session.scalars(
        sa.select(NetworkDiscovery)
        .join(NCPADeployment, NCPADeployment.NetworkDiscoveryID == NetworkDiscovery.NetDiscoveryID)
        .join(DeviceIdentifier, DeviceIdentifier.NetDiscoveryID == NetworkDiscovery.NetDiscoveryID)
        .where(
            NCPADeployment.Token.is_not(None),
            DeviceIdentifier.Kind == IdentifierKind.NCPA_CERT,
            NetworkDiscovery.Device_State.in_((DeviceState.ACTIVE, DeviceState.MISSING)),
        )
        .distinct()
    ).all()
    if not candidates:
        return []

    down = {
        host.Hostname
        for host in get_latest_hosts()
        if host.Current_State in (HostStateType.DOWN, HostStateType.UNREACHABLE)
    }
    return [device for device in candidates if nagios_host_name(device) in down]


def sweep_ncpa_port(network):
    """
    Fast scan of one network for hosts with the NCPA port open. Returns the
    set of responding IPv4 addresses. No service or OS detection.
    """
    port = str(current_app.config["NCPA_PORT"])
    nmap = nmap3.Nmap(path="/usr/local/bin/nmap-sudo")
    xmlroot = nmap.scan_command(network, f"-p {port} -n -T4", "--open")

    responders = set()
    for host in xmlroot.findall("host"):
        state = host.find("status")
        if state is not None and state.get("state") != "up":
            continue
        port_element = host.find(f"ports/port[@portid='{port}']/state")
        if port_element is None or port_element.get("state") != "open":
            continue
        for address in host.findall("address"):
            if address.attrib.get("addrtype") == "ipv4":
                responders.add(address.attrib["addr"])
    return responders


def discovery_is_running():
    """True while a full network discovery thread is alive."""
    from app.api.system import network_discovery as nd

    thread = nd.discovery_thread
    return thread is not None and thread.is_alive()


def move_device(device, ip, network):
    """
    Move a device to a newly found address: update IP and network, record the
    change as an NCPA_RELOCATE address row, reactivate it, and mark any other
    device still recorded at that address as address-unknown. Does not commit.
    """
    previous = device.IP_Address
    others = db.session.scalars(
        sa.select(NetworkDiscovery).where(
            NetworkDiscovery.IP_Address == ip,
            NetworkDiscovery.Network == network,
            NetworkDiscovery.NetDiscoveryID != device.NetDiscoveryID,
            NetworkDiscovery.Device_State.in_((DeviceState.ACTIVE, DeviceState.MISSING)),
        )
    ).all()
    for other in others:
        mark_address_unknown(other)

    device.IP_Address = ip
    device.Network = network
    device.Device_State = DeviceState.ACTIVE
    device.Missed_Scans = 0
    device.Last_Seen_At = utcnow()
    open_address(device, ip, network, device.MAC_Address, source=AddressSource.NCPA_RELOCATE)
    current_app.logger.info(
        "NCPA relocation: %s moved from %s to %s", device.Nagios_Host_Name, previous, ip
    )


def relocate_ncpa_devices():
    """
    One run of the relocation job (see the module docstring). Returns the
    list of device IDs that were moved; empty when nothing was down, a full
    discovery is running, or no certificate matched. Commits and regenerates
    the Nagios config only if something moved.
    """
    if discovery_is_running():
        return []

    candidates = find_devices_to_relocate()
    if not candidates:
        return []

    wanted = {}
    for device in candidates:
        for value in db.session.scalars(
            sa.select(DeviceIdentifier.Value).where(
                DeviceIdentifier.NetDiscoveryID == device.NetDiscoveryID,
                DeviceIdentifier.Kind == IdentifierKind.NCPA_CERT,
            )
        ).all():
            wanted[value] = device

    port = current_app.config["NCPA_PORT"]
    moved = []
    for network in current_app.config["NETWORKS"]:
        try:
            responders = sweep_ncpa_port(network)
        except Exception:
            current_app.logger.exception("NCPA relocation sweep failed for %s", network)
            continue

        for ip in sorted(responders):
            fingerprint = tls_certificate_fingerprint(ip, port)
            device = wanted.get(fingerprint) if fingerprint else None
            if device is None or device.NetDiscoveryID in moved:
                continue
            if device.IP_Address == ip:
                continue  # still where we think it is; its failure is something else
            move_device(device, ip, network)
            moved.append(device.NetDiscoveryID)

    if not moved:
        return []

    db.session.commit()

    from app.network_discovery.create_host_cfg import regenerate_and_apply_config

    changed, message = regenerate_and_apply_config()
    current_app.logger.info("NCPA relocation config: %s", message)
    return moved
