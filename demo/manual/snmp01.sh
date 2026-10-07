#!/usr/bin/env bash
# snmp01 - 10.77.0.5 - ssh (22), snmp (161/udp, community "public", read-only)
# Run as root inside the VM:  sudo bash snmp01.sh [LAN_INTERFACE]
# The VM needs two adapters: Adapter 1 NAT (internet, for installing packages) and
# Adapter 2 on the VirtualBox Internal Network "pinpoint-demo" (the lab network).
# LAN_INTERFACE is the Adapter 2 name from `ip -br link` (default: enp0s8).
# Safe to run again.
set -euo pipefail
NAME=snmp01; IP=10.77.0.5; LAN_IF="${1:-enp0s8}"
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y openssh-server snmpd

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

cat > /etc/snmp/snmpd.conf <<'SNMP'
agentAddress udp:161
sysLocation Pinpoint demo lab
sysContact demo
rocommunity public 10.77.0.0/28
SNMP
systemctl enable --now ssh snmpd
systemctl restart snmpd

echo; echo "== $NAME listening on:"; ss -ltn | grep -E ':22 '; ss -lun | grep -E ':161 '
