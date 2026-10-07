"""
Runs the custom check origin migration (b4e8d1a7c629) against throwaway databases and prints a
JSON report. Not a test itself: it is launched in a subprocess by test_custom_check_migration.py
because Alembic needs a Flask app configured for temporary databases before "app" is imported.

Usage (from server/): python tests/support/custom_check_migration_runner.py
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

BEFORE = "f3a8c1d6b2e9"
TARGET = "b4e8d1a7c629"
report = {}


def upgrade(revision=TARGET):
    with app.app_context():
        flask_migrate.upgrade(directory="migrations", revision=revision)


def downgrade(revision=BEFORE):
    with app.app_context():
        flask_migrate.downgrade(directory="migrations", revision=revision)


def add_config(conn, config_id, service, origin):
    conn.execute(
        "insert into PLUGIN_CONFIGURATION (PluginConfigurationID, Nagios_Service_Name, Origin, Status, Created_At, "
        "Updated_At, PluginID, NetDiscoveryID) values (?,?,?,'APPLIED','2026-01-01','2026-01-01',1,1)",
        (config_id, service, origin))


def origins(conn):
    return conn.execute("select Origin from PLUGIN_CONFIGURATION order by PluginConfigurationID").fetchall()


upgrade(BEFORE)
c = sqlite3.connect(sysdb)
c.execute("insert into ACTIVITY_LOG (LogID, Action_Type, Performed_At, UserID) values (1,'t','2026-01-01',1)")
c.execute("insert into NETWORK_DISCOVERY_STATUS (DiscoveryStatusID, Status, Progress, Message, Start_At, LogID) "
          "values (1,'SUCCESS',100,'ok','2026-01-01',1)")
c.execute("insert into NETWORK_DISCOVERY (NetDiscoveryID, Hostname, IP_Address, Network, NCPA_Eligible, Scanned_At, "
          "Include_Device_In_Scanning, DiscoveryStatusID) values (1,'web','10.0.0.1','10.0.0.0/24',1,'2026-01-02',1,1)")
c.execute("insert into PLUGIN (PluginID, Name, Plugin_Type, Source, Status, Created_At, Updated_At) "
          "values (1,'check_ups','NAGIOS','BASELINE_ISO','READY','2026-01-01','2026-01-01')")
add_config(c, 1, "ssh-22-tcp", "AUTO")
add_config(c, 2, "legacy", "MANUAL")
c.commit()
c.close()

upgrade()
c = sqlite3.connect(sysdb)
report["version"] = c.execute("select version_num from alembic_version").fetchall()
report["origins_after_upgrade"] = origins(c)
add_config(c, 3, "custom-ups-rack", "CUSTOM")
c.commit()
report["origins_with_custom"] = origins(c)
report["unique_constraint_kept"] = False
try:
    add_config(c, 4, "custom-ups-rack", "CUSTOM")
except sqlite3.IntegrityError:
    report["unique_constraint_kept"] = True
c.close()

downgrade()
c = sqlite3.connect(sysdb)
report["origins_after_downgrade"] = origins(c)
report["version_after_downgrade"] = c.execute("select version_num from alembic_version").fetchall()
c.close()

upgrade()
c = sqlite3.connect(sysdb)
report["origins_after_reupgrade"] = origins(c)
report["version_after_reupgrade"] = c.execute("select version_num from alembic_version").fetchall()
c.close()

print("REPORT_BEGIN")
print(json.dumps(report))
print("REPORT_END")
