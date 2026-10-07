"""
Plugin reconciler: keeps PluginConfiguration in step with what Plugin Manager
and Network Discovery say should be monitored.

Plugin Manager is the on/off switch and Network Discovery supplies the devices
and ports, so nobody picks devices by hand. This module computes the services
that should exist (a monitored port whose plugin is Enabled or Active, one entry
per metric for SNMP/NCPA), makes the AUTO rows of PLUGIN_CONFIGURATION match,
and asks the one existing Nagios writer, regenerate_and_apply_config_status(),
to validate, back up, reload and roll back. The services themselves are planned
by create_host_cfg.plan_host_services(), the same planner that writes hosts.cfg,
so a row here is exactly a service there.

Rows with Origin MANUAL (created by hand before this existed) are never touched.
Nothing is generated for the monitoring server: it is never a NetworkDiscovery
device (see create_host_cfg.get_monitoring_server_ips).

Functions
---------
desired_services()
    The services that should exist right now, read-only.
preview_enable(plugin_name)
    What enabling one more plugin would attach, read-only.
reconcile_plugin_monitoring(user_id)
    Promote identified ports, sync the rows, apply, set plugin states.
"""
from datetime import datetime, timezone

import sqlalchemy as sa
from flask import current_app

from app import db
from app.api.plugin.service import record_plugin_action
from app.network_discovery.create_host_cfg import (
    _load_monitored_hosts,
    load_host_plugin_facts,
    plan_host_services,
    regenerate_and_apply_config_status,
)
from app.network_discovery.plugin_registry import normalize_plugin_name, plugin_for_definition, resolve_plugin_name
from app.network_discovery.port_lifecycle import (
    enabled_plugin_names,
    promotable_ports,
    promote_identified_ports,
    transport_for,
)
from app.plugin_models import (
    Plugin,
    PluginActionResult,
    PluginConfiguration,
    PluginConfigurationOrigin,
    PluginConfigurationStatus,
    PluginHistoryAction,
    PluginStatus,
)


# ==========================================================
# DESIRED STATE
# ==========================================================

def desired_services():
    """
    Return the services that should be monitored now as a list of dicts with
    net_discovery_id, plugin (the Plugin Manager name, e.g. "check_ssh"), name
    (e.g. "ssh-22-tcp"), port, protocol and metric. Only ports that produce a
    Nagios service (Monitored or Missing) on scanned, non-retired devices are
    considered, and only when their plugin is Enabled or Active. Reads the
    database; changes nothing.
    """
    enabled_plugins = enabled_plugin_names()
    if not enabled_plugins:
        return []

    facts = load_host_plugin_facts()
    desired = []
    for hosts in _load_monitored_hosts().values():
        for host_data in hosts.values():
            device_id = host_data["data"].get("net_discovery_id")
            if device_id is None:
                continue
            for service in plan_host_services(host_data, facts, current_app.config, None, enabled_plugins):
                desired.append({
                    "net_discovery_id": device_id,
                    "plugin": plugin_for_definition(service["plugin"]),
                    "name": service["name"],
                    "port": service["port"],
                    "protocol": service["protocol"],
                    "metric": service["metric"],
                })
    return desired


def preview_enable(plugin_name):
    """
    Count what enabling plugin_name (a Plugin Manager name such as "check_ssh")
    would monitor on top of what is enabled now: the services the planner would
    generate for it from ports that are monitored or missing, plus identified
    suggestions it would promote. Returns {"matched_services": n,
    "matched_devices": m, "held_ports": k}, where held_ports counts identified
    suggestions of this plugin that are held back (set to Suggested by an admin, or
    left Suggested at an upgrade) and so are not attached. Read-only: nothing is
    promoted or saved.
    """
    plugin_name = normalize_plugin_name(plugin_name)
    enabled_plugins = enabled_plugin_names() | {plugin_name}

    hosts = {}
    for network_hosts in _load_monitored_hosts().values():
        for host_data in network_hosts.values():
            device_id = host_data["data"].get("net_discovery_id")
            if device_id is not None:
                hosts[device_id] = host_data

    for protocol, port in promotable_ports(enabled_plugins):
        host_data = hosts.get(port.NetDiscoveryID)
        if host_data is None:
            continue
        host_data["services"][protocol][str(port.Port_Number)] = {
            "service_name": port.Service_Name,
            "plugin_name": resolve_plugin_name(port.Service_Name, transport_for(protocol)),
        }

    facts = load_host_plugin_facts()
    services = 0
    devices = set()
    for device_id, host_data in hosts.items():
        for service in plan_host_services(host_data, facts, current_app.config, None, enabled_plugins):
            if plugin_for_definition(service["plugin"]) == plugin_name:
                services += 1
                devices.add(device_id)
    held = 0
    for protocol, port in promotable_ports(enabled_plugins, include_held=True):
        if port.Promotion_Held:
            definition_name = resolve_plugin_name(port.Service_Name, transport_for(protocol))
            if plugin_for_definition(definition_name) == plugin_name:
                held += 1
    return {"matched_services": services, "matched_devices": len(devices), "held_ports": held}


# ==========================================================
# RECONCILE
# ==========================================================

def utcnow():
    return datetime.now(timezone.utc)


def sync_rows(desired):
    """
    Make the AUTO PluginConfiguration rows match desired. Returns
    (added, removed): the rows created (status Pending) and the number deleted.
    MANUAL rows are never read or changed. Flushes; does not commit.
    """
    plugins_by_name = {
        normalize_plugin_name(plugin.Name): plugin
        for plugin in db.session.scalars(sa.select(Plugin).where(Plugin.Status.in_(
            (PluginStatus.ENABLED, PluginStatus.ACTIVE)
        ))).all()
    }

    wanted = {}
    for service in desired:
        plugin = plugins_by_name.get(service["plugin"])
        if plugin is not None:
            wanted[(plugin.PluginID, service["net_discovery_id"], service["name"])] = service

    existing = {}
    for row in db.session.scalars(sa.select(PluginConfiguration).where(
        PluginConfiguration.Origin == PluginConfigurationOrigin.AUTO
    )).all():
        existing[(row.PluginID, row.NetDiscoveryID, row.Nagios_Service_Name)] = row

    removed = 0
    for key, row in existing.items():
        if key not in wanted:
            db.session.delete(row)
            removed += 1

    added = []
    for key, service in wanted.items():
        if key in existing:
            continue
        row = PluginConfiguration(
            PluginID=key[0],
            NetDiscoveryID=key[1],
            Service_Description=service["name"],
            Nagios_Service_Name=service["name"],
            Port_Number=service["port"],
            Protocol=service["protocol"],
            Metric=service["metric"],
            Status=PluginConfigurationStatus.PENDING,
            Origin=PluginConfigurationOrigin.AUTO,
        )
        db.session.add(row)
        added.append(row)

    db.session.flush()
    return added, removed


def set_plugin_states():
    """
    Mark every Enabled or Active plugin Active when at least one applied
    configuration backs it and Enabled when none does. Plugins in any other
    state are left alone. Does not commit.
    """
    backed = set(db.session.scalars(
        sa.select(PluginConfiguration.PluginID).where(
            PluginConfiguration.Status == PluginConfigurationStatus.APPLIED
        ).distinct()
    ).all())
    for plugin in db.session.scalars(sa.select(Plugin).where(
        Plugin.Status.in_((PluginStatus.ENABLED, PluginStatus.ACTIVE))
    )).all():
        plugin.Status = PluginStatus.ACTIVE if plugin.PluginID in backed else PluginStatus.ENABLED


def reconcile_plugin_monitoring(user_id=None):
    """
    Bring monitoring in line with Plugin Manager. In order: promote identified
    ports whose plugin is now enabled; create or delete the AUTO configuration
    rows; regenerate and apply hosts.cfg once through the shared pipeline
    (validated, backed up, rolled back on failure); then mark the rows Applied
    and set each plugin Active or Enabled. If Nagios rejects the new config
    nothing in the database changes, the failure is recorded in the history of
    the plugins that were being attached (when user_id is given), and the
    result says why. Idempotent; commits.

    Returns {"success": bool, "changed": a new host config went live,
    "applied": rows added, "removed": rows deleted, "promoted": ports promoted,
    "message": str}.
    """
    try:
        promoted = promote_identified_ports()
        added, removed = sync_rows(desired_services())
        status, message = regenerate_and_apply_config_status()
    except Exception:
        db.session.rollback()
        raise

    if status == "failed":
        attached_plugins = {row.PluginID for row in added}
        db.session.rollback()
        if user_id is not None:
            for plugin in db.session.scalars(
                sa.select(Plugin).where(Plugin.PluginID.in_(attached_plugins))
            ).all():
                record_plugin_action(
                    plugin, PluginHistoryAction.CONFIGURE, PluginActionResult.FAILED, user_id,
                    message=f"Automatic attach failed: {message[:400]}",
                )
            db.session.commit()
        return {"success": False, "changed": False, "applied": 0, "removed": 0, "promoted": 0, "message": message}

    now = utcnow()
    for row in added:
        row.Status = PluginConfigurationStatus.APPLIED
        row.Applied_At = now
    db.session.flush()
    set_plugin_states()

    if user_id is not None:
        counts = {}
        for row in added:
            counts[row.PluginID] = counts.get(row.PluginID, 0) + 1
        for plugin in db.session.scalars(
            sa.select(Plugin).where(Plugin.PluginID.in_(counts))
        ).all():
            record_plugin_action(
                plugin, PluginHistoryAction.CONFIGURE, PluginActionResult.SUCCESS, user_id,
                new_value=plugin.Name,
                message=f"Automatically attached {counts[plugin.PluginID]} service(s) from discovered ports.",
            )

    db.session.commit()
    return {
        "success": True,
        "changed": status == "applied",
        "applied": len(added),
        "removed": removed,
        "promoted": promoted,
        "message": message,
    }
