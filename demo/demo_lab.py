#!/usr/bin/env python3
"""
Pinpoint demo lab: build, run and show a set of small VirtualBox servers.

It creates five tiny Ubuntu servers from one base image. They are the machines
Pinpoint's network discovery finds, and every service they run is one Pinpoint
turns into a Nagios check automatically (ssh, http, https, snmp, and ncpa once
deployed). Pinpoint itself is NOT created here: use your own Pinpoint VM and put
it on the same private network (see README.md).

Safety rules
------------
* Only VMs named "pinpoint-demo-*" are ever created, changed or deleted.
* build-base, create, snapshot, reset and destroy print the exact VBoxManage
  commands and change nothing unless --apply is given. The demo controls
  (up, down, break, fix, ssh-port, load) act immediately; they only touch demo
  VMs and are reversible with `fix` / `reset`.
* Every VM has a management SSH (key only) on the NAT side, forwarded to
  127.0.0.1 only. It is separate from the SSH service that Pinpoint monitors,
  so breaking or moving the monitored SSH never cuts the demo's control.

Usage: python3 demo_lab.py COMMAND [options]   (python3 demo_lab.py -h)
Needs only Python 3.10+, VBoxManage and ssh. No pip packages.
"""
import argparse
import base64
import concurrent.futures
import contextlib
import io
import os
import re
import secrets
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import NoReturn

PREFIX = "pinpoint-demo"
BASE_SNAPSHOT = "base-ready"
DEMO_SNAPSHOT = "demo-ready"
DEMO_USER = "demo"
DEFAULT_ISO = Path.home() / "Downloads" / "ubuntu-24.04.5-live-server-amd64.iso"
DEFAULT_STATE = Path.home() / ".local" / "share" / "pinpoint-demo"
DEFAULT_LAN_NAME = "pinpoint-demo"      # VirtualBox internal network
DEFAULT_LAN_PREFIX = "10.77.0"          # first three octets; the lab is <prefix>.0/28
LAN_PREFIXLEN = 28
DEFAULT_TARGET_MEMORY = 512             # MiB per target

# Targets, in the order they are created and started. "host" is the last octet of
# the lab address (.1 is left for your Pinpoint VM). service_ssh_port is where the
# monitored SSH listens when it is not 22.
VMS = {
    "base": {"name": PREFIX + "-base", "ssh_port": 2200, "memory": 1024, "cpus": 1},
    "web01": {"role": "web", "host": 2, "ssh_port": 2201},
    "web02": {"role": "web80", "host": 3, "ssh_port": 2202},
    "app01": {"role": "app", "host": 4, "ssh_port": 2203},
    "snmp01": {"role": "snmp", "host": 5, "ssh_port": 2204},
    "legacy01": {"role": "legacy", "host": 6, "ssh_port": 2205, "service_ssh_port": 2222},
}
TARGETS = ("web01", "web02", "app01", "snmp01", "legacy01")
for target_key in TARGETS:
    VMS[target_key]["name"] = PREFIX + "-" + target_key
    VMS[target_key]["memory"] = DEFAULT_TARGET_MEMORY
    VMS[target_key]["cpus"] = 1

# What each role runs: (label shown to the audience, systemd unit, port). Every
# one of these is a service Pinpoint monitors automatically once discovered.
ROLE_SERVICES = {
    "web": [("ssh", "ssh", "22/tcp"), ("http", "nginx", "80/tcp"), ("https", "nginx", "443/tcp")],
    "web80": [("ssh", "ssh", "22/tcp"), ("http", "nginx", "80/tcp")],
    "app": [("ssh", "ssh", "22/tcp"), ("http", "nginx", "8080/tcp")],
    "snmp": [("ssh", "ssh", "22/tcp"), ("snmp", "snmpd", "161/udp")],
    "legacy": [("ssh", "ssh", "2222/tcp")],
}

PREVIEW_FIRST = ("build-base", "create", "snapshot", "reset", "destroy")

# Set by configure() from the command line.
LAN_NAME = DEFAULT_LAN_NAME
LAN_PREFIX = DEFAULT_LAN_PREFIX
ACTIVE_TARGETS = list(TARGETS)


# ==========================================================
# GUEST SCRIPTS (run inside the VMs)
# ==========================================================

# Runs once, as root, inside the base VM. Installs every role's packages with
# their services off, and sets up the management SSH and the console board.
BASE_SCRIPT = r"""#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# The installer only fetched the main section (see INSTALLER_APT); enable the rest here.
cat > /etc/apt/sources.list.d/ubuntu.sources <<'EOF'
Types: deb
URIs: https://archive.ubuntu.com/ubuntu
Suites: noble noble-updates noble-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
EOF
# The lab NAT has no IPv6; skipping it avoids slow fallbacks.
printf 'Acquire::ForceIPv4 "true";\nAcquire::Retries "3";\n' > /etc/apt/apt.conf.d/99demo

apt-get update
apt-get install -y nginx snmpd openssl curl python3

# Role services stay off until demo-role enables the ones a VM needs.
for unit in nginx snmpd; do
    systemctl disable --now "$unit" || true
done

# Clones get new MAC addresses, so cloud-init must not rewrite the network.
echo 'network: {config: disabled}' > /etc/cloud/cloud.cfg.d/99-demo-no-network.cfg
echo 'net.ipv4.ip_nonlocal_bind = 1' > /etc/sysctl.d/90-demo.conf

# Service SSH (the one Pinpoint monitors) listens on the lab address only; port
# 22 on the NAT address belongs to the management SSH below.
systemctl disable --now ssh.socket || true
install -d /etc/ssh/sshd_config.d
printf 'ListenAddress 127.0.0.1\nPort 22\nPasswordAuthentication yes\n' > /etc/ssh/sshd_config.d/10-demo.conf
install -d /etc/systemd/system/ssh.service.d
printf '[Service]\nRuntimeDirectoryPreserve=yes\n' > /etc/systemd/system/ssh.service.d/10-demo-preserve.conf
systemctl enable ssh

cat > /etc/ssh/demo_mgmt_sshd_config <<'EOF'
Port 22
ListenAddress 10.0.2.15
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
AllowUsers demo
PidFile /run/demo-mgmt-sshd.pid
UsePAM yes
Subsystem sftp /usr/lib/openssh/sftp-server
EOF

cat > /etc/systemd/system/demo-mgmt-sshd.service <<'EOF'
[Unit]
Description=Demo lab management SSH (NAT side only)
After=network-online.target
Wants=network-online.target

[Service]
RuntimeDirectory=sshd
RuntimeDirectoryMode=0755
RuntimeDirectoryPreserve=yes
ExecStartPre=/usr/sbin/sshd -t -f /etc/ssh/demo_mgmt_sshd_config
ExecStart=/usr/sbin/sshd -D -f /etc/ssh/demo_mgmt_sshd_config
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# The VM console shows a live service board, so the audience can see the VM.
install -d /etc/demo-lab
install -d /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/10-demo-autologin.conf <<'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty -o '-p -- \\u' --noclear --autologin demo %I $TERM
EOF
cat > /home/demo/.bash_profile <<'EOF'
if [ "$(tty)" = /dev/tty1 ]; then
    exec /usr/local/bin/demo-board
fi
[ -f ~/.bashrc ] && . ~/.bashrc
EOF
chown demo:demo /home/demo/.bash_profile

cat > /usr/local/bin/demo-board <<'EOF'
#!/usr/bin/env bash
# Live service board for the VM console (tty1).
CONF=/etc/demo-lab/services.conf
while true; do
    clear
    printf '\033[1m%s\033[0m   Pinpoint demo lab\n' "$(hostname)"
    printf 'LAN %s   up %s   load %s\n\n' \
        "$(ip -4 -br addr show lan0 2>/dev/null | awk '{print $3}')" \
        "$(uptime -p | sed 's/^up //')" "$(cut -d' ' -f1-3 /proc/loadavg)"
    printf '%-10s %-9s %s\n' SERVICE PORT STATE
    if [ -r "$CONF" ]; then
        while read -r label unit port; do
            if systemctl is-active --quiet "$unit"; then
                state=$'\033[1;32mUP\033[0m'
            else
                state=$'\033[1;31mDOWN\033[0m'
            fi
            printf '%-10s %-9s %s\n' "$label" "$port" "$state"
        done < "$CONF"
    else
        echo "(no role configured yet)"
    fi
    printf '\n%s\n' "$(date '+%H:%M:%S')"
    sleep 2
done
EOF
chmod 755 /usr/local/bin/demo-board

cat > /usr/local/sbin/demo-role <<'EOF'
#!/usr/bin/env bash
# demo-role ROLE NAME IP LAN_MAC SSH_PORT LAN_CIDR: turn a clone of the base into a lab target.
set -euo pipefail
ROLE="$1"; NAME="$2"; IP="$3"; LAN_MAC="$4"; SSH_PORT="$5"; LAN_CIDR="$6"

hostnamectl set-hostname "$NAME"
sed -i '/^127\.0\.1\.1 /d' /etc/hosts
echo "127.0.1.1 $NAME" >> /etc/hosts

cat > /etc/netplan/60-demo-lan.yaml <<NETPLAN
network:
  version: 2
  ethernets:
    demo-lan:
      match:
        macaddress: "$LAN_MAC"
      set-name: lan0
      addresses: ["$IP/28"]
NETPLAN
chmod 600 /etc/netplan/60-demo-lan.yaml
netplan apply

printf 'ListenAddress %s\nPort %s\nPasswordAuthentication yes\n' "$IP" "$SSH_PORT" > /etc/ssh/sshd_config.d/10-demo.conf

web_site() {
    # web_site PORT...: serve the demo page on the given plain-HTTP port.
    install -d /var/www/demo
    echo "<h1>$NAME</h1><p>Pinpoint demo lab server</p>" > /var/www/demo/index.html
    rm -f /etc/nginx/sites-enabled/default
    : > /etc/nginx/conf.d/demo.conf
    for port in "$@"; do
        printf 'server {\n    listen %s default_server;\n    root /var/www/demo;\n}\n' "$port" >> /etc/nginx/conf.d/demo.conf
    done
}

UNITS=""
case "$ROLE" in
web)
    web_site 80
    if [ ! -s /etc/ssl/private/demo.key ]; then
        openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=$NAME" \
            -keyout /etc/ssl/private/demo.key -out /etc/ssl/certs/demo.crt
    fi
    cat >> /etc/nginx/conf.d/demo.conf <<'NGINX'
server {
    listen 443 ssl default_server;
    ssl_certificate /etc/ssl/certs/demo.crt;
    ssl_certificate_key /etc/ssl/private/demo.key;
    root /var/www/demo;
}
NGINX
    UNITS="nginx"
    printf 'ssh ssh %s/tcp\nhttp nginx 80/tcp\nhttps nginx 443/tcp\n' "$SSH_PORT" > /etc/demo-lab/services.conf
    ;;
web80)
    web_site 80
    UNITS="nginx"
    printf 'ssh ssh %s/tcp\nhttp nginx 80/tcp\n' "$SSH_PORT" > /etc/demo-lab/services.conf
    ;;
app)
    web_site 8080
    UNITS="nginx"
    printf 'ssh ssh %s/tcp\nhttp nginx 8080/tcp\n' "$SSH_PORT" > /etc/demo-lab/services.conf
    ;;
snmp)
    printf 'agentAddress udp:161\nsysLocation Pinpoint demo lab\nsysContact demo\nrocommunity public %s\n' "$LAN_CIDR" > /etc/snmp/snmpd.conf
    UNITS="snmpd"
    printf 'ssh ssh %s/tcp\nsnmp snmpd 161/udp\n' "$SSH_PORT" > /etc/demo-lab/services.conf
    ;;
legacy)
    printf 'ssh ssh %s/tcp\n' "$SSH_PORT" > /etc/demo-lab/services.conf
    ;;
*)
    echo "unknown role: $ROLE" >&2
    exit 2
    ;;
esac

systemctl daemon-reload
if [ -n "$UNITS" ]; then
    # shellcheck disable=SC2086
    systemctl enable $UNITS
    # shellcheck disable=SC2086
    systemctl restart $UNITS
fi
systemctl restart ssh
systemctl restart getty@tty1
EOF
chmod 755 /usr/local/sbin/demo-role

systemctl daemon-reload
systemctl enable demo-mgmt-sshd
"""

# One compact status report per VM for the `wall`: uptime, load, then one line
# per service: label port state.
REMOTE_STATUS = (
    "uptime -p; cut -d' ' -f1-3 /proc/loadavg; "
    "while read -r label unit port; do "
    "printf '%s %s %s\\n' \"$label\" \"$port\" \"$(systemctl is-active $unit)\"; "
    "done < /etc/demo-lab/services.conf"
)


# ==========================================================
# CONFIGURATION AND HELPERS
# ==========================================================

def say(message=""):
    print(message, flush=True)


def fail(message, code=1) -> NoReturn:
    print("ERROR: " + message, file=sys.stderr)
    sys.exit(code)


def configure(args):
    """Apply the global command-line options (network, targets, memory)."""
    global LAN_NAME, LAN_PREFIX, ACTIVE_TARGETS
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.lan_name):
        fail("--lan-name may only contain letters, digits, '_', '.' and '-'")
    if not re.fullmatch(r"\d{1,3}\.\d{1,3}\.\d{1,3}", args.lan_prefix):
        fail("--lan-prefix must be three octets such as 10.77.0")
    for octet in args.lan_prefix.split("."):
        if int(octet) > 255:
            fail("--lan-prefix has an octet above 255")
    LAN_NAME = args.lan_name
    LAN_PREFIX = args.lan_prefix

    if args.targets:
        chosen = []
        for key in args.targets.split(","):
            key = key.strip()
            if key not in TARGETS:
                fail("unknown target '" + key + "'. Choose from: " + ", ".join(TARGETS))
            if key not in chosen:
                chosen.append(key)
        ACTIVE_TARGETS = chosen
    else:
        ACTIVE_TARGETS = list(TARGETS)

    if args.memory < 256:
        fail("--memory must be at least 256 MiB")
    for key in TARGETS:
        VMS[key]["memory"] = args.memory


def lan_cidr():
    return LAN_PREFIX + ".0/" + str(LAN_PREFIXLEN)


def lan_ip(key):
    return LAN_PREFIX + "." + str(VMS[key]["host"])


def service_ssh_port(key):
    return VMS[key].get("service_ssh_port", 22)


def quote_args(args):
    """Shell-quoted form of an argument list, for printing."""
    parts = []
    for arg in args:
        parts.append(shlex.quote(str(arg)))
    return " ".join(parts)


def vbox_read(*args):
    """Run a read-only VBoxManage command and return the CompletedProcess."""
    command = ["VBoxManage"]
    for arg in args:
        command.append(str(arg))
    try:
        return subprocess.run(command, capture_output=True, text=True)
    except FileNotFoundError:
        fail("VBoxManage was not found. Install VirtualBox first.")


def vbox_do(apply, *args, check=True):
    """Print one VBoxManage command; run it only when apply is true."""
    say("  + VBoxManage " + quote_args(args))
    if not apply:
        return None
    result = vbox_read(*args)
    if check and result.returncode != 0:
        fail("VBoxManage " + quote_args(args) + " failed:\n" + result.stderr.strip())
    return result


def parse_vm_names(text):
    """Names from `VBoxManage list vms` output (lines like: "name" {uuid})."""
    names = []
    for line in text.splitlines():
        if line.startswith('"') and '" {' in line:
            names.append(line[1:line.index('" {')])
    return names


def parse_machine_readable(text):
    """key="value" lines from --machinereadable output as a dict."""
    info = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        info[key.strip().strip('"')] = value.strip().strip('"')
    return info


def format_mac(raw):
    """08002712AB34 -> 08:00:27:12:ab:34."""
    raw = raw.lower()
    pairs = []
    for index in range(0, 12, 2):
        pairs.append(raw[index:index + 2])
    return ":".join(pairs)


def registered_vms():
    return parse_vm_names(vbox_read("list", "vms").stdout)


def vm_exists(name):
    return name in registered_vms()


def vm_info(name):
    result = vbox_read("showvminfo", name, "--machinereadable")
    if result.returncode != 0:
        return {}
    return parse_machine_readable(result.stdout)


def vm_state(name):
    """VirtualBox state ('running', 'poweroff', ...) or 'missing'."""
    if not vm_exists(name):
        return "missing"
    return vm_info(name).get("VMState", "unknown")


def snapshot_names(info):
    names = []
    for key, value in info.items():
        if key == "SnapshotName" or key.startswith("SnapshotName-"):
            names.append(value)
    return names


def default_machine_folder():
    text = vbox_read("list", "systemproperties").stdout
    for line in text.splitlines():
        if line.startswith("Default machine folder:"):
            return Path(line.split(":", 1)[1].strip())
    return Path.home() / "VirtualBox VMs"


def require(condition, message, apply):
    """Fail when applying; only warn in a preview so the plan still prints."""
    if condition:
        return
    if apply:
        fail(message)
    say("  NOTE: " + message)


def lan_mac(name):
    """MAC of NIC 2 (the lab NIC) of a VM, in colon form."""
    raw = vm_info(name).get("macaddress2", "")
    if len(raw) != 12:
        return ""
    return format_mac(raw)


# ==========================================================
# CREDENTIALS AND SSH
# ==========================================================

def key_path(state_dir):
    return Path(state_dir) / "id_ed25519_demo"


def password_path(state_dir):
    return Path(state_dir) / "demo-password"


def ensure_credentials(state_dir, apply):
    """Create the demo SSH key and the demo user's password if missing."""
    state_dir = Path(state_dir)
    key = key_path(state_dir)
    pw = password_path(state_dir)
    if key.exists() and pw.exists():
        return
    say("  + create SSH key and demo password in " + str(state_dir) + " (mode 600)")
    if not apply:
        return
    state_dir.mkdir(parents=True, exist_ok=True)
    state_dir.chmod(0o700)
    if not key.exists():
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "pinpoint-demo",
                        "-f", str(key)], check=True)
    if not pw.exists():
        pw.write_text(secrets.token_urlsafe(12) + "\n")
        pw.chmod(0o600)


def ssh_base(state_dir, vm_key):
    port = VMS[vm_key]["ssh_port"]
    return ["ssh", "-i", str(key_path(state_dir)), "-p", str(port),
            "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR",
            "-o", "ConnectTimeout=3", DEMO_USER + "@127.0.0.1"]


def ssh_run(state_dir, vm_key, command, stdin_text=None, timeout=60, check=True):
    """Run a command in a VM over the management SSH; returns CompletedProcess."""
    result = subprocess.run(ssh_base(state_dir, vm_key) + [command], input=stdin_text,
                            capture_output=True, text=True, timeout=timeout)
    if check and result.returncode != 0:
        fail("ssh to " + vm_key + " failed: " + (result.stderr.strip() or result.stdout.strip()))
    return result


def run_script(state_dir, vm_key, script, timeout):
    """Copy a script into the VM and run it as root (not via stdin: apt reads stdin)."""
    ssh_run(state_dir, vm_key, "cat > /tmp/demo-script.sh", stdin_text=script)
    return ssh_run(state_dir, vm_key, "sudo bash /tmp/demo-script.sh", timeout=timeout)


def wait_for_ssh(state_dir, vm_key, minutes, vm_name=None):
    """Poll the management SSH until it answers; False on timeout.

    With vm_name, also give up as soon as that VM is no longer running, because a
    powered-off guest will never answer.
    """
    deadline = time.time() + minutes * 60
    started = time.time()
    while time.time() < deadline:
        if vm_name is not None and vm_state(vm_name) != "running":
            return False
        try:
            if ssh_run(state_dir, vm_key, "true", timeout=8, check=False).returncode == 0:
                return True
        except subprocess.TimeoutExpired:
            pass
        say("    waiting for " + vm_key + " ... " + str(int((time.time() - started) / 60)) + " min")
        time.sleep(15)
    return False


def wait_for_state(name, wanted, seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if vm_state(name) == wanted:
            return True
        time.sleep(3)
    return False


# The installer's own `apt-get update` downloads every index of every repository
# section. On a slow link that ran for more than 25 minutes and then failed, so the
# installer fetches only the main section of the release pocket and installs
# openssh-server itself; BASE_SCRIPT enables the rest over SSH afterwards.
# The mirror is used over https: on some networks plain http to the Ubuntu
# mirrors is reset while https works.
INSTALLER_APT = """  apt:
    geoip: false
    fallback: offline-install
    primary:
      - arches: [default]
        uri: https://archive.ubuntu.com/ubuntu
    disable_components: [restricted, universe, multiverse]
    disable_suites: [updates, backports, security]
  ssh:
    install-server: true
"""
VBOX_DEFAULT_APT = "  apt:\n    fallback: offline-install\n"


def patch_installer_config(apply, name):
    """Swap the apt section of the generated autoinstall file before the VM starts."""
    if not apply:
        say("  + patch the installer's apt settings (main only, openssh-server from the installer)")
        return
    files = sorted((default_machine_folder() / name).glob("Unattended-*-user-data"))
    if not files:
        fail("VirtualBox did not generate the installer's user-data file; cannot set its apt options.")
    text = files[0].read_text()
    if VBOX_DEFAULT_APT not in text:
        fail("the installer's user-data has no apt section in the expected form; "
             "this VirtualBox version needs demo_lab.py updated (see VBOX_DEFAULT_APT).")
    files[0].write_text(text.replace(VBOX_DEFAULT_APT, INSTALLER_APT))


def post_install_command(public_key):
    """One-line command for the unattended installer: SSH, our key, sudo."""
    script = (
        "set -e\n"
        "install -d -m 700 -o demo -g demo /home/demo/.ssh\n"
        "echo '" + public_key.strip() + "' > /home/demo/.ssh/authorized_keys\n"
        "chown demo:demo /home/demo/.ssh/authorized_keys\n"
        "chmod 600 /home/demo/.ssh/authorized_keys\n"
        "echo 'demo ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/90-demo\n"
        "chmod 440 /etc/sudoers.d/90-demo\n"
        "systemctl enable ssh\n"
    )
    encoded = base64.b64encode(script.encode()).decode()
    return "echo " + encoded + " | base64 -d | bash"


# ==========================================================
# PREFLIGHT
# ==========================================================

def mem_available_mib():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024
    return 0


def port_is_free(port):
    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def disk_free_gib(folder):
    probe = Path(folder)
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    stats = os.statvfs(str(probe))
    return int(stats.f_bavail * stats.f_frsize / (1024 ** 3))


def cmd_preflight(args):
    """Read-only checks. Exit status 1 if something blocks the demo."""
    problems = 0

    def report(ok, text, blocking=True):
        nonlocal problems
        mark = "ok  " if ok else ("FAIL" if blocking else "warn")
        say("  [" + mark + "] " + text)
        if blocking and not ok:
            problems += 1

    version = vbox_read("--version").stdout.strip()
    report(bool(version), "VirtualBox " + (version or "not found"))
    report(Path(args.iso).exists(), "Ubuntu ISO: " + str(args.iso), blocking=False)

    running = []
    for name in parse_vm_names(vbox_read("list", "runningvms").stdout):
        if not name.startswith(PREFIX):
            running.append(name)
    report(not running, "other running VMs: " + (", ".join(running) or "none")
           + ("  (they use host RAM; power them off if you are short)" if running else ""),
           blocking=False)

    needed = 0
    for key in ACTIVE_TARGETS:
        if vm_state(VMS[key]["name"]) != "running":
            needed += VMS[key]["memory"]
    free = mem_available_mib()
    report(free >= needed + 1024,
           "free RAM " + str(free) + " MiB; " + str(len(ACTIVE_TARGETS)) + " targets need "
           + str(needed) + " MiB plus headroom")

    folder = default_machine_folder()
    free_disk = disk_free_gib(folder)
    report(free_disk >= 20, "free disk in " + str(folder) + ": " + str(free_disk) + " GiB (need 20)")

    lab_running = False
    for key in ["base"] + list(TARGETS):
        state = vm_state(VMS[key]["name"])
        if state == "running":
            lab_running = True
        report(True, VMS[key]["name"] + ": " + state, blocking=False)
        leftover = folder / VMS[key]["name"]
        if state == "missing" and leftover.exists():
            report(False, leftover.name + ": a folder from an earlier lab is still on disk, so "
                   "VirtualBox cannot create the VM. Delete " + str(leftover)
                   + " (and `VBoxManage closemedium disk` any of its disks first)")

    busy = []
    wanted_ports = [VMS["base"]["ssh_port"]]
    for key in ACTIVE_TARGETS:
        wanted_ports.append(VMS[key]["ssh_port"])
    for port in wanted_ports:
        if not port_is_free(port) and not lab_running:
            busy.append(str(port))
    report(not busy, "host ports free for the management SSH forwards"
           + ("; in use: " + ", ".join(busy) if busy else ""), blocking=False)

    say("")
    say("Your Pinpoint VM must be on VirtualBox internal network '" + LAN_NAME + "' with address "
        + LAN_PREFIX + ".1/" + str(LAN_PREFIXLEN) + " (README step 1).")
    say("preflight: " + ("blocked by " + str(problems) + " item(s)" if problems else "nothing blocking"))
    return 1 if problems else 0


# ==========================================================
# BUILD AND CREATE
# ==========================================================

def cmd_build_base(args):
    """Install Ubuntu unattended into the base VM, provision it, snapshot it."""
    apply = args.apply
    name = VMS["base"]["name"]
    state_dir = Path(args.state_dir)
    ensure_credentials(state_dir, apply)

    if vm_exists(name) and BASE_SNAPSHOT in snapshot_names(vm_info(name)):
        say("Base VM already built (snapshot '" + BASE_SNAPSHOT + "'). Nothing to do.")
        return 0

    if not vm_exists(name):
        require(Path(args.iso).exists(), "Ubuntu ISO not found: " + str(args.iso), apply)
        vm_dir = default_machine_folder() / name
        disk = vm_dir / (name + ".vdi")
        public_key = "ssh-ed25519 AAAA...(demo key)"
        if apply:
            public_key = Path(str(key_path(state_dir)) + ".pub").read_text()
        say("Creating the base VM '" + name + "' (unattended Ubuntu install, about 10-20 minutes):")
        vbox_do(apply, "createvm", "--name", name, "--ostype", "Ubuntu_64", "--register")
        vbox_do(apply, "modifyvm", name, "--memory", VMS["base"]["memory"], "--cpus", 1,
                "--nic1=nat", "--audio-driver=none", "--graphicscontroller=vmsvga",
                "--rtc-use-utc=on")
        vbox_do(apply, "modifyvm", name, "--nat-pf1=ssh,tcp,127.0.0.1," + str(VMS["base"]["ssh_port"]) + ",,22")
        vbox_do(apply, "createmedium", "disk", "--filename", str(disk), "--size", 12288)
        vbox_do(apply, "storagectl", name, "--name", "SATA", "--add", "sata", "--controller", "IntelAhci")
        vbox_do(apply, "storageattach", name, "--storagectl", "SATA", "--port", 0, "--device", 0,
                "--type", "hdd", "--medium", str(disk))
        vbox_do(apply, "unattended", "install", name, "--iso=" + str(args.iso),
                "--user=" + DEMO_USER, "--user-password-file=" + str(password_path(state_dir)),
                "--full-user-name=Pinpoint Demo", "--hostname=demo-base.lab.local",
                "--locale=en_US", "--time-zone=UTC", "--no-install-additions",
                "--post-install-command=" + post_install_command(public_key))
        patch_installer_config(apply, name)
        # Disk first once installed; the empty disk falls through to the ISO the first time.
        vbox_do(apply, "modifyvm", name, "--boot1=disk", "--boot2=dvd", "--boot3=none", "--boot4=none")

    state = vm_state(name)
    if state != "running":
        vbox_do(apply, "startvm", name, "--type", "headless")
    say("Then, once the installer finishes and the VM answers on SSH:")
    say("  - provision it over SSH (packages for every role, management SSH, console board)")
    say("  - reboot once to verify the management SSH, power off, eject the ISO")
    say("  - take the powered-off snapshot '" + BASE_SNAPSHOT + "'")
    if not apply:
        return 0

    say("Waiting for the installer (it reboots on its own)...")
    if not wait_for_ssh(state_dir, "base", 45, vm_name=name):
        fail("the base VM did not answer on SSH (it stopped, or 45 minutes passed). Open its "
             "console with `VBoxManage startvm " + name + " --type separate`; if the installer "
             "stopped on an error, press Enter for a shell and read /var/log/installer/.")
    say("Provisioning the base VM...")
    run_script(state_dir, "base", BASE_SCRIPT, timeout=1800)
    ssh_run(state_dir, "base", "sudo systemctl poweroff", check=False)
    if not wait_for_state(name, "poweroff", 180):
        fail("the base VM did not power off.")

    say("Verifying the management SSH after a reboot...")
    eject_isos(name)
    vbox_do(True, "startvm", name, "--type", "headless")
    if not wait_for_ssh(state_dir, "base", 5):
        fail("after the reboot the management SSH did not come up. Check the console; "
             "the base VM was left running.")
    ssh_run(state_dir, "base", "sudo systemctl poweroff", check=False)
    wait_for_state(name, "poweroff", 180)
    vbox_do(True, "snapshot", name, "take", BASE_SNAPSHOT)
    say("Base VM ready. Next: python3 demo_lab.py create --apply")
    return 0


def set_forward(apply, name, rule, host_port, guest_port):
    """Set a NAT port-forward, first removing an inherited rule of the same name.

    VirtualBox 7.2 only accepts the delete as separate arguments
    (`--nat-pf1 delete NAME`); the `--nat-pf1=delete=NAME` form in its help text
    is rejected. A missing rule is fine, so the delete may fail; the add may not.
    """
    vbox_do(apply, "modifyvm", name, "--nat-pf1", "delete", rule, check=False)
    vbox_do(apply, "modifyvm", name, "--nat-pf1=" + rule + ",tcp,127.0.0.1," + str(host_port)
            + ",," + str(guest_port))


def eject_isos(name):
    """Detach every ISO from a powered-off VM (the installer media)."""
    for key, value in vm_info(name).items():
        if not value.lower().endswith(".iso") or key.count("-") < 2:
            continue
        controller, port, device = key.rsplit("-", 2)
        vbox_do(True, "storageattach", name, "--storagectl", controller, "--port", port,
                "--device", device, "--medium", "emptydrive", check=False)


def create_target(args, key):
    apply = args.apply
    spec = VMS[key]
    name = spec["name"]
    state_dir = Path(args.state_dir)
    say("Target " + key + " (" + spec["role"] + ", " + lan_ip(key) + ", " + str(spec["memory"])
        + " MiB, monitored SSH on port " + str(service_ssh_port(key)) + "):")
    if vm_exists(name) and DEMO_SNAPSHOT in snapshot_names(vm_info(name)):
        say("  already created (snapshot '" + DEMO_SNAPSHOT + "'), keeping it.")
        return
    if not vm_exists(name):
        vbox_do(apply, "clonevm", VMS["base"]["name"], "--snapshot", BASE_SNAPSHOT,
                "--options=link", "--name", name, "--register")
    vbox_do(apply, "modifyvm", name, "--memory", spec["memory"], "--cpus", spec["cpus"],
            "--vram", 8, "--nic2=intnet", "--intnet2=" + LAN_NAME)
    set_forward(apply, name, "ssh", spec["ssh_port"], 22)
    if not apply:
        say("  then: start, apply the " + spec["role"] + " role over SSH, power off, snapshot '"
            + DEMO_SNAPSHOT + "'")
        return
    vbox_do(True, "startvm", name, "--type", "headless")
    if not wait_for_ssh(state_dir, key, 10):
        fail(key + " did not answer on its management SSH.")
    mac = lan_mac(name)
    if not mac:
        fail("could not read the lab NIC MAC address of " + name)
    ssh_run(state_dir, key, "sudo /usr/local/sbin/demo-role " + spec["role"] + " " + key + " "
            + lan_ip(key) + " " + mac + " " + str(service_ssh_port(key)) + " " + lan_cidr(),
            timeout=300)
    ssh_run(state_dir, key, "sudo systemctl poweroff", check=False)
    wait_for_state(name, "poweroff", 180)
    vbox_do(True, "snapshot", name, "take", DEMO_SNAPSHOT)


def cmd_create(args):
    """Create the target VMs as linked clones of the base."""
    apply = args.apply
    ensure_credentials(args.state_dir, apply)
    base = VMS["base"]["name"]
    require(BASE_SNAPSHOT in snapshot_names(vm_info(base)),
            "base VM not built. Run: python3 demo_lab.py build-base --apply", apply)
    for key in ACTIVE_TARGETS:
        create_target(args, key)
    if apply:
        say("")
        say("Created. Start the lab with: python3 demo_lab.py up --gui")
    return 0


# ==========================================================
# RUNNING THE LAB
# ==========================================================

def demo_vm_keys():
    """The selected targets that exist."""
    keys = []
    for key in ACTIVE_TARGETS:
        if vm_exists(VMS[key]["name"]):
            keys.append(key)
    return keys


def start_vm(name, session):
    """startvm, retrying while VirtualBox still holds the session of a VM just powered off."""
    for attempt in range(6):
        result = vbox_do(True, "startvm", name, "--type", session, check=False)
        if result.returncode == 0:
            return
        if "locked by a session" not in result.stderr or attempt == 5:
            fail("VBoxManage startvm " + name + " failed:\n" + result.stderr.strip())
        say("  " + name + " is still being released by VirtualBox; retrying in 5 s")
        time.sleep(5)


def cmd_up(args):
    session = "gui" if args.gui else "headless"
    for key in demo_vm_keys():
        name = VMS[key]["name"]
        if vm_state(name) == "running":
            say(key + ": already running")
            continue
        say(key + ": starting (" + session + ")")
        start_vm(name, session)
    say("Lab network '" + LAN_NAME + "' " + lan_cidr() + ": point your Pinpoint VM's discovery at it.")
    return 0


def cmd_down(args):
    keys = list(reversed(demo_vm_keys()))
    for key in keys:
        name = VMS[key]["name"]
        if vm_state(name) != "running":
            continue
        say(key + ": shutting down")
        vbox_do(True, "controlvm", name, "acpipowerbutton")
    for key in keys:
        name = VMS[key]["name"]
        if vm_state(name) in ("missing", "poweroff"):
            continue
        if not wait_for_state(name, "poweroff", 60):
            say(key + ": did not stop in 60 s, powering off")
            vbox_do(True, "controlvm", name, "poweroff", check=False)
    return 0


def collect_target(state_dir, key):
    """Status of one target: dict with state and, when reachable, services."""
    name = VMS[key]["name"]
    state = vm_state(name)
    result = {"key": key, "state": state, "services": [], "uptime": "", "load": ""}
    if state != "running":
        return result
    try:
        reply = ssh_run(state_dir, key, REMOTE_STATUS, timeout=8, check=False)
    except subprocess.TimeoutExpired:
        result["note"] = "management SSH timed out"
        return result
    if reply.returncode != 0:
        result["note"] = "booting or management SSH not up yet"
        return result
    lines = reply.stdout.splitlines()
    if len(lines) >= 2:
        result["uptime"] = lines[0]
        result["load"] = lines[1]
    for line in lines[2:]:
        parts = line.split()
        if len(parts) == 3:
            result["services"].append((parts[0], parts[1], parts[2]))
    return result


def colour(text, code, use_colour):
    if not use_colour:
        return text
    return "\033[" + code + "m" + text + "\033[0m"


def render_wall(results, use_colour):
    lines = []
    lines.append(colour("Pinpoint demo lab", "1", use_colour) + "   " + time.strftime("%H:%M:%S")
                 + "   network " + LAN_NAME + " " + lan_cidr())
    for result in results:
        key = result["key"]
        state = result["state"]
        shown = colour(state, "1;32" if state == "running" else "1;31", use_colour)
        extra = ""
        if state == "running" and result["uptime"]:
            extra = "   " + result["uptime"] + ", load " + result["load"]
        if result.get("note"):
            extra = "   " + result["note"]
        lines.append("")
        lines.append(key.ljust(9) + " " + lan_ip(key).ljust(11) + " " + shown + extra)
        for label, port, status in result["services"]:
            ok = status == "active"
            mark = colour("UP  ", "1;32", use_colour) if ok else colour("DOWN", "1;31", use_colour)
            lines.append("    " + label.ljust(9) + port.ljust(9) + mark)
    return "\n".join(lines)


def build_wall(args):
    use_colour = sys.stdout.isatty() and not args.no_colour
    keys = demo_vm_keys()
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = []
        for key in keys:
            futures.append(pool.submit(collect_target, args.state_dir, key))
        for future in futures:
            results.append(future.result())
    if not results:
        return "No demo VMs yet. Run: python3 demo_lab.py create --apply"
    return render_wall(results, use_colour)


def cmd_status(args):
    args.no_colour = False
    say(build_wall(args))
    return 0


def cmd_wall(args):
    """Live board for the presenter's screen. Ctrl-C to stop."""
    if args.once:
        say(build_wall(args))
        return 0
    try:
        while True:
            text = build_wall(args)
            sys.stdout.write("\033[H\033[2J" + text + "\n")
            sys.stdout.flush()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        say("")
        return 0


# ==========================================================
# DEMO CONTROLS
# ==========================================================

def role_services(vm_key):
    return ROLE_SERVICES[VMS[vm_key]["role"]]


def unit_for(vm_key, service):
    for label, unit, _port in role_services(vm_key):
        if label == service:
            return unit
    labels = []
    for label, _unit, _port in role_services(vm_key):
        labels.append(label)
    fail(vm_key + " has no service '" + service + "'. Choose from: " + ", ".join(labels) + ", host")


def cmd_break(args):
    """Stop a monitored service (or power the VM off) so Pinpoint raises an alert."""
    name = VMS[args.vm]["name"]
    if args.service == "host":
        say(args.vm + ": powering off (host down)")
        vbox_do(True, "controlvm", name, "poweroff")
        return 0
    unit = unit_for(args.vm, args.service)
    say(args.vm + ": stopping " + args.service + " (" + unit + ")")
    ssh_run(args.state_dir, args.vm, "sudo systemctl stop " + unit)
    return 0


def cmd_fix(args):
    """Undo `break`: start the service(s) again, or boot the VM."""
    name = VMS[args.vm]["name"]
    if args.service == "host":
        say(args.vm + ": starting")
        start_vm(name, "gui" if args.gui else "headless")
        return 0
    units = []
    if args.service == "all":
        for _label, unit, _port in role_services(args.vm):
            if unit not in units:
                units.append(unit)
    else:
        units.append(unit_for(args.vm, args.service))
    say(args.vm + ": starting " + ", ".join(units))
    ssh_run(args.state_dir, args.vm, "sudo systemctl start " + " ".join(units))
    return 0


def cmd_ssh_port(args):
    """Move the monitored SSH service to another port (22 puts it back).

    Pinpoint keeps preferring the port it knew until that port has been missing
    for five scans, so use this to show the change on the wall; do not rely on it
    for an NCPA deployment right after the move. legacy01 already starts on 2222.
    """
    port = args.port
    if port != 22 and not 1024 <= port <= 65535:
        fail("use 22 or a port from 1024 to 65535")
    ip = lan_ip(args.vm)
    remote = (
        "printf 'ListenAddress " + ip + "\\nPort " + str(port) + "\\nPasswordAuthentication yes\\n' "
        "| sudo tee /etc/ssh/sshd_config.d/10-demo.conf >/dev/null && "
        "sudo sed -i 's#^ssh ssh .*#ssh ssh " + str(port) + "/tcp#' /etc/demo-lab/services.conf && "
        "sudo systemctl restart ssh"
    )
    say(args.vm + ": monitored SSH now on port " + str(port) + " (management SSH is unaffected)")
    say("  note: Pinpoint prefers the old port until it has been missing for 5 scans")
    ssh_run(args.state_dir, args.vm, remote)
    return 0


def cmd_load(args):
    """Burn every CPU for a while so the CPU graph and thresholds move."""
    seconds = int(args.seconds)
    remote = ("setsid sudo timeout " + str(seconds) + " sh -c "
              "'for i in $(seq $(nproc)); do (while :; do :; done) & done; wait' "
              ">/dev/null 2>&1 < /dev/null &")
    say(args.vm + ": CPU load for " + str(seconds) + " s")
    ssh_run(args.state_dir, args.vm, remote)
    return 0


def cmd_shell(args):
    """Open an interactive management shell in a target."""
    command = ssh_base(args.state_dir, args.vm)
    os.execvp(command[0], command)


def cmd_creds(args):
    """Print what you type into the NCPA deployment wizard."""
    pw = password_path(args.state_dir)
    if not pw.exists():
        fail("no credentials yet. Run build-base first.")
    say("Username: " + DEMO_USER)
    say("Password: " + pw.read_text().strip())
    parts = []
    for key in ACTIVE_TARGETS:
        parts.append(lan_ip(key) + " (" + key + ")")
    say("Targets: " + ", ".join(parts))
    return 0


# ==========================================================
# SNAPSHOTS, RESET, DESTROY
# ==========================================================

def cmd_snapshot(args):
    """Re-take the clean snapshot on powered-off targets."""
    apply = args.apply
    keys = args.vms or demo_vm_keys()
    for key in keys:
        name = VMS[key]["name"]
        say(key + ":")
        require(vm_state(name) == "poweroff", name + " must be powered off first (python3 demo_lab.py down)", apply)
        if DEMO_SNAPSHOT in snapshot_names(vm_info(name)):
            vbox_do(apply, "snapshot", name, "delete", DEMO_SNAPSHOT)
        vbox_do(apply, "snapshot", name, "take", DEMO_SNAPSHOT)
    return 0


def confirm(args, question):
    """Ask the person at the terminal before a destructive step; --yes skips it."""
    if not args.apply or getattr(args, "yes", False):
        return
    if not sys.stdin.isatty():
        fail("this needs a person at the terminal to confirm, or pass --yes.")
    answer = input(question + " Type 'yes' to continue: ")
    if answer.strip().lower() != "yes":
        say("Cancelled. Nothing was changed.")
        sys.exit(1)


def cmd_reset(args):
    """Return every selected target to its clean snapshot (a clean state for the next run)."""
    apply = args.apply
    keys = demo_vm_keys()
    if keys:
        confirm(args, "This discards everything changed in " + ", ".join(keys) + " since their clean snapshot.")
    for key in demo_vm_keys():
        name = VMS[key]["name"]
        say(key + ":")
        if vm_state(name) == "running":
            vbox_do(apply, "controlvm", name, "poweroff")
            if apply:
                wait_for_state(name, "poweroff", 60)
        vbox_do(apply, "snapshot", name, "restore", DEMO_SNAPSHOT)
    if apply and args.up:
        return cmd_up(args)
    return 0


def remove_installer_leftovers(apply, name):
    """The unattended installer leaves aux files and a registered .viso behind."""
    folder = default_machine_folder() / name
    if not apply:
        say("  + remove leftover installer files in " + str(folder) + " (if any)")
        return
    for line in vbox_read("list", "dvds").stdout.splitlines():
        if line.startswith("Location:") and str(folder) + "/Unattended-" in line:
            vbox_do(True, "closemedium", "dvd", line.split(":", 1)[1].strip(), check=False)
    if not folder.is_dir():
        return
    leftovers = list(folder.iterdir())
    only_installer_files = True
    for path in leftovers:
        if not path.name.startswith("Unattended-"):
            only_installer_files = False
    if not only_installer_files:
        say("  leaving " + str(folder) + ": it holds files this script did not create")
        return
    for path in leftovers:
        path.unlink()
    folder.rmdir()
    say("  removed leftover installer files in " + str(folder))


def cmd_destroy(args):
    """Delete the demo VMs and their disks (all targets, then the base). Never touches other VMs."""
    apply = args.apply
    order = list(reversed(TARGETS)) + ["base"]
    existing = []
    for key in order:
        if vm_exists(VMS[key]["name"]):
            existing.append(VMS[key]["name"])
    if existing:
        confirm(args, "This deletes " + ", ".join(existing) + " and their disks.")
    for key in order:
        name = VMS[key]["name"]
        if not name.startswith(PREFIX + "-"):
            fail("refusing to delete '" + name + "'")
        if not vm_exists(name):
            continue
        say(key + ":")
        if vm_state(name) == "running":
            vbox_do(apply, "controlvm", name, "poweroff")
        vbox_do(apply, "unregistervm", name, "--delete")
        if key == "base":
            remove_installer_leftovers(apply, name)
    return 0


# ==========================================================
# SELF-TEST
# ==========================================================

def cmd_self_test(args):
    """Checks of the pure logic and the printed plan. Needs no VirtualBox VMs."""
    failures = []

    def check(condition, label):
        if not condition:
            failures.append(label)

    names = parse_vm_names('"a b" {111}\n"pinpoint-demo-base" {222}\n')
    check(names == ["a b", "pinpoint-demo-base"], "parse_vm_names")
    info = parse_machine_readable('VMState="running"\nmemory=1024\nSnapshotName="x"\nSnapshotName-1="y"\n')
    check(info["VMState"] == "running" and snapshot_names(info) == ["x", "y"], "parse_machine_readable")
    check(format_mac("080027B3A002") == "08:00:27:b3:a0:02", "format_mac")

    for role in ROLE_SERVICES:
        labels = []
        for label, _unit, _port in ROLE_SERVICES[role]:
            labels.append(label)
        check("ssh" in labels, role + " has ssh")
        # Every service must be one Pinpoint monitors on its own after discovery.
        for label in labels:
            check(label in ("ssh", "http", "https", "snmp"), role + ": " + label + " is auto-monitored")
    check(unit_for("web01", "http") == "nginx", "unit_for")
    check(service_ssh_port("legacy01") != 22, "legacy01 monitored SSH is non-standard")

    decoded = base64.b64decode(post_install_command("ssh-ed25519 AAAA test").split()[1]).decode()
    check("ssh-ed25519 AAAA test" in decoded and "NOPASSWD" in decoded, "post_install_command")

    ports = set()
    hosts = set()
    for key in VMS:
        check(VMS[key]["name"].startswith(PREFIX + "-"), key + " name prefix")
        check(VMS[key]["ssh_port"] not in ports, key + " unique management port")
        ports.add(VMS[key]["ssh_port"])
    for key in TARGETS:
        check(VMS[key]["host"] not in hosts and 2 <= VMS[key]["host"] <= 14, key + " unique lab address inside the /28")
        hosts.add(VMS[key]["host"])
        check(VMS[key]["role"] in ROLE_SERVICES, key + " has a known role")

    check("disable_components" in INSTALLER_APT and "install-server: true" in INSTALLER_APT,
          "installer apt section limits components and installs openssh-server")
    check(INSTALLER_APT.startswith(VBOX_DEFAULT_APT.split("\n")[0]), "installer apt section replaces the same key")

    script_ok = True
    if shutil_which("bash"):
        outcome = subprocess.run(["bash", "-n"], input=BASE_SCRIPT, capture_output=True, text=True)
        if outcome.returncode != 0:
            script_ok = False
            failures.append("bash -n base script: " + outcome.stderr.strip())
    check(script_ok, "guest scripts parse")

    # The confirmation: only an explicit "yes" goes ahead, and a preview never asks.
    import builtins
    saved_input, saved_isatty = builtins.input, sys.stdin.isatty
    sys.stdin.isatty = lambda: True
    try:
        ask = argparse.Namespace(apply=True, yes=False)
        builtins.input = lambda prompt="": "yes"
        confirm(ask, "q")
        check(True, "confirm accepts yes")
        builtins.input = lambda prompt="": "no"
        stopped = False
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                confirm(ask, "q")
            except SystemExit:
                stopped = True
        check(stopped, "confirm stops on anything but yes")
        builtins.input = lambda prompt="": (_ for _ in ()).throw(AssertionError("asked in a preview"))
        confirm(argparse.Namespace(apply=False, yes=False), "q")
        confirm(argparse.Namespace(apply=True, yes=True), "q")
        check(True, "confirm never asks in a preview or with --yes")
    finally:
        builtins.input = saved_input
        sys.stdin.isatty = saved_isatty

    # The printed plan for `create` with nothing built yet: no VBoxManage call is made.
    saved = (vbox_read, vm_info, vm_exists, ensure_credentials)
    globals()["vbox_read"] = lambda *a: subprocess.CompletedProcess(a, 0, "", "")
    globals()["vm_info"] = lambda name: {}
    globals()["vm_exists"] = lambda name: False
    globals()["ensure_credentials"] = lambda state_dir, apply: None
    buffer = io.StringIO()
    try:
        plan_args = argparse.Namespace(apply=False, state_dir="/nonexistent")
        with contextlib.redirect_stdout(buffer):
            cmd_create(plan_args)
    finally:
        (globals()["vbox_read"], globals()["vm_info"], globals()["vm_exists"],
         globals()["ensure_credentials"]) = saved
    plan = buffer.getvalue()
    check(plan.count("--options=link") == len(ACTIVE_TARGETS), "create plans one linked clone per target")
    check("--nat-pf1 delete ssh" in plan and "delete=ssh" not in plan, "create drops inherited forwards (7.2 syntax)")
    check("--intnet2=" + LAN_NAME in plan, "create attaches the lab network")
    check("--memory 512" in plan, "targets are small")
    check("pinpoint-demo-server" not in plan, "no Pinpoint VM is created")

    if failures:
        for item in failures:
            print("FAIL: " + item)
        return 1
    say("self-test: all checks passed")
    return 0


def shutil_which(program):
    for folder in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(folder) / program
        if candidate.exists() and os.access(str(candidate), os.X_OK):
            return str(candidate)
    return None


# ==========================================================
# COMMAND LINE
# ==========================================================

def build_parser():
    parser = argparse.ArgumentParser(description="Pinpoint demo lab (VirtualBox).")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE), help="where the SSH key and password live")
    parser.add_argument("--iso", default=str(DEFAULT_ISO), help="Ubuntu 24.04 live-server ISO for build-base")
    parser.add_argument("--lan-name", default=DEFAULT_LAN_NAME,
                        help="VirtualBox internal network the targets join (your Pinpoint VM must be on it too)")
    parser.add_argument("--lan-prefix", default=DEFAULT_LAN_PREFIX,
                        help="first three octets of the lab /28; targets use .2-.6, leave .1 for Pinpoint")
    parser.add_argument("--targets", default="",
                        help="comma-separated subset of: " + ",".join(TARGETS) + " (default: all)")
    parser.add_argument("--memory", type=int, default=DEFAULT_TARGET_MEMORY, help="MiB of RAM per target")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, handler, help_text):
        sp = sub.add_parser(name, help=help_text)
        sp.set_defaults(handler=handler)
        if name in PREVIEW_FIRST:
            sp.add_argument("--apply", action="store_true", help="really do it (default: only print the plan)")
        return sp

    add("preflight", cmd_preflight, "check this machine and the VMs (read-only)")
    add("build-base", cmd_build_base, "install and provision the base Ubuntu VM")
    add("create", cmd_create, "create the target servers from the base")
    up = add("up", cmd_up, "start the targets")
    up.add_argument("--gui", action="store_true", help="open a console window per VM")
    add("down", cmd_down, "shut the targets down")
    add("status", cmd_status, "one-off status table")
    wall = add("wall", cmd_wall, "live status board for the presenter's screen")
    wall.add_argument("--once", action="store_true")
    wall.add_argument("--interval", type=float, default=3.0)
    wall.add_argument("--no-colour", action="store_true")
    brk = add("break", cmd_break, "stop a service (or 'host') on a target")
    brk.add_argument("vm", choices=TARGETS)
    brk.add_argument("service")
    fix = add("fix", cmd_fix, "start a service again ('all' or 'host')")
    fix.add_argument("vm", choices=TARGETS)
    fix.add_argument("service")
    fix.add_argument("--gui", action="store_true")
    sshp = add("ssh-port", cmd_ssh_port, "move the monitored SSH to another port (22 = back)")
    sshp.add_argument("vm", choices=TARGETS)
    sshp.add_argument("port", type=int)
    load = add("load", cmd_load, "burn CPU on a target")
    load.add_argument("vm", choices=TARGETS)
    load.add_argument("--seconds", default=90)
    shell = add("shell", cmd_shell, "management shell in a target")
    shell.add_argument("vm", choices=TARGETS)
    snap = add("snapshot", cmd_snapshot, "re-take the clean snapshot on powered-off targets")
    snap.add_argument("vms", nargs="*", choices=list(TARGETS))
    reset = add("reset", cmd_reset, "restore every target to the clean snapshot")
    reset.add_argument("--up", action="store_true", help="start the lab afterwards")
    reset.add_argument("--gui", action="store_true")
    reset.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    add("creds", cmd_creds, "print the login for the NCPA deployment wizard")
    destroy = add("destroy", cmd_destroy, "delete the demo VMs")
    destroy.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    add("self-test", cmd_self_test, "check the script's own logic")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not hasattr(args, "apply"):
        args.apply = True
    if not hasattr(args, "gui"):
        args.gui = False
    configure(args)
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
