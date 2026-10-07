"""
tests/unit/test_notifications.py — Tests for app/api/system/notifications.py

Routes covered:
  GET  /api/system/notifications
  GET  /api/system/notifications/unread-count
  POST /api/system/notifications/mark-read

Because there is no live Nagios server in the test environment, both
`request_notifications_range` and `request_notification_count_range` are
patched via unittest.mock.patch for every test that hits those code paths.
"""

import pytest
from unittest.mock import patch

# ── Patch targets ──────────────────────────────────────────────────────────────
# These must match where the names are *looked up* (inside the route module).
_PATCH_NOTIF_RANGE = (
    "app.api.system.notifications.request_notifications_range"
)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _sample_notifications(n=3, base_ts=1_000_000):
    """Return a list of fake Nagios notification dicts."""
    return [
        {
            "timestamp": base_ts + i,
            "contact_name": "nagiosadmin",
            "notification_type": "PROBLEM",
            "host_name": f"host{i}",
            "service_description": f"svc{i}",
            "state": "CRITICAL",
            "output": f"Check failed {i}",
        }
        for i in range(n)
    ]


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/system/notifications
# ══════════════════════════════════════════════════════════════════════════════

class TestGetNotifications:
    """Tests for GET /api/system/notifications"""

    URL = "/api/system/notifications"

    # ── Auth / permission guards ───────────────────────────────────────────────

    def test_requires_login(self, client, db_session):
        """Unauthenticated request should be rejected."""
        resp = client.get(self.URL)
        assert resp.status_code in (401, 302)

    def test_requires_system_notifications_permission(
        self, limited_client, db_session, seeded_permissions
    ):
        """User without system.notifications permission should get 403."""
        resp = limited_client.get(self.URL)
        assert resp.status_code == 403

    # ── Happy path ────────────────────────────────────────────────────────────

    def test_returns_notifications_list(
        self, logged_in_client, db_session, seeded_permissions, admin_user
    ):
        """Should return a successful response with the expected keys."""
        fake_notifications = _sample_notifications(3, base_ts=1_000_000)

        with patch(_PATCH_NOTIF_RANGE, return_value=fake_notifications):
            resp = logged_in_client.get(self.URL)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "data" in data
        payload = data["data"]
        assert "notifications" in payload
        assert "unread_count" in payload
        assert "last_seen_ts" in payload

    def test_notifications_sorted_newest_first(
        self, logged_in_client, db_session, seeded_permissions, admin_user
    ):
        """Notifications should come back sorted descending by timestamp."""
        # Create items with non-sequential timestamps
        items = [
            {"timestamp": 1_000_001, "host_name": "h1"},
            {"timestamp": 1_000_003, "host_name": "h3"},
            {"timestamp": 1_000_002, "host_name": "h2"},
        ]

        with patch(_PATCH_NOTIF_RANGE, return_value=items):
            resp = logged_in_client.get(self.URL)

        assert resp.status_code == 200
        notifications = resp.get_json()["data"]["notifications"]
        timestamps = [n["timestamp"] for n in notifications]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_millisecond_timestamps_can_be_marked_read(
        self, logged_in_client, db_session, seeded_permissions, admin_user
    ):
        """
        Nagios sends millisecond timestamps; the cursor is in seconds (the
        header sends the seconds value back as up_to). Marking read must clear them.
        """
        items = [{"timestamp": 1_700_000_000_000, "host_name": "h1"}]

        with patch(_PATCH_NOTIF_RANGE, return_value=items):
            first = logged_in_client.get(self.URL).get_json()["data"]
            assert first["notifications"][0]["timestamp"] == 1_700_000_000
            assert first["unread_count"] == 1

            logged_in_client.post(
                "/api/system/notifications/mark-read", json={"up_to": 1_700_000_000}
            )
            again = logged_in_client.get(self.URL).get_json()["data"]

        assert again["unread_count"] == 0
        assert again["notifications"][0]["is_read"] is True

    def test_is_read_annotation_with_new_cursor(
        self, logged_in_client, db_session, seeded_permissions, admin_user
    ):
        """All notifications should be unread for a brand-new cursor (last_seen_ts=0)."""
        fake_notifications = _sample_notifications(2, base_ts=1_000_000)

        with patch(_PATCH_NOTIF_RANGE, return_value=fake_notifications):
            resp = logged_in_client.get(self.URL)

        payload = resp.get_json()["data"]
        for n in payload["notifications"]:
            assert n["is_read"] is False
        assert payload["unread_count"] == len(fake_notifications)

    def test_nagios_dict_normalisation(
        self, logged_in_client, db_session, seeded_permissions, admin_user
    ):
        """
        Nagios sometimes returns a dict keyed by string index instead of a list.
        The endpoint should normalise this correctly.
        """
        # Simulate dict-style Nagios response
        dict_response = {
            "0": {"timestamp": 1_000_001, "host_name": "host0"},
            "1": {"timestamp": 1_000_002, "host_name": "host1"},
        }

        with patch(_PATCH_NOTIF_RANGE, return_value=dict_response):
            resp = logged_in_client.get(self.URL)

        assert resp.status_code == 200
        notifications = resp.get_json()["data"]["notifications"]
        assert len(notifications) == 2

    def test_nagios_unreachable_returns_502(
        self, logged_in_client, db_session, seeded_permissions, admin_user
    ):
        """When Nagios is unreachable (returns None), the route should return 502."""
        with patch(_PATCH_NOTIF_RANGE, return_value=None):
            resp = logged_in_client.get(self.URL)

        assert resp.status_code == 502

    def test_limit_param_respected(
        self, logged_in_client, db_session, seeded_permissions, admin_user
    ):
        """The `limit` query param should cap the number of returned items."""
        # Create 10 notifications but request only 3
        fake_notifications = _sample_notifications(10, base_ts=1_000_000)

        with patch(_PATCH_NOTIF_RANGE, return_value=fake_notifications):
            resp = logged_in_client.get(f"{self.URL}?limit=3")

        assert resp.status_code == 200
        notifications = resp.get_json()["data"]["notifications"]
        assert len(notifications) == 3

    def test_invalid_limit_returns_400(
        self, logged_in_client, db_session, seeded_permissions, admin_user
    ):
        """limit=0 and limit=201 are out of range — should return 400."""
        with patch(_PATCH_NOTIF_RANGE, return_value=[]):
            resp_low = logged_in_client.get(f"{self.URL}?limit=0")
            resp_high = logged_in_client.get(f"{self.URL}?limit=201")

        assert resp_low.status_code == 400
        assert resp_high.status_code == 400

    def test_invalid_lookback_days_returns_400(
        self, logged_in_client, db_session, seeded_permissions, admin_user
    ):
        """lookback_days=0 and lookback_days=91 are out of range — should return 400."""
        with patch(_PATCH_NOTIF_RANGE, return_value=[]):
            resp_low = logged_in_client.get(f"{self.URL}?lookback_days=0")
            resp_high = logged_in_client.get(f"{self.URL}?lookback_days=91")

        assert resp_low.status_code == 400
        assert resp_high.status_code == 400

    def test_empty_notification_list(
        self, logged_in_client, db_session, seeded_permissions, admin_user
    ):
        """An empty Nagios response should return an empty list with unread_count=0."""
        with patch(_PATCH_NOTIF_RANGE, return_value=[]):
            resp = logged_in_client.get(self.URL)

        assert resp.status_code == 200
        payload = resp.get_json()["data"]
        assert payload["notifications"] == []
        assert payload["unread_count"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# GET /api/system/notifications/unread-count
# ══════════════════════════════════════════════════════════════════════════════

class TestGetUnreadCount:
    """Tests for GET /api/system/notifications/unread-count"""

    URL = "/api/system/notifications/unread-count"

    # ── Auth / permission guards ───────────────────────────────────────────────

    def test_requires_login(self, client, db_session):
        resp = client.get(self.URL)
        assert resp.status_code in (401, 302)

    def test_requires_system_notifications_permission(
        self, limited_client, db_session, seeded_permissions
    ):
        resp = limited_client.get(self.URL)
        assert resp.status_code == 403

    # ── Happy path ────────────────────────────────────────────────────────────

    def test_returns_unread_count(
        self, logged_in_client, db_session, seeded_permissions, admin_user
    ):
        """Distinct hosts each count as one unread entry."""
        with patch(_PATCH_NOTIF_RANGE, return_value=_sample_notifications(7)):
            resp = logged_in_client.get(self.URL)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["unread_count"] == 7
        assert "last_seen_ts" in data["data"]

    def test_zero_count(
        self, logged_in_client, db_session, seeded_permissions, admin_user
    ):
        """No notifications should return 200 with unread_count=0."""
        with patch(_PATCH_NOTIF_RANGE, return_value=[]):
            resp = logged_in_client.get(self.URL)

        assert resp.status_code == 200
        assert resp.get_json()["data"]["unread_count"] == 0

    def test_repeat_notifications_count_once(
        self, logged_in_client, db_session, seeded_permissions, admin_user
    ):
        """Repeats of the same host in the same state are one unread entry."""
        repeats = [
            {"timestamp": 1_000_000 + i * 300, "hostname": "h1", "state": "DOWN"}
            for i in range(6)
        ]
        with patch(_PATCH_NOTIF_RANGE, return_value=repeats):
            resp = logged_in_client.get(self.URL)

        assert resp.get_json()["data"]["unread_count"] == 1

    def test_nagios_unreachable_returns_502(
        self, logged_in_client, db_session, seeded_permissions, admin_user
    ):
        """When Nagios returns None the endpoint should respond with 502."""
        with patch(_PATCH_NOTIF_RANGE, return_value=None):
            resp = logged_in_client.get(self.URL)

        assert resp.status_code == 502


# ══════════════════════════════════════════════════════════════════════════════
# POST /api/system/notifications/mark-read
# ══════════════════════════════════════════════════════════════════════════════

class TestMarkNotificationsRead:
    """Tests for POST /api/system/notifications/mark-read"""

    URL = "/api/system/notifications/mark-read"

    # ── Auth / permission guards ───────────────────────────────────────────────

    def test_requires_login(self, client, db_session):
        resp = client.post(self.URL, json={})
        assert resp.status_code in (401, 302)

    def test_requires_system_notifications_permission(
        self, limited_client, db_session, seeded_permissions
    ):
        resp = limited_client.post(self.URL, json={})
        assert resp.status_code == 403

    # ── Happy path ────────────────────────────────────────────────────────────

    def test_mark_read_no_body_sets_cursor_to_now(
        self, logged_in_client, db_session, seeded_permissions, admin_user
    ):
        """Calling without a body should advance the cursor to approximately now."""
        import time
        before = int(time.time()) - 1

        resp = logged_in_client.post(self.URL, json={})

        after = int(time.time()) + 1
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        payload = data["data"]
        assert "previous_last_seen_ts" in payload
        assert "last_seen_ts" in payload
        assert before <= payload["last_seen_ts"] <= after

    def test_mark_read_with_explicit_up_to(
        self, logged_in_client, db_session, seeded_permissions, admin_user
    ):
        """Providing `up_to` should set the cursor to that exact timestamp."""
        target_ts = 1_700_000_000

        resp = logged_in_client.post(self.URL, json={"up_to": target_ts})

        assert resp.status_code == 200
        payload = resp.get_json()["data"]
        assert payload["last_seen_ts"] == target_ts
        assert payload["previous_last_seen_ts"] == 0  # cursor was fresh

    def test_cursor_only_moves_forward(
        self, logged_in_client, db_session, seeded_permissions, admin_user
    ):
        """A second call with an older timestamp must NOT move the cursor back."""
        # First call — advance to a future timestamp
        future_ts = 2_000_000_000
        logged_in_client.post(self.URL, json={"up_to": future_ts})

        # Second call — try to roll back with an older timestamp
        old_ts = 1_000_000_000
        resp = logged_in_client.post(self.URL, json={"up_to": old_ts})

        assert resp.status_code == 200
        payload = resp.get_json()["data"]
        # The cursor should still be at future_ts, not rolled back
        assert payload["last_seen_ts"] == future_ts

    def test_invalid_up_to_type_returns_400(
        self, logged_in_client, db_session, seeded_permissions, admin_user
    ):
        """Passing a non-numeric `up_to` value should return 400."""
        resp = logged_in_client.post(self.URL, json={"up_to": "not-a-timestamp"})
        assert resp.status_code == 400

    def test_mark_read_empty_body_succeeds(
        self, logged_in_client, db_session, seeded_permissions, admin_user
    ):
        """Sending no JSON body at all should be treated the same as {}."""
        resp = logged_in_client.post(self.URL)
        # May not have Content-Type: application/json but silent=True handles it
        assert resp.status_code == 200

    def test_previous_ts_reflects_prior_cursor_state(
        self, logged_in_client, db_session, seeded_permissions, admin_user
    ):
        """The `previous_last_seen_ts` in the response should match the old cursor."""
        first_ts = 1_600_000_000
        second_ts = 1_700_000_000

        logged_in_client.post(self.URL, json={"up_to": first_ts})
        resp = logged_in_client.post(self.URL, json={"up_to": second_ts})

        payload = resp.get_json()["data"]
        assert payload["previous_last_seen_ts"] == first_ts
        assert payload["last_seen_ts"] == second_ts

    # ── Integration: mark-read affects get_notifications is_read flags ─────────

    def test_mark_read_then_get_shows_notifications_as_read(
        self, logged_in_client, db_session, seeded_permissions, admin_user
    ):
        """
        After marking read up to ts X, notifications with timestamp <= X
        should have is_read=True in subsequent GET responses.
        """
        old_ts = 999_000
        new_ts = 1_001_000

        fake_notifications = [
            {"timestamp": old_ts, "host_name": "old-host"},   # will be read
            {"timestamp": new_ts, "host_name": "new-host"},   # will be unread
        ]

        # Mark read up to a point between old_ts and new_ts
        mark_ts = 1_000_000
        logged_in_client.post(self.URL, json={"up_to": mark_ts})

        with patch(_PATCH_NOTIF_RANGE, return_value=fake_notifications):
            resp = logged_in_client.get("/api/system/notifications")

        assert resp.status_code == 200
        notifications = resp.get_json()["data"]["notifications"]

        by_host = {n["host_name"]: n for n in notifications}
        assert by_host["old-host"]["is_read"] is True
        assert by_host["new-host"]["is_read"] is False


# ══════════════════════════════════════════════════════════════════════════════
# normalize_notification / collapse_repeats
# ══════════════════════════════════════════════════════════════════════════════

from app.nagios.notifications import collapse_repeats, normalize_notification


class TestNormalizeNotification:
    def test_reads_alias_keys(self):
        n = normalize_notification({
            "host_name": "h1", "service_description": "ssh", "contact_name": "bob",
            "notification_reason": "down", "plugin_output": "boom",
        })
        assert (n["hostname"], n["servicedesc"], n["contact"]) == ("h1", "ssh", "bob")
        assert (n["state"], n["output"]) == ("DOWN", "boom")

    def test_missing_fields_stay_empty(self):
        n = normalize_notification({"timestamp": 1})
        assert n["hostname"] == "" and n["servicedesc"] is None and n["output"] == ""


class TestCollapseRepeats:
    @staticmethod
    def _n(ts, host="h1", state="DOWN", service=None):
        return {"timestamp": ts, "hostname": host, "servicedesc": service, "state": state}

    def test_same_state_collapses_with_count(self):
        out = collapse_repeats([self._n(1), self._n(2), self._n(3)])
        assert len(out) == 1
        assert out[0]["repeat_count"] == 3
        assert (out[0]["timestamp"], out[0]["first_timestamp"]) == (3, 1)

    def test_state_change_starts_new_entry(self):
        out = collapse_repeats([self._n(1), self._n(2, state="UP"), self._n(3)])
        assert [o["state"] for o in out] == ["DOWN", "UP", "DOWN"]

    def test_different_hosts_and_services_stay_separate(self):
        out = collapse_repeats([self._n(1), self._n(2, host="h2"), self._n(3, service="ssh")])
        assert len(out) == 3

    def test_blank_host_is_never_collapsed(self):
        out = collapse_repeats([self._n(1, host=""), self._n(2, host="")])
        assert len(out) == 2
