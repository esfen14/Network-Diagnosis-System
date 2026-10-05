"""merge service identification and NCPA deployment results

e5a9c3d7f210 (service identification) and e5c1a9d3f7b2 (NCPA deployment
results and review) were written on separate branches and both revise
d41f7a2b9e10, which left two heads; "flask db upgrade" refuses to run with
more than one. This revision joins them so the history has a single head
again. It changes no schema, so a database that already has either branch
applied upgrades cleanly.

Revision ID: f3b7d2e8a614
Revises: e5a9c3d7f210, e5c1a9d3f7b2
Create Date: 2026-10-05 01:00:00.000000

"""


# revision identifiers, used by Alembic.
revision = 'f3b7d2e8a614'
down_revision = ('e5a9c3d7f210', 'e5c1a9d3f7b2')
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
