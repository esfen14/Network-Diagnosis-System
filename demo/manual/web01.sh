#!/usr/bin/env bash
# web01 - 10.77.0.2 - ssh (22), http (80), https (443)
# Run as root inside the VM:  sudo bash web01.sh [LAN_INTERFACE]
# The VM needs two adapters: Adapter 1 NAT (internet, for installing packages) and
# Adapter 2 on the VirtualBox Internal Network "pinpoint-demo" (the lab network).
# LAN_INTERFACE is the Adapter 2 name from `ip -br link` (default: enp0s8).
# Safe to run again.
set -euo pipefail
NAME=web01; IP=10.77.0.2; LAN_IF="${1:-enp0s8}"
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y openssh-server nginx openssl

hostnamectl set-hostname "$NAME"
cat > /etc/netplan/60-demo-lan.yaml <<NETPLAN
network:
  version: 2
  ethernets:
    $LAN_IF:
      addresses: ["$IP/28"]
NETPLAN
chmod 600 /etc/netplan/60-demo-lan.yaml
netplan apply

install -d /var/www/demo
echo "<h1>$NAME</h1><p>Pinpoint demo lab server</p>" > /var/www/demo/index.html
rm -f /etc/nginx/sites-enabled/default
if [ ! -s /etc/ssl/private/demo.key ]; then
    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=$NAME" \
        -keyout /etc/ssl/private/demo.key -out /etc/ssl/certs/demo.crt
fi
cat > /etc/nginx/conf.d/demo.conf <<'NGINX'
server {
    listen 80 default_server;
    root /var/www/demo;
}
server {
    listen 443 ssl default_server;
    ssl_certificate /etc/ssl/certs/demo.crt;
    ssl_certificate_key /etc/ssl/private/demo.key;
    root /var/www/demo;
}
NGINX
nginx -t
systemctl enable --now ssh nginx
systemctl restart nginx

echo; echo "== $NAME listening on:"; ss -ltn | grep -E ':(22|80|443) '
