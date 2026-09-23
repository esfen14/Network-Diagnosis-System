"""
tests/test_plugin_monitoring_config.py — Tests for Phase 10
(Monitoring Configuration): monitoring_config.py's generate/validate/
apply pipeline + the full GET/POST /plugin/<id>/configurations routes.

Uses real files for generation/directive logic (tmp_path, config
values patched in) and mocks only subprocess.run at the
monitoring_config module boundary for the two calls that genuinely
can't run in a test environment (`nagios -v`, `systemctl reload`) —
same discipline as test_plugin_update.py. Confirmed via extensive
manual end-to-end testing before writing these (including a real
two-plugin, two-target scenario proving the full-rebuild preserves
prior configurations rather than wiping them, and directive
idempotency across repeated applies) — these tests codify exactly
what was already verified by hand.
"""
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.plugin_models import (
    Plugin, PluginType, PluginSource, PluginStatus, PluginCommand,
    PluginConfiguration, PluginConfigurationStatus, PluginHistory,
)
from app.system_models import NetworkDiscovery, NetworkDiscoveryStatus, DiscoveryStatus, ActivityLog
from app.api.plugin.monitoring_config import (
    generate_command_name, render_command_object, generate_plugin_services_cfg,
    ensure_cfg_file_directive,
)


# ─── fixtures / helpers ─────────────────────────────────────────────────────

def _make_activity_log(db_session, user):
    log = ActivityLog(Action_Type="test", UserID=user.UserID)
    db_session.session.add(log)
    db_session.session.flush()
    return log


def _make_target(db_session, user, *, hostname="router-01", ip="192.168.130.10"):
    log = _make_activity_log(db_session, user)
    status = NetworkDiscoveryStatus(Status=DiscoveryStatus.SUCCESS, Progress=100, Message="done", LogID=log.LogID)
    db_session.session.add(status)
    db_session.session.flush()
    device = NetworkDiscovery(Hostname=hostname, IP_Address=ip, Network="192.168.130.0/24", DiscoveryStatusID=status.DiscoveryStatusID)
    db_session.session.add(device)
    db_session.session.flush()
    return device


def _make_plugin(db_session, name, *, status=PluginStatus.ENABLED, command_definition="check_x -H $HOSTADDRESS$", with_command=True):
    plugin = Plugin(Name=name, Plugin_Type=PluginType.NAGIOS, Source=PluginSource.BASELINE_ISO, Status=status)
    db_session.session.add(plugin)
    db_session.session.flush()
    if with_command:
        db_session.session.add(PluginCommand(
            PluginID=plugin.PluginID, Command_Name=name, Command_Definition=command_definition, Is_Default=True,
        ))
    db_session.session.commit()
    return plugin


def _patch_nagios_paths(tmp_path):
    main_cfg = tmp_path / "nagios.cfg"
    main_cfg.write_text(
        "log_file=/usr/local/nagios/var/nagios.log\n"
        "cfg_file=/usr/local/nagios/etc/objects/hosts.cfg\n"
    )
    service_cfg = tmp_path / "objects" / "plugin-services.cfg"
    staging_dir = tmp_path / "staging"
    backup_dir = tmp_path / "backup"
    return {
        "NAGIOS_MAIN_CFG": main_cfg,
        "PLUGIN_SERVICE_CFG": service_cfg,
        "PLUGIN_SERVICE_STAGING_DIR": staging_dir,
        "PLUGIN_SERVICE_BACKUP_DIR": backup_dir,
    }


def _fake_subprocess_success(cmd, **kwargs):
    result = MagicMock()
    result.returncode = 0
    result.stdout = "ok"
    result.stderr = ""
    return result


def _fake_subprocess_validation_fails(cmd, **kwargs):
    result = MagicMock()
    if "-v" in cmd:
        result.returncode = 1
        result.stdout = ""
        result.stderr = "Error: could not parse config"
    else:
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
    return result


from contextlib import contextmanager


@contextmanager
def _patched_config(app, **overrides):
    """Flask's app.config is dict-like, not attribute-based, so
    unittest.mock.patch.multiple can't target it directly — this
    manually saves/restores the overridden keys instead."""
    original = {key: app.config.get(key) for key in overrides}
    app.config.update(overrides)
    try:
        yield
    finally:
        app.config.update(original)


@pytest.fixture
def nagios_paths(app, tmp_path):
    paths = _patch_nagios_paths(tmp_path)
    with _patched_config(app, **paths):
        yield paths


# ─── generate_command_name / render_command_object ─────────────────────────

class TestCommandGeneration:
    def test_command_name_namespaced(self):
        """Confirmed scope: pinpoint_ prefix avoids colliding with
        stock nagios-plugins command names Network Discovery already
        references directly (e.g. check_tcp)."""
        assert generate_command_name("check_snmp") == "pinpoint_check_snmp"

    def test_command_object_contains_name_and_line(self):
        rendered = render_command_object("pinpoint_check_snmp", "check_snmp -H $HOSTADDRESS$")
        assert "command_name    pinpoint_check_snmp" in rendered
        assert "command_line    check_snmp -H $HOSTADDRESS$" in rendered


# ─── generate_plugin_services_cfg ───────────────────────────────────────────

class TestGeneratePluginServicesCfg:
    def test_empty_list_still_valid_header(self):
        content = generate_plugin_services_cfg([])
        assert "generated by PinPoint Plugin Manager" in content

    def test_includes_command_and_service_per_entry(self):
        content = generate_plugin_services_cfg([
            ("router-01", "SNMP Interface Traffic", "pinpoint_check_snmp", "check_snmp -H $HOSTADDRESS$"),
        ])
        assert "command_name    pinpoint_check_snmp" in content
        assert "host_name                   router-01" in content
        assert "service_description         SNMP Interface Traffic" in content
        assert "check_command               pinpoint_check_snmp" in content

    def test_duplicate_command_not_repeated(self):
        """Two services on the same plugin shouldn't produce two
        identical `command` object definitions (Nagios would reject
        a duplicate object)."""
        content = generate_plugin_services_cfg([
            ("router-01", "SNMP A", "pinpoint_check_snmp", "check_snmp -H $HOSTADDRESS$"),
            ("switch-01", "SNMP B", "pinpoint_check_snmp", "check_snmp -H $HOSTADDRESS$"),
        ])
        assert content.count("command_name    pinpoint_check_snmp") == 1
        assert content.count("service_description") == 2


# ─── ensure_cfg_file_directive ──────────────────────────────────────────────

class TestEnsureCfgFileDirective:
    def test_adds_directive_when_missing(self, app, tmp_path):
        paths = _patch_nagios_paths(tmp_path)
        with _patched_config(app, **paths):
            result = ensure_cfg_file_directive()
        assert result is True
        content = paths["NAGIOS_MAIN_CFG"].read_text()
        assert f"cfg_file={paths['PLUGIN_SERVICE_CFG']}" in content

    def test_idempotent_second_call_no_duplicate(self, app, tmp_path):
        paths = _patch_nagios_paths(tmp_path)
        with _patched_config(app, **paths):
            ensure_cfg_file_directive()
            ensure_cfg_file_directive()
        content = paths["NAGIOS_MAIN_CFG"].read_text()
        assert content.count(str(paths["PLUGIN_SERVICE_CFG"])) == 1

    def test_creates_empty_service_cfg_if_missing(self, app, tmp_path):
        paths = _patch_nagios_paths(tmp_path)
        with _patched_config(app, **paths):
            ensure_cfg_file_directive()
        assert paths["PLUGIN_SERVICE_CFG"].exists()

    def test_backs_up_nagios_cfg_before_modifying(self, app, tmp_path):
        paths = _patch_nagios_paths(tmp_path)
        with _patched_config(app, **paths):
            ensure_cfg_file_directive()
        backups = list(paths["PLUGIN_SERVICE_BACKUP_DIR"].glob("nagios-*.cfg"))
        assert len(backups) == 1


# ─── POST /plugin/<id>/configurations ───────────────────────────────────────

class TestApplyConfigurationRoute:
    def test_requires_login(self, client, db_session):
        resp = client.post("/api/plugin/1/configurations", json={"net_discovery_id": 1, "service_description": "x"})
        assert resp.status_code in (401, 302)

    def test_requires_permission(self, limited_client, db_session, admin_user):
        target = _make_target(db_session, admin_user)
        plugin = _make_plugin(db_session, "check_x")
        resp = limited_client.post(
            f"/api/plugin/{plugin.PluginID}/configurations",
            json={"net_discovery_id": target.NetDiscoveryID, "service_description": "x"},
        )
        assert resp.status_code == 403

    def test_plugin_not_found(self, logged_in_client, db_session, admin_user):
        target = _make_target(db_session, admin_user)
        resp = logged_in_client.post(
            "/api/plugin/999999/configurations",
            json={"net_discovery_id": target.NetDiscoveryID, "service_description": "x"},
        )
        assert resp.status_code == 404

    def test_target_not_found(self, logged_in_client, db_session, admin_user):
        plugin = _make_plugin(db_session, "check_x")
        resp = logged_in_client.post(
            f"/api/plugin/{plugin.PluginID}/configurations",
            json={"net_discovery_id": 999999, "service_description": "x"},
        )
        assert resp.status_code == 404

    def test_missing_required_field(self, logged_in_client, db_session, admin_user):
        target = _make_target(db_session, admin_user)
        plugin = _make_plugin(db_session, "check_x")
        resp = logged_in_client.post(
            f"/api/plugin/{plugin.PluginID}/configurations",
            json={"net_discovery_id": target.NetDiscoveryID},
        )
        assert resp.status_code == 400

    def test_no_command_defined(self, logged_in_client, db_session, admin_user, nagios_paths):
        target = _make_target(db_session, admin_user)
        plugin = _make_plugin(db_session, "check_nocmd", with_command=False)
        resp = logged_in_client.post(
            f"/api/plugin/{plugin.PluginID}/configurations",
            json={"net_discovery_id": target.NetDiscoveryID, "service_description": "x"},
        )
        assert resp.status_code == 409

    def test_blocked_plugin_status(self, logged_in_client, db_session, admin_user, nagios_paths):
        target = _make_target(db_session, admin_user)
        plugin = _make_plugin(db_session, "check_failed", status=PluginStatus.VALIDATION_FAILED)
        resp = logged_in_client.post(
            f"/api/plugin/{plugin.PluginID}/configurations",
            json={"net_discovery_id": target.NetDiscoveryID, "service_description": "x"},
        )
        assert resp.status_code == 409

    def test_successful_apply_sets_plugin_active(self, logged_in_client, db_session, admin_user, nagios_paths):
        target = _make_target(db_session, admin_user)
        plugin = _make_plugin(db_session, "check_snmp")

        with patch("app.api.plugin.monitoring_config.subprocess.run", side_effect=_fake_subprocess_success):
            resp = logged_in_client.post(
                f"/api/plugin/{plugin.PluginID}/configurations",
                json={"net_discovery_id": target.NetDiscoveryID, "service_description": "SNMP Interface Traffic"},
            )

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["success"] is True
        assert data["plugin_status"] == "Active"

        db_session.session.refresh(plugin)
        assert plugin.Status == PluginStatus.ACTIVE

        config = db_session.session.execute(
            db_session.select(PluginConfiguration).where(PluginConfiguration.PluginID == plugin.PluginID)
        ).scalar_one()
        assert config.Status == PluginConfigurationStatus.APPLIED
        assert config.NetDiscoveryID == target.NetDiscoveryID

        cfg_content = nagios_paths["PLUGIN_SERVICE_CFG"].read_text()
        assert "router-01" in cfg_content
        assert "SNMP Interface Traffic" in cfg_content
        assert "pinpoint_check_snmp" in cfg_content

    def test_directive_added_to_real_nagios_cfg(self, logged_in_client, db_session, admin_user, nagios_paths):
        target = _make_target(db_session, admin_user)
        plugin = _make_plugin(db_session, "check_snmp")

        with patch("app.api.plugin.monitoring_config.subprocess.run", side_effect=_fake_subprocess_success):
            logged_in_client.post(
                f"/api/plugin/{plugin.PluginID}/configurations",
                json={"net_discovery_id": target.NetDiscoveryID, "service_description": "x"},
            )

        assert str(nagios_paths["PLUGIN_SERVICE_CFG"]) in nagios_paths["NAGIOS_MAIN_CFG"].read_text()

    def test_second_apply_preserves_first_configuration(self, logged_in_client, db_session, admin_user, nagios_paths):
        """Regression test for the core architectural concern this
        phase was built around: the full-rebuild must not wipe out
        prior configurations."""
        target1 = _make_target(db_session, admin_user, hostname="router-01", ip="192.168.130.10")
        target2 = _make_target(db_session, admin_user, hostname="switch-01", ip="192.168.130.11")
        plugin1 = _make_plugin(db_session, "check_snmp")
        plugin2 = _make_plugin(db_session, "check_disk", command_definition="check_disk -w 20% -c 10%")

        with patch("app.api.plugin.monitoring_config.subprocess.run", side_effect=_fake_subprocess_success):
            logged_in_client.post(
                f"/api/plugin/{plugin1.PluginID}/configurations",
                json={"net_discovery_id": target1.NetDiscoveryID, "service_description": "SNMP Traffic"},
            )
            resp = logged_in_client.post(
                f"/api/plugin/{plugin2.PluginID}/configurations",
                json={"net_discovery_id": target2.NetDiscoveryID, "service_description": "Disk Space"},
            )

        assert resp.status_code == 200
        cfg_content = nagios_paths["PLUGIN_SERVICE_CFG"].read_text()
        assert "router-01" in cfg_content
        assert "SNMP Traffic" in cfg_content
        assert "switch-01" in cfg_content
        assert "Disk Space" in cfg_content

        # Directive still added only once, even after two applies.
        assert nagios_paths["NAGIOS_MAIN_CFG"].read_text().count(str(nagios_paths["PLUGIN_SERVICE_CFG"])) == 1

    def test_validation_failure_no_live_changes(self, logged_in_client, db_session, admin_user, nagios_paths):
        target = _make_target(db_session, admin_user)
        plugin = _make_plugin(db_session, "check_snmp")
        original_main_cfg = nagios_paths["NAGIOS_MAIN_CFG"].read_text()

        with patch("app.api.plugin.monitoring_config.subprocess.run", side_effect=_fake_subprocess_validation_fails):
            resp = logged_in_client.post(
                f"/api/plugin/{plugin.PluginID}/configurations",
                json={"net_discovery_id": target.NetDiscoveryID, "service_description": "x"},
            )

        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["success"] is False
        assert data["status"] == "Failed"

        db_session.session.refresh(plugin)
        assert plugin.Status == PluginStatus.ENABLED  # NOT Active

        # nagios.cfg genuinely untouched — the directive step never ran.
        assert nagios_paths["NAGIOS_MAIN_CFG"].read_text() == original_main_cfg

        config = db_session.session.execute(
            db_session.select(PluginConfiguration).where(PluginConfiguration.PluginID == plugin.PluginID)
        ).scalar_one()
        assert config.Status == PluginConfigurationStatus.FAILED

    def test_records_history(self, logged_in_client, db_session, admin_user, nagios_paths):
        target = _make_target(db_session, admin_user)
        plugin = _make_plugin(db_session, "check_snmp")

        with patch("app.api.plugin.monitoring_config.subprocess.run", side_effect=_fake_subprocess_success):
            logged_in_client.post(
                f"/api/plugin/{plugin.PluginID}/configurations",
                json={"net_discovery_id": target.NetDiscoveryID, "service_description": "SNMP"},
            )

        history = db_session.session.execute(
            db_session.select(PluginHistory).where(PluginHistory.PluginID == plugin.PluginID)
        ).scalar_one()
        assert history.Action.value == "Configure"
        assert history.Result.value == "Success"

    def test_reapplying_same_target_updates_not_duplicates(self, logged_in_client, db_session, admin_user, nagios_paths):
        target = _make_target(db_session, admin_user)
        plugin = _make_plugin(db_session, "check_snmp")

        with patch("app.api.plugin.monitoring_config.subprocess.run", side_effect=_fake_subprocess_success):
            logged_in_client.post(
                f"/api/plugin/{plugin.PluginID}/configurations",
                json={"net_discovery_id": target.NetDiscoveryID, "service_description": "SNMP Traffic"},
            )
            logged_in_client.post(
                f"/api/plugin/{plugin.PluginID}/configurations",
                json={"net_discovery_id": target.NetDiscoveryID, "service_description": "SNMP Traffic",
                      "configuration_data": {"warning": 80}},
            )

        configs = db_session.session.execute(
            db_session.select(PluginConfiguration).where(PluginConfiguration.PluginID == plugin.PluginID)
        ).scalars().all()
        assert len(configs) == 1
        assert configs[0].Configuration_Data == {"warning": 80}


# ─── GET /plugin/<id>/configurations ────────────────────────────────────────

class TestListConfigurationsRoute:
    def test_requires_login(self, client, db_session):
        resp = client.get("/api/plugin/1/configurations")
        assert resp.status_code in (401, 302)

    def test_not_found(self, logged_in_client, db_session):
        resp = logged_in_client.get("/api/plugin/999999/configurations")
        assert resp.status_code == 404

    def test_empty_list(self, logged_in_client, db_session):
        plugin = _make_plugin(db_session, "check_x")
        resp = logged_in_client.get(f"/api/plugin/{plugin.PluginID}/configurations")
        assert resp.status_code == 200
        assert resp.get_json()["data"] == []

    def test_lists_applied_configuration(self, logged_in_client, db_session, admin_user, nagios_paths):
        target = _make_target(db_session, admin_user)
        plugin = _make_plugin(db_session, "check_snmp")

        with patch("app.api.plugin.monitoring_config.subprocess.run", side_effect=_fake_subprocess_success):
            logged_in_client.post(
                f"/api/plugin/{plugin.PluginID}/configurations",
                json={"net_discovery_id": target.NetDiscoveryID, "service_description": "SNMP Traffic"},
            )

        resp = logged_in_client.get(f"/api/plugin/{plugin.PluginID}/configurations")
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert len(data) == 1
        assert data[0]["target"]["hostname"] == "router-01"
        assert data[0]["service_description"] == "SNMP Traffic"
        assert data[0]["status"] == "Applied"
