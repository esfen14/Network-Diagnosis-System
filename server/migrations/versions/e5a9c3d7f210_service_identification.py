"""service identification

Records how each discovered port's service was identified (operator pin,
"always treat port as" rule, nmap fingerprint, or a port-number guess) and
adds the "always treat port as" discovery settings. Existing ports keep
Identified_By NULL, which the port lifecycle treats like before. The new
ReviewKind value SERVICE_CHANGED needs no schema change.

history.db is not touched.

Revision ID: e5a9c3d7f210
Revises: d41f7a2b9e10
Create Date: 2026-10-04 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5a9c3d7f210'
down_revision = 'd41f7a2b9e10'
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


IDENTIFICATION = sa.Enum('USER', 'PORT_RULE', 'FINGERPRINT', 'PORT_HINT', name='serviceidentification')
PORT_TABLES = ('OPEN_TCP_Services', 'OPEN_UDP_Services')


def upgrade_():
    for table in PORT_TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('Identified_By', IDENTIFICATION, nullable=True))

    with op.batch_alter_table('DISCOVERY_SETTINGS', schema=None) as batch_op:
        batch_op.add_column(sa.Column('TCP_Forced_Services', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('UDP_Forced_Services', sa.JSON(), nullable=True))


def downgrade_():
    with op.batch_alter_table('DISCOVERY_SETTINGS', schema=None) as batch_op:
        batch_op.drop_column('UDP_Forced_Services')
        batch_op.drop_column('TCP_Forced_Services')

    for table in PORT_TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column('Identified_By')


def upgrade_history():
    pass


def downgrade_history():
    pass
