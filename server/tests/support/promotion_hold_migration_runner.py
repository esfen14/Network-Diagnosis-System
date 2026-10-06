"""
Runs the port promotion hold migration (e9b4c2f7a105) against throwaway databases and prints a
JSON report. Not a test itself: it is launched in a subprocess by
test_promotion_hold_migration.py because Alembic needs a Flask app configured for temporary
databases before "app" is imported.

Usage (from server/): python tests/support/promotion_hold_migration_runner.py
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

BEFORE = "d2f6a1c8e507"
TARGET = "e9b4c2f7a105"
report = {}


def upgrade(revision=TARGET):
    with app.app_context():
        flask_migrate.upgrade(directory="migrations", revision=revision)


def downgrade(revision=BEFORE):
    with app.app_context():
        flask_migrate.downgrade(directory="migrations", revision=revision)


def columns(conn, table):
    return [row[1] for row in conn.execute(f"pragma table_info({table})")]


def held(conn):
    tcp = [["tcp", r[0]] for r in conn.execute("select Port_Number from OPEN_TCP_Services where Promotion_Held = 1 order by 1")]
    udp = [["udp", r[0]] for r in conn.execute("select Port_Number from OPEN_UDP_Services where Promotion_Held = 1 order by 1")]
    return tcp + udp


upgrade(BEFORE)
c = sqlite3.connect(sysdb)
c.execute("insert into ACTIVITY_LOG (LogID, Action_Type, Performed_At, UserID) values (1,'t','2026-01-01',1)")
c.execute("insert into NETWORK_DISCOVERY_STATUS (DiscoveryStatusID, Status, Progress, Message, Start_At, LogID) "
          "values (1,'SUCCESS',100,'ok','2026-01-01',1)")
c.execute("insert into NETWORK_DISCOVERY (NetDiscoveryID, Hostname, IP_Address, Network, NCPA_Eligible, Scanned_At, "
          "Include_Device_In_Scanning, DiscoveryStatusID) values (1,'web','10.0.0.1','10.0.0.0/24',1,'2026-01-02',1,1)")

for plugin_id, (name, state) in enumerate([
    ("check_ssh", "ENABLED"), ("check_http", "ACTIVE"), ("check_tcp", "ENABLED"), ("check_mysql", "READY"),
    ("check_dns", "ENABLED"), ("check_snmp", "DISABLED"),
], start=1):
    c.execute("insert into PLUGIN (PluginID, Name, Plugin_Type, Source, Status, Created_At, Updated_At) "
              "values (?,?,'NAGIOS','BASELINE_ISO',?,'2026-01-01','2026-01-01')", (plugin_id, name, state))

# (table, port, service, state, identified by, expected service, acknowledged)
ports = [
    ("OPEN_TCP_Services", 22, "ssh", "SUGGESTED", "FINGERPRINT", None, None),        # check_ssh enabled          -> held
    ("OPEN_TCP_Services", 80, "http", "SUGGESTED", "USER", None, None),              # pinned, check_http active  -> held
    ("OPEN_TCP_Services", 9100, "printer", "SUGGESTED", "PORT_RULE", None, None),    # generic, check_tcp enabled -> held
    ("OPEN_TCP_Services", 3306, "mysql", "SUGGESTED", "FINGERPRINT", None, None),    # check_mysql never enabled  -> free
    ("OPEN_TCP_Services", 8080, "http-proxy", "SUGGESTED", "PORT_HINT", None, None), # only a guess               -> free
    ("OPEN_TCP_Services", 443, "https", "SUGGESTED", "FINGERPRINT", "http", None),   # flagged, unacknowledged    -> free
    ("OPEN_TCP_Services", 8443, "https", "SUGGESTED", "FINGERPRINT", "http", "2026-02-01"),  # acknowledged       -> held
    ("OPEN_TCP_Services", 5000, "upnp", "MONITORED", "FINGERPRINT", None, None),     # already monitored          -> free
    ("OPEN_TCP_Services", 2222, "ssh", "IGNORED", "FINGERPRINT", None, None),        # ignored                    -> free
    ("OPEN_TCP_Services", 2223, "ssh", "ARCHIVED", "FINGERPRINT", None, None),       # archived                   -> free
    ("OPEN_UDP_Services", 53, "dns", "SUGGESTED", "FINGERPRINT", None, None),        # check_dns enabled          -> held
    ("OPEN_UDP_Services", 5353, "domain", "SUGGESTED", "FINGERPRINT", None, None),   # an alias of dns            -> held
    ("OPEN_UDP_Services", 9999, "mystery", "SUGGESTED", "FINGERPRINT", None, None),  # no UDP plugin speaks it    -> free
    ("OPEN_UDP_Services", 161, "snmp", "SUGGESTED", "FINGERPRINT", None, None),      # check_snmp is disabled     -> free
]
for table, number, service, state, identified, expected, acknowledged in ports:
    c.execute(
        f"insert into {table} (Port_Number, Service_Name, Port_State, Source, Identified_By, Expected_Service_Name, "
        "Mismatch_Acknowledged_At, Missed_Scans, NetDiscoveryID) values (?,?,?,'SCAN',?,?,?,0,1)",
        (number, service, state, identified, expected, acknowledged))
c.commit()
c.close()

upgrade()
c = sqlite3.connect(sysdb)
report["version"] = c.execute("select version_num from alembic_version").fetchall()
report["columns"] = {t: "Promotion_Held" in columns(c, t) for t in ("OPEN_TCP_Services", "OPEN_UDP_Services")}
report["held"] = held(c)
report["states"] = c.execute("select count(*) from OPEN_TCP_Services where Port_State = 'SUGGESTED'").fetchall()
c.close()

downgrade()
c = sqlite3.connect(sysdb)
report["columns_after_downgrade"] = {t: "Promotion_Held" in columns(c, t) for t in ("OPEN_TCP_Services", "OPEN_UDP_Services")}
report["ports_after_downgrade"] = c.execute("select count(*) from OPEN_TCP_Services").fetchall()
c.execute("update PLUGIN set Status = 'READY'")        # nothing enabled: a fresh-style install
c.commit()
c.close()

upgrade()
c = sqlite3.connect(sysdb)
report["held_when_nothing_is_enabled"] = held(c)
report["version_after_reupgrade"] = c.execute("select version_num from alembic_version").fetchall()
c.close()

print("REPORT_BEGIN")
print(json.dumps(report))
print("REPORT_END")
