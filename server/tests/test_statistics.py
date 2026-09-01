"""
tests/test_statistics.py
========================
Unit tests for app/api/system/statistics.py.

statistics.py contains pure helper functions — no Flask routes.
These tests call the functions directly inside an app context and verify
their return values against data seeded into the in-memory history DB.

Tested functions:
  _plugin_key()               _display_name()
  get_latest_hosts()          host_counts()           service_counts()
  active_alert_count()        avg_ping_metrics()      ncpa_averages()
  nagios_server_resources()   service_health_by_plugin()   perf_trends()
"""

import pytest
from datetime import timezone

from app.history_models import HostStateType, ServiceStateType

from tests.seed_helpers import (
    _ts,
    _make_host, _make_host_perf,
    _make_service, _make_service_perf,
    NCPA_CPU_SERVICE, NCPA_MEMORY_SERVICE, NCPA_DISK_SERVICE,
)


# ==========================================================
# _plugin_key()
# ==========================================================

class TestPluginKey:
    """
    _plugin_key() must resolve all service description formats produced by
    create_host_cfg.py to the correct check command string.
    """

    def test_simple_tcp_services(self, app):
        from app.api.system.statistics import _plugin_key
        with app.app_context():
            assert _plugin_key("http-80-TCP")    == "check_http"
            assert _plugin_key("ssh-22-TCP")     == "check_ssh"
            assert _plugin_key("mysql-3306-TCP") == "check_mysql"
            assert _plugin_key("smtp-25-TCP")    == "check_smtp"
            assert _plugin_key("ftp-21-TCP")     == "check_ftp"

    def test_simple_udp_services(self, app):
        from app.api.system.statistics import _plugin_key
        with app.app_context():
            assert _plugin_key("snmp-161-UDP") == "check_snmp"
            assert _plugin_key("dns-53-UDP")   == "check_dns"
            assert _plugin_key("ntp-123-UDP")  == "check_ntp"

    def test_ncpa_bare(self, app):
        """ncpa-5693-TCP → check_ncpa (disk-per-partition form)."""
        from app.api.system.statistics import _plugin_key
        with app.app_context():
            assert _plugin_key("ncpa-5693-TCP") == "check_ncpa"

    def test_ncpa_cpu_usage(self, app):
        """ncpa_cpu_usage-5693-TCP → check_ncpa."""
        from app.api.system.statistics import _plugin_key
        with app.app_context():
            assert _plugin_key("ncpa_cpu_usage-5693-TCP") == "check_ncpa"

    def test_ncpa_memory_usage(self, app):
        """ncpa_memory_usage-5693-TCP → check_ncpa."""
        from app.api.system.statistics import _plugin_key
        with app.app_context():
            assert _plugin_key("ncpa_memory_usage-5693-TCP") == "check_ncpa"

    def test_ncpa_disk_usage(self, app):
        """ncpa_disk_usage-5693-TCP → check_ncpa."""
        from app.api.system.statistics import _plugin_key
        with app.app_context():
            assert _plugin_key("ncpa_disk_usage-5693-TCP") == "check_ncpa"

    def test_ncpa_disk_per_partition(self, app):
        """ncpa-5693-TCP-disk_usage_/ → check_ncpa (partition name after 3rd segment)."""
        from app.api.system.statistics import _plugin_key
        with app.app_context():
            assert _plugin_key("ncpa-5693-TCP-disk_usage_/") == "check_ncpa"

    def test_nagios_server_local_plugins(self, app):
        from app.api.system.statistics import _plugin_key
        with app.app_context():
            assert _plugin_key("load-0-TCP")  == "check_load"
            assert _plugin_key("disk-0-TCP")  == "check_disk"
            assert _plugin_key("swap-0-TCP")  == "check_swap"

    def test_unknown_service_falls_back_to_check_prefix(self, app):
        """Service not in any map falls back to check_{prefix}."""
        from app.api.system.statistics import _plugin_key
        with app.app_context():
            assert _plugin_key("xyzservice-9999-TCP") == "check_xyzservice"

    def test_case_insensitive_prefix(self, app):
        """Prefix extraction is lowercased before lookup."""
        from app.api.system.statistics import _plugin_key
        with app.app_context():
            assert _plugin_key("HTTP-80-TCP") == "check_http"


# ==========================================================
# _display_name()
# ==========================================================

class TestDisplayName:

    def test_strips_check_prefix(self, app):
        from app.api.system.statistics import _display_name
        with app.app_context():
            assert _display_name("check_http")  == "HTTP"
            assert _display_name("check_ncpa")  == "NCPA"
            assert _display_name("check_ping")  == "PING"
            assert _display_name("check_ssh")   == "SSH"
            assert _display_name("check_snmp")  == "SNMP"
            assert _display_name("check_mysql") == "MYSQL"

    def test_bare_name_without_check_prefix(self, app):
        from app.api.system.statistics import _display_name
        with app.app_context():
            assert _display_name("http") == "HTTP"
            assert _display_name("ncpa") == "NCPA"



# ==========================================================
# host_counts()
# ==========================================================

class TestHostCounts:

    def test_empty_list(self, app):
        from app.api.system.statistics import host_counts
        with app.app_context():
            result = host_counts([])
        assert result == {
            "total": 0, "up": 0, "down": 0, "unreachable": 0,
            "flapping": 0, "in_downtime": 0,
        }

    def test_all_up(self, db_session, app):
        from app.api.system.statistics import host_counts, get_latest_hosts
        with app.app_context():
            for i in range(3):
                _make_host(db_session, f"host{i}", HostStateType.UP)
            db_session.session.commit()
            result = host_counts(get_latest_hosts())
        assert result["total"] == 3
        assert result["up"] == 3
        assert result["down"] == 0

    def test_mixed_states(self, db_session, app):
        from app.api.system.statistics import host_counts, get_latest_hosts
        with app.app_context():
            _make_host(db_session, "h1", HostStateType.UP)
            _make_host(db_session, "h2", HostStateType.DOWN)
            _make_host(db_session, "h3", HostStateType.UNREACHABLE)
            db_session.session.commit()
            result = host_counts(get_latest_hosts())
        assert result["total"] == 3
        assert result["up"] == 1
        assert result["down"] == 1
        assert result["unreachable"] == 1

    def test_flapping_and_downtime(self, db_session, app):
        from app.api.system.statistics import host_counts, get_latest_hosts
        with app.app_context():
            _make_host(db_session, "h1", HostStateType.UP, is_flapping=True)
            _make_host(db_session, "h2", HostStateType.UP, downtime_depth=1)
            _make_host(db_session, "h3", HostStateType.UP)
            db_session.session.commit()
            result = host_counts(get_latest_hosts())
        assert result["flapping"] == 1
        assert result["in_downtime"] == 1

    def test_latest_per_host_only(self, db_session, app):
        """When a host has multiple rows, only the newest counts."""
        from app.api.system.statistics import host_counts, get_latest_hosts
        with app.app_context():
            _make_host(db_session, "h1", HostStateType.DOWN, ts=_ts(-7200))
            _make_host(db_session, "h1", HostStateType.UP, ts=_ts(-60))
            db_session.session.commit()
            result = host_counts(get_latest_hosts())
        assert result["total"] == 1
        assert result["up"] == 1
        assert result["down"] == 0


# ==========================================================
# service_counts()
# ==========================================================

class TestServiceCounts:

    def test_empty_list(self, app):
        from app.api.system.statistics import service_counts
        with app.app_context():
            result = service_counts([])
        assert result == {
            "total": 0, "ok": 0, "warning": 0, "critical": 0,
            "unknown": 0, "flapping": 0, "in_downtime": 0,
        }

    def test_mixed_states(self, db_session, app):
        from app.api.system.statistics import service_counts, get_latest_services
        with app.app_context():
            _make_service(db_session, "h1", "http-80-TCP", ServiceStateType.OK)
            _make_service(db_session, "h1", "ssh-22-TCP", ServiceStateType.WARNING)
            _make_service(db_session, "h1", "mysql-3306-TCP", ServiceStateType.CRITICAL)
            _make_service(db_session, "h1", "snmp-161-UDP", ServiceStateType.UNKNOWN)
            db_session.session.commit()
            result = service_counts(get_latest_services())
        assert result["total"] == 4
        assert result["ok"] == 1
        assert result["warning"] == 1
        assert result["critical"] == 1
        assert result["unknown"] == 1

    def test_latest_per_service_only(self, db_session, app):
        from app.api.system.statistics import service_counts, get_latest_services
        with app.app_context():
            _make_service(db_session, "h1", "http-80-TCP", ServiceStateType.CRITICAL, ts=_ts(-7200))
            _make_service(db_session, "h1", "http-80-TCP", ServiceStateType.OK, ts=_ts(-60))
            db_session.session.commit()
            result = service_counts(get_latest_services())
        assert result["total"] == 1
        assert result["ok"] == 1
        assert result["critical"] == 0

    def test_flapping_and_downtime(self, db_session, app):
        from app.api.system.statistics import service_counts, get_latest_services
        with app.app_context():
            _make_service(db_session, "h1", "http-80-TCP", is_flapping=True)
            _make_service(db_session, "h1", "ssh-22-TCP", downtime_depth=2)
            db_session.session.commit()
            result = service_counts(get_latest_services())
        assert result["flapping"] == 1
        assert result["in_downtime"] == 1


# ==========================================================
# active_alert_count()
# ==========================================================

class TestActiveAlertCount:

    def test_no_alerts(self, app):
        from app.api.system.statistics import active_alert_count
        with app.app_context():
            result = active_alert_count([], [])
        assert result == {"total": 0, "critical": 0, "warning": 0, "unknown": 0}

    def test_host_down_counts_as_critical(self, db_session, app):
        from app.api.system.statistics import active_alert_count, get_latest_hosts
        with app.app_context():
            _make_host(db_session, "h1", HostStateType.DOWN)
            _make_host(db_session, "h2", HostStateType.UNREACHABLE)
            _make_host(db_session, "h3", HostStateType.UP)
            db_session.session.commit()
            result = active_alert_count(get_latest_hosts(), [])
        assert result["critical"] == 2
        assert result["total"] == 2

    def test_service_states_categorised(self, db_session, app):
        from app.api.system.statistics import active_alert_count, get_latest_services
        with app.app_context():
            _make_service(db_session, "h1", "http-80-TCP", ServiceStateType.WARNING)
            _make_service(db_session, "h1", "ssh-22-TCP", ServiceStateType.CRITICAL)
            _make_service(db_session, "h1", "snmp-161-UDP", ServiceStateType.UNKNOWN)
            _make_service(db_session, "h1", "smtp-25-TCP", ServiceStateType.OK)
            db_session.session.commit()
            result = active_alert_count([], get_latest_services())
        assert result["warning"] == 1
        assert result["critical"] == 1
        assert result["unknown"] == 1
        assert result["total"] == 3

    def test_combined_host_and_service(self, db_session, app):
        from app.api.system.statistics import (
            active_alert_count, get_latest_hosts, get_latest_services,
        )
        with app.app_context():
            _make_host(db_session, "h1", HostStateType.DOWN)
            _make_service(db_session, "h1", "http-80-TCP", ServiceStateType.WARNING)
            db_session.session.commit()
            hosts = get_latest_hosts()
            svcs = get_latest_services()
            result = active_alert_count(hosts, svcs)
        # host DOWN → critical, service WARNING → warning
        assert result["critical"] == 1
        assert result["warning"] == 1
        assert result["total"] == 2


# ==========================================================
# avg_ping_metrics()
# ==========================================================

class TestAvgPingMetrics:

    def test_no_hosts_returns_not_configured(self, app):
        from app.api.system.statistics import avg_ping_metrics
        with app.app_context():
            result = avg_ping_metrics([])
        assert result["configured"] is False
        assert result["avg_rta_ms"] is None

    def test_single_host_returns_insufficient_data(self, db_session, app):
        """< 2 hosts with ping data → insufficient_data flag, no averages."""
        from app.api.system.statistics import avg_ping_metrics, get_latest_hosts
        with app.app_context():
            h = _make_host(db_session, "h1")
            _make_host_perf(db_session, h, "rta", 5.0, "ms")
            _make_host_perf(db_session, h, "pl", 0.0, "%")
            db_session.session.commit()
            result = avg_ping_metrics(get_latest_hosts())
        assert result["configured"] is True
        assert result.get("insufficient_data") is True
        assert result["avg_rta_ms"] is None

    def test_two_hosts_returns_averages(self, db_session, app):
        from app.api.system.statistics import avg_ping_metrics, get_latest_hosts
        with app.app_context():
            h1 = _make_host(db_session, "h1")
            _make_host_perf(db_session, h1, "rta", 4.0, "ms")
            _make_host_perf(db_session, h1, "pl", 0.0, "%")
            h2 = _make_host(db_session, "h2")
            _make_host_perf(db_session, h2, "rta", 6.0, "ms")
            _make_host_perf(db_session, h2, "pl", 2.0, "%")
            db_session.session.commit()
            result = avg_ping_metrics(get_latest_hosts())
        assert result["configured"] is True
        assert result["avg_rta_ms"] == pytest.approx(5.0)
        assert result["avg_packet_loss_pct"] == pytest.approx(1.0)
        assert result["host_count"] == 2

    def test_no_perf_data_returns_not_configured(self, db_session, app):
        from app.api.system.statistics import avg_ping_metrics, get_latest_hosts
        with app.app_context():
            _make_host(db_session, "h1")
            _make_host(db_session, "h2")
            db_session.session.commit()
            result = avg_ping_metrics(get_latest_hosts())
        assert result["configured"] is False


# ==========================================================
# ncpa_averages()
# ==========================================================

class TestNcpaAverages:

    def test_no_ncpa_services_returns_none(self, db_session, app):
        from app.api.system.statistics import ncpa_averages, get_latest_services, get_latest_hosts
        with app.app_context():
            _make_service(db_session, "h1", "http-80-TCP")
            db_session.session.commit()
            result = ncpa_averages(get_latest_services(), get_latest_hosts())
        assert result is None

    def test_ncpa_cpu_service_detected(self, db_session, app):
        """ncpa_cpu_usage-5693-TCP must be detected as an NCPA service."""
        from app.api.system.statistics import ncpa_averages, get_latest_services, get_latest_hosts
        with app.app_context():
            svc = _make_service(db_session, "h1", NCPA_CPU_SERVICE)
            _make_service_perf(db_session, svc, "cpu/percent", 15.0, "%")
            db_session.session.commit()
            result = ncpa_averages(get_latest_services(), get_latest_hosts())
        assert result is not None

    def test_ncpa_memory_service_detected(self, db_session, app):
        """ncpa_memory_usage-5693-TCP must be detected as an NCPA service."""
        from app.api.system.statistics import ncpa_averages, get_latest_services, get_latest_hosts
        with app.app_context():
            svc = _make_service(db_session, "h1", NCPA_MEMORY_SERVICE)
            _make_service_perf(db_session, svc, "memory/virtual/percent", 45.0, "%")
            db_session.session.commit()
            result = ncpa_averages(get_latest_services(), get_latest_hosts())
        assert result is not None

    def test_single_ncpa_host_null_averages(self, db_session, app):
        """Only 1 host's values → averages are None (< 2 data points)."""
        from app.api.system.statistics import ncpa_averages, get_latest_services, get_latest_hosts
        with app.app_context():
            cpu = _make_service(db_session, "h1", NCPA_CPU_SERVICE)
            _make_service_perf(db_session, cpu, "cpu/percent", 15.0, "%")
            mem = _make_service(db_session, "h1", NCPA_MEMORY_SERVICE)
            _make_service_perf(db_session, mem, "memory/virtual/percent", 40.0, "%")
            disk = _make_service(db_session, "h1", NCPA_DISK_SERVICE)
            _make_service_perf(db_session, disk, "disk/logical/|/used_percent", 55.0, "%")
            db_session.session.commit()
            result = ncpa_averages(get_latest_services(), get_latest_hosts())
        assert result is not None
        assert result["avg_cpu_pct"] is None
        assert result["avg_memory_pct"] is None
        assert result["avg_disk_pct"] is None

    def test_two_ncpa_hosts_return_averages(self, db_session, app):
        from app.api.system.statistics import ncpa_averages, get_latest_services, get_latest_hosts
        with app.app_context():
            cpu1 = _make_service(db_session, "h1", NCPA_CPU_SERVICE)
            _make_service_perf(db_session, cpu1, "cpu/percent", 10.0, "%")
            mem1 = _make_service(db_session, "h1", NCPA_MEMORY_SERVICE)
            _make_service_perf(db_session, mem1, "memory/virtual/percent", 30.0, "%")
            disk1 = _make_service(db_session, "h1", NCPA_DISK_SERVICE)
            _make_service_perf(db_session, disk1, "disk/logical/|/used_percent", 20.0, "%")

            cpu2 = _make_service(db_session, "h2", NCPA_CPU_SERVICE)
            _make_service_perf(db_session, cpu2, "cpu/percent", 30.0, "%")
            mem2 = _make_service(db_session, "h2", NCPA_MEMORY_SERVICE)
            _make_service_perf(db_session, mem2, "memory/virtual/percent", 50.0, "%")
            disk2 = _make_service(db_session, "h2", NCPA_DISK_SERVICE)
            _make_service_perf(db_session, disk2, "disk/logical/|/used_percent", 40.0, "%")

            db_session.session.commit()
            result = ncpa_averages(get_latest_services(), get_latest_hosts())
        assert result is not None
        assert result["avg_cpu_pct"] == pytest.approx(20.0)
        assert result["avg_memory_pct"] == pytest.approx(40.0)
        assert result["avg_disk_pct"] == pytest.approx(30.0)

    def test_ncpa_host_count_tracked(self, db_session, app):
        from app.api.system.statistics import ncpa_averages, get_latest_services, get_latest_hosts
        with app.app_context():
            cpu1 = _make_service(db_session, "h1", NCPA_CPU_SERVICE)
            _make_service_perf(db_session, cpu1, "cpu/percent", 10.0)
            cpu2 = _make_service(db_session, "h2", NCPA_CPU_SERVICE)
            _make_service_perf(db_session, cpu2, "cpu/percent", 20.0)
            _make_host(db_session, "h1")
            _make_host(db_session, "h2")
            _make_host(db_session, "h3")  # no NCPA
            db_session.session.commit()
            result = ncpa_averages(get_latest_services(), get_latest_hosts())
        assert result["ncpa_host_count"] == 2
        assert result["total_host_count"] == 3


# ==========================================================
# nagios_server_resources()
# ==========================================================

class TestNagiosServerResources:

    def test_all_not_configured_when_empty(self, app):
        from app.api.system.statistics import nagios_server_resources
        with app.app_context():
            result = nagios_server_resources([])
        assert result["cpu_load"]["configured"] is False
        assert result["disk"]["configured"] is False
        assert result["swap"]["configured"] is False

    def test_load_configured(self, db_session, app):
        from app.api.system.statistics import nagios_server_resources, get_latest_services
        with app.app_context():
            svc = _make_service(db_session, "localhost", "load-0-TCP")
            _make_service_perf(db_session, svc, "load1", 0.42)
            _make_service_perf(db_session, svc, "load5", 0.35)
            _make_service_perf(db_session, svc, "load15", 0.28)
            db_session.session.commit()
            result = nagios_server_resources(get_latest_services())
        cpu = result["cpu_load"]
        assert cpu["configured"] is True
        assert cpu["load1"] == pytest.approx(0.42)
        assert cpu["load5"] == pytest.approx(0.35)
        assert cpu["load15"] == pytest.approx(0.28)

    def test_swap_configured(self, db_session, app):
        from app.api.system.statistics import nagios_server_resources, get_latest_services
        with app.app_context():
            svc = _make_service(db_session, "localhost", "swap-0-TCP")
            _make_service_perf(db_session, svc, "swap", 256.0, "MB", 512.0, 1024.0)
            db_session.session.commit()
            result = nagios_server_resources(get_latest_services())
        swap = result["swap"]
        assert swap["configured"] is True
        assert swap["swap_used_mb"] == pytest.approx(256.0)
        assert swap["warn"] == pytest.approx(512.0)
        assert swap["crit"] == pytest.approx(1024.0)

    def test_disk_configured(self, db_session, app):
        from app.api.system.statistics import nagios_server_resources, get_latest_services
        with app.app_context():
            svc = _make_service(db_session, "localhost", "disk-0-TCP")
            _make_service_perf(db_session, svc, "/", 10_000_000_000.0, "B",
                               20_000_000_000.0, 25_000_000_000.0)
            db_session.session.commit()
            result = nagios_server_resources(get_latest_services())
        disk = result["disk"]
        assert disk["configured"] is True
        assert len(disk["mounts"]) == 1
        assert disk["mounts"][0]["mount"] == "/"
        assert disk["mounts"][0]["used_bytes"] == pytest.approx(10_000_000_000.0)

    def test_non_localhost_services_ignored(self, db_session, app):
        """Resources from non-NAGIOS_HOST hosts must not affect the result."""
        from app.api.system.statistics import nagios_server_resources, get_latest_services
        with app.app_context():
            svc = _make_service(db_session, "other-host", "load-0-TCP")
            _make_service_perf(db_session, svc, "load1", 5.0)
            db_session.session.commit()
            result = nagios_server_resources(get_latest_services())
        assert result["cpu_load"]["configured"] is False


# ==========================================================
# service_health_by_plugin()
# ==========================================================

class TestServiceHealthByPlugin:

    def test_empty_returns_empty_list(self, app):
        from app.api.system.statistics import service_health_by_plugin
        with app.app_context():
            assert service_health_by_plugin([]) == []

    def test_groups_by_plugin_key(self, db_session, app):
        from app.api.system.statistics import service_health_by_plugin, get_latest_services
        with app.app_context():
            _make_service(db_session, "h1", "http-80-TCP")
            _make_service(db_session, "h2", "http-443-TCP")
            _make_service(db_session, "h1", "ssh-22-TCP")
            db_session.session.commit()
            result = service_health_by_plugin(get_latest_services())
        names = {g["display_name"] for g in result}
        assert "HTTP" in names
        assert "SSH" in names

    def test_worst_state_sorting_critical_first(self, db_session, app):
        from app.api.system.statistics import service_health_by_plugin, get_latest_services
        with app.app_context():
            _make_service(db_session, "h1", "http-80-TCP", ServiceStateType.OK)
            _make_service(db_session, "h1", "ssh-22-TCP", ServiceStateType.CRITICAL)
            _make_service(db_session, "h1", "mysql-3306-TCP", ServiceStateType.WARNING)
            db_session.session.commit()
            result = service_health_by_plugin(get_latest_services())
        states = [g["worst_state"] for g in result]
        assert states.index("critical") < states.index("warning")
        assert states.index("critical") < states.index("ok")

    def test_counts_within_group(self, db_session, app):
        from app.api.system.statistics import service_health_by_plugin, get_latest_services
        with app.app_context():
            _make_service(db_session, "h1", "http-80-TCP", ServiceStateType.OK)
            _make_service(db_session, "h2", "http-443-TCP", ServiceStateType.CRITICAL)
            _make_service(db_session, "h3", "http-8080-TCP", ServiceStateType.WARNING)
            db_session.session.commit()
            result = service_health_by_plugin(get_latest_services())
        http = next(g for g in result if g["display_name"] == "HTTP")
        assert http["total"] == 3
        assert http["ok"] == 1
        assert http["warning"] == 1
        assert http["critical"] == 1

    def test_group_shape(self, db_session, app):
        from app.api.system.statistics import service_health_by_plugin, get_latest_services
        with app.app_context():
            _make_service(db_session, "h1", "http-80-TCP")
            db_session.session.commit()
            result = service_health_by_plugin(get_latest_services())
        g = result[0]
        for key in ("display_name", "total", "ok", "warning", "critical", "unknown", "worst_state"):
            assert key in g


# ==========================================================
# perf_trends()
# ==========================================================

class TestPerfTrends:

    def test_returns_empty_when_no_data(self, db_session, app):
        from app.api.system.statistics import perf_trends
        with app.app_context():
            result = perf_trends("nonexistent", "nothing", ["rta"], hours=1, buckets=4)
        assert result == []

    def test_correct_bucket_count(self, db_session, app):
        from app.api.system.statistics import perf_trends
        with app.app_context():
            svc = _make_service(db_session, "h1", "http-80-TCP", ts=_ts(-1800))
            _make_service_perf(db_session, svc, "time", 0.5, "s")
            db_session.session.commit()
            result = perf_trends("h1", "http-80-TCP", ["time"], hours=6, buckets=6)
        assert len(result) == 6

    def test_non_null_bucket_has_correct_value(self, db_session, app):
        from app.api.system.statistics import perf_trends
        with app.app_context():
            svc = _make_service(db_session, "h1", "http-80-TCP", ts=_ts(-1800))
            _make_service_perf(db_session, svc, "time", 0.2, "s")
            db_session.session.commit()
            result = perf_trends("h1", "http-80-TCP", ["time"], hours=24, buckets=24)
        non_null = [r for r in result if r["avg_value"] is not None]
        assert len(non_null) >= 1
        assert non_null[0]["avg_value"] == pytest.approx(0.2)

    def test_aggregates_across_hosts_when_hostname_none(self, db_session, app):
        from app.api.system.statistics import perf_trends
        with app.app_context():
            svc1 = _make_service(db_session, "h1", "http-80-TCP", ts=_ts(-1800))
            _make_service_perf(db_session, svc1, "time", 0.1, "s")
            svc2 = _make_service(db_session, "h2", "http-80-TCP", ts=_ts(-1800))
            _make_service_perf(db_session, svc2, "time", 0.3, "s")
            db_session.session.commit()
            result = perf_trends(None, None, ["time"], hours=24, buckets=24)
        non_null = [r for r in result if r["avg_value"] is not None]
        assert len(non_null) >= 1
        assert non_null[0]["avg_value"] == pytest.approx(0.2, abs=0.01)

    def test_bucket_start_is_iso8601(self, db_session, app):
        from app.api.system.statistics import perf_trends
        with app.app_context():
            svc = _make_service(db_session, "h1", "http-80-TCP", ts=_ts(-1800))
            _make_service_perf(db_session, svc, "time", 0.1, "s")
            db_session.session.commit()
            result = perf_trends("h1", "http-80-TCP", ["time"], hours=1, buckets=4)
        for row in result:
            assert "bucket_start" in row
            # Must be parseable as an ISO-8601 string
            from datetime import datetime
            datetime.fromisoformat(row["bucket_start"])
