#!/usr/bin/env bash
# app01 - 10.77.0.4 - ssh (22), http on the non-standard port 8080
# Run as root inside the VM:  sudo bash app01.sh [LAN_INTERFACE]
# The VM needs two adapters: Adapter 1 NAT (internet, for installing packages) and
# Adapter 2 on the VirtualBox Internal Network "pinpoint-demo" (the lab network).
# LAN_INTERFACE is the Adapter 2 name from `ip -br link` (default: enp0s8).
# Safe to run again.
set -euo pipefail
NAME=app01; IP=10.77.0.4; LAN_IF="${1:-enp0s8}"
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
echo "<h1>$NAME</h1><p>Pinpoint demo lab server (port 8080)</p>" > /var/www/demo/index.html
rm -f /etc/nginx/sites-enabled/default
cat > /etc/nginx/conf.d/demo.conf <<'NGINX'
server {
    listen 8080 default_server;
    root /var/www/demo;
}
NGINX
nginx -t
systemctl enable --now ssh nginx
systemctl restart nginx

echo; echo "== $NAME listening on:"; ss -ltn | grep -E ':(22|8080) '
