from unittest.mock import patch

from app.system_models import ActivityLog, NetworkDiscovery, NetworkDiscoveryStatus, DiscoveryStatus, Open_UDP_Services
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
        editable = {d["label"]: d["value"] for d in data["details"] if not d["derived"]}
        assert editable == {"ISP": "", "Location": ""}

    def test_save_round_trip(self, logged_in_client, db_session):
        assert logged_in_client.put("/api/system/network-profile", json=PROFILE).status_code == 200
        data = logged_in_client.get("/api/system/network-profile").get_json()["data"]
        assert data["name"] == "Main Campus"
        assert data["reference"] == "#X1"
        values = {d["label"]: d["value"] for d in data["details"]}
        assert values["IP Range"] != "10.0.0.1 - 10.0.0.254"  # derived, the submitted value is ignored
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


def _seed_devices(db_session, user_id):
    log = ActivityLog(Action_Type="test", UserID=user_id)
    db_session.session.add(log)
    db_session.session.flush()
    status = NetworkDiscoveryStatus(Status=DiscoveryStatus.SUCCESS, Progress=100, Message="done", LogID=log.LogID)
    db_session.session.add(status)
    db_session.session.flush()
    devices = {}
    for name, ip in (("router", "10.0.0.1"), ("dns1", "10.0.0.53"), ("pc", "10.0.0.20")):
        devices[name] = NetworkDiscovery(
            Hostname=name, IP_Address=ip, Network="10.0.0.0/24", DiscoveryStatusID=status.DiscoveryStatusID
        )
        db_session.session.add(devices[name])
    db_session.session.flush()
    db_session.session.add(Open_UDP_Services(Port_Number=53, Service_Name="domain", NetDiscoveryID=devices["dns1"].NetDiscoveryID))
    db_session.session.commit()


class TestDerivedDetails:
    def _values(self, client):
        data = client.get("/api/system/network-profile").get_json()["data"]
        return {d["label"]: d for d in data["details"]}

    def test_derived_from_scan_settings_and_devices(self, logged_in_client, db_session, admin_user):
        _seed_devices(db_session, admin_user.UserID)
        with patch("app.api.system.network_profile.get_discovery_setting", return_value=["10.0.0.0/24"]), \
             patch("app.api.system.network_profile._local_default_gateway", return_value=None):
            values = self._values(logged_in_client)
        assert values["IP Range"]["value"] == "10.0.0.1 - 10.0.0.254"
        assert values["Subnet Mask"]["value"] == "255.255.255.0"
        assert values["Gateway Device"]["value"] == "router - 10.0.0.1"
        assert values["DNS Server"]["value"] == "dns1 - 10.0.0.53"
        assert all(values[label]["derived"] for label in ("IP Range", "Subnet Mask", "Gateway Device", "DNS Server"))
        assert not values["ISP"]["derived"] and not values["Location"]["derived"]

    def test_not_detected_without_devices(self, logged_in_client, db_session):
        with patch("app.api.system.network_profile.get_discovery_setting", return_value=["10.0.0.0/24"]), \
             patch("app.api.system.network_profile._local_default_gateway", return_value=None):
            values = self._values(logged_in_client)
        assert values["Gateway Device"]["value"] == "Not detected"
        assert values["DNS Server"]["value"] == "Not detected"

    def test_derived_values_are_not_stored(self, logged_in_client, db_session):
        payload = {**PROFILE, "details": [{"label": "Subnet Mask", "value": "1.2.3.4"}, {"label": "ISP", "value": "Globe"}]}
        assert logged_in_client.put("/api/system/network-profile", json=payload).status_code == 200
        from app.system_models import NetworkProfile
        assert db_session.session.get(NetworkProfile, 1).Details == {"ISP": "Globe"}


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
