"""add smtp settings and the settings.email permission

SMTP_SETTINGS holds the mail account edited from Settings -> Email (the password
encrypted). With no row, no mail transport is configured. The settings.email
permission guards the tab and its routes; like `flask sync-permissions`, the
upgrade grants it to the Administrator role. The downgrade drops the table and
the permission with its grants.

history.db is not touched.

Revision ID: b6e1d4a8c2f9
Revises: a6f4d2c8e190
Create Date: 2026-10-10 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b6e1d4a8c2f9'
down_revision = 'a6f4d2c8e190'
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


PERMISSION = 'settings.email'


def upgrade_():
    op.create_table('SMTP_SETTINGS',
    sa.Column('Id', sa.Integer(), nullable=False),
    sa.Column('Provider', sa.String(length=20), nullable=False),
    sa.Column('Host', sa.String(length=255), nullable=False),
    sa.Column('Port', sa.Integer(), nullable=False),
    sa.Column('Tls', sa.String(length=10), nullable=False),
    sa.Column('Username', sa.String(length=255), nullable=False),
    sa.Column('Sender', sa.String(length=255), nullable=False),
    sa.Column('Password_Encrypted', sa.Text(), nullable=True),
    sa.Column('Version', sa.Integer(), nullable=False),
    sa.Column('Updated_At', sa.DateTime(), nullable=False),
    sa.Column('Updated_By', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['Updated_By'], ['USER.UserID'], ),
    sa.PrimaryKeyConstraint('Id')
    )
    with op.batch_alter_table('SMTP_SETTINGS', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_SMTP_SETTINGS_Updated_By'), ['Updated_By'], unique=False)

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

    with op.batch_alter_table('SMTP_SETTINGS', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_SMTP_SETTINGS_Updated_By'))

    op.drop_table('SMTP_SETTINGS')


def upgrade_history():
    pass


def downgrade_history():
    pass
