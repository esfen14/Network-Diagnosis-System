"""
Runs the device-identity migration against throwaway databases and prints a
JSON report. Not a test itself (the name does not start with test_): it is
launched in a subprocess by test_device_migration.py because Alembic needs a
Flask app configured for temporary databases before "app" is imported.

Usage (from server/): python tests/support/migration_runner.py
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

BEFORE = "c3610bb0fc54"
# The revision this runner checks; later migrations have their own runners.
TARGET = "d41f7a2b9e10"
report = {}

with app.app_context():
    flask_migrate.upgrade(directory="migrations", revision=BEFORE)

# Rows as they look before the migration: a duplicate DNS name, an IP-derived
# name, an "Unknown" name, a randomized MAC, duplicate port rows, NCPA token.
c = sqlite3.connect(sysdb)
c.execute("insert into ACTIVITY_LOG (LogID, Action_Type, Performed_At, UserID) values (1,'t','2026-01-01',1)")
c.execute("insert into NETWORK_DISCOVERY_STATUS (DiscoveryStatusID, Status, Progress, Message, Start_At, LogID) "
          "values (1,'SUCCESS',100,'ok','2026-01-01',1)")
devices = [
    (1, "web.test.local", "10.0.0.1", "00:bb:cc:00:00:01"),
    (2, "web.test.local", "10.0.0.2", "02:bb:cc:00:00:02"),
    (3, "10.0.0.3.test.local", "10.0.0.3", None),
    (4, "Unknown", "10.0.0.4", "00:bb:cc:00:00:04"),
]
for device_id, hostname, ip, mac in devices:
    c.execute(
        "insert into NETWORK_DISCOVERY (NetDiscoveryID, Hostname, IP_Address, Network, MAC_Address, NCPA_Eligible, "
        "Scanned_At, Include_Device_In_Scanning, DiscoveryStatusID) values (?,?,?,?,?,1,'2026-01-02',1,1)",
        (device_id, hostname, ip, "10.0.0.0/24", mac))
c.execute("insert into SSH_CREDENTIALS (SSHID, SSH_Port, Key_Installed, Key_Fingerprint, NetworkDiscoveryID) "
          "values (1,22,0,'FPRINT1',1)")
c.execute("insert into NCPA_DEPLOYMENT (NCPADeployID, Token, NetworkDiscoveryID) values (1,'tok',1)")
for table in ("OPEN_TCP_Services", "OPEN_UDP_Services"):
    c.execute(f"insert into {table} (Port_Number, Service_Name, NetDiscoveryID) values (22,'ssh',1)")
    c.execute(f"insert into {table} (Port_Number, Service_Name, NetDiscoveryID) values (22,'ssh',1)")
c.execute("insert into OPEN_TCP_Services (Port_Number, Service_Name, NetDiscoveryID) values (5693,'ncpa',1)")
c.execute("insert into OPEN_TCP_Services (Port_Number, Service_Name, NetDiscoveryID) values (5693,'ncpa',2)")
c.commit()
c.close()

with app.app_context():
    flask_migrate.upgrade(directory="migrations", revision=TARGET)

c = sqlite3.connect(sysdb)
report["version"] = c.execute("select version_num from alembic_version").fetchall()
report["devices"] = c.execute(
    "select NetDiscoveryID, Nagios_Host_Name, Identity_Confidence, Device_State, Addressing, Missed_Scans, "
    "First_Seen_At from NETWORK_DISCOVERY order by 1").fetchall()
report["identifiers"] = c.execute(
    "select NetDiscoveryID, Kind, Value, Is_Strong from DEVICE_IDENTIFIER order by 1, 2").fetchall()
report["addresses"] = c.execute(
    "select NetDiscoveryID, IP_Address, Closed_At from DEVICE_ADDRESS_HISTORY order by 1").fetchall()
report["tcp"] = c.execute(
    "select NetDiscoveryID, Port_Number, Port_State, Source, Missed_Scans, Observed_Service_Name "
    "from OPEN_TCP_Services order by 1, 2").fetchall()
report["udp"] = c.execute("select NetDiscoveryID, Port_Number, Port_State from OPEN_UDP_Services").fetchall()

# The constraints really are enforced.
errors = {}
for name, sql in {
    "duplicate_host_name": "update NETWORK_DISCOVERY set Nagios_Host_Name = 'web.test.local' where NetDiscoveryID = 3",
    "duplicate_port": "insert into OPEN_TCP_Services (Port_Number, Service_Name, NetDiscoveryID) values (22,'ssh',1)",
    "duplicate_strong_identifier": "insert into DEVICE_IDENTIFIER (Kind, Value, Is_Strong, First_Seen_At, Last_Seen_At, "
                                   "NetDiscoveryID) values ('SSH_HOST_KEY','FPRINT1',1,'2026-01-01','2026-01-01',2)",
}.items():
    try:
        c.execute(sql)
        errors[name] = None
    except sqlite3.IntegrityError as exc:
        errors[name] = str(exc)
    c.rollback()
# A weak identifier may repeat.
c.execute("insert into DEVICE_IDENTIFIER (Kind, Value, Is_Strong, First_Seen_At, Last_Seen_At, NetDiscoveryID) "
          "values ('DNS_NAME','same.lan',0,'2026-01-01','2026-01-01',1)")
c.execute("insert into DEVICE_IDENTIFIER (Kind, Value, Is_Strong, First_Seen_At, Last_Seen_At, NetDiscoveryID) "
          "values ('DNS_NAME','same.lan',0,'2026-01-01','2026-01-01',2)")
c.rollback()
report["integrity_errors"] = errors
c.close()

# history.db is untouched apart from the revision stamp.
h = sqlite3.connect(histdb)
report["history_tables"] = sorted(r[0] for r in h.execute("select name from sqlite_master where type='table'"))
h.close()

with app.app_context():
    flask_migrate.downgrade(directory="migrations", revision=BEFORE)
c = sqlite3.connect(sysdb)
report["tables_after_downgrade"] = sorted(r[0] for r in c.execute("select name from sqlite_master where type='table'"))
report["device_columns_after_downgrade"] = [r[1] for r in c.execute("pragma table_info(NETWORK_DISCOVERY)")]
report["devices_after_downgrade"] = c.execute("select NetDiscoveryID, Hostname from NETWORK_DISCOVERY order by 1").fetchall()
c.close()

with app.app_context():
    flask_migrate.upgrade(directory="migrations", revision=TARGET)
c = sqlite3.connect(sysdb)
report["version_after_reupgrade"] = c.execute("select version_num from alembic_version").fetchall()
c.close()

print("REPORT_BEGIN")
print(json.dumps(report))
print("REPORT_END")
