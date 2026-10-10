"""
tests/unit/test_device_identity.py — Device identity and reconciliation
(app/network_discovery/device_identity.py and _save_discovered_hosts).

Covers Phases 0 and 1 of "docs/plans/DHCP_Device_Identity_Plan.md": the three
Phase 0 bug fixes, one test per row of the section 4 decision table, stable
Nagios host names, the device lifecycle (section 6) and the edge cases of
section 13. Nmap, SSH and Nagios are never touched: scans are plain dicts.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import sqlalchemy as sa

from app import db
from app.network_discovery import create_host_cfg
from app.network_discovery.device_identity import (
    Evidence,
    attach_identifiers,
    build_evidence,
    create_stable_host_name,
    is_hardware_mac,
    nagios_host_name,
    normalize_mac,
    record_device_evidence,
)
from app.ncpa_deployment.ncpa_deployment import mark_device_incompatible
from app.system_models import (
    AddressSource,
    AddressingMode,
    DeviceIdentifier,
    DeviceState,
    IdentifierKind,
    IdentityConfidence,
    NCPADeployment,
    NetworkDiscovery,
    ReviewKind,
    SSHCredentials,
)
from tests.support.identity_helpers import (
    MAC_1, MAC_2, MAC_3, NET, RANDOM_MAC, SSH_1, SSH_2, CERT_1, CERT_2,
    address_rows, all_devices, cert, combine, identifier_values, machine_id,
    make_status, open_addresses, patched_config, review_items, run_scan, scan, ssh,
)


# ==========================================================
# EVIDENCE HELPERS
# ==========================================================

class TestEvidence:
    def test_normalize_mac(self):
        assert normalize_mac("00-11-22-33-44-AA") == "00:11:22:33:44:aa"
        assert normalize_mac("nonsense") is None
        assert normalize_mac(None) is None

    def test_randomized_mac_is_not_hardware(self):
        assert is_hardware_mac(MAC_1)
        assert not is_hardware_mac(RANDOM_MAC)
        assert not is_hardware_mac(None)

    def test_randomized_mac_is_dropped_from_evidence(self):
        assert [e for e in build_evidence(RANDOM_MAC) if e.kind is IdentifierKind.MAC] == []

    def test_dns_name_is_weak_and_unknown_is_ignored(self):
        evidence = build_evidence(None, None, "Printer.Local")
        assert evidence == [Evidence(IdentifierKind.DNS_NAME, "printer.local", False)]
        assert build_evidence(None, None, "Unknown") == []


# ==========================================================
# PHASE 0 — BUGS IN THE OLD SAVE CODE
# ==========================================================

class TestPhaseZeroBugs:

    def test_address_unknown_host_reactivates_when_seen_again_at_same_ip(self, db_session, admin_user):
        """
        A device whose address was temporarily marked unknown must match
        and reactivate when a scan observes that same IP again without
        contradicting identifiers.
        """
        status = make_status(db_session, admin_user)
        discovered = scan("10.77.0.6", hostname="legacy01", tcp={2222: "ssh"})

        first = run_scan(db_session, status, discovered)[(NET, "10.77.0.6")]
        first.Device_State = DeviceState.ADDRESS_UNKNOWN
        db_session.session.commit()

        again = run_scan(db_session, status, discovered)[(NET, "10.77.0.6")]

        assert again.NetDiscoveryID == first.NetDiscoveryID
        assert again.Device_State is DeviceState.ACTIVE
        assert len(all_devices()) == 1

    def test_first_new_linux_host_saves_with_standard_ssh_port(self, db_session, admin_user):
        """Used to raise UnboundLocalError (SSH_Port used before assignment)."""
        status = make_status(db_session, admin_user)

        # Two new Linux hosts in one scan: neither may inherit another's port.
        discovered = combine(
            scan("10.0.0.1", tcp={22: "ssh", 80: "http"}),
            scan("10.0.0.2", tcp={443: "https"}),
        )
        devices = run_scan(db_session, status, discovered)

        assert len(devices) == 2
        creds = db.session.scalars(sa.select(SSHCredentials)).all()
        assert [c.SSH_Port for c in creds] == [22, 22]
        assert all(d.NCPA_Eligible for d in devices.values())

    def test_changed_ip_updates_the_existing_row(self, db_session, admin_user):
        """A MAC match used to keep the old IP, so Nagios kept checking it."""
        status = make_status(db_session, admin_user)
        first = run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1))[(NET, "10.0.0.5")]

        second = run_scan(db_session, status, scan("10.0.0.77", mac=MAC_1))[(NET, "10.0.0.77")]

        assert second.NetDiscoveryID == first.NetDiscoveryID
        assert second.IP_Address == "10.0.0.77"
        assert len(all_devices()) == 1

    def test_rescan_keeps_ncpa_eligibility(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        device = run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1))[(NET, "10.0.0.5")]
        assert device.NCPA_Eligible is True

        device = run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1))[(NET, "10.0.0.5")]

        assert device.NCPA_Eligible is True
        assert len(db.session.scalars(sa.select(NCPADeployment)).all()) == 1

    def test_rescan_does_not_undo_incompatible(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        device = run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1))[(NET, "10.0.0.5")]
        mark_device_incompatible(device.NetDiscoveryID)

        device = run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1))[(NET, "10.0.0.5")]

        assert device.NCPA_Eligible is False

    def test_failed_os_detection_does_not_erase_known_os(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1, os="Linux"))

        device = run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1, os="Unknown"))[(NET, "10.0.0.5")]

        assert device.OS_Type == "Linux"

    def test_save_discovered_hosts_commits_and_skips_the_server_itself(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        discovered = combine(scan("10.0.0.1", mac=MAC_1), scan("10.0.0.2", mac=MAC_2))

        with patch.object(create_host_cfg, "get_monitoring_server_ips", return_value={"10.0.0.1"}):
            saved = create_host_cfg._save_discovered_hosts(discovered, status, 50)

        assert [ip for _net, ip in saved] == ["10.0.0.2"]
        assert [d.IP_Address for d in all_devices()] == ["10.0.0.2"]

    def test_save_discovered_hosts_rolls_back_on_error(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        db_session.session.commit()

        with patch.object(create_host_cfg, "get_monitoring_server_ips", return_value=set()), \
             patch.object(create_host_cfg, "process_device_ports", side_effect=RuntimeError("boom")):
            saved = create_host_cfg._save_discovered_hosts(scan("10.0.0.1", mac=MAC_1), status, 50)

        assert saved == {}
        assert all_devices() == []


# ==========================================================
# STABLE NAGIOS HOST NAMES (plan section 8)
# ==========================================================

class TestStableHostNames:

    def test_unnamed_device_never_gets_an_ip_based_name(self, app, db_session, admin_user):
        status = make_status(db_session, admin_user)

        device = run_scan(db_session, status, scan("10.0.0.5", hostname="Unknown"))[(NET, "10.0.0.5")]

        assert device.Nagios_Host_Name.startswith("dev-")
        assert "." not in device.Nagios_Host_Name
        assert "10.0.0.5" not in device.Nagios_Host_Name

    def test_dns_name_is_used_when_free(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        device = run_scan(db_session, status, scan("10.0.0.5", hostname="Web Server.lan"))[(NET, "10.0.0.5")]
        assert device.Nagios_Host_Name == "web-server.lan"
        assert device.Hostname == "Web Server.lan"

    def test_dns_name_that_embeds_the_ip_is_not_used(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        device = run_scan(db_session, status, scan("10.0.0.5", hostname="10.0.0.5.test.local"))[(NET, "10.0.0.5")]
        assert device.Nagios_Host_Name.startswith("dev-")

    def test_two_devices_with_the_same_dns_name_get_unique_names(self, db_session, admin_user):
        """Problem E: duplicate host_name made `nagios -v` reject the whole config."""
        status = make_status(db_session, admin_user)
        discovered = combine(
            scan("10.0.0.1", mac=MAC_1, hostname="nas.lan"),
            scan("10.0.0.2", mac=MAC_2, hostname="nas.lan"),
        )
        devices = run_scan(db_session, status, discovered)

        names = sorted(d.Nagios_Host_Name for d in devices.values())
        assert names == ["nas.lan", "nas.lan-2"]

    def test_name_does_not_change_when_the_ip_changes(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        first = run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1))[(NET, "10.0.0.5")]
        name = first.Nagios_Host_Name

        moved = run_scan(db_session, status, scan("10.0.0.99", mac=MAC_1))[(NET, "10.0.0.99")]

        assert moved.Nagios_Host_Name == name

    def test_dns_name_change_does_not_rename_the_nagios_host(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1, hostname="old.lan"))

        device = run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1, hostname="new.lan"))[(NET, "10.0.0.5")]

        assert device.Hostname == "new.lan"
        assert device.Nagios_Host_Name == "old.lan"

    def test_create_stable_host_name_prefers_ncpa_node_name_and_resolves_collisions(self, app, db_session, admin_user):
        status = make_status(db_session, admin_user)
        run_scan(db_session, status, scan("10.0.0.1", hostname="node.lan"))

        assert create_stable_host_name("dns.lan", "node.lan") == "node.lan-2"
        assert create_stable_host_name("dns.lan", None) == "dns.lan"

    def test_nagios_host_name_falls_back_for_older_rows(self, app, db_session, admin_user):
        status = make_status(db_session, admin_user)
        db_session.session.add(NetworkDiscovery(
            Hostname="legacy", IP_Address="10.0.0.9", Network=NET, DiscoveryStatusID=status))
        db_session.session.add(NetworkDiscovery(
            Hostname=None, IP_Address="10.0.0.8", Network=NET, DiscoveryStatusID=status))
        db_session.session.commit()
        legacy, bare = all_devices()

        assert nagios_host_name(legacy) == "legacy"
        assert nagios_host_name(bare) == "10.0.0.8"


# ==========================================================
# MATCHING RULES (plan section 4 table, one test per row)
# ==========================================================

class TestMatchingRules:

    def test_strong_identifier_matches_one_device_across_ip_and_mac_change(self, db_session, admin_user):
        """Row 1: strong identifiers point to one device -> same device, Verified."""
        status = make_status(db_session, admin_user)
        first = run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1, identifiers=[ssh(SSH_1)]))[(NET, "10.0.0.5")]

        again = run_scan(db_session, status, scan("10.0.0.50", mac=MAC_2, identifiers=[ssh(SSH_1)]))[(NET, "10.0.0.50")]

        assert again.NetDiscoveryID == first.NetDiscoveryID
        assert again.IP_Address == "10.0.0.50"
        assert again.Identity_Confidence is IdentityConfidence.VERIFIED
        assert len(all_devices()) == 1

    def test_routed_device_without_mac_is_followed_by_certificate(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        first = run_scan(db_session, status, scan("10.0.0.5", identifiers=[cert(CERT_1)]))[(NET, "10.0.0.5")]

        again = run_scan(db_session, status, scan("10.0.0.60", identifiers=[cert(CERT_1)]))[(NET, "10.0.0.60")]

        assert again.NetDiscoveryID == first.NetDiscoveryID
        assert len(all_devices()) == 1

    def test_hardware_mac_alone_matches_as_likely(self, db_session, admin_user):
        """Row 2: only a hardware MAC matches -> same device, Likely."""
        status = make_status(db_session, admin_user)
        first = run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1))[(NET, "10.0.0.5")]

        again = run_scan(db_session, status, scan("10.0.0.70", mac=MAC_1))[(NET, "10.0.0.70")]

        assert again.NetDiscoveryID == first.NetDiscoveryID
        assert again.Identity_Confidence is IdentityConfidence.LIKELY
        assert again.Addressing is AddressingMode.DHCP  # an observed change is the evidence

    def test_randomized_mac_is_treated_like_no_mac(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        run_scan(db_session, status, scan("10.0.0.5", mac=RANDOM_MAC))

        run_scan(db_session, status, scan("10.0.0.6", mac=RANDOM_MAC))

        # The randomized MAC never became an identifier, so it cannot link them.
        assert len(all_devices()) == 2
        assert db.session.scalars(sa.select(DeviceIdentifier)).all() == []

    def test_strong_identifiers_of_two_devices_are_a_conflict_not_a_merge(self, db_session, admin_user):
        """Row 3: strong identifiers point to two different devices -> review item."""
        status = make_status(db_session, admin_user)
        discovered = combine(
            scan("10.0.0.1", identifiers=[ssh(SSH_1)]),
            scan("10.0.0.2", identifiers=[ssh(SSH_2)]),
        )
        devices = run_scan(db_session, status, discovered)
        one, two = devices[(NET, "10.0.0.1")], devices[(NET, "10.0.0.2")]

        run_scan(db_session, status, scan("10.0.0.3", identifiers=[ssh(SSH_1), cert(CERT_1)] + [ssh(SSH_2)]))

        conflicts = review_items(ReviewKind.CONFLICT)
        assert len(conflicts) == 1
        assert sorted(conflicts[0].Candidate_Device_IDs) == sorted([one.NetDiscoveryID, two.NetDiscoveryID])
        # Nothing merged: both originals untouched, the observation became its own device.
        assert one.IP_Address == "10.0.0.1" and two.IP_Address == "10.0.0.2"
        assert one.Device_State is DeviceState.ACTIVE and two.Device_State is DeviceState.ACTIVE
        assert len(all_devices()) == 3

    def test_one_strong_match_with_a_contradicting_identifier_is_a_conflict(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        first = run_scan(db_session, status, scan(
            "10.0.0.1", identifiers=[ssh(SSH_1), cert(CERT_1)]))[(NET, "10.0.0.1")]

        run_scan(db_session, status, scan("10.0.0.9", identifiers=[ssh(SSH_1), cert(CERT_2)]))

        assert len(review_items(ReviewKind.CONFLICT)) == 1
        assert first.IP_Address == "10.0.0.1"
        assert identifier_values(first, IdentifierKind.NCPA_CERT) == {CERT_1}

    def test_ip_reuse_by_a_different_mac_creates_a_new_device(self, db_session, admin_user):
        """Row 4: same IP, contradicting MAC -> new device; old one's address unknown."""
        status = make_status(db_session, admin_user)
        old = run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1, tcp={22: "ssh"}))[(NET, "10.0.0.5")]

        new = run_scan(db_session, status, scan("10.0.0.5", mac=MAC_2))[(NET, "10.0.0.5")]

        assert new.NetDiscoveryID != old.NetDiscoveryID
        assert old.Device_State is DeviceState.ADDRESS_UNKNOWN
        assert open_addresses(old) == []
        assert [i.Kind for i in review_items()] == [ReviewKind.IP_REUSE]
        # The new device does not inherit the old device's ports or NCPA records.
        assert new.Nagios_Host_Name != old.Nagios_Host_Name
        assert db.session.scalars(sa.select(NCPADeployment).where(
            NCPADeployment.NetworkDiscoveryID == new.NetDiscoveryID)).all() != []  # its own, not the old one's

    def test_ip_reuse_by_a_different_host_key_creates_a_new_device(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        old = run_scan(db_session, status, scan("10.0.0.5", identifiers=[ssh(SSH_1)]))[(NET, "10.0.0.5")]

        new = run_scan(db_session, status, scan("10.0.0.5", identifiers=[ssh(SSH_2)]))[(NET, "10.0.0.5")]

        assert new.NetDiscoveryID != old.NetDiscoveryID
        assert old.Device_State is DeviceState.ADDRESS_UNKNOWN
        assert review_items(ReviewKind.IP_REUSE)

    def test_same_ip_with_no_identifiers_is_the_same_device_unverified(self, db_session, admin_user):
        """Row 5: same IP, nothing on either side -> same device, Unverified."""
        status = make_status(db_session, admin_user)
        first = run_scan(db_session, status, scan("10.0.0.5"))[(NET, "10.0.0.5")]

        again = run_scan(db_session, status, scan("10.0.0.5"))[(NET, "10.0.0.5")]

        assert again.NetDiscoveryID == first.NetDiscoveryID
        assert again.Identity_Confidence is IdentityConfidence.UNVERIFIED
        assert len(all_devices()) == 1
        assert len(open_addresses(first)) == 1

    def test_nothing_matches_creates_a_new_device(self, db_session, admin_user):
        """Row 6."""
        status = make_status(db_session, admin_user)
        run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1))

        run_scan(db_session, status, scan("10.0.0.6", mac=MAC_2))

        assert len(all_devices()) == 2

    def test_new_device_confidence_follows_its_evidence(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        discovered = combine(
            scan("10.0.0.1", identifiers=[ssh(SSH_1)]),
            scan("10.0.0.2", mac=MAC_2),
            scan("10.0.0.3"),
        )
        devices = run_scan(db_session, status, discovered)

        assert devices[(NET, "10.0.0.1")].Identity_Confidence is IdentityConfidence.VERIFIED
        assert devices[(NET, "10.0.0.2")].Identity_Confidence is IdentityConfidence.LIKELY
        assert devices[(NET, "10.0.0.3")].Identity_Confidence is IdentityConfidence.UNVERIFIED

    def test_os_reinstall_is_flagged_not_auto_accepted(self, db_session, admin_user):
        """Section 13: same MAC, new host key -> review item, never silently trusted."""
        status = make_status(db_session, admin_user)
        old = run_scan(db_session, status, scan(
            "10.0.0.5", mac=MAC_1, identifiers=[ssh(SSH_1)]))[(NET, "10.0.0.5")]

        new = run_scan(db_session, status, scan(
            "10.0.0.6", mac=MAC_1, identifiers=[ssh(SSH_2)]))[(NET, "10.0.0.6")]

        assert new.NetDiscoveryID != old.NetDiscoveryID
        assert identifier_values(old, IdentifierKind.SSH_HOST_KEY) == {SSH_1}
        items = review_items(ReviewKind.IDENTITY_CHANGED)
        assert len(items) == 1
        assert items[0].Candidate_Device_IDs == [old.NetDiscoveryID]

    def test_a_repeated_review_case_does_not_pile_up_devices_or_items(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1, identifiers=[ssh(SSH_1)]))
        for _ in range(3):
            run_scan(db_session, status, scan("10.0.0.6", mac=MAC_1, identifiers=[ssh(SSH_2)]))

        assert len(all_devices()) == 2
        assert len(review_items(ReviewKind.IDENTITY_CHANGED)) == 1

    def test_repeat_ip_reuse_review_is_not_duplicated(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1))
        for _ in range(3):
            run_scan(db_session, status, scan("10.0.0.5", mac=MAC_2))

        assert len(all_devices()) == 2
        assert len(review_items(ReviewKind.IP_REUSE)) == 1


# ==========================================================
# ADDRESS HISTORY
# ==========================================================

class TestAddressHistory:

    def test_address_change_closes_the_old_row_and_opens_a_new_one(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        device = run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1))[(NET, "10.0.0.5")]

        run_scan(db_session, status, scan("10.0.0.6", mac=MAC_1))

        rows = address_rows(device)
        assert [r.IP_Address for r in rows] == ["10.0.0.5", "10.0.0.6"]
        assert rows[0].Closed_At is not None
        assert rows[1].Closed_At is None
        assert all(r.Source is AddressSource.SCAN for r in rows)

    def test_a_rescan_at_the_same_address_adds_no_rows(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        device = run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1))[(NET, "10.0.0.5")]
        for _ in range(3):
            run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1))

        assert len(address_rows(device)) == 1

    def test_static_device_that_moves_is_followed_and_flagged(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        device = run_scan(db_session, status, scan("10.0.0.5", mac=MAC_1))[(NET, "10.0.0.5")]
        device.Addressing = AddressingMode.STATIC
        db_session.session.commit()

        moved = run_scan(db_session, status, scan("10.0.0.6", mac=MAC_1))[(NET, "10.0.0.6")]

        assert moved.NetDiscoveryID == device.NetDiscoveryID
        assert moved.IP_Address == "10.0.0.6"
        assert moved.Addressing is AddressingMode.STATIC  # not silently reclassified
        assert len(review_items(ReviewKind.STATIC_MOVED)) == 1


# ==========================================================
# IDENTIFIERS
# ==========================================================

class TestIdentifiers:

    def test_strong_identifier_cannot_belong_to_two_devices(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        devices = run_scan(db_session, status, combine(scan("10.0.0.1"), scan("10.0.0.2")))
        one, two = devices[(NET, "10.0.0.1")], devices[(NET, "10.0.0.2")]

        assert attach_identifiers(one, [Evidence(IdentifierKind.MACHINE_ID, "m" * 32)]) == []
        rejected = attach_identifiers(two, [Evidence(IdentifierKind.MACHINE_ID, "m" * 32)])

        assert [e.value for e in rejected] == ["m" * 32]
        assert identifier_values(two, IdentifierKind.MACHINE_ID) == set()

    def test_weak_identifier_may_be_shared(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        devices = run_scan(db_session, status, combine(scan("10.0.0.1"), scan("10.0.0.2")))
        one, two = devices[(NET, "10.0.0.1")], devices[(NET, "10.0.0.2")]
        weak = Evidence(IdentifierKind.DNS_NAME, "same.lan", False)

        assert attach_identifiers(one, [weak]) == []
        assert attach_identifiers(two, [weak]) == []
        db_session.session.commit()

    def test_multi_nic_device_keeps_several_mac_rows(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        device = run_scan(db_session, status, scan("10.0.0.1", mac=MAC_1))[(NET, "10.0.0.1")]

        attach_identifiers(device, [Evidence(IdentifierKind.MAC, MAC_2)])

        assert identifier_values(device, IdentifierKind.MAC) == {MAC_1, MAC_2}

    def test_record_device_evidence_raises_a_review_item_for_a_clone(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        devices = run_scan(db_session, status, combine(scan("10.0.0.1"), scan("10.0.0.2")))
        one, two = devices[(NET, "10.0.0.1")], devices[(NET, "10.0.0.2")]
        record_device_evidence(one, [Evidence(IdentifierKind.MACHINE_ID, "c" * 32)])

        rejected = record_device_evidence(two, [Evidence(IdentifierKind.MACHINE_ID, "c" * 32)])

        assert len(rejected) == 1
        items = review_items(ReviewKind.CONFLICT)
        assert len(items) == 1
        assert sorted(items[0].Candidate_Device_IDs) == sorted([one.NetDiscoveryID, two.NetDiscoveryID])
        assert one.Identity_Confidence is IdentityConfidence.VERIFIED
        assert two.Identity_Confidence is IdentityConfidence.UNVERIFIED

    def test_learning_an_identifier_upgrades_confidence(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        device = run_scan(db_session, status, scan("10.0.0.1"))[(NET, "10.0.0.1")]
        assert device.Identity_Confidence is IdentityConfidence.UNVERIFIED

        record_device_evidence(device, [Evidence(IdentifierKind.SSH_HOST_KEY, SSH_1)])

        assert device.Identity_Confidence is IdentityConfidence.VERIFIED


# ==========================================================
# MULTI-NIC, SWAPS AND CLONES (section 13)
# ==========================================================

class TestSeveralObservationsOfOneDevice:

    def test_multi_nic_device_keeps_one_primary_address(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        device = run_scan(db_session, status, scan(
            "10.0.0.1", mac=MAC_1, identifiers=[ssh(SSH_1)]))[(NET, "10.0.0.1")]

        # Second NIC listed FIRST so scan order cannot decide the outcome.
        discovered = combine(
            scan("10.0.0.2", mac=MAC_2, identifiers=[ssh(SSH_1)]),
            scan("10.0.0.1", mac=MAC_1, identifiers=[ssh(SSH_1)]),
        )
        devices = run_scan(db_session, status, discovered)

        assert len(all_devices()) == 1
        assert device.IP_Address == "10.0.0.1"
        assert list(devices) == [(NET, "10.0.0.1")]
        assert [r.IP_Address for r in open_addresses(device)] == ["10.0.0.1"]
        assert "10.0.0.2" in [r.IP_Address for r in address_rows(device)]
        assert review_items(ReviewKind.DUPLICATE_IDENTITY)  # new MAC with a shared key: second NIC or clone

    def test_swapped_addresses_resolve_by_strong_identifier(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        devices = run_scan(db_session, status, combine(
            scan("10.0.0.1", identifiers=[ssh(SSH_1)]),
            scan("10.0.0.2", identifiers=[ssh(SSH_2)]),
        ))
        one, two = devices[(NET, "10.0.0.1")], devices[(NET, "10.0.0.2")]

        run_scan(db_session, status, combine(
            scan("10.0.0.1", identifiers=[ssh(SSH_2)]),
            scan("10.0.0.2", identifiers=[ssh(SSH_1)]),
        ))

        assert (one.IP_Address, two.IP_Address) == ("10.0.0.2", "10.0.0.1")
        assert len(all_devices()) == 2
        assert review_items() == []
        assert one.Device_State is DeviceState.ACTIVE and two.Device_State is DeviceState.ACTIVE

    def test_a_displaced_device_that_moved_in_the_same_scan_is_not_marked_unknown(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        mover = run_scan(db_session, status, scan("10.0.0.1", mac=MAC_1))[(NET, "10.0.0.1")]

        # Its old IP is taken by a stranger while it shows up at a new address.
        run_scan(db_session, status, combine(
            scan("10.0.0.1", mac=MAC_2),
            scan("10.0.0.9", mac=MAC_1),
        ))

        assert mover.IP_Address == "10.0.0.9"
        assert mover.Device_State is DeviceState.ACTIVE


# ==========================================================
# LIFECYCLE (plan section 6)
# ==========================================================

class TestDeviceLifecycle:

    def test_one_missed_scan_changes_nothing_visible(self, app, db_session, admin_user):
        status = make_status(db_session, admin_user)
        gone = run_scan(db_session, status, scan("10.0.0.1", mac=MAC_1))[(NET, "10.0.0.1")]

        run_scan(db_session, status, scan("10.0.0.2", mac=MAC_2))

        assert gone.Device_State is DeviceState.ACTIVE
        assert gone.Missed_Scans == 1

    def test_device_becomes_missing_after_the_configured_number_of_scans(self, app, db_session, admin_user):
        status = make_status(db_session, admin_user)
        gone = run_scan(db_session, status, scan("10.0.0.1", mac=MAC_1))[(NET, "10.0.0.1")]

        with patched_config(app, DEVICE_MISSING_AFTER_SCANS=2):
            run_scan(db_session, status, scan("10.0.0.2", mac=MAC_2))
            run_scan(db_session, status, scan("10.0.0.2", mac=MAC_2))

        assert gone.Device_State is DeviceState.MISSING
        # Still in the config: Nagios reports it DOWN, which is the right signal.
        assert gone.IP_Address == "10.0.0.1"

    def test_missing_device_returns_to_active_when_found_again(self, app, db_session, admin_user):
        status = make_status(db_session, admin_user)
        gone = run_scan(db_session, status, scan("10.0.0.1", mac=MAC_1))[(NET, "10.0.0.1")]
        with patched_config(app, DEVICE_MISSING_AFTER_SCANS=1):
            run_scan(db_session, status, scan("10.0.0.2", mac=MAC_2))
        assert gone.Device_State is DeviceState.MISSING

        run_scan(db_session, status, scan("10.0.0.40", mac=MAC_1))

        assert gone.Device_State is DeviceState.ACTIVE
        assert gone.Missed_Scans == 0
        assert gone.IP_Address == "10.0.0.40"

    def test_devices_on_networks_that_were_not_scanned_are_left_alone(self, app, db_session, admin_user):
        status = make_status(db_session, admin_user)
        other = run_scan(db_session, status, scan("192.168.1.5", mac=MAC_3, network="192.168.1.0/24"))[
            ("192.168.1.0/24", "192.168.1.5")]

        with patched_config(app, DEVICE_MISSING_AFTER_SCANS=1):
            run_scan(db_session, status, scan("10.0.0.1", mac=MAC_1))

        assert other.Device_State is DeviceState.ACTIVE
        assert other.Missed_Scans == 0

    def test_ip_taken_over_by_a_matched_device_makes_the_old_one_address_unknown(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        devices = run_scan(db_session, status, combine(
            scan("10.0.0.1", identifiers=[ssh(SSH_1)]),
            scan("10.0.0.2"),
        ))
        mover, bystander = devices[(NET, "10.0.0.1")], devices[(NET, "10.0.0.2")]

        # The mover takes the bystander's address; the bystander is not seen.
        run_scan(db_session, status, scan("10.0.0.2", identifiers=[ssh(SSH_1)]))

        assert mover.IP_Address == "10.0.0.2"
        assert bystander.Device_State is DeviceState.ADDRESS_UNKNOWN

    def test_long_missing_device_is_retired_and_keeps_its_record(self, app, db_session, admin_user):
        status = make_status(db_session, admin_user)
        gone = run_scan(db_session, status, scan("10.0.0.1", mac=MAC_1))[(NET, "10.0.0.1")]
        with patched_config(app, DEVICE_MISSING_AFTER_SCANS=1, DEVICE_RETIRE_AFTER_DAYS=30):
            run_scan(db_session, status, scan("10.0.0.2", mac=MAC_2))
            gone.Last_Seen_At = datetime.now(timezone.utc) - timedelta(days=31)
            db_session.session.commit()

            run_scan(db_session, status, scan("10.0.0.2", mac=MAC_2))

        assert gone.Device_State is DeviceState.RETIRED
        assert open_addresses(gone) == []
        assert identifier_values(gone, IdentifierKind.MAC) == {MAC_1}  # kept for later recognition

    def test_retired_device_is_reactivated_if_it_reappears(self, app, db_session, admin_user):
        status = make_status(db_session, admin_user)
        gone = run_scan(db_session, status, scan("10.0.0.1", mac=MAC_1))[(NET, "10.0.0.1")]
        gone.Device_State = DeviceState.RETIRED
        db_session.session.commit()

        back = run_scan(db_session, status, scan("10.0.0.33", mac=MAC_1))[(NET, "10.0.0.33")]

        assert back.NetDiscoveryID == gone.NetDiscoveryID
        assert back.Device_State is DeviceState.ACTIVE
        assert len(open_addresses(back)) == 1

    def test_retired_devices_ip_is_not_matched_by_a_new_unidentified_host(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        gone = run_scan(db_session, status, scan("10.0.0.1"))[(NET, "10.0.0.1")]
        gone.Device_State = DeviceState.RETIRED
        db_session.session.commit()

        new = run_scan(db_session, status, scan("10.0.0.1"))[(NET, "10.0.0.1")]

        assert new.NetDiscoveryID != gone.NetDiscoveryID
        assert gone.Device_State is DeviceState.RETIRED

    def test_merged_device_resolves_to_its_target(self, db_session, admin_user):
        status = make_status(db_session, admin_user)
        devices = run_scan(db_session, status, combine(
            scan("10.0.0.1", mac=MAC_1), scan("10.0.0.2", mac=MAC_2)))
        source, target = devices[(NET, "10.0.0.1")], devices[(NET, "10.0.0.2")]
        # What the merge route does to the identifiers and the record.
        for row in db.session.scalars(sa.select(DeviceIdentifier).where(
                DeviceIdentifier.NetDiscoveryID == source.NetDiscoveryID)).all():
            row.NetDiscoveryID = target.NetDiscoveryID
        source.Device_State = DeviceState.MERGED
        source.Merged_Into_ID = target.NetDiscoveryID
        db_session.session.commit()

        seen = run_scan(db_session, status, scan("10.0.0.50", mac=MAC_1))[(NET, "10.0.0.50")]

        assert seen.NetDiscoveryID == target.NetDiscoveryID
        assert source.Device_State is DeviceState.MERGED
