"""merge heads

Revision ID: 3b2c40f55ffe
Revises: 7c1c38a2c2be, ec429f135306
Create Date: 2026-08-18 11:57:15.491300

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3b2c40f55ffe'
down_revision = ('7c1c38a2c2be', 'ec429f135306')
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

