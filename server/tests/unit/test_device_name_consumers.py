"""
tests/unit/test_device_name_consumers.py — Code outside discovery that must use a
device's stable Nagios host name (and record identity) now that the name no
longer equals the DNS name or IP:

- plugin configurations are rendered against the Nagios host_name;
- the hosts-by-OS report maps Nagios snapshots to devices by that name;
- SSH trust confirmation stores the host key as a device identifier.
"""
from unittest.mock import patch

import sqlalchemy as sa

from app import db
from app.api.plugin import service as plugin_service
from app.history_models import HostStateType
from app.plugin_models import Plugin, PluginConfiguration, PluginSource, PluginStatus, PluginType
from app.system_models import IdentifierKind, IdentityConfidence, SSHCredentials
from tests.support.identity_helpers import (
    MAC_1, NET, identifier_values, make_status, review_items, run_scan, scan,
)
from tests.support.seed_helpers import _make_host


def device_named(db_session, status, nagios_name="stable.lan", dns_name="dns.lan", **kwargs):
    device = run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1, hostname=dns_name, **kwargs))[(NET, "10.0.0.5")]
    device.Nagios_Host_Name = nagios_name
    db_session.session.commit()
    return device


class TestPluginServicesUseTheNagiosName:
    """The services a plugin monitors are listed and matched to Nagios results by the stable name."""

    def attach(self, db_session, admin_user, nagios_name):
        from app.plugin_models import PluginConfigurationOrigin, PluginConfigurationStatus
        device = device_named(db_session, make_status(db_session, admin_user), nagios_name=nagios_name)
        plugin = Plugin(Name="check_ssh", Plugin_Type=PluginType.NAGIOS, Source=PluginSource.BASELINE_ISO,
                        Status=PluginStatus.ACTIVE)
        db_session.session.add(plugin)
        db_session.session.flush()
        db_session.session.add(PluginConfiguration(
            PluginID=plugin.PluginID, NetDiscoveryID=device.NetDiscoveryID, Service_Description="ssh-22-tcp",
            Nagios_Service_Name="ssh-22-tcp", Port_Number=22, Protocol="tcp",
            Status=PluginConfigurationStatus.APPLIED, Origin=PluginConfigurationOrigin.AUTO,
        ))
        db_session.session.commit()
        return plugin

    def test_the_listing_shows_the_stable_name_not_the_dns_name(self, db_session, admin_user):
        plugin = self.attach(db_session, admin_user, "stable.lan")

        (item,) = plugin_service.get_plugin_services(plugin.PluginID, 1, 10, "")["items"]

        assert item["device"]["hostname"] == "stable.lan"

    def test_a_device_without_a_stable_name_falls_back_to_the_dns_name(self, db_session, admin_user):
        plugin = self.attach(db_session, admin_user, None)

        (item,) = plugin_service.get_plugin_services(plugin.PluginID, 1, 10, "")["items"]

        assert item["device"]["hostname"] == "dns.lan"


class TestReportUsesTheNagiosName:

    def test_hosts_by_os_matches_snapshots_by_stable_name(self, logged_in_client, db_session, admin_user):
        device_named(db_session, make_status(db_session, admin_user))
        _make_host(db_session, "stable.lan", state=HostStateType.UP)
        db_session.session.commit()

        resp = logged_in_client.get("/api/system/report/hosts-by-os?period=last_24h")

        assert resp.status_code == 200
        groups = {g["os_type"]: g for g in resp.get_json()["data"]["by_os"]}
        assert "Linux" in groups, groups.keys()
        assert [h["hostname"] for h in groups["Linux"]["hosts"]] == ["stable.lan"]


class TestTrustConfirmationRecordsIdentity:

    def confirm(self, client, device, fingerprint):
        with patch("app.api.system.ncpa_deployment.get_host_key_fingerprint", return_value=fingerprint):
            return client.post(f"/api/system/deployment/ncpa/{device.NetDiscoveryID}/confirm-trust",
                               json={"fingerprint": fingerprint})

    def test_host_key_becomes_a_strong_identifier(self, logged_in_client, db_session, admin_user):
        device = device_named(db_session, make_status(db_session, admin_user))
        assert device.Identity_Confidence is IdentityConfidence.LIKELY

        resp = self.confirm(logged_in_client, device, "TRUSTEDKEY")

        assert resp.status_code == 200
        db_session.session.refresh(device)
        assert identifier_values(device, IdentifierKind.SSH_HOST_KEY) == {"TRUSTEDKEY"}
        assert device.Identity_Confidence is IdentityConfidence.VERIFIED
        creds = db.session.scalar(sa.select(SSHCredentials).where(
            SSHCredentials.NetworkDiscoveryID == device.NetDiscoveryID))
        assert creds.Key_Fingerprint == "TRUSTEDKEY"

    def test_confirming_again_does_not_duplicate_the_identifier(self, logged_in_client, db_session, admin_user):
        device = device_named(db_session, make_status(db_session, admin_user))

        self.confirm(logged_in_client, device, "TRUSTEDKEY")
        resp = self.confirm(logged_in_client, device, "TRUSTEDKEY")

        assert resp.status_code == 200
        assert len(identifier_values(device, IdentifierKind.SSH_HOST_KEY)) == 1

    def test_a_key_another_device_owns_is_flagged_not_stolen(self, logged_in_client, db_session, admin_user):
        status = make_status(db_session, admin_user)
        first = device_named(db_session, status)
        other = run_scan(db_session, status, scan("10.0.0.6", mac="00:11:22:33:44:06"))[(NET, "10.0.0.6")]
        self.confirm(logged_in_client, first, "SHAREDKEY")

        resp = self.confirm(logged_in_client, other, "SHAREDKEY")

        assert resp.status_code == 200
        assert identifier_values(first, IdentifierKind.SSH_HOST_KEY) == {"SHAREDKEY"}
        assert identifier_values(other, IdentifierKind.SSH_HOST_KEY) == set()
        assert len(review_items()) == 1
