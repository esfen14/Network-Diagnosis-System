"""
tests/unit/test_plugin_scale.py — How the plugin reconciler and the monitored-services
list behave on a network of a few hundred devices.

Plugin-driven monitoring plans every host on each reconcile and builds a plugin's whole
service list before paging it (gaps G14 and G20 in the plan). These tests build a
300-device network directly in the database, time both, and check the results are right.
The time limits are deliberately loose: they catch an accidental slowdown to minutes
(for example a query per row), not small differences between machines. Nagios is never
run; the single writer is mocked.
"""
import time
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from app import db
from app.api.plugin import service
from app.api.plugin.reconcile import desired_services, reconcile_plugin_monitoring
from app.plugin_models import (
    Plugin, PluginConfiguration, PluginConfigurationOrigin, PluginSource, PluginStatus, PluginType,
)
from app.system_models import (
    DiscoveryStatus, NetworkDiscovery, NetworkDiscoveryStatus, Open_TCP_Services, Open_UDP_Services,
    PortSource, PortState, ServiceIdentification,
)
from app.logging.user_activity import create_user_log

DEVICES = 300
# (port, service name, plugin it needs)
TCP_PORTS = [(22, "ssh"), (80, "http"), (443, "https"), (3306, "mysql"), (21, "ftp"), (9100, "printer")]
ENABLED = ["check_ssh", "check_http", "check_mysql", "check_ftp", "check_tcp", "check_snmp"]

# Generous ceilings, in seconds, for a 300-device network on a slow machine.
RECONCILE_LIMIT = 60
LIST_LIMIT = 5


@pytest.fixture
def network(db_session, admin_user):
    """DEVICES devices, each with six monitored TCP ports and an SNMP port, and six plugins enabled."""
    log = create_user_log(admin_user.UserID, "Discovering Network Hosts")
    status = NetworkDiscoveryStatus(Status=DiscoveryStatus.SUCCESS, Progress=100, Message="done", LogID=log.LogID)
    db_session.session.add(status)
    db_session.session.flush()

    devices = [
        NetworkDiscovery(
            Hostname=f"host-{i}", IP_Address=f"10.1.{i // 250}.{i % 250 + 1}", Network="10.1.0.0/16",
            DiscoveryStatusID=status.DiscoveryStatusID, Nagios_Host_Name=f"host-{i}",
        )
        for i in range(DEVICES)
    ]
    db_session.session.add_all(devices)
    db_session.session.flush()

    ports = []
    for device in devices:
        for number, name in TCP_PORTS:
            ports.append(Open_TCP_Services(
                NetDiscoveryID=device.NetDiscoveryID, Port_Number=number, Service_Name=name,
                Observed_Service_Name=name, Port_State=PortState.MONITORED, Source=PortSource.SCAN,
                Identified_By=ServiceIdentification.FINGERPRINT, Plugin_Name=None, Missed_Scans=0,
            ))
        ports.append(Open_UDP_Services(
            NetDiscoveryID=device.NetDiscoveryID, Port_Number=161, Service_Name="snmp",
            Observed_Service_Name="snmp", Port_State=PortState.MONITORED, Source=PortSource.SCAN,
            Identified_By=ServiceIdentification.FINGERPRINT, Plugin_Name=None, Missed_Scans=0,
        ))
    db_session.session.add_all(ports)

    for name in ENABLED:
        db_session.session.add(Plugin(
            Name=name, Plugin_Type=PluginType.NAGIOS, Source=PluginSource.BASELINE_ISO, Status=PluginStatus.ENABLED,
        ))
    db_session.session.commit()
    return devices


def timed(function, *args):
    started = time.perf_counter()
    result = function(*args)
    return result, time.perf_counter() - started


class TestReconcileAtScale:

    def test_planning_every_host_gives_the_right_services_quickly(self, app, network):
        oids = len(app.config["SNMP_OIDS"])

        desired, seconds = timed(desired_services)

        # ssh, http (80 only: https needs check_http too, so 443 counts), mysql needs its user
        # variable so it falls back to check_tcp, ftp, and the generic printer port.
        by_plugin = {}
        for entry in desired:
            by_plugin[entry["plugin"]] = by_plugin.get(entry["plugin"], 0) + 1
        assert by_plugin["check_ssh"] == DEVICES
        assert by_plugin["check_http"] == DEVICES * 2          # http and https share check_http
        assert by_plugin["check_ftp"] == DEVICES
        assert by_plugin["check_snmp"] == DEVICES * oids
        assert len({(e["net_discovery_id"], e["name"]) for e in desired}) == len(desired)
        assert seconds < RECONCILE_LIMIT, f"planning {DEVICES} hosts took {seconds:.1f}s"

    def test_a_full_reconcile_attaches_everything_once_and_a_second_changes_nothing(self, app, db_session, admin_user, network):
        with patch("app.api.plugin.reconcile.regenerate_and_apply_config_status", return_value=("applied", "ok")):
            first, first_seconds = timed(reconcile_plugin_monitoring, admin_user.UserID)
            rows = db_session.session.scalar(sa.select(sa.func.count()).select_from(PluginConfiguration))
            second, second_seconds = timed(reconcile_plugin_monitoring, admin_user.UserID)

        assert first["success"] and first["applied"] == rows and rows > DEVICES * 5
        assert (second["applied"], second["removed"], second["promoted"]) == (0, 0, 0)
        assert db_session.session.scalar(sa.select(sa.func.count()).select_from(PluginConfiguration)) == rows
        assert first_seconds < RECONCILE_LIMIT and second_seconds < RECONCILE_LIMIT
        print(f"\nreconcile of {DEVICES} devices / {rows} services: first {first_seconds:.2f}s, repeat {second_seconds:.2f}s")


class TestServicesListAtScale:

    @pytest.fixture
    def attached(self, db_session, admin_user, network):
        with patch("app.api.plugin.reconcile.regenerate_and_apply_config_status", return_value=("applied", "ok")):
            reconcile_plugin_monitoring(admin_user.UserID)
        return db_session.session.scalar(sa.select(Plugin).where(Plugin.Name == "check_ssh"))

    def test_a_page_of_a_large_plugin_comes_back_quickly(self, db_session, attached):
        page, seconds = timed(service.get_plugin_services, attached.PluginID, 1, 10, "")

        assert page["total"] == DEVICES and len(page["items"]) == 10 and page["pages"] == DEVICES // 10
        assert seconds < LIST_LIMIT, f"listing took {seconds:.1f}s"
        print(f"\nservices page of {DEVICES}: {seconds:.2f}s")

    def test_the_last_page_and_a_search_are_right(self, db_session, attached):
        last = service.get_plugin_services(attached.PluginID, DEVICES // 10, 10, "")
        found, seconds = timed(service.get_plugin_services, attached.PluginID, 1, 10, "host-299")

        assert len(last["items"]) == 10 and last["has_next"] is False and last["has_prev"] is True
        assert [item["device"]["hostname"] for item in found["items"]] == ["host-299"]
        assert seconds < LIST_LIMIT

    def test_the_inventory_counts_services_for_every_plugin_in_one_pass(self, db_session, attached):
        statements = []

        def count(conn, cursor, statement, *args):
            statements.append(statement)

        engine = db.engine
        sa.event.listen(engine, "before_cursor_execute", count)
        try:
            usage = service.get_applied_usage([p.PluginID for p in db_session.session.scalars(sa.select(Plugin)).all()])
        finally:
            sa.event.remove(engine, "before_cursor_execute", count)

        assert usage[attached.PluginID] == {"services": DEVICES, "devices": DEVICES}
        assert len(statements) == 2, "usage counts should be one grouped query (plus the plugin list), not one per plugin"
