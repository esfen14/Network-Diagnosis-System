"""add user receive email alerts

Revision ID: a4c8e1f6d392
Revises: d3a9e6b2f741
Create Date: 2026-10-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a4c8e1f6d392'
down_revision = 'd3a9e6b2f741'
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_():
    # server_default true: every existing user keeps receiving alerts.
    with op.batch_alter_table('USER', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('Receive_Email_Alerts', sa.Boolean(), server_default=sa.true(), nullable=False)
        )


def downgrade_():
    with op.batch_alter_table('USER', schema=None) as batch_op:
        batch_op.drop_column('Receive_Email_Alerts')


def upgrade_history():
    pass


def downgrade_history():
    pass
