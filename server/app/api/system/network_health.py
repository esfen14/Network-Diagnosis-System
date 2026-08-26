"""
network_health.py — API routes for the Network Health page.

Sections from Display_Requirements.md covered here:
  §2.1  Page-Level Summary Strip          (GET /system/network-health/summary)
  §2.4  Network-Wide Performance Trends   (GET /system/network-health/trends)
  §2.5  Service Health by Plugin Type     (GET /system/network-health/plugins)

Host and service status tables (§2.2, §2.3) live in their own files:
  network_hosts.py    — host table + host detail
  network_services.py — service table + service detail

All routes require login and the "system.network_health" permission.
"""

import sqlalchemy as sa
from flask import request, current_app
from flask_login import login_required

from app import db
from app.api.helper.database_access.permissions import require_permission
from app.api.helper.responses import success, error
from app.api.system import system_bp
from app.api.system.statistics import (
    get_latest_hosts,
    get_latest_services,
    host_counts,
    service_counts,
    active_alert_count,
    avg_ping_metrics,
    ncpa_averages,
    nagios_server_resources,
    service_health_by_plugin,
    perf_trends,
    NAGIOS_HOST,
    PING_PLUGINS,
    _plugin_key,
)
from app.history_models import ServiceStatus

# ---------------------------------------------------------------------------
# §2.1  Page-Level Summary Strip
# ---------------------------------------------------------------------------

@system_bp.get("/network-health/summary")
@login_required
@require_permission("system.network_health")
def network_health_summary():
    """
    Return the compact header counts for the Network Health page.

    Response shape:
    {
        "hosts": {
            "total": int, "up": int, "down": int, "unreachable": int,
            "flapping": int, "in_downtime": int
        },
        "services": {
            "total": int, "ok": int, "warning": int, "critical": int,
            "unknown": int, "flapping": int, "in_downtime": int
        },
        "active_alerts": { "total": int, "critical": int, "warning": int, "unknown": int }
    }
    """
    try:
        latest_hosts    = get_latest_hosts()
        latest_services = get_latest_services()

        return success({
            "hosts":         host_counts(latest_hosts),
            "services":      service_counts(latest_services),
            "active_alerts": active_alert_count(latest_hosts, latest_services),
        })

    except Exception:
        current_app.logger.exception(
            "Unexpected error in GET /system/network-health/summary"
        )
        return error("An unexpected error occurred.", 500)


# ---------------------------------------------------------------------------
# §2.4  Network-Wide Performance Trends
# ---------------------------------------------------------------------------

# Valid time window presets (hours).
_VALID_HOURS = {1, 6, 24, 168}  # 168 = 7 days

@system_bp.get("/network-health/trends")
@login_required
@require_permission("system.network_health")
def network_health_trends():
    """
    Return time-bucketed trend data for all network-wide metrics.

    Includes:
      - Average RTA and packet loss (always present; absent if no ping checks)
      - Average NCPA CPU/disk/memory (conditional; absent if no NCPA services)
      - Nagios server CPU load (load1, load5, load15) if check_load is configured
      - Nagios server swap if check_swap is configured
      - Nagios server disk if check_disk is configured

    Query params:
        hours   — time window: 1, 6, 24 (default), or 168 (7 days)
        buckets — number of data points in the chart (default 24, max 168)

    Response shape:
    {
        "hours":  int,
        "buckets": int,
        "ping": {
            "configured": bool,
            "rta":          [ { "bucket_start", "avg_value", "unit" } ],
            "packet_loss":  [ { "bucket_start", "avg_value", "unit" } ],
        },
        "ncpa": null | {      // null = no NCPA services, hide section
            "cpu":    [ { "bucket_start", "avg_value", "unit" } ],
            "disk":   [ { "bucket_start", "avg_value", "unit" } ],
            "memory": [ { "bucket_start", "avg_value", "unit" } ],
        },
        "nagios_server": {
            "cpu_load": {
                "configured": bool,
                "load1":  [ { "bucket_start", "avg_value", "unit" } ],
                "load5":  [ { "bucket_start", "avg_value", "unit" } ],
                "load15": [ { "bucket_start", "avg_value", "unit" } ],
            },
            "swap": {
                "configured": bool,
                "swap": [ { "bucket_start", "avg_value", "unit" } ],
            },
            "disk": {
                "configured": bool,
                "mounts": {
                    "<mount_point>": [ { "bucket_start", "avg_value", "unit" } ],
                    ...
                }
            }
        }
    }
    """
    try:
        hours   = request.args.get("hours", default=24, type=int)
        buckets = min(request.args.get("buckets", default=24, type=int), 168)

        if hours not in _VALID_HOURS:
            return error(
                f"hours must be one of: {sorted(_VALID_HOURS)}.", 400
            )
        if buckets < 1:
            return error("buckets must be at least 1.", 400)

        latest_services = get_latest_services()

        # ── Ping trends ──────────────────────────────────────────────────────
        has_ping = any(_plugin_key(s.Service) in PING_PLUGINS for s in latest_services)

        if has_ping:
            rta_trend = perf_trends(
                hostname=None, service_name=None,
                metric_names=["rta"], hours=hours, buckets=buckets,
            )
            pl_trend = perf_trends(
                hostname=None, service_name=None,
                metric_names=["pl"], hours=hours, buckets=buckets,
            )
            ping_section = {
                "configured":  True,
                "rta":         [_bucket_point(r) for r in rta_trend],
                "packet_loss": [_bucket_point(r) for r in pl_trend],
            }
        else:
            ping_section = {"configured": False, "rta": [], "packet_loss": []}

        # ── NCPA trends ──────────────────────────────────────────────────────
        ncpa_svcs = [s for s in latest_services if _plugin_key(s.Service) == "check_ncpa"]

        if ncpa_svcs:
            cpu_trend  = _ncpa_trend("cpu",    hours, buckets)
            disk_trend = _ncpa_trend("disk",   hours, buckets)
            mem_trend  = _ncpa_trend("memory", hours, buckets)
            ncpa_section: dict | None = {
                "cpu":    cpu_trend,
                "disk":   disk_trend,
                "memory": mem_trend,
            }
        else:
            ncpa_section = None

        # ── Nagios server resource trends ────────────────────────────────────
        nagios_server_section = _nagios_server_trends(
            latest_services, hours, buckets
        )

        return success({
            "hours":         hours,
            "buckets":       buckets,
            "ping":          ping_section,
            "ncpa":          ncpa_section,
            "nagios_server": nagios_server_section,
        })

    except Exception:
        current_app.logger.exception(
            "Unexpected error in GET /system/network-health/trends"
        )
        return error("An unexpected error occurred.", 500)


# ---------------------------------------------------------------------------
# §2.5  Service Health by Plugin Type
# ---------------------------------------------------------------------------

@system_bp.get("/network-health/plugins")
@login_required
@require_permission("system.network_health")
def network_health_plugins():
    """
    Return service state counts grouped by plugin type, sorted by severity.

    Response shape:
    {
        "groups": [
            {
                "plugin_key":   str,
                "display_name": str,
                "total":        int,
                "ok":           int,
                "warning":      int,
                "critical":     int,
                "unknown":      int,
                "worst_state":  "ok" | "warning" | "critical" | "unknown"
            },
            ...
        ]
    }
    """
    try:
        latest_services = get_latest_services()
        groups = service_health_by_plugin(latest_services)
        return success({"groups": groups})

    except Exception:
        current_app.logger.exception(
            "Unexpected error in GET /system/network-health/plugins"
        )
        return error("An unexpected error occurred.", 500)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _bucket_point(row: dict) -> dict:
    """Strip the 'metric' key — callers already know which metric they asked for."""
    return {
        "bucket_start": row["bucket_start"],
        "avg_value":    row["avg_value"],
        "unit":         row["unit"],
    }


def _ncpa_trend(dimension: str, hours: int, buckets: int) -> list[dict]:
    """
    Return bucketed NCPA trend data for a named dimension (cpu / disk / memory).

    NCPA metric path patterns (from Display_Requirements §1.4):
      cpu    → metric contains "cpu" and "percent"
      disk   → metric contains "disk" and ("used_percent" or "percent")
      memory → metric contains "memory" and "percent"

    We query all NCPA ServicePerfData rows in the window and filter by the
    dimension pattern rather than an exact metric name, since NCPA paths vary.
    """
    from app.history_models import ServicePerfData, ServiceStatus
    from datetime import datetime, timezone, timedelta
    from collections import defaultdict

    now   = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours)
    bucket_size = timedelta(hours=hours) / buckets

    # Fetch all NCPA service rows in the window.
    ncpa_svc_ids = db.session.scalars(
        sa.select(ServiceStatus.ServiceStatusID).where(
            ServiceStatus.Timestamp >= start,
            ServiceStatus.Service.ilike("%check_ncpa%"),
        )
    ).all()

    if not ncpa_svc_ids:
        return [{"bucket_start": (start + bucket_size * i).isoformat(),
                 "avg_value": None, "unit": None}
                for i in range(buckets)]

    rows = db.session.execute(
        sa.select(
            ServicePerfData.Metric,
            ServicePerfData.Measured_Value,
            ServicePerfData.Unit,
            ServiceStatus.Timestamp,
        )
        .join(ServiceStatus, ServicePerfData.ServiceStatusID == ServiceStatus.ServiceStatusID)
        .where(ServicePerfData.ServiceStatusID.in_(ncpa_svc_ids))
    ).all()

    # Filter rows by dimension.
    def _matches(metric: str) -> bool:
        m = metric.lower()
        if dimension == "cpu":
            return "cpu" in m and "percent" in m
        if dimension == "disk":
            return "disk" in m and ("used_percent" in m or "percent" in m)
        if dimension == "memory":
            return "memory" in m and "percent" in m
        return False

    bucket_vals: dict[int, list[float]] = defaultdict(list)
    unit_val = None

    for row in rows:
        if not _matches(row.Metric):
            continue
        ts = row.Timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        offset   = (ts - start).total_seconds()
        bucket_i = min(int(offset / bucket_size.total_seconds()), buckets - 1)
        bucket_vals[bucket_i].append(row.Measured_Value)
        if unit_val is None:
            unit_val = row.Unit

    result = []
    for i in range(buckets):
        vals = bucket_vals.get(i, [])
        avg  = round(sum(vals) / len(vals), 4) if vals else None
        result.append({
            "bucket_start": (start + bucket_size * i).isoformat(),
            "avg_value":    avg,
            "unit":         unit_val,
        })
    return result


def _nagios_server_trends(
    latest_services: list,
    hours: int,
    buckets: int,
) -> dict:
    """
    Build the nagios_server section of the trends response.

    Uses perf_trends() for each local check plugin on NAGIOS_HOST.
    Falls back to "configured: False" if the plugin is absent.
    """
    from app.api.system.statistics import LOAD_PLUGIN, DISK_PLUGIN, SWAP_PLUGIN

    nagios_svcs = {
        _plugin_key(s.Service): s.Service
        for s in latest_services
        if s.Hostname == NAGIOS_HOST
    }

    # ── CPU load ─────────────────────────────────────────────────────────────
    if LOAD_PLUGIN in nagios_svcs:
        load_trends = perf_trends(
            hostname=NAGIOS_HOST,
            service_name=nagios_svcs[LOAD_PLUGIN],
            metric_names=["load1", "load5", "load15"],
            hours=hours,
            buckets=buckets,
        )
        # Split into per-metric lists.
        load1  = [_bucket_point(r) for r in load_trends if r["metric"] == "load1"]
        load5  = [_bucket_point(r) for r in load_trends if r["metric"] == "load5"]
        load15 = [_bucket_point(r) for r in load_trends if r["metric"] == "load15"]
        cpu_load_section = {
            "configured": True,
            "load1":  load1,
            "load5":  load5,
            "load15": load15,
        }
    else:
        cpu_load_section = {"configured": False, "load1": [], "load5": [], "load15": []}

    # ── Swap ─────────────────────────────────────────────────────────────────
    if SWAP_PLUGIN in nagios_svcs:
        swap_trends = perf_trends(
            hostname=NAGIOS_HOST,
            service_name=nagios_svcs[SWAP_PLUGIN],
            metric_names=["swap"],
            hours=hours,
            buckets=buckets,
        )
        swap_section = {
            "configured": True,
            "swap": [_bucket_point(r) for r in swap_trends],
        }
    else:
        swap_section = {"configured": False, "swap": []}

    # ── Disk ─────────────────────────────────────────────────────────────────
    # Discover mount-point metric names from the latest snapshot.
    if DISK_PLUGIN in nagios_svcs:
        from app.history_models import ServiceStatus, ServicePerfData
        disk_svc = next(
            (s for s in latest_services
             if s.Hostname == NAGIOS_HOST and _plugin_key(s.Service) == DISK_PLUGIN),
            None,
        )
        if disk_svc:
            mount_metrics = db.session.scalars(
                sa.select(ServicePerfData.Metric)
                .where(
                    ServicePerfData.ServiceStatusID == disk_svc.ServiceStatusID,
                    ServicePerfData.Metric.notlike("%inode%"),
                )
                .distinct()
            ).all()

            mount_trends: dict[str, list] = {}
            for mount in mount_metrics:
                trend = perf_trends(
                    hostname=NAGIOS_HOST,
                    service_name=nagios_svcs[DISK_PLUGIN],
                    metric_names=[mount],
                    hours=hours,
                    buckets=buckets,
                )
                mount_trends[mount] = [_bucket_point(r) for r in trend]

            disk_section = {"configured": True, "mounts": mount_trends}
        else:
            disk_section = {"configured": False, "mounts": {}}
    else:
        disk_section = {"configured": False, "mounts": {}}

    return {
        "cpu_load": cpu_load_section,
        "swap":     swap_section,
        "disk":     disk_section,
    }
