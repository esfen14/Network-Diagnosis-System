"""
Runs the NCPA deployment results migration (e5c1a9d3f7b2) against throwaway
databases and prints a JSON report. Not a test itself: it is launched in a
subprocess by test_ncpa_results_migration.py because Alembic needs a Flask
app configured for temporary databases before "app" is imported.

Usage (from server/): python tests/support/ncpa_results_migration_runner.py
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

BEFORE = "d41f7a2b9e10"
TARGET = "e5c1a9d3f7b2"
report = {}


def columns(conn, table):
    return [row[1] for row in conn.execute(f"pragma table_info({table})")]


def tables(conn):
    return sorted(row[0] for row in conn.execute("select name from sqlite_master where type='table'"))


with app.app_context():
    flask_migrate.upgrade(directory="migrations", revision=BEFORE)

# A run that exists before the migration must survive it.
c = sqlite3.connect(sysdb)
c.execute("insert into ACTIVITY_LOG (LogID, Action_Type, Performed_At, UserID) values (1,'t','2026-01-01',1)")
c.execute("insert into NCPA_DEPLOYMENT_STATUS (NCPADeployStatusID, Status, Progress, Message, Start_At, LogID) "
          "values (1,'SUCCESS',100,'ok','2026-01-01',1)")
c.commit()
c.close()

with app.app_context():
    flask_migrate.upgrade(directory="migrations", revision=TARGET)

c = sqlite3.connect(sysdb)
report["version"] = c.execute("select version_num from alembic_version").fetchall()
report["result_columns"] = columns(c, "NCPA_DEPLOYMENT_RESULT")
report["status_columns"] = columns(c, "NCPA_DEPLOYMENT_STATUS")
report["existing_run"] = c.execute(
    "select NCPADeployStatusID, Status, Reviewed_At, Reviewed_By from NCPA_DEPLOYMENT_STATUS").fetchall()
report["result_indexes"] = sorted(row[1] for row in c.execute("pragma index_list(NCPA_DEPLOYMENT_RESULT)"))
c.close()

with app.app_context():
    flask_migrate.downgrade(directory="migrations", revision=BEFORE)
c = sqlite3.connect(sysdb)
report["tables_after_downgrade"] = tables(c)
report["status_columns_after_downgrade"] = columns(c, "NCPA_DEPLOYMENT_STATUS")
report["run_after_downgrade"] = c.execute("select NCPADeployStatusID, Status from NCPA_DEPLOYMENT_STATUS").fetchall()
c.close()

with app.app_context():
    flask_migrate.upgrade(directory="migrations", revision=TARGET)
c = sqlite3.connect(sysdb)
report["version_after_reupgrade"] = c.execute("select version_num from alembic_version").fetchall()
c.close()

print("REPORT_BEGIN")
print(json.dumps(report))
print("REPORT_END")
