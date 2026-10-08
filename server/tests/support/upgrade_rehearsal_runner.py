"""
Rehearses upgrading an installation to plugin-driven monitoring and prints a JSON report.
Not a test itself: it is launched in a subprocess by test_upgrade_rehearsal.py because
Alembic needs a Flask app configured for temporary databases before "app" is imported.

It builds a database as an install on main would have it (the revision just before this
branch's migrations), populated the way a real one is: discovered devices with monitored
and suggested ports, plugins in the states the old code left them (one applied to a host by
the old manual path), old discovery settings, and the plugin.configure permission granted to
a role. Then it upgrades to head, runs the first reconcile with Nagios mocked, downgrades,
and upgrades again.

Usage (from server/): python tests/support/upgrade_rehearsal_runner.py
"""
import json
import os
import sqlite3
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.getcwd())

tmp = tempfile.mkdtemp()
sysdb = os.path.join(tmp, "sys.db").replace("\\", "/")
histdb = os.path.join(tmp, "hist.db").replace("\\", "/")
os.environ["DATABASE_URL"] = "sqlite:///" + sysdb
os.environ["SECRET_KEY"] = "x"

import config  # noqa: E402

config.Config.SQLALCHEMY_BINDS = {"history": "sqlite:///" + histdb}

import flask_migrate  # noqa: E402
from app import app  # noqa: E402

# The head of main before the plugin-driven monitoring migrations were added.
BEFORE = "c7e3a9d1b5f2"
report = {}


def upgrade(revision="head"):
    with app.app_context():
        flask_migrate.upgrade(directory="migrations", revision=revision)


def downgrade(revision):
    with app.app_context():
        flask_migrate.downgrade(directory="migrations", revision=revision)


def rows(conn, sql, args=()):
    return [list(row) for row in conn.execute(sql, args).fetchall()]


def seed(conn):
    conn.execute("insert into ACTIVITY_LOG (LogID, Action_Type, Performed_At, UserID) values (1,'t','2026-01-01',1)")
    conn.execute("insert into NETWORK_DISCOVERY_STATUS (DiscoveryStatusID, Status, Progress, Message, Start_At, LogID) "
                 "values (1,'SUCCESS',100,'ok','2026-01-01',1)")
    for device_id, host, ip in ((1, "web-01", "10.0.0.11"), (2, "db-01", "10.0.0.12"), (3, "agent-01", "10.0.0.13")):
        conn.execute(
            "insert into NETWORK_DISCOVERY (NetDiscoveryID, Hostname, IP_Address, Network, NCPA_Eligible, Scanned_At, "
            "Include_Device_In_Scanning, DiscoveryStatusID, Nagios_Host_Name) values (?,?,?,?,1,'2026-01-02',1,1,?)",
            (device_id, host, ip, "10.0.0.0/24", host))

    # (table, device, port, service, frozen plugin, state)
    ports = [
        ("OPEN_TCP_Services", 1, 22, "ssh", "ssh", "MONITORED"),
        ("OPEN_TCP_Services", 1, 80, "http", "http", "MONITORED"),
        ("OPEN_TCP_Services", 1, 443, "https", "https", "MONITORED"),
        ("OPEN_TCP_Services", 1, 8080, "http-proxy", "tcp", "MONITORED"),        # monitored by the generic check
        ("OPEN_TCP_Services", 1, 3306, "mysql", None, "SUGGESTED"),              # never promoted
        ("OPEN_TCP_Services", 2, 22, "ssh", "ssh", "MONITORED"),
        ("OPEN_TCP_Services", 2, 9100, "printer", None, "SUGGESTED"),
        ("OPEN_TCP_Services", 2, 5666, "nrpe", "tcp", "MISSING"),                # still in Nagios as CRITICAL
        ("OPEN_TCP_Services", 3, 5693, "ncpa", "ncpa", "MONITORED"),
        ("OPEN_UDP_Services", 3, 161, "snmp", "snmp", "MONITORED"),
        ("OPEN_UDP_Services", 3, 53, "dns", "dns", "MONITORED"),
        ("OPEN_UDP_Services", 3, 9999, "mystery", None, "MONITORED"),            # no UDP plugin, discovery skips it
    ]
    for table, device, port, service, plugin, state in ports:
        conn.execute(
            f"insert into {table} (Port_Number, Service_Name, Plugin_Name, Port_State, Source, Identified_By, Missed_Scans, "
            "NetDiscoveryID) values (?,?,?,?,?,'FINGERPRINT',0,?)",
            (port, service, plugin, state, "NCPA" if port == 5693 else "SCAN", device))

    conn.execute("insert into NCPA_DEPLOYMENT (NCPADeployID, Token, Agent_Status, NetworkDiscoveryID) "
                 "values (1, ?, 'DEPLOYED', 3)", ("t" * 32,))

    # Plugin states as the old code left them: nothing is enabled, except check_ping, which the
    # old enable-applies-to-every-host feature had made Active with a manual applied configuration.
    plugins = [
        "check_ssh:READY", "check_http:DISABLED", "check_tcp:INSTALLED", "check_snmp:READY", "check_ncpa:READY",
        "check_dns:READY", "check_mysql:READY", "check_ping:ACTIVE", "check_load:READY", "check_disk:VALIDATION_FAILED",
    ]
    for plugin_id, entry in enumerate(plugins, start=1):
        name, state = entry.split(":")
        conn.execute("insert into PLUGIN (PluginID, Name, Plugin_Type, Source, Status, Created_At, Updated_At) "
                     "values (?,?,'NAGIOS','BASELINE_ISO',?,'2026-01-01','2026-01-01')", (plugin_id, name, state))
    conn.execute("insert into PLUGIN_CONFIGURATION (PluginConfigurationID, Service_Description, Status, Created_At, "
                 "Updated_At, PluginID, NetDiscoveryID) values (1,'check_ping','APPLIED','2026-02-01','2026-03-01',8,1)")

    conn.execute(
        "insert into DISCOVERY_SETTINGS (Id, Networks, TCP_Service_Overrides, UDP_Service_Overrides, "
        "TCP_Forced_Services, UDP_Forced_Services, Version, Updated_At) values (1,?,?,?,?,?,4,'2026-01-01')",
        (json.dumps(["10.0.0.0/24"]), json.dumps({"22": "ssh", "8080": "http-proxy"}), json.dumps({"161": "snmp"}),
         json.dumps({"5693": "ncpa", "9100": "printer"}), json.dumps({})))

    for permission_id, name in enumerate(["plugin.enable", "plugin.disable", "plugin.configure"], start=1):
        conn.execute("insert into PERMISSION (PermissionID, Name, Description) values (?,?,?)", (permission_id, name, name))
    conn.execute("insert into ROLE (RoleID, Name, Is_Active, Created_At) values (1,'Administrator',1,'2026-01-01')")
    for permission_id in (1, 2, 3):
        conn.execute("insert into ROLE_PERMISSION (RoleID, PermissionID) values (1, ?)", (permission_id,))
    conn.commit()


def snapshot(conn):
    config_columns = [r[1] for r in conn.execute("pragma table_info(PLUGIN_CONFIGURATION)")]
    origin = "Origin" if "Origin" in config_columns else "NULL"
    held = []
    for table, protocol in (("OPEN_TCP_Services", "tcp"), ("OPEN_UDP_Services", "udp")):
        if "Promotion_Held" in [r[1] for r in conn.execute(f"pragma table_info({table})")]:
            held += rows(conn, f"select '{protocol}', NetDiscoveryID, Port_Number from {table} where Promotion_Held = 1 order by 2, 3")
    return {
        "held": held,
        "version": rows(conn, "select version_num from alembic_version"),
        "plugins": dict(conn.execute("select Name, Status from PLUGIN").fetchall()),
        "permissions": sorted(r[0] for r in conn.execute("select Name from PERMISSION")),
        "grants": rows(conn, "select PermissionID from ROLE_PERMISSION order by 1"),
        "configs": rows(conn, f"select PluginConfigurationID, {origin}, Status, Service_Description from PLUGIN_CONFIGURATION"),
        "port_states": rows(
            conn, "select 'tcp', NetDiscoveryID, Port_Number, Port_State from OPEN_TCP_Services union all "
                  "select 'udp', NetDiscoveryID, Port_Number, Port_State from OPEN_UDP_Services order by 1, 2, 3"),
        "settings_columns": [r[1] for r in conn.execute("pragma table_info(DISCOVERY_SETTINGS)")],
    }


upgrade(BEFORE)
c = sqlite3.connect(sysdb)
seed(c)
report["before"] = snapshot(c)
c.close()

upgrade("head")
c = sqlite3.connect(sysdb)
report["after_upgrade"] = snapshot(c)
report["settings_after_upgrade"] = rows(c, "select Networks, TCP_Port_Services, UDP_Port_Services, Version from DISCOVERY_SETTINGS")
report["manual_applied_at"] = rows(c, "select Applied_At from PLUGIN_CONFIGURATION where PluginConfigurationID = 1")
c.close()

# The first reconcile after the upgrade (what the first scan, or enabling a plugin, triggers).
with app.app_context():
    from app.api.plugin.reconcile import reconcile_plugin_monitoring

    with patch("app.api.plugin.reconcile.regenerate_and_apply_config_status", return_value=("applied", "ok")):
        first = reconcile_plugin_monitoring(None)
        second = reconcile_plugin_monitoring(None)
report["first_reconcile"] = first
report["second_reconcile"] = second

c = sqlite3.connect(sysdb)
report["attached"] = rows(
    c, "select NetDiscoveryID, Nagios_Service_Name, Protocol, Port_Number from PLUGIN_CONFIGURATION "
       "where Origin = 'AUTO' order by NetDiscoveryID, Nagios_Service_Name")
report["after_reconcile"] = snapshot(c)
c.close()

downgrade(BEFORE)
c = sqlite3.connect(sysdb)
after_downgrade = snapshot(c)
after_downgrade["config_columns"] = [r[1] for r in c.execute("pragma table_info(PLUGIN_CONFIGURATION)")]
report["after_downgrade"] = after_downgrade
report["settings_after_downgrade"] = rows(c, "select TCP_Forced_Services, UDP_Forced_Services from DISCOVERY_SETTINGS")
c.close()

upgrade("head")
c = sqlite3.connect(sysdb)
report["after_reupgrade"] = snapshot(c)
c.close()

print("REPORT_BEGIN")
print(json.dumps(report))
print("REPORT_END")
