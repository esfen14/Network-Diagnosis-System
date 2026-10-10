"""add user needs setup

Revision ID: d3a9e6b2f741
Revises: c8d2f5a1b693
Create Date: 2026-10-10 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd3a9e6b2f741'
down_revision = 'c8d2f5a1b693'
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_():
    with op.batch_alter_table('USER', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('Needs_Setup', sa.Boolean(), server_default=sa.false(), nullable=False)
        )


def downgrade_():
    with op.batch_alter_table('USER', schema=None) as batch_op:
        batch_op.drop_column('Needs_Setup')


def upgrade_history():
    pass


def downgrade_history():
    pass
