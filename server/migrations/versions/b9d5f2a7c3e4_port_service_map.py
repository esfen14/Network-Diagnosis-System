"""port to service map

Plugin-driven monitoring, phase 2b. The two Network Discovery tables per
protocol ("always treat port as" and "fallback service names") become one
Port -> Service table per protocol: TCP_Port_Services and UDP_Port_Services.
Entries from both old tables are kept; where a port was in both, the "always
treat port as" entry wins, as it did when scanning. The ports tables gain
Expected_Service_Name and Mismatch_Acknowledged_At for the "not used as
intended" flag.

The downgrade writes every entry back as "always treat port as" and leaves the
fallback table empty. The mismatch columns are dropped with their data.

history.db is not touched.

Revision ID: b9d5f2a7c3e4
Revises: a8c4e1f6b2d3
Create Date: 2026-10-05 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b9d5f2a7c3e4'
down_revision = 'a8c4e1f6b2d3'
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


PORT_TABLES = ('OPEN_TCP_Services', 'OPEN_UDP_Services')
SETTINGS = sa.table(
    'DISCOVERY_SETTINGS',
    sa.column('Id', sa.Integer),
    sa.column('TCP_Service_Overrides', sa.JSON),
    sa.column('UDP_Service_Overrides', sa.JSON),
    sa.column('TCP_Forced_Services', sa.JSON),
    sa.column('UDP_Forced_Services', sa.JSON),
    sa.column('TCP_Port_Services', sa.JSON),
    sa.column('UDP_Port_Services', sa.JSON),
)


def merged(fallback, forced):
    """Fallback entries first, then forced ones over them; None stays None."""
    if fallback is None and forced is None:
        return None
    result = dict(fallback or {})
    result.update(forced or {})
    return result


def upgrade_():
    for table in PORT_TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('Expected_Service_Name', sa.String(length=255), nullable=True))
            batch_op.add_column(sa.Column('Mismatch_Acknowledged_At', sa.DateTime(), nullable=True))

    with op.batch_alter_table('DISCOVERY_SETTINGS', schema=None) as batch_op:
        batch_op.add_column(sa.Column('TCP_Port_Services', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('UDP_Port_Services', sa.JSON(), nullable=True))

    bind = op.get_bind()
    for row in bind.execute(sa.select(SETTINGS)).mappings().all():
        bind.execute(
            SETTINGS.update().where(SETTINGS.c.Id == row['Id']).values(
                TCP_Port_Services=merged(row['TCP_Service_Overrides'], row['TCP_Forced_Services']),
                UDP_Port_Services=merged(row['UDP_Service_Overrides'], row['UDP_Forced_Services']),
            )
        )

    with op.batch_alter_table('DISCOVERY_SETTINGS', schema=None) as batch_op:
        batch_op.drop_column('UDP_Forced_Services')
        batch_op.drop_column('TCP_Forced_Services')
        batch_op.drop_column('UDP_Service_Overrides')
        batch_op.drop_column('TCP_Service_Overrides')


def downgrade_():
    with op.batch_alter_table('DISCOVERY_SETTINGS', schema=None) as batch_op:
        batch_op.add_column(sa.Column('TCP_Service_Overrides', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('UDP_Service_Overrides', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('TCP_Forced_Services', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('UDP_Forced_Services', sa.JSON(), nullable=True))

    bind = op.get_bind()
    for row in bind.execute(sa.select(SETTINGS)).mappings().all():
        bind.execute(
            SETTINGS.update().where(SETTINGS.c.Id == row['Id']).values(
                TCP_Forced_Services=row['TCP_Port_Services'],
                UDP_Forced_Services=row['UDP_Port_Services'],
                TCP_Service_Overrides=None if row['TCP_Port_Services'] is None else {},
                UDP_Service_Overrides=None if row['UDP_Port_Services'] is None else {},
            )
        )

    with op.batch_alter_table('DISCOVERY_SETTINGS', schema=None) as batch_op:
        batch_op.drop_column('UDP_Port_Services')
        batch_op.drop_column('TCP_Port_Services')

    for table in PORT_TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column('Mismatch_Acknowledged_At')
            batch_op.drop_column('Expected_Service_Name')


def upgrade_history():
    pass


def downgrade_history():
    pass
