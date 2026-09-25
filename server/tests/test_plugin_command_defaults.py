"""
tests/test_plugin_command_defaults.py — Tests for the hand-curated
per-plugin command defaults (plugin_command_defaults.py), built from
spec files/Plugins_List.md's catalog of all 57 bundled nagios-plugins.
"""
import pytest

from app.api.plugin.plugin_command_defaults import PLUGIN_COMMAND_DEFAULTS, get_default_command
from app.api.plugin.command_validator import validate_command_definition


class TestPluginCommandDefaults:
    def test_covers_all_57_bundled_plugins(self):
        """58 dict entries = 57 unique plugin binaries: check_ntp's
        deprecated-C and Perl variants share one filename (collapsed
        to one entry), and check_ldap/check_ldaps are two distinct
        binaries documented under one catalog entry (split into two)."""
        assert len(PLUGIN_COMMAND_DEFAULTS) == 58

    def test_every_default_passes_command_validation(self):
        """None of the 58 curated defaults should trip Phase 6's
        shell-injection guard — a real safety sanity check, not just
        an assumption."""
        for name, command in PLUGIN_COMMAND_DEFAULTS.items():
            is_valid, message = validate_command_definition(command)
            assert is_valid, f"{name}: {message}"

    def test_get_default_command_returns_curated_value(self):
        assert get_default_command("check_snmp") == "check_snmp -H $HOSTADDRESS$ -o $ARG1$"

    def test_get_default_command_returns_none_for_unknown_plugin(self):
        assert get_default_command("check_some_custom_thing") is None

    @pytest.mark.parametrize("name", [
        "check_disk", "check_load", "check_swap", "check_procs",
        "check_users", "check_uptime", "check_mailq", "check_sensors",
        "check_apt", "check_dhcp", "check_oracle",
    ])
    def test_local_checks_have_no_hostaddress_macro(self, name):
        """These plugins have no -H/--hostname flag at all per the
        catalog — they check the Nagios server itself, not a remote
        target. Including $HOSTADDRESS$ for these would be wrong."""
        command = PLUGIN_COMMAND_DEFAULTS[name]
        assert "$HOSTADDRESS$" not in command

    @pytest.mark.parametrize("name", [
        "check_snmp", "check_http", "check_ping", "check_tcp", "check_ssh",
        "check_smtp", "check_dns", "check_ntp", "check_mysql", "check_pgsql",
    ])
    def test_remote_checks_have_hostaddress_macro(self, name):
        """These plugins have a real -H/--hostname flag per the
        catalog (required or optional) — Plugin Manager's whole point
        is targeting a specific device, so all of these should point
        at it."""
        command = PLUGIN_COMMAND_DEFAULTS[name]
        assert "$HOSTADDRESS$" in command

    def test_required_multi_arg_plugin_has_all_args_in_order(self):
        """check_mrtg has 6 required arguments per the catalog — spot
        checks that multi-arg ordering was preserved correctly, not
        just that *some* $ARGn$ macros are present."""
        command = PLUGIN_COMMAND_DEFAULTS["check_mrtg"]
        assert command == "check_mrtg -F $ARG1$ -w $ARG2$ -c $ARG3$ -e $ARG4$ -a $ARG5$ -v $ARG6$"
