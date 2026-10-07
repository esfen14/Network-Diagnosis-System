#!/usr/bin/env bash
# legacy01 - 10.77.0.6 - ssh on the non-standard port 2222 (nothing on 22)
# Run as root inside the VM:  sudo bash legacy01.sh [LAN_INTERFACE]
# The VM needs two adapters: Adapter 1 NAT (internet, for installing packages) and
# Adapter 2 on the VirtualBox Internal Network "pinpoint-demo" (the lab network).
# LAN_INTERFACE is the Adapter 2 name from `ip -br link` (default: enp0s8).
# Safe to run again.
# After this runs, log in over SSH on port 2222 (or use the VM console).
set -euo pipefail
NAME=legacy01; IP=10.77.0.6; LAN_IF="${1:-enp0s8}"; SSH_PORT=2222
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y openssh-server

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

# Ubuntu 24.04 starts sshd through ssh.socket, which ignores Port in sshd_config.
systemctl disable --now ssh.socket || true
install -d /etc/ssh/sshd_config.d
printf 'Port %s\nPasswordAuthentication yes\n' "$SSH_PORT" > /etc/ssh/sshd_config.d/10-demo.conf
sshd -t
systemctl enable ssh
systemctl restart ssh

echo; echo "== $NAME listening on:"; ss -ltn | grep -E ":($SSH_PORT|22) "
