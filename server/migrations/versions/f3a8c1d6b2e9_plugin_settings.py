"""add plugin settings and the settings.plugins permission

PLUGIN_SETTINGS holds the plugin defaults edited from Settings -> Plugins (the
SNMP OID table first). With no row a plugin keeps using its config.py defaults,
so nothing changes until someone saves. The settings.plugins permission guards
the tab and its routes; like `flask sync-permissions`, the upgrade grants it to
the Administrator role. The downgrade drops the table and the permission with
its grants.

history.db is not touched.

Revision ID: f3a8c1d6b2e9
Revises: e9b4c2f7a105
Create Date: 2026-10-07 13:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3a8c1d6b2e9'
down_revision = 'e9b4c2f7a105'
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


PERMISSION = 'settings.plugins'


def upgrade_():
    op.create_table('PLUGIN_SETTINGS',
    sa.Column('Id', sa.Integer(), nullable=False),
    sa.Column('Plugin_Name', sa.String(length=50), nullable=False),
    sa.Column('Variables', sa.JSON(), nullable=False),
    sa.Column('Version', sa.Integer(), nullable=False),
    sa.Column('Updated_At', sa.DateTime(), nullable=False),
    sa.Column('Updated_By', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['Updated_By'], ['USER.UserID'], ),
    sa.PrimaryKeyConstraint('Id')
    )
    with op.batch_alter_table('PLUGIN_SETTINGS', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_PLUGIN_SETTINGS_Plugin_Name'), ['Plugin_Name'], unique=True)
        batch_op.create_index(batch_op.f('ix_PLUGIN_SETTINGS_Updated_By'), ['Updated_By'], unique=False)

    bind = op.get_bind()
    exists = bind.execute(sa.text('SELECT 1 FROM PERMISSION WHERE Name = :name'), {"name": PERMISSION}).fetchone()
    if exists is None:
        bind.execute(
            sa.text('INSERT INTO PERMISSION (Name, Description) VALUES (:name, :description)'),
            {"name": PERMISSION, "description": f"Permission for {PERMISSION}"},
        )
    bind.execute(
        sa.text(
            'INSERT INTO ROLE_PERMISSION (RoleID, PermissionID) '
            'SELECT r.RoleID, p.PermissionID FROM ROLE r, PERMISSION p '
            'WHERE r.Name = :role AND p.Name = :name AND NOT EXISTS ('
            'SELECT 1 FROM ROLE_PERMISSION rp WHERE rp.RoleID = r.RoleID AND rp.PermissionID = p.PermissionID)'
        ),
        {"role": "Administrator", "name": PERMISSION},
    )


def downgrade_():
    bind = op.get_bind()
    bind.execute(
        sa.text('DELETE FROM ROLE_PERMISSION WHERE PermissionID IN '
                '(SELECT PermissionID FROM PERMISSION WHERE Name = :name)'),
        {"name": PERMISSION},
    )
    bind.execute(sa.text('DELETE FROM PERMISSION WHERE Name = :name'), {"name": PERMISSION})

    with op.batch_alter_table('PLUGIN_SETTINGS', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_PLUGIN_SETTINGS_Updated_By'))
        batch_op.drop_index(batch_op.f('ix_PLUGIN_SETTINGS_Plugin_Name'))

    op.drop_table('PLUGIN_SETTINGS')


def upgrade_history():
    pass


def downgrade_history():
    pass
