#!/usr/bin/env python3
"""Opt-in libvirt provisioning, isolation, verification and baseline restoration.

All changes require --apply. Existing domains must match saved ownership UUIDs.
Image downloads are handled separately by fetch_image.py.
"""

import argparse
import fcntl
import hashlib
import ipaddress
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
URI = 'qemu:///system'
TARGETS = ('target01', 'target02')


def command(argv, *, check=True, input_text=None, timeout=60):
    """Run argument-list commands without exposing subprocess output on errors."""
    result = subprocess.run(argv, input=input_text, text=True, capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f'{Path(argv[0]).name} {argv[1] if len(argv) > 1 else ""} failed (exit {result.returncode}); check local permissions and prerequisites')
    return result


def virsh(*args, check=True):
    """Use the system libvirt connection for an explicit command."""
    return command(['virsh', '-c', URI, *args], check=check)


def preferred_hypervisor():
    """Return kvm only when its device and libvirt domain type are usable."""
    if not os.access('/dev/kvm', os.R_OK | os.W_OK):
        return 'qemu'
    capability = virsh('domcapabilities', '--virttype', 'kvm', check=False)
    return 'kvm' if capability.returncode == 0 else 'qemu'


def validate(config):
    """Validate names, resources and unique usable private addresses."""
    if config.get('schema_version') != 1:
        raise ValueError('schema_version must be 1')
    network = ipaddress.ip_network(config['lab_network'], strict=True)
    private_ranges = [ipaddress.ip_network(value) for value in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')]
    if network.version != 4 or network.prefixlen != 28 or not any(network.subnet_of(value) for value in private_ranges):
        raise ValueError('Provisioning requires a canonical private IPv4 /28')
    addresses = [ipaddress.ip_address(config[key]) for key in ('pinpoint_address', 'target01_address', 'target02_address')]
    if len(set(addresses)) != 3 or any(a not in network or a in (network.network_address, network.broadcast_address) for a in addresses):
        raise ValueError('Addresses must be unique usable members of the lab network')
    for key in ('lab_network_name', 'install_network_name', 'domain_prefix'):
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,39}', config[key]):
            raise ValueError(f'Invalid {key}')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,14}', config['lab_bridge']):
        raise ValueError('Invalid lab_bridge')
    if config['lab_network_name'] == config['install_network_name']:
        raise ValueError('Install and lab networks must differ')
    for key, low, high in [('vcpu', 1, 4), ('disk_gib', 8, 32), ('timeout_seconds', 60, 3600), ('target01_memory_mib', 1024, 3072), ('target02_memory_mib', 1024, 3072)]:
        value = config[key]
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f'{key} must be an integer from {low} to {high}')
    return network


def validate_scope(config, routes, interfaces):
    """Reject overlap with management routes/interfaces, excluding the lab bridge."""
    network = validate(config)
    bridge = config['lab_bridge']
    for route in routes:
        if route.get('dst') == 'default':
            if route.get('dev') == bridge:
                raise ValueError('Lab bridge carries a default route')
        elif route.get('dev') != bridge and 'dst' in route:
            other = ipaddress.ip_network(route['dst'], strict=False)
            if other.version == 4 and network.overlaps(other):
                raise ValueError('Lab subnet overlaps a non-lab route')
    found_host = False
    for interface in interfaces:
        for address in interface.get('addr_info', []):
            if address.get('family') != 'inet':
                continue
            other = ipaddress.ip_network(f"{address['local']}/{address['prefixlen']}", strict=False)
            if network.overlaps(other) and interface['ifname'] != bridge:
                raise ValueError('Lab subnet overlaps a non-lab interface')
            if interface['ifname'] == bridge and address['local'] == config['pinpoint_address']:
                found_host = True
    return found_host


def check_network(config, install=True):
    """Require a pre-existing active isolated bridge and active install NAT network."""
    routes = json.loads(command(['ip', '-j', '-4', 'route', 'show']).stdout)
    interfaces = json.loads(command(['ip', '-j', '-4', 'address', 'show']).stdout)
    if not validate_scope(config, routes, interfaces):
        raise ValueError('Monitoring address is absent from the lab bridge; create the isolated libvirt network first')
    xml = ET.fromstring(virsh('net-dumpxml', config['lab_network_name']).stdout)
    bridge = xml.find('bridge')
    if xml.find('forward') is not None or bridge is None or bridge.get('name') != config['lab_bridge']:
        raise ValueError('Lab network must have the expected bridge and no forwarding')
    ips = xml.findall('ip')
    if len(ips) != 1 or ips[0].get('address') != config['pinpoint_address'] or ipaddress.ip_network(f"{ips[0].get('address')}/{ips[0].get('netmask', ips[0].get('prefix', ''))}", strict=False) != validate(config):
        raise ValueError('Libvirt lab network does not match configured /28')
    active = virsh('net-list', '--name').stdout.splitlines()
    if config['lab_network_name'] not in active:
        raise ValueError('Lab network is inactive')
    if not install:
        return
    nat = ET.fromstring(virsh('net-dumpxml', config['install_network_name']).stdout)
    forward = nat.find('forward')
    if forward is None or forward.get('mode') != 'nat' or config['install_network_name'] not in active:
        raise ValueError('Package-install network must be active NAT')


def ensure_network(config):
    """Create/start only the explicitly named isolated lab network; never change NAT."""
    routes = json.loads(command(['ip', '-j', '-4', 'route', 'show']).stdout)
    interfaces = json.loads(command(['ip', '-j', '-4', 'address', 'show']).stdout)
    validate_scope(config, routes, interfaces)
    names = virsh('net-list', '--all', '--name').stdout.splitlines()
    name = config['lab_network_name']
    if name in names:
        xml = ET.fromstring(virsh('net-dumpxml', name).stdout)
        bridge = xml.find('bridge')
        addresses = xml.findall('ip')
        if xml.find('forward') is not None or bridge is None or bridge.get('name') != config['lab_bridge'] or len(addresses) != 1:
            raise ValueError('Refusing to replace an existing network with a different contract')
        address = addresses[0]
        mask = address.get('netmask', address.get('prefix', ''))
        if address.get('address') != config['pinpoint_address'] or ipaddress.ip_network(address.get('address') + '/' + mask, strict=False) != validate(config):
            raise ValueError('Existing isolated network address does not match')
    else:
        network = ET.Element('network')
        ET.SubElement(network, 'name').text = name
        ET.SubElement(network, 'bridge', name=config['lab_bridge'], stp='on', delay='0')
        ET.SubElement(network, 'ip', address=config['pinpoint_address'], netmask=str(validate(config).netmask))
        with tempfile.NamedTemporaryFile('w', suffix='.xml') as handle:
            handle.write(ET.tostring(network, encoding='unicode'))
            handle.flush()
            virsh('net-define', handle.name)
    if name not in virsh('net-list', '--name').stdout.splitlines():
        virsh('net-start', name)
    print('Isolated lab network ready; no forwarding or DHCP enabled.')


def digest(path):
    """Hash an image in bounded-memory chunks."""
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write(path, content, mode=0o600):
    """Atomically replace a local artifact with private permissions by default."""
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(descriptor, 'w') as handle:
        handle.write(content)
    temporary.chmod(mode)
    temporary.replace(path)


def domain_xml(config, state, root, target, installing):
    """Build a managed domain definition with explicit disk paths and adapters."""
    saved = state['targets'][target]
    domain = ET.Element('domain', type=state['hypervisor'])
    ET.SubElement(domain, 'name').text = saved['name']
    ET.SubElement(domain, 'uuid').text = saved['uuid']
    ET.SubElement(domain, 'memory', unit='MiB').text = str(config[target + '_memory_mib'])
    ET.SubElement(domain, 'vcpu').text = str(config['vcpu'])
    os_node = ET.SubElement(domain, 'os')
    ET.SubElement(os_node, 'type', arch='x86_64', machine='pc').text = 'hvm'
    ET.SubElement(os_node, 'boot', dev='hd')
    features = ET.SubElement(domain, 'features')
    ET.SubElement(features, 'acpi')
    ET.SubElement(features, 'apic')
    devices = ET.SubElement(domain, 'devices')
    ET.SubElement(devices, 'emulator').text = shutil.which('qemu-system-x86_64') or '/usr/bin/qemu-system-x86_64'
    for filename, dev, fmt in [(target + '.qcow2', 'vda', 'qcow2'), (target + '-seed.img', 'vdb', 'raw')]:
        disk = ET.SubElement(devices, 'disk', type='file', device='disk')
        ET.SubElement(disk, 'driver', name='qemu', type=fmt)
        ET.SubElement(disk, 'source', file=str(root / filename))
        ET.SubElement(disk, 'target', dev=dev, bus='virtio')
        if fmt == 'raw':
            ET.SubElement(disk, 'readonly')
    for network, mac in [(config['lab_network_name'], saved['lab_mac'])] + ([(config['install_network_name'], saved['install_mac'])] if installing else []):
        interface = ET.SubElement(devices, 'interface', type='network')
        ET.SubElement(interface, 'mac', address=mac)
        ET.SubElement(interface, 'source', network=network)
        ET.SubElement(interface, 'model', type='virtio')
    serial = ET.SubElement(devices, 'serial', type='pty')
    ET.SubElement(serial, 'target', port='0')
    console = ET.SubElement(devices, 'console', type='pty')
    ET.SubElement(console, 'target', type='serial', port='0')
    return ET.tostring(domain, encoding='unicode')


def ownership(state, target):
    """Refuse to operate on existing guests not owned by this saved manifest."""
    saved = state['targets'][target]
    result = virsh('domuuid', saved['name'], check=False)
    if result.returncode:
        # An inaccessible daemon must not be mistaken for an absent guest.
        names = virsh('list', '--all', '--name').stdout.splitlines()
        if saved['name'] in names:
            raise RuntimeError('Cannot inspect existing domain UUID')
        return False
    if result.stdout.strip() != saved['uuid']:
        raise ValueError('Refusing to modify an existing domain with a different ownership UUID')
    return True


def reject_foreign_guests(config, state):
    """Reserve the isolated lab for this pair, rejecting active unrelated guests."""
    owned_names = {saved['name'] for saved in state['targets'].values()}
    for name in virsh('list', '--name').stdout.splitlines():
        if not name or name in owned_names:
            continue
        xml = ET.fromstring(virsh('dumpxml', name).stdout)
        for interface in xml.findall('./devices/interface'):
            source = interface.find('source')
            if source is not None and (source.get('network') == config['lab_network_name'] or source.get('bridge') == config['lab_bridge']):
                raise ValueError('An unrelated running guest already uses this isolated lab; stop it or choose a different subnet')


def ssh(config, root, target, remote, *, input_text=None, check=True):
    """Use locally generated pinned host keys, never automatic trust acceptance."""
    return command(['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', f'UserKnownHostsFile={root / "known_hosts"}', '-o', 'ConnectTimeout=5', '-i', str(root / 'lab_key'), 'pinpoint-test@' + config[target + '_address'], remote], input_text=input_text, check=check, timeout=25)


def wait_for(predicate, seconds, label):
    """Poll one bounded operation and print periodic non-sensitive progress."""
    deadline = time.monotonic() + seconds
    last_message = 0
    while time.monotonic() < deadline:
        if predicate():
            return
        if time.monotonic() - last_message > 30:
            print('Waiting for ' + label + '...', flush=True)
            last_message = time.monotonic()
        time.sleep(5)
    raise TimeoutError('Timed out waiting for ' + label + '; rerun up to resume, or stop to shut down owned guests')


def save(root, state):
    """Persist resumable ownership/configuration without printing secrets."""
    write(root / 'state.json', json.dumps(state, indent=2) + '\n')


def prepare(config, root, image, checksum):
    """Create ownership, keys, cloud-init seeds and sparse guest disks once."""
    if not image or not re.fullmatch(r'[a-fA-F0-9]{64}', checksum or ''):
        raise ValueError('First prepare/up requires --image and its --sha256 checksum')
    image = image.expanduser().resolve()
    if digest(image) != checksum.lower():
        raise ValueError('Cloud image SHA-256 mismatch')
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o711)  # QEMU must traverse this directory; individual secrets stay 0600.
    state_path = root / 'state.json'
    if state_path.exists():
        state = json.loads(state_path.read_text())
        if state['config'] != config or state['image_sha256'] != checksum.lower():
            raise ValueError('Saved lab configuration/image differs; use a new state directory')
    else:
        if any(p.name != '.provision.lock' for p in root.iterdir()):
            raise ValueError('New lab requires an empty state directory; refusing to reuse unowned files')
        state = {'schema_version': 1, 'config': config, 'image_sha256': checksum.lower(), 'hypervisor': preferred_hypervisor(), 'snmp_community': secrets.token_hex(24), 'mysql_password': secrets.token_hex(24), 'targets': {}}
        for target in TARGETS:
            state['targets'][target] = {'name': config['domain_prefix'] + '-' + target, 'uuid': str(uuid.uuid4()), 'lab_mac': '52:54:00:' + ':'.join(secrets.token_hex(1) for _ in range(3)), 'install_mac': '52:54:00:' + ':'.join(secrets.token_hex(1) for _ in range(3))}
        # Inspect names before writing ownership or any guest definitions.
        for target in TARGETS:
            ownership(state, target)
        reject_foreign_guests(config, state)
        save(root, state)
    base = root / 'base-image.qcow2'
    if not base.exists():
        shutil.copyfile(image, base)
        base.chmod(0o644)
    if digest(base) != state['image_sha256']:
        raise ValueError('Cached base image SHA-256 mismatch')
    key = root / 'lab_key'
    if not key.exists():
        command(['ssh-keygen', '-t', 'ed25519', '-N', '', '-f', str(key), '-C', 'pinpoint-disposable-lab'])
    key.chmod(0o600)
    known = []
    for target in TARGETS:
        ownership(state, target)
        hostkey = root / (target + '-host-key')
        if not hostkey.exists():
            command(['ssh-keygen', '-t', 'ed25519', '-N', '', '-f', str(hostkey), '-C', target])
        hostkey.chmod(0o600)
        public = hostkey.with_suffix('.pub').read_text().strip()
        known.append(config[target + '_address'] + ' ' + public)
        guest = {**config, 'network': config['lab_network'], 'target': target, 'mysql_password': state['mysql_password'], 'snmp_community': state['snmp_community']}
        user_data = {'hostname': target, 'manage_etc_hosts': True, 'ssh_pwauth': False, 'ssh_keys': {'ed25519_private': hostkey.read_text(), 'ed25519_public': public}, 'users': [{'name': 'pinpoint-test', 'shell': '/bin/bash', 'lock_passwd': True, 'sudo': 'ALL=(ALL) NOPASSWD:ALL', 'ssh_authorized_keys': [key.with_suffix('.pub').read_text().strip()]}], 'write_files': [{'path': '/etc/pinpoint-disposable-target', 'permissions': '0600', 'content': target + '\n'}, {'path': '/etc/pinpoint-lab.json', 'permissions': '0600', 'content': json.dumps(guest)}, {'path': '/root/pinpoint-guest-setup.py', 'permissions': '0700', 'content': (HERE / 'guest_setup.py').read_text()}], 'runcmd': [['python3', '/root/pinpoint-guest-setup.py']]}
        net = {'version': 2, 'ethernets': {'lab': {'match': {'macaddress': state['targets'][target]['lab_mac']}, 'set-name': 'lab0', 'addresses': [config[target + '_address'] + '/28']}, 'install': {'match': {'macaddress': state['targets'][target]['install_mac']}, 'set-name': 'install0', 'dhcp4': True, 'optional': True}}}
        seed = root / (target + '-seed.img')
        if not seed.exists():
            write(root / (target + '-user-data'), '#cloud-config\n' + json.dumps(user_data))
            write(root / (target + '-network'), json.dumps(net))
            write(root / (target + '-meta-data'), f'instance-id: {state["targets"][target]["uuid"]}\nlocal-hostname: {target}\n')
            command(['cloud-localds', '--network-config=' + str(root / (target + '-network')), str(seed), str(root / (target + '-user-data')), str(root / (target + '-meta-data'))])
            seed.chmod(0o600)
        disk = root / (target + '.qcow2')
        if not disk.exists():
            backing = root / (target + '-baseline.qcow2')
            backing = backing if backing.exists() else base
            command(['qemu-img', 'create', '-f', 'qcow2', '-F', 'qcow2', '-b', str(backing), str(disk), str(config['disk_gib']) + 'G'])
    write(root / 'known_hosts', '\n'.join(known) + '\n')
    return state


def define_start(config, state, root, target, installing):
    """Define/start an owned guest while preserving its stable UUID."""
    exists = ownership(state, target)
    name = state['targets'][target]['name']
    if exists and virsh('domstate', name).stdout.strip() != 'shut off':
        return
    xml = root / (target + '.xml')
    write(xml, domain_xml(config, state, root, target, installing))
    virsh('define', str(xml))
    virsh('start', name)


def domain_hypervisor(state, target, inactive=False):
    """Return the owned domain's live or persistent libvirt type."""
    if not ownership(state, target):
        raise ValueError('Managed guest is missing')
    arguments = ['dumpxml', state['targets'][target]['name']]
    if inactive:
        arguments.append('--inactive')
    return ET.fromstring(virsh(*arguments).stdout).get('type')


def enable_kvm(config, state, root):
    """Convert owned QEMU domains to KVM without replacing disks or baselines."""
    if preferred_hypervisor() != 'kvm':
        raise ValueError('KVM is not usable; verify nested virtualization and /dev/kvm access')

    types = {target: domain_hypervisor(state, target, inactive=True) for target in TARGETS}
    unsupported = {target: value for target, value in types.items() if value not in ('qemu', 'kvm')}
    if unsupported:
        raise ValueError('Refusing unsupported domain types: ' + str(unsupported))

    live_types = {}
    for target in TARGETS:
        name = state['targets'][target]['name']
        if virsh('domstate', name).stdout.strip() != 'shut off':
            live_types[target] = domain_hypervisor(state, target)

    if all(value == 'kvm' for value in types.values()) and all(
        value == 'kvm' for value in live_types.values()
    ):
        state['hypervisor'] = 'kvm'
        save(root, state)
        print('Both owned guests are already configured for KVM.', flush=True)
        return

    for target in TARGETS:
        name = state['targets'][target]['name']
        backup = root / (target + '-before-kvm.xml')
        if types[target] == 'qemu' and not backup.exists():
            write(backup, virsh('dumpxml', name, '--inactive').stdout)

    for target in TARGETS:
        shutoff(config, state, target)

    state['hypervisor'] = 'kvm'
    save(root, state)
    for target in TARGETS:
        name = state['targets'][target]['name']
        xml = root / (target + '.xml')
        write(xml, domain_xml(config, state, root, target, False))
        virsh('define', str(xml))
        if domain_hypervisor(state, target, inactive=True) != 'kvm':
            raise RuntimeError(target + ' persistent definition did not switch to KVM')
        virsh('start', name)
        monitor = virsh('qemu-monitor-command', name, '--hmp', 'info kvm')
        if 'enabled' not in monitor.stdout.lower():
            raise RuntimeError(target + ' started without KVM acceleration')
        wait_for(lambda: ssh(config, root, target, 'true', check=False).returncode == 0, config['timeout_seconds'], target + ' KVM SSH')
        wait_services(config, root, target)
    verify(config, state, root)
    print('Both owned guests now run with KVM; disks and baseline images were unchanged.', flush=True)


def shutoff(config, state, target):
    """Cleanly shut down an owned guest and confirm it is off before disk changes."""
    if not ownership(state, target):
        return
    name = state['targets'][target]['name']
    if virsh('domstate', name).stdout.strip() != 'shut off':
        virsh('shutdown', name)
        wait_for(lambda: virsh('domstate', name).stdout.strip() == 'shut off', 180, target + ' shutdown')


def isolate(config, state, root, target):
    """Remove NAT guest settings, save a cold baseline and boot an isolated overlay."""
    remote = '''import json,yaml
from pathlib import Path
c=json.loads(Path('/etc/pinpoint-lab.json').read_text())
p=Path('/etc/netplan/50-cloud-init.yaml');d=yaml.safe_load(p.read_text())
d['network']['ethernets'].pop('install',None)
d['network']['ethernets']['lab']['nameservers']={'addresses':[c['target02_address']]}
p.write_text(yaml.safe_dump(d));p.chmod(0o600)
Path('/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg').write_text('network: {config: disabled}\\n')
'''
    ssh(config, root, target, 'sudo -n python3 -', input_text=remote)
    shutoff(config, state, target)
    baseline = root / (target + '-baseline.qcow2')
    if not baseline.exists():
        temporary = root / (target + '-baseline.partial.qcow2')
        command(['qemu-img', 'convert', '-O', 'qcow2', str(root / (target + '.qcow2')), str(temporary)], timeout=config['timeout_seconds'])
        temporary.chmod(0o600)
        temporary.replace(baseline)
    restore_disk(config, root, target)
    define_start(config, state, root, target, False)


def restore_disk(config, root, target):
    """Preserve the old overlay and replace it with a fresh baseline overlay."""
    disk = root / (target + '.qcow2')
    if disk.exists():
        disk.rename(root / (target + '-retired-' + uuid.uuid4().hex + '.qcow2'))
    command(['qemu-img', 'create', '-f', 'qcow2', '-F', 'qcow2', '-b', str(root / (target + '-baseline.qcow2')), str(disk), str(config['disk_gib']) + 'G'])


def guest_units(target):
    """Return the fixed service names for one disposable target."""
    return 'ssh nginx vsftpd postfix mariadb pinpoint-test-tcp' if target == 'target01' else 'ssh named chrony snmpd pinpoint-test-udp'


def wait_services(config, root, target):
    """Wait for service startup after SSH becomes reachable on a fresh boot."""
    wait_for(lambda: ssh(config, root, target, 'sudo -n systemctl is-active ' + guest_units(target), check=False).returncode == 0, config['timeout_seconds'], target + ' active services')


def verify(config, state, root):
    """Confirm ownership, isolated adapters/routes and actual guest service listeners."""
    inventory = {}
    for target in TARGETS:
        if not ownership(state, target):
            raise ValueError('Managed guest is missing')
        xml = ET.fromstring(virsh('dumpxml', state['targets'][target]['name']).stdout)
        hypervisor = xml.get('type')
        if hypervisor != state['hypervisor']:
            raise ValueError(f'{target} runs as {hypervisor}, but saved state requires {state["hypervisor"]}')
        interfaces = xml.findall('./devices/interface')
        if len(interfaces) != 1 or interfaces[0].find('source').get('network') != config['lab_network_name']:
            raise ValueError('Guest still has a non-lab adapter; rerun up to finish isolation')
        routes = json.loads(ssh(config, root, target, 'ip -j -4 route show').stdout)
        if any(r.get('dst') == 'default' for r in routes):
            raise ValueError('Guest still has a default route')
        ssh(config, root, target, 'sudo -n systemctl is-active ' + guest_units(target))
        listeners = ssh(config, root, target, 'sudo -n ss -H -lntu').stdout
        expected = {'tcp': [21, 22, 25, 80, 443, 3306, 9000], 'udp': []} if target == 'target01' else {'tcp': [22, 53], 'udp': [53, 69, 123, 161]}
        actual = {'tcp': set(), 'udp': set()}
        for line in listeners.splitlines():
            fields = line.split()
            if len(fields) >= 5 and fields[0] in actual:
                bind, port = fields[4].rsplit(':', 1)
                if bind in ('*', '0.0.0.0', '[::]', config[target + '_address']):
                    actual[fields[0]].add(int(port))
        for protocol, ports in expected.items():
            if not set(ports).issubset(actual[protocol]):
                raise ValueError(f'{target} is missing expected {protocol} listeners')
        inventory[target] = {'address': config[target + '_address'], 'hypervisor': hypervisor, 'routes': routes, 'listeners': listeners, 'expected_ports': expected}
    write(root / 'inventory.json', json.dumps(inventory, indent=2) + '\n', 0o644)
    print('Both guests have isolated-only adapters/routes and all pre-NCPA Profile A listeners.', flush=True)


def export_harness(config, state, root):
    """Write public harness settings and private per-host plugin variables locally."""
    lab = {'schema_version': 1, 'lab_network': config['lab_network'], 'pinpoint': {'address': config['pinpoint_address'], 'base_url': config['pinpoint_base_url'], 'email_env': 'PINPOINT_TEST_EMAIL', 'password_env': 'PINPOINT_TEST_PASSWORD'}, 'targets': {}, 'discovery': {'tcp_ports': [21, 22, 25, 53, 80, 443, 3306, 5693, 9000], 'udp_ports': [53, 69, 123, 161], 'tcp_port_services': {'21': 'ftp', '22': 'ssh', '25': 'smtp', '53': 'dns', '80': 'http', '443': 'https', '3306': 'mysql', '5693': 'ncpa', '9000': 'testtcp'}, 'udp_port_services': {'53': 'dns', '123': 'ntp', '161': 'snmp'}, 'timeout_seconds': 3600, 'poll_seconds': 5}, 'nagios': {'binary': '/usr/local/nagios/bin/nagios', 'main_config': '/usr/local/nagios/etc/nagios.cfg', 'service_name': 'nagios'}, 'databases': {'system': 'REPLACE_WITH_ABSOLUTE_SYSTEM_DB_PATH'}, 'output_root': '~/pinpoint-test-results'}
    for target in TARGETS:
        lab['targets'][target] = {'address': config[target + '_address'], 'hostname': target + '.test.local', 'ssh_user': 'pinpoint-test', 'ssh_key_env': 'PINPOINT_TEST_SSH_KEY', 'expected_tcp_ports': [21, 22, 25, 80, 443, 3306, 5693, 9000] if target == 'target01' else [22, 53], 'expected_udp_ports': [] if target == 'target01' else [53, 69, 123, 161]}
    lab['targets']['target02']['expected_skipped_udp_ports'] = [69]
    if not (root / 'lab.json').exists():
        write(root / 'lab.json', json.dumps(lab, indent=2) + '\n')
    variables = {'target01': {'mysql': {'user': 'pinpoint_ro', 'password': state['mysql_password'], 'database': 'pinpoint_test'}}, 'target02': {'snmp': {'community': state['snmp_community']}, 'dns': {'lookup': 'target01.test.local', 'expected_address': config['target01_address']}}}
    write(root / 'plugin-variables.private.json', json.dumps(variables, indent=2) + '\n')


def main():
    """Preview by default; perform only explicitly selected managed lab operations."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['network', 'prepare', 'up', 'enable-kvm', 'verify', 'status', 'stop', 'restore'])
    parser.add_argument('--config', type=Path, default=HERE / 'vm-lab.example.json')
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--image', type=Path)
    parser.add_argument('--sha256')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    validate(config)
    if args.state_dir.is_symlink():
        raise ValueError('State directory must not be a symlink')
    root = args.state_dir.expanduser().resolve()
    if root in (Path('/'), Path('/tmp'), Path('/home')):
        raise ValueError('Use a dedicated persistent state directory')
    print(f'{args.action}: {config["domain_prefix"]}-target01/target02 on {config["lab_network"]}; state={root}', flush=True)
    if args.action not in ('status', 'verify') and not args.apply:
        print('Preview only. Add --apply to perform this operation. No files or domains changed.')
        return 0
    for executable in ('virsh', 'ip', 'ssh', 'ssh-keygen', 'qemu-img', 'cloud-localds', 'qemu-system-x86_64'):
        if not shutil.which(executable):
            raise ValueError('Missing prerequisite: ' + executable)
    if args.action == 'network':
        ensure_network(config)
        return 0
    if args.action not in ('status', 'stop'):
        check_network(config, install=args.action in ('prepare', 'up'))
    lock = None
    if args.apply:
        root.mkdir(parents=True, exist_ok=True)
        lock = (root / '.provision.lock').open('a')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another provisioner is using this state directory')
    if args.action in ('prepare', 'up'):
        if (root / 'state.json').exists() and not args.image:
            state = json.loads((root / 'state.json').read_text())
            if state['config'] != config:
                raise ValueError('Saved configuration differs')
            state = prepare(config, root, root / 'base-image.qcow2', state['image_sha256'])
        else:
            state = prepare(config, root, args.image, args.sha256)
        export_harness(config, state, root)
    else:
        state = json.loads((root / 'state.json').read_text())
        if state['config'] != config:
            raise ValueError('Saved configuration differs')
    # Check both guests before touching either, including stop/restore.
    for target in TARGETS:
        ownership(state, target)
    if args.action not in ('status', 'stop'):
        reject_foreign_guests(config, state)
    if args.action == 'prepare':
        print('Prepared images, pinned SSH keys and cloud-init seeds. Run up --apply to boot.')
    elif args.action == 'status':
        print('host preferred hypervisor: ' + preferred_hypervisor())
        for target in TARGETS:
            if ownership(state, target):
                runtime = virsh('domstate', state['targets'][target]['name']).stdout.strip()
                persistent = domain_hypervisor(state, target, inactive=True)
                print(f'{target}: {runtime}; persistent hypervisor={persistent}')
            else:
                print(target + ': not defined')
    elif args.action == 'stop':
        for target in TARGETS:
            shutoff(config, state, target)
        print('Owned guests stopped; all disks and baselines retained.')
    elif args.action == 'enable-kvm':
        enable_kvm(config, state, root)
    elif args.action == 'restore':
        if any(not (root / (target + '-baseline.qcow2')).is_file() for target in TARGETS):
            raise ValueError('Both cold baselines are required before restoration')
        for target in TARGETS:
            shutoff(config, state, target)
            restore_disk(config, root, target)
            define_start(config, state, root, target, False)
            wait_for(lambda: ssh(config, root, target, 'true', check=False).returncode == 0, config['timeout_seconds'], target + ' SSH')
            wait_services(config, root, target)
        verify(config, state, root)
    elif args.action == 'up':
        for target in TARGETS:
            baseline = root / (target + '-baseline.qcow2')
            define_start(config, state, root, target, not baseline.exists())
            def ready():
                result = ssh(config, root, target, 'sudo -n test -f /var/lib/pinpoint-lab-ready', check=False)
                if result.returncode == 0:
                    # Do not race the remaining cloud-final work.
                    return ssh(config, root, target, 'sudo -n test -f /var/lib/cloud/instance/boot-finished', check=False).returncode == 0
                status = ssh(config, root, target, 'cloud-init status', check=False)
                if 'status: error' in status.stdout:
                    raise RuntimeError(target + ' setup failed; inspect root-only guest setup logs and stop owned guests before retrying')
                return False
            wait_for(ready, config['timeout_seconds'], target + ' completed guest setup')
            # Isolation also resumes a run interrupted after baseline creation.
            live = ET.fromstring(virsh('dumpxml', state['targets'][target]['name']).stdout)
            if len(live.findall('./devices/interface')) != 1 or not baseline.exists():
                isolate(config, state, root, target)
            wait_for(lambda: ssh(config, root, target, 'true', check=False).returncode == 0, config['timeout_seconds'], target + ' isolated SSH')
            wait_services(config, root, target)
        verify(config, state, root)
    else:
        verify(config, state, root)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, OSError, TimeoutError, subprocess.TimeoutExpired, KeyError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        sys.exit(1)
