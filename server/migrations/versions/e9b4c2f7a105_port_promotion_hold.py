"""port promotion hold

Plugin-driven monitoring. An enabled plugin promotes every identified Suggested port it can
check. Two things should not be promoted that way: a port an admin deliberately left
Suggested, and a port that was only Suggested before an upgrade when the upgrade itself
switched a plugin on to keep existing services running (for example the generic TCP plugin,
which would otherwise start monitoring every identified port that has no plugin of its own).

Promotion_Held marks those ports. While it is set no plugin promotes the port; monitoring it
by hand (state MONITORED, or acknowledging a mismatch) clears it. The data step holds every
Suggested port that the plugins enabled right now would promote, i.e. exactly the ports the
first reconcile after this upgrade would have started monitoring. Suggested ports whose plugin
is not enabled are not held: enabling that plugin later is the admin's consent to attach them.

The data step uses the plugin registry to resolve service names, so aliases are handled the
same way discovery handles them. The downgrade drops the column.

history.db is not touched.

Revision ID: e9b4c2f7a105
Revises: d2f6a1c8e507
Create Date: 2026-10-06 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e9b4c2f7a105'
down_revision = 'd2f6a1c8e507'
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


PORT_TABLES = (('OPEN_TCP_Services', 'tcp'), ('OPEN_UDP_Services', 'udp'))
IDENTIFIED = ('USER', 'PORT_RULE', 'FINGERPRINT')
ENABLED_PLUGIN_STATES = ('ENABLED', 'ACTIVE')


def upgrade_():
    for table, _ in PORT_TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('Promotion_Held', sa.Boolean(), nullable=False, server_default=sa.false()))

    from app.network_discovery.plugin_registry import Transport, plugin_for_definition, resolve_plugin_name

    bind = op.get_bind()
    enabled = {
        name for (name,) in bind.execute(
            sa.text("SELECT Name FROM PLUGIN WHERE Status IN ('ENABLED', 'ACTIVE')")
        ).fetchall()
    }
    if not enabled:
        return

    for table, protocol in PORT_TABLES:
        transport = Transport.UDP if protocol == 'udp' else Transport.TCP
        rows = bind.execute(sa.text(
            f'SELECT OpenPortID, Service_Name FROM "{table}" '
            "WHERE Port_State = 'SUGGESTED' AND Identified_By IN ('USER', 'PORT_RULE', 'FINGERPRINT') "
            "AND (Expected_Service_Name IS NULL OR Mismatch_Acknowledged_At IS NOT NULL)"
        )).fetchall()
        for port_id, service_name in rows:
            definition_name = resolve_plugin_name(service_name, transport)
            if transport is Transport.UDP and definition_name == 'udp':
                continue          # discovery skips UDP ports no plugin speaks
            if plugin_for_definition(definition_name) in enabled:
                bind.execute(
                    sa.text(f'UPDATE "{table}" SET Promotion_Held = 1 WHERE OpenPortID = :id'), {"id": port_id}
                )


def downgrade_():
    for table, _ in PORT_TABLES:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column('Promotion_Held')


def upgrade_history():
    pass


def downgrade_history():
    pass
