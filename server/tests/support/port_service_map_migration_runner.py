"""
Runs the Port -> Service map migration (b9d5f2a7c3e4) against throwaway
databases and prints a JSON report. Not a test itself: it is launched in a
subprocess by test_port_service_map_migration.py because Alembic needs a Flask
app configured for temporary databases before "app" is imported.

Usage (from server/): python tests/support/port_service_map_migration_runner.py
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

BEFORE = "a8c4e1f6b2d3"
TARGET = "b9d5f2a7c3e4"
report = {}


def columns(conn, table):
    return [row[1] for row in conn.execute(f"pragma table_info({table})")]


def settings_row(conn, names):
    row = conn.execute(f"select {', '.join(names)} from DISCOVERY_SETTINGS").fetchone()
    return [json.loads(value) if value is not None else None for value in row]


with app.app_context():
    flask_migrate.upgrade(directory="migrations", revision=BEFORE)

# Both old tables populated; port 22 is in both, and "always treat port as" must win.
c = sqlite3.connect(sysdb)
c.execute(
    "insert into DISCOVERY_SETTINGS (Id, Networks, TCP_Service_Overrides, UDP_Service_Overrides, "
    "TCP_Forced_Services, UDP_Forced_Services, Version, Updated_At) values (1, ?, ?, ?, ?, ?, 3, '2026-01-01')",
    (json.dumps(["10.0.0.0/24"]),
     json.dumps({"22": "ssh", "80": "http"}), json.dumps({"161": "snmp"}),
     json.dumps({"22": "sshd", "5693": "ncpa"}), json.dumps({})),
)
c.commit()
c.close()

with app.app_context():
    flask_migrate.upgrade(directory="migrations", revision=TARGET)

c = sqlite3.connect(sysdb)
report["version"] = c.execute("select version_num from alembic_version").fetchall()
report["settings_columns"] = columns(c, "DISCOVERY_SETTINGS")
report["tcp_port_services"], report["udp_port_services"] = settings_row(c, ["TCP_Port_Services", "UDP_Port_Services"])
report["settings_kept"] = c.execute("select Networks, Version from DISCOVERY_SETTINGS").fetchall()
report["port_columns"] = {t: columns(c, t) for t in ("OPEN_TCP_Services", "OPEN_UDP_Services")}
c.close()

with app.app_context():
    flask_migrate.downgrade(directory="migrations", revision=BEFORE)
c = sqlite3.connect(sysdb)
report["settings_columns_after_downgrade"] = columns(c, "DISCOVERY_SETTINGS")
report["forced_after_downgrade"], report["overrides_after_downgrade"] = settings_row(
    c, ["TCP_Forced_Services", "TCP_Service_Overrides"])
report["port_columns_after_downgrade"] = {t: columns(c, t) for t in ("OPEN_TCP_Services", "OPEN_UDP_Services")}
c.close()

with app.app_context():
    flask_migrate.upgrade(directory="migrations", revision=TARGET)
c = sqlite3.connect(sysdb)
report["version_after_reupgrade"] = c.execute("select version_num from alembic_version").fetchall()
report["tcp_after_reupgrade"] = settings_row(c, ["TCP_Port_Services"])[0]
c.close()

# Settings that were never saved stay unsaved (NULL), so config.py defaults still apply.
with app.app_context():
    flask_migrate.downgrade(directory="migrations", revision=BEFORE)
c = sqlite3.connect(sysdb)
c.execute("delete from DISCOVERY_SETTINGS")
c.execute("insert into DISCOVERY_SETTINGS (Id, Networks, Version, Updated_At) values (1, ?, 1, '2026-01-01')",
          (json.dumps(["10.0.0.0/24"]),))
c.commit()
c.close()
with app.app_context():
    flask_migrate.upgrade(directory="migrations", revision=TARGET)
c = sqlite3.connect(sysdb)
report["unsaved_tables"] = settings_row(c, ["TCP_Port_Services", "UDP_Port_Services"])
c.close()

print("REPORT_BEGIN")
print(json.dumps(report))
print("REPORT_END")
