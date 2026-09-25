"""
plugin_command_defaults.py — Hand-curated default command lines for
every plugin bundled with nagios-plugins 2.4.12 (the baseline ISO
set — see scanner.py's PluginSource.BASELINE_ISO).

Source: spec files/Plugins_List.md (integration branch) — a complete
catalog of all 57 bundled plugins' actual required/optional arguments,
built from the real nagios-plugins 2.4.12 source. Curated by hand
against that catalog, not auto-parsed: a wrong default here could
cause a real monitoring failure once applied via Phase 10, so each
entry was checked individually rather than derived mechanically.

Rules applied consistently across every entry:
  - Any plugin with an -H/--hostname flag gets "-H $HOSTADDRESS$" —
    even when the plugin doc marks -H optional (e.g. check_mysql,
    check_pgsql default to localhost) — because Plugin Manager's
    whole purpose (Phase 10) is targeting a specific remote device;
    an admin applying a plugin to a target virtually always wants it
    pointed at that target.
  - Every OTHER required argument (per the catalog's "Required: Yes"
    column) becomes $ARG1$, $ARG2$, etc. in the order it's listed —
    the standard Nagios convention for values supplied per-service via
    the service definition, not hardcoded into the command itself.
  - Plugins with no -H flag at all (check_disk, check_load, check_swap,
    etc.) are genuinely LOCAL checks — they inspect the Nagios server
    itself, not a remote target — so no $HOSTADDRESS$ is added.
  - Purely optional arguments are left out entirely; an admin can add
    them via Phase 6's command override.

This is looked up by scanner.py's sync_plugin_inventory() BEFORE
falling back to the generic "<name> -H $HOSTADDRESS$" default — see
PLUGIN_COMMAND_DEFAULTS.get(name, GENERIC_FALLBACK) there. Plugins not
in this dict (custom/non-standard executables) still get the generic
fallback, unchanged from before.
"""

PLUGIN_COMMAND_DEFAULTS = {
    "check_apt": "check_apt",
    "check_breeze": "check_breeze -H $HOSTADDRESS$ -w $ARG1$ -c $ARG2$",
    "check_by_ssh": "check_by_ssh -H $HOSTADDRESS$ -C $ARG1$",
    "check_cluster": "check_cluster -d $ARG1$ -w $ARG2$ -c $ARG3$",
    "check_dbi": "check_dbi -d $ARG1$ -H $HOSTADDRESS$",
    "check_dhcp": "check_dhcp",
    "check_dig": "check_dig -H $HOSTADDRESS$",
    "check_disk": "check_disk -w $ARG1$ -c $ARG2$",
    "check_disk_smb": "check_disk_smb -H $HOSTADDRESS$ -s $ARG1$",
    "check_dns": "check_dns -H $HOSTADDRESS$",
    "check_dummy": "check_dummy $ARG1$",
    "check_flexlm": "check_flexlm -F $ARG1$",
    "check_fping": "check_fping -H $HOSTADDRESS$ -w $ARG1$ -c $ARG2$",
    "check_game": "check_game -H $HOSTADDRESS$ -G $ARG1$",
    "check_hpjd": "check_hpjd -H $HOSTADDRESS$",
    "check_http": "check_http -H $HOSTADDRESS$",
    "check_ide_smart": "check_ide_smart -d $ARG1$",
    "check_icmp": "check_icmp -H $HOSTADDRESS$ -w $ARG1$ -c $ARG2$",
    # -k/-d/-T are mutually exclusive ("one of three" required) — -k
    # (interface index) chosen as the representative default; an
    # admin checking by description/type instead should override.
    "check_ifoperstatus": "check_ifoperstatus -H $HOSTADDRESS$ -k $ARG1$",
    "check_ifstatus": "check_ifstatus -H $HOSTADDRESS$",
    "check_ircd": "check_ircd -H $HOSTADDRESS$",
    "check_ldap": "check_ldap -H $HOSTADDRESS$ -b $ARG1$",
    "check_ldaps": "check_ldaps -H $HOSTADDRESS$ -b $ARG1$",
    "check_load": "check_load -w $ARG1$ -c $ARG2$",
    "check_log": "check_log -F $ARG1$ -O $ARG2$ -q $ARG3$",
    "check_mailq": "check_mailq -w $ARG1$ -c $ARG2$",
    "check_mrtg": "check_mrtg -F $ARG1$ -w $ARG2$ -c $ARG3$ -e $ARG4$ -a $ARG5$ -v $ARG6$",
    "check_mrtgtraf": "check_mrtgtraf -F $ARG1$ -w $ARG2$ -c $ARG3$ -e $ARG4$ -a $ARG5$",
    "check_mysql": "check_mysql -H $HOSTADDRESS$",
    "check_mysql_query": "check_mysql_query -H $HOSTADDRESS$ -q $ARG1$ -w $ARG2$ -c $ARG3$",
    "check_ncpa": "check_ncpa -H $HOSTADDRESS$ -t $ARG1$ -M $ARG2$",
    "check_nagios": "check_nagios -F $ARG1$ -e $ARG2$ -C $ARG3$",
    "check_nt": "check_nt -H $HOSTADDRESS$ -v $ARG1$",
    # Both the deprecated C build and the Perl replacement are
    # installed as the same "check_ntp" filename — one entry covers
    # both, since only one is ever actually on disk at a time.
    "check_ntp": "check_ntp -H $HOSTADDRESS$",
    "check_ntp_peer": "check_ntp_peer -H $HOSTADDRESS$",
    "check_ntp_time": "check_ntp_time -H $HOSTADDRESS$",
    "check_nwstat": "check_nwstat -H $HOSTADDRESS$ -v $ARG1$",
    "check_overcr": "check_overcr -H $HOSTADDRESS$ -v $ARG1$",
    # check_oracle uses positional mode-selection flags (--tns/--db/
    # --login/etc.), a fundamentally different structure from every
    # other plugin here — deliberately left bare; needs a manual
    # override matching whichever mode is actually wanted.
    "check_oracle": "check_oracle",
    "check_pgsql": "check_pgsql -H $HOSTADDRESS$",
    "check_ping": "check_ping -H $HOSTADDRESS$ -w $ARG1$ -c $ARG2$",
    "check_procs": "check_procs -w $ARG1$ -c $ARG2$",
    "check_radius": "check_radius -H $HOSTADDRESS$ -u $ARG1$ -p $ARG2$ -F $ARG3$",
    "check_real": "check_real -H $HOSTADDRESS$ -u $ARG1$",
    "check_rpc": "check_rpc -H $HOSTADDRESS$ -C $ARG1$",
    "check_sensors": "check_sensors",
    "check_smtp": "check_smtp -H $HOSTADDRESS$",
    "check_snmp": "check_snmp -H $HOSTADDRESS$ -o $ARG1$",
    "check_ssl_validity": "check_ssl_validity -H $HOSTADDRESS$",
    "check_ssh": "check_ssh -H $HOSTADDRESS$",
    "check_swap": "check_swap -w $ARG1$ -c $ARG2$",
    "check_tcp": "check_tcp -H $HOSTADDRESS$ -p $ARG1$",
    "check_time": "check_time -H $HOSTADDRESS$",
    "check_ups": "check_ups -H $HOSTADDRESS$ -u $ARG1$",
    "check_uptime": "check_uptime",
    "check_users": "check_users -w $ARG1$ -c $ARG2$",
    "check_wave": "check_wave -H $HOSTADDRESS$ -w $ARG1$ -c $ARG2$",
    "check_file_age": "check_file_age -f $ARG1$",
}


def get_default_command(plugin_name):
    """
    Returns the hand-curated default command line for a known baseline
    plugin, or None if the name isn't in the catalog (custom/
    non-standard executables) — callers should fall back to the
    generic "<name> -H $HOSTADDRESS$" default in that case.
    """
    return PLUGIN_COMMAND_DEFAULTS.get(plugin_name)
