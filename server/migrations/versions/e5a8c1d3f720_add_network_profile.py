"""add network profile

Revision ID: e5a8c1d3f720
Revises: d41f7a2b9e10
Create Date: 2026-10-05 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e5a8c1d3f720'
down_revision = 'd41f7a2b9e10'
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_():
    op.create_table('NETWORK_PROFILE',
    sa.Column('Id', sa.Integer(), nullable=False),
    sa.Column('Name', sa.String(length=100), nullable=False),
    sa.Column('Reference', sa.String(length=50), nullable=True),
    sa.Column('Details', sa.JSON(), nullable=True),
    sa.Column('Updated_At', sa.DateTime(), nullable=False),
    sa.Column('Updated_By', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['Updated_By'], ['USER.UserID'], ),
    sa.PrimaryKeyConstraint('Id')
    )
    with op.batch_alter_table('NETWORK_PROFILE', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_NETWORK_PROFILE_Updated_By'), ['Updated_By'], unique=False)


def downgrade_():
    with op.batch_alter_table('NETWORK_PROFILE', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_NETWORK_PROFILE_Updated_By'))

    op.drop_table('NETWORK_PROFILE')


def upgrade_history():
    pass


def downgrade_history():
    pass
