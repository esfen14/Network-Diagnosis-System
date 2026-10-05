"""add user must change password

Revision ID: f2b9d6a4c871
Revises: e5a8c1d3f720
Create Date: 2026-10-05 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f2b9d6a4c871'
down_revision = 'e5a8c1d3f720'
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_():
    with op.batch_alter_table('USER', schema=None) as batch_op:
        batch_op.add_column(sa.Column('Must_Change_Password', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade_():
    with op.batch_alter_table('USER', schema=None) as batch_op:
        batch_op.drop_column('Must_Change_Password')


def upgrade_history():
    pass


def downgrade_history():
    pass
