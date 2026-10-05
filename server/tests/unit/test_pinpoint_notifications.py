from datetime import datetime, timezone
from unittest.mock import patch

from app.system_models import ActivityLog, DiscoveryStatus, NetworkDiscoveryStatus

NOW = datetime.now(timezone.utc)
NAGIOS_ITEM = {
    "timestamp": int(NOW.timestamp()) - 60,
    "hostname": "web1",
    "service_description": "HTTP",
    "output": "Connection refused",
    "notification_reason": "CRITICAL",
}


def _scan(db_session, admin_user, status, message, error=None):
    log = ActivityLog(Action_Type="Discovering Network Hosts", UserID=admin_user.UserID)
    db_session.session.add(log)
    db_session.session.flush()
    row = NetworkDiscoveryStatus(
        Status=status, Progress=100, Message=message, Error=error,
        Completed_At=NOW.replace(tzinfo=None), LogID=log.LogID,
    )
    db_session.session.add(row)
    db_session.session.commit()
    return row


def _patch_nagios():
    return (
        patch("app.api.system.notifications.request_notifications_range", return_value=[NAGIOS_ITEM]),
        patch("app.api.system.history.request_notifications_range", return_value=[NAGIOS_ITEM]),
    )


class TestBellFeed:
    def test_items_are_tagged_by_source(self, logged_in_client, db_session, admin_user):
        _scan(db_session, admin_user, DiscoveryStatus.SUCCESS, "New host.cfg successfully applied")
        _scan(db_session, admin_user, DiscoveryStatus.FAILED, "Config failed to validate", error="bad config")
        p1, p2 = _patch_nagios()
        with p1, p2:
            data = logged_in_client.get("/api/system/notifications").get_json()["data"]
        by_source = {}
        for item in data["notifications"]:
            by_source.setdefault(item["source"], []).append(item)
        assert len(by_source["nagios"]) == 1
        states = {i["state"] for i in by_source["pinpoint"]}
        assert states == {"SUCCESS", "FAILED"}
        failed = next(i for i in by_source["pinpoint"] if i["state"] == "FAILED")
        assert "bad config" in failed["message"]

    def test_running_scans_are_not_notifications(self, logged_in_client, db_session, admin_user):
        log = ActivityLog(Action_Type="Discovering Network Hosts", UserID=admin_user.UserID)
        db_session.session.add(log)
        db_session.session.flush()
        db_session.session.add(NetworkDiscoveryStatus(
            Status=DiscoveryStatus.RUNNING, Progress=10, Message="working", LogID=log.LogID,
        ))
        db_session.session.commit()
        p1, p2 = _patch_nagios()
        with p1, p2:
            data = logged_in_client.get("/api/system/notifications").get_json()["data"]
        assert [i["source"] for i in data["notifications"]] == ["nagios"]


class TestHistory:
    def test_history_lists_both_sources_and_filters(self, logged_in_client, db_session, admin_user):
        _scan(db_session, admin_user, DiscoveryStatus.SUCCESS, "done")
        p1, p2 = _patch_nagios()
        with p1, p2:
            both = logged_in_client.get("/api/system/history/notifications?preset=24h").get_json()["data"]
            only_pp = logged_in_client.get(
                "/api/system/history/notifications?preset=24h&source=pinpoint"
            ).get_json()["data"]
            only_nagios = logged_in_client.get(
                "/api/system/history/notifications?preset=24h&source=nagios"
            ).get_json()["data"]
        assert {i["source"] for i in both["items"]} == {"nagios", "pinpoint"}
        assert [i["source"] for i in only_pp["items"]] == ["pinpoint"]
        assert only_pp["items"][0]["type"] == "scan"
        assert [i["source"] for i in only_nagios["items"]] == ["nagios"]

    def test_host_filter_excludes_pinpoint(self, logged_in_client, db_session, admin_user):
        _scan(db_session, admin_user, DiscoveryStatus.SUCCESS, "done")
        p1, p2 = _patch_nagios()
        with p1, p2:
            data = logged_in_client.get(
                "/api/system/history/notifications?preset=24h&hostname=web1"
            ).get_json()["data"]
        assert [i["source"] for i in data["items"]] == ["nagios"]

    def test_invalid_source_rejected(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/history/notifications?preset=24h&source=bogus")
        assert resp.status_code == 400

    def test_pinpoint_detail(self, logged_in_client, db_session, admin_user):
        row = _scan(db_session, admin_user, DiscoveryStatus.FAILED, "Config not applied", error="reload failed")
        resp = logged_in_client.get(
            f"/api/system/history/notifications/detail?source=pinpoint&id={row.DiscoveryStatusID}"
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["source"] == "pinpoint"
        assert data["state"] == "FAILED"
        assert "reload failed" in data["message"]

    def test_pinpoint_detail_unknown_id(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/system/history/notifications/detail?source=pinpoint&id=999")
        assert resp.status_code == 404


class TestNagiosUnavailable:
    def test_scan_results_still_listed_when_nagios_is_down(self, logged_in_client, db_session, admin_user):
        _scan(db_session, admin_user, DiscoveryStatus.SUCCESS, "done")
        with patch("app.api.system.notifications.request_notifications_range", return_value=None), \
                patch("app.api.system.history.request_notifications_range", return_value=None):
            feed = logged_in_client.get("/api/system/notifications")
            history = logged_in_client.get("/api/system/history/notifications?preset=24h")
        assert feed.status_code == 200
        assert [i["source"] for i in feed.get_json()["data"]["notifications"]] == ["pinpoint"]
        assert history.status_code == 200
        assert history.get_json()["data"]["nagios_unavailable"] is True

    def test_still_502_when_nagios_is_down_and_nothing_else_exists(self, logged_in_client, db_session):
        with patch("app.api.system.notifications.request_notifications_range", return_value=None), \
                patch("app.api.system.history.request_notifications_range", return_value=None):
            assert logged_in_client.get("/api/system/notifications").status_code == 502
            assert logged_in_client.get("/api/system/history/notifications?preset=24h").status_code == 502
