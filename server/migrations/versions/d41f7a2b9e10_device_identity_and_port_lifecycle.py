"""device identity and port lifecycle

Adds the tables and columns from "spec files/DHCP_Device_Identity_Plan.md"
(section 5) to system.db and migrates existing rows so current behaviour is
preserved: every device keeps its current host name as its stable
Nagios_Host_Name (so history.db rows and acknowledgements stay attached),
every existing port becomes MONITORED, and the evidence PinPoint already
holds (MACs, SSH host key fingerprints) becomes DeviceIdentifier rows.

history.db is not touched.

Revision ID: d41f7a2b9e10
Revises: 7d2e4b9a1c05
Create Date: 2026-10-03 12:00:00.000000

"""
import os
import re
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd41f7a2b9e10'
down_revision = '7d2e4b9a1c05'
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


ADDRESSING = sa.Enum('DHCP', 'STATIC', 'UNKNOWN', name='addressingmode')
CONFIDENCE = sa.Enum('VERIFIED', 'LIKELY', 'UNVERIFIED', name='identityconfidence')
STATE = sa.Enum('ACTIVE', 'MISSING', 'ADDRESS_UNKNOWN', 'RETIRED', 'MERGED', name='devicestate')
PORT_STATE = sa.Enum('SUGGESTED', 'MONITORED', 'MISSING', 'ARCHIVED', 'IGNORED', name='portstate')
PORT_SOURCE = sa.Enum('SCAN', 'NCPA', 'USER', name='portsource')
IDENTIFIER_KIND = sa.Enum('NCPA_CERT', 'MACHINE_ID', 'SSH_HOST_KEY', 'MAC', 'DNS_NAME', name='identifierkind')
ADDRESS_SOURCE = sa.Enum('SCAN', 'NCPA_RELOCATE', 'MANUAL', name='addresssource')
REVIEW_KIND = sa.Enum('CONFLICT', 'IDENTITY_CHANGED', 'IP_REUSE', 'DUPLICATE_IDENTITY', 'STATIC_MOVED', name='reviewkind')


def is_hardware_mac(mac):
    """Universally administered MAC (locally-administered bit clear)."""
    text = (mac or "").strip().lower()
    if not re.fullmatch(r"([0-9a-f]{2}:){5}[0-9a-f]{2}", text):
        return False
    return (int(text[:2], 16) & 0x02) == 0


def upgrade_():
    # ---- NETWORK_DISCOVERY ------------------------------------------------
    with op.batch_alter_table('NETWORK_DISCOVERY', schema=None) as batch_op:
        batch_op.add_column(sa.Column('Nagios_Host_Name', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('Display_Name', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('Addressing', ADDRESSING, nullable=False, server_default='UNKNOWN'))
        batch_op.add_column(sa.Column('Identity_Confidence', CONFIDENCE, nullable=False, server_default='UNVERIFIED'))
        batch_op.add_column(sa.Column('Device_State', STATE, nullable=False, server_default='ACTIVE'))
        batch_op.add_column(sa.Column('First_Seen_At', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('Last_Seen_At', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('Missed_Scans', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('Merged_Into_ID', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_NETWORK_DISCOVERY_Device_State'), ['Device_State'], unique=False)
        batch_op.create_foreign_key('fk_network_discovery_merged_into', 'NETWORK_DISCOVERY', ['Merged_Into_ID'], ['NetDiscoveryID'])

    # ---- new tables --------------------------------------------------------
    op.create_table('DEVICE_IDENTIFIER',
    sa.Column('IdentifierID', sa.Integer(), nullable=False),
    sa.Column('Kind', IDENTIFIER_KIND, nullable=False),
    sa.Column('Value', sa.String(length=255), nullable=False),
    sa.Column('Is_Strong', sa.Boolean(), nullable=False),
    sa.Column('First_Seen_At', sa.DateTime(), nullable=False),
    sa.Column('Last_Seen_At', sa.DateTime(), nullable=False),
    sa.Column('NetDiscoveryID', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['NetDiscoveryID'], ['NETWORK_DISCOVERY.NetDiscoveryID'], ),
    sa.PrimaryKeyConstraint('IdentifierID')
    )
    with op.batch_alter_table('DEVICE_IDENTIFIER', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_DEVICE_IDENTIFIER_NetDiscoveryID'), ['NetDiscoveryID'], unique=False)
    # Unique only for strong identifiers; weak ones (DNS names) may repeat.
    op.create_index(
        'uq_device_identifier_strong', 'DEVICE_IDENTIFIER', ['Kind', 'Value'], unique=True,
        sqlite_where=sa.text('"Is_Strong" = 1'),
        postgresql_where=sa.text('"Is_Strong" = true'),
    )

    op.create_table('DEVICE_ADDRESS_HISTORY',
    sa.Column('AddressID', sa.Integer(), nullable=False),
    sa.Column('IP_Address', sa.String(length=45), nullable=False),
    sa.Column('Network', sa.String(length=18), nullable=True),
    sa.Column('MAC_Address', sa.String(length=17), nullable=True),
    sa.Column('Source', ADDRESS_SOURCE, nullable=False),
    sa.Column('First_Seen_At', sa.DateTime(), nullable=False),
    sa.Column('Last_Seen_At', sa.DateTime(), nullable=False),
    sa.Column('Closed_At', sa.DateTime(), nullable=True),
    sa.Column('NetDiscoveryID', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['NetDiscoveryID'], ['NETWORK_DISCOVERY.NetDiscoveryID'], ),
    sa.PrimaryKeyConstraint('AddressID')
    )
    with op.batch_alter_table('DEVICE_ADDRESS_HISTORY', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_DEVICE_ADDRESS_HISTORY_NetDiscoveryID'), ['NetDiscoveryID'], unique=False)

    op.create_table('DEVICE_REVIEW_ITEM',
    sa.Column('ReviewID', sa.Integer(), nullable=False),
    sa.Column('Kind', REVIEW_KIND, nullable=False),
    sa.Column('IP_Address', sa.String(length=45), nullable=True),
    sa.Column('MAC_Address', sa.String(length=17), nullable=True),
    sa.Column('Message', sa.String(length=255), nullable=False),
    sa.Column('Candidate_Device_IDs', sa.JSON(), nullable=True),
    sa.Column('Created_At', sa.DateTime(), nullable=False),
    sa.Column('Resolved_At', sa.DateTime(), nullable=True),
    sa.Column('DiscoveryStatusID', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['DiscoveryStatusID'], ['NETWORK_DISCOVERY_STATUS.DiscoveryStatusID'], ),
    sa.PrimaryKeyConstraint('ReviewID')
    )
    with op.batch_alter_table('DEVICE_REVIEW_ITEM', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_DEVICE_REVIEW_ITEM_DiscoveryStatusID'), ['DiscoveryStatusID'], unique=False)

    # ---- port tables -------------------------------------------------------
    connection = op.get_bind()
    for table, constraint in (('OPEN_TCP_Services', 'uq_open_tcp_device_port'),
                              ('OPEN_UDP_Services', 'uq_open_udp_device_port')):
        # A unique (device, port) needs the duplicates gone first; keep the oldest row.
        connection.execute(sa.text(
            f'DELETE FROM "{table}" WHERE "OpenPortID" NOT IN '
            f'(SELECT MIN("OpenPortID") FROM "{table}" GROUP BY "NetDiscoveryID", "Port_Number")'
        ))
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('Port_State', PORT_STATE, nullable=False, server_default='MONITORED'))
            batch_op.add_column(sa.Column('Source', PORT_SOURCE, nullable=False, server_default='SCAN'))
            batch_op.add_column(sa.Column('Plugin_Name', sa.String(length=100), nullable=True))
            batch_op.add_column(sa.Column('Observed_Service_Name', sa.String(length=255), nullable=True))
            batch_op.add_column(sa.Column('First_Seen_At', sa.DateTime(), nullable=True))
            batch_op.add_column(sa.Column('Last_Seen_At', sa.DateTime(), nullable=True))
            batch_op.add_column(sa.Column('Closed_At', sa.DateTime(), nullable=True))
            batch_op.add_column(sa.Column('Missed_Scans', sa.Integer(), nullable=False, server_default='0'))
            batch_op.create_unique_constraint(constraint, ['NetDiscoveryID', 'Port_Number'])

    migrate_existing_rows(connection)


def migrate_existing_rows(connection):
    """
    Fill the new columns for rows that existed before this migration:
    stable host names, timestamps, identifiers, one open address row per
    device, confidence, and NCPA-sourced ports.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    domain = os.environ.get('PINPOINT_DOMAIN') or "test.local"

    devices = connection.execute(sa.text(
        'SELECT "NetDiscoveryID", "Hostname", "IP_Address", "Network", "MAC_Address", "Scanned_At" '
        'FROM "NETWORK_DISCOVERY" ORDER BY "NetDiscoveryID"'
    )).fetchall()

    fingerprints = {
        row[0]: row[1]
        for row in connection.execute(sa.text(
            'SELECT "NetworkDiscoveryID", "Key_Fingerprint" FROM "SSH_CREDENTIALS" '
            'WHERE "Key_Fingerprint" IS NOT NULL'
        )).fetchall()
    }

    used_names = set()
    seen_identifiers = set()

    for device_id, hostname, ip, network, mac, scanned_at in devices:
        # Keep the name Nagios already uses so history and acks stay attached.
        base = hostname if hostname and hostname != "Unknown" else f"{ip}.{domain}"
        name = base
        counter = 2
        while name in used_names:
            name = f"{base}-{counter}"
            counter += 1
        used_names.add(name)

        mac_text = (mac or "").strip().lower() or None
        hardware_mac = mac_text if is_hardware_mac(mac_text) else None
        fingerprint = fingerprints.get(device_id)

        if fingerprint:
            confidence = 'VERIFIED'
        elif hardware_mac:
            confidence = 'LIKELY'
        else:
            confidence = 'UNVERIFIED'

        seen = scanned_at or now
        connection.execute(sa.text(
            'UPDATE "NETWORK_DISCOVERY" SET "Nagios_Host_Name" = :name, "Identity_Confidence" = :confidence, '
            '"First_Seen_At" = :seen, "Last_Seen_At" = :seen WHERE "NetDiscoveryID" = :id'
        ), {"name": name, "confidence": confidence, "seen": seen, "id": device_id})

        for kind, value in (('MAC', hardware_mac), ('SSH_HOST_KEY', fingerprint)):
            # Strong identifiers must be unique; a value two rows share is
            # kept on the first device only.
            if value and (kind, value) not in seen_identifiers:
                seen_identifiers.add((kind, value))
                connection.execute(sa.text(
                    'INSERT INTO "DEVICE_IDENTIFIER" ("Kind", "Value", "Is_Strong", "First_Seen_At", "Last_Seen_At", "NetDiscoveryID") '
                    'VALUES (:kind, :value, 1, :seen, :seen, :id)'
                ), {"kind": kind, "value": value, "seen": seen, "id": device_id})

        connection.execute(sa.text(
            'INSERT INTO "DEVICE_ADDRESS_HISTORY" ("IP_Address", "Network", "MAC_Address", "Source", "First_Seen_At", "Last_Seen_At", "NetDiscoveryID") '
            "VALUES (:ip, :network, :mac, 'SCAN', :seen, :seen, :id)"
        ), {"ip": ip, "network": network, "mac": mac_text, "seen": seen, "id": device_id})

    # Existing ports keep monitoring as they do today (server default MONITORED).
    # Port timestamps start now; NCPA's port on a device with a token is NCPA-sourced.
    for table in ('OPEN_TCP_Services', 'OPEN_UDP_Services'):
        connection.execute(sa.text(
            f'UPDATE "{table}" SET "First_Seen_At" = :now, "Last_Seen_At" = :now, "Observed_Service_Name" = "Service_Name"'
        ), {"now": now})

    connection.execute(sa.text(
        'UPDATE "OPEN_TCP_Services" SET "Source" = \'NCPA\' WHERE "Port_Number" = :port AND "NetDiscoveryID" IN '
        '(SELECT "NetworkDiscoveryID" FROM "NCPA_DEPLOYMENT" WHERE "Token" IS NOT NULL)'
    ), {"port": 5693})

    # Now every row has a name, enforce uniqueness.
    with op.batch_alter_table('NETWORK_DISCOVERY', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_network_discovery_nagios_host_name', ['Nagios_Host_Name'])


def downgrade_():
    with op.batch_alter_table('NETWORK_DISCOVERY', schema=None) as batch_op:
        batch_op.drop_constraint('uq_network_discovery_nagios_host_name', type_='unique')

    for table, constraint in (('OPEN_UDP_Services', 'uq_open_udp_device_port'),
                              ('OPEN_TCP_Services', 'uq_open_tcp_device_port')):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(constraint, type_='unique')
            for column in ('Missed_Scans', 'Closed_At', 'Last_Seen_At', 'First_Seen_At',
                           'Observed_Service_Name', 'Plugin_Name', 'Source', 'Port_State'):
                batch_op.drop_column(column)

    with op.batch_alter_table('DEVICE_REVIEW_ITEM', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_DEVICE_REVIEW_ITEM_DiscoveryStatusID'))
    op.drop_table('DEVICE_REVIEW_ITEM')

    with op.batch_alter_table('DEVICE_ADDRESS_HISTORY', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_DEVICE_ADDRESS_HISTORY_NetDiscoveryID'))
    op.drop_table('DEVICE_ADDRESS_HISTORY')

    op.drop_index('uq_device_identifier_strong', table_name='DEVICE_IDENTIFIER')
    with op.batch_alter_table('DEVICE_IDENTIFIER', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_DEVICE_IDENTIFIER_NetDiscoveryID'))
    op.drop_table('DEVICE_IDENTIFIER')

    with op.batch_alter_table('NETWORK_DISCOVERY', schema=None) as batch_op:
        batch_op.drop_constraint('fk_network_discovery_merged_into', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_NETWORK_DISCOVERY_Device_State'))
        for column in ('Merged_Into_ID', 'Missed_Scans', 'Last_Seen_At', 'First_Seen_At', 'Device_State',
                       'Identity_Confidence', 'Addressing', 'Display_Name', 'Nagios_Host_Name'):
            batch_op.drop_column(column)


def upgrade_history():
    # history.db holds Nagios snapshots only; nothing changes there.
    pass


def downgrade_history():
    pass
