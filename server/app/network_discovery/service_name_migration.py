"""
Carry service history across the service-naming change.

Services used to be named "ssh", "dns-TCP" or "ncpa-cpu-5693-TCP"; they are
now "{service}[-{metric}]-{port}-{protocol}" in lowercase. Status history and
acknowledgements are keyed by (hostname, service name), so without this they
would be orphaned by the first regeneration after the change.

After a config is applied, rows stored under a legacy name are renamed to the
new name of the same service. A legacy name is only matched when exactly one
service of the host could own it ("ssh" with both ssh-22-tcp and ssh-22-udp
is ambiguous and left alone), and a rename that would collide with an
existing row is skipped. Nothing here commits; the caller owns the session.
"""

import re

import sqlalchemy as sa

from app import db
from app.history_models import ServiceStatus
from app.system_models import AckHistory, AlertAcknowledgement

_NEW_NAME = re.compile(r"^(?P<stem>.+)-(?P<port>\d+)-(?P<proto>tcp|udp)$")


def legacy_service_names(new_name):
    """Lowercased names an old config could have used for this service."""
    match = _NEW_NAME.match(new_name.lower())
    if not match:
        return set()
    stem, port, proto = match["stem"], match["port"], match["proto"]
    return {stem, f"{stem}-{proto}", f"{stem}-{port}-{proto}"} - {new_name.lower()}


def legacy_name_map(new_names):
    """{legacy lowercase name: new name} for the names that are unambiguous."""
    owners = {}
    for new_name in new_names:
        for legacy in legacy_service_names(new_name):
            owners.setdefault(legacy, set()).add(new_name)
    # A legacy name that is itself a current name is not legacy.
    current = {name.lower() for name in new_names}
    return {
        legacy: next(iter(candidates))
        for legacy, candidates in owners.items()
        if len(candidates) == 1 and legacy not in current
    }


def migrate_legacy_service_history(names_by_host):
    """
    Rename legacy-named history and acknowledgement rows for every host in
    names_by_host ({hostname: [service names]}). Returns the number of rows
    renamed.
    """
    renamed = 0
    for hostname, names in names_by_host.items():
        mapping = legacy_name_map(names)
        if not mapping:
            continue

        for model, host_col, name_col in (
            (ServiceStatus, ServiceStatus.Hostname, ServiceStatus.Service),
            (AlertAcknowledgement, AlertAcknowledgement.Hostname, AlertAcknowledgement.Service_Name),
            (AckHistory, AckHistory.Hostname, AckHistory.Service_Name),
        ):
            rows = db.session.scalars(
                sa.select(model).where(host_col == hostname, sa.func.lower(name_col).in_(list(mapping)))
            ).all()
            for row in rows:
                target = mapping[getattr(row, name_col.key).lower()]
                if model is AlertAcknowledgement and db.session.scalar(
                    sa.select(AlertAcknowledgement.AckID).where(
                        AlertAcknowledgement.Hostname == hostname,
                        AlertAcknowledgement.Service_Name == target)
                ) is not None:
                    continue
                setattr(row, name_col.key, target)
                renamed += 1
    return renamed
