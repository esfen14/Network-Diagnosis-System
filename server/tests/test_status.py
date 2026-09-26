"""
tests/test_status.py — Tests for the Nagios status parser in
app/nagios/status.py.

Payloads mirror what statusjson.cgi actually returns with
formatoptions=enumerate: lowercase state names, millisecond timestamps,
'max_attempts', and perf data under 'perf_data'. check_command is not in
statusjson.cgi, so it is looked up from objectjson.cgi's servicelist.
Nagios is never contacted — requests.get is patched.
"""
from unittest.mock import MagicMock, patch

import requests
import sqlalchemy as sa

from app.nagios.status import (
    get_check_commands,
    get_status,
    insert_host_status_data,
    insert_service_status_data,
)
from app.history_models import (
    HostPerfData,
    HostStatus,
    HostStateType,
    ServicePerfData,
    ServiceStatus,
    ServiceStateType,
)


HOSTNAME = "parser-test-host"


def host_payload(**overrides):
    """Build a hostlist entry in statusjson.cgi's enumerated shape."""
    payload = {
        "name": HOSTNAME,
        "status": "up",
        "state_type": "hard",
        "plugin_output": "PING OK - Packet loss = 0%, RTA = 0.04 ms",
        "perf_data": "rta=0.039000ms;3000.000000;5000.000000;0.000000 pl=0%;80;100;0",
        "last_update": 1_790_418_781_000,
        "last_check": 1_790_418_781_000,
        "next_check": 1_790_419_081_000,
        "current_attempt": 1,
        "max_attempts": 10,
        "acknowledgement_type": "none",
        "is_flapping": False,
        "notifications_enabled": True,
    }
    payload.update(overrides)
    return payload


def service_payload(**overrides):
    """Build a servicelist entry in statusjson.cgi's enumerated shape."""
    payload = {
        "status": "ok",
        "state_type": "hard",
        "plugin_output": "PING OK - Packet loss = 0%, RTA = 0.05 ms",
        "perf_data": "rta=0.051000ms;100.000000;500.000000;0.000000 pl=0%;20;60;0",
        "last_update": 1_790_418_781_000,
        "last_check": 1_790_418_781_000,
        "next_check": 1_790_419_081_000,
        "current_attempt": 1,
        "max_attempts": 4,
        "acknowledgement_type": "none",
        "is_flapping": False,
        "notifications_enabled": True,
    }
    payload.update(overrides)
    return payload


def get_service(db_session, service):
    return db_session.session.scalar(
        sa.select(ServiceStatus).where(
            ServiceStatus.Hostname == HOSTNAME, ServiceStatus.Service == service
        )
    )


# ==========================================================
# SERVICE STATUS
# ==========================================================

class TestServiceStatusParsing:

    def test_lowercase_states_are_mapped(self, db_session):
        cases = {
            "svc-ok": ("ok", ServiceStateType.OK),
            "svc-warning": ("warning", ServiceStateType.WARNING),
            "svc-critical": ("critical", ServiceStateType.CRITICAL),
            "svc-unknown": ("unknown", ServiceStateType.UNKNOWN),
        }
        for service, (status, _expected) in cases.items():
            insert_service_status_data(HOSTNAME, service, service_payload(status=status))

        for service, (_status, expected) in cases.items():
            assert get_service(db_session, service).Current_State == expected

    def test_max_attempts_is_read(self, db_session):
        insert_service_status_data(HOSTNAME, "PING", service_payload(max_attempts=4))

        assert get_service(db_session, "PING").Max_Attempts == 4

    def test_perf_data_is_stored(self, db_session):
        insert_service_status_data(HOSTNAME, "PING", service_payload())

        row = get_service(db_session, "PING")
        perf = {
            p.Metric: p
            for p in db_session.session.scalars(
                sa.select(ServicePerfData).where(ServicePerfData.ServiceStatusID == row.ServiceStatusID)
            )
        }
        assert set(perf) == {"rta", "pl"}
        assert perf["rta"].Measured_Value == 0.051
        assert perf["rta"].Unit == "ms"
        assert perf["rta"].Warning_Threshold == 100.0
        assert perf["rta"].Critical_Threshold == 500.0

    def test_missing_perf_data_stores_no_rows(self, db_session):
        insert_service_status_data(HOSTNAME, "no-perf", service_payload(perf_data=""))

        row = get_service(db_session, "no-perf")
        count = db_session.session.scalar(
            sa.select(sa.func.count()).select_from(ServicePerfData)
            .where(ServicePerfData.ServiceStatusID == row.ServiceStatusID)
        )
        assert count == 0


# ==========================================================
# HOST STATUS
# ==========================================================

class TestHostStatusParsing:

    def get_host(self, db_session):
        return db_session.session.scalar(sa.select(HostStatus).where(HostStatus.Hostname == HOSTNAME))

    def test_state_and_max_attempts(self, db_session):
        insert_host_status_data(host_payload(status="down", max_attempts=10))

        row = self.get_host(db_session)
        assert row.Current_State == HostStateType.DOWN
        assert row.Max_Attempts == 10

    def test_perf_data_is_stored(self, db_session):
        insert_host_status_data(host_payload())

        row = self.get_host(db_session)
        metrics = set(db_session.session.scalars(
            sa.select(HostPerfData.Metric).where(HostPerfData.HostStatusID == row.HostStatusID)
        ))
        assert metrics == {"rta", "pl"}


# ==========================================================
# CHECK COMMAND LOOKUP (objectjson.cgi)
# ==========================================================

OBJECT_URL = "http://nagios.test/nagios/cgi-bin/objectjson.cgi"


def json_response(payload):
    """Build a mock requests response returning payload from .json()."""
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def object_servicelist(services):
    """Build an objectjson.cgi servicelist payload from {host: {svc: command}}."""
    servicelist = {}
    for hostname, commands in services.items():
        servicelist[hostname] = {}
        for service, command in commands.items():
            servicelist[hostname][service] = {"host_name": hostname, "check_command": command}
    return {"data": {"servicelist": servicelist}}


class TestGetCheckCommands:

    def test_maps_host_and_service_to_command(self, db_session):
        payload = object_servicelist({
            "localhost": {"Current Load": "check_local_load!5.0,4.0,3.0!10.0,6.0,4.0"},
            HOSTNAME: {"PING": "pinpoint_nd_ping!100!500"},
        })
        with patch("app.nagios.status.requests.get", return_value=json_response(payload)) as get:
            result = get_check_commands(OBJECT_URL, ("user", "pass"))

        assert result == {
            ("localhost", "Current Load"): "check_local_load!5.0,4.0,3.0!10.0,6.0,4.0",
            (HOSTNAME, "PING"): "pinpoint_nd_ping!100!500",
        }
        assert get.call_args.kwargs["params"] == {"query": "servicelist", "details": "true"}

    def test_request_failure_returns_empty(self, db_session):
        with patch("app.nagios.status.requests.get", side_effect=requests.ConnectionError("down")):
            assert get_check_commands(OBJECT_URL, ("user", "pass")) == {}

    def test_malformed_payload_returns_empty(self, db_session):
        with patch("app.nagios.status.requests.get", return_value=json_response({"data": {}})):
            assert get_check_commands(OBJECT_URL, ("user", "pass")) == {}


class TestGetStatusCheckCommand:

    def fake_nagios(self, object_payload):
        """Return a requests.get replacement answering statusjson/objectjson queries."""
        def fake_get(url, params=None, **kwargs):
            query = params["query"]
            if url == OBJECT_URL:
                if isinstance(object_payload, Exception):
                    raise object_payload
                return object_payload
            if query == "programstatus":
                return json_response({"data": {"programstatus": {"version": "4.5.0"}}})
            if query == "hostlist":
                return json_response({"data": {"hostlist": {HOSTNAME: host_payload()}}})
            return json_response({"data": {"servicelist": {HOSTNAME: {
                "PING": service_payload(),
                "not-in-objects": service_payload(),
            }}}})
        return fake_get

    def poll(self, app, object_payload):
        with patch.dict(app.config, {"NAGIOS_OBJECT_URL": OBJECT_URL}), \
                patch("app.nagios.status.requests.get", side_effect=self.fake_nagios(object_payload)):
            get_status()

    def test_check_command_name_is_stored(self, app, db_session):
        payload = json_response(object_servicelist({HOSTNAME: {"PING": "pinpoint_nd_ping!100!500"}}))
        self.poll(app, payload)

        # Only the command name is kept — arguments may carry secrets.
        assert get_service(db_session, "PING").Check_Command == "pinpoint_nd_ping"
        assert get_service(db_session, "not-in-objects").Check_Command is None

    def test_object_lookup_failure_still_stores_status(self, app, db_session):
        self.poll(app, requests.ConnectionError("objectjson down"))

        row = get_service(db_session, "PING")
        assert row is not None
        assert row.Check_Command is None
