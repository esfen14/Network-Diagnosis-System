"""
tests/unit/test_port_lifecycle.py — Port lifecycle (app/network_discovery/port_lifecycle.py).

Phase 3 of "docs/plans/DHCP_Device_Identity_Plan.md": one missed scan changes
nothing, three misses mark a monitored port MISSING, a host that was not seen
changes no counters, NCPA's port is never archived while a token is deployed,
new ports are suggestions unless auto-monitored, a monitored port's plugin is
frozen, and only MONITORED / MISSING ports reach the Nagios config.
"""
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from app import db
from app.network_discovery.create_host_cfg import _load_monitored_hosts, build_host_services
from app.network_discovery.port_lifecycle import (
    add_user_port,
    mark_ncpa_port,
    process_device_ports,
    promote_identified_ports,
    set_port_state,
)
from app.plugin_models import Plugin, PluginSource, PluginStatus, PluginType
from app.system_models import (
    AgentStatus,
    NCPADeployment,
    Open_TCP_Services,
    Open_UDP_Services,
    PortSource,
    PortState,
)
from tests.support.identity_helpers import MAC_1, NET, make_status, patched_config, run_scan, scan

# Ports are monitored only when their plugin is enabled in Plugin Manager.
pytestmark = pytest.mark.usefixtures("monitoring_plugins")


@pytest.fixture
def device(db_session, admin_user):
    """A Linux device already saved by a scan with no ports."""
    status = make_status(db_session, admin_user)
    return run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1))[(NET, "10.0.0.5")]


def services(tcp=None, udp=None):
    return {
        "tcp": {str(p): {"service_name": n, "identified_by": "FINGERPRINT"} for p, n in (tcp or {}).items()},
        "udp": {str(p): {"service_name": n, "identified_by": "FINGERPRINT"} for p, n in (udp or {}).items()},
    }


def tcp_port(device, number):
    return db.session.scalar(sa.select(Open_TCP_Services).where(
        Open_TCP_Services.NetDiscoveryID == device.NetDiscoveryID,
        Open_TCP_Services.Port_Number == number))


def udp_port(device, number):
    return db.session.scalar(sa.select(Open_UDP_Services).where(
        Open_UDP_Services.NetDiscoveryID == device.NetDiscoveryID,
        Open_UDP_Services.Port_Number == number))


def scan_ports(device, tcp=None, udp=None, host_seen=True):
    process_device_ports(device, services(tcp, udp), host_seen=host_seen)
    db.session.commit()


def miss(device, times, tcp=None, host_seen=True):
    for _ in range(times):
        scan_ports(device, tcp=tcp, host_seen=host_seen)


def deploy_ncpa_token(device, token="tok"):
    db.session.add(NCPADeployment(
        Token=token, Agent_Status=AgentStatus.DEPLOYED, NetworkDiscoveryID=device.NetDiscoveryID))
    db.session.commit()


# ==========================================================
# NEW PORTS
# ==========================================================

class TestNewPorts:

    def test_auto_monitored_service_is_monitored_on_first_sighting(self, device):
        scan_ports(device, tcp={22: "ssh"}, udp={161: "snmp"})

        ssh = tcp_port(device, 22)
        assert ssh.Port_State is PortState.MONITORED
        assert ssh.Source is PortSource.SCAN
        assert ssh.Plugin_Name == "ssh"
        assert udp_port(device, 161).Port_State is PortState.MONITORED

    def test_other_services_start_as_suggestions(self, device):
        scan_ports(device, tcp={8080: "http-proxy", 9999: "Unknown"})

        assert tcp_port(device, 8080).Port_State is PortState.SUGGESTED
        assert tcp_port(device, 9999).Port_State is PortState.SUGGESTED
        assert tcp_port(device, 8080).Plugin_Name is None

    def test_plugin_manager_is_the_switch(self, device):
        http_plugin = db.session.scalar(sa.select(Plugin).where(Plugin.Name == "check_http"))
        http_plugin.Status = PluginStatus.DISABLED
        db.session.commit()

        scan_ports(device, tcp={22: "ssh", 80: "http"})

        assert tcp_port(device, 22).Port_State is PortState.MONITORED
        assert tcp_port(device, 80).Port_State is PortState.SUGGESTED
        assert tcp_port(device, 80).Plugin_Name is None

    def test_enabling_a_plugin_promotes_its_identified_ports(self, device):
        scan_ports(device, tcp={3306: "mysql"})
        assert tcp_port(device, 3306).Port_State is PortState.SUGGESTED
        assert promote_identified_ports() == 0

        db.session.add(Plugin(Name="check_mysql", Plugin_Type=PluginType.NAGIOS,
                              Source=PluginSource.BASELINE_ISO, Status=PluginStatus.ENABLED))
        db.session.commit()

        assert promote_identified_ports() == 1
        db.session.commit()
        assert tcp_port(device, 3306).Port_State is PortState.MONITORED
        assert tcp_port(device, 3306).Plugin_Name == "mysql"

    def test_ephemeral_ports_are_never_recorded(self, device):
        scan_ports(device, tcp={40000: "http", 55000: "ssh", 6000: "http"})

        assert tcp_port(device, 40000) is None
        assert tcp_port(device, 55000) is None
        assert tcp_port(device, 6000) is not None

    def test_rescanning_never_duplicates_a_port(self, device):
        for _ in range(3):
            scan_ports(device, tcp={22: "ssh"})

        assert len(db.session.scalars(sa.select(Open_TCP_Services)).all()) == 1

    def test_database_enforces_one_row_per_device_and_port(self, device):
        scan_ports(device, tcp={22: "ssh"})
        db.session.add(Open_TCP_Services(
            Port_Number=22, Service_Name="ssh", NetDiscoveryID=device.NetDiscoveryID))

        with pytest.raises(sa.exc.IntegrityError):
            db.session.commit()
        db.session.rollback()


# ==========================================================
# MISSED SCANS AND HYSTERESIS
# ==========================================================

class TestMissedScans:

    def test_one_missed_scan_changes_nothing(self, device):
        scan_ports(device, tcp={22: "ssh"})

        miss(device, 1)

        port = tcp_port(device, 22)
        assert port is not None
        assert port.Port_State is PortState.MONITORED
        assert port.Missed_Scans == 1

    def test_five_misses_mark_a_monitored_port_missing_but_keep_it(self, device):
        scan_ports(device, tcp={22: "ssh"})

        miss(device, 4)
        assert tcp_port(device, 22).Port_State is PortState.MONITORED
        miss(device, 1)

        port = tcp_port(device, 22)
        assert port.Port_State is PortState.MISSING
        assert port.Closed_At is not None

    def test_threshold_is_configurable(self, app, device):
        scan_ports(device, tcp={22: "ssh"})

        with patched_config(app, PORT_MISSING_AFTER_SCANS=1):
            miss(device, 1)

        assert tcp_port(device, 22).Port_State is PortState.MISSING

    def test_a_sighting_resets_the_miss_count(self, device):
        scan_ports(device, tcp={22: "ssh"})
        miss(device, 2)

        scan_ports(device, tcp={22: "ssh"})
        miss(device, 2)

        port = tcp_port(device, 22)
        assert port.Port_State is PortState.MONITORED
        assert port.Missed_Scans == 2

    def test_missing_port_returns_to_monitored_when_seen_again(self, device):
        scan_ports(device, tcp={22: "ssh"})
        miss(device, 5)
        assert tcp_port(device, 22).Port_State is PortState.MISSING

        scan_ports(device, tcp={22: "ssh"})

        port = tcp_port(device, 22)
        assert port.Port_State is PortState.MONITORED
        assert port.Closed_At is None
        assert port.Missed_Scans == 0

    def test_host_not_seen_changes_no_port_counters(self, device):
        scan_ports(device, tcp={22: "ssh"})

        miss(device, 10, host_seen=False)

        port = tcp_port(device, 22)
        assert port.Port_State is PortState.MONITORED
        assert port.Missed_Scans == 0

    def test_unseen_suggestion_is_archived_after_the_threshold(self, device):
        scan_ports(device, tcp={8080: "http-proxy"})

        miss(device, 5)

        assert tcp_port(device, 8080).Port_State is PortState.ARCHIVED

    def test_missing_port_is_archived_after_the_timeout(self, app, device):
        scan_ports(device, tcp={22: "ssh"})
        miss(device, 5)
        port = tcp_port(device, 22)
        port.Closed_At = datetime.now(timezone.utc) - timedelta(days=31)
        db.session.commit()

        with patched_config(app, PORT_ARCHIVE_AFTER_DAYS=30):
            miss(device, 1)

        assert tcp_port(device, 22).Port_State is PortState.ARCHIVED

    def test_missing_port_inside_the_timeout_stays_missing(self, app, device):
        scan_ports(device, tcp={22: "ssh"})
        miss(device, 5)

        with patched_config(app, PORT_ARCHIVE_AFTER_DAYS=30):
            miss(device, 5)

        assert tcp_port(device, 22).Port_State is PortState.MISSING

    def test_archived_port_seen_again_is_only_suggested(self, device):
        scan_ports(device, tcp={8080: "http-proxy"})
        miss(device, 5)
        assert tcp_port(device, 8080).Port_State is PortState.ARCHIVED

        scan_ports(device, tcp={8080: "http-proxy"})

        assert tcp_port(device, 8080).Port_State is PortState.SUGGESTED

    def test_ignored_port_stays_ignored_when_seen_and_when_missed(self, device):
        scan_ports(device, tcp={8080: "http-proxy"})
        set_port_state(device.NetDiscoveryID, "tcp", 8080, PortState.IGNORED)
        db.session.commit()

        scan_ports(device, tcp={8080: "http-proxy"})
        assert tcp_port(device, 8080).Port_State is PortState.IGNORED
        miss(device, 5)
        assert tcp_port(device, 8080).Port_State is PortState.IGNORED

    def test_udp_ports_follow_the_same_rules(self, device):
        scan_ports(device, udp={161: "snmp"})

        process = lambda: process_device_ports(device, services(), host_seen=True)
        for _ in range(5):
            process()
        db.session.commit()

        assert udp_port(device, 161).Port_State is PortState.MISSING

    def test_no_port_row_is_ever_deleted_by_a_scan(self, device):
        scan_ports(device, tcp={22: "ssh", 80: "http", 8080: "http-proxy"})

        miss(device, 50)

        assert len(db.session.scalars(sa.select(Open_TCP_Services)).all()) == 3


# ==========================================================
# NCPA PORT PROTECTION
# ==========================================================

class TestNcpaPort:

    def test_ncpa_port_is_never_demoted_while_a_token_is_deployed(self, device):
        deploy_ncpa_token(device)
        mark_ncpa_port(device.NetDiscoveryID)
        db.session.commit()

        miss(device, 20)

        port = tcp_port(device, 5693)
        assert port.Port_State is PortState.MONITORED
        assert port.Source is PortSource.NCPA

    def test_ncpa_port_can_be_demoted_without_a_token(self, device):
        mark_ncpa_port(device.NetDiscoveryID)
        db.session.commit()

        miss(device, 5)

        assert tcp_port(device, 5693).Port_State is PortState.MISSING

    def test_mark_ncpa_port_upserts_over_a_scanned_row(self, device):
        scan_ports(device, tcp={5693: "ncpa"})

        mark_ncpa_port(device.NetDiscoveryID)
        mark_ncpa_port(device.NetDiscoveryID)
        db.session.commit()

        rows = db.session.scalars(sa.select(Open_TCP_Services).where(
            Open_TCP_Services.Port_Number == 5693)).all()
        assert len(rows) == 1
        assert rows[0].Source is PortSource.NCPA
        assert rows[0].Plugin_Name == "ncpa"

    def test_ncpa_port_cannot_be_ignored_or_archived_by_a_user_with_a_token(self, device):
        deploy_ncpa_token(device)
        mark_ncpa_port(device.NetDiscoveryID)
        db.session.commit()

        for state in (PortState.IGNORED, PortState.ARCHIVED):
            with pytest.raises(ValueError):
                set_port_state(device.NetDiscoveryID, "tcp", 5693, state)


# ==========================================================
# FROZEN PLUGIN
# ==========================================================

class TestFrozenPlugin:

    def test_changed_nmap_guess_does_not_rename_a_monitored_service(self, device):
        scan_ports(device, tcp={80: "http"})
        port = tcp_port(device, 80)
        original = (port.Service_Name, port.Plugin_Name)

        scan_ports(device, tcp={80: "https"})  # nmap changes its mind

        port = tcp_port(device, 80)
        assert (port.Service_Name, port.Plugin_Name) == original
        assert port.Observed_Service_Name == "https"  # offered as a suggestion

    def test_suggestion_follows_nmap_until_it_is_monitored(self, device):
        scan_ports(device, tcp={8080: "Unknown"})

        scan_ports(device, tcp={8080: "http-proxy"})
        assert tcp_port(device, 8080).Service_Name == "http-proxy"

        set_port_state(device.NetDiscoveryID, "tcp", 8080, PortState.MONITORED)
        db.session.commit()
        port = tcp_port(device, 8080)
        frozen = (port.Service_Name, port.Plugin_Name)
        assert port.Plugin_Name is not None

        scan_ports(device, tcp={8080: "ssh"})
        assert (tcp_port(device, 8080).Service_Name, tcp_port(device, 8080).Plugin_Name) == frozen

    def test_ports_from_before_the_lifecycle_are_frozen_on_first_sighting(self, device):
        db.session.add(Open_TCP_Services(
            Port_Number=80, Service_Name="http", NetDiscoveryID=device.NetDiscoveryID))
        db.session.commit()
        assert tcp_port(device, 80).Plugin_Name is None

        scan_ports(device, tcp={80: "http"})

        assert tcp_port(device, 80).Plugin_Name == "http"

    def test_frozen_plugin_is_used_when_the_config_is_built(self, app, device):
        scan_ports(device, tcp={80: "http"})

        host = _load_monitored_hosts()[NET]["10.0.0.5"]
        assert host["services"]["tcp"]["80"] == {"service_name": "http", "plugin_name": "http"}

        # A frozen plugin wins over what the service name would resolve to now.
        host["services"]["tcp"]["80"]["plugin_name"] = "tcp"
        planned = build_host_services(host, {}, app.config)
        assert all("check_http" not in command for _name, command, _plugin in planned)


# ==========================================================
# USER ACTIONS
# ==========================================================

class TestUserActions:

    def test_monitoring_a_suggestion_freezes_its_plugin(self, device):
        # mysql is not in AUTO_MONITOR_SERVICES, so it starts as a suggestion.
        scan_ports(device, tcp={3306: "mysql"})
        assert tcp_port(device, 3306).Port_State is PortState.SUGGESTED

        port = set_port_state(device.NetDiscoveryID, "tcp", 3306, PortState.MONITORED)

        assert port.Port_State is PortState.MONITORED
        assert port.Plugin_Name == "mysql"

    def test_unknown_port_returns_none(self, device):
        assert set_port_state(device.NetDiscoveryID, "tcp", 1234, PortState.MONITORED) is None

    def test_restoring_a_missing_port_keeps_its_plugin(self, device):
        scan_ports(device, tcp={22: "ssh"})
        miss(device, 5)

        port = set_port_state(device.NetDiscoveryID, "tcp", 22, PortState.MONITORED)

        assert port.Port_State is PortState.MONITORED
        assert port.Plugin_Name == "ssh"
        assert port.Closed_At is None

    def test_user_can_add_an_ephemeral_range_port(self, device):
        port = add_user_port(device.NetDiscoveryID, "tcp", 40000, "http")
        db.session.commit()

        assert port.Source is PortSource.USER
        assert port.Port_State is PortState.MONITORED
        # A scan that does not see it does not drop it until the usual rules apply.
        miss(device, 1)
        assert tcp_port(device, 40000).Port_State is PortState.MONITORED


# ==========================================================
# WHAT REACHES THE NAGIOS CONFIG
# ==========================================================

class TestConfigContent:

    def test_only_monitored_and_missing_ports_are_loaded(self, device):
        scan_ports(device, tcp={22: "ssh", 80: "http", 8080: "http-proxy", 3306: "mysql", 21: "ftp"})
        set_port_state(device.NetDiscoveryID, "tcp", 3306, PortState.IGNORED)
        miss_ports = tcp_port(device, 80)
        miss_ports.Port_State = PortState.MISSING
        archived = tcp_port(device, 21)
        archived.Port_State = PortState.ARCHIVED
        db.session.commit()

        loaded = _load_monitored_hosts()[NET]["10.0.0.5"]["services"]["tcp"]

        # monitored (22), missing (80); suggested 8080, ignored 3306 and archived 21 are out.
        assert set(loaded) == {"22", "80"}
