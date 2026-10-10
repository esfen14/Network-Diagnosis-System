"""add password reset request

Revision ID: c8d2f5a1b693
Revises: b4e8d1a7c629
Create Date: 2026-10-08 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c8d2f5a1b693'
down_revision = 'b4e8d1a7c629'
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_():
    op.create_table(
        'PASSWORD_RESET_REQUEST',
        sa.Column('RequestID', sa.Integer(), nullable=False),
        sa.Column('UserID', sa.Integer(), nullable=False),
        sa.Column('Status', sa.String(length=10), server_default='Pending', nullable=False),
        sa.Column('Requested_At', sa.DateTime(), nullable=False),
        sa.Column('Resolved_At', sa.DateTime(), nullable=True),
        sa.Column('Resolved_By', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['UserID'], ['USER.UserID'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['Resolved_By'], ['USER.UserID'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('RequestID'),
    )
    with op.batch_alter_table('PASSWORD_RESET_REQUEST', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_PASSWORD_RESET_REQUEST_UserID'), ['UserID'], unique=False)
        batch_op.create_index(batch_op.f('ix_PASSWORD_RESET_REQUEST_Status'), ['Status'], unique=False)


def downgrade_():
    with op.batch_alter_table('PASSWORD_RESET_REQUEST', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_PASSWORD_RESET_REQUEST_Status'))
        batch_op.drop_index(batch_op.f('ix_PASSWORD_RESET_REQUEST_UserID'))
    op.drop_table('PASSWORD_RESET_REQUEST')


def upgrade_history():
    pass


def downgrade_history():
    pass
