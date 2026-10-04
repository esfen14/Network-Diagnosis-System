#!/usr/bin/env python3
"""
Pinpoint demo lab: build, run and show a small VirtualBox lab.

It creates two Ubuntu target VMs (web01, infra01) from one base image, and a
disposable copy of your Pinpoint server VM, all on a private VirtualBox
network (10.77.0.0/28) that never touches your real LAN. See README.md for the
plan, the one-time preparation and the run of show.

Safety rules
------------
* Only VMs named "pinpoint-demo-*" are ever created, changed or deleted. The
  source Pinpoint VM is only read (it is cloned, never modified).
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
import secrets
import shlex
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PREFIX = "pinpoint-demo"
LAN_NAME = "pinpoint-demo"          # VirtualBox internal network
LAN_CIDR = "10.77.0.0/28"
BASE_SNAPSHOT = "base-ready"
DEMO_SNAPSHOT = "demo-ready"
DEMO_USER = "demo"
DEFAULT_ISO = Path.home() / "Downloads" / "ubuntu-24.04.5-live-server-amd64.iso"
DEFAULT_STATE = Path.home() / ".local" / "share" / "pinpoint-demo"
DEFAULT_SOURCE_VM = "Pinpoint-installer-testing"
DEFAULT_UI_HOST_PORT = 8480        # 8080 is commonly taken on a developer laptop

VMS = {
    "base": {"name": PREFIX + "-base", "ssh_port": 2200, "memory": 1024, "cpus": 1},
    "pinpoint": {"name": PREFIX + "-server", "ip": "10.77.0.1", "ssh_port": 2201,
                 "memory": 4096, "cpus": 2},
    "web01": {"name": PREFIX + "-web01", "role": "web", "ip": "10.77.0.2",
              "ssh_port": 2202, "memory": 1024, "cpus": 1},
    "infra01": {"name": PREFIX + "-infra01", "role": "infra", "ip": "10.77.0.3",
                "ssh_port": 2203, "memory": 1024, "cpus": 1,
                # Its monitored SSH starts on a non-standard port (see README).
                "service_ssh_port": 2222},
}
TARGETS = ("web01", "infra01")

# (label shown to the audience, systemd unit, port) per role.
ROLE_SERVICES = {
    "web": [("ssh", "ssh", "22/tcp"), ("http", "nginx", "80/tcp"),
            ("https", "nginx", "443/tcp"), ("mariadb", "mariadb", "3306/tcp")],
    "infra": [("ssh", "ssh", "22/tcp"), ("dns", "named", "53/udp"),
              ("ntp", "chrony", "123/udp"), ("snmp", "snmpd", "161/udp")],
}

PREVIEW_FIRST = ("build-base", "create", "snapshot", "reset", "destroy")


# ==========================================================
# GUEST SCRIPTS (run inside the VMs)
# ==========================================================

# Runs once, as root, inside the base VM. Installs every role's packages with
# their services off, and sets up the management SSH and the console board.
BASE_SCRIPT = r"""#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y nginx mariadb-server bind9 bind9-utils chrony snmpd socat openssl curl python3

# Role services stay off until demo-role enables the ones a VM needs.
for unit in nginx mariadb named chrony snmpd; do
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
# demo-role ROLE NAME IP LAN_MAC [SSH_PORT]: turn a clone of the base into a lab target.
set -euo pipefail
ROLE="$1"; NAME="$2"; IP="$3"; LAN_MAC="$4"; SSH_PORT="${5:-22}"

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

case "$ROLE" in
web)
    install -d /var/www/demo
    echo "<h1>$NAME</h1><p>Pinpoint demo lab web server</p>" > /var/www/demo/index.html
    if [ ! -s /etc/ssl/private/demo.key ]; then
        openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=$NAME" \
            -keyout /etc/ssl/private/demo.key -out /etc/ssl/certs/demo.crt
    fi
    rm -f /etc/nginx/sites-enabled/default
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
    printf '[mysqld]\nbind-address = 0.0.0.0\n' > /etc/mysql/mariadb.conf.d/99-demo.cnf
    UNITS="nginx mariadb"
    printf 'ssh ssh %s/tcp\nhttp nginx 80/tcp\nhttps nginx 443/tcp\nmariadb mariadb 3306/tcp\n' "$SSH_PORT" > /etc/demo-lab/services.conf
    ;;
infra)
    cat > /etc/bind/named.conf.options <<'BIND'
options {
    directory "/var/cache/bind";
    recursion no;
    allow-query { any; };
    listen-on { any; };
    listen-on-v6 { none; };
};
BIND
    printf 'local stratum 10\nallow @LAN_CIDR@\n' > /etc/chrony/conf.d/demo.conf
    cat > /etc/snmp/snmpd.conf <<'SNMP'
agentAddress udp:161
sysLocation Pinpoint demo lab
sysContact demo
rocommunity public @LAN_CIDR@
SNMP
    UNITS="named chrony snmpd"
    printf 'ssh ssh %s/tcp\ndns named 53/udp\nntp chrony 123/udp\nsnmp snmpd 161/udp\n' "$SSH_PORT" > /etc/demo-lab/services.conf
    ;;
*)
    echo "unknown role: $ROLE" >&2
    exit 2
    ;;
esac

systemctl daemon-reload
# shellcheck disable=SC2086
systemctl enable $UNITS
# shellcheck disable=SC2086
systemctl restart $UNITS
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
# HELPERS
# ==========================================================

def say(message=""):
    print(message, flush=True)


def fail(message, code=1):
    print("ERROR: " + message, file=sys.stderr)
    sys.exit(code)


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


def wait_for_ssh(state_dir, vm_key, minutes):
    """Poll the management SSH until it answers; False on timeout."""
    deadline = time.time() + minutes * 60
    started = time.time()
    while time.time() < deadline:
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


def post_install_command(public_key):
    """One-line command for the unattended installer: SSH, our key, sudo."""
    script = (
        "set -e\n"
        "apt-get install -y openssh-server\n"
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
           + ("  (power them off before the demo: they use host RAM)" if running else ""),
           blocking=False)

    needed = 0
    for key in ("pinpoint", "web01", "infra01"):
        if vm_state(VMS[key]["name"]) != "running":
            needed += VMS[key]["memory"]
    free = mem_available_mib()
    report(free >= needed + 1024,
           "free RAM " + str(free) + " MiB, demo VMs need " + str(needed) + " MiB plus headroom")

    folder = default_machine_folder()
    disk_free = shutil_disk_free_gib(folder)
    report(disk_free >= 20, "free disk in " + str(folder) + ": " + str(disk_free) + " GiB (need 20)")

    source_info = vm_info(args.source_vm)
    report(bool(source_info), "source Pinpoint VM '" + args.source_vm + "' exists")
    report(DEMO_SNAPSHOT in snapshot_names(source_info),
           "source VM has a '" + DEMO_SNAPSHOT + "' snapshot (see README step 1)")

    for key in ("base", "web01", "infra01", "pinpoint"):
        state = vm_state(VMS[key]["name"])
        report(True, VMS[key]["name"] + ": " + state, blocking=False)

    lab_running = False
    for key in VMS:
        if vm_state(VMS[key]["name"]) == "running":
            lab_running = True
    busy = []
    for port in (2200, 2201, 2202, 2203, args.ui_host_port):
        if not port_is_free(port) and not lab_running:
            busy.append(str(port))
    report(not busy, "host ports free (2200-2203, " + str(args.ui_host_port) + ")"
           + ("; in use: " + ", ".join(busy) if busy else ""), blocking=False)

    say("")
    say("preflight: " + ("blocked by " + str(problems) + " item(s)" if problems else "nothing blocking"))
    return 1 if problems else 0


def shutil_disk_free_gib(folder):
    probe = Path(folder)
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    stats = os.statvfs(str(probe))
    return int(stats.f_bavail * stats.f_frsize / (1024 ** 3))


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
    if not wait_for_ssh(state_dir, "base", 45):
        fail("the base VM did not answer on SSH within 45 minutes. Open its console with "
             "`VBoxManage startvm " + name + " --type separate` to see why.")
    say("Provisioning the base VM...")
    run_script(state_dir, "base", BASE_SCRIPT.replace("@LAN_CIDR@", LAN_CIDR), timeout=1800)
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


def clone_vm(apply, source, snapshot, target):
    """Linked clone of a snapshot (small and fast), registered."""
    if vm_exists(target):
        say("  " + target + " already exists, keeping it.")
        return
    vbox_do(apply, "clonevm", source, "--snapshot", snapshot, "--options=link",
            "--name", target, "--register")


def create_target(args, key):
    apply = args.apply
    spec = VMS[key]
    name = spec["name"]
    state_dir = Path(args.state_dir)
    say("Target " + key + " (" + spec["role"] + ", " + spec["ip"] + ", monitored SSH on port "
        + str(spec.get("service_ssh_port", 22)) + "):")
    if vm_exists(name) and DEMO_SNAPSHOT in snapshot_names(vm_info(name)):
        say("  already created (snapshot '" + DEMO_SNAPSHOT + "'), keeping it.")
        return
    clone_vm(apply, VMS["base"]["name"], BASE_SNAPSHOT, name)
    vbox_do(apply, "modifyvm", name, "--memory", spec["memory"], "--cpus", spec["cpus"],
            "--nic2=intnet", "--intnet2=" + LAN_NAME)
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
            + spec["ip"] + " " + mac + " " + str(spec.get("service_ssh_port", 22)), timeout=300)
    ssh_run(state_dir, key, "sudo systemctl poweroff", check=False)
    wait_for_state(name, "poweroff", 180)
    vbox_do(True, "snapshot", name, "take", DEMO_SNAPSHOT)


def create_pinpoint(args):
    apply = args.apply
    spec = VMS["pinpoint"]
    name = spec["name"]
    say("Pinpoint server (a linked copy of '" + args.source_vm + "' at snapshot '" + DEMO_SNAPSHOT + "'):")
    source_info = vm_info(args.source_vm)
    require(DEMO_SNAPSHOT in snapshot_names(source_info),
            "'" + args.source_vm + "' has no '" + DEMO_SNAPSHOT + "' snapshot. Do README step 1 first.", apply)
    if vm_exists(name) and DEMO_SNAPSHOT in snapshot_names(vm_info(name)):
        say("  already created (snapshot '" + DEMO_SNAPSHOT + "'), keeping it.")
        return
    clone_vm(apply, args.source_vm, DEMO_SNAPSHOT, name)
    vbox_do(apply, "modifyvm", name, "--memory", spec["memory"], "--cpus", spec["cpus"],
            "--nic1=nat", "--nic2=intnet", "--intnet2=" + LAN_NAME)
    set_forward(apply, name, "ui", args.ui_host_port, args.ui_guest_port)
    set_forward(apply, name, "ssh", spec["ssh_port"], 22)
    vbox_do(apply, "snapshot", name, "take", DEMO_SNAPSHOT)


def cmd_create(args):
    """Create the target VMs and the Pinpoint server copy."""
    apply = args.apply
    ensure_credentials(args.state_dir, apply)
    base = VMS["base"]["name"]
    require(BASE_SNAPSHOT in snapshot_names(vm_info(base)),
            "base VM not built. Run: python3 demo_lab.py build-base --apply", apply)
    for key in TARGETS:
        create_target(args, key)
    create_pinpoint(args)
    if apply:
        say("")
        say("Created. Start the lab with: python3 demo_lab.py up --gui")
    return 0


# ==========================================================
# RUNNING THE LAB
# ==========================================================

def demo_vm_keys():
    """Existing demo VMs, targets first so Pinpoint finds them at its first scan."""
    keys = []
    for key in TARGETS + ("pinpoint",):
        if vm_exists(VMS[key]["name"]):
            keys.append(key)
    return keys


def cmd_up(args):
    session = "gui" if args.gui else "headless"
    for key in demo_vm_keys():
        name = VMS[key]["name"]
        if vm_state(name) == "running":
            say(key + ": already running")
            continue
        say(key + ": starting (" + session + ")")
        vbox_do(True, "startvm", name, "--type", session)
    say("Pinpoint UI (once booted): http://127.0.0.1:" + str(args.ui_host_port))
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


def pinpoint_ui_status(port):
    try:
        with urllib.request.urlopen("http://127.0.0.1:" + str(port) + "/", timeout=2) as reply:
            return "UI answers (HTTP " + str(reply.status) + ")"
    except Exception as error:
        return "UI not answering (" + type(error).__name__ + ")"


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


def render_wall(results, pinpoint_state, ui_text, use_colour):
    lines = []
    lines.append(colour("Pinpoint demo lab", "1", use_colour) + "   " + time.strftime("%H:%M:%S"))
    lines.append("")
    state_text = pinpoint_state
    if pinpoint_state == "running":
        state_text = colour("running", "1;32", use_colour) + "   " + ui_text
    lines.append("pinpoint  10.77.0.1   " + state_text)
    for result in results:
        spec = VMS[result["key"]]
        state = result["state"]
        shown = colour(state, "1;32" if state == "running" else "1;31", use_colour)
        extra = ""
        if state == "running" and result["uptime"]:
            extra = "   " + result["uptime"] + ", load " + result["load"]
        if result.get("note"):
            extra = "   " + result["note"]
        lines.append("")
        lines.append(result["key"].ljust(9) + " " + spec["ip"] + "   " + shown + extra)
        for label, port, status in result["services"]:
            ok = status == "active"
            mark = colour("UP  ", "1;32", use_colour) if ok else colour("DOWN", "1;31", use_colour)
            lines.append("    " + label.ljust(9) + port.ljust(9) + mark)
    return "\n".join(lines)


def build_wall(args):
    use_colour = sys.stdout.isatty() and not args.no_colour
    keys = []
    for key in TARGETS:
        if vm_exists(VMS[key]["name"]):
            keys.append(key)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = []
        for key in keys:
            futures.append(pool.submit(collect_target, args.state_dir, key))
        for future in futures:
            results.append(future.result())
    pinpoint_state = vm_state(VMS["pinpoint"]["name"])
    ui_text = pinpoint_ui_status(args.ui_host_port) if pinpoint_state == "running" else ""
    return render_wall(results, pinpoint_state, ui_text, use_colour)


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
        vbox_do(True, "startvm", name, "--type", "gui" if args.gui else "headless")
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
    for an NCPA deployment right after the move. infra01 already starts on 2222.
    """
    port = args.port
    if port != 22 and not 1024 <= port <= 65535:
        fail("use 22 or a port from 1024 to 65535")
    ip = VMS[args.vm]["ip"]
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
    say("Targets: " + ", ".join(VMS[key]["ip"] + " (" + key + ")" for key in TARGETS))
    return 0


# ==========================================================
# SNAPSHOTS, RESET, DESTROY
# ==========================================================

def cmd_snapshot(args):
    """Re-take '<demo-ready>' on powered-off demo VMs (e.g. after tuning Pinpoint)."""
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


def cmd_reset(args):
    """Return every demo VM to '<demo-ready>' (clean state for the next run)."""
    apply = args.apply
    for key in demo_vm_keys():
        name = VMS[key]["name"]
        say(key + ":")
        if vm_state(name) == "running":
            vbox_do(apply, "controlvm", name, "poweroff")
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
    """Delete the demo VMs and their disks. Never touches other VMs."""
    apply = args.apply
    order = ("web01", "infra01", "pinpoint", "base")
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
    check(unit_for("web01", "http") == "nginx", "unit_for")
    check(VMS["infra01"]["service_ssh_port"] != 22, "infra01 monitored SSH is non-standard")

    decoded = base64.b64decode(post_install_command("ssh-ed25519 AAAA test").split()[1]).decode()
    check("ssh-ed25519 AAAA test" in decoded and "NOPASSWD" in decoded, "post_install_command")

    names_seen = set()
    for key in VMS:
        check(VMS[key]["name"].startswith(PREFIX + "-"), key + " name prefix")
        check(VMS[key]["ssh_port"] not in names_seen, key + " unique ssh port")
        names_seen.add(VMS[key]["ssh_port"])

    shell_ok = True
    if shutil_which("bash"):
        script = BASE_SCRIPT.replace("@LAN_CIDR@", LAN_CIDR)
        outcome = subprocess.run(["bash", "-n"], input=script, capture_output=True, text=True)
        if outcome.returncode != 0:
            shell_ok = False
            failures.append("bash -n base script: " + outcome.stderr.strip())
    check(shell_ok, "guest scripts parse")

    # The printed plan for `create` with nothing built yet: no VBoxManage call is made.
    saved = (vbox_read, vm_info, vm_exists, ensure_credentials)
    globals()["vbox_read"] = lambda *a: subprocess.CompletedProcess(a, 0, "", "")
    globals()["vm_info"] = lambda name: {}
    globals()["vm_exists"] = lambda name: False
    globals()["ensure_credentials"] = lambda state_dir, apply: None
    buffer = io.StringIO()
    try:
        plan_args = argparse.Namespace(apply=False, state_dir="/nonexistent", source_vm="Src",
                                       ui_guest_port=80, ui_host_port=DEFAULT_UI_HOST_PORT)
        with contextlib.redirect_stdout(buffer):
            cmd_create(plan_args)
    finally:
        (globals()["vbox_read"], globals()["vm_info"], globals()["vm_exists"],
         globals()["ensure_credentials"]) = saved
    plan = buffer.getvalue()
    check("--options=link" in plan and "clonevm" in plan, "create plans linked clones")
    check("--nat-pf1 delete ssh" in plan and "delete=ssh" not in plan, "create drops inherited forwards (7.2 syntax)")
    check("--nat-pf1 delete ui" in plan, "pinpoint copy drops an inherited ui forward")
    check("--intnet2=" + LAN_NAME in plan, "create attaches the lab network")
    check("--nat-pf1=ui,tcp,127.0.0.1," + str(DEFAULT_UI_HOST_PORT) in plan, "create forwards the UI")

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
    parser.add_argument("--source-vm", default=DEFAULT_SOURCE_VM, help="your installed Pinpoint VM (cloned, never changed)")
    parser.add_argument("--ui-guest-port", type=int, default=80, help="port the Pinpoint web UI listens on inside its VM")
    parser.add_argument("--ui-host-port", type=int, default=DEFAULT_UI_HOST_PORT, help="127.0.0.1 port that reaches the UI")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, handler, help_text):
        sp = sub.add_parser(name, help=help_text)
        sp.set_defaults(handler=handler)
        if name in PREVIEW_FIRST:
            sp.add_argument("--apply", action="store_true", help="really do it (default: only print the plan)")
        return sp

    add("preflight", cmd_preflight, "check this machine and the VMs (read-only)")
    add("build-base", cmd_build_base, "install and provision the base Ubuntu VM")
    add("create", cmd_create, "create web01, infra01 and the Pinpoint server copy")
    up = add("up", cmd_up, "start the lab")
    up.add_argument("--gui", action="store_true", help="open a console window per VM")
    add("down", cmd_down, "shut the lab down")
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
    snap = add("snapshot", cmd_snapshot, "re-take the clean snapshot on powered-off VMs")
    snap.add_argument("vms", nargs="*", choices=list(TARGETS) + ["pinpoint"])
    reset = add("reset", cmd_reset, "restore every VM to the clean snapshot")
    reset.add_argument("--up", action="store_true", help="start the lab afterwards")
    reset.add_argument("--gui", action="store_true")
    add("creds", cmd_creds, "print the login for the NCPA deployment wizard")
    add("destroy", cmd_destroy, "delete the demo VMs")
    add("self-test", cmd_self_test, "check the script's own logic")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not hasattr(args, "apply"):
        args.apply = True
    if not hasattr(args, "gui"):
        args.gui = False
    return args.handler(args)


if __name__ == "__main__":
    sys.exit(main())
