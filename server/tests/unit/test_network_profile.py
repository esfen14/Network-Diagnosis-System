from app.system_models import ActivityLog
from app.api.system.log import _describe_activity

PROFILE = {
    "name": "Main Campus",
    "reference": "#X1",
    "details": [
        {"label": "IP Range", "value": "10.0.0.1 - 10.0.0.254"},
        {"label": "ISP", "value": "Globe"},
    ],
}


class TestNetworkProfile:
    def test_requires_login(self, client, db_session):
        assert client.get("/api/system/network-profile").status_code in (401, 302)

    def test_defaults_until_saved(self, logged_in_client, db_session):
        data = logged_in_client.get("/api/system/network-profile").get_json()["data"]
        assert data["name"] == "CICT Network"
        assert [d["label"] for d in data["details"]][0] == "IP Range"
        assert data["reference"] == ""
        assert all(d["value"] == "" for d in data["details"])

    def test_save_round_trip(self, logged_in_client, db_session):
        assert logged_in_client.put("/api/system/network-profile", json=PROFILE).status_code == 200
        data = logged_in_client.get("/api/system/network-profile").get_json()["data"]
        assert data["name"] == "Main Campus"
        assert data["reference"] == "#X1"
        values = {d["label"]: d["value"] for d in data["details"]}
        assert values["IP Range"] == "10.0.0.1 - 10.0.0.254"
        assert values["ISP"] == "Globe"
        assert values["Location"] == ""

    def test_save_is_logged(self, logged_in_client, db_session):
        logged_in_client.put("/api/system/network-profile", json=PROFILE)
        actions = [a.Action_Type for a in db_session.session.query(ActivityLog).all()]
        assert "Updated network profile 'Main Campus'" in actions

    def test_blank_name_rejected(self, logged_in_client, db_session):
        assert logged_in_client.put("/api/system/network-profile", json={**PROFILE, "name": "  "}).status_code == 400

    def test_unknown_field_rejected(self, logged_in_client, db_session):
        bad = {**PROFILE, "details": [{"label": "Nope", "value": "x"}]}
        assert logged_in_client.put("/api/system/network-profile", json=bad).status_code == 400

    def test_too_long_value_rejected(self, logged_in_client, db_session):
        bad = {**PROFILE, "details": [{"label": "ISP", "value": "x" * 101}]}
        assert logged_in_client.put("/api/system/network-profile", json=bad).status_code == 400

    def test_edit_needs_discovery_permission(self, limited_client, db_session):
        assert limited_client.put("/api/system/network-profile", json=PROFILE).status_code == 403


class TestActivityDescriptions:
    def test_new_style_entry_keeps_its_sentence(self):
        title, description = _describe_activity("Enabled plugin 'check_http'")
        assert title == "Plugin enabled"
        assert description == "Enabled plugin 'check_http'"

    def test_legacy_plugin_code_is_translated(self):
        title, description = _describe_activity("plugin.enable")
        assert title == "Enabled a plugin"
        assert "plugin.enable" not in description

    def test_failed_login_is_explained(self):
        title, description = _describe_activity("Failed login attempt")
        assert title == "Failed sign in"
        assert "wrong password" in description

    def test_unknown_text_passes_through(self):
        assert _describe_activity("Something else") == ("Something else", "Something else")
