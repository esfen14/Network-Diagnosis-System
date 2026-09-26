"""
tests/test_create_host_cfg.py — Tests for Network Discovery's Nagios
service generation in app/network_discovery/create_host_cfg.py.

Verifies that each host only receives the services of the plugins its own
discovered ports resolve to (by service NAME, not port), that multi-check
plugins produce one service per metric, that per-host variable overrides
and system facts (NCPA token/partitions) are applied, and that the full
generated hosts.cfg defines each command once. Nagios itself is never run.
"""
import re
from contextlib import contextmanager

import pytest

from app.network_discovery.create_host_cfg import (
    _create_host_cfg_file,
    _load_monitored_hosts,
    build_host_services,
    load_host_plugin_facts,
)
from app.system_models import (
    ActivityLog,
    AgentStatus,
    DiscoveryStatus,
    NCPADeployment,
    NCPADevicePartition,
    NetworkDiscovery,
    NetworkDiscoveryStatus,
    Open_UDP_Services,
)
from app.nagios.status import insert_service_status_data
from app.history_models import ServiceStatus


SNMP_OIDS = [
    {"metric": "uptime", "oid": "1.3.6.1.2.1.1.3.0"},
    {"metric": "memory_total", "oid": "1.3.6.1.4.1.2021.4.5.0"},
    {"metric": "lan_status", "oid": "1.3.6.1.2.1.2.2.1.8.3"},
]

NCPA_METRICS = [
    {"metric": "cpu", "path": "cpu/percent", "warning": "50", "critical": "80"},
    {"metric": "memory", "path": "memory/virtual/percent", "warning": "50", "critical": "80"},
    {"metric": "disk", "path": "disk/logical/{partition}/percent", "fallback_path": "disk/logical/percent"},
]


# ─── fixtures / helpers ─────────────────────────────────────────────────────

@contextmanager
def patched_config(app, **overrides):
    """Temporarily override app.config keys, restoring them afterwards."""
    original = {key: app.config.get(key) for key in overrides}
    app.config.update(overrides)
    try:
        yield
    finally:
        app.config.update(original)


@pytest.fixture
def plugin_config(app):
    with patched_config(
        app,
        SNMP_OIDS=SNMP_OIDS,
        SNMP_COMMUNITY_STRING="public",
        SNMP_PORT="161",
        NCPA_METRICS=NCPA_METRICS,
        NCPA_PORT="5693",
    ):
        yield app.config


def make_host(hostname, tcp=None, udp=None, net_discovery_id=None, plugin_variables=None, os_name="Linux"):
    """Build one host entry in _load_monitored_hosts()'s shape."""
    return {
        "data": {
            "hostname": hostname,
            "mac_address": None,
            "os": os_name,
            "net_discovery_id": net_discovery_id,
            "plugin_variables": plugin_variables,
        },
        "services": {
            "tcp": {port: {"service_name": name} for port, name in (tcp or {}).items()},
            "udp": {port: {"service_name": name} for port, name in (udp or {}).items()},
        },
    }


def as_dict(services):
    """(name, command, plugin) tuples → {name: command}."""
    return {name: command for name, command, _plugin in services}


def make_device(db_session, user, hostname, ip, plugin_variables=None):
    log = ActivityLog(Action_Type="test", UserID=user.UserID)
    db_session.session.add(log)
    db_session.session.flush()
    status = NetworkDiscoveryStatus(
        Status=DiscoveryStatus.SUCCESS, Progress=100, Message="done", LogID=log.LogID
    )
    db_session.session.add(status)
    db_session.session.flush()
    device = NetworkDiscovery(
        Hostname=hostname,
        IP_Address=ip,
        Network="192.168.130.0/24",
        OS_Type="Linux",
        DiscoveryStatusID=status.DiscoveryStatusID,
        Plugin_Variables=plugin_variables,
    )
    db_session.session.add(device)
    db_session.session.flush()
    return device


def make_ncpa_deployment(db_session, device, token, partitions=()):
    deployment = NCPADeployment(
        Token=token, Agent_Status=AgentStatus.PENDING_NCPA, NetworkDiscoveryID=device.NetDiscoveryID
    )
    db_session.session.add(deployment)
    db_session.session.flush()
    for name in partitions:
        db_session.session.add(NCPADevicePartition(Name=name, NCPADeployID=deployment.NCPADeployID))
    db_session.session.flush()
    return deployment


def services_by_host(cfg_text):
    """Parse generated cfg text into {host_name: {service_description: check_command}}."""
    result = {}
    for block in re.findall(r"define service \{(.*?)\}", cfg_text, re.S):
        fields = {}
        for line in block.strip().splitlines():
            key, _, value = line.strip().partition(" ")
            fields[key] = value.strip()
        result.setdefault(fields["host_name"], {})[fields["service_description"]] = fields["check_command"]
    return result


# ==========================================================
# build_host_services — per-plugin behaviour
# ==========================================================

class TestSnmpHost:

    def test_one_service_per_oid(self, app, plugin_config):
        host = make_host("switch-a", udp={"161": "snmp"})
        with app.app_context():
            services = as_dict(build_host_services(host, {}, plugin_config))

        assert services == {
            "snmp-uptime-161": "pinpoint_nd_snmp!161!public!1.3.6.1.2.1.1.3.0!",
            "snmp-memory_total-161": "pinpoint_nd_snmp!161!public!1.3.6.1.4.1.2021.4.5.0!",
            "snmp-lan_status-161": "pinpoint_nd_snmp!161!public!1.3.6.1.2.1.2.2.1.8.3!",
        }

    def test_host_overrides_community_port_and_oids(self, app, plugin_config):
        host = make_host(
            "switch-b",
            udp={"161": "snmp"},
            plugin_variables={"snmp": {
                "community": "private",
                "port": 1161,
                "oids": [
                    {"metric": "cpu", "oid": "1.3.6.1.4.1.2021.11.9.0", "warning": "80"},
                    {"metric": "if_in", "oid": "1.3.6.1.2.1.2.2.1.10.1"},
                ],
            }},
        )
        with app.app_context():
            services = as_dict(build_host_services(host, {}, plugin_config))

        assert services == {
            "snmp-cpu-1161": "pinpoint_nd_snmp!1161!private!1.3.6.1.4.1.2021.11.9.0!-w '80'",
            "snmp-if_in-1161": "pinpoint_nd_snmp!1161!private!1.3.6.1.2.1.2.2.1.10.1!",
        }

    def test_unsafe_override_is_skipped_without_leaking_value(self, app, plugin_config, caplog):
        host = make_host(
            "switch-c", udp={"161": "snmp"}, plugin_variables={"snmp": {"community": "x';reboot'"}}
        )
        skipped = []
        with app.app_context():
            services = as_dict(build_host_services(host, {}, plugin_config, skipped))

        # UDP never falls back to the generic check_udp — the port is skipped.
        assert services == {}
        assert [entry["port"] for entry in skipped] == ["161"]
        assert "reboot" not in caplog.text
        assert "reboot" not in skipped[0]["reason"]


class TestNcpaHost:

    def test_one_service_per_metric_and_partition(self, app, plugin_config):
        host = make_host("linux-b", tcp={"5693": "ncpa"}, net_discovery_id=7)
        facts = {7: {"ncpa": {"token": "secrettoken", "partitions": ["sda1", "sdb1"]}}}
        with app.app_context():
            services = as_dict(build_host_services(host, facts, plugin_config))

        assert services == {
            "ncpa-cpu-5693": "pinpoint_nd_ncpa!5693!secrettoken!cpu/percent!-w '50' -c '80'",
            "ncpa-memory-5693": "pinpoint_nd_ncpa!5693!secrettoken!memory/virtual/percent!-w '50' -c '80'",
            "ncpa-disk_sda1-5693": "pinpoint_nd_ncpa!5693!secrettoken!disk/logical/sda1/percent!",
            "ncpa-disk_sdb1-5693": "pinpoint_nd_ncpa!5693!secrettoken!disk/logical/sdb1/percent!",
        }

    def test_without_deployed_token_falls_back_to_tcp(self, app, plugin_config):
        host = make_host("linux-x", tcp={"5693": "ncpa"}, net_discovery_id=8)
        with app.app_context():
            services = as_dict(build_host_services(host, {}, plugin_config))

        assert services == {"ncpa-5693": "pinpoint_nd_tcp!5693!"}

    def test_facts_belong_to_their_own_host_only(self, app, plugin_config):
        host = make_host("linux-y", tcp={"5693": "ncpa"}, net_discovery_id=9)
        facts = {7: {"ncpa": {"token": "other-hosts-token", "partitions": []}}}
        with app.app_context():
            services = as_dict(build_host_services(host, facts, plugin_config))

        assert "other-hosts-token" not in "".join(services.values())


class TestTcpUdpHosts:

    def test_tcp_services_resolve_by_name(self, app, plugin_config):
        host = make_host("web-c", tcp={"22": "ssh", "8081": "http", "443": "https", "8080": "http-proxy"})
        with app.app_context():
            services = as_dict(build_host_services(host, {}, plugin_config))

        assert services == {
            "ssh-22": "pinpoint_nd_ssh!22!",
            "http-8081": "pinpoint_nd_http!8081!",
            "https-443": "pinpoint_nd_https!443!",
            "http-proxy-8080": "pinpoint_nd_tcp!8080!",
        }

    def test_udp_services_resolve_by_name(self, app, plugin_config):
        host = make_host("ntp-d", udp={"123": "ntp", "53": "domain"})
        with app.app_context():
            services = as_dict(build_host_services(host, {}, plugin_config))

        assert services == {
            "ntp-123": "pinpoint_nd_ntp!123!",
            "dns-53": "pinpoint_nd_dns!localhost!",
        }

    def test_nrpe_port_gets_plain_tcp_check(self, app, plugin_config):
        host = make_host("nrpe-host", tcp={"5666": "nrpe"})
        with app.app_context():
            services = as_dict(build_host_services(host, {}, plugin_config))

        assert services == {"nrpe-5666": "pinpoint_nd_tcp!5666!"}

    def test_mysql_without_user_falls_back_to_tcp(self, app, plugin_config):
        host = make_host("db", tcp={"3306": "mysql"})
        with app.app_context():
            assert as_dict(build_host_services(host, {}, plugin_config)) == {
                "mysql-3306": "pinpoint_nd_tcp!3306!"
            }

    def test_mysql_with_user_override(self, app, plugin_config):
        host = make_host("db", tcp={"3306": "mysql"}, plugin_variables={"mysql": {"user": "nagios"}})
        with app.app_context():
            assert as_dict(build_host_services(host, {}, plugin_config)) == {
                "mysql-3306": "pinpoint_nd_mysql!3306!nagios!"
            }


class TestSkippedUdpServices:
    """UDP ports without a plugin that speaks their protocol are not monitored
    (a generic UDP check cannot tell up from down) but are reported."""

    def test_udp_without_plugin_is_skipped_and_reported(self, app, plugin_config):
        host = make_host("router", udp={"161": "snmp", "69": "tftp", "514": "syslog"})
        skipped = []
        with app.app_context():
            services = as_dict(build_host_services(host, {}, plugin_config, skipped))

        assert all(name.startswith("snmp-") for name in services)
        assert not any("pinpoint_nd_udp" in command for command in services.values())
        assert sorted((entry["port"], entry["service_name"]) for entry in skipped) == [
            ("514", "syslog"), ("69", "tftp"),
        ]
        for entry in skipped:
            assert entry["hostname"] == "router"
            assert entry["protocol"] == "UDP"
            assert entry["reason"] == "No plugin can check this UDP service."

    def test_override_to_plugin_name_is_monitored(self, app, plugin_config):
        # UDP_SERVICE_OVERRIDES renames by port before planning; a name that
        # matches a UDP plugin is monitored, not skipped.
        host = make_host("switch", udp={"161": "snmp"})
        skipped = []
        with app.app_context():
            services = build_host_services(host, {}, plugin_config, skipped)

        assert services and skipped == []

    def test_unconfigurable_udp_plugin_is_skipped_not_generic(self, app, plugin_config):
        # A malformed SNMP OID list cannot build a check; UDP must not fall
        # back to the generic check_udp.
        host = make_host("switch", udp={"161": "snmp"}, plugin_variables={"snmp": {"oids": "not-a-list"}})
        skipped = []
        with app.app_context():
            services = build_host_services(host, {}, plugin_config, skipped)

        assert services == []
        assert [entry["port"] for entry in skipped] == ["161"]

    def test_tcp_without_plugin_still_gets_generic_check(self, app, plugin_config):
        host = make_host("box", tcp={"9000": "cslistener"})
        skipped = []
        with app.app_context():
            services = as_dict(build_host_services(host, {}, plugin_config, skipped))

        assert services == {"cslistener-9000": "pinpoint_nd_tcp!9000!"}
        assert skipped == []

    def test_skipped_list_is_optional(self, app, plugin_config):
        host = make_host("router", udp={"69": "tftp"})
        with app.app_context():
            assert build_host_services(host, {}, plugin_config) == []


class TestServiceNames:

    def test_transport_suffix_only_on_collision(self, app, plugin_config):
        host = make_host("dns-server", tcp={"53": "domain", "22": "ssh"}, udp={"53": "domain"})
        with app.app_context():
            services = as_dict(build_host_services(host, {}, plugin_config))

        assert set(services) == {"dns-53-TCP", "dns-53-UDP", "ssh-22"}

    def test_duplicate_metric_names_stay_unique(self, app, plugin_config):
        host = make_host(
            "switch-dup",
            udp={"161": "snmp"},
            plugin_variables={"snmp": {"oids": [
                {"metric": "port", "oid": "1.1"},
                {"metric": "port", "oid": "1.2"},
            ]}},
        )
        with app.app_context():
            services = as_dict(build_host_services(host, {}, plugin_config))

        assert services == {
            "snmp-port-161": "pinpoint_nd_snmp!161!public!1.1!",
            "snmp-port-161-2": "pinpoint_nd_snmp!161!public!1.2!",
        }

    def test_illegal_characters_sanitized(self, app, plugin_config):
        host = make_host("odd", tcp={"9000": "weird(name)"})
        with app.app_context():
            services = as_dict(build_host_services(host, {}, plugin_config))

        assert services == {"weird_name_-9000": "pinpoint_nd_tcp!9000!"}

    def test_non_dict_plugin_variables_ignored(self, app, plugin_config):
        host = make_host("h", tcp={"22": "ssh"}, plugin_variables=["not", "a", "dict"])
        with app.app_context():
            assert as_dict(build_host_services(host, {}, plugin_config)) == {"ssh-22": "pinpoint_nd_ssh!22!"}


# ==========================================================
# DATABASE-BACKED INPUTS
# ==========================================================

class TestLoadHostPluginFacts:

    def test_only_deployed_agents_with_latest_deployment(self, db_session, admin_user):
        deployed = make_device(db_session, admin_user, "deployed", "10.0.0.1")
        pending = make_device(db_session, admin_user, "pending", "10.0.0.2")
        make_ncpa_deployment(db_session, deployed, "old-token", ["sda1"])
        make_ncpa_deployment(db_session, deployed, "new-token", ["nvme0n1p2"])
        make_ncpa_deployment(db_session, pending, None)

        facts = load_host_plugin_facts()

        assert facts == {
            deployed.NetDiscoveryID: {"ncpa": {"token": "new-token", "partitions": ["nvme0n1p2"]}}
        }

    def test_loaded_hosts_carry_id_and_overrides(self, db_session, admin_user):
        device = make_device(
            db_session, admin_user, "switch", "10.0.0.3",
            plugin_variables={"snmp": {"community": "private"}},
        )
        db_session.session.add(Open_UDP_Services(
            Port_Number=161, Service_Name="snmp", NetDiscoveryID=device.NetDiscoveryID
        ))
        db_session.session.commit()

        host = _load_monitored_hosts()["192.168.130.0/24"]["10.0.0.3"]

        assert host["data"]["net_discovery_id"] == device.NetDiscoveryID
        assert host["data"]["plugin_variables"] == {"snmp": {"community": "private"}}
        assert host["services"]["udp"] == {"161": {"service_name": "snmp"}}


# ==========================================================
# FULL CONFIG FILE
# ==========================================================

class TestCreateHostCfgFile:

    def test_each_host_gets_only_its_own_services(self, app, db_session, admin_user, plugin_config, tmp_path):
        ncpa_device = make_device(db_session, admin_user, "host-b", "10.0.0.12")
        make_ncpa_deployment(db_session, ncpa_device, "tokenB", ["sda1"])
        db_session.session.commit()

        discovered = {
            "10.0.0.0/24": {
                "10.0.0.11": make_host("host-a", udp={"161": "snmp"}),
                "10.0.0.12": make_host("host-b", tcp={"5693": "ncpa"}, net_discovery_id=ncpa_device.NetDiscoveryID),
                "10.0.0.13": make_host("host-c", tcp={"22": "ssh"}),
                "10.0.0.14": make_host("host-d", udp={"123": "ntp"}),
            }
        }

        with patched_config(app, HOST_CONFIG_DIR=tmp_path):
            cfg_path = _create_host_cfg_file(discovered)
        cfg_text = cfg_path.read_text()
        services = services_by_host(cfg_text)

        assert set(services["host-a"]) == {"snmp-uptime-161", "snmp-memory_total-161", "snmp-lan_status-161"}
        assert set(services["host-b"]) == {"ncpa-cpu-5693", "ncpa-memory-5693", "ncpa-disk_sda1-5693"}
        assert services["host-c"] == {"ssh-22": "pinpoint_nd_ssh!22!"}
        assert services["host-d"] == {"ntp-123": "pinpoint_nd_ntp!123!"}

        assert all(cmd.startswith("pinpoint_nd_snmp!") for cmd in services["host-a"].values())
        assert all(cmd.startswith("pinpoint_nd_ncpa!5693!tokenB!") for cmd in services["host-b"].values())

    def test_commands_defined_once_for_used_plugins_only(self, app, db_session, admin_user, plugin_config, tmp_path):
        discovered = {
            "10.0.0.0/24": {
                "10.0.0.11": make_host("host-a", udp={"161": "snmp"}),
                "10.0.0.13": make_host("host-c", tcp={"22": "ssh", "2222": "ssh"}),
            }
        }

        with patched_config(app, HOST_CONFIG_DIR=tmp_path):
            cfg_text = _create_host_cfg_file(discovered).read_text()

        command_names = re.findall(r"command_name\s+(\S+)", cfg_text)
        assert sorted(command_names) == ["pinpoint_nd_snmp", "pinpoint_nd_ssh"]
        assert "$USER1$/check_snmp -H $HOSTADDRESS$" in cfg_text
        assert "snmp-devices" not in cfg_text

    # Added with the Bug 1 fix (BUG_FINDINGS.md): commit 6109a08e had also
    # removed the OS hostgroup assignment, leaving every OS group empty.
    def test_hosts_are_added_to_their_os_hostgroup(self, app, db_session, admin_user, plugin_config, tmp_path):
        discovered = {
            "10.0.0.0/24": {
                "10.0.0.11": make_host("linux-1", os_name="Linux"),
                "10.0.0.12": make_host("win-1", os_name="Windows"),
                "10.0.0.13": make_host("mystery", os_name="SomethingElse"),
            }
        }

        with patched_config(app, HOST_CONFIG_DIR=tmp_path):
            cfg_text = _create_host_cfg_file(discovered).read_text()

        groups = dict(re.findall(r"hostgroup_name\s+(.+?)\n.*?members\s+(\S+)", cfg_text, re.S))
        assert groups == {"Linux": "linux-1", "Windows": "win-1", "Unknown": "mystery"}

    def test_skipped_services_are_collected_with_ip(self, app, db_session, admin_user, plugin_config, tmp_path):
        discovered = {
            "10.0.0.0/24": {
                "10.0.0.11": make_host("host-a", udp={"161": "snmp", "162": "snmptrap"}),
                "10.0.0.13": make_host("host-c", tcp={"22": "ssh"}),
            }
        }
        skipped = []

        with patched_config(app, HOST_CONFIG_DIR=tmp_path):
            cfg_text = _create_host_cfg_file(discovered, skipped).read_text()

        assert skipped == [{
            "hostname": "host-a",
            "port": "162",
            "protocol": "UDP",
            "service_name": "snmptrap",
            "reason": "No plugin can check this UDP service.",
            "ip_address": "10.0.0.11",
        }]
        assert "snmptrap" not in cfg_text
        assert "pinpoint_nd_udp" not in cfg_text

    def test_host_without_services_generates_no_commands(self, app, db_session, admin_user, plugin_config, tmp_path):
        discovered = {"10.0.0.0/24": {"10.0.0.20": make_host("quiet-host")}}

        with patched_config(app, HOST_CONFIG_DIR=tmp_path):
            cfg_text = _create_host_cfg_file(discovered).read_text()

        assert re.search(r"host_name\s+quiet-host", cfg_text)
        assert "define command" not in cfg_text
        assert "define service" not in cfg_text


# ==========================================================
# STATUS POLLING — Check_Command capture
# ==========================================================

class TestServiceStatusCheckCommand:

    def service_payload(self, check_command):
        """
        Minimal statusjson.cgi servicelist entry. Timestamps are in
        milliseconds and acknowledgement_type uses Nagios' own "none", to
        match what convert_to_UTC / convert_acknowledgement_type_enum now
        expect (commit 5cbd26fb). Service entries carry no host name —
        insert_service_status_data() receives it as its own argument.
        """
        return {
            "check_command": check_command,
            "status": "0",
            "plugin_output": "OK",
            "state_type": "1",
            "last_update": 1_700_000_000_000,
            "last_check": 1_700_000_000_000,
            "next_check": 1_700_000_300_000,
            "current_attempt": 1,
            "max_attempt": 3,
            "acknowledgement_type": "none",
            "is_flapping": False,
            "notifications_enabled": True,
        }

    # FIX (BUG_FINDINGS.md, Bug 2): insert_service_status_data() now takes
    # (hostname, service, data) since commit 5cbd26fb — pass the hostname
    # explicitly as the first argument.
    def test_only_command_name_is_stored(self, db_session):
        insert_service_status_data(
            "host-b",
            "ncpa-cpu-5693",
            self.service_payload("pinpoint_nd_ncpa!5693!secrettoken!cpu/percent!"),
        )

        row = db_session.session.scalar(db_session.select(ServiceStatus))
        assert row.Hostname == "host-b"
        assert row.Check_Command == "pinpoint_nd_ncpa"

    def test_missing_check_command_stored_as_null(self, db_session):
        insert_service_status_data("host-b", "ssh-22", self.service_payload(None))

        row = db_session.session.scalar(db_session.select(ServiceStatus))
        assert row.Hostname == "host-b"
        assert row.Check_Command is None
