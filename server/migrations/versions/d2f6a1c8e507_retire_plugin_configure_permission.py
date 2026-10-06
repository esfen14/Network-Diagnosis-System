"""retire the plugin.configure permission

plugin.configure guarded the manual "apply a plugin to a device" routes. Those
routes are gone: plugins now attach to discovered ports when they are enabled,
under plugin.enable and plugin.disable. This removes the permission and any
role grants of it so Manage Roles no longer offers a permission that does
nothing. The downgrade puts the permission row back; it does not restore the
role grants.

history.db is not touched.

Revision ID: d2f6a1c8e507
Revises: b9d5f2a7c3e4
Create Date: 2026-10-05 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd2f6a1c8e507'
down_revision = 'b9d5f2a7c3e4'
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


PERMISSION = 'plugin.configure'


def upgrade_():
    bind = op.get_bind()
    bind.execute(
        sa.text('DELETE FROM ROLE_PERMISSION WHERE PermissionID IN '
                '(SELECT PermissionID FROM PERMISSION WHERE Name = :name)'),
        {"name": PERMISSION},
    )
    bind.execute(sa.text('DELETE FROM PERMISSION WHERE Name = :name'), {"name": PERMISSION})


def downgrade_():
    bind = op.get_bind()
    exists = bind.execute(sa.text('SELECT 1 FROM PERMISSION WHERE Name = :name'), {"name": PERMISSION}).fetchone()
    if exists is None:
        bind.execute(
            sa.text('INSERT INTO PERMISSION (Name, Description) VALUES (:name, :description)'),
            {"name": PERMISSION, "description": f"Permission for {PERMISSION}"},
        )


def upgrade_history():
    pass


def downgrade_history():
    pass
