"""
network_health_activity.py — Network Health page cards beyond the §2 summary
and trends: host availability, system activity, per-host CPU utilization,
active connections, and generated insights.

Where the data comes from:
  - Host availability is a "what happened between two dates" question, so it
    comes from Nagios archivejson.cgi (query=availability), not from the
    history.db snapshots — see AGENTS.md §8.
  - System activity, CPU utilization and insights describe the current state,
    so they read the latest history.db snapshots via statistics.py.
  - Active connections are counted live from the kernel's TCP table
    (/proc/net/tcp) on the Pinpoint server, which is also the Nagios server.
    No Nagios plugin in this system collects connection counts.

All routes require login and the "system.network_health" permission.

Routes
------
GET  /system/network-health/availability
    Network-wide host availability per day for the last N days.

GET  /system/network-health/system-activity
    Process and logged-in user counts from check_procs / check_users.

GET  /system/network-health/cpu
    CPU utilization trend for one host with an NCPA CPU check.

GET  /system/network-health/connections
    TCP connection counts on the Nagios/Pinpoint server.

GET  /system/network-health/insights
    Short plain-language observations about the current network state.

GET  /system/network-health/plugin-trends
    One entry per plugin added through the Plugin Manager: state counts,
    current values, and averaged trends for time / percentage metrics.
"""

from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import sqlalchemy as sa
from flask import request, current_app
from flask_login import login_required

from app import db
from app.api.helper.database_access.permissions import require_permission
from app.api.helper.responses import success, error
from app.api.system import system_bp
from app.api.system.network_health import utc_isoformat
from app.api.system.statistics import (
    VALID_TREND_HOURS,
    trend_hours,
    get_latest_hosts,
    get_latest_services,
    avg_ping_metrics,
    ncpa_averages,
    perf_trends,
    NAGIOS_HOST,
    PING_PLUGINS,
    DISCOVERY_COMMAND_PREFIX,
    PLUGIN_MANAGER_COMMAND_PREFIX,
    LOAD_PLUGIN,
    SWAP_PLUGIN,
    DISK_PLUGIN,
    _plugin_key,
)
from app.network_discovery.plugin_registry import normalize_plugin_name
from app.network_discovery.port_lifecycle import ENABLED_PLUGIN_STATES
from app.history_models import (
    HostStateType,
    ServicePerfData,
    ServiceStateType,
    ServiceStatus,
)
from app.nagios.notifications import request_host_availability_range
from app.plugin_models import Plugin

# Valid trend windows (hours) — same presets as /network-health/trends.
VALID_HOURS = VALID_TREND_HOURS

# Longest availability window, in days. Each day is one archivejson call.
MAX_AVAILABILITY_DAYS = 30

# Insight thresholds.
HIGH_LATENCY_MS = 100
HIGH_PACKET_LOSS_PCT = 5
HIGH_RESOURCE_PCT = 80

# /proc/net/tcp "st" column values (hex) → connection state.
TCP_ESTABLISHED = "01"
TCP_TIME_WAIT = "06"
TCP_LISTEN = "0A"
PROC_TCP_FILES = (Path("/proc/net/tcp"), Path("/proc/net/tcp6"))

STATE_LABELS = {
    ServiceStateType.OK: "ok",
    ServiceStateType.WARNING: "warning",
    ServiceStateType.CRITICAL: "critical",
    ServiceStateType.UNKNOWN: "unknown",
}
STATE_SEVERITY = {"ok": 0, "unknown": 1, "warning": 2, "critical": 3}

# Perf-data units that can be averaged across hosts: durations and
# percentages mean the same thing on every host. Sizes and counts (disk
# MiB, processes) depend on the machine, so those are reported per host.
AVERAGEABLE_UNITS = {"s", "ms", "us", "%"}


# ==========================================================
# HELPERS
# ==========================================================

def availability_pct(host_rows):
    """
    Percentage of known time that hosts were UP, summed across every host in
    an archivejson availability result. Time Nagios has no data for
    (time_indeterminate_*) is left out. Returns None if no time is known.
    """
    up = down = unreachable = 0
    for row in host_rows:
        up += row.get("time_up", 0) or 0
        down += row.get("time_down", 0) or 0
        unreachable += row.get("time_unreachable", 0) or 0

    known = up + down + unreachable
    if known == 0:
        return None
    return round(up / known * 100, 2)


def latest_perf_by_service(services, metric):
    """
    Map each ServiceStatus row's ID to the value of the named perf metric in
    that snapshot. Services without the metric are left out.
    """
    if not services:
        return {}

    rows = db.session.execute(
        sa.select(ServicePerfData.ServiceStatusID, ServicePerfData.Measured_Value)
        .where(
            ServicePerfData.ServiceStatusID.in_([s.ServiceStatusID for s in services]),
            ServicePerfData.Metric == metric,
        )
    ).all()
    return {row.ServiceStatusID: row.Measured_Value for row in rows}


def per_host_max(services, values_by_id):
    """
    Highest value per hostname. A host can run several check_procs services
    (e.g. total and zombie processes); the largest one is the total count.
    """
    by_host = {}
    for service in services:
        value = values_by_id.get(service.ServiceStatusID)
        if value is None:
            continue
        by_host[service.Hostname] = max(value, by_host.get(service.Hostname, value))
    return by_host


def worst_state(services):
    """Worst state label ("ok" / "unknown" / "warning" / "critical") among services, or None."""
    labels = [STATE_LABELS.get(s.Current_State, "unknown") for s in services]
    if not labels:
        return None
    return max(labels, key=lambda label: STATE_SEVERITY[label])


def cpu_services(latest_services):
    """
    The NCPA CPU service per hostname — a check_ncpa service whose name
    mentions "cpu" (e.g. "ncpa-cpu-5693", generated from NCPA_METRICS).
    """
    by_host = {}
    for service in latest_services:
        if _plugin_key(service.Service, service.Check_Command) != "check_ncpa":
            continue
        if "cpu" not in service.Service.lower():
            continue
        by_host.setdefault(service.Hostname, service)
    return by_host


def count_tcp_connections():
    """
    Count TCP sockets on this machine by state, from /proc/net/tcp and
    /proc/net/tcp6. Returns None where /proc is not available (e.g. a
    developer's macOS machine).
    """
    files = [path for path in PROC_TCP_FILES if path.exists()]
    if not files:
        return None

    counts = {"established": 0, "listening": 0, "time_wait": 0, "other": 0}
    for path in files:
        lines = path.read_text().splitlines()[1:]  # first line is the header
        for line in lines:
            fields = line.split()
            if len(fields) < 4:
                continue
            state = fields[3].upper()
            if state == TCP_ESTABLISHED:
                counts["established"] += 1
            elif state == TCP_LISTEN:
                counts["listening"] += 1
            elif state == TCP_TIME_WAIT:
                counts["time_wait"] += 1
            else:
                counts["other"] += 1
    counts["total"] = sum(counts.values())
    return counts


def latest_change(rows):
    """Most recent Last_State_Change among host/service rows, as ISO-8601 (or None)."""
    times = [r.Last_State_Change for r in rows if r.Last_State_Change is not None]
    return utc_isoformat(max(times)) if times else None


# Plugins that already have their own Network Health widgets (ping/latency,
# NCPA resources and the Nagios server's local load, swap and disk checks).
DEDICATED_WIDGET_PLUGINS = PING_PLUGINS | {"check_ncpa", LOAD_PLUGIN, SWAP_PLUGIN, DISK_PLUGIN}


def added_plugin_name(service, enabled_plugins):
    """
    The Plugin Manager plugin a service gets a widget for, or None.

    A service belongs to a plugin through its Nagios command (see
    statistics._plugin_key): Network Discovery's "pinpoint_nd_<plugin>" and
    the older Plugin Manager "pinpoint_<plugin>" both resolve to the plugin.
    It gets a widget when that plugin is enabled in Plugin Manager
    (enabled_plugins holds normalized names) and does not already have a
    dedicated widget. Checks of plugins that are not enabled, such as stock
    Nagios commands, are left out; they appear in the plugin state summary.
    """
    command = (service.Check_Command or "").split("!")[0].strip()
    key = normalize_plugin_name(_plugin_key(service.Service, service.Check_Command))
    if key in DEDICATED_WIDGET_PLUGINS:
        return None
    is_manual = command.startswith(PLUGIN_MANAGER_COMMAND_PREFIX) and not command.startswith(DISCOVERY_COMMAND_PREFIX)
    return key if is_manual or key in enabled_plugins else None


def bucketed_average(pairs, metric, unit, hours, buckets):
    """
    Average of one perf metric across the given (hostname, service) pairs,
    split into `buckets` equal time buckets over the last `hours` hours.
    Buckets without data have avg_value None.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours)
    bucket_seconds = hours * 3600 / buckets

    rows = db.session.execute(
        sa.select(ServiceStatus.Timestamp, ServicePerfData.Measured_Value)
        .join(ServicePerfData, ServicePerfData.ServiceStatusID == ServiceStatus.ServiceStatusID)
        .where(
            ServiceStatus.Timestamp >= start,
            ServicePerfData.Metric == metric,
            sa.tuple_(ServiceStatus.Hostname, ServiceStatus.Service).in_(pairs),
        )
    ).all()

    values = defaultdict(list)
    for row in rows:
        ts = row.Timestamp if row.Timestamp.tzinfo else row.Timestamp.replace(tzinfo=timezone.utc)
        index = min(int((ts - start).total_seconds() / bucket_seconds), buckets - 1)
        values[index].append(row.Measured_Value)

    points = []
    for i in range(buckets):
        bucket = values.get(i)
        points.append({
            "bucket_start": (start + timedelta(seconds=bucket_seconds * i)).isoformat(),
            "avg_value": round(sum(bucket) / len(bucket), 4) if bucket else None,
            "unit": unit,
        })
    return points


def plural(count, word):
    """ "1 device" / "3 devices". """
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


# ==========================================================
# HOST AVAILABILITY
# ==========================================================

@system_bp.get("/network-health/availability")
@login_required
@require_permission("system.network_health")
def network_health_availability():
    """
    Network-wide host availability — the share of time hosts were UP — for
    each of the last N days (rolling 24-hour windows ending now), read from
    Nagios archivejson.cgi. Time Nagios has no data for is not counted.

    Query params:
        days — number of days, 1 to 30 (default 7)

    Response shape:
    {
        "days": int,
        "availability_pct": float | null,    // across the whole window
        "change_pct": float | null,          // latest day minus the day before, in points
        "trend_pct": float | null,           // latest day minus the first day with data, in points
        "daily": [ { "start": iso, "end": iso, "availability_pct": float | null } ]
    }

    Returns 502 if Nagios cannot be reached.
    """
    raw_days = request.args.get("days", "7")
    if not raw_days.isdigit() or not 1 <= int(raw_days) <= MAX_AVAILABILITY_DAYS:
        return error(f"days must be between 1 and {MAX_AVAILABILITY_DAYS}.", 400)
    days = int(raw_days)

    try:
        now = int(datetime.now(timezone.utc).timestamp())
        all_rows = []
        daily = []
        for i in range(days):
            start = now - (days - i) * 86400
            end = start + 86400
            host_rows = request_host_availability_range(start, end)
            if host_rows is None:
                return error("Unable to read availability from Nagios.", 502)

            all_rows.extend(host_rows)
            daily.append({
                "start": datetime.fromtimestamp(start, timezone.utc).isoformat(),
                "end": datetime.fromtimestamp(end, timezone.utc).isoformat(),
                "availability_pct": availability_pct(host_rows),
            })

        known = [d["availability_pct"] for d in daily if d["availability_pct"] is not None]
        change = None
        if len(daily) >= 2 and daily[-1]["availability_pct"] is not None and daily[-2]["availability_pct"] is not None:
            change = round(daily[-1]["availability_pct"] - daily[-2]["availability_pct"], 2)
        trend = round(known[-1] - known[0], 2) if len(known) >= 2 else None

        return success({
            "days": days,
            "availability_pct": availability_pct(all_rows),
            "change_pct": change,
            "trend_pct": trend,
            "daily": daily,
        })

    except Exception:
        current_app.logger.exception("Unexpected error in GET /system/network-health/availability")
        return error("An unexpected error occurred.", 500)


# ==========================================================
# SYSTEM ACTIVITY
# ==========================================================

@system_bp.get("/network-health/system-activity")
@login_required
@require_permission("system.network_health")
def network_health_system_activity():
    """
    Process and logged-in user counts across monitored devices, from the
    latest check_procs ("procs" perf metric) and check_users ("users" perf
    metric) results. The stock Nagios localhost config runs both. A section
    is null when no device runs that check.

    Response shape:
    {
        "processes": null | {
            "device_count": int,
            "total": int,
            "avg_per_device": float,
            "state": "ok" | "warning" | "critical" | "unknown",
            "peak_24h": { "hostname": str, "count": int } | null
        },
        "users": null | {
            "device_count": int,
            "total": int,
            "min_per_device": int,
            "max_per_device": int,
            "change_1h": int | null     // total now minus total an hour ago
        }
    }
    """
    try:
        latest = get_latest_services()

        # ── Processes ────────────────────────────────────────────────────────
        procs_svcs = [s for s in latest if _plugin_key(s.Service, s.Check_Command) == "check_procs"]
        procs_by_host = per_host_max(procs_svcs, latest_perf_by_service(procs_svcs, "procs"))

        processes = None
        if procs_by_host:
            since = datetime.now(timezone.utc) - timedelta(hours=24)
            peak_row = db.session.execute(
                sa.select(ServiceStatus.Hostname, ServicePerfData.Measured_Value)
                .join(ServicePerfData, ServicePerfData.ServiceStatusID == ServiceStatus.ServiceStatusID)
                .where(
                    ServiceStatus.Timestamp >= since,
                    ServicePerfData.Metric == "procs",
                    sa.tuple_(ServiceStatus.Hostname, ServiceStatus.Service).in_(
                        [(s.Hostname, s.Service) for s in procs_svcs]
                    ),
                )
                .order_by(ServicePerfData.Measured_Value.desc())
                .limit(1)
            ).first()

            total = sum(procs_by_host.values())
            processes = {
                "device_count": len(procs_by_host),
                "total": int(total),
                "avg_per_device": round(total / len(procs_by_host), 1),
                "state": worst_state(procs_svcs),
                "peak_24h": (
                    {"hostname": peak_row.Hostname, "count": int(peak_row.Measured_Value)}
                    if peak_row else None
                ),
            }

        # ── Users ────────────────────────────────────────────────────────────
        users_svcs = [s for s in latest if _plugin_key(s.Service, s.Check_Command) == "check_users"]
        users_now = latest_perf_by_service(users_svcs, "users")
        users_by_host = per_host_max(users_svcs, users_now)

        users = None
        if users_by_host:
            # Compare with each service's last snapshot from an hour or more ago.
            hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
            before_total = 0
            now_total = 0
            compared = 0
            for service in users_svcs:
                if service.ServiceStatusID not in users_now:
                    continue
                before = db.session.execute(
                    sa.select(ServicePerfData.Measured_Value)
                    .join(ServiceStatus, ServicePerfData.ServiceStatusID == ServiceStatus.ServiceStatusID)
                    .where(
                        ServiceStatus.Hostname == service.Hostname,
                        ServiceStatus.Service == service.Service,
                        ServiceStatus.Timestamp <= hour_ago,
                        ServicePerfData.Metric == "users",
                    )
                    .order_by(ServiceStatus.Timestamp.desc())
                    .limit(1)
                ).scalar()
                if before is None:
                    continue
                before_total += before
                now_total += users_now[service.ServiceStatusID]
                compared += 1

            users = {
                "device_count": len(users_by_host),
                "total": int(sum(users_by_host.values())),
                "min_per_device": int(min(users_by_host.values())),
                "max_per_device": int(max(users_by_host.values())),
                "change_1h": int(now_total - before_total) if compared else None,
            }

        return success({"processes": processes, "users": users})

    except Exception:
        current_app.logger.exception("Unexpected error in GET /system/network-health/system-activity")
        return error("An unexpected error occurred.", 500)


# ==========================================================
# CPU UTILIZATION
# ==========================================================

@system_bp.get("/network-health/cpu")
@login_required
@require_permission("system.network_health")
def network_health_cpu():
    """
    CPU utilization (%) over time for one host, from its NCPA CPU check
    (cpu/percent). Only hosts with that check can be picked. Without a
    hostname, the Nagios server (localhost) is used when it has one,
    otherwise the first host alphabetically.

    NCPA reports overall utilization only — there is no idle / system /
    user / wait breakdown to show.

    Query params:
        hostname — host to show (optional)
        hours    — 5/60 (5 minutes), 1, 6, 24 (default) or 168
        buckets  — number of points, 1 to 168 (default 24)

    Response shape:
    {
        "hosts": [str],             // hosts with an NCPA CPU check
        "hostname": str | null,     // null when no host has one
        "service": str | null,
        "hours": int,
        "current_pct": float | null,
        "avg_pct": float | null,
        "max_pct": float | null,
        "points": [ { "bucket_start": iso, "avg_value": float | null, "unit": str | null } ]
    }
    """
    hours = request.args.get("hours", default=24, type=trend_hours)
    buckets = request.args.get("buckets", default=24, type=int)
    hostname = request.args.get("hostname")

    if hours not in VALID_HOURS:
        return error(f"hours must be one of: {sorted(VALID_HOURS)}.", 400)
    if buckets is None or not 1 <= buckets <= 168:
        return error("buckets must be between 1 and 168.", 400)

    try:
        services_by_host = cpu_services(get_latest_services())
        hosts = sorted(services_by_host)

        if hostname and hostname not in services_by_host:
            return error("That host has no NCPA CPU check.", 404)
        if not hostname and hosts:
            hostname = NAGIOS_HOST if NAGIOS_HOST in services_by_host else hosts[0]

        empty = {
            "hosts": hosts, "hostname": hostname, "service": None, "hours": hours,
            "current_pct": None, "avg_pct": None, "max_pct": None, "points": [],
        }
        if not hostname:
            return success(empty)

        service = services_by_host[hostname]
        latest_metrics = db.session.execute(
            sa.select(ServicePerfData.Metric, ServicePerfData.Measured_Value)
            .where(ServicePerfData.ServiceStatusID == service.ServiceStatusID)
        ).all()
        if not latest_metrics:
            return success({**empty, "service": service.Service})

        # check_ncpa names the metric after the last path segment ("percent");
        # prefer a percent metric if the check reports several.
        metric = next((m for m in latest_metrics if "percent" in m.Metric.lower()), latest_metrics[0])

        points = []
        for row in perf_trends(hostname, service.Service, [metric.Metric], hours, buckets):
            points.append({
                "bucket_start": row["bucket_start"],
                "avg_value": row["avg_value"],
                "unit": row["unit"],
            })

        values = [p["avg_value"] for p in points if p["avg_value"] is not None]
        return success({
            **empty,
            "service": service.Service,
            "current_pct": round(metric.Measured_Value, 2),
            "avg_pct": round(sum(values) / len(values), 2) if values else None,
            "max_pct": round(max(values), 2) if values else None,
            "points": points,
        })

    except Exception:
        current_app.logger.exception("Unexpected error in GET /system/network-health/cpu")
        return error("An unexpected error occurred.", 500)


# ==========================================================
# ACTIVE CONNECTIONS
# ==========================================================

@system_bp.get("/network-health/connections")
@login_required
@require_permission("system.network_health")
def network_health_connections():
    """
    TCP connections open on the Nagios/Pinpoint server right now, by state,
    read from /proc/net/tcp and /proc/net/tcp6. "available" is false when
    the server has no /proc (not Linux); the counts are then null.

    Response shape:
    {
        "available": bool,
        "hostname": "localhost",
        "established": int | null,
        "listening": int | null,
        "time_wait": int | null,
        "other": int | null,
        "total": int | null
    }
    """
    try:
        counts = count_tcp_connections()
        if counts is None:
            return success({
                "available": False, "hostname": NAGIOS_HOST, "established": None,
                "listening": None, "time_wait": None, "other": None, "total": None,
            })
        return success({"available": True, "hostname": NAGIOS_HOST, **counts})

    except Exception:
        current_app.logger.exception("Unexpected error in GET /system/network-health/connections")
        return error("An unexpected error occurred.", 500)


# ==========================================================
# INSIGHTS
# ==========================================================

@system_bp.get("/network-health/insights")
@login_required
@require_permission("system.network_health")
def network_health_insights():
    """
    Short plain-language observations generated from the latest snapshot:
    devices down, services in a problem state, flapping, high average
    latency / packet loss, and high NCPA resource averages. When nothing
    needs attention, a single "stable" insight is returned. Sorted most
    severe first, then newest first.

    Each insight's "at" is when it became true where that is known (the
    latest state change involved), otherwise the snapshot time.

    Response shape:
    {
        "insights": [
            { "severity": "critical" | "warning" | "info" | "ok", "message": str, "at": iso | null }
        ]
    }
    """
    try:
        hosts = get_latest_hosts()
        services = get_latest_services()
        insights = []

        if not hosts:
            return success({"insights": [{
                "severity": "info",
                "message": "No devices are being monitored yet.",
                "at": None,
            }]})

        snapshot_at = utc_isoformat(max(h.Timestamp for h in hosts))

        # ── Host and service states ──────────────────────────────────────────
        down = [h for h in hosts if h.Current_State in (HostStateType.DOWN, HostStateType.UNREACHABLE)]
        if down:
            insights.append({
                "severity": "critical",
                "message": f"{plural(len(down), 'device')} {'is' if len(down) == 1 else 'are'} down or unreachable.",
                "at": latest_change(down),
            })

        critical = [s for s in services if s.Current_State == ServiceStateType.CRITICAL]
        if critical:
            insights.append({
                "severity": "critical",
                "message": f"{plural(len(critical), 'service')} {'is' if len(critical) == 1 else 'are'} in a critical state.",
                "at": latest_change(critical),
            })

        warning = [s for s in services if s.Current_State == ServiceStateType.WARNING]
        if warning:
            insights.append({
                "severity": "warning",
                "message": f"{plural(len(warning), 'service')} {'is' if len(warning) == 1 else 'are'} in a warning state.",
                "at": latest_change(warning),
            })

        flapping = [h for h in hosts if h.Is_Flapping] + [s for s in services if s.Is_Flapping]
        if flapping:
            insights.append({
                "severity": "warning",
                "message": f"{plural(len(flapping), 'host or service')} {'is' if len(flapping) == 1 else 'are'} flapping between states.",
                "at": latest_change(flapping),
            })

        # ── Ping averages ────────────────────────────────────────────────────
        ping = avg_ping_metrics(hosts)
        if ping["avg_rta_ms"] is not None:
            insights.append({
                "severity": "warning" if ping["avg_rta_ms"] >= HIGH_LATENCY_MS else "info",
                "message": f"Average latency across online devices is {ping['avg_rta_ms']:.1f} ms.",
                "at": snapshot_at,
            })
        if ping["avg_packet_loss_pct"]:
            insights.append({
                "severity": "warning" if ping["avg_packet_loss_pct"] >= HIGH_PACKET_LOSS_PCT else "info",
                "message": f"Average packet loss is {ping['avg_packet_loss_pct']:.1f}%.",
                "at": snapshot_at,
            })

        # ── NCPA resource averages ───────────────────────────────────────────
        ncpa = ncpa_averages(services, hosts)
        if ncpa:
            for key, label in (("avg_cpu_pct", "CPU"), ("avg_memory_pct", "memory"), ("avg_disk_pct", "disk")):
                value = ncpa[key]
                if value is not None and value >= HIGH_RESOURCE_PCT:
                    insights.append({
                        "severity": "warning",
                        "message": f"Average {label} usage on NCPA hosts is {value:.0f}%.",
                        "at": snapshot_at,
                    })

        if not any(i["severity"] in ("critical", "warning") for i in insights):
            insights.append({
                "severity": "ok",
                "message": "Overall network condition is stable.",
                "at": snapshot_at,
            })

        order = {"critical": 0, "warning": 1, "info": 2, "ok": 3}
        insights.sort(key=lambda i: i["at"] or "", reverse=True)
        insights.sort(key=lambda i: order[i["severity"]])

        return success({"insights": insights})

    except Exception:
        current_app.logger.exception("Unexpected error in GET /system/network-health/insights")
        return error("An unexpected error occurred.", 500)


# ==========================================================
# ADDED PLUGIN TRENDS
# ==========================================================

@system_bp.get("/network-health/plugin-trends")
@login_required
@require_permission("system.network_health")
def network_health_plugin_trends():
    """
    One entry per plugin that has services and is either enabled in Plugin
    Manager (its Network Discovery "pinpoint_nd_<plugin>" services) or runs
    through the older manual "pinpoint_<plugin>" commands, so each gets its
    own widget. Plugins with dedicated widgets (ping, NCPA, the Nagios
    server's load/swap/disk) and plugins that are not enabled are left out.

    For every perf metric a plugin reports, "current" lists the latest value
    per service. Only durations (s, ms, us) and percentages are averaged
    across services ("averaged": true, with "current_avg" and a bucketed
    "points" trend); sizes and counts differ per machine, so those metrics
    only have per-service values.

    Query params:
        hours   — 5/60 (5 minutes), 1, 6, 24 (default) or 168
        buckets — number of points, 1 to 168 (default 24)

    Response shape:
    {
        "hours": int,
        "plugins": [
            {
                "plugin_name": str,               // e.g. "check_dig"
                "display_name": str,              // Plugin Manager display name
                "total": int, "ok": int, "warning": int, "critical": int, "unknown": int,
                "worst_state": "ok" | "warning" | "critical" | "unknown",
                "metrics": [
                    {
                        "metric": str,
                        "unit": str | null,
                        "averaged": bool,
                        "service_count": int,
                        "current_avg": float | null,
                        "current": [ { "hostname": str, "service": str, "value": float } ],
                        "points": [ { "bucket_start": iso, "avg_value": float | null, "unit": str | null } ]
                    }
                ]
            }
        ]
    }
    """
    hours = request.args.get("hours", default=24, type=trend_hours)
    buckets = request.args.get("buckets", default=24, type=int)

    if hours not in VALID_HOURS:
        return error(f"hours must be one of: {sorted(VALID_HOURS)}.", 400)
    if buckets is None or not 1 <= buckets <= 168:
        return error("buckets must be between 1 and 168.", 400)

    try:
        enabled = db.session.scalars(
            sa.select(Plugin).where(Plugin.Status.in_(ENABLED_PLUGIN_STATES))
        ).all()
        enabled_names = {normalize_plugin_name(p.Name) for p in enabled}

        services_by_plugin = defaultdict(list)
        for service in get_latest_services():
            name = added_plugin_name(service, enabled_names)
            if name:
                services_by_plugin[name].append(service)

        if not services_by_plugin:
            return success({"hours": hours, "plugins": []})

        display_names = {}
        for plugin in db.session.scalars(sa.select(Plugin)):
            display_names.setdefault(normalize_plugin_name(plugin.Name), plugin.Display_Name or plugin.Name)

        plugins = []
        for name, services in services_by_plugin.items():
            counts = {"ok": 0, "warning": 0, "critical": 0, "unknown": 0}
            for service in services:
                counts[STATE_LABELS.get(service.Current_State, "unknown")] += 1

            by_id = {s.ServiceStatusID: s for s in services}
            perf_rows = db.session.execute(
                sa.select(
                    ServicePerfData.ServiceStatusID,
                    ServicePerfData.Metric,
                    ServicePerfData.Unit,
                    ServicePerfData.Measured_Value,
                )
                .where(ServicePerfData.ServiceStatusID.in_(list(by_id)))
                .order_by(ServicePerfData.ServicePerfDataID)
            ).all()

            # Group current values by (metric, unit), keeping report order.
            grouped = {}
            for row in perf_rows:
                service = by_id[row.ServiceStatusID]
                grouped.setdefault((row.Metric, row.Unit), []).append({
                    "hostname": service.Hostname,
                    "service": service.Service,
                    "value": row.Measured_Value,
                })

            metrics = []
            for (metric, unit), current in grouped.items():
                current.sort(key=lambda c: (c["hostname"], c["service"]))
                averaged = (unit or "").lower() in AVERAGEABLE_UNITS
                pairs = [(c["hostname"], c["service"]) for c in current]
                metrics.append({
                    "metric": metric,
                    "unit": unit,
                    "averaged": averaged,
                    "service_count": len(current),
                    "current_avg": (
                        round(sum(c["value"] for c in current) / len(current), 4) if averaged else None
                    ),
                    "current": current,
                    "points": bucketed_average(pairs, metric, unit, hours, buckets) if averaged else [],
                })
            metrics.sort(key=lambda m: not m["averaged"])

            plugins.append({
                "plugin_name": name,
                "display_name": display_names.get(name, name),
                "total": len(services),
                **counts,
                "worst_state": max(
                    (label for label, count in counts.items() if count),
                    key=lambda label: STATE_SEVERITY[label],
                ),
                "metrics": metrics,
            })

        plugins.sort(key=lambda p: p["display_name"].lower())
        return success({"hours": hours, "plugins": plugins})

    except Exception:
        current_app.logger.exception("Unexpected error in GET /system/network-health/plugin-trends")
        return error("An unexpected error occurred.", 500)
