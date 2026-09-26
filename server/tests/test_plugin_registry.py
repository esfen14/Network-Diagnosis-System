"""
tests/test_plugin_registry.py — Unit tests for
app/network_discovery/plugin_registry.py.

Covers plugin-name resolution (port is never the lookup key), variable
precedence, command building and validation, multi-check expansion for
SNMP (one service per OID) and NCPA (one service per metric/partition),
and the rendered Nagios `define command` objects. Pure functions — no
database or app context needed.
"""
import pytest

from app.network_discovery.plugin_registry import (
    PLUGIN_DEFINITIONS,
    PluginConfigurationError,
    Transport,
    build_service_checks,
    get_plugin_definition,
    plugin_for_command,
    render_command_definition,
    resolve_plugin_command,
    resolve_plugin_name,
    resolve_plugin_variables,
    sanitize_name_part,
)


SNMP_CONFIG = {
    "SNMP_COMMUNITY_STRING": "public",
    "SNMP_PORT": "161",
    "SNMP_OIDS": [
        {"metric": "uptime", "oid": "1.3.6.1.2.1.1.3.0"},
        {"metric": "memory_total", "oid": "1.3.6.1.4.1.2021.4.5.0"},
        {"metric": "lan_status", "oid": "1.3.6.1.2.1.2.2.1.8.3", "warning": "1", "critical": "2"},
    ],
}

NCPA_CONFIG = {
    "NCPA_PORT": "5693",
    "NCPA_METRICS": [
        {"metric": "cpu", "path": "cpu/percent", "warning": "50", "critical": "80"},
        {"metric": "memory", "path": "memory/virtual/percent", "units": "Gi"},
        {"metric": "disk", "path": "disk/logical/{partition}/percent", "fallback_path": "disk/logical/percent"},
    ],
}


# ==========================================================
# PLUGIN NAME RESOLUTION
# ==========================================================

class TestResolvePluginName:

    def test_known_names_resolve_to_their_plugin(self):
        assert resolve_plugin_name("snmp", Transport.UDP) == "snmp"
        assert resolve_plugin_name("ncpa", Transport.TCP) == "ncpa"
        assert resolve_plugin_name("ssh", Transport.TCP) == "ssh"
        assert resolve_plugin_name("ntp", Transport.UDP) == "ntp"

    def test_aliases_resolve(self):
        """nmap reports DNS as 'domain'."""
        assert resolve_plugin_name("domain", Transport.UDP) == "dns"
        assert resolve_plugin_name("domain", Transport.TCP) == "dns"

    def test_case_insensitive(self):
        assert resolve_plugin_name("SNMP", Transport.UDP) == "snmp"

    def test_unknown_names_use_generic_transport_plugin(self):
        assert resolve_plugin_name("ms-wbt-server", Transport.TCP) == "tcp"
        assert resolve_plugin_name("tftp", Transport.UDP) == "udp"
        assert resolve_plugin_name(None, Transport.TCP) == "tcp"

    def test_nrpe_is_a_plain_port_check(self):
        """NRPE is not a registered plugin; its port gets a generic TCP check."""
        assert resolve_plugin_name("nrpe", Transport.TCP) == "tcp"

    def test_plugin_on_unsupported_transport_uses_generic(self):
        """SNMP is UDP-only; an 'snmp' guess on TCP gets a plain TCP check."""
        assert resolve_plugin_name("snmp", Transport.TCP) == "tcp"

    def test_get_plugin_definition_unknown_raises(self):
        with pytest.raises(PluginConfigurationError):
            get_plugin_definition("does-not-exist")


# ==========================================================
# VARIABLES
# ==========================================================

class TestResolvePluginVariables:

    def test_precedence_defaults_config_discovered_overrides(self):
        variables = resolve_plugin_variables(
            "snmp",
            {"SNMP_COMMUNITY_STRING": "from-config", "SNMP_PORT": "161"},
            discovered={"port": "1161"},
            overrides={"community": "from-host"},
        )
        assert variables["community"] == "from-host"
        assert variables["port"] == "1161"

    def test_definition_defaults_apply_without_config(self):
        variables = resolve_plugin_variables("snmp")
        assert variables["community"] == "public"
        assert variables["port"] == 161

    def test_none_values_do_not_override(self):
        variables = resolve_plugin_variables("snmp", SNMP_CONFIG, overrides={"community": None})
        assert variables["community"] == "public"

    def test_inputs_are_not_mutated(self):
        overrides = {"community": "x"}
        resolve_plugin_variables("snmp", SNMP_CONFIG, overrides=overrides)
        assert overrides == {"community": "x"}
        assert PLUGIN_DEFINITIONS["snmp"].defaults == {"port": 161, "community": "public"}


# ==========================================================
# COMMAND RESOLUTION
# ==========================================================

class TestResolvePluginCommand:

    def test_snmp_command(self):
        command = resolve_plugin_command(
            "snmp", {"port": 161, "community": "public", "oid": "1.3.6.1.2.1.1.3.0"}, Transport.UDP
        )
        assert command == "pinpoint_nd_snmp!161!public!1.3.6.1.2.1.1.3.0!"

    def test_optional_variables_render_into_last_argument(self):
        command = resolve_plugin_command(
            "snmp",
            {"port": 161, "community": "public", "oid": "1.2.3", "warning": "5", "critical": "10"},
        )
        assert command == "pinpoint_nd_snmp!161!public!1.2.3!-w '5' -c '10'"

    def test_unknown_variables_are_ignored(self):
        command = resolve_plugin_command("tcp", {"port": 8080, "oids": [1, 2], "unused": "x"})
        assert command == "pinpoint_nd_tcp!8080!"

    def test_port_is_a_variable_not_a_lookup_key(self):
        """The same plugin on a non-default port still resolves by name."""
        assert resolve_plugin_command("http", {"port": 8081}) == "pinpoint_nd_http!8081!"
        assert resolve_plugin_command("ssh", {"port": 2222}) == "pinpoint_nd_ssh!2222!"

    def test_missing_required_variable(self):
        with pytest.raises(PluginConfigurationError, match="'oid'"):
            resolve_plugin_command("snmp", {"port": 161, "community": "public"})

    def test_empty_required_variable(self):
        with pytest.raises(PluginConfigurationError, match="'token'"):
            resolve_plugin_command("ncpa", {"port": 5693, "token": "", "metric_path": "cpu/percent"})

    @pytest.mark.parametrize("port", [0, 65536, "abc", "-1", "16 1"])
    def test_invalid_port(self, port):
        with pytest.raises(PluginConfigurationError, match="'port'"):
            resolve_plugin_command("tcp", {"port": port})

    @pytest.mark.parametrize("community", [
        "pub'lic",       # breaks out of single quotes
        "a!b",           # splits Nagios arguments
        "$USER1$",       # Nagios macro expansion
        "a;b",           # Nagios cfg comment
        "a`id`",         # shell command substitution
        'a"b',
        "a\\b",
        "line\nbreak",
    ])
    def test_unsafe_values_rejected_without_leaking_value(self, community):
        with pytest.raises(PluginConfigurationError) as excinfo:
            resolve_plugin_command("snmp", {"port": 161, "community": community, "oid": "1.2.3"})
        assert "'community'" in str(excinfo.value)
        assert community not in str(excinfo.value)

    def test_unsafe_optional_value_rejected(self):
        with pytest.raises(PluginConfigurationError, match="'warning'"):
            resolve_plugin_command("tcp", {"port": 80, "warning": "1;rm"})

    def test_transport_mismatch(self):
        with pytest.raises(PluginConfigurationError, match="TCP"):
            resolve_plugin_command("snmp", {"port": 161, "community": "p", "oid": "1"}, Transport.TCP)

    def test_multi_transport_plugin_accepts_both(self):
        variables = resolve_plugin_variables("dns")
        assert resolve_plugin_command("dns", variables, Transport.TCP) == "pinpoint_nd_dns!localhost!"
        assert resolve_plugin_command("dns", variables, Transport.UDP) == "pinpoint_nd_dns!localhost!"

    def test_every_definition_command_arity_matches_command_line(self):
        """Each command passes exactly len(arguments) + 1 args, matching $ARGn$ in its command_line."""
        for name, definition in PLUGIN_DEFINITIONS.items():
            variables = {variable: "1" for _flag, variable in definition.arguments}
            command = resolve_plugin_command(name, variables)
            arguments = command.split("!")[1:]
            assert len(arguments) == len(definition.arguments) + 1, name
            assert f"$ARG{len(arguments)}$" in definition.command_line, name
            assert f"$ARG{len(arguments) + 1}$" not in definition.command_line, name


# ==========================================================
# MULTI-CHECK EXPANSION
# ==========================================================

class TestSnmpChecks:

    def test_one_service_per_oid_with_its_own_oid(self):
        variables = resolve_plugin_variables("snmp", SNMP_CONFIG, discovered={"port": "161"})
        checks = build_service_checks("snmp", variables)

        assert [check.metric for check, _ in checks] == ["uptime", "memory_total", "lan_status"]
        commands = [resolve_plugin_command("snmp", service_vars, Transport.UDP) for _, service_vars in checks]
        assert commands == [
            "pinpoint_nd_snmp!161!public!1.3.6.1.2.1.1.3.0!",
            "pinpoint_nd_snmp!161!public!1.3.6.1.4.1.2021.4.5.0!",
            "pinpoint_nd_snmp!161!public!1.3.6.1.2.1.2.2.1.8.3!-w '1' -c '2'",
        ]

    def test_host_can_replace_oid_list(self):
        variables = resolve_plugin_variables(
            "snmp", SNMP_CONFIG,
            overrides={"oids": [{"metric": "cpu", "oid": "1.3.6.1.4.1.2021.11.9.0"}]},
        )
        checks = build_service_checks("snmp", variables)
        assert len(checks) == 1
        assert checks[0][1]["oid"] == "1.3.6.1.4.1.2021.11.9.0"

    def test_per_service_variables_do_not_leak_between_services(self):
        variables = resolve_plugin_variables("snmp", SNMP_CONFIG)
        checks = build_service_checks("snmp", variables)
        assert "warning" not in checks[0][1]
        assert checks[2][1]["warning"] == "1"
        assert "oid" not in variables

    @pytest.mark.parametrize("oids", [
        [{"metric": "x"}],
        [{"oid": "1.2.3"}],
        ["1.2.3"],
        "1.2.3",
    ])
    def test_malformed_oid_entries_rejected(self, oids):
        with pytest.raises(PluginConfigurationError):
            build_service_checks("snmp", {"oids": oids})

    def test_no_oids_means_no_services(self):
        assert build_service_checks("snmp", {"oids": []}) == []


class TestNcpaChecks:

    def test_one_service_per_metric_and_partition(self):
        variables = resolve_plugin_variables(
            "ncpa", NCPA_CONFIG, discovered={"token": "tok", "partitions": ["sda1", "sdb1"]}
        )
        checks = build_service_checks("ncpa", variables)

        assert [check.metric for check, _ in checks] == ["cpu", "memory", "disk_sda1", "disk_sdb1"]
        assert [service_vars["metric_path"] for _, service_vars in checks] == [
            "cpu/percent",
            "memory/virtual/percent",
            "disk/logical/sda1/percent",
            "disk/logical/sdb1/percent",
        ]

    def test_commands_carry_token_port_and_thresholds(self):
        variables = resolve_plugin_variables("ncpa", NCPA_CONFIG, discovered={"token": "tok"})
        (cpu, cpu_vars), (memory, memory_vars), _disk = build_service_checks("ncpa", variables)

        assert resolve_plugin_command("ncpa", cpu_vars, Transport.TCP) == \
            "pinpoint_nd_ncpa!5693!tok!cpu/percent!-w '50' -c '80'"
        assert resolve_plugin_command("ncpa", memory_vars, Transport.TCP) == \
            "pinpoint_nd_ncpa!5693!tok!memory/virtual/percent!-u 'Gi'"

    def test_no_partitions_uses_fallback_path(self):
        variables = resolve_plugin_variables("ncpa", NCPA_CONFIG, discovered={"token": "tok"})
        disk_check, disk_vars = build_service_checks("ncpa", variables)[2]
        assert disk_check.metric == "disk"
        assert disk_vars["metric_path"] == "disk/logical/percent"

    def test_missing_token_fails_command_resolution(self):
        variables = resolve_plugin_variables("ncpa", NCPA_CONFIG)
        _check, cpu_vars = build_service_checks("ncpa", variables)[0]
        with pytest.raises(PluginConfigurationError, match="'token'"):
            resolve_plugin_command("ncpa", cpu_vars)


# ==========================================================
# RENDERING / LOOKUPS
# ==========================================================

class TestRendering:

    def test_snmp_command_definition(self):
        rendered = render_command_definition("snmp")
        assert "command_name    pinpoint_nd_snmp" in rendered
        assert (
            "$USER1$/check_snmp -H $HOSTADDRESS$ -p '$ARG1$' -C '$ARG2$' -o '$ARG3$' $ARG4$"
            in rendered
        )

    def test_dns_queries_the_host_as_server(self):
        """check_dns' -H is the lookup name; the target host goes in -s."""
        assert PLUGIN_DEFINITIONS["dns"].command_line == \
            "$USER1$/check_dns -s $HOSTADDRESS$ -H '$ARG1$' $ARG2$"

    def test_fixed_flags_rendered(self):
        assert "-S" in PLUGIN_DEFINITIONS["https"].command_line
        assert "-s '' -e ''" in PLUGIN_DEFINITIONS["udp"].command_line

    def test_plugin_for_command(self):
        assert plugin_for_command("pinpoint_nd_snmp") == "check_snmp"
        assert plugin_for_command("pinpoint_nd_https!443!") == "check_http"
        assert plugin_for_command("pinpoint_check_snmp") is None
        assert plugin_for_command("check_ping") is None
        assert plugin_for_command(None) is None

    def test_sanitize_name_part(self):
        assert sanitize_name_part("ssl/http") == "ssl/http"
        assert sanitize_name_part("my service(1)") == "my_service_1_"
        assert sanitize_name_part("") == "unknown"
        assert sanitize_name_part(None) == "unknown"
