#!/usr/bin/env bash
# Prepare the disposable application target. Preview-only unless --apply is supplied.
set -euo pipefail

if [[ "${1:-}" != "--apply" ]]; then
  echo "Preview: install SSH, FTP, SMTP, nginx, MariaDB, socat, and a TCP/9000 listener."
  echo "Run as root with --apply only inside the disposable target01 guest."
  exit 0
fi

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: configure_target01.sh --apply must run as root." >&2
  exit 2
fi

if [[ ! -f /etc/debian_version ]]; then
  echo "ERROR: this bootstrap supports Debian/Ubuntu guests only." >&2
  exit 2
fi

export DEBIAN_FRONTEND=noninteractive
echo "postfix postfix/main_mailer_type select Local only" | debconf-set-selections
echo "postfix postfix/mailname string target01.test.local" | debconf-set-selections
apt-get update
apt-get install -y openssh-server nginx vsftpd postfix mariadb-server socat openssl

install -d -m 0755 /etc/nginx/pinpoint-test
if [[ ! -f /etc/nginx/pinpoint-test/server.key ]]; then
  openssl req -x509 -newkey rsa:2048 -nodes -days 7 \
    -keyout /etc/nginx/pinpoint-test/server.key \
    -out /etc/nginx/pinpoint-test/server.crt \
    -subj "/CN=target01.test.local"
  chmod 0600 /etc/nginx/pinpoint-test/server.key
fi

install -m 0644 /dev/stdin /etc/nginx/sites-available/pinpoint-test <<'EOF'
server {
    listen 80 default_server;
    server_name target01.test.local;
    location / { return 200 "pinpoint-http-ok\n"; }
}
server {
    listen 443 ssl default_server;
    server_name target01.test.local;
    ssl_certificate /etc/nginx/pinpoint-test/server.crt;
    ssl_certificate_key /etc/nginx/pinpoint-test/server.key;
    location / { return 200 "pinpoint-https-ok\n"; }
}
EOF
rm -f /etc/nginx/sites-enabled/default
ln -sfn /etc/nginx/sites-available/pinpoint-test /etc/nginx/sites-enabled/pinpoint-test

install -m 0644 /dev/stdin /etc/mysql/mariadb.conf.d/99-pinpoint-test.cnf <<'EOF'
[mysqld]
bind-address = 0.0.0.0
EOF

install -m 0644 /dev/stdin /etc/systemd/system/pinpoint-test-tcp.service <<'EOF'
[Unit]
Description=Pinpoint disposable TCP echo service on port 9000
After=network-online.target

[Service]
ExecStart=/usr/bin/socat TCP4-LISTEN:9000,reuseaddr,fork EXEC:/bin/cat
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

nginx -t
systemctl daemon-reload
systemctl enable --now ssh vsftpd postfix mariadb nginx pinpoint-test-tcp

echo "target01 core services are configured. NCPA must still be deployed through Pinpoint."
