"""merge network profile and password change with the earlier history

f2b9d6a4c871 (network profile, then must-change-password) was written on main
from d41f7a2b9e10, while the plugin-driven monitoring branch carried
f3b7d2e8a614 (the merge of service identification and NCPA results). Both
descend from d41f7a2b9e10, which left two heads; "flask db upgrade" refuses to
run with more than one. This revision joins them. It changes no schema, so a
database that already has either branch applied upgrades cleanly.

Revision ID: c7e3a9d1b5f2
Revises: f3b7d2e8a614, f2b9d6a4c871
Create Date: 2026-10-05 20:30:00.000000

"""


# revision identifiers, used by Alembic.
revision = 'c7e3a9d1b5f2'
down_revision = ('f3b7d2e8a614', 'f2b9d6a4c871')
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_():
    pass


def downgrade_():
    pass


def upgrade_history():
    pass


def downgrade_history():
    pass
