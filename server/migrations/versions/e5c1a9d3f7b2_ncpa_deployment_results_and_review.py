"""ncpa deployment results and review

Adds the per-run, per-device NCPA_DEPLOYMENT_RESULT table and the review
columns on NCPA_DEPLOYMENT_STATUS from "docs/plans/NCPA_Deployment_UI_Plan.md"
(section 4). Existing runs keep their rows; they simply have no device
results and are not reviewed.

history.db is not touched.

Revision ID: e5c1a9d3f7b2
Revises: d41f7a2b9e10
Create Date: 2026-10-04 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5c1a9d3f7b2'
down_revision = 'd41f7a2b9e10'
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


OUTCOME = sa.Enum('PENDING', 'RUNNING', 'SUCCESS', 'FAILED', 'UNREACHABLE', 'INCOMPATIBLE',
                  'REJECTED', 'SKIPPED', name='deploymentoutcome')


def upgrade_():
    op.create_table('NCPA_DEPLOYMENT_RESULT',
    sa.Column('NCPADeployResultID', sa.Integer(), nullable=False),
    sa.Column('Hostname', sa.String(length=255), nullable=True),
    sa.Column('IP_Address', sa.String(length=45), nullable=True),
    sa.Column('Outcome', OUTCOME, nullable=False),
    sa.Column('Error', sa.String(length=255), nullable=True),
    sa.Column('Started_At', sa.DateTime(), nullable=True),
    sa.Column('Completed_At', sa.DateTime(), nullable=True),
    sa.Column('NCPADeploymentStatusID', sa.Integer(), nullable=False),
    sa.Column('NetworkDiscoveryID', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['NCPADeploymentStatusID'], ['NCPA_DEPLOYMENT_STATUS.NCPADeployStatusID'], ),
    sa.ForeignKeyConstraint(['NetworkDiscoveryID'], ['NETWORK_DISCOVERY.NetDiscoveryID'], ),
    sa.PrimaryKeyConstraint('NCPADeployResultID')
    )
    with op.batch_alter_table('NCPA_DEPLOYMENT_RESULT', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_NCPA_DEPLOYMENT_RESULT_NCPADeploymentStatusID'), ['NCPADeploymentStatusID'], unique=False)
        batch_op.create_index(batch_op.f('ix_NCPA_DEPLOYMENT_RESULT_NetworkDiscoveryID'), ['NetworkDiscoveryID'], unique=False)

    with op.batch_alter_table('NCPA_DEPLOYMENT_STATUS', schema=None) as batch_op:
        batch_op.add_column(sa.Column('Reviewed_At', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('Reviewed_By', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_ncpa_deployment_status_reviewed_by', 'USER', ['Reviewed_By'], ['UserID'])


def downgrade_():
    with op.batch_alter_table('NCPA_DEPLOYMENT_STATUS', schema=None) as batch_op:
        batch_op.drop_constraint('fk_ncpa_deployment_status_reviewed_by', type_='foreignkey')
        batch_op.drop_column('Reviewed_By')
        batch_op.drop_column('Reviewed_At')

    with op.batch_alter_table('NCPA_DEPLOYMENT_RESULT', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_NCPA_DEPLOYMENT_RESULT_NetworkDiscoveryID'))
        batch_op.drop_index(batch_op.f('ix_NCPA_DEPLOYMENT_RESULT_NCPADeploymentStatusID'))

    op.drop_table('NCPA_DEPLOYMENT_RESULT')
    OUTCOME.drop(op.get_bind(), checkfirst=True)


def upgrade_history():
    # history.db holds Nagios snapshots only; nothing changes there.
    pass


def downgrade_history():
    pass
