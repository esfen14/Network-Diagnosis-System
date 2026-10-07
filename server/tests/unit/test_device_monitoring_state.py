"""
tests/unit/test_device_monitoring_state.py — The monitoring label, its filter on the Device
Inventory host list, and the pause / resume routes.

See "docs/plans/Device_Monitoring_State_Plan.md". A device has one label saying whether Nagios is
checking it: monitored, missing, address_unknown, paused, retired or merged (first match wins in
that reverse order). Pause sets Include_Device_In_Scanning to false and nothing else; scans keep
tracking the device but never turn the pause off. Regenerating the Nagios config is mocked.
"""
from unittest.mock import patch

import pytest
import sqlalchemy as sa

from app import db
from app.network_discovery.create_host_cfg import _load_monitored_hosts
from app.network_discovery.device_identity import MONITORING_STATES, monitoring_state
from app.system_models import ActivityLog, DeviceState
from tests.support.identity_helpers import MAC_1, MAC_2, NET, make_status, run_scan, scan
from app.history_models import HostStateType, ServiceStateType
from tests.support.seed_helpers import _make_host, _make_service

pytestmark = pytest.mark.usefixtures("monitoring_plugins")

BASE = "/api/system"
HOSTS = f"{BASE}/network-health/hosts"


@pytest.fixture(autouse=True)
def regenerate():
    with patch("app.api.system.device_identity.reconcile_plugin_monitoring",
               return_value={"success": True, "changed": True, "message": "applied"}) as mock:
        yield mock


@pytest.fixture
def status(db_session, admin_user):
    return make_status(db_session, admin_user)


def new_device(db_session, status, ip="10.0.0.5", mac=MAC_1, name="web-01"):
    device = run_scan(db_session, status, scan(ip, mac=mac))[(NET, ip)]
    device.Nagios_Host_Name = name
    db.session.commit()
    return device


def log_actions():
    return [row.Action_Type for row in db.session.scalars(sa.select(ActivityLog).order_by(ActivityLog.LogID)).all()]


def host_names(client, query=""):
    data = client.get(f"{HOSTS}?per_page=100{query}").get_json()["data"]
    return sorted(item["hostname"] for item in data["items"])


class TestMonitoringState:

    def test_an_active_device_is_monitored(self, db_session, status):
        assert monitoring_state(new_device(db_session, status)) == "monitored"

    @pytest.mark.parametrize("state, label", [
        (DeviceState.MISSING, "missing"),
        (DeviceState.ADDRESS_UNKNOWN, "address_unknown"),
        (DeviceState.RETIRED, "retired"),
        (DeviceState.MERGED, "merged"),
    ])
    def test_each_lifecycle_state_has_its_label(self, db_session, status, state, label):
        device = new_device(db_session, status)
        device.Device_State = state

        assert monitoring_state(device) == label

    def test_a_paused_device_is_paused(self, db_session, status):
        device = new_device(db_session, status)
        device.Include_Device_In_Scanning = False

        assert monitoring_state(device) == "paused"

    @pytest.mark.parametrize("state, label", [
        (DeviceState.MISSING, "paused"),
        (DeviceState.ADDRESS_UNKNOWN, "paused"),
        (DeviceState.RETIRED, "retired"),
        (DeviceState.MERGED, "merged"),
    ])
    def test_the_first_match_wins(self, db_session, status, state, label):
        device = new_device(db_session, status)
        device.Include_Device_In_Scanning = False
        device.Device_State = state

        assert monitoring_state(device) == label

    def test_every_label_is_listed(self):
        assert set(MONITORING_STATES) == {"monitored", "missing", "address_unknown", "paused", "retired", "merged"}


class TestPause:

    def test_pauses_without_touching_anything_else(self, logged_in_client, db_session, status, regenerate):
        device = new_device(db_session, status)

        resp = logged_in_client.post(f"{BASE}/hosts/{device.NetDiscoveryID}/pause")

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert (data["config_applied"], data["config_ok"]) == (True, True)
        assert data["device"]["monitoring_state"] == "paused" and data["device"]["monitored"] is False
        db_session.session.refresh(device)
        assert device.Include_Device_In_Scanning is False
        assert device.Device_State is DeviceState.ACTIVE
        regenerate.assert_called_once()
        assert log_actions()[-1] == "Paused monitoring of device web-01"

    def test_a_paused_device_leaves_the_nagios_config(self, logged_in_client, db_session, status):
        device = new_device(db_session, status)
        assert _load_monitored_hosts()

        logged_in_client.post(f"{BASE}/hosts/{device.NetDiscoveryID}/pause")

        assert not _load_monitored_hosts()

    def test_cannot_pause_twice(self, logged_in_client, db_session, status):
        device = new_device(db_session, status)
        logged_in_client.post(f"{BASE}/hosts/{device.NetDiscoveryID}/pause")

        assert logged_in_client.post(f"{BASE}/hosts/{device.NetDiscoveryID}/pause").status_code == 400

    @pytest.mark.parametrize("state", [DeviceState.RETIRED, DeviceState.MERGED])
    def test_cannot_pause_a_retired_or_merged_device(self, logged_in_client, db_session, status, state):
        device = new_device(db_session, status)
        device.Device_State = state
        db.session.commit()

        assert logged_in_client.post(f"{BASE}/hosts/{device.NetDiscoveryID}/pause").status_code == 400

    def test_unknown_device_is_404(self, logged_in_client, db_session):
        assert logged_in_client.post(BASE + "/hosts/999/pause").status_code == 404
        assert logged_in_client.post(BASE + "/hosts/999/resume").status_code == 404

    def test_a_config_failure_is_reported_but_the_pause_is_kept(self, logged_in_client, db_session, status, regenerate):
        device = new_device(db_session, status)
        regenerate.side_effect = RuntimeError("nagios exploded")

        data = logged_in_client.post(f"{BASE}/hosts/{device.NetDiscoveryID}/pause").get_json()["data"]

        assert (data["config_applied"], data["config_ok"]) == (False, False)
        db_session.session.refresh(device)
        assert device.Include_Device_In_Scanning is False


class TestResume:

    def test_resumes_with_the_state_the_device_has_now(self, logged_in_client, db_session, status, regenerate):
        device = new_device(db_session, status)
        logged_in_client.post(f"{BASE}/hosts/{device.NetDiscoveryID}/pause")
        device.Device_State = DeviceState.MISSING
        db.session.commit()

        resp = logged_in_client.post(f"{BASE}/hosts/{device.NetDiscoveryID}/resume")

        assert resp.status_code == 200
        assert resp.get_json()["data"]["device"]["monitoring_state"] == "missing"
        db_session.session.refresh(device)
        assert device.Include_Device_In_Scanning is True
        assert regenerate.call_count == 2
        assert log_actions()[-1] == "Resumed monitoring of device web-01"

    def test_cannot_resume_a_device_that_is_not_paused(self, logged_in_client, db_session, status):
        device = new_device(db_session, status)

        assert logged_in_client.post(f"{BASE}/hosts/{device.NetDiscoveryID}/resume").status_code == 400


class TestScansLeaveThePauseAlone:

    def test_a_scan_that_moves_the_device_keeps_it_paused(self, logged_in_client, db_session, status):
        device = new_device(db_session, status, ip="10.0.0.5", mac=MAC_1)
        logged_in_client.post(f"{BASE}/hosts/{device.NetDiscoveryID}/pause")

        run_scan(db_session, status, scan("10.0.0.9", mac=MAC_1))

        db_session.session.refresh(device)
        assert device.IP_Address == "10.0.0.9"
        assert device.Include_Device_In_Scanning is False

    def test_a_device_that_goes_missing_keeps_its_pause(self, logged_in_client, db_session, status):
        device = new_device(db_session, status, ip="10.0.0.5", mac=MAC_1)
        logged_in_client.post(f"{BASE}/hosts/{device.NetDiscoveryID}/pause")

        for _ in range(6):
            run_scan(db_session, status, scan("10.0.0.7", mac=MAC_2))

        db_session.session.refresh(device)
        assert device.Device_State is DeviceState.MISSING
        assert device.Include_Device_In_Scanning is False


class TestHostListAndDetail:

    def seed(self, db_session, status):
        paused = new_device(db_session, status, ip="10.0.0.5", mac=MAC_1, name="paused-01")
        paused.Include_Device_In_Scanning = False
        missing = new_device(db_session, status, ip="10.0.0.6", mac=MAC_2, name="missing-01")
        missing.Device_State = DeviceState.MISSING
        new_device(db_session, status, ip="10.0.0.7", mac="00:11:22:33:44:07", name="ok-01")
        db.session.commit()
        for name in ("paused-01", "missing-01", "ok-01", "localhost"):
            _make_host(db_session, name)
        db_session.session.commit()

    def test_each_host_carries_its_label_or_null(self, logged_in_client, db_session, status):
        self.seed(db_session, status)

        items = {i["hostname"]: i for i in logged_in_client.get(HOSTS).get_json()["data"]["items"]}

        assert items["paused-01"]["monitoring_state"] == "paused" and items["paused-01"]["monitored"] is False
        assert items["missing-01"]["monitoring_state"] == "missing" and items["missing-01"]["monitored"] is False
        assert items["ok-01"]["monitoring_state"] == "monitored" and items["ok-01"]["monitored"] is True
        assert items["localhost"]["monitoring_state"] is None and items["localhost"]["monitored"] is None

    def test_the_detail_carries_the_label(self, logged_in_client, db_session, status):
        self.seed(db_session, status)

        paused = logged_in_client.get(f"{HOSTS}/paused-01/detail").get_json()["data"]
        local = logged_in_client.get(f"{HOSTS}/localhost/detail").get_json()["data"]

        assert (paused["monitoring_state"], paused["monitored"]) == ("paused", False)
        assert (local["monitoring_state"], local["monitored"]) == (None, None)

    @pytest.mark.parametrize("query, expected", [
        ("", ["localhost", "missing-01", "ok-01", "paused-01"]),
        ("&monitoring=all", ["localhost", "missing-01", "ok-01", "paused-01"]),
        ("&monitoring=not_monitored", ["missing-01", "paused-01"]),
        ("&monitoring=monitored", ["localhost", "ok-01"]),
        ("&monitoring=paused", ["paused-01"]),
        ("&monitoring=missing", ["missing-01"]),
        ("&monitoring=retired", []),
    ])
    def test_the_filter(self, logged_in_client, db_session, status, query, expected):
        self.seed(db_session, status)

        assert host_names(logged_in_client, query) == expected

    def test_the_filter_combines_with_search_and_paging(self, logged_in_client, db_session, status):
        self.seed(db_session, status)

        data = logged_in_client.get(f"{HOSTS}?monitoring=not_monitored&search=01&per_page=1").get_json()["data"]

        assert data["total"] == 2 and len(data["items"]) == 1

    def test_an_unknown_filter_is_400(self, logged_in_client, db_session):
        assert logged_in_client.get(f"{HOSTS}?monitoring=sleepy").status_code == 400


class TestPausedDevicesAreNotLive:
    """
    A paused, retired or merged device is out of the Nagios config, so its last history.db
    snapshot is stale. It must not count as an online host, a service or an active alert.
    """

    def seed(self, db_session, status):
        paused = new_device(db_session, status, ip="10.0.0.5", mac=MAC_1, name="paused-01")
        paused.Include_Device_In_Scanning = False
        retired = new_device(db_session, status, ip="10.0.0.6", mac=MAC_2, name="retired-01")
        retired.Device_State = DeviceState.RETIRED
        missing = new_device(db_session, status, ip="10.0.0.8", mac="00:11:22:33:44:08", name="missing-01")
        missing.Device_State = DeviceState.MISSING
        new_device(db_session, status, ip="10.0.0.7", mac="00:11:22:33:44:07", name="ok-01")
        db.session.commit()
        _make_host(db_session, "paused-01")
        _make_host(db_session, "retired-01", state=HostStateType.DOWN)
        _make_host(db_session, "missing-01", state=HostStateType.DOWN)
        _make_host(db_session, "ok-01")
        _make_service(db_session, "paused-01", state=ServiceStateType.CRITICAL)
        _make_service(db_session, "ok-01")
        db_session.session.commit()

    @pytest.mark.parametrize("url", [f"{BASE}/dashboard/summary", f"{BASE}/network-health/summary"])
    def test_host_and_service_counts_leave_them_out(self, logged_in_client, db_session, status, url):
        self.seed(db_session, status)

        data = logged_in_client.get(url).get_json()["data"]

        # ok-01 is up; missing-01 is still checked by Nagios, so its DOWN counts.
        assert (data["hosts"]["total"], data["hosts"]["up"], data["hosts"]["down"]) == (2, 1, 1)
        assert data["services"]["total"] == 1

    def test_they_raise_no_active_alert(self, logged_in_client, db_session, status):
        self.seed(db_session, status)

        alerts = logged_in_client.get(f"{BASE}/dashboard/alerts").get_json()["data"]["alerts"]

        assert {a["hostname"] for a in alerts} == {"missing-01"}

    def test_resume_counts_the_device_again(self, logged_in_client, db_session, status):
        self.seed(db_session, status)
        device_id = logged_in_client.get(f"{HOSTS}/paused-01/detail").get_json()["data"]["device_id"]

        logged_in_client.post(f"{BASE}/hosts/{device_id}/resume")

        hosts = logged_in_client.get(f"{BASE}/dashboard/summary").get_json()["data"]["hosts"]
        assert (hosts["total"], hosts["up"]) == (3, 2)
