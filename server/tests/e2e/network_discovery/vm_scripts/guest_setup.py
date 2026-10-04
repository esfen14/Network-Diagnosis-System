#!/usr/bin/env python3
"""Configure Profile A only inside a cloud-init-marked disposable guest."""

import ipaddress
import json
import os
import re
import subprocess
from pathlib import Path


def run(argv, input_text=None):
    """Run a guest command without printing credential-bearing arguments."""
    result = subprocess.run(argv, input=input_text, text=True, capture_output=True)
    if result.returncode:
        # Detailed output stays root-only: SNMP/MySQL settings must not reach logs.
        Path('/root/pinpoint-setup-error.txt').write_text(result.stdout + result.stderr)
        Path('/root/pinpoint-setup-error.txt').chmod(0o600)
        raise RuntimeError(f'Guest setup command failed: {argv[0]} (exit {result.returncode})')


def write(path, content, mode=0o644):
    """Write a dedicated guest configuration file with explicit permissions."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(mode)


def configure(config):
    """Install services and apply configuration before marking the guest ready."""
    target = config['target']
    network = ipaddress.ip_network(config['network'], strict=True)
    if not network.is_private or network.prefixlen < 28:
        raise ValueError('Guest requires a private /28 or smaller network')
    host = str(ipaddress.ip_address(config['pinpoint_address']))
    if ipaddress.ip_address(host) not in network:
        raise ValueError('Monitoring host must belong to lab network')
    for field in ['mysql_password', 'snmp_community']:
        if not re.fullmatch(r'[a-f0-9]{48}', config[field]):
            raise ValueError('Invalid generated guest credential')
    os.environ['DEBIAN_FRONTEND'] = 'noninteractive'
    packages = ['openssh-server', 'socat', 'python3-yaml']
    if target == 'target01':
        run(['debconf-set-selections'], 'postfix postfix/main_mailer_type select Local only\npostfix postfix/mailname string target01.test.local\n')
        packages += ['nginx', 'vsftpd', 'postfix', 'mariadb-server', 'openssl']
    elif target == 'target02':
        packages += ['bind9', 'bind9-utils', 'chrony', 'snmpd']
    else:
        raise ValueError('Unknown disposable guest')
    run(['apt-get', 'update'])
    run(['apt-get', 'install', '-y', '--no-install-recommends', *packages])
    if target == 'target01':
        certdir = Path('/etc/nginx/pinpoint-test')
        certdir.mkdir(parents=True, exist_ok=True)
        if not (certdir / 'server.key').exists():
            run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '365', '-keyout', str(certdir / 'server.key'), '-out', str(certdir / 'server.crt'), '-subj', '/CN=target01.test.local'])
            (certdir / 'server.key').chmod(0o600)
        write('/etc/nginx/sites-available/pinpoint-test', '''server {
 listen 80 default_server;
 server_name target01.test.local;
 location / { return 200 "pinpoint-http-ok\\n"; }
}
server {
 listen 443 ssl default_server;
 server_name target01.test.local;
 ssl_certificate /etc/nginx/pinpoint-test/server.crt;
 ssl_certificate_key /etc/nginx/pinpoint-test/server.key;
 location / { return 200 "pinpoint-https-ok\\n"; }
}
''')
        Path('/etc/nginx/sites-enabled/default').unlink(missing_ok=True)
        link = Path('/etc/nginx/sites-enabled/pinpoint-test')
        if not link.is_symlink():
            link.symlink_to('/etc/nginx/sites-available/pinpoint-test')
        write('/etc/mysql/mariadb.conf.d/99-pinpoint-test.cnf', '[mysqld]\nbind-address = 0.0.0.0\n')
        run(['postconf', '-e', 'inet_interfaces = all'])
        run(['postconf', '-e', 'mynetworks = 127.0.0.0/8 [::1]/128'])
        write('/etc/systemd/system/pinpoint-test-tcp.service', unit('TCP4-LISTEN:9000,reuseaddr,fork', 'TCP echo on 9000'))
        units = ['ssh', 'nginx', 'vsftpd', 'postfix', 'mariadb', 'pinpoint-test-tcp']
        run(['nginx', '-t'])
        run(['systemctl', 'daemon-reload'])
        run(['systemctl', 'enable', *units])
        run(['systemctl', 'restart', *units])
        password = config['mysql_password']
        # Values are validated fixed-format generated credentials and IP addresses.
        run(['mysql'], f"CREATE DATABASE IF NOT EXISTS pinpoint_test;\nCREATE TABLE IF NOT EXISTS pinpoint_test.health (id INT PRIMARY KEY, status VARCHAR(16));\nINSERT INTO pinpoint_test.health VALUES (1, 'ok') ON DUPLICATE KEY UPDATE status='ok';\nCREATE USER IF NOT EXISTS 'pinpoint_ro'@'{host}' IDENTIFIED BY '{password}';\nALTER USER 'pinpoint_ro'@'{host}' IDENTIFIED BY '{password}';\nGRANT SELECT ON pinpoint_test.* TO 'pinpoint_ro'@'{host}';\n")
    else:
        write('/etc/bind/named.conf.options', f'options {{ directory "/var/cache/bind"; recursion yes; allow-query {{ localhost; {network}; }}; listen-on {{ any; }}; listen-on-v6 {{ none; }}; dnssec-validation auto; }};\n')
        write('/etc/bind/named.conf.local', 'zone "test.local" { type master; file "/etc/bind/db.pinpoint-test"; };\n')
        first = str(ipaddress.ip_address(config['target01_address']))
        second = str(ipaddress.ip_address(config['target02_address']))
        write('/etc/bind/db.pinpoint-test', f'$TTL 60\n@ IN SOA target02.test.local. admin.test.local. (2026100301 60 60 3600 60)\n@ IN NS target02.test.local.\ntarget01 IN A {first}\ntarget02 IN A {second}\n')
        write('/etc/chrony/conf.d/pinpoint-test.conf', f'local stratum 10\nallow {network}\n')
        write('/etc/snmp/snmpd.conf', f'agentAddress udp:161\nsysLocation Pinpoint disposable lab\nsysContact test-only\nrocommunity {config["snmp_community"]} {host}/32\n', 0o600)
        write('/etc/systemd/system/pinpoint-test-udp.service', unit('UDP4-RECVFROM:69,reuseaddr,fork', 'UDP echo on 69'))
        run(['named-checkconf'])
        run(['named-checkzone', 'test.local', '/etc/bind/db.pinpoint-test'])
        units = ['ssh', 'named', 'chrony', 'snmpd', 'pinpoint-test-udp']
        run(['systemctl', 'daemon-reload'])
        run(['systemctl', 'enable', *units])
        run(['systemctl', 'restart', *units])
    run(['systemctl', 'is-active', *units])
    write('/var/lib/pinpoint-lab-ready', target + '\n')


def unit(listener, description):
    """Return a dedicated systemd definition for a disposable echo listener."""
    return f'[Unit]\nDescription=Pinpoint disposable {description}\nAfter=network-online.target\n[Service]\nExecStart=/usr/bin/socat {listener} EXEC:/bin/cat\nRestart=on-failure\n[Install]\nWantedBy=multi-user.target\n'


if __name__ == '__main__':
    if os.geteuid() != 0 or not Path('/etc/pinpoint-disposable-target').is_file():
        raise SystemExit('Refusing setup outside a root-owned disposable lab guest')
    config = json.loads(Path('/etc/pinpoint-lab.json').read_text())
    if Path('/etc/pinpoint-disposable-target').read_text().strip() != config['target']:
        raise SystemExit('Disposable target marker mismatch')
    Path('/var/lib/pinpoint-lab-ready').unlink(missing_ok=True)
    configure(config)
