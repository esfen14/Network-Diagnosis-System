"""add NetworkDiscovery.Plugin_Variables and ServiceStatus.Check_Command

Revision ID: 7b3f2a9c41d8
Revises: e47789ff90f3
Create Date: 2026-09-26 12:00:00.000000

- system.db: NETWORK_DISCOVERY.Plugin_Variables — per-host plugin
  variable overrides consumed by network_discovery/plugin_registry.py.
- history.db: SERVICE_STATUS.Check_Command — the Nagios command name
  reported by statusjson.cgi, used by statistics._plugin_key() to link a
  service to its plugin without parsing the service name.

Hand-written against this chain's head (e47789ff90f3) for the same
reason given in that migration: `flask db migrate` refuses to run while
the repo's two independent migration chains coexist.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7b3f2a9c41d8'
down_revision = 'e47789ff90f3'
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_():
    with op.batch_alter_table('NETWORK_DISCOVERY', schema=None) as batch_op:
        batch_op.add_column(sa.Column('Plugin_Variables', sa.JSON(), nullable=True))


def downgrade_():
    with op.batch_alter_table('NETWORK_DISCOVERY', schema=None) as batch_op:
        batch_op.drop_column('Plugin_Variables')


def upgrade_history():
    with op.batch_alter_table('SERVICE_STATUS', schema=None) as batch_op:
        batch_op.add_column(sa.Column('Check_Command', sa.String(length=100), nullable=True))


def downgrade_history():
    with op.batch_alter_table('SERVICE_STATUS', schema=None) as batch_op:
        batch_op.drop_column('Check_Command')
