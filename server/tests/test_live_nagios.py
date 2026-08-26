"""
tests/test_live_nagios.py
=========================
Integration tests that call a real Nagios instance.

These tests are SKIPPED automatically unless both CGI endpoints respond
correctly.  They are intended to run manually against a live server:

    cd server
    .venv/bin/python -m pytest tests/test_live_nagios.py -v

Configuration (override via environment variables):

    NAGIOS_URL      base URL, default http://192.168.130.10/nagios
    NAGIOS_USER     HTTP-Basic username, default nagiosadmin
    NAGIOS_PASSWORD HTTP-Basic password, default password

Two test classes:
  TestLiveNagiosDirectCGI      — raw HTTP calls to statusjson / archivejson
  TestLiveNagiosViaFlaskRoutes — Flask test client without mocking Nagios helpers

Known behaviour on the reference Nagios instance
-------------------------------------------------
* statusjson hostlist/servicelist returns compact integer state values per
  host/service, not full dict objects.
* archivejson alertlist entries are dicts with keys:
    timestamp, object_type, host_name, description, state (int),
    state_type, plugin_output
* archivejson alertcount returns data.count (integer), not data.alertcount.
* archivejson notificationlist times out on large installations; the Flask
  route test for /dashboard/notifications is therefore marked xfail so it
  does not block CI when the server is slow.

Skip guard
----------
The guard calls both CGI endpoints with bounded time windows before any test
runs. If either times out or returns non-200, the entire module is skipped.
The archivejson probe uses a 1-hour window (fast) rather than all-history.
"""

import os
import time

import pytest
import requests as _requests

# ---------------------------------------------------------------------------
# Connection parameters
# ---------------------------------------------------------------------------

_NAGIOS_BASE = os.environ.get("NAGIOS_URL", "http://192.168.130.10/nagios")
_NAGIOS_USER = os.environ.get("NAGIOS_USER", "nagiosadmin")
_NAGIOS_PASS = os.environ.get("NAGIOS_PASSWORD", "password")

_STATUS_CGI  = f"{_NAGIOS_BASE}/cgi-bin/statusjson.cgi"
_ARCHIVE_CGI = f"{_NAGIOS_BASE}/cgi-bin/archivejson.cgi"
_NAGIOS_AUTH = (_NAGIOS_USER, _NAGIOS_PASS)

# Use a bounded 1-hour window for all archivejson queries.
# Large installations time out with starttime=0 due to log file size.
_NOW = int(time.time())
_1H  = _NOW - 3600
_7D  = _NOW - 7 * 86400


# ---------------------------------------------------------------------------
# Reachability probe — evaluated once at collection time
# ---------------------------------------------------------------------------

def _both_cgis_reachable() -> bool:
    """
    Return True only when both CGIs respond with HTTP 200 within 5 seconds.

    Uses a 1-hour archivejson window to keep the probe fast even on
    installations with large log histories.
    """
    try:
        r1 = _requests.get(
            _STATUS_CGI,
            params={"query": "programstatus"},
            auth=_NAGIOS_AUTH,
            timeout=5,
        )
        if r1.status_code != 200:
            return False

        r2 = _requests.get(
            _ARCHIVE_CGI,
            params={"query": "alertlist", "starttime": _1H, "endtime": _NOW},
            auth=_NAGIOS_AUTH,
            timeout=8,
        )
        return r2.status_code == 200

    except Exception:
        return False


_NAGIOS_LIVE = _both_cgis_reachable()

nagios_live = pytest.mark.skipif(
    not _NAGIOS_LIVE,
    reason=(
        f"Nagios CGIs not reachable at {_NAGIOS_BASE}. "
        "Set NAGIOS_URL / NAGIOS_USER / NAGIOS_PASSWORD to point at a live instance."
    ),
)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _status_get(query: str, extra: dict | None = None) -> dict:
    """GET statusjson.cgi and return parsed JSON."""
    params = {"query": query, **(extra or {})}
    resp = _requests.get(_STATUS_CGI, params=params, auth=_NAGIOS_AUTH, timeout=8)
    resp.raise_for_status()
    return resp.json()


def _archive_get(query: str, extra: dict | None = None) -> dict:
    """GET archivejson.cgi with a 1-hour window and return parsed JSON."""
    params = {"query": query, "starttime": _1H, "endtime": _NOW, **(extra or {})}
    resp = _requests.get(_ARCHIVE_CGI, params=params, auth=_NAGIOS_AUTH, timeout=8)
    resp.raise_for_status()
    return resp.json()


# ==========================================================
# Direct CGI tests
# ==========================================================

class TestLiveNagiosDirectCGI:
    """Verify the CGI endpoints respond with the expected JSON structure."""

    # ── statusjson.cgi ────────────────────────────────────────────────────

    @nagios_live
    def test_statusjson_programstatus_responds(self):
        """programstatus must be present and result.type_code must be 0 (success)."""
        data = _status_get("programstatus")
        assert data.get("result", {}).get("type_code") == 0
        assert "data" in data
        assert "programstatus" in data["data"]

    @nagios_live
    def test_statusjson_programstatus_has_pid(self):
        """Nagios must report a numeric PID > 0."""
        ps = _status_get("programstatus")["data"]["programstatus"]
        assert "nagios_pid" in ps
        assert isinstance(ps["nagios_pid"], int)
        assert ps["nagios_pid"] > 0

    @nagios_live
    def test_statusjson_programstatus_version_present(self):
        """Version string must be non-empty."""
        ps = _status_get("programstatus")["data"]["programstatus"]
        assert "version" in ps
        assert ps["version"]

    @nagios_live
    def test_statusjson_hostlist_responds(self):
        """hostlist key must be present in the response data."""
        data = _status_get("hostlist")
        assert "data" in data
        assert "hostlist" in data["data"]
        assert isinstance(data["data"]["hostlist"], dict)

    @nagios_live
    def test_statusjson_hostlist_is_non_empty(self):
        """At least one host must be registered in this Nagios instance."""
        hostlist = _status_get("hostlist")["data"]["hostlist"]
        assert len(hostlist) > 0, "Expected at least one host in Nagios"

    @nagios_live
    def test_statusjson_servicelist_responds(self):
        """servicelist key must be present in the response data."""
        data = _status_get("servicelist")
        assert "data" in data
        assert "servicelist" in data["data"]
        assert isinstance(data["data"]["servicelist"], dict)

    @nagios_live
    def test_statusjson_result_type_code_success(self):
        """Any statusjson query must return result.type_code == 0 for success."""
        for query in ("programstatus", "hostlist", "servicelist"):
            data = _status_get(query)
            assert data.get("result", {}).get("type_code") == 0, \
                f"query={query} returned type_code != 0"

    # ── archivejson.cgi ───────────────────────────────────────────────────

    @nagios_live
    def test_archivejson_alertlist_responds(self):
        """alertlist key must be present in the response data."""
        data = _archive_get("alertlist")
        assert "data" in data
        assert "alertlist" in data["data"]
        assert isinstance(data["data"]["alertlist"], list)

    @nagios_live
    def test_archivejson_alertlist_entry_shape(self):
        """
        Each alert entry must have the keys that dashboard.py reads.

        Per this Nagios version:
          host_name, description, state (int), state_type, plugin_output,
          timestamp, object_type
        """
        alertlist = _archive_get("alertlist")["data"]["alertlist"]
        if not alertlist:
            pytest.skip("No alerts in the last hour — skipping field check.")
        entry = alertlist[0]
        assert isinstance(entry, dict), "Alert entry must be a dict"
        for field in ("timestamp", "host_name", "state"):
            assert field in entry, f"Missing required field '{field}' in alert entry"

    @nagios_live
    def test_archivejson_alertlist_state_is_integer(self):
        """
        Nagios returns numeric state codes (0=OK, 1=WARNING, 2=CRITICAL, 3=UNKNOWN).
        This is distinct from the string states the app mock data uses.
        """
        alertlist = _archive_get("alertlist")["data"]["alertlist"]
        if not alertlist:
            pytest.skip("No alerts in the last hour.")
        for entry in alertlist:
            assert isinstance(entry["state"], int), \
                f"Expected int state, got {type(entry['state']).__name__}: {entry['state']!r}"

    @nagios_live
    def test_archivejson_alertcount_responds(self):
        """alertcount must return a numeric count under data.count."""
        data = _archive_get("alertcount")
        assert "data" in data
        # This Nagios version returns data.count (int), not data.alertcount
        assert "count" in data["data"], \
            f"Expected 'count' in data, got keys: {list(data['data'].keys())}"
        assert isinstance(data["data"]["count"], int)

    @nagios_live
    def test_archivejson_alertcount_non_negative(self):
        """Alert count must be >= 0."""
        count = _archive_get("alertcount")["data"]["count"]
        assert count >= 0

    @nagios_live
    def test_archivejson_result_type_code_success(self):
        """archivejson queries must return result.type_code == 0."""
        data = _archive_get("alertlist")
        assert data.get("result", {}).get("type_code") == 0

    @nagios_live
    def test_authentication_required(self):
        """CGI must reject wrong credentials with HTTP 401."""
        resp = _requests.get(
            _STATUS_CGI,
            params={"query": "programstatus"},
            auth=("wrong_user", "wrong_pass"),
            timeout=5,
        )
        assert resp.status_code == 401


# ==========================================================
# Flask route integration tests (no mocking)
# ==========================================================

class TestLiveNagiosViaFlaskRoutes:
    """
    End-to-end tests: Flask routes call the real Nagios CGI.

    Tests confirm the routes respond with 200 (not 500/502) and return the
    documented response shape when connected to a live Nagios server.

    The /dashboard/notifications route is marked xfail because the
    notificationlist CGI query consistently times out on this installation.
    Change to a regular test once the Nagios instance is tuned.
    """

    @nagios_live
    def test_dashboard_status_returns_200(self, logged_in_client, db_session):
        """Route shape must be correct regardless of DB state."""
        resp = logged_in_client.get("/api/system/dashboard/status")
        assert resp.status_code == 200
        nagios = resp.get_json()["data"]["nagios"]
        for key in ("running", "pid", "version", "active_host_checks",
                    "active_service_checks", "notifications_enabled"):
            assert key in nagios

    @nagios_live
    def test_dashboard_summary_returns_200(self, logged_in_client, db_session):
        """Summary shape must always be correct."""
        resp = logged_in_client.get("/api/system/dashboard/summary")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        for key in ("hosts", "services", "active_alerts", "ping_metrics"):
            assert key in data

    @nagios_live
    def test_network_health_summary_returns_200(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/network-health/summary")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        for key in ("hosts", "services", "active_alerts"):
            assert key in data

    @nagios_live
    def test_network_health_trends_returns_200(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/network-health/trends?hours=24")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["hours"] == 24
        for key in ("ping", "ncpa", "nagios_server"):
            assert key in data

    @nagios_live
    def test_network_health_plugins_returns_200(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/network-health/plugins")
        assert resp.status_code == 200
        assert "groups" in resp.get_json()["data"]

    @nagios_live
    def test_network_health_hosts_returns_200(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/network-health/hosts")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        for key in ("items", "page", "per_page", "total"):
            assert key in data

    @nagios_live
    def test_network_health_services_returns_200(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/network-health/services")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        for key in ("items", "page", "per_page", "total"):
            assert key in data

    @nagios_live
    def test_dashboard_alerts_returns_200(self, logged_in_client, db_session):
        """
        GET /dashboard/alerts must return 200 with live Nagios data.
        Verifies the fix for the integer state code crash in dashboard.py.
        """
        resp = logged_in_client.get("/api/system/dashboard/alerts")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "alerts" in data
        assert isinstance(data["alerts"], list)
        assert "total_shown" in data

    @nagios_live
    def test_dashboard_alerts_item_shape(self, logged_in_client, db_session):
        """Each live alert must have all required fields with correct types."""
        resp = logged_in_client.get("/api/system/dashboard/alerts")
        assert resp.status_code == 200
        alerts = resp.get_json()["data"]["alerts"]
        if not alerts:
            pytest.skip("No active alerts in live Nagios instance.")
        for alert in alerts:
            for field in ("type", "hostname", "state", "timestamp",
                          "duration_seconds", "plugin_output", "in_downtime", "ack"):
                assert field in alert, f"Missing field '{field}' in live alert"
        # state must be a string (e.g. "CRITICAL", "DOWN"), not an int
        for alert in alerts:
            assert isinstance(alert["state"], str), \
                f"state must be str, got {type(alert['state'])}: {alert['state']!r}"
        # timestamp must be in seconds (not milliseconds)
        for alert in alerts:
            assert alert["timestamp"] < 9_999_999_999, \
                f"timestamp looks like milliseconds: {alert['timestamp']}"

    @nagios_live
    def test_dashboard_notifications_returns_200_not_502(self, logged_in_client, db_session):
        """
        GET /dashboard/notifications must return 200 even when Nagios
        notificationlist times out — it now degrades to an empty list.
        """
        resp = logged_in_client.get("/api/system/dashboard/notifications")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "notifications" in data
        assert isinstance(data["notifications"], list)
        assert len(data["notifications"]) <= 5
