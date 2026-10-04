#!/usr/bin/env bash
# Prepare the disposable infrastructure target. Preview-only unless --apply is supplied.
set -euo pipefail

if [[ "${1:-}" != "--apply" ]]; then
  echo "Preview: install SSH, DNS, NTP, SNMP, socat, and and a UDP/69 TFTP responder."
  echo "Run as root with --apply only inside the disposable target02 guest."
  exit 0
fi

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: configure_target02.sh --apply must run as root." >&2
  exit 2
fi

if [[ ! -f /etc/debian_version ]]; then
  echo "ERROR: this bootstrap supports Debian/Ubuntu guests only." >&2
  exit 2
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y openssh-server bind9 bind9-utils chrony snmpd python3

install -m 0644 /dev/stdin /etc/bind/named.conf.options <<'EOF'
options {
    directory "/var/cache/bind";
    recursion yes;
    allow-query { any; };
    listen-on { any; };
    listen-on-v6 { none; };
    dnssec-validation auto;
};
EOF

install -d -m 0755 /etc/chrony/conf.d
install -m 0644 /dev/stdin /etc/chrony/conf.d/pinpoint-test.conf <<'EOF'
local stratum 10
allow 192.168.130.0/28
EOF

install -m 0600 /dev/stdin /etc/snmp/snmpd.conf <<'EOF'
agentAddress udp:161
sysLocation Pinpoint disposable lab
sysContact test-only
rocommunity public 192.168.130.1/32
EOF

# nmap reports open|filtered for UDP ports that ignore its empty probe, so the
# listener must answer a real protocol probe. Any TFTP request gets a TFTP
# ERROR packet, which nmap's service probe recognises as an open tftp port.
install -m 0755 /dev/stdin /usr/local/sbin/pinpoint-test-tftp.py <<'PY'
#!/usr/bin/python3
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", 69))
while True:
    _data, addr = sock.recvfrom(1024)
    sock.sendto(b"\x00\x05\x00\x01File not found\x00", addr)
PY

install -m 0644 /dev/stdin /etc/systemd/system/pinpoint-test-udp.service <<'EOF'
[Unit]
Description=Pinpoint disposable TFTP responder on UDP port 69
After=network-online.target

[Service]
ExecStart=/usr/bin/python3 /usr/local/sbin/pinpoint-test-tftp.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

named-checkconf
chronyd -p
systemctl daemon-reload
systemctl enable --now ssh bind9 chrony snmpd pinpoint-test-udp

echo "target02 core infrastructure services are configured."
