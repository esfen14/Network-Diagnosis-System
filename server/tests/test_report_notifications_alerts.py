"""
tests/test_report_notifications_alerts.py
Tests for the two Nagios-backed report routes in app/api/system/report.py:

  GET /api/system/report/alerts
  GET /api/system/report/notifications

Both routes share the same period-parsing logic and optional hostname/service
filters, so most test cases apply symmetrically to both.

Nagios backend functions are always patched — there is no live Nagios server
in the test environment.
"""

import pytest
from unittest.mock import patch

# ── Patch targets (where the names are looked up, inside the route module) ────
_PATCH_ALERTS_RANGE       = "app.api.system.report.request_alerts_range"
_PATCH_ALERT_COUNT_RANGE  = "app.api.system.report.request_alert_count_range"
_PATCH_NOTIF_RANGE        = "app.api.system.report.request_notifications_range"
_PATCH_NOTIF_COUNT_RANGE  = "app.api.system.report.request_notification_count_range"

ALERTS_URL        = "/api/system/report/alerts"
NOTIFICATIONS_URL = "/api/system/report/notifications"


# ── Sample data factories ──────────────────────────────────────────────────────

def _fake_alerts(n=3):
    return [
        {
            "timestamp":          1_700_000_000 + i,
            "host_name":          f"host{i}",
            "service_description": f"svc{i}",
            "state_type":         "HARD",
            "state":              "CRITICAL",
            "output":             f"Alert output {i}",
        }
        for i in range(n)
    ]


def _fake_alert_count(total=5):
    return {"total": total, "host_up": 0, "host_down": 3, "host_unreachable": 0,
            "service_ok": 0, "service_warning": 1, "service_critical": 1,
            "service_unknown": 0}


def _fake_notifications(n=3):
    return [
        {
            "timestamp":          1_700_000_000 + i,
            "contact_name":       "nagiosadmin",
            "notification_type":  "PROBLEM",
            "host_name":          f"host{i}",
            "service_description": f"svc{i}",
            "state":              "CRITICAL",
            "output":             f"Notification output {i}",
        }
        for i in range(n)
    ]


def _fake_notif_count(total=4):
    return {"total": total, "host_up": 0, "host_down": 2, "host_unreachable": 0,
            "service_ok": 0, "service_warning": 0, "service_critical": 2,
            "service_unknown": 0}


# ── Shared patcher helpers ─────────────────────────────────────────────────────

def _patch_alerts(alerts=None, count=None):
    """Context manager that patches both alert Nagios functions."""
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(
        patch(_PATCH_ALERTS_RANGE, return_value=alerts if alerts is not None else _fake_alerts())
    )
    stack.enter_context(
        patch(_PATCH_ALERT_COUNT_RANGE, return_value=count if count is not None else _fake_alert_count())
    )
    return stack


def _patch_notifications(notifications=None, count=None):
    """Context manager that patches both notification Nagios functions."""
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(
        patch(_PATCH_NOTIF_RANGE, return_value=notifications if notifications is not None else _fake_notifications())
    )
    stack.enter_context(
        patch(_PATCH_NOTIF_COUNT_RANGE, return_value=count if count is not None else _fake_notif_count())
    )
    return stack


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/system/report/alerts
# ══════════════════════════════════════════════════════════════════════════════

class TestReportAlerts:

    # ── Auth / permission guards ───────────────────────────────────────────────

    def test_requires_login(self, client, db_session):
        """Unauthenticated request must be rejected."""
        resp = client.get(ALERTS_URL)
        assert resp.status_code in (401, 302)

    def test_requires_system_report_permission(
        self, limited_client, db_session, seeded_permissions
    ):
        """User without system.report must get 403."""
        resp = limited_client.get(ALERTS_URL)
        assert resp.status_code == 403

    # ── Default period (last_24h) ──────────────────────────────────────────────

    def test_default_period_returns_200(
        self, logged_in_client, db_session, seeded_permissions
    ):
        """No period param → defaults to last_24h and returns 200."""
        with _patch_alerts():
            resp = logged_in_client.get(ALERTS_URL)

        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True

    def test_response_shape(
        self, logged_in_client, db_session, seeded_permissions
    ):
        """Response must contain period, count, and alerts keys."""
        alerts = _fake_alerts(2)
        count  = _fake_alert_count(2)

        with _patch_alerts(alerts=alerts, count=count):
            resp = logged_in_client.get(ALERTS_URL)

        body = resp.get_json()
        data = body["data"]
        assert "period"  in data
        assert "count"   in data
        assert "alerts"  in data
        assert data["alerts"] == alerts
        assert data["count"]  == count

    def test_period_meta_keys(
        self, logged_in_client, db_session, seeded_permissions
    ):
        """The period block must include period, start, and end."""
        with _patch_alerts():
            resp = logged_in_client.get(f"{ALERTS_URL}?period=last_7d")

        period_block = resp.get_json()["data"]["period"]
        assert period_block["period"] == "last_7d"
        assert "start" in period_block
        assert "end"   in period_block

    # ── All valid period values ────────────────────────────────────────────────

    @pytest.mark.parametrize("period", [
        "last_24h", "today", "last_7d", "last_30d", "last_90d"
    ])
    def test_all_named_periods(
        self, logged_in_client, db_session, seeded_permissions, period
    ):
        with _patch_alerts():
            resp = logged_in_client.get(f"{ALERTS_URL}?period={period}")

        assert resp.status_code == 200
        assert resp.get_json()["data"]["period"]["period"] == period

    def test_custom_period(
        self, logged_in_client, db_session, seeded_permissions
    ):
        """period=custom with start/end dates should return 200."""
        with _patch_alerts():
            resp = logged_in_client.get(
                f"{ALERTS_URL}?period=custom&start=2024-01-01&end=2024-01-31"
            )

        assert resp.status_code == 200

    # ── Invalid period / custom edge cases ────────────────────────────────────

    def test_invalid_period_returns_400(
        self, logged_in_client, db_session, seeded_permissions
    ):
        resp = logged_in_client.get(f"{ALERTS_URL}?period=bad_period")
        assert resp.status_code == 400

    def test_custom_period_missing_start_returns_400(
        self, logged_in_client, db_session, seeded_permissions
    ):
        resp = logged_in_client.get(f"{ALERTS_URL}?period=custom&end=2024-01-31")
        assert resp.status_code == 400

    def test_custom_period_missing_end_returns_400(
        self, logged_in_client, db_session, seeded_permissions
    ):
        resp = logged_in_client.get(f"{ALERTS_URL}?period=custom&start=2024-01-01")
        assert resp.status_code == 400

    def test_custom_period_end_before_start_returns_400(
        self, logged_in_client, db_session, seeded_permissions
    ):
        resp = logged_in_client.get(
            f"{ALERTS_URL}?period=custom&start=2024-06-01&end=2024-01-01"
        )
        assert resp.status_code == 400

    # ── Hostname / service filters ─────────────────────────────────────────────

    def test_hostname_filter_passed_to_nagios(
        self, logged_in_client, db_session, seeded_permissions
    ):
        """The hostname query param must be forwarded to the Nagios helper."""
        with (
            patch(_PATCH_ALERTS_RANGE, return_value=_fake_alerts(1)) as mock_alerts,
            patch(_PATCH_ALERT_COUNT_RANGE, return_value=_fake_alert_count(1)),
        ):
            logged_in_client.get(f"{ALERTS_URL}?hostname=myhost")

        _, kwargs = mock_alerts.call_args
        assert kwargs.get("hostname") == "myhost"

    def test_service_filter_passed_to_nagios(
        self, logged_in_client, db_session, seeded_permissions
    ):
        """The service query param must be forwarded to the Nagios helper."""
        with (
            patch(_PATCH_ALERTS_RANGE, return_value=_fake_alerts(1)) as mock_alerts,
            patch(_PATCH_ALERT_COUNT_RANGE, return_value=_fake_alert_count(1)),
        ):
            logged_in_client.get(f"{ALERTS_URL}?service=PING")

        _, kwargs = mock_alerts.call_args
        assert kwargs.get("service") == "PING"

    def test_both_filters_passed_to_nagios(
        self, logged_in_client, db_session, seeded_permissions
    ):
        with (
            patch(_PATCH_ALERTS_RANGE, return_value=_fake_alerts(1)) as mock_alerts,
            patch(_PATCH_ALERT_COUNT_RANGE, return_value=_fake_alert_count(1)),
        ):
            logged_in_client.get(f"{ALERTS_URL}?hostname=myhost&service=PING")

        _, kwargs = mock_alerts.call_args
        assert kwargs.get("hostname") == "myhost"
        assert kwargs.get("service") == "PING"

    # ── Nagios unavailability ──────────────────────────────────────────────────

    def test_nagios_both_none_returns_502(
        self, logged_in_client, db_session, seeded_permissions
    ):
        """When both Nagios calls fail (return None) the endpoint must return 502."""
        with (
            patch(_PATCH_ALERTS_RANGE, return_value=None),
            patch(_PATCH_ALERT_COUNT_RANGE, return_value=None),
        ):
            resp = logged_in_client.get(ALERTS_URL)

        assert resp.status_code == 502

    def test_nagios_only_alerts_none_still_succeeds(
        self, logged_in_client, db_session, seeded_permissions
    ):
        """If only the list call fails but count succeeds, route returns 200 with null alerts."""
        with (
            patch(_PATCH_ALERTS_RANGE, return_value=None),
            patch(_PATCH_ALERT_COUNT_RANGE, return_value=_fake_alert_count()),
        ):
            resp = logged_in_client.get(ALERTS_URL)

        assert resp.status_code == 200
        assert resp.get_json()["data"]["alerts"] is None

    def test_nagios_only_count_none_still_succeeds(
        self, logged_in_client, db_session, seeded_permissions
    ):
        """If only the count call fails but list succeeds, route returns 200 with null count."""
        with (
            patch(_PATCH_ALERTS_RANGE, return_value=_fake_alerts()),
            patch(_PATCH_ALERT_COUNT_RANGE, return_value=None),
        ):
            resp = logged_in_client.get(ALERTS_URL)

        assert resp.status_code == 200
        assert resp.get_json()["data"]["count"] is None

    # ── Empty responses ────────────────────────────────────────────────────────

    def test_empty_alerts_list(
        self, logged_in_client, db_session, seeded_permissions
    ):
        """An empty Nagios response should return alerts=[] with 200."""
        with _patch_alerts(alerts=[], count=_fake_alert_count(0)):
            resp = logged_in_client.get(ALERTS_URL)

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["alerts"] == []
        assert data["count"]["total"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/system/report/notifications
# ══════════════════════════════════════════════════════════════════════════════

class TestReportNotifications:

    # ── Auth / permission guards ───────────────────────────────────────────────

    def test_requires_login(self, client, db_session):
        resp = client.get(NOTIFICATIONS_URL)
        assert resp.status_code in (401, 302)

    def test_requires_system_report_permission(
        self, limited_client, db_session, seeded_permissions
    ):
        resp = limited_client.get(NOTIFICATIONS_URL)
        assert resp.status_code == 403

    # ── Default period (last_24h) ──────────────────────────────────────────────

    def test_default_period_returns_200(
        self, logged_in_client, db_session, seeded_permissions
    ):
        with _patch_notifications():
            resp = logged_in_client.get(NOTIFICATIONS_URL)

        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

    def test_response_shape(
        self, logged_in_client, db_session, seeded_permissions
    ):
        """Response must contain period, count, and notifications keys."""
        notifs = _fake_notifications(2)
        count  = _fake_notif_count(2)

        with _patch_notifications(notifications=notifs, count=count):
            resp = logged_in_client.get(NOTIFICATIONS_URL)

        data = resp.get_json()["data"]
        assert "period"        in data
        assert "count"         in data
        assert "notifications" in data
        assert data["notifications"] == notifs
        assert data["count"]         == count

    def test_period_meta_keys(
        self, logged_in_client, db_session, seeded_permissions
    ):
        """The period block must contain period, start, and end."""
        with _patch_notifications():
            resp = logged_in_client.get(f"{NOTIFICATIONS_URL}?period=last_30d")

        period_block = resp.get_json()["data"]["period"]
        assert period_block["period"] == "last_30d"
        assert "start" in period_block
        assert "end"   in period_block

    # ── All valid period values ────────────────────────────────────────────────

    @pytest.mark.parametrize("period", [
        "last_24h", "today", "last_7d", "last_30d", "last_90d"
    ])
    def test_all_named_periods(
        self, logged_in_client, db_session, seeded_permissions, period
    ):
        with _patch_notifications():
            resp = logged_in_client.get(f"{NOTIFICATIONS_URL}?period={period}")

        assert resp.status_code == 200
        assert resp.get_json()["data"]["period"]["period"] == period

    def test_custom_period(
        self, logged_in_client, db_session, seeded_permissions
    ):
        with _patch_notifications():
            resp = logged_in_client.get(
                f"{NOTIFICATIONS_URL}?period=custom&start=2024-03-01&end=2024-03-31"
            )

        assert resp.status_code == 200

    # ── Invalid period / custom edge cases ────────────────────────────────────

    def test_invalid_period_returns_400(
        self, logged_in_client, db_session, seeded_permissions
    ):
        resp = logged_in_client.get(f"{NOTIFICATIONS_URL}?period=bad_period")
        assert resp.status_code == 400

    def test_custom_period_missing_start_returns_400(
        self, logged_in_client, db_session, seeded_permissions
    ):
        resp = logged_in_client.get(f"{NOTIFICATIONS_URL}?period=custom&end=2024-03-31")
        assert resp.status_code == 400

    def test_custom_period_missing_end_returns_400(
        self, logged_in_client, db_session, seeded_permissions
    ):
        resp = logged_in_client.get(f"{NOTIFICATIONS_URL}?period=custom&start=2024-03-01")
        assert resp.status_code == 400

    def test_custom_period_end_before_start_returns_400(
        self, logged_in_client, db_session, seeded_permissions
    ):
        resp = logged_in_client.get(
            f"{NOTIFICATIONS_URL}?period=custom&start=2024-06-01&end=2024-01-01"
        )
        assert resp.status_code == 400

    # ── Hostname / service filters ─────────────────────────────────────────────

    def test_hostname_filter_passed_to_nagios(
        self, logged_in_client, db_session, seeded_permissions
    ):
        with (
            patch(_PATCH_NOTIF_RANGE, return_value=_fake_notifications(1)) as mock_notif,
            patch(_PATCH_NOTIF_COUNT_RANGE, return_value=_fake_notif_count(1)),
        ):
            logged_in_client.get(f"{NOTIFICATIONS_URL}?hostname=myhost")

        _, kwargs = mock_notif.call_args
        assert kwargs.get("hostname") == "myhost"

    def test_service_filter_passed_to_nagios(
        self, logged_in_client, db_session, seeded_permissions
    ):
        with (
            patch(_PATCH_NOTIF_RANGE, return_value=_fake_notifications(1)) as mock_notif,
            patch(_PATCH_NOTIF_COUNT_RANGE, return_value=_fake_notif_count(1)),
        ):
            logged_in_client.get(f"{NOTIFICATIONS_URL}?service=HTTP")

        _, kwargs = mock_notif.call_args
        assert kwargs.get("service") == "HTTP"

    def test_both_filters_passed_to_nagios(
        self, logged_in_client, db_session, seeded_permissions
    ):
        with (
            patch(_PATCH_NOTIF_RANGE, return_value=_fake_notifications(1)) as mock_notif,
            patch(_PATCH_NOTIF_COUNT_RANGE, return_value=_fake_notif_count(1)),
        ):
            logged_in_client.get(f"{NOTIFICATIONS_URL}?hostname=myhost&service=HTTP")

        _, kwargs = mock_notif.call_args
        assert kwargs.get("hostname") == "myhost"
        assert kwargs.get("service") == "HTTP"

    # ── Nagios unavailability ──────────────────────────────────────────────────

    def test_nagios_both_none_returns_502(
        self, logged_in_client, db_session, seeded_permissions
    ):
        with (
            patch(_PATCH_NOTIF_RANGE, return_value=None),
            patch(_PATCH_NOTIF_COUNT_RANGE, return_value=None),
        ):
            resp = logged_in_client.get(NOTIFICATIONS_URL)

        assert resp.status_code == 502

    def test_nagios_only_list_none_still_succeeds(
        self, logged_in_client, db_session, seeded_permissions
    ):
        """If only the list call fails, route returns 200 with null notifications."""
        with (
            patch(_PATCH_NOTIF_RANGE, return_value=None),
            patch(_PATCH_NOTIF_COUNT_RANGE, return_value=_fake_notif_count()),
        ):
            resp = logged_in_client.get(NOTIFICATIONS_URL)

        assert resp.status_code == 200
        assert resp.get_json()["data"]["notifications"] is None

    def test_nagios_only_count_none_still_succeeds(
        self, logged_in_client, db_session, seeded_permissions
    ):
        """If only the count call fails, route returns 200 with null count."""
        with (
            patch(_PATCH_NOTIF_RANGE, return_value=_fake_notifications()),
            patch(_PATCH_NOTIF_COUNT_RANGE, return_value=None),
        ):
            resp = logged_in_client.get(NOTIFICATIONS_URL)

        assert resp.status_code == 200
        assert resp.get_json()["data"]["count"] is None

    # ── Empty responses ────────────────────────────────────────────────────────

    def test_empty_notifications_list(
        self, logged_in_client, db_session, seeded_permissions
    ):
        with _patch_notifications(notifications=[], count=_fake_notif_count(0)):
            resp = logged_in_client.get(NOTIFICATIONS_URL)

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["notifications"] == []
        assert data["count"]["total"] == 0
