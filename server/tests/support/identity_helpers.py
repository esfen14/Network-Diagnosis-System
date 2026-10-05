"""
tests/support/identity_helpers.py
=========================
Shared builders for the device-identity tests (reconciler, port lifecycle,
config generation, NCPA identity, routes). Import from here rather than
repeating them in each file.

    from tests.support.identity_helpers import NET, make_status, scan, run_scan, ...
"""

from contextlib import contextmanager

import sqlalchemy as sa

from app import db
from app.network_discovery.device_identity import reconcile_scan
from app.network_discovery.port_lifecycle import process_device_ports
from app.system_models import (
    ActivityLog,
    DeviceAddressHistory,
    DeviceIdentifier,
    DeviceReviewItem,
    DiscoveryStatus,
    IdentifierKind,
    NetworkDiscovery,
    NetworkDiscoveryStatus,
)

NET = "10.0.0.0/24"

# Universally administered MACs (locally-administered bit clear).
MAC_1 = "00:11:22:33:44:01"
MAC_2 = "00:11:22:33:44:02"
MAC_3 = "00:11:22:33:44:03"
# Randomized MAC: second-lowest bit of the first octet is set.
RANDOM_MAC = "02:11:22:33:44:99"

SSH_1 = "SSHKEY1"
SSH_2 = "SSHKEY2"
CERT_1 = "a" * 64
CERT_2 = "b" * 64


@contextmanager
def patched_config(app, **overrides):
    """Temporarily override app.config keys, restoring them afterwards."""
    original = {key: app.config.get(key) for key in overrides}
    app.config.update(overrides)
    try:
        yield
    finally:
        app.config.update(original)


def make_status(db_session, user):
    """Create the NetworkDiscoveryStatus row every device points at; returns its ID."""
    log = ActivityLog(Action_Type="test", UserID=user.UserID)
    db_session.session.add(log)
    db_session.session.flush()
    status = NetworkDiscoveryStatus(
        Status=DiscoveryStatus.SUCCESS, Progress=100, Message="done", LogID=log.LogID
    )
    db_session.session.add(status)
    db_session.session.flush()
    return status.DiscoveryStatusID


def scan(ip, mac=None, hostname="Unknown", os="Linux", identifiers=(), tcp=None, udp=None, network=NET):
    """One host as discover_network() reports it, in a one-network scan dict."""
    return {
        network: {
            ip: {
                "data": {
                    "hostname": hostname,
                    "mac_address": mac,
                    "os": os,
                    "identifiers": list(identifiers),
                },
                "services": {
                    "tcp": {str(p): {"service_name": n, "identified_by": "FINGERPRINT"} for p, n in (tcp or {}).items()},
                    "udp": {str(p): {"service_name": n, "identified_by": "FINGERPRINT"} for p, n in (udp or {}).items()},
                },
            }
        }
    }


def combine(*scans):
    """Merge several scan() dicts into one scan result."""
    merged = {}
    for single in scans:
        for network, hosts in single.items():
            merged.setdefault(network, {}).update(hosts)
    return merged


def run_scan(db_session, status_id, discovered, skip_ips=()):
    """
    Reconcile a scan and process its ports like _save_discovered_hosts does,
    then commit. Returns {(network, ip): device}.
    """
    devices = reconcile_scan(discovered, status_id, skip_ips)
    for (network, ip), device in devices.items():
        process_device_ports(device, discovered[network][ip].get("services", {}), host_seen=True)
    db_session.session.commit()
    return devices


def ssh(value):
    return (IdentifierKind.SSH_HOST_KEY, value)


def cert(value):
    return (IdentifierKind.NCPA_CERT, value)


def machine_id(value):
    return (IdentifierKind.MACHINE_ID, value)


def all_devices():
    return db.session.scalars(sa.select(NetworkDiscovery).order_by(NetworkDiscovery.NetDiscoveryID)).all()


def open_addresses(device):
    return db.session.scalars(
        sa.select(DeviceAddressHistory).where(
            DeviceAddressHistory.NetDiscoveryID == device.NetDiscoveryID,
            DeviceAddressHistory.Closed_At.is_(None),
        )
    ).all()


def address_rows(device):
    return db.session.scalars(
        sa.select(DeviceAddressHistory)
        .where(DeviceAddressHistory.NetDiscoveryID == device.NetDiscoveryID)
        .order_by(DeviceAddressHistory.AddressID)
    ).all()


def identifier_values(device, kind):
    return set(db.session.scalars(
        sa.select(DeviceIdentifier.Value).where(
            DeviceIdentifier.NetDiscoveryID == device.NetDiscoveryID,
            DeviceIdentifier.Kind == kind,
        )
    ).all())


def review_items(kind=None):
    query = sa.select(DeviceReviewItem)
    if kind is not None:
        query = query.where(DeviceReviewItem.Kind == kind)
    return db.session.scalars(query.order_by(DeviceReviewItem.ReviewID)).all()
