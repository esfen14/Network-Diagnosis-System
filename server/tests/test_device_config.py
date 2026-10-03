"""
tests/test_device_config.py — How device identity reaches the generated Nagios
config (Phase 1 and 3 of "spec files/DHCP_Device_Identity_Plan.md", section 10).

Covers which devices are loaded, the stable host_name, the inactive config for
a device whose address is unknown, skipping validate/apply/reload when nothing
changed, and the single config-writer lock. Nagios itself is never run.
"""
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from app.network_discovery import create_host_cfg
from app.network_discovery.create_host_cfg import (
    _create_host_cfg_file,
    _load_monitored_hosts,
    config_fingerprint,
    config_unchanged,
    config_write_lock,
    regenerate_and_apply_config,
)
from app.network_discovery.host_config_templates import create_host, create_service
from app.system_models import DeviceState, NetworkDiscovery
from tests.identity_helpers import (
    MAC_1, MAC_2, NET, all_devices, make_status, patched_config, run_scan, scan,
)
from tests.test_create_host_cfg import make_host, services_by_host


# ==========================================================
# WHICH DEVICES ARE LOADED
# ==========================================================

class TestLoadedDevices:

    def test_host_name_is_the_stable_nagios_name_not_the_dns_name(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1, hostname="Fridge.lan", tcp={22: "ssh"}))

        host = _load_monitored_hosts()[NET]["10.0.0.5"]

        assert host["data"]["hostname"] == "fridge.lan"
        assert host["data"]["address"] == "10.0.0.5"
        assert host["data"]["active_checks_enabled"] is True

    def test_moved_device_is_loaded_at_its_new_address_with_the_same_name(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1, hostname="fridge.lan"))
        run_scan(db_session, status, scan("10.0.0.99", mac=MAC_1, hostname="fridge.lan"))

        hosts = _load_monitored_hosts()[NET]

        assert list(hosts) == ["10.0.0.99"]
        assert hosts["10.0.0.99"]["data"]["hostname"] == "fridge.lan"

    @pytest.mark.parametrize("state, loaded", [
        (DeviceState.ACTIVE, True),
        (DeviceState.MISSING, True),
        (DeviceState.ADDRESS_UNKNOWN, True),
        (DeviceState.RETIRED, False),
        (DeviceState.MERGED, False),
    ])
    def test_device_states_in_the_config(self, db_session, admin_user, state, loaded):
        status = make_status(db_session, admin_user)
        device = run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1))[(NET, "10.0.0.5")]
        device.Device_State = state
        db_session.session.commit()

        assert bool(_load_monitored_hosts()) is loaded

    def test_address_unknown_device_has_active_checks_disabled(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        device = run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1))[(NET, "10.0.0.5")]
        device.Device_State = DeviceState.ADDRESS_UNKNOWN
        db_session.session.commit()

        host = _load_monitored_hosts()[NET]["10.0.0.5"]

        assert host["data"]["active_checks_enabled"] is False

    def test_two_devices_sharing_an_ip_are_both_loaded(self, db_session, admin_user):
        """After IP reuse the old device (address unknown) and the new one share an IP."""
        status = make_status(db_session, admin_user)
        old = run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1))[(NET, "10.0.0.5")]
        run_scan(db_session, status, scan("10.0.0.5", mac=MAC_2))
        assert old.Device_State is DeviceState.ADDRESS_UNKNOWN

        hosts = _load_monitored_hosts()[NET]

        assert len(hosts) == 2
        assert {h["data"]["address"] for h in hosts.values()} == {"10.0.0.5"}
        assert {h["data"]["active_checks_enabled"] for h in hosts.values()} == {True, False}


# ==========================================================
# WHAT THE CONFIG FILE SAYS
# ==========================================================

class TestGeneratedFile:

    def test_address_unknown_host_and_its_services_are_not_checked(self, app, db_session, admin_user, tmp_path):
        status = make_status(db_session, admin_user)
        old = run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1, tcp={22: "ssh"}))[(NET, "10.0.0.5")]
        old.Device_State = DeviceState.ADDRESS_UNKNOWN
        db_session.session.commit()

        with patched_config(app, HOST_CONFIG_DIR=tmp_path):
            text = _create_host_cfg_file(_load_monitored_hosts()).read_text()

        host_block = text.split("define host {")[1].split("}")[0]
        service_block = text.split("define service {")[1].split("}")[0]
        for block in (host_block, service_block):
            assert "active_checks_enabled           0" in block
            assert "Address unknown" in block

    def test_normal_host_keeps_active_checks(self, app, db_session, admin_user, tmp_path):
        status = make_status(db_session, admin_user)
        run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1, tcp={22: "ssh"}))

        with patched_config(app, HOST_CONFIG_DIR=tmp_path):
            text = _create_host_cfg_file(_load_monitored_hosts()).read_text()

        assert "active_checks_enabled" not in text

    def test_config_uses_the_stable_name_and_current_address(self, app, db_session, admin_user, tmp_path):
        status = make_status(db_session, admin_user)
        run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1, hostname="fridge.lan", tcp={22: "ssh"}))
        run_scan(db_session, status, scan("10.0.0.99", mac=MAC_1, hostname="fridge.lan", tcp={22: "ssh"}))

        with patched_config(app, HOST_CONFIG_DIR=tmp_path):
            text = _create_host_cfg_file(_load_monitored_hosts()).read_text()

        assert "host_name                       fridge.lan" in text
        assert "address                         10.0.0.99" in text
        assert "10.0.0.5" not in text.replace("10.0.0.5.", "")  # the old IP is gone
        assert set(services_by_host(text)["fridge.lan"]) == {"ssh-22"}

    def test_template_helpers_render_inactive_objects(self):
        host = create_host({"host_name": "h", "alias": "a", "address": "1.2.3.4", "contact_groups": "g",
                            "active_checks_enabled": False, "notes": "n"})
        service = create_service({"host_name": "h", "service_name": "s", "contact_groups": "g",
                                  "active_checks_enabled": False}, "cmd")

        assert host.rstrip().endswith("}")
        assert "active_checks_enabled           0" in host
        assert "notes                           n" in host
        assert "active_checks_enabled           0" in service
        assert "active_checks_enabled" not in create_host(
            {"host_name": "h", "alias": "a", "address": "1.2.3.4", "contact_groups": "g"})


# ==========================================================
# SKIP APPLY WHEN NOTHING CHANGED
# ==========================================================

class TestSkipWhenUnchanged:

    def test_fingerprint_ignores_the_timestamp_line(self):
        a = "        # generated at 01-01-2026-10-00\ndefine host {\n}\n"
        b = "        # generated at 02-02-2027-23-59\ndefine host {\n}\n"
        c = "        # generated at 02-02-2027-23-59\ndefine host {\n  x\n}\n"

        assert config_fingerprint(a) == config_fingerprint(b)
        assert config_fingerprint(a) != config_fingerprint(c)

    def test_config_unchanged_compares_against_the_live_file(self, app, tmp_path):
        live = tmp_path / "hosts.cfg"
        live.write_text("# generated at 1\nbody\n")
        same = tmp_path / "same.cfg"
        same.write_text("# generated at 2\nbody\n")
        different = tmp_path / "different.cfg"
        different.write_text("# generated at 2\nother\n")

        with patched_config(app, NAGIOS_HOST_CFG=live):
            assert config_unchanged(same) is True
            assert config_unchanged(different) is False

    def test_missing_live_file_counts_as_changed(self, app, tmp_path):
        candidate = tmp_path / "new.cfg"
        candidate.write_text("x")

        with patched_config(app, NAGIOS_HOST_CFG=tmp_path / "missing.cfg"):
            assert config_unchanged(candidate) is False

    def test_regenerate_skips_validate_apply_and_reload_when_unchanged(self, app, db_session, admin_user, tmp_path):
        status = make_status(db_session, admin_user)
        run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1, hostname="fridge.lan", tcp={22: "ssh"}))
        live = tmp_path / "hosts.cfg"

        with patched_config(app, HOST_CONFIG_DIR=tmp_path / "gen", NAGIOS_HOST_CFG=live):
            live.write_text(_create_host_cfg_file(_load_monitored_hosts()).read_text())
            with patch.object(create_host_cfg, "_validate_config") as validate, \
                 patch.object(create_host_cfg, "_apply_new_host_cfg") as apply:
                changed, message = regenerate_and_apply_config()

        assert changed is False
        assert "unchanged" in message
        validate.assert_not_called()
        apply.assert_not_called()

    def test_regenerate_applies_when_something_changed(self, app, db_session, admin_user, tmp_path):
        status = make_status(db_session, admin_user)
        run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1, hostname="fridge.lan", tcp={22: "ssh"}))
        live = tmp_path / "hosts.cfg"
        live.write_text("# an older config\n")

        with patched_config(app, HOST_CONFIG_DIR=tmp_path / "gen", NAGIOS_HOST_CFG=live):
            with patch.object(create_host_cfg, "_validate_config", return_value=(True, "ok")) as validate, \
                 patch.object(create_host_cfg, "_apply_new_host_cfg", return_value=(True, "applied")) as apply:
                changed, message = regenerate_and_apply_config()

        assert (changed, message) == (True, "applied")
        validate.assert_called_once()
        apply.assert_called_once()

    def test_regenerate_does_not_apply_an_invalid_config(self, app, db_session, admin_user, tmp_path):
        status = make_status(db_session, admin_user)
        run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1, tcp={22: "ssh"}))
        live = tmp_path / "hosts.cfg"
        live.write_text("# an older config\n")

        with patched_config(app, HOST_CONFIG_DIR=tmp_path / "gen", NAGIOS_HOST_CFG=live):
            with patch.object(create_host_cfg, "_validate_config", return_value=(False, "bad object")), \
                 patch.object(create_host_cfg, "_apply_new_host_cfg") as apply:
                changed, message = regenerate_and_apply_config()

        assert changed is False
        assert "bad object" in message
        apply.assert_not_called()


# ==========================================================
# ONE WRITER AT A TIME
# ==========================================================

class TestConfigWriteLock:

    def test_regenerate_holds_the_lock_while_it_loads_and_applies(self, app, tmp_path):
        held = []

        def load():
            held.append(("load", config_write_lock._is_owned()))
            return {}

        def apply(_path):
            held.append(("apply", config_write_lock._is_owned()))
            return True, "ok"

        live = tmp_path / "hosts.cfg"
        live.write_text("different")
        candidate = tmp_path / "candidate.cfg"
        candidate.write_text("candidate")
        with app.app_context(), patched_config(app, NAGIOS_HOST_CFG=live), \
             patch.object(create_host_cfg, "_load_monitored_hosts", side_effect=load), \
             patch.object(create_host_cfg, "_create_host_cfg_file", return_value=candidate), \
             patch.object(create_host_cfg, "_validate_config", return_value=(True, "")), \
             patch.object(create_host_cfg, "_apply_new_host_cfg", side_effect=apply):
            regenerate_and_apply_config()

        assert held == [("load", True), ("apply", True)]
        assert not config_write_lock._is_owned()

    def test_a_second_writer_waits_for_the_first(self, app, tmp_path):
        events = []
        first_inside = threading.Event()
        release_first = threading.Event()
        live = tmp_path / "hosts.cfg"
        live.write_text("different")

        def load():
            name = threading.current_thread().name
            events.append(f"{name} start")
            if name == "first":
                first_inside.set()
                assert release_first.wait(5)
            events.append(f"{name} end")
            return {}

        def writer():
            with app.app_context():
                regenerate_and_apply_config()

        # No database in these threads: an in-memory SQLite is per-connection.
        candidate = tmp_path / "candidate.cfg"
        candidate.write_text("candidate")

        with patched_config(app, NAGIOS_HOST_CFG=live), \
             patch.object(create_host_cfg, "_load_monitored_hosts", side_effect=load), \
             patch.object(create_host_cfg, "_create_host_cfg_file", return_value=candidate), \
             patch.object(create_host_cfg, "_validate_config", return_value=(True, "")), \
             patch.object(create_host_cfg, "_apply_new_host_cfg", return_value=(True, "ok")):
            first = threading.Thread(target=writer, name="first")
            second = threading.Thread(target=writer, name="second")
            first.start()
            assert first_inside.wait(5)
            second.start()
            second.join(0.3)
            assert second.is_alive(), "second writer must wait while the first holds the lock"
            release_first.set()
            first.join(5)
            second.join(5)

        assert events == ["first start", "first end", "second start", "second end"]


# ==========================================================
# THE WHOLE DISCOVERY FLOW
# ==========================================================

class TestDiscoveryFlow:
    """discover_network_create_hosts() end to end, with nmap and Nagios mocked."""

    def run_flow(self, app, admin_user, tmp_path, unchanged):
        from app.system_models import NetworkDiscoveryStatus
        import sqlalchemy as sa
        from app import db

        live = tmp_path / "hosts.cfg"
        live.write_text("# live\n")
        scanned = scan("10.0.0.5", mac=MAC_1, hostname="fridge.lan", tcp={22: "ssh"})

        with patched_config(app, HOST_CONFIG_DIR=tmp_path / "gen", NAGIOS_HOST_CFG=live), \
             patch.object(create_host_cfg, "discover_network", return_value=scanned), \
             patch.object(create_host_cfg, "collect_identifiers", return_value=[]), \
             patch.object(create_host_cfg, "get_monitoring_server_ips", return_value=set()), \
             patch.object(create_host_cfg, "config_unchanged", return_value=unchanged), \
             patch.object(create_host_cfg, "_validate_config", return_value=(True, "ok")) as validate, \
             patch.object(create_host_cfg, "_apply_new_host_cfg", return_value=(True, "applied")) as apply:
            create_host_cfg.discover_network_create_hosts(app, admin_user.UserID, threading.Event())

        status = db.session.scalars(
            sa.select(NetworkDiscoveryStatus).order_by(NetworkDiscoveryStatus.DiscoveryStatusID.desc())
        ).first()
        return status, validate, apply

    def test_unchanged_config_is_not_validated_applied_or_reloaded(self, app, db_session, admin_user, tmp_path):
        status, validate, apply = self.run_flow(app, admin_user, tmp_path, unchanged=True)

        assert status.Status.name == "SUCCESS"
        assert "unchanged" in status.Message
        validate.assert_not_called()
        apply.assert_not_called()
        assert [d.Nagios_Host_Name for d in all_devices()] == ["fridge.lan"]

    def test_changed_config_is_validated_and_applied(self, app, db_session, admin_user, tmp_path):
        status, validate, apply = self.run_flow(app, admin_user, tmp_path, unchanged=False)

        assert status.Status.name == "SUCCESS"
        validate.assert_called_once()
        apply.assert_called_once()
