"""History and acknowledgements follow a service through the naming change."""

import sqlalchemy as sa

from app import db
from app.history_models import ServiceStatus
from app.network_discovery import create_host_cfg
from app.network_discovery.service_name_migration import (
    legacy_name_map,
    legacy_service_names,
    migrate_legacy_service_history,
)
from app.system_models import AlertAcknowledgement
from tests.seed_helpers import _make_service


class TestLegacyNames:

    def test_candidates_cover_bare_protocol_and_port_forms(self):
        assert legacy_service_names("dns-53-tcp") == {"dns", "dns-tcp", "dns-53-tcp"} - {"dns-53-tcp"}
        assert "ncpa-cpu-tcp" in legacy_service_names("ncpa-cpu-5693-tcp")

    def test_ambiguous_bare_name_is_not_mapped(self):
        mapping = legacy_name_map(["ssh-22-tcp", "ssh-22-udp"])
        assert "ssh" not in mapping
        assert mapping["ssh-tcp"] == "ssh-22-tcp"

    def test_names_already_in_the_new_format_are_not_remapped(self):
        assert legacy_name_map(["http-80-tcp", "http-80-tcp-81-tcp"]) .get("http-80-tcp") is None


class TestMigration:

    def statuses(self, host):
        return sorted(db.session.scalars(
            sa.select(ServiceStatus.Service).where(ServiceStatus.Hostname == host)).all())

    def test_legacy_status_rows_are_renamed(self, db_session):
        _make_service(db_session, hostname="h1", service="ssh")
        _make_service(db_session, hostname="h1", service="dns-TCP")
        _make_service(db_session, hostname="h2", service="ssh")
        db.session.commit()

        renamed = migrate_legacy_service_history({"h1": ["ssh-22-tcp", "dns-53-tcp"]})
        db.session.commit()

        assert renamed == 2
        assert self.statuses("h1") == ["dns-53-tcp", "ssh-22-tcp"]
        assert self.statuses("h2") == ["ssh"]

    def test_apply_carries_history_over(self, app, db_session, tmp_path):
        from unittest.mock import MagicMock, patch
        from tests.test_device_config import patched_config
        _make_service(db_session, hostname="h1", service="ssh")
        db.session.commit()
        live = tmp_path / "hosts.cfg"
        live.write_text("OLD")
        candidate = tmp_path / "candidate.cfg"
        candidate.write_text("NEW")
        create_host_cfg._last_generated_names = {"h1": ["ssh-22-tcp"]}
        with patched_config(app, NAGIOS_HOST_CFG=live, BACKUP_DIR=tmp_path / "b"), \
             patch.object(create_host_cfg.subprocess, "run",
                          return_value=MagicMock(returncode=0, stdout="", stderr="")):
            ok, _ = create_host_cfg._apply_new_host_cfg(candidate)

        assert ok is True
        assert self.statuses("h1") == ["ssh-22-tcp"]
