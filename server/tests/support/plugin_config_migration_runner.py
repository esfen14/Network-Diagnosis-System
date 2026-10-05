"""
Runs the plugin configuration service columns migration (a8c4e1f6b2d3)
against throwaway databases and prints a JSON report. Not a test itself: it is
launched in a subprocess by test_plugin_config_migration.py because Alembic
needs a Flask app configured for temporary databases before "app" is imported.

Usage (from server/): python tests/support/plugin_config_migration_runner.py
"""
import json
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.getcwd())

tmp = tempfile.mkdtemp()
sysdb = os.path.join(tmp, "sys.db").replace("\\", "/")
histdb = os.path.join(tmp, "hist.db").replace("\\", "/")
os.environ["DATABASE_URL"] = "sqlite:///" + sysdb
os.environ["SECRET_KEY"] = "x"
os.environ["PINPOINT_DOMAIN"] = "test.local"

import config  # noqa: E402

config.Config.SQLALCHEMY_BINDS = {"history": "sqlite:///" + histdb}

import flask_migrate  # noqa: E402
from app import app  # noqa: E402

BEFORE = "c7e3a9d1b5f2"
TARGET = "a8c4e1f6b2d3"
report = {}


def columns(conn, table):
    return [row[1] for row in conn.execute(f"pragma table_info({table})")]


def plugin_states(conn):
    return dict(conn.execute("select Name, Status from PLUGIN").fetchall())


with app.app_context():
    flask_migrate.upgrade(directory="migrations", revision=BEFORE)

c = sqlite3.connect(sysdb)
c.execute("insert into ACTIVITY_LOG (LogID, Action_Type, Performed_At, UserID) values (1,'t','2026-01-01',1)")
c.execute("insert into NETWORK_DISCOVERY_STATUS (DiscoveryStatusID, Status, Progress, Message, Start_At, LogID) "
          "values (1,'SUCCESS',100,'ok','2026-01-01',1)")
c.execute("insert into NETWORK_DISCOVERY (NetDiscoveryID, Hostname, IP_Address, Network, NCPA_Eligible, "
          "Scanned_At, Include_Device_In_Scanning, DiscoveryStatusID) "
          "values (1,'web.test.local','10.0.0.1','10.0.0.0/24',1,'2026-01-02',1,1)")

plugins = [
    ("check_ssh", "READY"), ("check_http", "DISABLED"), ("check_tcp", "INSTALLED"),
    ("check_snmp", "READY"), ("check_mysql", "VALIDATION_FAILED"), ("check_ftp", "READY"),
    ("check_dns", "READY"), ("check_udp", "READY"), ("check_ntp_time", "ACTIVE"),
]
for plugin_id, (name, status) in enumerate(plugins, start=1):
    c.execute("insert into PLUGIN (PluginID, Name, Plugin_Type, Source, Status, Created_At, Updated_At) "
              "values (?,?,'NAGIOS','BASELINE_ISO',?,'2026-01-01','2026-01-01')", (plugin_id, name, status))

# (table, port, service, plugin_name, state)
ports = [
    ("OPEN_TCP_Services", 22, "ssh", "ssh", "MONITORED"),
    ("OPEN_TCP_Services", 443, "https", None, "MONITORED"),
    ("OPEN_TCP_Services", 3306, "mysql", "mysql", "MONITORED"),
    ("OPEN_TCP_Services", 21, "ftp", "ftp", "SUGGESTED"),
    ("OPEN_TCP_Services", 9100, "printer", None, "MISSING"),
    ("OPEN_UDP_Services", 53, "dns", "dns", "MONITORED"),
    ("OPEN_UDP_Services", 9999, "mystery", None, "MONITORED"),
]
for table, port, service, plugin_name, state in ports:
    c.execute(f"insert into {table} (Port_Number, Service_Name, Plugin_Name, Port_State, Source, Missed_Scans, "
              "NetDiscoveryID) values (?,?,?,?,'SCAN',0,1)", (port, service, plugin_name, state))

# A manual configuration that was applied and one that is still pending.
c.execute("insert into PLUGIN_CONFIGURATION (PluginConfigurationID, Service_Description, Status, Created_At, "
          "Updated_At, PluginID, NetDiscoveryID) values (1,'Web ping','APPLIED','2026-02-01','2026-03-01',3,1)")
c.execute("insert into PLUGIN_CONFIGURATION (PluginConfigurationID, Service_Description, Status, Created_At, "
          "Updated_At, PluginID, NetDiscoveryID) values (2,'Pending','PENDING','2026-02-01','2026-03-02',3,1)")
c.commit()
c.close()

with app.app_context():
    flask_migrate.upgrade(directory="migrations", revision=TARGET)

c = sqlite3.connect(sysdb)
report["version"] = c.execute("select version_num from alembic_version").fetchall()
report["config_columns"] = columns(c, "PLUGIN_CONFIGURATION")
report["configs"] = c.execute(
    "select PluginConfigurationID, Origin, Applied_At, Nagios_Service_Name from PLUGIN_CONFIGURATION "
    "order by PluginConfigurationID").fetchall()
report["states_after"] = plugin_states(c)

# Two derived rows for the same service on one device are refused.
insert_named = ("insert into PLUGIN_CONFIGURATION (Status, Created_At, Updated_At, PluginID, NetDiscoveryID, "
                "Nagios_Service_Name, Origin) values ('APPLIED','2026-04-01','2026-04-01',1,1,'ssh-22-tcp','AUTO')")
c.execute(insert_named)
try:
    c.execute(insert_named)
    report["duplicate_refused"] = False
except sqlite3.IntegrityError:
    report["duplicate_refused"] = True
c.rollback()

# Rows without a service name (legacy manual rows) are not compared.
insert_unnamed = ("insert into PLUGIN_CONFIGURATION (Status, Created_At, Updated_At, PluginID, NetDiscoveryID) "
                  "values ('PENDING','2026-04-01','2026-04-01',1,1)")
c.execute(insert_unnamed)
try:
    c.execute(insert_unnamed)
    report["null_names_allowed"] = True
except sqlite3.IntegrityError:
    report["null_names_allowed"] = False
c.rollback()
c.close()

with app.app_context():
    flask_migrate.downgrade(directory="migrations", revision=BEFORE)
c = sqlite3.connect(sysdb)
report["config_columns_after_downgrade"] = columns(c, "PLUGIN_CONFIGURATION")
report["configs_after_downgrade"] = c.execute("select PluginConfigurationID from PLUGIN_CONFIGURATION").fetchall()
c.close()

with app.app_context():
    flask_migrate.upgrade(directory="migrations", revision=TARGET)
c = sqlite3.connect(sysdb)
report["version_after_reupgrade"] = c.execute("select version_num from alembic_version").fetchall()
c.close()

print("REPORT_BEGIN")
print(json.dumps(report))
print("REPORT_END")
