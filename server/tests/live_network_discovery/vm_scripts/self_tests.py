#!/usr/bin/env python3
"""Standard-library safety/recovery tests; no live guests or networks required."""

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch
import xml.etree.ElementTree as ET

import provision_lab as lab


class ProvisionTests(unittest.TestCase):
    """Check scope, ownership and artifact behavior without live mutations."""

    def setUp(self):
        self.config = json.loads((lab.HERE / 'vm-lab.example.json').read_text())
        self.state = {'hypervisor': 'qemu', 'targets': {target: {'name': 'pinpoint-lab-' + target, 'uuid': target + '-uuid', 'lab_mac': '52:54:00:13:00:02', 'install_mac': '52:54:00:14:00:02'} for target in lab.TARGETS}}

    def test_rejects_management_overlap(self):
        routes = [{'dst': '10.0.2.0/24', 'dev': 'enp0s3'}]
        with self.assertRaisesRegex(ValueError, 'overlaps'):
            lab.validate_scope(self.config, routes, [])

    def test_rejects_interface_overlap_even_without_route(self):
        interfaces = [{'ifname': 'enp0s3', 'addr_info': [{'family': 'inet', 'local': '10.0.2.105', 'prefixlen': 24}]}]
        with self.assertRaisesRegex(ValueError, 'overlaps'):
            lab.validate_scope(self.config, [], interfaces)

    def test_rejects_default_route_on_lab_bridge(self):
        with self.assertRaisesRegex(ValueError, 'default route'):
            lab.validate_scope(self.config, [{'dst': 'default', 'dev': 'virbr-pinpoint'}], [])

    def test_accepts_internal_bridge(self):
        interfaces = [{'ifname': 'virbr-pinpoint', 'addr_info': [{'family': 'inet', 'local': '10.0.2.1', 'prefixlen': 28}]}]
        self.assertTrue(lab.validate_scope(self.config, [{'dst': '10.0.2.0/28', 'dev': 'virbr-pinpoint'}], interfaces))

    def test_rejects_public_loopback_reserved_and_broad_network(self):
        for network in ['8.8.8.0/28', '127.0.0.0/28', '0.0.0.0/28', '192.168.0.0/16']:
            config = copy.deepcopy(self.config)
            config['lab_network'] = network
            with self.subTest(network=network), self.assertRaises(ValueError):
                lab.validate(config)

    def test_rejects_injected_domain_name(self):
        self.config['domain_prefix'] = 'lab; touch /tmp/unsafe'
        with self.assertRaises(ValueError):
            lab.validate(self.config)

    def test_rejects_network_and_broadcast_target(self):
        for address in ['10.0.2.0', '10.0.2.15']:
            self.config['target01_address'] = address
            with self.assertRaises(ValueError):
                lab.validate(self.config)

    def test_unrelated_domain_cannot_be_adopted(self):
        with patch.object(lab, 'virsh', return_value=CompletedProcess([], 0, 'other-uuid\n', '')):
            with self.assertRaisesRegex(ValueError, 'ownership UUID'):
                lab.ownership(self.state, 'target01')

    def test_failed_daemon_probe_is_not_absent_domain(self):
        with patch.object(lab, 'virsh', side_effect=[CompletedProcess([], 1, '', ''), RuntimeError('daemon inaccessible')]):
            with self.assertRaisesRegex(RuntimeError, 'inaccessible'):
                lab.ownership(self.state, 'target01')

    def test_final_domain_has_only_lab_interface(self):
        xml = ET.fromstring(lab.domain_xml(self.config, self.state, Path('/tmp/test-lab'), 'target01', False))
        interfaces = xml.findall('./devices/interface')
        self.assertEqual(len(interfaces), 1)
        self.assertEqual(interfaces[0].find('source').get('network'), 'pinpoint-test')
        self.assertEqual(xml.find('uuid').text, 'target01-uuid')

    def test_install_definition_has_separate_nat(self):
        xml = ET.fromstring(lab.domain_xml(self.config, self.state, Path('/tmp/test-lab'), 'target02', True))
        self.assertEqual([node.find('source').get('network') for node in xml.findall('./devices/interface')], ['pinpoint-test', 'default'])

    def test_image_checksum_rejected_before_any_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'image'
            image.write_bytes(b'not trusted')
            state = Path(directory) / 'new-state'
            with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                lab.prepare(self.config, state, image, '0' * 64)
            self.assertFalse(state.exists())

    def test_private_file_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'secret.json'
            lab.write(path, 'private')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertFalse(path.with_name(path.name + '.tmp').exists())

    def test_restore_preserves_old_disk(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'target01.qcow2').write_text('old disk')
            with patch.object(lab, 'command') as mocked:
                lab.restore_disk(self.config, root, 'target01')
            retired = list(root.glob('target01-retired-*.qcow2'))
            self.assertEqual(len(retired), 1)
            self.assertEqual(retired[0].read_text(), 'old disk')
            self.assertIn(str(root / 'target01-baseline.qcow2'), mocked.call_args.args[0])

    def test_cloud_init_failure_prevents_ready_marker(self):
        import guest_setup
        with patch.object(guest_setup, 'run', side_effect=RuntimeError('apt failed')), patch.object(guest_setup, 'write') as mocked:
            config = dict(self.config, target='target01', network='10.0.2.0/28', mysql_password='a' * 48, snmp_community='b' * 48)
            with self.assertRaises(RuntimeError):
                guest_setup.configure(config)
            mocked.assert_not_called()

    def test_foreign_guest_on_lab_is_rejected(self):
        xml = '<domain><devices><interface><source network="pinpoint-test"/></interface></devices></domain>'
        with patch.object(lab, 'virsh', side_effect=[CompletedProcess([], 0, 'existing-target\n', ''), CompletedProcess([], 0, xml, '')]):
            with self.assertRaisesRegex(ValueError, 'unrelated running guest'):
                lab.reject_foreign_guests(self.config, self.state)

    @unittest.skipUnless(all(shutil.which(name) for name in ['qemu-img', 'cloud-localds', 'ssh-keygen']), 'Image preparation tools absent')
    def test_real_seed_preparation_is_private_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'source.qcow2'
            root = Path(directory) / 'state'
            lab.command(['qemu-img', 'create', '-f', 'qcow2', str(image), '8M'])
            checksum = lab.digest(image)
            def mock_virsh(*args, check=True):
                return CompletedProcess([], 1 if args[0] == 'domuuid' else 0, '', '')
            with patch.object(lab, 'virsh', side_effect=mock_virsh):
                state = lab.prepare(self.config, root, image, checksum)
                again = lab.prepare(self.config, root, image, checksum)
            self.assertEqual(state, again)
            for target in lab.TARGETS:
                seed = root / (target + '-seed.img')
                self.assertTrue(seed.is_file())
                self.assertEqual(seed.stat().st_mode & 0o777, 0o600)
                data = json.loads((root / (target + '-user-data')).read_text().split('\n', 1)[1])
                self.assertEqual(data['runcmd'], [['python3', '/root/pinpoint-guest-setup.py']])
                private = data['ssh_keys']['ed25519_private']
                self.assertIn('OPENSSH PRIVATE KEY', private)
                self.assertNotIn(private, (root / 'known_hosts').read_text())
                self.assertEqual((root / (target + '-user-data')).stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main(verbosity=2)
