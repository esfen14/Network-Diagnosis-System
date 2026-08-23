"""
Report routes for the Network Diagnosis System.

All routes accept a `period` query parameter:
    last_24h  - previous 24 hours from now
    today     - midnight-to-now of the current calendar day
    last_7d   - previous 7 days
    last_30d  - previous 30 days
    last_90d  - previous 90 days
    custom    - requires `start` and `end` (YYYY-MM-DD, both inclusive)

Uptime % is computed from polling snapshots stored in HostStatus / ServiceStatus:
    host uptime    % = (UP snapshots    / total snapshots) * 100
    service uptime % = (OK snapshots    / total snapshots) * 100

Routes that query Nagios CGI (alerts, notifications) return the raw Nagios
data shaped into a consistent envelope.

Routes
------
GET /report/availability
    Host availability report within the selected period. Computes uptime % per
    host from HostStatus snapshots and returns a summary of Up/Down/Unreachable
    counts alongside per-host details.

GET /report/hosts-by-os
    Host availability grouped by OS type. Works like /report/availability but
    adds an OS_Type dimension from NetworkDiscovery, with per-OS aggregate
    counts and per-host breakdowns.

GET /report/network-services
    Network-wide service health overview. Aggregates ServiceStatus snapshots
    per unique service name across all hosts, computing uptime % and current
    state for each (host, service) instance.

GET /report/device-services
    Per-device service health. Groups service snapshots by hostname, showing
    all monitored services per host with uptime % and current state.

GET /report/alerts
    Alert list and summary count fetched from Nagios archivejson.cgi.
    Optional hostname and service filters. Returns raw Nagios alert data.

GET /report/notifications
    Notification list and summary count fetched from Nagios archivejson.cgi.
    Optional hostname and service filters. Returns raw Nagios notification data.
"""

from collections import Counter
from datetime import datetime, timedelta

import sqlalchemy as sa
from flask import request, current_app
from flask_login import login_required

from app import db
from app.api.system import system_bp
from app.api.helper import get_range_custom, success, error
from app.api.helper.database_access.permissions import require_permission
from app.history_models import HostStatus, ServiceStatus, ServiceStateType
from app.system_models import NetworkDiscovery
from app.nagios.notifications import (
    request_alerts_range,
    request_alert_count_range,
    request_notifications_range,
    request_notification_count_range,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

VALID_PERIODS = {"last_24h", "today", "last_7d", "last_30d", "last_90d", "custom"}


def _resolve_period(period, start, end):
    """
    Translate a period name into (start_ts, end_ts, start_dt, end_dt).

    Raises ValueError with a human-readable message on bad input.
    """
    now = datetime.now()

    if period == "today":
        start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now

    elif period == "last_24h":
        end_dt = now
        start_dt = now - timedelta(hours=24)

    elif period == "last_7d":
        end_dt = now
        start_dt = now - timedelta(days=7)

    elif period == "last_30d":
        end_dt = now
        start_dt = now - timedelta(days=30)

    elif period == "last_90d":
        end_dt = now
        start_dt = now - timedelta(days=90)

    elif period == "custom":
        if not start or not end:
            raise ValueError(
                "'start' and 'end' are required when period=custom (format: YYYY-MM-DD)"
            )
        start_ts, end_ts = get_range_custom(start, end)
        start_dt = datetime.fromtimestamp(start_ts)
        end_dt = datetime.fromtimestamp(end_ts)
        return start_ts, end_ts, start_dt, end_dt

    else:
        raise ValueError(
            f"Invalid period '{period}'. "
            f"Valid values: {', '.join(sorted(VALID_PERIODS))}"
        )

    return int(start_dt.timestamp()), int(end_dt.timestamp()), start_dt, end_dt


def _period_params():
    """
    Extract and validate `period`, `start`, `end` from the request's query string.

    Returns:
        (start_ts, end_ts, start_dt, end_dt, None)  on success
        (None, None, None, None, (body, status))     on error
    """
    period = request.args.get("period", "last_24h").strip().lower()
    start = request.args.get("start") or None
    end = request.args.get("end") or None

    if period not in VALID_PERIODS:
        return None, None, None, None, (
            {
                "message": (
                    f"Invalid period. Valid values: "
                    f"{', '.join(sorted(VALID_PERIODS))}"
                )
            },
            400,
        )

    try:
        start_ts, end_ts, start_dt, end_dt = _resolve_period(period, start, end)
    except ValueError as exc:
        return None, None, None, None, ({"message": str(exc)}, 400)

    return start_ts, end_ts, start_dt, end_dt, None


def _period_meta(period, start_dt, end_dt):
    """Metadata block included in every report response."""
    return {
        "period": period,
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
    }


# ---------------------------------------------------------------------------
# 1. Host Availability
# ---------------------------------------------------------------------------

@system_bp.get('/report/availability')
@login_required
@require_permission("system.report")
def report_host_availability():
    """
    Host availability within the selected period.

    For each host, counts all HostStatus snapshots in the window and computes:
        uptime % = (UP snapshots / total snapshots) * 100

    The "current state" shown is taken from the most-recent snapshot.

    Response shape:
    {
        "period":  { "period": "...", "start": "...", "end": "..." },
        "summary": {
            "total": n, "up": n, "down": n, "unreachable": n,
            "uptime_pct": 99.5
        },
        "hosts": [
            {
                "hostname":          "...",
                "state":             "Up|Down|Unreachable",
                "uptime_pct":        99.5,
                "total_snapshots":   n,
                "last_check":        "ISO-8601 | null",
                "last_state_change": "ISO-8601 | null"
            },
            ...
        ]
    }
    """
    try:
        start_ts, end_ts, start_dt, end_dt, err = _period_params()
        if err:
            return err

        period = request.args.get("period", "last_24h").strip().lower()

        # All snapshots within the window (need every row for uptime %)
        all_snapshots = db.session.execute(
            sa.select(
                HostStatus.Hostname,
                HostStatus.Current_State,
                HostStatus.Last_Check,
                HostStatus.Last_State_Change,
            )
            .where(
                HostStatus.Timestamp >= start_dt,
                HostStatus.Timestamp <= end_dt,
            )
            .order_by(HostStatus.Hostname.asc(), HostStatus.Last_Check.asc())
        ).all()

        # Aggregate per-host stats
        host_stats: dict[str, dict] = {}

        for snap in all_snapshots:
            h = snap.Hostname
            if h not in host_stats:
                host_stats[h] = {
                    "total": 0,
                    "up": 0,
                    "last_check": None,
                    "last_state_change": None,
                    "state": None,
                }
            s = host_stats[h]
            s["total"] += 1
            if snap.Current_State.value == "Up":
                s["up"] += 1
            # The rows are ordered by Last_Check asc, so last iteration = most recent
            s["last_check"] = snap.Last_Check
            s["last_state_change"] = snap.Last_State_Change
            s["state"] = snap.Current_State.value

        hosts = []
        state_counts = Counter()
        total_up_snaps = 0
        total_snaps = 0

        for hostname, s in sorted(host_stats.items()):
            total = s["total"]
            up = s["up"]
            uptime_pct = round((up / total) * 100, 2) if total > 0 else None
            state = s["state"] or "Unknown"

            state_counts[state] += 1
            total_up_snaps += up
            total_snaps += total

            hosts.append({
                "hostname":          hostname,
                "state":             state,
                "uptime_pct":        uptime_pct,
                "total_snapshots":   total,
                "last_check":        s["last_check"].isoformat() if s["last_check"] else None,
                "last_state_change": (
                    s["last_state_change"].isoformat()
                    if s["last_state_change"] else None
                ),
            })

        overall_uptime = (
            round((total_up_snaps / total_snaps) * 100, 2)
            if total_snaps > 0 else None
        )

        return success({
            "period": _period_meta(period, start_dt, end_dt),
            "summary": {
                "total":       len(hosts),
                "up":          state_counts.get("Up", 0),
                "down":        state_counts.get("Down", 0),
                "unreachable": state_counts.get("Unreachable", 0),
                "uptime_pct":  overall_uptime,
            },
            "hosts": hosts,
        })

    except Exception:
        current_app.logger.exception(
            "Unexpected error in report_host_availability"
        )
        return error("An unexpected error occurred.", 500)


# ---------------------------------------------------------------------------
# 2. Hosts by OS
# ---------------------------------------------------------------------------

@system_bp.get('/report/hosts-by-os')
@login_required
@require_permission("system.report")
def report_hosts_by_os():
    """
    Host availability within the selected period, grouped by OS type.

    Works identically to /report/availability but adds the OS_Type dimension
    from NetworkDiscovery.  For each OS group the response includes:
      - a per-host breakdown (same as availability)
      - aggregate UP / DOWN / UNREACHABLE counts
      - an uptime percentage for the group

    Uptime % per group = (UP snapshots in group / total snapshots in group) * 100
    Hosts that have no HostStatus record in the window are listed separately
    under os_type "Unknown" if their OS is not set, or under their OS with
    state "No Data".

    Response shape:
    {
        "period": { ... },
        "summary": {
            "total_hosts": n,
            "up": n, "down": n, "unreachable": n,
            "uptime_pct": 99.5
        },
        "by_os": [
            {
                "os_type": "Windows",
                "total":        n,
                "up":           n,
                "down":         n,
                "unreachable":  n,
                "uptime_pct":   99.5,
                "hosts": [
                    {
                        "hostname":          "...",
                        "state":             "Up|Down|Unreachable|No Data",
                        "uptime_pct":        99.5,
                        "last_check":        "ISO-8601 | null",
                        "last_state_change": "ISO-8601 | null"
                    },
                    ...
                ]
            },
            ...
        ]
    }
    """
    try:
        start_ts, end_ts, start_dt, end_dt, err = _period_params()
        if err:
            return err

        period = request.args.get("period", "last_24h").strip().lower()

        # ── All snapshots for every host within the window ──────────────────
        # We need ALL rows (not just the latest) to compute uptime %.
        all_snapshots = db.session.execute(
            sa.select(
                HostStatus.Hostname,
                HostStatus.Current_State,
                HostStatus.Last_Check,
                HostStatus.Last_State_Change,
            )
            .where(
                HostStatus.Timestamp >= start_dt,
                HostStatus.Timestamp <= end_dt,
            )
        ).all()

        # ── OS type map: hostname -> os_type (from NetworkDiscovery) ─────────
        nd_rows = db.session.execute(
            sa.select(NetworkDiscovery.Hostname, NetworkDiscovery.OS_Type)
        ).all()

        os_map = {
            r.Hostname: (r.OS_Type or "Unknown")
            for r in nd_rows
            if r.Hostname
        }

        # ── Aggregate per-host stats from snapshots ──────────────────────────
        # hostname -> { total, up, last_check, last_state_change }
        host_stats: dict[str, dict] = {}

        for snap in all_snapshots:
            h = snap.Hostname
            if h not in host_stats:
                host_stats[h] = {
                    "total": 0,
                    "up": 0,
                    "last_check": snap.Last_Check,
                    "last_state_change": snap.Last_State_Change,
                }
            stats = host_stats[h]
            stats["total"] += 1
            if snap.Current_State.value == "Up":
                stats["up"] += 1
            # Keep the most-recent last_check / last_state_change
            if snap.Last_Check and (
                stats["last_check"] is None
                or snap.Last_Check > stats["last_check"]
            ):
                stats["last_check"] = snap.Last_Check
                stats["last_state_change"] = snap.Last_State_Change

        # ── Build per-OS groups ───────────────────────────────────────────────
        # Include every host that has data in the window.
        os_groups: dict[str, list] = {}

        for hostname, stats in sorted(host_stats.items()):
            os_type = os_map.get(hostname, "Unknown")
            total = stats["total"]
            up = stats["up"]
            uptime_pct = round((up / total) * 100, 2) if total > 0 else None

            # Determine "current" state from the last snapshot
            down = total - up
            if up == total:
                state = "Up"
            elif up == 0:
                state = "Down"
            else:
                state = "Down"   # majority-down; use last snapshot below

            os_groups.setdefault(os_type, []).append({
                "hostname":          hostname,
                "uptime_pct":        uptime_pct,
                "total_snapshots":   total,
                "last_check":        stats["last_check"].isoformat() if stats["last_check"] else None,
                "last_state_change": (
                    stats["last_state_change"].isoformat()
                    if stats["last_state_change"]
                    else None
                ),
            })

        # Re-compute last snapshot state per host for the state column
        # (use a separate pass with the most-recent snapshot per host)
        latest_state: dict[str, str] = {}
        for snap in all_snapshots:
            h = snap.Hostname
            if h not in latest_state:
                latest_state[h] = snap.Current_State.value
            # all_snapshots is unordered; we already tracked last_check above
            # so overwrite with the row whose Last_Check is most recent
            if snap.Last_Check and host_stats[h]["last_check"] == snap.Last_Check:
                latest_state[h] = snap.Current_State.value

        # Inject state back into host entries
        for hosts_list in os_groups.values():
            for entry in hosts_list:
                entry["state"] = latest_state.get(entry["hostname"], "Unknown")

        # ── Build response structure ──────────────────────────────────────────
        by_os = []
        global_up = global_total = 0

        for os_type, hosts_list in sorted(os_groups.items()):
            grp_total_snaps = sum(h["total_snapshots"] for h in hosts_list)
            grp_up_snaps    = sum(
                round((h["uptime_pct"] / 100) * h["total_snapshots"])
                if h["uptime_pct"] is not None else 0
                for h in hosts_list
            )
            grp_uptime = (
                round((grp_up_snaps / grp_total_snaps) * 100, 2)
                if grp_total_snaps > 0 else None
            )

            state_counter = Counter(h["state"] for h in hosts_list)

            global_up    += state_counter.get("Up", 0)
            global_total += len(hosts_list)

            by_os.append({
                "os_type":    os_type,
                "total":      len(hosts_list),
                "up":         state_counter.get("Up", 0),
                "down":       state_counter.get("Down", 0),
                "unreachable": state_counter.get("Unreachable", 0),
                "uptime_pct": grp_uptime,
                "hosts":      hosts_list,
            })

        global_uptime = (
            round((global_up / global_total) * 100, 2)
            if global_total > 0 else None
        )
        global_state_counts = Counter(
            entry["state"]
            for grp in by_os
            for entry in grp["hosts"]
        )

        return success({
            "period": _period_meta(period, start_dt, end_dt),
            "summary": {
                "total_hosts": global_total,
                "up":          global_state_counts.get("Up", 0),
                "down":        global_state_counts.get("Down", 0),
                "unreachable": global_state_counts.get("Unreachable", 0),
                "uptime_pct":  global_uptime,
            },
            "by_os": by_os,
        })

    except Exception:
        current_app.logger.exception(
            "Unexpected error in report_hosts_by_os"
        )
        return error("An unexpected error occurred.", 500)


# ---------------------------------------------------------------------------
# 3. Network Services Overview
# ---------------------------------------------------------------------------

@system_bp.get('/report/network-services')
@login_required
@require_permission("system.report")
def report_network_services():
    """
    Network-wide service health overview within the selected period.

    For each unique service name monitored across all hosts, aggregates all
    ServiceStatus snapshots in the window and computes:
        uptime % = (OK snapshots / total snapshots) * 100

    "OK" is the healthy state for services (equivalent to "Up" for hosts).
    The "current state" shown is taken from the most-recent snapshot for
    each (hostname, service) pair.

    Response shape:
    {
        "period": { ... },
        "summary": {
            "total_services":  n,    # unique service names
            "total_instances": n,    # total (host, service) pairs
            "ok":              n,    # instances currently OK
            "warning":         n,
            "critical":        n,
            "unknown":         n,
            "uptime_pct":      99.5  # across all instances
        },
        "services": [
            {
                "service":         "PING",
                "total_instances": n,
                "ok":              n,
                "warning":         n,
                "critical":        n,
                "unknown":         n,
                "uptime_pct":      99.5,
                "instances": [
                    {
                        "hostname":          "...",
                        "state":             "Ok|Warning|Critical|Unknown",
                        "uptime_pct":        99.5,
                        "total_snapshots":   n,
                        "last_check":        "ISO-8601 | null",
                        "last_state_change": "ISO-8601 | null",
                        "plugin_output":     "..."
                    },
                    ...
                ]
            },
            ...
        ]
    }
    """
    try:
        start_ts, end_ts, start_dt, end_dt, err = _period_params()
        if err:
            return err

        period = request.args.get("period", "last_24h").strip().lower()

        # All service snapshots within the window
        all_snapshots = db.session.execute(
            sa.select(
                ServiceStatus.Hostname,
                ServiceStatus.Service,
                ServiceStatus.Current_State,
                ServiceStatus.Last_Check,
                ServiceStatus.Last_State_Change,
                ServiceStatus.Plugin_Output,
            )
            .where(
                ServiceStatus.Timestamp >= start_dt,
                ServiceStatus.Timestamp <= end_dt,
            )
            .order_by(
                ServiceStatus.Service.asc(),
                ServiceStatus.Hostname.asc(),
                ServiceStatus.Last_Check.asc(),
            )
        ).all()

        # Aggregate per (service, hostname)
        # key: (service, hostname) -> stats dict
        instance_stats: dict[tuple, dict] = {}

        for snap in all_snapshots:
            key = (snap.Service, snap.Hostname)
            if key not in instance_stats:
                instance_stats[key] = {
                    "total": 0,
                    "ok": 0,
                    "last_check": None,
                    "last_state_change": None,
                    "state": None,
                    "plugin_output": None,
                }
            s = instance_stats[key]
            s["total"] += 1
            if snap.Current_State == ServiceStateType.OK:
                s["ok"] += 1
            # Rows ordered by Last_Check asc → last iteration is most recent
            s["last_check"] = snap.Last_Check
            s["last_state_change"] = snap.Last_State_Change
            s["state"] = snap.Current_State.value
            s["plugin_output"] = snap.Plugin_Output

        # Group instances by service name
        service_groups: dict[str, list] = {}

        for (service_name, hostname), s in sorted(instance_stats.items()):
            total = s["total"]
            ok = s["ok"]
            uptime_pct = round((ok / total) * 100, 2) if total > 0 else None

            service_groups.setdefault(service_name, []).append({
                "hostname":          hostname,
                "state":             s["state"] or "Unknown",
                "uptime_pct":        uptime_pct,
                "total_snapshots":   total,
                "last_check":        s["last_check"].isoformat() if s["last_check"] else None,
                "last_state_change": (
                    s["last_state_change"].isoformat()
                    if s["last_state_change"] else None
                ),
                "plugin_output":     s["plugin_output"],
            })

        # Build per-service summary rows
        services = []
        global_state_counts = Counter()
        global_ok_snaps = 0
        global_total_snaps = 0

        for service_name, instances in sorted(service_groups.items()):
            svc_total_snaps = sum(i["total_snapshots"] for i in instances)
            svc_ok_snaps    = sum(
                round((i["uptime_pct"] / 100) * i["total_snapshots"])
                if i["uptime_pct"] is not None else 0
                for i in instances
            )
            svc_uptime = (
                round((svc_ok_snaps / svc_total_snaps) * 100, 2)
                if svc_total_snaps > 0 else None
            )

            state_counter = Counter(i["state"] for i in instances)
            global_state_counts.update(state_counter)
            global_ok_snaps    += svc_ok_snaps
            global_total_snaps += svc_total_snaps

            services.append({
                "service":         service_name,
                "total_instances": len(instances),
                "ok":              state_counter.get("Ok", 0),
                "warning":         state_counter.get("Warning", 0),
                "critical":        state_counter.get("Critical", 0),
                "unknown":         state_counter.get("Unknown", 0),
                "uptime_pct":      svc_uptime,
                "instances":       instances,
            })

        total_instances = sum(s["total_instances"] for s in services)
        overall_uptime = (
            round((global_ok_snaps / global_total_snaps) * 100, 2)
            if global_total_snaps > 0 else None
        )

        return success({
            "period": _period_meta(period, start_dt, end_dt),
            "summary": {
                "total_services":  len(services),
                "total_instances": total_instances,
                "ok":              global_state_counts.get("Ok", 0),
                "warning":         global_state_counts.get("Warning", 0),
                "critical":        global_state_counts.get("Critical", 0),
                "unknown":         global_state_counts.get("Unknown", 0),
                "uptime_pct":      overall_uptime,
            },
            "services": services,
        })

    except Exception:
        current_app.logger.exception(
            "Unexpected error in report_network_services"
        )
        return error("An unexpected error occurred.", 500)


# ---------------------------------------------------------------------------
# 4. Services per Device
# ---------------------------------------------------------------------------

@system_bp.get('/report/device-services')
@login_required
@require_permission("system.report")
def report_device_services():
    """
    Per-device service health within the selected period.

    For each (hostname, service) pair, counts all snapshots in the window and
    computes uptime % = (OK snapshots / total snapshots) * 100.
    Results are grouped by hostname.

    Response shape:
    {
        "period": { ... },
        "total_hosts":    n,
        "total_services": n,
        "hosts": [
            {
                "hostname":   "...",
                "uptime_pct": 99.5,   # host-level: across all its services
                "services": [
                    {
                        "service":           "...",
                        "state":             "Ok|Warning|Critical|Unknown",
                        "uptime_pct":        99.5,
                        "total_snapshots":   n,
                        "last_check":        "ISO-8601 | null",
                        "last_state_change": "ISO-8601 | null",
                        "plugin_output":     "..."
                    },
                    ...
                ]
            },
            ...
        ]
    }
    """
    try:
        start_ts, end_ts, start_dt, end_dt, err = _period_params()
        if err:
            return err

        period = request.args.get("period", "last_24h").strip().lower()

        # All service snapshots within the window, ordered so last row per
        # (hostname, service) is the most-recent one.
        all_snapshots = db.session.execute(
            sa.select(
                ServiceStatus.Hostname,
                ServiceStatus.Service,
                ServiceStatus.Current_State,
                ServiceStatus.Last_Check,
                ServiceStatus.Last_State_Change,
                ServiceStatus.Plugin_Output,
            )
            .where(
                ServiceStatus.Timestamp >= start_dt,
                ServiceStatus.Timestamp <= end_dt,
            )
            .order_by(
                ServiceStatus.Hostname.asc(),
                ServiceStatus.Service.asc(),
                ServiceStatus.Last_Check.asc(),
            )
        ).all()

        # Aggregate per (hostname, service)
        instance_stats: dict[tuple, dict] = {}

        for snap in all_snapshots:
            key = (snap.Hostname, snap.Service)
            if key not in instance_stats:
                instance_stats[key] = {
                    "total": 0, "ok": 0,
                    "last_check": None, "last_state_change": None,
                    "state": None, "plugin_output": None,
                }
            s = instance_stats[key]
            s["total"] += 1
            if snap.Current_State == ServiceStateType.OK:
                s["ok"] += 1
            s["last_check"] = snap.Last_Check
            s["last_state_change"] = snap.Last_State_Change
            s["state"] = snap.Current_State.value
            s["plugin_output"] = snap.Plugin_Output

        # Group by hostname
        grouped: dict[str, list] = {}

        for (hostname, service_name), s in sorted(instance_stats.items()):
            total = s["total"]
            ok = s["ok"]
            uptime_pct = round((ok / total) * 100, 2) if total > 0 else None

            grouped.setdefault(hostname, []).append({
                "service":           service_name,
                "state":             s["state"] or "Unknown",
                "uptime_pct":        uptime_pct,
                "total_snapshots":   total,
                "last_check":        s["last_check"].isoformat() if s["last_check"] else None,
                "last_state_change": (
                    s["last_state_change"].isoformat()
                    if s["last_state_change"] else None
                ),
                "plugin_output":     s["plugin_output"],
            })

        hosts = []
        for hostname, services in sorted(grouped.items()):
            # Host-level uptime: average across all its service snapshots
            host_total = sum(svc["total_snapshots"] for svc in services)
            host_ok = sum(
                round((svc["uptime_pct"] / 100) * svc["total_snapshots"])
                if svc["uptime_pct"] is not None else 0
                for svc in services
            )
            host_uptime = (
                round((host_ok / host_total) * 100, 2)
                if host_total > 0 else None
            )
            hosts.append({
                "hostname":   hostname,
                "uptime_pct": host_uptime,
                "services":   services,
            })

        return success({
            "period": _period_meta(period, start_dt, end_dt),
            "total_hosts":    len(hosts),
            "total_services": sum(len(h["services"]) for h in hosts),
            "hosts": hosts,
        })

    except Exception:
        current_app.logger.exception(
            "Unexpected error in report_device_services"
        )
        return error("An unexpected error occurred.", 500)


# ---------------------------------------------------------------------------
# 5. Alerts  (Nagios CGI)
# ---------------------------------------------------------------------------

@system_bp.get('/report/alerts')
@login_required
@require_permission("system.report")
def report_alerts():
    """
    Alert list and summary count from Nagios archivejson.cgi.

    Optional filters:
        hostname  - limit to a specific monitored host
        service   - limit to a specific service on that host

    Response shape:
    {
        "period": { ... },
        "count":  { ... },   # raw Nagios alertcount object  (null on Nagios error)
        "alerts": [ ... ]    # raw Nagios alertlist array    (null on Nagios error)
    }
    """
    try:
        start_ts, end_ts, start_dt, end_dt, err = _period_params()
        if err:
            return err

        period   = request.args.get("period", "last_24h").strip().lower()
        hostname = request.args.get("hostname") or None
        service  = request.args.get("service")  or None

        alerts = request_alerts_range(start_ts, end_ts, hostname=hostname, service=service)
        count  = request_alert_count_range(start_ts, end_ts, hostname=hostname, service=service)

        if alerts is None and count is None:
            return error(
                "Failed to retrieve alert data from Nagios. "
                "Check server logs for details.",
                502,
            )

        return success({
            "period": _period_meta(period, start_dt, end_dt),
            "count":  count,
            "alerts": alerts,
        })

    except Exception:
        current_app.logger.exception("Unexpected error in report_alerts")
        return error("An unexpected error occurred.", 500)


# ---------------------------------------------------------------------------
# 6. Notifications  (Nagios CGI)
# ---------------------------------------------------------------------------

@system_bp.get('/report/notifications')
@login_required
@require_permission("system.report")
def report_notifications():
    """
    Notification list and summary count from Nagios archivejson.cgi.

    Optional filters:
        hostname  - limit to a specific monitored host
        service   - limit to a specific service on that host

    Response shape:
    {
        "period": { ... },
        "count":         { ... },   # raw Nagios notificationcount object  (null on Nagios error)
        "notifications": [ ... ]    # raw Nagios notificationlist array    (null on Nagios error)
    }
    """
    try:
        start_ts, end_ts, start_dt, end_dt, err = _period_params()
        if err:
            return err

        period   = request.args.get("period", "last_24h").strip().lower()
        hostname = request.args.get("hostname") or None
        service  = request.args.get("service")  or None

        notifications = request_notifications_range(
            start_ts, end_ts, hostname=hostname, service=service
        )
        count = request_notification_count_range(
            start_ts, end_ts, hostname=hostname, service=service
        )

        if notifications is None and count is None:
            return error(
                "Failed to retrieve notification data from Nagios. "
                "Check server logs for details.",
                502,
            )

        return success({
            "period": _period_meta(period, start_dt, end_dt),
            "count":         count,
            "notifications": notifications,
        })

    except Exception:
        current_app.logger.exception("Unexpected error in report_notifications")
        return error("An unexpected error occurred.", 500)
