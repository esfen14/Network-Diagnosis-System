"""
statistics.py — Shared aggregation helpers for the dashboard and network health routes.

These are plain functions, not Flask routes. They query the history database
and return plain Python dicts/lists that the route handlers serialize into JSON.

Sections covered:
  - latest_snapshot()           : most-recent HostStatus + ServiceStatus rows per entity
  - host_counts()               : UP/DOWN/UNREACHABLE breakdown
  - service_counts()            : OK/WARNING/CRITICAL/UNKNOWN breakdown
  - active_alerts()             : hosts and services currently in a problem state
  - avg_ping_metrics()          : network-wide average RTA and packet loss (§1.3, §2.4)
  - ncpa_averages()             : network-wide NCPA CPU/disk/memory averages (§1.4, §2.4)
  - service_health_by_plugin()  : per-plugin state breakdown (§2.5)
  - perf_trends()               : time-bucketed performance data for trend charts (§2.4)
  - nagios_server_resources()   : check_load / check_disk / check_swap for localhost (§1.1, §2.4)
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

import sqlalchemy as sa

from app import db
from app.history_models import (
    HostStatus,
    HostPerfData,
    ServiceStatus,
    ServicePerfData,
    HostStateType,
    ServiceStateType,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Hostname of the Nagios server itself — its own resource checks
# (check_load, check_disk, check_swap) appear under this hostname.
NAGIOS_HOST = "localhost"

# Plugins whose perf data counts as NCPA resource metrics.
NCPA_PLUGIN_PREFIX = "check_ncpa"

# Plugins that report RTA / packet loss.
PING_PLUGINS = {"check_ping", "check_icmp", "check_fping"}

# Nagios server local resource plugins.
LOAD_PLUGIN  = "check_load"
DISK_PLUGIN  = "check_disk"
SWAP_PLUGIN  = "check_swap"

# Plugin → human-readable display name mapping (§2.5).
PLUGIN_DISPLAY_NAMES: dict[str, str] = {
    "check_ping":          "Ping / ICMP",
    "check_icmp":          "Ping / ICMP",
    "check_fping":         "Ping / ICMP",
    "check_http":          "HTTP",
    "check_tcp":           "TCP Port",
    "check_ssh":           "SSH",
    "check_smtp":          "SMTP",
    "check_dns":           "DNS",
    "check_dig":           "DNS",
    "check_disk":          "Disk (local)",
    "check_load":          "CPU Load (local)",
    "check_swap":          "Swap (local)",
    "check_ncpa":          "NCPA Agent",
    "check_snmp":          "SNMP",
    "check_ntp_time":      "NTP",
    "check_ntp_peer":      "NTP",
    "check_mysql":         "MySQL",
    "check_mysql_query":   "MySQL",
    "check_pgsql":         "PostgreSQL",
    "check_ldap":          "LDAP",
    "check_ups":           "UPS",
    "check_apt":           "Package Updates",
    "check_procs":         "Processes",
    "check_users":         "Users",
    "check_uptime":        "Uptime",
    "check_ifstatus":      "Network Interfaces",
    "check_ifoperstatus":  "Network Interfaces",
}

# Severity ranking for sorting (lower = more severe).
_STATE_RANK: dict[ServiceStateType, int] = {
    ServiceStateType.CRITICAL: 0,
    ServiceStateType.WARNING:  1,
    ServiceStateType.UNKNOWN:  2,
    ServiceStateType.OK:       3,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _latest_host_subquery():
    """Subquery that returns the most recent Timestamp per Hostname."""
    return (
        sa.select(
            HostStatus.Hostname,
            sa.func.max(HostStatus.Timestamp).label("max_ts"),
        )
        .group_by(HostStatus.Hostname)
        .subquery()
    )


def _latest_service_subquery():
    """Subquery that returns the most recent Timestamp per (Hostname, Service)."""
    return (
        sa.select(
            ServiceStatus.Hostname,
            ServiceStatus.Service,
            sa.func.max(ServiceStatus.Timestamp).label("max_ts"),
        )
        .group_by(ServiceStatus.Hostname, ServiceStatus.Service)
        .subquery()
    )


def _plugin_key(service_name: str) -> str:
    """
    Extract the plugin key from a Nagios service name.

    Nagios service descriptions often look like:
        "check_ping!host!100,20%!200,40%"   →  "check_ping"
        "HTTP Port 80"                       →  "HTTP Port 80"  (no known prefix)

    Strategy: if the service name starts with a known plugin prefix, use it.
    Otherwise, try to parse the first token before '!' or whitespace.
    """
    lower = service_name.lower().strip()
    for key in PLUGIN_DISPLAY_NAMES:
        if lower.startswith(key):
            return key
    # Fallback: first token
    first = lower.split("!")[0].split()[0]
    return first


def _display_name(plugin_key: str) -> str:
    """Map a plugin key to a human-readable display name."""
    name = PLUGIN_DISPLAY_NAMES.get(plugin_key)
    if name:
        return name
    # Strip check_ prefix for unknown plugins.
    if plugin_key.startswith("check_"):
        return plugin_key[len("check_"):].replace("_", " ").title()
    return plugin_key.replace("_", " ").title()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_latest_hosts() -> list[HostStatus]:
    """
    Return one HostStatus row per hostname (the most recent snapshot).
    """
    subq = _latest_host_subquery()
    return db.session.scalars(
        sa.select(HostStatus).join(
            subq,
            sa.and_(
                HostStatus.Hostname == subq.c.Hostname,
                HostStatus.Timestamp == subq.c.max_ts,
            ),
        )
    ).all()


def get_latest_services() -> list[ServiceStatus]:
    """
    Return one ServiceStatus row per (hostname, service) pair (most recent snapshot).
    """
    subq = _latest_service_subquery()
    return db.session.scalars(
        sa.select(ServiceStatus).join(
            subq,
            sa.and_(
                ServiceStatus.Hostname == subq.c.Hostname,
                ServiceStatus.Service  == subq.c.Service,
                ServiceStatus.Timestamp == subq.c.max_ts,
            ),
        )
    ).all()


def host_counts(hosts: list[HostStatus]) -> dict:
    """
    Return a dict with total and per-state counts for a list of latest hosts.

    Shape:
        { "total": int, "up": int, "down": int, "unreachable": int,
          "flapping": int, "in_downtime": int }
    """
    counts = {s: 0 for s in HostStateType}
    flapping = 0
    in_downtime = 0

    for h in hosts:
        counts[h.Current_State] += 1
        if h.Is_Flapping:
            flapping += 1
        if h.Scheduled_Downtime_Depth > 0:
            in_downtime += 1

    return {
        "total":       len(hosts),
        "up":          counts[HostStateType.UP],
        "down":        counts[HostStateType.DOWN],
        "unreachable": counts[HostStateType.UNREACHABLE],
        "flapping":    flapping,
        "in_downtime": in_downtime,
    }


def service_counts(services: list[ServiceStatus]) -> dict:
    """
    Return a dict with total and per-state counts for a list of latest services.

    Shape:
        { "total": int, "ok": int, "warning": int, "critical": int,
          "unknown": int, "flapping": int, "in_downtime": int }
    """
    counts = {s: 0 for s in ServiceStateType}
    flapping = 0
    in_downtime = 0

    for s in services:
        counts[s.Current_State] += 1
        if s.Is_Flapping:
            flapping += 1
        if s.Scheduled_Downtime_Depth > 0:
            in_downtime += 1

    return {
        "total":     len(services),
        "ok":        counts[ServiceStateType.OK],
        "warning":   counts[ServiceStateType.WARNING],
        "critical":  counts[ServiceStateType.CRITICAL],
        "unknown":   counts[ServiceStateType.UNKNOWN],
        "flapping":  flapping,
        "in_downtime": in_downtime,
    }


def active_alert_count(hosts: list[HostStatus], services: list[ServiceStatus]) -> dict:
    """
    Count all entities currently in a problem state.

    Shape:
        { "total": int, "critical": int, "warning": int, "unknown": int }

    Host DOWN/UNREACHABLE states are counted under "critical" since they
    represent the most severe reachability problem.
    """
    critical = sum(
        1 for h in hosts
        if h.Current_State in (HostStateType.DOWN, HostStateType.UNREACHABLE)
    )
    warning = sum(
        1 for s in services if s.Current_State == ServiceStateType.WARNING
    )
    svc_critical = sum(
        1 for s in services if s.Current_State == ServiceStateType.CRITICAL
    )
    unknown = sum(
        1 for s in services if s.Current_State == ServiceStateType.UNKNOWN
    )
    critical += svc_critical

    return {
        "total":    critical + warning + unknown,
        "critical": critical,
        "warning":  warning,
        "unknown":  unknown,
    }


def avg_ping_metrics(services: list[ServiceStatus]) -> dict:
    """
    Compute network-wide average RTA (ms) and packet loss (%) from the latest
    check_ping / check_icmp / check_fping service snapshots (§1.3, §2.4).

    Only includes hosts that have reported within the latest check cycle.

    Returns:
        {
            "configured": bool,         # False if no ping checks exist at all
            "avg_rta_ms": float | None,
            "avg_packet_loss_pct": float | None,
            "host_count": int,          # hosts included in average
        }
    """
    # Collect the ServiceStatusIDs for all ping services.
    ping_svc_ids = [
        s.ServiceStatusID
        for s in services
        if _plugin_key(s.Service) in PING_PLUGINS
    ]

    if not ping_svc_ids:
        return {"configured": False, "avg_rta_ms": None,
                "avg_packet_loss_pct": None, "host_count": 0}

    # Fetch the rta and pl metrics for those service rows.
    rows = db.session.execute(
        sa.select(
            ServicePerfData.ServiceStatusID,
            ServicePerfData.Metric,
            ServicePerfData.Measured_Value,
        ).where(
            ServicePerfData.ServiceStatusID.in_(ping_svc_ids),
            ServicePerfData.Metric.in_(["rta", "pl"]),
        )
    ).all()

    rta_vals: list[float] = []
    pl_vals: list[float] = []

    # Group by service row so we count one value per host.
    rta_by_svc: dict[int, float] = {}
    pl_by_svc:  dict[int, float] = {}

    for row in rows:
        if row.Metric == "rta":
            rta_by_svc[row.ServiceStatusID] = row.Measured_Value
        elif row.Metric == "pl":
            pl_by_svc[row.ServiceStatusID] = row.Measured_Value

    rta_vals = list(rta_by_svc.values())
    pl_vals  = list(pl_by_svc.values())

    host_count = max(len(rta_vals), len(pl_vals))

    if host_count < 2:
        # Spec §3.5: do not display an average if fewer than 2 data points.
        return {"configured": True, "avg_rta_ms": None,
                "avg_packet_loss_pct": None, "host_count": host_count,
                "insufficient_data": True}

    avg_rta = round(sum(rta_vals) / len(rta_vals), 3) if rta_vals else None
    avg_pl  = round(sum(pl_vals)  / len(pl_vals),  3) if pl_vals  else None

    return {
        "configured":          True,
        "avg_rta_ms":          avg_rta,
        "avg_packet_loss_pct": avg_pl,
        "host_count":          host_count,
    }


def ncpa_averages(
    services: list[ServiceStatus],
    hosts: list[HostStatus],
) -> dict | None:
    """
    Compute network-wide NCPA resource averages (CPU, disk, memory) across all
    hosts with check_ncpa services (§1.4, §2.4).

    Returns None when no NCPA services exist at all (conditional section — hide
    the UI block entirely).

    Returns:
        {
            "ncpa_host_count": int,     # hosts with NCPA
            "total_host_count": int,    # all monitored hosts
            "avg_cpu_pct": float | None,
            "avg_disk_pct": float | None,
            "avg_memory_pct": float | None,
        }
    """
    ncpa_svcs = [s for s in services if _plugin_key(s.Service) == "check_ncpa"]

    if not ncpa_svcs:
        return None

    ncpa_ids = [s.ServiceStatusID for s in ncpa_svcs]

    rows = db.session.execute(
        sa.select(
            ServicePerfData.Metric,
            ServicePerfData.Measured_Value,
        ).where(
            ServicePerfData.ServiceStatusID.in_(ncpa_ids),
        )
    ).all()

    cpu_vals:  list[float] = []
    disk_vals: list[float] = []
    mem_vals:  list[float] = []

    for row in rows:
        metric = row.Metric.lower()
        val    = row.Measured_Value
        # cpu/percent
        if "cpu" in metric and "percent" in metric:
            cpu_vals.append(val)
        # disk/logical/.../used_percent
        elif "disk" in metric and ("used_percent" in metric or "percent" in metric):
            disk_vals.append(val)
        # memory/virtual/percent
        elif "memory" in metric and "percent" in metric:
            mem_vals.append(val)

    def _safe_avg(vals: list[float]) -> Optional[float]:
        if len(vals) < 2:
            return None
        return round(sum(vals) / len(vals), 2)

    ncpa_hostnames = {s.Hostname for s in ncpa_svcs}

    return {
        "ncpa_host_count":  len(ncpa_hostnames),
        "total_host_count": len(hosts),
        "avg_cpu_pct":      _safe_avg(cpu_vals),
        "avg_disk_pct":     _safe_avg(disk_vals),
        "avg_memory_pct":   _safe_avg(mem_vals),
    }


def nagios_server_resources(services: list[ServiceStatus]) -> dict:
    """
    Extract the latest check_load / check_disk / check_swap metrics for the
    Nagios server itself (hostname = NAGIOS_HOST) (§1.1, §2.4).

    Always returns a result — missing plugins are represented with
    "configured: False" so the UI can show a "plugin not configured" message.

    Returns:
        {
            "cpu_load": {
                "configured": bool,
                "load1": float | None,
                "load5": float | None,
                "load15": float | None,
            },
            "disk": {
                "configured": bool,
                "mounts": [ { "mount": str, "used_bytes": float,
                              "warn": float | None, "crit": float | None } ]
            },
            "swap": {
                "configured": bool,
                "swap_used_mb": float | None,
                "warn": float | None,
                "crit": float | None,
            },
        }
    """
    # Filter to only services on the Nagios host.
    nagios_svcs = {s.Service: s for s in services if s.Hostname == NAGIOS_HOST}

    # ── check_load ──────────────────────────────────────────────────────────
    load_svc = next(
        (s for name, s in nagios_svcs.items() if _plugin_key(name) == LOAD_PLUGIN),
        None,
    )
    cpu_load: dict = {"configured": False, "load1": None, "load5": None, "load15": None}

    if load_svc:
        perf = db.session.execute(
            sa.select(ServicePerfData).where(
                ServicePerfData.ServiceStatusID == load_svc.ServiceStatusID
            )
        ).scalars().all()

        cpu_load["configured"] = True
        for p in perf:
            if p.Metric == "load1":
                cpu_load["load1"] = p.Measured_Value
            elif p.Metric == "load5":
                cpu_load["load5"] = p.Measured_Value
            elif p.Metric == "load15":
                cpu_load["load15"] = p.Measured_Value

    # ── check_disk ──────────────────────────────────────────────────────────
    disk_svc = next(
        (s for name, s in nagios_svcs.items() if _plugin_key(name) == DISK_PLUGIN),
        None,
    )
    disk: dict = {"configured": False, "mounts": []}

    if disk_svc:
        perf = db.session.execute(
            sa.select(ServicePerfData).where(
                ServicePerfData.ServiceStatusID == disk_svc.ServiceStatusID
            )
        ).scalars().all()

        disk["configured"] = True
        for p in perf:
            # Disk metric keys look like "/", "/boot", "/home", etc.
            if p.Metric.startswith("/") and "inode" not in p.Metric:
                disk["mounts"].append({
                    "mount":      p.Metric,
                    "used_bytes": p.Measured_Value,
                    "warn":       p.Warning_Threshold,
                    "crit":       p.Critical_Threshold,
                })

    # ── check_swap ──────────────────────────────────────────────────────────
    swap_svc = next(
        (s for name, s in nagios_svcs.items() if _plugin_key(name) == SWAP_PLUGIN),
        None,
    )
    swap: dict = {"configured": False, "swap_used_mb": None, "warn": None, "crit": None}

    if swap_svc:
        perf = db.session.execute(
            sa.select(ServicePerfData).where(
                ServicePerfData.ServiceStatusID == swap_svc.ServiceStatusID
            )
        ).scalars().all()

        swap["configured"] = True
        for p in perf:
            if p.Metric == "swap":
                swap["swap_used_mb"] = p.Measured_Value
                swap["warn"] = p.Warning_Threshold
                swap["crit"] = p.Critical_Threshold

    return {"cpu_load": cpu_load, "disk": disk, "swap": swap}


def service_health_by_plugin(services: list[ServiceStatus]) -> list[dict]:
    """
    Group all latest services by plugin type and produce a state breakdown (§2.5).

    Returns a list sorted by worst severity first (groups with CRITICAL services
    before WARNING, before all-OK).

    Each entry:
        {
            "plugin_key":    str,   # e.g. "check_ping"
            "display_name":  str,   # e.g. "Ping / ICMP"
            "total":         int,
            "ok":            int,
            "warning":       int,
            "critical":      int,
            "unknown":       int,
            "worst_state":   str,   # "ok" | "warning" | "critical" | "unknown"
        }
    """
    groups: dict[str, dict] = {}

    for svc in services:
        key = _plugin_key(svc.Service)
        if key not in groups:
            groups[key] = {
                "plugin_key":   key,
                "display_name": _display_name(key),
                "total":        0,
                "ok":           0,
                "warning":      0,
                "critical":     0,
                "unknown":      0,
            }
        g = groups[key]
        g["total"] += 1
        state = svc.Current_State
        if state == ServiceStateType.OK:
            g["ok"] += 1
        elif state == ServiceStateType.WARNING:
            g["warning"] += 1
        elif state == ServiceStateType.CRITICAL:
            g["critical"] += 1
        else:
            g["unknown"] += 1

    def _worst(g: dict) -> int:
        if g["critical"] > 0:
            return 0
        if g["warning"] > 0:
            return 1
        if g["unknown"] > 0:
            return 2
        return 3

    _worst_label = {0: "critical", 1: "warning", 2: "unknown", 3: "ok"}

    result = list(groups.values())
    for g in result:
        g["worst_state"] = _worst_label[_worst(g)]

    result.sort(key=_worst)
    return result


def perf_trends(
    hostname: Optional[str],
    service_name: Optional[str],
    metric_names: list[str],
    hours: int = 24,
    buckets: int = 24,
) -> list[dict]:
    """
    Return time-bucketed average performance data for a given host/service/metric
    combination over the last `hours` hours, divided into `buckets` buckets (§2.4).

    If `hostname` is None, aggregates across all hosts (network-wide).
    If `service_name` is None, aggregates across all services on that host.

    Each bucket:
        {
            "bucket_start": str (ISO-8601),
            "metric":       str,
            "avg_value":    float | None,   # None = no data in this bucket
            "unit":         str | None,
        }
    """
    now  = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours)
    bucket_size = timedelta(hours=hours) / buckets

    # Build the service subquery to limit to the right host/service.
    svc_query = sa.select(ServiceStatus.ServiceStatusID).where(
        ServiceStatus.Timestamp >= start
    )
    if hostname:
        svc_query = svc_query.where(ServiceStatus.Hostname == hostname)
    if service_name:
        svc_query = svc_query.where(ServiceStatus.Service == service_name)
    svc_ids = db.session.scalars(svc_query).all()

    if not svc_ids:
        return []

    # Fetch all relevant perf data rows in the time window.
    perf_rows = db.session.execute(
        sa.select(
            ServicePerfData.Metric,
            ServicePerfData.Measured_Value,
            ServicePerfData.Unit,
            ServiceStatus.Timestamp,
        )
        .join(ServiceStatus, ServicePerfData.ServiceStatusID == ServiceStatus.ServiceStatusID)
        .where(
            ServicePerfData.ServiceStatusID.in_(svc_ids),
            ServicePerfData.Metric.in_(metric_names),
        )
        .order_by(ServiceStatus.Timestamp.asc())
    ).all()

    # Bucket each reading.
    # bucket_index[metric][bucket_i] = list of values
    from collections import defaultdict
    bucket_data: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    unit_map: dict[str, Optional[str]] = {}

    for row in perf_rows:
        ts = row.Timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        offset = (ts - start).total_seconds()
        bucket_i = min(int(offset / bucket_size.total_seconds()), buckets - 1)
        bucket_data[row.Metric][bucket_i].append(row.Measured_Value)
        if row.Metric not in unit_map:
            unit_map[row.Metric] = row.Unit

    result: list[dict] = []
    for metric in metric_names:
        for i in range(buckets):
            bucket_start = (start + bucket_size * i).isoformat()
            vals = bucket_data[metric].get(i, [])
            avg_val = round(sum(vals) / len(vals), 4) if vals else None
            result.append({
                "bucket_start": bucket_start,
                "metric":       metric,
                "avg_value":    avg_val,
                "unit":         unit_map.get(metric),
            })

    return result
