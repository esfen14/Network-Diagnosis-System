"""
Runs the plugin.configure retirement migration (d2f6a1c8e507) against throwaway
databases and prints a JSON report. Not a test itself: it is launched in a
subprocess by test_retire_permission_migration.py because Alembic needs a Flask
app configured for temporary databases before "app" is imported.

Usage (from server/): python tests/support/retire_permission_migration_runner.py
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

import config  # noqa: E402

config.Config.SQLALCHEMY_BINDS = {"history": "sqlite:///" + histdb}

import flask_migrate  # noqa: E402
from app import app  # noqa: E402

BEFORE = "b9d5f2a7c3e4"
TARGET = "d2f6a1c8e507"
report = {}


def permissions(conn):
    return sorted(row[0] for row in conn.execute("select Name from PERMISSION"))


def grants(conn):
    return sorted(conn.execute(
        "select ROLE.Name, PERMISSION.Name from ROLE_PERMISSION "
        "join ROLE on ROLE.RoleID = ROLE_PERMISSION.RoleID "
        "join PERMISSION on PERMISSION.PermissionID = ROLE_PERMISSION.PermissionID").fetchall())


with app.app_context():
    flask_migrate.upgrade(directory="migrations", revision=BEFORE)

c = sqlite3.connect(sysdb)
for permission_id, name in enumerate(["plugin.enable", "plugin.disable", "plugin.configure"], start=1):
    c.execute("insert into PERMISSION (PermissionID, Name, Description) values (?,?,?)", (permission_id, name, name))
for role_id, name in ((1, "Administrator"), (2, "Staff")):
    c.execute("insert into ROLE (RoleID, Name, Is_Active, Created_At) values (?,?,1,'2026-01-01')", (role_id, name))
for role_id, permission_id in ((1, 1), (1, 2), (1, 3), (2, 3)):
    c.execute("insert into ROLE_PERMISSION (RoleID, PermissionID) values (?,?)", (role_id, permission_id))
c.commit()
report["permissions_before"] = permissions(c)
c.close()

with app.app_context():
    flask_migrate.upgrade(directory="migrations", revision=TARGET)
c = sqlite3.connect(sysdb)
report["version"] = c.execute("select version_num from alembic_version").fetchall()
report["permissions_after"] = permissions(c)
report["grants_after"] = grants(c)
c.close()

with app.app_context():
    flask_migrate.downgrade(directory="migrations", revision=BEFORE)
c = sqlite3.connect(sysdb)
report["permissions_after_downgrade"] = permissions(c)
report["grants_after_downgrade"] = grants(c)
c.close()

with app.app_context():
    flask_migrate.upgrade(directory="migrations", revision=TARGET)
c = sqlite3.connect(sysdb)
report["permissions_after_reupgrade"] = permissions(c)
report["version_after_reupgrade"] = c.execute("select version_num from alembic_version").fetchall()
c.close()

print("REPORT_BEGIN")
print(json.dumps(report))
print("REPORT_END")
