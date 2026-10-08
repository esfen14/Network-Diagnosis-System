"""
tests/unit/test_host_device_id.py — The device id on the Device Inventory host list and host
detail, and the registry's service options.

The Device Inventory page works from Nagios host names (the status snapshot), while the port
routes need the device id. GET /network-health/hosts and /hosts/<hostname>/detail therefore
carry "device_id", found with the same naming rule the Nagios config uses, and null for a host
with no device record such as localhost.
"""
import sqlalchemy as sa

from app import db
from app.network_discovery.device_identity import device_ids_by_host_name, nagios_host_name
from app.network_discovery.plugin_registry import service_options
from app.system_models import DeviceState, NetworkDiscovery
from tests.support.identity_helpers import MAC_1, MAC_2, NET, make_status, run_scan, scan
from tests.support.seed_helpers import _make_host

HOSTS = "/api/system/network-health/hosts"


def new_device(db_session, admin_user, ip="10.0.0.5", mac=MAC_1, name="web-01"):
    status = make_status(db_session, admin_user)
    device = run_scan(db, status, scan(ip, mac=mac))[(NET, ip)]
    device.Nagios_Host_Name = name
    db.session.commit()
    return device


class TestDeviceIdsByHostName:

    def test_maps_the_stable_nagios_name_to_the_device(self, db_session, admin_user):
        device = new_device(db_session, admin_user)

        assert device_ids_by_host_name(["web-01"]) == {"web-01": device.NetDiscoveryID}

    def test_a_host_with_no_device_is_absent(self, db_session, admin_user):
        new_device(db_session, admin_user)

        assert device_ids_by_host_name(["localhost", "web-01"]) == {"web-01": db.session.scalar(sa.select(NetworkDiscovery.NetDiscoveryID))}

    def test_nothing_asked_nothing_queried(self, db_session):
        assert device_ids_by_host_name([]) == {}

    def test_it_uses_the_same_rule_as_the_nagios_config_when_there_is_no_stable_name(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        device = run_scan(db, status, scan("10.0.0.7", mac=MAC_2, hostname="dns-name.lan"))[(NET, "10.0.0.7")]
        device.Nagios_Host_Name = None
        db.session.commit()

        assert nagios_host_name(device) == "dns-name.lan"
        assert device_ids_by_host_name(["dns-name.lan"]) == {"dns-name.lan": device.NetDiscoveryID}

    def test_an_ip_derived_name_is_found_too(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        device = run_scan(db, status, scan("10.0.0.8", mac=MAC_2, hostname="Unknown"))[(NET, "10.0.0.8")]
        device.Nagios_Host_Name = None
        db.session.commit()
        derived = "10.0.0.8"

        assert nagios_host_name(device) == derived
        assert device_ids_by_host_name([derived]) == {derived: device.NetDiscoveryID}

    def test_a_current_device_beats_a_retired_one_with_the_same_name(self, db_session, admin_user):
        # The stable name column is unique, but a retired device that never got one falls back to
        # its DNS name, which a current device may now carry as its stable name.
        status = make_status(db_session, admin_user)
        old = run_scan(db, status, scan("10.0.0.5", mac=MAC_1, hostname="shared.lan"))[(NET, "10.0.0.5")]
        old.Nagios_Host_Name = None
        old.Device_State = DeviceState.RETIRED
        current = run_scan(db, status, scan("10.0.0.9", mac=MAC_2))[(NET, "10.0.0.9")]
        current.Nagios_Host_Name = "shared.lan"
        db.session.commit()

        assert nagios_host_name(old) == nagios_host_name(current) == "shared.lan"
        assert device_ids_by_host_name(["shared.lan"]) == {"shared.lan": current.NetDiscoveryID}

    def test_a_retired_device_is_still_found_when_it_is_the_only_one(self, db_session, admin_user):
        old = new_device(db_session, admin_user)
        old.Device_State = DeviceState.RETIRED
        db.session.commit()

        assert device_ids_by_host_name(["web-01"]) == {"web-01": old.NetDiscoveryID}


class TestHostList:

    def test_each_host_carries_its_device_id_or_null(self, logged_in_client, db_session, admin_user):
        device = new_device(db_session, admin_user)
        _make_host(db_session, "web-01")
        _make_host(db_session, "localhost")
        db_session.session.commit()

        items = {i["hostname"]: i for i in logged_in_client.get(HOSTS).get_json()["data"]["items"]}

        assert items["web-01"]["device_id"] == device.NetDiscoveryID
        assert items["localhost"]["device_id"] is None

    def test_each_host_carries_the_devices_current_ip_or_null(self, logged_in_client, db_session, admin_user):
        new_device(db_session, admin_user, ip="10.0.0.5")
        _make_host(db_session, "web-01")
        _make_host(db_session, "localhost")
        db_session.session.commit()

        items = {i["hostname"]: i for i in logged_in_client.get(HOSTS).get_json()["data"]["items"]}

        assert items["web-01"]["ip_address"] == "10.0.0.5"
        assert items["localhost"]["ip_address"] is None

    def test_the_whole_page_is_resolved_with_one_device_query(self, logged_in_client, db_session, admin_user):
        for i in range(12):
            _make_host(db_session, f"host-{i}")
        new_device(db_session, admin_user)
        db_session.session.commit()
        statements = []

        def record(conn, cursor, statement, *args):
            if "NETWORK_DISCOVERY" in statement.upper() and statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        engine = db.engine
        sa.event.listen(engine, "before_cursor_execute", record)
        try:
            logged_in_client.get(HOSTS + "?per_page=100")
        finally:
            sa.event.remove(engine, "before_cursor_execute", record)

        assert len(statements) <= 2          # the device lookup, not one per host

    def test_filters_and_paging_still_work_with_the_new_field(self, logged_in_client, db_session, admin_user):
        new_device(db_session, admin_user)
        for name in ("web-01", "web-02", "db-01"):
            _make_host(db_session, name)
        db_session.session.commit()

        data = logged_in_client.get(HOSTS + "?search=web&per_page=1").get_json()["data"]

        assert data["total"] == 2 and len(data["items"]) == 1 and "device_id" in data["items"][0]


class TestHostDetail:

    def test_the_detail_carries_the_device_id(self, logged_in_client, db_session, admin_user):
        device = new_device(db_session, admin_user)
        _make_host(db_session, "web-01")
        db_session.session.commit()

        data = logged_in_client.get(f"{HOSTS}/web-01/detail").get_json()["data"]

        assert data["device_id"] == device.NetDiscoveryID

    def test_a_host_with_no_device_has_a_null_id(self, logged_in_client, db_session):
        _make_host(db_session, "localhost")
        db_session.session.commit()

        assert logged_in_client.get(f"{HOSTS}/localhost/detail").get_json()["data"]["device_id"] is None


class TestServiceOptions:

    def test_every_option_names_a_service_its_plugin_and_protocols(self):
        options = service_options()

        assert options, "the registry offers no services"
        for option in options:
            assert set(option) == {"name", "plugin", "protocols"}
            assert option["plugin"].startswith("check_") and option["protocols"]
            assert set(option["protocols"]) <= {"tcp", "udp"}

    def test_it_is_sorted_and_has_no_duplicates(self):
        names = [o["name"] for o in service_options()]
        assert names == sorted(names) and len(names) == len(set(names))

    def test_aliases_are_offered_and_the_generic_checks_are_not(self):
        by_name = {o["name"]: o for o in service_options()}

        assert by_name["domain"]["plugin"] == "check_dns"
        assert "tcp" not in by_name and "udp" not in by_name

    def test_every_option_is_a_valid_pin_name(self):
        from app.network_discovery.discovery_settings import SERVICE_NAME_PATTERN
        assert all(SERVICE_NAME_PATTERN.match(o["name"]) for o in service_options())
