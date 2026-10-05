"""plugin configuration service columns

Plugin-driven monitoring, phase 2. A PluginConfiguration becomes a derived
record of "plugin X is monitoring port P on device D", so it gains the port,
protocol, metric, final Nagios service name, a first-applied time that a
re-apply does not reset, and an Origin. Rows that already exist were created
by hand through Plugin Manager and are marked MANUAL; the reconciler never
touches them.

Data step: until now discovery generated services without looking at
Plugin.Status, so disabling or never enabling a plugin changed nothing. Once
generation is gated by the plugin's state, existing monitoring would vanish
the first time discovery ran. To prevent that, every plugin that backs a
monitored (or missing) port is set to ENABLED here. The mapping below is the
registry-definition to Plugin Manager plugin table from the plan (section
2.2), copied so the migration does not depend on application code. A plugin
that is not in PLUGIN yet (no plugin scan has run) cannot be enabled here;
the phase 3 startup ordering runs a plugin scan before discovery for that
case. Downgrade drops the schema only; it does not put plugin states back.

history.db is not touched.

Revision ID: a8c4e1f6b2d3
Revises: c7e3a9d1b5f2
Create Date: 2026-10-05 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8c4e1f6b2d3'
down_revision = 'c7e3a9d1b5f2'
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


ORIGIN = sa.Enum('AUTO', 'MANUAL', name='pluginconfigurationorigin')
UNIQUE_NAME = 'uq_plugin_config_service'

PORT_TABLES = (('OPEN_TCP_Services', 'tcp'), ('OPEN_UDP_Services', 'udp'))

# Registry definition name -> Plugin Manager plugin (plan section 2.2).
PLUGIN_FOR_DEFINITION = {
    'tcp': 'check_tcp',
    'udp': 'check_udp',
    'snmp': 'check_snmp',
    'ncpa': 'check_ncpa',
    'http': 'check_http',
    'https': 'check_http',
    'ssh': 'check_ssh',
    'ftp': 'check_ftp',
    'smtp': 'check_smtp',
    'mysql': 'check_mysql',
    'dns': 'check_dns',
    'ntp': 'check_ntp_time',
}

def plugins_backing_monitored_ports(bind):
    """
    Return the set of Plugin Manager plugin names behind every monitored or
    missing port. A port uses its frozen Plugin_Name, else its Service_Name;
    a TCP port matching no definition is checked by the generic TCP plugin,
    as discovery does. Unmatched UDP ports are skipped by discovery.
    """
    needed = set()
    for table, transport in PORT_TABLES:
        rows = bind.execute(sa.text(
            f'SELECT Plugin_Name, Service_Name FROM "{table}" '
            "WHERE Port_State IN ('MONITORED', 'MISSING')"
        )).fetchall()
        for plugin_name, service_name in rows:
            key = str(plugin_name or service_name or '').strip().lower()
            plugin = PLUGIN_FOR_DEFINITION.get(key)
            if plugin is None and transport == 'tcp':
                plugin = PLUGIN_FOR_DEFINITION['tcp']
            if plugin is not None:
                needed.add(plugin)
    return needed


def upgrade_():
    with op.batch_alter_table('PLUGIN_CONFIGURATION', schema=None) as batch_op:
        batch_op.add_column(sa.Column('Port_Number', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('Protocol', sa.String(length=3), nullable=True))
        batch_op.add_column(sa.Column('Metric', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('Nagios_Service_Name', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('Applied_At', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('Origin', ORIGIN, nullable=False, server_default='MANUAL'))
        batch_op.create_unique_constraint(UNIQUE_NAME, ['PluginID', 'NetDiscoveryID', 'Nagios_Service_Name'])

    bind = op.get_bind()

    # Manual rows that were applied have been running since they were applied.
    bind.execute(sa.text(
        "UPDATE PLUGIN_CONFIGURATION SET Applied_At = Updated_At WHERE Status = 'APPLIED'"
    ))

    # Keep existing monitoring alive once generation is gated by plugin state.
    # Plugins in a failure state are left alone: they cannot run until fixed.
    for plugin_name in sorted(plugins_backing_monitored_ports(bind)):
        bind.execute(
            sa.text(
                "UPDATE PLUGIN SET Status = 'ENABLED' "
                "WHERE Name = :name AND Status IN ('AVAILABLE', 'READY', 'INSTALLED', "
                "'DISABLED', 'UPDATE_AVAILABLE')"
            ),
            {"name": plugin_name},
        )


def downgrade_():
    with op.batch_alter_table('PLUGIN_CONFIGURATION', schema=None) as batch_op:
        batch_op.drop_constraint(UNIQUE_NAME, type_='unique')
        batch_op.drop_column('Origin')
        batch_op.drop_column('Applied_At')
        batch_op.drop_column('Nagios_Service_Name')
        batch_op.drop_column('Metric')
        batch_op.drop_column('Protocol')
        batch_op.drop_column('Port_Number')


def upgrade_history():
    pass


def downgrade_history():
    pass
