"""
tests/test_skipped_services.py — Recording and reporting discovered ports that
Network Discovery did not turn into a Nagios service.

Covers create_skipped_service_logs() (app/logging/network_discovery_status.py)
and the skipped_services list in GET /api/system/networkdiscovery.
"""
import sqlalchemy as sa

from app.logging.network_discovery_status import create_skipped_service_logs
from app.system_models import (
    ActivityLog,
    DiscoveryStatus,
    NetworkDiscoveryStatus,
    ServiceProtocol,
    SkippedService,
)


def make_discovery_run(db_session, user, message="New host.cfg successfully applied"):
    log = ActivityLog(Action_Type="Discovering Network Hosts", UserID=user.UserID)
    db_session.session.add(log)
    db_session.session.flush()
    status = NetworkDiscoveryStatus(
        Status=DiscoveryStatus.SUCCESS, Progress=100, Message=message, LogID=log.LogID
    )
    db_session.session.add(status)
    db_session.session.commit()
    return status


def skipped_entry(**overrides):
    """Build one entry in _create_host_cfg_file()'s skipped-list shape."""
    entry = {
        "hostname": "switch-1",
        "ip_address": "10.10.99.4",
        "port": "162",
        "protocol": "UDP",
        "service_name": "snmptrap",
        "reason": "No plugin can check this UDP service.",
    }
    entry.update(overrides)
    return entry


# ==========================================================
# RECORDING
# ==========================================================

class TestCreateSkippedServiceLogs:

    def test_rows_are_stored_for_the_run(self, db_session, admin_user):
        run = make_discovery_run(db_session, admin_user)

        create_skipped_service_logs(run.DiscoveryStatusID, [
            skipped_entry(),
            skipped_entry(hostname="router", ip_address="192.168.130.1", port="514", service_name="syslog"),
        ])

        rows = db_session.session.scalars(
            sa.select(SkippedService).order_by(SkippedService.Port_Number)
        ).all()
        assert [(r.Hostname, r.IP_Address, r.Port_Number, r.Service_Name) for r in rows] == [
            ("switch-1", "10.10.99.4", 162, "snmptrap"),
            ("router", "192.168.130.1", 514, "syslog"),
        ]
        assert all(r.Protocol == ServiceProtocol.UDP for r in rows)
        assert all(r.DiscoveryStatusID == run.DiscoveryStatusID for r in rows)

    def test_empty_list_stores_nothing(self, db_session, admin_user):
        run = make_discovery_run(db_session, admin_user)

        create_skipped_service_logs(run.DiscoveryStatusID, [])

        assert db_session.session.scalar(sa.select(sa.func.count()).select_from(SkippedService)) == 0

    def test_bad_entry_does_not_raise(self, db_session, admin_user):
        run = make_discovery_run(db_session, admin_user)

        # Missing keys must be logged and swallowed, never fail discovery.
        create_skipped_service_logs(run.DiscoveryStatusID, [{"hostname": "x"}])

        assert db_session.session.scalar(sa.select(sa.func.count()).select_from(SkippedService)) == 0


# ==========================================================
# REPORTING — GET /api/system/networkdiscovery
# ==========================================================

class TestNetworkDiscoveryLogSkippedServices:

    def test_skipped_services_listed_per_run(self, logged_in_client, db_session, admin_user):
        run_with_skips = make_discovery_run(db_session, admin_user)
        run_without = make_discovery_run(db_session, admin_user, message="Config not applied")
        create_skipped_service_logs(run_with_skips.DiscoveryStatusID, [skipped_entry()])

        resp = logged_in_client.get("/api/system/networkdiscovery")
        assert resp.status_code == 200, resp.get_json()
        items = {item["id"]: item for item in resp.get_json()["data"]["items"]}

        assert items[run_with_skips.DiscoveryStatusID]["details"]["skipped_services"] == [{
            "hostname": "switch-1",
            "ip_address": "10.10.99.4",
            "port": 162,
            "protocol": "UDP",
            "service_name": "snmptrap",
            "reason": "No plugin can check this UDP service.",
        }]
        assert items[run_without.DiscoveryStatusID]["details"]["skipped_services"] == []

    def test_requires_login(self, client, db_session):
        assert client.get("/api/system/networkdiscovery").status_code == 401
