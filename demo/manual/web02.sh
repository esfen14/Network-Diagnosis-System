#!/usr/bin/env bash
# web02 - 10.77.0.3 - ssh (22), http (80)
# Run as root inside the VM:  sudo bash web02.sh [LAN_INTERFACE]
# The VM needs two adapters: Adapter 1 NAT (internet, for installing packages) and
# Adapter 2 on the VirtualBox Internal Network "pinpoint-demo" (the lab network).
# LAN_INTERFACE is the Adapter 2 name from `ip -br link` (default: enp0s8).
# Safe to run again.
set -euo pipefail
NAME=web02; IP=10.77.0.3; LAN_IF="${1:-enp0s8}"
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y openssh-server nginx

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
cat > /etc/nginx/conf.d/demo.conf <<'NGINX'
server {
    listen 80 default_server;
    root /var/www/demo;
}
NGINX
nginx -t
systemctl enable --now ssh nginx
systemctl restart nginx

echo; echo "== $NAME listening on:"; ss -ltn | grep -E ':(22|80) '
