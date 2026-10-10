"""add system-wide Nagios check interval

Revision ID: a6f4d2c8e190
Revises: d3a9e6b2f741
"""
from alembic import op
import sqlalchemy as sa

revision = 'a6f4d2c8e190'
down_revision = 'd3a9e6b2f741'
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_():
    with op.batch_alter_table('SYSTEM_SETTINGS') as batch_op:
        batch_op.add_column(sa.Column('Check_Interval', sa.Integer(), nullable=False, server_default='5'))


def downgrade_():
    with op.batch_alter_table('SYSTEM_SETTINGS') as batch_op:
        batch_op.drop_column('Check_Interval')


def upgrade_history():
    pass


def downgrade_history():
    pass
