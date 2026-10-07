"""add the CUSTOM origin of a plugin configuration

A custom check is a PLUGIN_CONFIGURATION row an administrator added for a plugin
discovery cannot drive (spec files/Custom_Checks_Plan.md). It needs a third
Origin value so the reconciler, which owns AUTO rows, never touches it. No column
is added: the arguments live in Configuration_Data.

On SQLite the Origin column is a string, so the batch alter only widens the type;
PostgreSQL gets the new enum value. Downgrade deletes the CUSTOM rows (older code
would not know them) and restores the two-value type.

history.db is not touched.

Revision ID: b4e8d1a7c629
Revises: f3a8c1d6b2e9
Create Date: 2026-10-07 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4e8d1a7c629'
down_revision = 'f3a8c1d6b2e9'
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


OLD_ORIGIN = sa.Enum('AUTO', 'MANUAL', name='pluginconfigurationorigin')
NEW_ORIGIN = sa.Enum('AUTO', 'MANUAL', 'CUSTOM', name='pluginconfigurationorigin')


def upgrade_():
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("ALTER TYPE pluginconfigurationorigin ADD VALUE IF NOT EXISTS 'CUSTOM'")
        return
    with op.batch_alter_table('PLUGIN_CONFIGURATION', schema=None) as batch_op:
        batch_op.alter_column('Origin', existing_type=OLD_ORIGIN, type_=NEW_ORIGIN,
                              existing_nullable=False, existing_server_default='MANUAL')


def downgrade_():
    op.get_bind().execute(sa.text("DELETE FROM PLUGIN_CONFIGURATION WHERE Origin = 'CUSTOM'"))
    if op.get_bind().dialect.name == 'postgresql':
        # PostgreSQL cannot drop an enum value; the unused one is harmless.
        return
    with op.batch_alter_table('PLUGIN_CONFIGURATION', schema=None) as batch_op:
        batch_op.alter_column('Origin', existing_type=NEW_ORIGIN, type_=OLD_ORIGIN,
                              existing_nullable=False, existing_server_default='MANUAL')


def upgrade_history():
    pass


def downgrade_history():
    pass
