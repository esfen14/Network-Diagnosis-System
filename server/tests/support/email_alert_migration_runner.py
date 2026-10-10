"""
Runs the email alert migration (a4c8e1f6d392) against throwaway databases and prints a JSON report.
Not a test itself: it is launched in a subprocess by test_email_alerts.py because Alembic needs a
Flask app configured for temporary databases before "app" is imported.

Usage (from server/): python tests/support/email_alert_migration_runner.py
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

BEFORE = "a6f4d2c8e190"
TARGET = "a4c8e1f6d392"
report = {}


def upgrade(revision=TARGET):
    with app.app_context():
        flask_migrate.upgrade(directory="migrations", revision=revision)


def downgrade(revision=BEFORE):
    with app.app_context():
        flask_migrate.downgrade(directory="migrations", revision=revision)


def add_user(conn, user_id, email, status):
    conn.execute(
        'insert into "USER" (UserID, First_Name, Last_Name, Email, Hashed_Password, Status, Must_Change_Password, '
        "Needs_Setup, Created_At, Updated_At, RoleID) values (?,?,?,?,'x',?,0,0,'2026-01-01','2026-01-01',1)",
        (user_id, "T", "U", email, status))


def alerts(conn):
    return conn.execute('select Email, Receive_Email_Alerts from "USER" order by UserID').fetchall()


def columns(conn):
    return [row[1] for row in conn.execute('pragma table_info("USER")')]


upgrade(BEFORE)
c = sqlite3.connect(sysdb)
c.execute("insert into ROLE (RoleID, Name, Is_Active, Description, Created_At) values (1,'Admin',1,'d','2026-01-01')")
add_user(c, 1, "active@example.com", "ACTIVE")
add_user(c, 2, "inactive@example.com", "INACTIVE")
c.commit()
report["column_before"] = "Receive_Email_Alerts" in columns(c)
c.close()

upgrade()
c = sqlite3.connect(sysdb)
report["version"] = c.execute("select version_num from alembic_version").fetchall()
report["alerts_after_upgrade"] = alerts(c)
# A user inserted without the column (older code, raw SQL) also defaults to on.
add_user(c, 3, "later@example.com", "ACTIVE")
c.commit()
report["alerts_with_new_user"] = alerts(c)
c.close()

downgrade()
c = sqlite3.connect(sysdb)
report["column_after_downgrade"] = "Receive_Email_Alerts" in columns(c)
report["users_after_downgrade"] = c.execute('select Email from "USER" order by UserID').fetchall()
report["version_after_downgrade"] = c.execute("select version_num from alembic_version").fetchall()
c.close()

upgrade()
c = sqlite3.connect(sysdb)
report["alerts_after_reupgrade"] = alerts(c)
c.close()

print("REPORT_BEGIN")
print(json.dumps(report))
print("REPORT_END")
