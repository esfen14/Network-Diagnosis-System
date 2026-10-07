"""
custom_checks.py — storage and Nagios changes for custom checks.

A custom check is one PLUGIN_CONFIGURATION row (Origin CUSTOM): an administrator
runs a plugin discovery cannot attach to a port against one discovered device,
with arguments they supply (docs/plans/Custom_Checks_Plan.md). Plugins that
take them, and what each accepts, are in network_discovery/custom_checks.py.

Every change saves the row, regenerates hosts.cfg through the shared writer
(validated, backed up, rolled back on failure) and, if Nagios does not accept
it, undoes the change and raises MonitoringChangeError, so the database never
claims a check Nagios is not running. Each change is written to the plugin
history. Kept apart from service.py as manager.py's routes call it directly.
"""
from datetime import datetime, timezone

import sqlalchemy as sa

from app import db
from app.api.plugin.service import (
    BLOCKED_TRANSITION_STATUSES,
    InvalidQueryError,
    MonitoringChangeError,
    PluginNotFoundError,
    describe_service_status,
    latest_service_results,
    record_plugin_action,
)
from app import secrets_store
from app.network_discovery import custom_checks
from app.network_discovery.create_host_cfg import regenerate_and_apply_config_status
from app.network_discovery.device_identity import nagios_host_name
from app.network_discovery.plugin_registry import PluginConfigurationError
from app.plugin_models import (
    Plugin, PluginActionResult, PluginConfiguration, PluginConfigurationOrigin,
    PluginConfigurationStatus, PluginHistoryAction,
)
from app.system_models import DeviceState, NetworkDiscovery

# Devices that are no longer monitored take no new checks.
UNMONITORED_DEVICE_STATES = (DeviceState.RETIRED, DeviceState.MERGED)


class CustomCheckError(Exception):
    """The request is not valid (unknown device, bad argument, name taken, plugin not supported)."""
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class CustomCheckNotFoundError(Exception):
    """No such custom check on this plugin."""
    def __init__(self, message="Custom check not found."):
        super().__init__(message)
        self.message = message


# ==========================================================
# READING
# ==========================================================

def get_plugin_or_raise(plugin_id):
    """The Plugin row, or PluginNotFoundError."""
    plugin = db.session.get(Plugin, plugin_id)
    if plugin is None:
        raise PluginNotFoundError()
    return plugin


def describe_custom_support(plugin):
    """
    What the plugin drawer needs to know about custom checks for this plugin:
    {"class": ..., "supported": bool, "note": str | None, "fields": [...]}. fields lists each
    argument as {"name", "flag", "label", "required", "placeholder"} in the order the form shows them.
    """
    plugin_class = custom_checks.plugin_class(plugin.Name)
    supported = custom_checks.is_custom_checkable(plugin.Name)
    return {
        "class": plugin_class,
        "supported": supported,
        # Where a check of this plugin runs: "device" (pick one) or "server" (the Nagios server).
        "target": custom_checks.check_target(plugin.Name),
        "note": custom_checks.PLUGIN_CLASS_NOTES.get(plugin_class),
        "fields": [
            {"name": f.name, "flag": f.flag, "label": f.label, "required": f.required,
             "placeholder": f.placeholder, "secret": f.secret}
            for f in custom_checks.plugin_fields(plugin.Name)
        ],
    }


def server_label():
    """The name a server check shows where a device would be."""
    return "Nagios server"


def serialize_target(device):
    """A check's target as {"id", "hostname", "ip_address"}: the device, or the Nagios server (id null)."""
    if device is None:
        return {"id": None, "hostname": server_label(), "ip_address": ""}
    return {"id": device.NetDiscoveryID, "hostname": nagios_host_name(device), "ip_address": device.IP_Address}


def target_host_name(device):
    """The Nagios host a check's service belongs to: the device's, or the server's own host."""
    return custom_checks.SERVER_HOST_NAME if device is None else nagios_host_name(device)


def serialize_check(row, device, result, now):
    """One check as the API returns it, with its device and live status."""
    data = row.Configuration_Data or {}
    paused = bool(data.get("paused"))
    if paused:
        status = {"kind": "paused", "state": None, "last_check": None, "output": "Paused. Nothing is checking this."}
    else:
        status = describe_service_status(result, row.Applied_At, now)
    return {
        "id": row.PluginConfigurationID,
        "name": row.Service_Description,
        "service": row.Nagios_Service_Name,
        "device": serialize_target(device),
        "variables": data.get("variables") or {},
        # Passwords are never returned: only which ones are set, and whether they can still be read.
        "secrets_set": sorted((data.get("secrets") or {}).keys()),
        "secrets_readable": all(secrets_store.is_readable(token) for token in (data.get("secrets") or {}).values()),
        "paused": paused,
        "running_since": row.Applied_At.isoformat() if row.Applied_At and not paused else None,
        "status": status,
    }


def search_devices(search, limit=20):
    """
    Devices a custom check can be added to, for the form's device picker: up to limit monitored
    devices whose name or IP contains search (case-insensitive), by name. Each item is
    {"id", "hostname", "ip_address"}.
    """
    query = sa.select(NetworkDiscovery).where(NetworkDiscovery.Device_State.not_in(UNMONITORED_DEVICE_STATES))
    needle = (search or "").strip()
    if needle:
        pattern = f"%{needle}%"
        query = query.where(sa.or_(
            NetworkDiscovery.Hostname.ilike(pattern),
            NetworkDiscovery.Nagios_Host_Name.ilike(pattern),
            NetworkDiscovery.IP_Address.ilike(pattern),
        ))
    devices = db.session.scalars(query.limit(500)).all()
    devices.sort(key=lambda device: nagios_host_name(device).lower())
    return [
        {"id": device.NetDiscoveryID, "hostname": nagios_host_name(device), "ip_address": device.IP_Address}
        for device in devices[:limit]
    ]


def list_custom_checks(plugin_id, page, per_page, search):
    """
    Paginated custom checks of a plugin, sorted by device then name, each with its device, arguments
    and live status (describe_service_status; "paused" for a paused one). search matches name,
    service, device hostname and IP. Raises PluginNotFoundError, InvalidQueryError.
    """
    get_plugin_or_raise(plugin_id)
    if page < 1:
        raise InvalidQueryError("Page must be greater than 0")
    if per_page < 1 or per_page > 100:
        raise InvalidQueryError("per_page must be between 1 and 100")

    pairs = []
    for row in db.session.scalars(sa.select(PluginConfiguration).where(
        PluginConfiguration.PluginID == plugin_id,
        PluginConfiguration.Origin == PluginConfigurationOrigin.CUSTOM,
    )).all():
        device = db.session.get(NetworkDiscovery, row.NetDiscoveryID) if row.NetDiscoveryID else None
        if device is not None or row.NetDiscoveryID is None:
            pairs.append((row, device))

    if search:
        needle = search.lower()
        pairs = [
            (row, device) for row, device in pairs
            if needle in (row.Service_Description or "").lower()
            or needle in (row.Nagios_Service_Name or "").lower()
            or needle in serialize_target(device)["hostname"].lower()
            or needle in serialize_target(device)["ip_address"]
        ]
    pairs.sort(key=lambda pair: (serialize_target(pair[1])["hostname"].lower(), (pair[0].Service_Description or "").lower()))

    total = len(pairs)
    pages = max(1, -(-total // per_page))
    window = pairs[(page - 1) * per_page: page * per_page]
    results = latest_service_results({(target_host_name(device), row.Nagios_Service_Name) for row, device in window})
    now = datetime.now(timezone.utc)
    return {
        "items": [
            serialize_check(row, device, results.get((target_host_name(device), row.Nagios_Service_Name)), now)
            for row, device in window
        ],
        "page": page, "per_page": per_page, "pages": pages, "total": total,
        "has_next": page < pages, "has_prev": page > 1,
    }


# ==========================================================
# CHANGING
# ==========================================================

def require_custom_plugin(plugin):
    """Raise CustomCheckError unless this plugin can take custom checks right now."""
    if not custom_checks.is_custom_checkable(plugin.Name):
        note = custom_checks.PLUGIN_CLASS_NOTES.get(custom_checks.plugin_class(plugin.Name))
        raise CustomCheckError(f"{plugin.Name} does not take custom checks." + (f" {note}" if note else ""))
    if plugin.Status in BLOCKED_TRANSITION_STATUSES:
        raise CustomCheckError(f"{plugin.Name} is in '{plugin.Status.value}' state; fix or validate it first.")


def get_device(device_id):
    """The monitored device, or CustomCheckError."""
    device = db.session.get(NetworkDiscovery, device_id) if isinstance(device_id, int) else None
    if device is None or device.Device_State in UNMONITORED_DEVICE_STATES:
        raise CustomCheckError("Device not found.")
    return device


def resolve_target(plugin, device_id):
    """
    The device a new check is added to, or None for a server check. A device plugin needs a device
    and a server plugin takes none; either mismatch raises CustomCheckError.
    """
    if custom_checks.check_target(plugin.Name) == "server":
        if device_id is not None:
            raise CustomCheckError(f"{plugin.Name} checks the Nagios server, so it takes no device.")
        return None
    if device_id is None:
        raise CustomCheckError("Choose a device.")
    return get_device(device_id)


def get_check(plugin_id, check_id):
    """The CUSTOM row of this plugin, or CustomCheckNotFoundError."""
    row = db.session.get(PluginConfiguration, check_id)
    if row is None or row.PluginID != plugin_id or row.Origin is not PluginConfigurationOrigin.CUSTOM:
        raise CustomCheckNotFoundError()
    return row


def apply_to_nagios(plugin_id, user_id, summary):
    """
    Regenerate and apply hosts.cfg for a change already flushed to the session. On success returns
    {"changed": bool, "message": str} (the caller commits). If Nagios does not accept it, rolls the
    session back, writes a Failed history row and raises MonitoringChangeError.
    """
    try:
        status, message = regenerate_and_apply_config_status()
    except Exception:
        db.session.rollback()
        raise
    if status == "failed":
        db.session.rollback()
        record_plugin_action(
            get_plugin_or_raise(plugin_id), PluginHistoryAction.CONFIGURE, PluginActionResult.FAILED, user_id,
            message=f"{summary}: {message[:380]}",
        )
        db.session.commit()
        raise MonitoringChangeError(message)
    return {"changed": status == "applied", "message": message}


def record_success(plugin, user_id, new_value, message):
    """Write the Success history row for a custom check change. Does not commit."""
    record_plugin_action(
        plugin, PluginHistoryAction.CONFIGURE, PluginActionResult.SUCCESS, user_id,
        new_value=new_value, message=message,
    )


def mark_applied(row):
    """Mark a row Applied now (keeps the original Applied_At when it has one)."""
    row.Status = PluginConfigurationStatus.APPLIED
    if row.Applied_At is None:
        row.Applied_At = datetime.now(timezone.utc)


def prepare_variables(plugin, variables, stored_secrets=None, clear_secrets=()):
    """
    Validate what an administrator typed and split it into what is stored: (public variables,
    encrypted secrets). stored_secrets are the passwords already saved on a check being changed:
    a password left blank keeps its stored value, unless it is in clear_secrets. Raises CustomCheckError
    for an invalid value, a missing required argument, an unreadable stored password that was not
    typed again, or when passwords cannot be stored at all (no fixed SECRET_KEY).
    """
    stored_secrets = stored_secrets or {}
    names = set(custom_checks.secret_names(plugin.Name))
    unknown = sorted(set(clear_secrets) - names)
    if unknown:
        raise CustomCheckError(f"'{unknown[0]}' is not a password of {plugin.Name}.")

    merged = dict(variables)
    for name in names:
        typed = str(merged.get(name) or "").strip()
        if typed or name in clear_secrets or name not in stored_secrets:
            continue
        try:
            merged[name] = secrets_store.decrypt(stored_secrets[name])
        except secrets_store.SecretsError:
            pass  # left out: a required one is reported below as missing
    try:
        cleaned = custom_checks.clean_variables(plugin.Name, merged)
    except PluginConfigurationError as error:
        raise CustomCheckError(str(error))

    public, secret_values = custom_checks.split_secrets(plugin.Name, cleaned)
    try:
        encrypted = {name: secrets_store.encrypt(value) for name, value in secret_values.items()}
    except secrets_store.SecretsError as error:
        raise CustomCheckError(error.message)
    return public, encrypted


def create_custom_check(plugin_id, device_id, name, variables, user_id):
    """
    Add a custom check of plugin_id on a device and apply it. Returns the serialized check plus
    {"changed", "message"} from Nagios. Raises PluginNotFoundError, CustomCheckError (plugin not
    supported, unknown device, bad name or argument, name already used on the device) and
    MonitoringChangeError (Nagios refused; nothing changed).
    """
    plugin = get_plugin_or_raise(plugin_id)
    require_custom_plugin(plugin)
    device = resolve_target(plugin, device_id)
    try:
        name = custom_checks.validate_check_name(name)
    except PluginConfigurationError as error:
        raise CustomCheckError(str(error))
    public, encrypted = prepare_variables(plugin, variables)

    service_name = custom_checks.service_name(plugin.Name, name)
    device_filter = (
        PluginConfiguration.NetDiscoveryID.is_(None) if device is None
        else PluginConfiguration.NetDiscoveryID == device.NetDiscoveryID
    )
    taken = db.session.scalar(sa.select(PluginConfiguration.PluginConfigurationID).where(
        device_filter, PluginConfiguration.Nagios_Service_Name == service_name,
    ))
    if taken is not None:
        raise CustomCheckError(
            f"The Nagios server already has a check named '{name}'." if device is None
            else f"This device already has a check named '{name}'."
        )

    row = PluginConfiguration(
        PluginID=plugin.PluginID, NetDiscoveryID=None if device is None else device.NetDiscoveryID,
        Service_Description=name,
        Nagios_Service_Name=service_name, Origin=PluginConfigurationOrigin.CUSTOM,
        Status=PluginConfigurationStatus.PENDING, Configuration_Data={"variables": public, "secrets": encrypted, "paused": False},
    )
    db.session.add(row)
    db.session.flush()

    applied = apply_to_nagios(plugin_id, user_id, f"Adding check '{name}' failed")
    mark_applied(row)
    record_success(plugin, user_id, service_name, f"Added check '{name}' on {target_host_name(device)}.")
    db.session.commit()
    return {**serialize_check(row, device, None, datetime.now(timezone.utc)), **applied}


def update_custom_check(plugin_id, check_id, name, variables, user_id, clear_secrets=()):
    """
    Rename a check and replace its arguments (the device cannot change; remove and add instead).
    A password left blank keeps the stored one; one named in clear_secrets is removed (only an
    optional password can be). Same errors as create_custom_check, plus CustomCheckNotFoundError.
    """
    plugin = get_plugin_or_raise(plugin_id)
    require_custom_plugin(plugin)
    row = get_check(plugin_id, check_id)
    device = db.session.get(NetworkDiscovery, row.NetDiscoveryID) if row.NetDiscoveryID else None
    try:
        name = custom_checks.validate_check_name(name)
    except PluginConfigurationError as error:
        raise CustomCheckError(str(error))
    stored = dict((row.Configuration_Data or {}).get("secrets") or {})
    public, encrypted = prepare_variables(plugin, variables, stored, clear_secrets)

    service_name = custom_checks.service_name(plugin.Name, name)
    clash = db.session.scalar(sa.select(PluginConfiguration.PluginConfigurationID).where(
        PluginConfiguration.NetDiscoveryID.is_(None) if row.NetDiscoveryID is None
        else PluginConfiguration.NetDiscoveryID == row.NetDiscoveryID,
        PluginConfiguration.Nagios_Service_Name == service_name,
        PluginConfiguration.PluginConfigurationID != row.PluginConfigurationID,
    ))
    if clash is not None:
        raise CustomCheckError(f"This device already has a check named '{name}'.")

    data = dict(row.Configuration_Data or {})
    data["variables"] = public
    data["secrets"] = encrypted
    row.Configuration_Data = data
    row.Service_Description = name
    row.Nagios_Service_Name = service_name
    db.session.flush()

    applied = apply_to_nagios(plugin_id, user_id, f"Changing check '{name}' failed")
    mark_applied(row)
    record_success(plugin, user_id, service_name, f"Changed check '{name}'.")
    db.session.commit()
    return {**serialize_check(row, device, None, datetime.now(timezone.utc)), **applied}


def set_check_paused(plugin_id, check_id, paused, user_id):
    """
    Pause a check (its service leaves Nagios, the row stays) or resume it. Repeating it reports
    changed false. Raises PluginNotFoundError, CustomCheckNotFoundError, CustomCheckError,
    MonitoringChangeError.
    """
    plugin = get_plugin_or_raise(plugin_id)
    row = get_check(plugin_id, check_id)
    device = db.session.get(NetworkDiscovery, row.NetDiscoveryID) if row.NetDiscoveryID else None
    if bool((row.Configuration_Data or {}).get("paused")) == paused:
        return {**serialize_check(row, device, None, datetime.now(timezone.utc)), "changed": False, "message": ""}
    if not paused:
        require_custom_plugin(plugin)

    data = dict(row.Configuration_Data or {})
    data["paused"] = paused
    row.Configuration_Data = data
    db.session.flush()

    verb = "Pausing" if paused else "Resuming"
    applied = apply_to_nagios(plugin_id, user_id, f"{verb} check '{row.Service_Description}' failed")
    if not paused:
        mark_applied(row)
    record_success(plugin, user_id, row.Nagios_Service_Name,
                   f"{'Paused' if paused else 'Resumed'} check '{row.Service_Description}'.")
    db.session.commit()
    return {**serialize_check(row, device, None, datetime.now(timezone.utc)), **applied}


def delete_custom_check(plugin_id, check_id, user_id):
    """
    Remove a check and its service. Returns {"id", "changed", "message"}. Raises PluginNotFoundError,
    CustomCheckNotFoundError, MonitoringChangeError.
    """
    plugin = get_plugin_or_raise(plugin_id)
    row = get_check(plugin_id, check_id)
    name, service_name, device_id = row.Service_Description, row.Nagios_Service_Name, row.NetDiscoveryID
    db.session.delete(row)
    db.session.flush()

    applied = apply_to_nagios(plugin_id, user_id, f"Removing check '{name}' failed")
    record_success(plugin, user_id, None, f"Removed check '{name}' ({service_name}) from device {device_id}.")
    db.session.commit()
    return {"id": check_id, **applied}
