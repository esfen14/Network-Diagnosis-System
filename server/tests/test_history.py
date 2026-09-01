"""
tests/test_history.py
=====================
Tests for app/api/system/history.py.

Routes tested:
  GET /api/system/history/alerts
  GET /api/system/history/alerts/detail
  GET /api/system/history/notifications
  GET /api/system/history/notifications/detail

Nagios archivejson calls (request_alerts_range, request_notifications_range)
are mocked in all tests so no live Nagios instance is needed.
"""

import pytest
from unittest.mock import patch

# Patch targets inside history.py
_ALERTS_RANGE    = "app.api.system.history.request_alerts_range"
_NOTIFS_RANGE    = "app.api.system.history.request_notifications_range"

# ---------------------------------------------------------------------------
# Sample Nagios payloads
# ---------------------------------------------------------------------------

FAKE_ALERTS = [
    {
        "hostname": "webserver",
        "service_description": "http-80-TCP",
        "state": "CRITICAL",
        "last_state": "OK",
        "state_type": "hard",
        "timestamp": 1700001000,
        "duration_seconds": 3600,
        "plugin_output": "HTTP CRITICAL - Connection refused",
    },
    {
        "hostname": "dbserver",
        "service_description": None,
        "state": "DOWN",
        "last_state": "UP",
        "state_type": "hard",
        "timestamp": 1700002000,
        "duration_seconds": 7200,
        "plugin_output": "PING CRITICAL - 100% packet loss",
    },
    {
        "hostname": "fileserver",
        "service_description": "disk-0-TCP",
        "state": "WARNING",
        "last_state": "OK",
        "state_type": "soft",
        "timestamp": 1700003000,
        "duration_seconds": 300,
        "plugin_output": "DISK WARNING - free space low",
    },
    {
        "hostname": "webserver",
        "service_description": "ssh-22-TCP",
        "state": "OK",
        "last_state": "CRITICAL",
        "state_type": "hard",
        "timestamp": 1700004000,
        "duration_seconds": 60,
        "plugin_output": "SSH OK - recovered",
    },
]

FAKE_NOTIFICATIONS = [
    {
        "hostname": "webserver",
        "service_description": "http-80-TCP",
        "notification_reason": "CRITICAL",
        "contact": "admin",
        "notificationmethod": "email",
        "timestamp": 1700001100,
        "output": "HTTP CRITICAL - Connection refused on port 80",
    },
    {
        "hostname": "dbserver",
        "service_description": None,
        "notification_reason": "DOWN",
        "contact": "admin,ops",
        "notificationmethod": "email",
        "timestamp": 1700002100,
        "output": "Host dbserver is DOWN",
    },
    {
        "hostname": "fileserver",
        "service_description": "disk-0-TCP",
        "notification_reason": "WARNING",
        "contact": "admin",
        "notificationmethod": "sms",
        "timestamp": 1700003100,
        "output": "DISK WARNING on fileserver",
    },
]


# ==========================================================
# Auth / permission guards
# ==========================================================

class TestHistoryAuthGuards:
    READ_ENDPOINTS = [
        "/api/system/history/alerts",
        "/api/system/history/alerts/detail",
        "/api/system/history/notifications",
        "/api/system/history/notifications/detail",
    ]

    @pytest.mark.parametrize("url", READ_ENDPOINTS)
    def test_requires_login(self, client, db_session, url):
        assert client.get(url).status_code in (401, 302)

    @pytest.mark.parametrize("url", READ_ENDPOINTS)
    def test_requires_permission(self, limited_client, db_session, url):
        assert limited_client.get(url).status_code == 403


# ==========================================================
# GET /api/system/history/alerts
# ==========================================================

class TestAlertsHistory:

    def test_returns_paginated_list(self, logged_in_client, db_session):
        with patch(_ALERTS_RANGE, return_value=FAKE_ALERTS):
            resp = logged_in_client.get("/api/system/history/alerts?preset=24h")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "items" in data
        assert "total" in data
        assert "page" in data

    def test_nagios_failure_returns_502(self, logged_in_client, db_session):
        with patch(_ALERTS_RANGE, return_value=None):
            resp = logged_in_client.get("/api/system/history/alerts?preset=24h")
        assert resp.status_code == 502

    def test_default_time_range_is_last_24h(self, logged_in_client, db_session):
        """No params → defaults to last 24 hours, returns 200."""
        with patch(_ALERTS_RANGE, return_value=FAKE_ALERTS):
            resp = logged_in_client.get("/api/system/history/alerts")
        assert resp.status_code == 200

    def test_invalid_preset_returns_400(self, logged_in_client, db_session):
        with patch(_ALERTS_RANGE, return_value=FAKE_ALERTS):
            resp = logged_in_client.get("/api/system/history/alerts?preset=5m")
        assert resp.status_code == 400

    def test_invalid_per_page_returns_400(self, logged_in_client, db_session):
        with patch(_ALERTS_RANGE, return_value=FAKE_ALERTS):
            resp = logged_in_client.get("/api/system/history/alerts?preset=24h&per_page=10")
        assert resp.status_code == 400

    def test_invalid_order_returns_400(self, logged_in_client, db_session):
        with patch(_ALERTS_RANGE, return_value=FAKE_ALERTS):
            resp = logged_in_client.get("/api/system/history/alerts?preset=24h&order=random")
        assert resp.status_code == 400

    def test_invalid_ack_filter_returns_400(self, logged_in_client, db_session):
        with patch(_ALERTS_RANGE, return_value=FAKE_ALERTS):
            resp = logged_in_client.get(
                "/api/system/history/alerts?preset=24h&ack_filter=maybe"
            )
        assert resp.status_code == 400

    def test_invalid_page_returns_400(self, logged_in_client, db_session):
        with patch(_ALERTS_RANGE, return_value=FAKE_ALERTS):
            resp = logged_in_client.get("/api/system/history/alerts?preset=24h&page=0")
        assert resp.status_code == 400

    @pytest.mark.parametrize("preset", ["1h", "6h", "24h", "7d", "30d"])
    def test_all_valid_presets(self, logged_in_client, db_session, preset):
        with patch(_ALERTS_RANGE, return_value=FAKE_ALERTS):
            resp = logged_in_client.get(f"/api/system/history/alerts?preset={preset}")
        assert resp.status_code == 200

    def test_custom_date_range(self, logged_in_client, db_session):
        with patch(_ALERTS_RANGE, return_value=FAKE_ALERTS):
            resp = logged_in_client.get(
                "/api/system/history/alerts?start_date=2024-01-01&end_date=2024-01-31"
            )
        assert resp.status_code == 200

    def test_type_filter_host(self, logged_in_client, db_session):
        with patch(_ALERTS_RANGE, return_value=FAKE_ALERTS):
            resp = logged_in_client.get("/api/system/history/alerts?preset=24h&type=host")
        items = resp.get_json()["data"]["items"]
        assert all(i["type"] == "host" for i in items)

    def test_type_filter_service(self, logged_in_client, db_session):
        with patch(_ALERTS_RANGE, return_value=FAKE_ALERTS):
            resp = logged_in_client.get("/api/system/history/alerts?preset=24h&type=service")
        items = resp.get_json()["data"]["items"]
        assert all(i["type"] == "service" for i in items)

    def test_new_state_filter(self, logged_in_client, db_session):
        with patch(_ALERTS_RANGE, return_value=FAKE_ALERTS):
            resp = logged_in_client.get(
                "/api/system/history/alerts?preset=24h&new_state=CRITICAL"
            )
        items = resp.get_json()["data"]["items"]
        assert all(i["new_state"] == "CRITICAL" for i in items)

    def test_state_type_filter(self, logged_in_client, db_session):
        with patch(_ALERTS_RANGE, return_value=FAKE_ALERTS):
            resp = logged_in_client.get(
                "/api/system/history/alerts?preset=24h&state_type=soft"
            )
        items = resp.get_json()["data"]["items"]
        assert all(i["state_type"] == "soft" for i in items)

    def test_default_sort_is_timestamp_desc(self, logged_in_client, db_session):
        with patch(_ALERTS_RANGE, return_value=FAKE_ALERTS):
            resp = logged_in_client.get("/api/system/history/alerts?preset=24h")
        items = resp.get_json()["data"]["items"]
        if len(items) > 1:
            timestamps = [i["timestamp"] for i in items]
            assert timestamps == sorted(timestamps, reverse=True)

    def test_sort_asc(self, logged_in_client, db_session):
        with patch(_ALERTS_RANGE, return_value=FAKE_ALERTS):
            resp = logged_in_client.get(
                "/api/system/history/alerts?preset=24h&order=asc&sort_by=timestamp"
            )
        items = resp.get_json()["data"]["items"]
        if len(items) > 1:
            timestamps = [i["timestamp"] for i in items]
            assert timestamps == sorted(timestamps)

    def test_pagination_per_page(self, logged_in_client, db_session):
        with patch(_ALERTS_RANGE, return_value=FAKE_ALERTS):
            resp = logged_in_client.get("/api/system/history/alerts?preset=24h&per_page=25")
        data = resp.get_json()["data"]
        assert len(data["items"]) <= 25

    def test_item_shape(self, logged_in_client, db_session):
        with patch(_ALERTS_RANGE, return_value=FAKE_ALERTS):
            resp = logged_in_client.get("/api/system/history/alerts?preset=24h")
        items = resp.get_json()["data"]["items"]
        assert len(items) > 0
        item = items[0]
        for key in (
            "timestamp", "type", "hostname", "service_name",
            "previous_state", "new_state", "state_type",
            "duration_seconds", "plugin_output", "acknowledged",
        ):
            assert key in item, f"Missing key: {key}"

    def test_ack_filter_acknowledged(self, logged_in_client, db_session):
        """Records in AckHistory for ACKNOWLEDGED action appear when ack_filter=acknowledged."""
        from app.system_models import AckHistory, AckAction
        from datetime import datetime, timezone
        with db_session.session.begin_nested():
            db_session.session.add(AckHistory(
                Hostname="webserver",
                Service_Name="http-80-TCP",
                Action=AckAction.ACKNOWLEDGED,
                Actioned_At=datetime.now(timezone.utc),
                ActorUserID=None,
                Comment="test ack",
            ))
        db_session.session.commit()

        with patch(_ALERTS_RANGE, return_value=FAKE_ALERTS):
            resp = logged_in_client.get(
                "/api/system/history/alerts?preset=24h&ack_filter=acknowledged"
            )
        items = resp.get_json()["data"]["items"]
        assert all(i["acknowledged"] for i in items)

    def test_ack_filter_unacknowledged(self, logged_in_client, db_session):
        """When no acks exist, ack_filter=unacknowledged returns all items."""
        with patch(_ALERTS_RANGE, return_value=FAKE_ALERTS):
            resp = logged_in_client.get(
                "/api/system/history/alerts?preset=24h&ack_filter=unacknowledged"
            )
        items = resp.get_json()["data"]["items"]
        assert all(not i["acknowledged"] for i in items)

    def test_empty_nagios_response_returns_empty_list(self, logged_in_client, db_session):
        with patch(_ALERTS_RANGE, return_value=[]):
            resp = logged_in_client.get("/api/system/history/alerts?preset=24h")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["total"] == 0

    def test_nagios_dict_response_normalised(self, logged_in_client, db_session):
        """Nagios may return a dict keyed by string index instead of a list."""
        dict_alerts = {str(i): a for i, a in enumerate(FAKE_ALERTS)}
        with patch(_ALERTS_RANGE, return_value=dict_alerts):
            resp = logged_in_client.get("/api/system/history/alerts?preset=24h")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["total"] == len(FAKE_ALERTS)

    def test_output_truncated_to_200_chars(self, logged_in_client, db_session):
        long_output = "x" * 500
        alert = [{**FAKE_ALERTS[0], "plugin_output": long_output}]
        with patch(_ALERTS_RANGE, return_value=alert):
            resp = logged_in_client.get("/api/system/history/alerts?preset=24h")
        item = resp.get_json()["data"]["items"][0]
        assert len(item["plugin_output"]) == 200


# ==========================================================
# GET /api/system/history/alerts/detail
# ==========================================================

class TestAlertsHistoryDetail:

    def _base_alert(self):
        return FAKE_ALERTS[0]  # webserver / http-80-TCP / CRITICAL

    def test_returns_detail_for_known_alert(self, logged_in_client, db_session):
        alert = self._base_alert()
        with patch(_ALERTS_RANGE, return_value=[alert]):
            with patch(_NOTIFS_RANGE, return_value=[]):
                resp = logged_in_client.get(
                    "/api/system/history/alerts/detail"
                    f"?hostname={alert['hostname']}"
                    f"&timestamp={alert['timestamp']}"
                    f"&new_state={alert['state']}"
                    f"&service={alert['service_description']}"
                )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["hostname"] == alert["hostname"]
        assert data["new_state"] == alert["state"].upper()

    def test_missing_hostname_returns_400(self, logged_in_client, db_session):
        with patch(_ALERTS_RANGE, return_value=[]):
            with patch(_NOTIFS_RANGE, return_value=[]):
                resp = logged_in_client.get(
                    "/api/system/history/alerts/detail?timestamp=1700001000&new_state=CRITICAL"
                )
        assert resp.status_code == 400

    def test_missing_timestamp_returns_400(self, logged_in_client, db_session):
        with patch(_ALERTS_RANGE, return_value=[]):
            with patch(_NOTIFS_RANGE, return_value=[]):
                resp = logged_in_client.get(
                    "/api/system/history/alerts/detail?hostname=webserver&new_state=CRITICAL"
                )
        assert resp.status_code == 400

    def test_nagios_failure_returns_502(self, logged_in_client, db_session):
        with patch(_ALERTS_RANGE, return_value=None):
            resp = logged_in_client.get(
                "/api/system/history/alerts/detail"
                "?hostname=webserver&timestamp=1700001000&new_state=CRITICAL"
            )
        assert resp.status_code == 502

    def test_alert_not_found_returns_404(self, logged_in_client, db_session):
        with patch(_ALERTS_RANGE, return_value=[]):
            with patch(_NOTIFS_RANGE, return_value=[]):
                resp = logged_in_client.get(
                    "/api/system/history/alerts/detail"
                    "?hostname=ghost&timestamp=9999999999&new_state=DOWN"
                )
        assert resp.status_code == 404

    def test_response_shape(self, logged_in_client, db_session):
        alert = self._base_alert()
        with patch(_ALERTS_RANGE, return_value=[alert]):
            with patch(_NOTIFS_RANGE, return_value=[]):
                resp = logged_in_client.get(
                    "/api/system/history/alerts/detail"
                    f"?hostname={alert['hostname']}"
                    f"&timestamp={alert['timestamp']}"
                    f"&new_state={alert['state']}"
                    f"&service={alert['service_description']}"
                )
        data = resp.get_json()["data"]
        for key in (
            "hostname", "service_name", "timestamp", "type",
            "previous_state", "new_state", "state_type",
            "duration_seconds", "plugin_output",
            "acknowledged", "ack", "recovery_duration",
            "linked_notifications",
        ):
            assert key in data, f"Missing key: {key}"

    def test_plugin_output_is_not_truncated(self, logged_in_client, db_session):
        long_output = "y" * 500
        alert = {**self._base_alert(), "plugin_output": long_output}
        with patch(_ALERTS_RANGE, return_value=[alert]):
            with patch(_NOTIFS_RANGE, return_value=[]):
                resp = logged_in_client.get(
                    "/api/system/history/alerts/detail"
                    f"?hostname={alert['hostname']}"
                    f"&timestamp={alert['timestamp']}"
                    f"&new_state={alert['state']}"
                    f"&service={alert['service_description']}"
                )
        # Full output should be present (not truncated to 200 as the list is)
        assert len(resp.get_json()["data"]["plugin_output"]) == 500

    def test_linked_notifications_populated(self, logged_in_client, db_session):
        alert = self._base_alert()
        notif = FAKE_NOTIFICATIONS[0]
        with patch(_ALERTS_RANGE, return_value=[alert]):
            with patch(_NOTIFS_RANGE, return_value=[notif]):
                resp = logged_in_client.get(
                    "/api/system/history/alerts/detail"
                    f"?hostname={alert['hostname']}"
                    f"&timestamp={alert['timestamp']}"
                    f"&new_state={alert['state']}"
                    f"&service={alert['service_description']}"
                )
        linked = resp.get_json()["data"]["linked_notifications"]
        assert isinstance(linked, list)

    def test_recovery_duration_set_when_state_ok(self, logged_in_client, db_session):
        recovery_alert = {
            "hostname": "webserver",
            "service_description": "http-80-TCP",
            "state": "OK",
            "last_state": "CRITICAL",
            "state_type": "hard",
            "timestamp": 1700010000,
            "duration_seconds": 1800,
            "plugin_output": "HTTP OK - recovered",
        }
        with patch(_ALERTS_RANGE, return_value=[recovery_alert]):
            with patch(_NOTIFS_RANGE, return_value=[]):
                resp = logged_in_client.get(
                    "/api/system/history/alerts/detail"
                    "?hostname=webserver&timestamp=1700010000"
                    "&new_state=OK&service=http-80-TCP"
                )
        data = resp.get_json()["data"]
        assert data["recovery_duration"] == 1800

    def test_recovery_duration_none_for_non_ok_state(self, logged_in_client, db_session):
        alert = self._base_alert()
        with patch(_ALERTS_RANGE, return_value=[alert]):
            with patch(_NOTIFS_RANGE, return_value=[]):
                resp = logged_in_client.get(
                    "/api/system/history/alerts/detail"
                    f"?hostname={alert['hostname']}"
                    f"&timestamp={alert['timestamp']}"
                    f"&new_state={alert['state']}"
                    f"&service={alert['service_description']}"
                )
        assert resp.get_json()["data"]["recovery_duration"] is None

    def test_host_level_alert_type_is_host(self, logged_in_client, db_session):
        alert = FAKE_ALERTS[1]  # dbserver / no service / DOWN
        with patch(_ALERTS_RANGE, return_value=[alert]):
            with patch(_NOTIFS_RANGE, return_value=[]):
                resp = logged_in_client.get(
                    "/api/system/history/alerts/detail"
                    f"?hostname={alert['hostname']}"
                    f"&timestamp={alert['timestamp']}"
                    f"&new_state={alert['state']}"
                )
        assert resp.get_json()["data"]["type"] == "host"


# ==========================================================
# GET /api/system/history/notifications
# ==========================================================

class TestNotificationsHistory:

    def test_returns_paginated_list(self, logged_in_client, db_session):
        with patch(_NOTIFS_RANGE, return_value=FAKE_NOTIFICATIONS):
            resp = logged_in_client.get("/api/system/history/notifications?preset=24h")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert "items" in data
        assert "total" in data

    def test_nagios_failure_returns_502(self, logged_in_client, db_session):
        with patch(_NOTIFS_RANGE, return_value=None):
            resp = logged_in_client.get("/api/system/history/notifications?preset=24h")
        assert resp.status_code == 502

    def test_default_time_range(self, logged_in_client, db_session):
        with patch(_NOTIFS_RANGE, return_value=FAKE_NOTIFICATIONS):
            resp = logged_in_client.get("/api/system/history/notifications")
        assert resp.status_code == 200

    def test_invalid_preset_returns_400(self, logged_in_client, db_session):
        with patch(_NOTIFS_RANGE, return_value=FAKE_NOTIFICATIONS):
            resp = logged_in_client.get("/api/system/history/notifications?preset=99d")
        assert resp.status_code == 400

    def test_invalid_per_page_returns_400(self, logged_in_client, db_session):
        with patch(_NOTIFS_RANGE, return_value=FAKE_NOTIFICATIONS):
            resp = logged_in_client.get(
                "/api/system/history/notifications?preset=24h&per_page=10"
            )
        assert resp.status_code == 400

    def test_invalid_order_returns_400(self, logged_in_client, db_session):
        with patch(_NOTIFS_RANGE, return_value=FAKE_NOTIFICATIONS):
            resp = logged_in_client.get(
                "/api/system/history/notifications?preset=24h&order=sideways"
            )
        assert resp.status_code == 400

    @pytest.mark.parametrize("preset", ["1h", "6h", "24h", "7d", "30d"])
    def test_all_valid_presets(self, logged_in_client, db_session, preset):
        with patch(_NOTIFS_RANGE, return_value=FAKE_NOTIFICATIONS):
            resp = logged_in_client.get(
                f"/api/system/history/notifications?preset={preset}"
            )
        assert resp.status_code == 200

    def test_type_filter_host(self, logged_in_client, db_session):
        with patch(_NOTIFS_RANGE, return_value=FAKE_NOTIFICATIONS):
            resp = logged_in_client.get(
                "/api/system/history/notifications?preset=24h&type=host"
            )
        items = resp.get_json()["data"]["items"]
        assert all(i["type"] == "host" for i in items)

    def test_type_filter_service(self, logged_in_client, db_session):
        with patch(_NOTIFS_RANGE, return_value=FAKE_NOTIFICATIONS):
            resp = logged_in_client.get(
                "/api/system/history/notifications?preset=24h&type=service"
            )
        items = resp.get_json()["data"]["items"]
        assert all(i["type"] == "service" for i in items)

    def test_state_filter(self, logged_in_client, db_session):
        with patch(_NOTIFS_RANGE, return_value=FAKE_NOTIFICATIONS):
            resp = logged_in_client.get(
                "/api/system/history/notifications?preset=24h&state=CRITICAL"
            )
        items = resp.get_json()["data"]["items"]
        assert all(i["state"] == "CRITICAL" for i in items)

    def test_contact_filter_partial_match(self, logged_in_client, db_session):
        with patch(_NOTIFS_RANGE, return_value=FAKE_NOTIFICATIONS):
            resp = logged_in_client.get(
                "/api/system/history/notifications?preset=24h&contact=admin"
            )
        items = resp.get_json()["data"]["items"]
        assert all("admin" in i["contact"].lower() for i in items)

    def test_default_sort_is_timestamp_desc(self, logged_in_client, db_session):
        with patch(_NOTIFS_RANGE, return_value=FAKE_NOTIFICATIONS):
            resp = logged_in_client.get("/api/system/history/notifications?preset=24h")
        items = resp.get_json()["data"]["items"]
        if len(items) > 1:
            timestamps = [i["timestamp"] for i in items]
            assert timestamps == sorted(timestamps, reverse=True)

    def test_item_shape(self, logged_in_client, db_session):
        with patch(_NOTIFS_RANGE, return_value=FAKE_NOTIFICATIONS):
            resp = logged_in_client.get("/api/system/history/notifications?preset=24h")
        items = resp.get_json()["data"]["items"]
        assert len(items) > 0
        item = items[0]
        for key in (
            "timestamp", "type", "hostname", "service_name",
            "state", "contact", "method", "message",
        ):
            assert key in item, f"Missing key: {key}"

    def test_message_truncated_to_200_chars(self, logged_in_client, db_session):
        long_notif = [{**FAKE_NOTIFICATIONS[0], "output": "z" * 500}]
        with patch(_NOTIFS_RANGE, return_value=long_notif):
            resp = logged_in_client.get("/api/system/history/notifications?preset=24h")
        item = resp.get_json()["data"]["items"][0]
        assert len(item["message"]) == 200

    def test_nagios_dict_response_normalised(self, logged_in_client, db_session):
        dict_notifs = {str(i): n for i, n in enumerate(FAKE_NOTIFICATIONS)}
        with patch(_NOTIFS_RANGE, return_value=dict_notifs):
            resp = logged_in_client.get("/api/system/history/notifications?preset=24h")
        assert resp.get_json()["data"]["total"] == len(FAKE_NOTIFICATIONS)

    def test_empty_response_returns_empty_list(self, logged_in_client, db_session):
        with patch(_NOTIFS_RANGE, return_value=[]):
            resp = logged_in_client.get("/api/system/history/notifications?preset=24h")
        assert resp.status_code == 200
        assert resp.get_json()["data"]["total"] == 0

    def test_pagination_has_correct_metadata(self, logged_in_client, db_session):
        with patch(_NOTIFS_RANGE, return_value=FAKE_NOTIFICATIONS):
            resp = logged_in_client.get(
                "/api/system/history/notifications?preset=24h&page=1&per_page=25"
            )
        data = resp.get_json()["data"]
        for key in ("page", "per_page", "total", "pages", "has_next", "has_prev"):
            assert key in data


# ==========================================================
# GET /api/system/history/notifications/detail
# ==========================================================

class TestNotificationsHistoryDetail:

    def _base_notif(self):
        return FAKE_NOTIFICATIONS[0]  # webserver / http-80-TCP / CRITICAL

    def test_returns_detail_for_known_notification(self, logged_in_client, db_session):
        notif = self._base_notif()
        with patch(_NOTIFS_RANGE, return_value=[notif]):
            with patch(_ALERTS_RANGE, return_value=[]):
                resp = logged_in_client.get(
                    "/api/system/history/notifications/detail"
                    f"?hostname={notif['hostname']}"
                    f"&timestamp={notif['timestamp']}"
                    f"&service={notif['service_description']}"
                )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["hostname"] == notif["hostname"]

    def test_missing_hostname_returns_400(self, logged_in_client, db_session):
        with patch(_NOTIFS_RANGE, return_value=[]):
            with patch(_ALERTS_RANGE, return_value=[]):
                resp = logged_in_client.get(
                    "/api/system/history/notifications/detail?timestamp=1700001100"
                )
        assert resp.status_code == 400

    def test_missing_timestamp_returns_400(self, logged_in_client, db_session):
        with patch(_NOTIFS_RANGE, return_value=[]):
            with patch(_ALERTS_RANGE, return_value=[]):
                resp = logged_in_client.get(
                    "/api/system/history/notifications/detail?hostname=webserver"
                )
        assert resp.status_code == 400

    def test_nagios_failure_returns_502(self, logged_in_client, db_session):
        with patch(_NOTIFS_RANGE, return_value=None):
            resp = logged_in_client.get(
                "/api/system/history/notifications/detail"
                "?hostname=webserver&timestamp=1700001100"
            )
        assert resp.status_code == 502

    def test_notification_not_found_returns_404(self, logged_in_client, db_session):
        with patch(_NOTIFS_RANGE, return_value=[]):
            with patch(_ALERTS_RANGE, return_value=[]):
                resp = logged_in_client.get(
                    "/api/system/history/notifications/detail"
                    "?hostname=ghost&timestamp=9999999999"
                )
        assert resp.status_code == 404

    def test_response_shape(self, logged_in_client, db_session):
        notif = self._base_notif()
        with patch(_NOTIFS_RANGE, return_value=[notif]):
            with patch(_ALERTS_RANGE, return_value=[]):
                resp = logged_in_client.get(
                    "/api/system/history/notifications/detail"
                    f"?hostname={notif['hostname']}"
                    f"&timestamp={notif['timestamp']}"
                    f"&service={notif['service_description']}"
                )
        data = resp.get_json()["data"]
        for key in (
            "hostname", "service_name", "timestamp", "type",
            "state", "contacts", "method", "message", "linked_alert",
        ):
            assert key in data, f"Missing key: {key}"

    def test_contacts_is_list(self, logged_in_client, db_session):
        notif = self._base_notif()
        with patch(_NOTIFS_RANGE, return_value=[notif]):
            with patch(_ALERTS_RANGE, return_value=[]):
                resp = logged_in_client.get(
                    "/api/system/history/notifications/detail"
                    f"?hostname={notif['hostname']}"
                    f"&timestamp={notif['timestamp']}"
                    f"&service={notif['service_description']}"
                )
        contacts = resp.get_json()["data"]["contacts"]
        assert isinstance(contacts, list)
        assert "admin" in contacts

    def test_multiple_contacts_split_correctly(self, logged_in_client, db_session):
        """'admin,ops' in contact field → ["admin", "ops"] in contacts list."""
        notif = FAKE_NOTIFICATIONS[1]  # contact = "admin,ops"
        with patch(_NOTIFS_RANGE, return_value=[notif]):
            with patch(_ALERTS_RANGE, return_value=[]):
                resp = logged_in_client.get(
                    "/api/system/history/notifications/detail"
                    f"?hostname={notif['hostname']}"
                    f"&timestamp={notif['timestamp']}"
                )
        contacts = resp.get_json()["data"]["contacts"]
        assert "admin" in contacts
        assert "ops" in contacts

    def test_full_message_not_truncated(self, logged_in_client, db_session):
        long_msg = "m" * 500
        notif = {**self._base_notif(), "output": long_msg}
        with patch(_NOTIFS_RANGE, return_value=[notif]):
            with patch(_ALERTS_RANGE, return_value=[]):
                resp = logged_in_client.get(
                    "/api/system/history/notifications/detail"
                    f"?hostname={notif['hostname']}"
                    f"&timestamp={notif['timestamp']}"
                    f"&service={notif['service_description']}"
                )
        # Detail endpoint must return the full message, not truncated to 200
        assert len(resp.get_json()["data"]["message"]) == 500

    def test_linked_alert_present_when_nearby(self, logged_in_client, db_session):
        notif = self._base_notif()
        nearby_alert = {**FAKE_ALERTS[0], "timestamp": notif["timestamp"] + 30}
        with patch(_NOTIFS_RANGE, return_value=[notif]):
            with patch(_ALERTS_RANGE, return_value=[nearby_alert]):
                resp = logged_in_client.get(
                    "/api/system/history/notifications/detail"
                    f"?hostname={notif['hostname']}"
                    f"&timestamp={notif['timestamp']}"
                    f"&service={notif['service_description']}"
                )
        linked = resp.get_json()["data"]["linked_alert"]
        assert linked is not None
        assert "timestamp" in linked
        assert "new_state" in linked

    def test_linked_alert_null_when_none_nearby(self, logged_in_client, db_session):
        notif = self._base_notif()
        with patch(_NOTIFS_RANGE, return_value=[notif]):
            with patch(_ALERTS_RANGE, return_value=[]):
                resp = logged_in_client.get(
                    "/api/system/history/notifications/detail"
                    f"?hostname={notif['hostname']}"
                    f"&timestamp={notif['timestamp']}"
                    f"&service={notif['service_description']}"
                )
        assert resp.get_json()["data"]["linked_alert"] is None

    def test_host_level_type_is_host(self, logged_in_client, db_session):
        notif = FAKE_NOTIFICATIONS[1]  # dbserver / no service
        with patch(_NOTIFS_RANGE, return_value=[notif]):
            with patch(_ALERTS_RANGE, return_value=[]):
                resp = logged_in_client.get(
                    "/api/system/history/notifications/detail"
                    f"?hostname={notif['hostname']}"
                    f"&timestamp={notif['timestamp']}"
                )
        assert resp.get_json()["data"]["type"] == "host"
