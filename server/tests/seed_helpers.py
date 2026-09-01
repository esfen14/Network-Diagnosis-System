"""
tests/seed_helpers.py
=====================
Shared seed helper functions used across the dashboard/network-health test
files.  Import from here rather than duplicating in each file.

These helpers create HostStatus, ServiceStatus, PerfData and ProgramStatus
rows in the in-memory history DB.  All data mirrors real Nagios plugin output
as documented in spec files/Plugins_List.md.

Service names follow the "{service}-{port}-{protocol}" convention used by
create_host_cfg.py so that _plugin_key() in statistics.py extracts the correct
plugin key.

Usage
-----
    from tests.seed_helpers import (
        _ts, _make_host, _make_host_perf,
        _make_service, _make_service_perf,
        _make_program_status, _seed_realistic_network,
    )
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import sqlalchemy as sa

from app.history_models import (
    HostStatus,
    HostPerfData,
    ServiceStatus,
    ServicePerfData,
    ProgramStatus,
    HostStateType,
    ServiceStateType,
    PluginStatusType,
    ConnectionStateType,
    AcknowledgementType,
)


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def _ts(offset_seconds: int = 0) -> datetime:
    """Return a UTC-aware datetime offset from now."""
    return datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)


# ---------------------------------------------------------------------------
# NCPA service name constants — match create_host_cfg.py exactly.
#
# create_host_cfg.py generates these NCPA service descriptions per host:
#   ncpa_cpu_usage-5693-TCP
#   ncpa_memory_usage-5693-TCP
#   ncpa-5693-TCP-disk_usage_{partition_name}   (per-partition)
#   ncpa_disk_usage-5693-TCP                    (fallback, no partition data)
#
# _plugin_key() in statistics.py splits on '-' then '_', extracting "ncpa"
# as the bare prefix for all of these, then looks it up in tcp_commands.json
# which maps "ncpa" → "check_ncpa".  All four forms therefore resolve to
# "check_ncpa" correctly.
# ---------------------------------------------------------------------------
NCPA_CPU_SERVICE    = "ncpa_cpu_usage-5693-TCP"
NCPA_MEMORY_SERVICE = "ncpa_memory_usage-5693-TCP"
NCPA_DISK_SERVICE   = "ncpa-5693-TCP-disk_usage_/"   # per-partition (root partition)

def _make_host(
    db_session,
    hostname: str = "host1",
    state: HostStateType = HostStateType.UP,
    ts: datetime | None = None,
    is_flapping: bool = False,
    downtime_depth: int = 0,
    ack_type: AcknowledgementType = AcknowledgementType.NOACK,
    plugin_output: str = "PING OK - Packet loss = 0%, RTA = 1.23 ms",
) -> HostStatus:
    """Insert a HostStatus row and return it (flushed, not committed)."""
    h = HostStatus(
        Timestamp=ts or _ts(),
        Hostname=hostname,
        Current_State=state,
        Plugin_Status=(
            PluginStatusType.OK if state == HostStateType.UP else PluginStatusType.CRITICAL
        ),
        Plugin_Output=plugin_output,
        State_Type=ConnectionStateType.HARD,
        Current_Attempt=1,
        Max_Attempts=3,
        Last_Check=_ts(-60),
        Next_Check=_ts(60),
        Last_State_Change=_ts(-3600),
        Last_Hard_State_Change=_ts(-3600),
        Last_Time_Up=_ts(-60) if state == HostStateType.UP else None,
        Last_Time_Down=_ts(-60) if state == HostStateType.DOWN else None,
        Last_Time_Unreachable=_ts(-60) if state == HostStateType.UNREACHABLE else None,
        Check_Latency=0.01,
        Check_Execution_Time=0.05,
        Is_Flapping=is_flapping,
        Acknowledgement_Type=ack_type,
        Scheduled_Downtime_Depth=downtime_depth,
        Notification_Enabled=True,
    )
    db_session.session.add(h)
    db_session.session.flush()
    return h


def _make_host_perf(
    db_session,
    host_status: HostStatus,
    metric: str,
    value: float,
    unit: str | None = None,
    warn: float | None = None,
    crit: float | None = None,
    min_val: float | None = None,
    max_val: float | None = None,
) -> HostPerfData:
    """Insert a HostPerfData row linked to the given HostStatus."""
    p = HostPerfData(
        HostStatusID=host_status.HostStatusID,
        Metric=metric,
        Measured_Value=value,
        Unit=unit,
        Warning_Threshold=warn,
        Critical_Threshold=crit,
        Minimum=min_val,
        Maximum=max_val,
    )
    db_session.session.add(p)
    db_session.session.flush()
    return p


# ---------------------------------------------------------------------------
# ServiceStatus
# ---------------------------------------------------------------------------

def _make_service(
    db_session,
    hostname: str = "host1",
    service: str = "http-80-TCP",
    state: ServiceStateType = ServiceStateType.OK,
    ts: datetime | None = None,
    is_flapping: bool = False,
    downtime_depth: int = 0,
    plugin_output: str = "HTTP OK: 200",
    ack_type: AcknowledgementType = AcknowledgementType.NOACK,
) -> ServiceStatus:
    """Insert a ServiceStatus row and return it (flushed, not committed)."""
    s = ServiceStatus(
        Timestamp=ts or _ts(),
        Hostname=hostname,
        Service=service,
        Current_State=state,
        Plugin_Output=plugin_output,
        State_Type=ConnectionStateType.HARD,
        Last_Time_Ok=_ts(-60) if state == ServiceStateType.OK else None,
        Last_Time_Warning=_ts(-60) if state == ServiceStateType.WARNING else None,
        Last_Time_Critical=_ts(-60) if state == ServiceStateType.CRITICAL else None,
        Last_Time_Unknown=_ts(-60) if state == ServiceStateType.UNKNOWN else None,
        Current_Attempt=1,
        Max_Attempts=3,
        Last_Check=_ts(-60),
        Next_Check=_ts(60),
        Last_State_Change=_ts(-3600),
        Last_Hard_State_Change=_ts(-3600),
        Check_Latency=0.01,
        Check_Execution_Time=0.05,
        Notification_Enabled=True,
        Acknowledgement_Type=ack_type,
        Is_Flapping=is_flapping,
        Scheduled_Downtime_Depth=downtime_depth,
    )
    db_session.session.add(s)
    db_session.session.flush()
    return s


def _make_service_perf(
    db_session,
    svc_status: ServiceStatus,
    metric: str,
    value: float,
    unit: str | None = None,
    warn: float | None = None,
    crit: float | None = None,
    min_val: float | None = None,
    max_val: float | None = None,
) -> ServicePerfData:
    """Insert a ServicePerfData row linked to the given ServiceStatus."""
    p = ServicePerfData(
        ServiceStatusID=svc_status.ServiceStatusID,
        Metric=metric,
        Measured_Value=value,
        Unit=unit,
        Warning_Threshold=warn,
        Critical_Threshold=crit,
        Minimum=min_val,
        Maximum=max_val,
    )
    db_session.session.add(p)
    db_session.session.flush()
    return p


# ---------------------------------------------------------------------------
# ProgramStatus
# ---------------------------------------------------------------------------

def _make_program_status(db_session) -> ProgramStatus:
    """Insert a ProgramStatus row representing a running Nagios instance."""
    p = ProgramStatus(
        Timestamp=_ts(),
        Version="4.4.14",
        Update_Available=False,
        New_Version=None,
        Last_Update_Check=_ts(-3600),
        NagiosPID=1234,
        Enable_Notifications=True,
        Enable_Flap_Detection=True,
        Daemon_Mode=True,
        Program_Start_Time=_ts(-86400),
        Passive_Host_Checks_Enabled=False,
        Active_Host_Checks_Enabled=True,
        Passive_Service_Checks_Enabled=False,
        Active_Service_Checks_Enabled=True,
    )
    db_session.session.add(p)
    db_session.session.flush()
    return p


# ---------------------------------------------------------------------------
# Realistic multi-host network seed
# ---------------------------------------------------------------------------

def _seed_realistic_network(db_session):
    """
    Seed a realistic multi-host Nagios dataset.

    Hosts:
      - gateway (UP)    — check_ping perf, check_http
      - webserver (UP)  — check_ping, check_http, check_ssh, ncpa
      - dbserver (DOWN) — check_ping (100% loss), check_mysql
      - fileserver (UP) — check_ping, check_disk (WARNING), ncpa
      - localhost (UP)  — Nagios server: check_load, check_disk, check_swap

    All service names follow the "{name}-{port}-{protocol}" format.
    """
    # ── gateway (UP) ────────────────────────────────────────────────────────
    gw = _make_host(db_session, "gateway", HostStateType.UP,
                    plugin_output="PING OK - Packet loss = 0%, RTA = 2.10 ms")
    _make_host_perf(db_session, gw, "rta", 2.10, "ms", 100.0, 200.0, 0.0)
    _make_host_perf(db_session, gw, "pl", 0.0, "%", 20.0, 60.0, 0.0, 100.0)
    _make_service(db_session, "gateway", "http-80-TCP", ServiceStateType.OK,
                  plugin_output="HTTP OK: 200 - 0.123 seconds response time")
    http_gw = db_session.session.scalars(
        sa.select(ServiceStatus).where(
            ServiceStatus.Hostname == "gateway",
            ServiceStatus.Service == "http-80-TCP",
        )
    ).first()
    _make_service_perf(db_session, http_gw, "time", 0.123, "s", 1.0, 5.0, 0.0)
    _make_service_perf(db_session, http_gw, "size", 12345.0, "B")

    # ── webserver (UP) ──────────────────────────────────────────────────────
    web = _make_host(db_session, "webserver", HostStateType.UP,
                     plugin_output="PING OK - Packet loss = 0%, RTA = 3.50 ms")
    _make_host_perf(db_session, web, "rta", 3.50, "ms", 100.0, 200.0, 0.0)
    _make_host_perf(db_session, web, "pl", 0.0, "%", 20.0, 60.0, 0.0, 100.0)
    _make_service(db_session, "webserver", "http-80-TCP", ServiceStateType.OK,
                  plugin_output="HTTP OK: 200 - 0.089 seconds response time")
    http_web = db_session.session.scalars(
        sa.select(ServiceStatus).where(
            ServiceStatus.Hostname == "webserver",
            ServiceStatus.Service == "http-80-TCP",
        )
    ).first()
    _make_service_perf(db_session, http_web, "time", 0.089, "s", 1.0, 5.0, 0.0)
    ssh_web = _make_service(db_session, "webserver", "ssh-22-TCP", ServiceStateType.OK,
                            plugin_output="SSH OK - OpenSSH_8.9 (protocol 2.0)")
    _make_service_perf(db_session, ssh_web, "time", 0.012, "s", 1.0, 5.0, 0.0)
    ncpa_cpu_web = _make_service(db_session, "webserver", NCPA_CPU_SERVICE, ServiceStateType.OK,
                                 plugin_output="OK: Percent was 12.50 % | 'percent'=12.50%;70;90;")
    _make_service_perf(db_session, ncpa_cpu_web, "cpu/percent", 12.50, "%", 70.0, 90.0)

    ncpa_mem_web = _make_service(db_session, "webserver", NCPA_MEMORY_SERVICE, ServiceStateType.OK,
                                 plugin_output="OK: Percent was 45.30 % | 'percent'=45.30%;60;90;")
    _make_service_perf(db_session, ncpa_mem_web, "memory/virtual/percent", 45.30, "%", 60.0, 90.0)

    ncpa_disk_web = _make_service(db_session, "webserver", NCPA_DISK_SERVICE, ServiceStateType.OK,
                                  plugin_output="OK: Used_percent was 35.60 % | 'used_percent'=35.60%;60;96;")
    _make_service_perf(db_session, ncpa_disk_web, "disk/logical/|/used_percent", 35.60, "%", 60.0, 96.0)

    # ── dbserver (DOWN) ─────────────────────────────────────────────────────
    db_host = _make_host(db_session, "dbserver", HostStateType.DOWN,
                         plugin_output="PING CRITICAL - Packet loss = 100%")
    _make_host_perf(db_session, db_host, "rta", 0.0, "ms", 100.0, 200.0, 0.0)
    _make_host_perf(db_session, db_host, "pl", 100.0, "%", 20.0, 60.0, 0.0, 100.0)
    _make_service(db_session, "dbserver", "mysql-3306-TCP", ServiceStateType.CRITICAL,
                  plugin_output="CRITICAL: Connection refused on port 3306")

    # ── fileserver (UP) ─────────────────────────────────────────────────────
    fs = _make_host(db_session, "fileserver", HostStateType.UP,
                    plugin_output="PING OK - Packet loss = 0%, RTA = 1.80 ms")
    _make_host_perf(db_session, fs, "rta", 1.80, "ms", 100.0, 200.0, 0.0)
    _make_host_perf(db_session, fs, "pl", 0.0, "%", 20.0, 60.0, 0.0, 100.0)
    disk_fs = _make_service(db_session, "fileserver", "disk-0-TCP", ServiceStateType.WARNING,
                            plugin_output="DISK WARNING - free space: / 512 MiB (8%)")
    _make_service_perf(db_session, disk_fs, "/", 5_800_000_000.0, "B",
                       4_000_000_000.0, 5_500_000_000.0, 0.0, 6_000_000_000.0)
    ncpa_cpu_fs = _make_service(db_session, "fileserver", NCPA_CPU_SERVICE, ServiceStateType.OK,
                                plugin_output="OK: Percent was 22.10 % | 'percent'=22.10%;70;90;")
    _make_service_perf(db_session, ncpa_cpu_fs, "cpu/percent", 22.10, "%", 70.0, 90.0)

    ncpa_mem_fs = _make_service(db_session, "fileserver", NCPA_MEMORY_SERVICE, ServiceStateType.OK,
                                plugin_output="OK: Percent was 60.00 % | 'percent'=60.00%;60;90;")
    _make_service_perf(db_session, ncpa_mem_fs, "memory/virtual/percent", 60.00, "%", 60.0, 90.0)

    ncpa_disk_fs = _make_service(db_session, "fileserver", NCPA_DISK_SERVICE, ServiceStateType.OK,
                                 plugin_output="OK: Used_percent was 85.00 % | 'used_percent'=85.00%;60;96;")
    _make_service_perf(db_session, ncpa_disk_fs, "disk/logical/|/used_percent", 85.00, "%", 60.0, 96.0)

    # ── localhost (Nagios server) ────────────────────────────────────────────
    local = _make_host(db_session, "localhost", HostStateType.UP,
                       plugin_output="PING OK - Packet loss = 0%, RTA = 0.05 ms")
    _make_host_perf(db_session, local, "rta", 0.05, "ms", 100.0, 200.0, 0.0)
    _make_host_perf(db_session, local, "pl", 0.0, "%", 20.0, 60.0, 0.0, 100.0)
    load_svc = _make_service(db_session, "localhost", "load-0-TCP", ServiceStateType.OK,
                             plugin_output="OK - load average: 0.42, 0.35, 0.28")
    _make_service_perf(db_session, load_svc, "load1", 0.42, None, 5.0, 10.0)
    _make_service_perf(db_session, load_svc, "load5", 0.35, None, 5.0, 10.0)
    _make_service_perf(db_session, load_svc, "load15", 0.28, None, 5.0, 10.0)
    swap_svc = _make_service(db_session, "localhost", "swap-0-TCP", ServiceStateType.OK,
                             plugin_output="SWAP OK - 92% free (1887 MB out of 2047 MB)")
    _make_service_perf(db_session, swap_svc, "swap", 160.0, "MB", 512.0, 1024.0, 0.0, 2047.0)
    disk_svc = _make_service(db_session, "localhost", "disk-0-TCP", ServiceStateType.OK,
                             plugin_output="DISK OK - free space: / 45000 MiB (62%)")
    _make_service_perf(db_session, disk_svc, "/", 27_000_000_000.0, "B",
                       45_000_000_000.0, 54_000_000_000.0, 0.0, 72_000_000_000.0)

    db_session.session.commit()
