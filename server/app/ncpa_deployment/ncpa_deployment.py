import paramiko
from flask import current_app
from app.logging.deployment_history import *
from app.system_models import SSHCredentials, NCPADeployment, NCPADevicePartition, DeploymentMethod, AgentStatus, NetworkDiscovery
from datetime import datetime, timezone
import hashlib
import base64
import hmac 
import secrets
import shlex
import requests
import os
import re
import textwrap
from app.network_discovery.create_host_cfg import add_ncpa_port, ADD_NCPA_PORT_PROGRESS_WEIGHT
from app.network_discovery.device_identity import Evidence, is_hardware_mac, normalize_mac, record_device_evidence
from app.network_discovery.identity_probes import tls_certificate_fingerprint
from app.system_models import IdentifierKind


home = str(os.getenv("HOME"))
PUBLIC_KEY_PATH = os.path.join(home,".ssh","pinpoint_ncpa_deploy.pub")
PRIVATE_KEY_PATH = os.path.join(home,".ssh","pinpoint_ncpa_deploy")

SSH_PORT = 22
NCPA_PORT = "5693"
DEPLOYMENT_USER = "pinpoint-deployment"
SSH_TIMEOUT = 10
REMOTE_SSH_DIR = f"/home/{DEPLOYMENT_USER}/.ssh" 
REMOTE_AUTHORIZED_KEYS = f"{REMOTE_SSH_DIR}/authorized_keys"

REMOTE_HELPER = "/usr/local/sbin/pinpoint-ncpa-deploy" 
REMOTE_SUDOERS = "/etc/sudoers.d/pinpoint-ncpa-deploy"

def mark_device_incompatible(device_id):
    device = db.session.get(NetworkDiscovery, device_id)
    if device is not None:
        device.NCPA_Eligible = False
        db.session.commit()

def update_ncpa_deployment_info(device_id, ncpa_deployment_status_id, deployment_method=None, token=None, agent_status=None, error=None):
    ncpa_deployment = db.session.scalar(
        sa.select(NCPADeployment).where(
            NCPADeployment.NetworkDiscoveryID == device_id
        )
    )
                                                 
    if ncpa_deployment is None:
        return False
                                                 
    if deployment_method is not None:
        ncpa_deployment.Deployement_Method = deployment_method
    if agent_status is not None:
        ncpa_deployment.Agent_Status = agent_status
    if token is not None:
        ncpa_deployment.Token = token
    if ncpa_deployment_status_id is not None:
        ncpa_deployment.NCPADeploymentStatusID = ncpa_deployment_status_id
    if error is not None: 
        ncpa_deployment.Error = error

    db.session.commit()

def run_command(client, command, log_command=None):
    stdin, stdout, stderr = client.exec_command(command, get_pty=False)

    output = stdout.read().decode('utf-8')
    errors = stderr.read().decode('utf-8')
    exit_status = stdout.channel.recv_exit_status()

    logged_command = log_command if log_command is not None else command

    if exit_status != 0:
        current_app.logger.error(
            f"Command failed (exit {exit_status}): "
            f"{logged_command}\n"
            f"Output: {output}\n"
            f"Errors: {errors}"
        )

        return {
            "success": False,
            "message": "Privileged command failed.",
            "output": output,
            "error": errors
        }

    if errors:
        current_app.logger.warning(
            f"Command succeeded but wrote to stderr: "
            f"{logged_command}\n"
            f"Errors: {errors}"
        )

    return {
            "success": True, 
            "message": "",
            "output": output,
            "error": errors
            }

def run_sudo_command(client, command, password, log_command=None):
    stdin, stdout, stderr = client.exec_command( f"sudo -S -p '' {command}", get_pty=False)
    stdin.write(password + '\n')
    stdin.flush()

    output = stdout.read().decode('utf-8',errors="replace")
    errors = stderr.read().decode('utf-8', errors="replace")
    exit_status = stdout.channel.recv_exit_status()

    logged_command = log_command if log_command is not None else command

    if exit_status != 0:
        current_app.logger.error(
            f"Command failed (exit {exit_status}): "
            f"{logged_command}\n"
            f"Output: {output}\n"
            f"Errors: {errors}"
        )
        return {
            "success": False, 
            "message": "Privilidged command failed.",
            "output": output,
            "error": errors
            }

    if errors:
        # Non-zero-exit-only failures can still log warnings to stderr
        # (e.g. apt/gpg noise) — log for visibility, but don't treat as failure
        current_app.logger.warning(
            f"Command succeeded but wrote to stderr: "
            f"{logged_command}\n"
            f"Errors: {errors}"
        )

    return {
            "success": True, 
            "message": "",
            "output": output,
            "error": errors
            }

def get_host_key_fingerprint(ip_address):
    transport = None
    try:
        transport = paramiko.Transport((ip_address, SSH_PORT))
        transport.start_client(timeout=SSH_TIMEOUT)
        key = transport.get_remote_server_key()

        raw_key_bytes = key.asbytes()
        sha256_digest = hashlib.sha256(raw_key_bytes).digest()
        fingerprint = base64.b64encode(sha256_digest).decode('utf-8').rstrip('=')

        return f"{fingerprint}"
    except paramiko.SSHException as e:
        current_app.logger.exception("Cannot reach host")
        return None
    except Exception as e:
        current_app.logger.exception("An unexpected error occured.")
        return None
    finally:
        if transport is not None:
            transport.close()

def query_key_fingerprint(device_id):

    try :
        creds = db.session.scalar(
            sa.select(SSHCredentials.Key_Fingerprint).where(SSHCredentials.NetworkDiscoveryID == device_id)
        )
    except Exception as e:
        current_app.logger.exception(f"Device {device_id} does not exist.")
        creds = None

    return creds

def verify_host_fingerprint(ip_address, expected_fingerprint): 
    """ 
    Verify that the live SSH host key matches the trusted fingerprint. 
    """ 
    if not expected_fingerprint: 
        current_app.logger.error("No trusted host fingerprint exists.")
        return False
    
    actual_fingerprint = get_host_key_fingerprint(ip_address)

    if actual_fingerprint is None:
        current_app.logger.error(f"Cannot reach host {ip_address}.")
        return False

    if not hmac.compare_digest( actual_fingerprint, expected_fingerprint): 
        current_app.logger.error(f"SSH host-key mismatch for {ip_address}.")
        return False

    return True

def connect_with_fingerprint_check( 
        ip_address, 
        username, 
        expected_fingerprint, 
        password=None,
        private_key=None,
    ): 

    result = verify_host_fingerprint( 
        ip_address,
        expected_fingerprint
    ) 

    if not result:
        return None
    
    client = paramiko.SSHClient() 

    client.set_missing_host_key_policy( paramiko.RejectPolicy() ) 
    
    transport = paramiko.Transport( 
        (ip_address, SSH_PORT) 
    ) 

    try: 
        transport.start_client(timeout=SSH_TIMEOUT) 
        host_key = transport.get_remote_server_key() 
        client.get_host_keys().add( 
            ip_address, host_key.get_name(), 
            host_key
            )
    except paramiko.SSHException as e:
        current_app.logger.exception(f"Failed to retreieve key from {ip_address}.")
        return None
    except Exception as e:
        current_app.logger.error(f"An unexpected error occured.")
        return None
    finally: 
        transport.close() 

    client.connect( 
            hostname=ip_address, 
            port=SSH_PORT, 
            username=username, 
            password=password,
            key_filename=private_key,
            timeout=SSH_TIMEOUT, 
            allow_agent=False, 
            look_for_keys=False
    ) 

    return client

def check_debian_based(client): 
    """ 
    Determine whether the remote machine is Debian/Ubuntu based.
    """ 
    result = run_command( client, "cat /etc/os-release" ) 
    if not result["success"]: return False, "unknown" 
    os_release = result["output"] 

    is_debian_based = any( 
        line in os_release for line in 
        (
             "ID=ubuntu", 
             'ID="ubuntu"', 
             "ID=debian", 
             'ID="debian"', 
             "ID_LIKE=debian", 
             'ID_LIKE="debian"', ) 
    ) 

    return is_debian_based, os_release

def ensure_deployment_user(client, password): 
    
    result = run_command( client, f"id {DEPLOYMENT_USER}", ) 

    if result["success"]: 
        return True 

    result = run_sudo_command( client, f"/usr/sbin/useradd -m {DEPLOYMENT_USER}", password, ) 

    return result["success"]

def install_deployment_key(client, password): 
    try: 
        with open(PUBLIC_KEY_PATH, "r", encoding="utf-8") as file: 
            public_key = file.read().strip() 

    except OSError: 
        current_app.logger.exception("Unable to read deployment public key.") 
        return False 

    if not public_key: 
        return False 
    
    if "\n" in public_key or "\r" in public_key: 
        current_app.logger.error( "Deployment public key contains unexpected newlines.") 
        return False 

    result = run_sudo_command( client, f"/usr/bin/mkdir -p {REMOTE_SSH_DIR}", password) 

    if not result["success"]: 
        return False 

    check_key_command = ( f"/usr/bin/grep -Fqx -- " f"'{public_key}' " f"{REMOTE_AUTHORIZED_KEYS}" ) 
    result = run_sudo_command( client, check_key_command, password ) 
    
    if not result["success"]:


        quoted_public_key = public_key.replace("'", "'\\''")
        quoted_authorized_keys = REMOTE_AUTHORIZED_KEYS.replace("'", "'\\''")
        add_key_command = (
            f"/bin/sh -c "
            f"'printf \"%s\\n\" \"{quoted_public_key}\" "
            f">> {quoted_authorized_keys}'"
        )
    
        result = run_sudo_command( client, add_key_command, password) 
        if not result["success"]: 
            return False 

    commands = [ 
        f"/usr/bin/chmod 700 {REMOTE_SSH_DIR}", 
        f"/usr/bin/chmod 600 {REMOTE_AUTHORIZED_KEYS}", 
        (f"/usr/bin/chown -R " f"{DEPLOYMENT_USER}:{DEPLOYMENT_USER} " 
         f"{REMOTE_SSH_DIR}"), 
        ] 
    
    for command in commands: 
        result = run_sudo_command( client, command, password) 
        if not result["success"]: 
            return False 

    return True

def install_restricted_sudo(client, password): 

    sudoers_content = ( f"{DEPLOYMENT_USER} ALL=(root) " f"NOPASSWD: {REMOTE_HELPER}\n" ) 

    script = (
        f"printf '%s' {shlex.quote(sudoers_content)} > {shlex.quote(REMOTE_SUDOERS)}"
        f" && /usr/bin/chmod 440 {shlex.quote(REMOTE_SUDOERS)}"
        f" && /usr/sbin/visudo -cf {shlex.quote(REMOTE_SUDOERS)}"
    )

    command = f"/bin/sh -c {shlex.quote(script)}"
    
    result = run_sudo_command(client, command, password) 

    return result["success"]

def install_deployment_helper(client, password):


    helper_path = "/usr/local/sbin/pinpoint-ncpa-deploy"
    temp_path = f"/tmp/.pinpoint-ncpa-deploy-{secrets.token_hex(16)}"

    
    helper_content = textwrap.dedent('''
    #!/bin/bash
    set -euo pipefail

    TOKEN="${1:-}"

    if [[ ! "$TOKEN" =~ ^[a-f0-9]{32}$ ]]; then
        echo "Invalid token." >&2
        exit 1
    fi

    APT="/usr/bin/apt-get"
    MKDIR="/usr/bin/mkdir"
    GPG="/usr/bin/gpg"
    TEE="/usr/bin/tee"
    SED="/usr/bin/sed"
    UFW="/usr/sbin/ufw"
    NCPA_INIT="/etc/init.d/ncpa"
    CURL="/usr/bin/curl"

    KEYRING_DIR="/etc/apt/keyrings"
    GPG_KEY="/etc/apt/keyrings/GPG-KEY-NAGIOS-V3.gpg"
    NCPA_SOURCE="/etc/apt/sources.list.d/nagios.sources"
    NCPA_CONFIG="/usr/local/ncpa/etc/ncpa.cfg"

    NCPA_PORT="5693"

    "$APT" update

    "$MKDIR" -m 0755 -p "$KEYRING_DIR"

    "$CURL" -fsSL https://repo.nagios.com/GPG-KEY-NAGIOS-V3 | "$GPG" --batch --yes --dearmor -o "$GPG_KEY"

    . /etc/os-release
    CODENAME="${VERSION_CODENAME:-}"

    if [ -z "$CODENAME" ]; then
        echo "Unable to determine OS codename." >&2
        exit 1
    fi

    "$TEE" "$NCPA_SOURCE" > /dev/null <<EOF
    Types: deb
    URIs: https://repo.nagios.com/deb/$CODENAME
    Suites: /
    Signed-By: $GPG_KEY
    EOF

    "$APT" update

    DEBIAN_FRONTEND=noninteractive "$APT" install -y ncpa

    "$SED" -i "s/^community_string = .*/community_string = $TOKEN/" "$NCPA_CONFIG"

    # Use a persistent self-signed certificate instead of NCPA's "adhoc" one,
    # which may be regenerated on restart. PinPoint identifies the device by
    # this certificate's fingerprint after its IP changes, so it must survive
    # restarts. Created once and reused on redeploys.
    OPENSSL="/usr/bin/openssl"
    CERT_FILE="/usr/local/ncpa/etc/pinpoint-ncpa.crt"
    KEY_FILE="/usr/local/ncpa/etc/pinpoint-ncpa.key"

    if [ ! -s "$CERT_FILE" ] || [ ! -s "$KEY_FILE" ]; then
        "$OPENSSL" req -x509 -newkey rsa:2048 -nodes -days 3650 \
            -subj "/CN=$(/usr/bin/hostname)" -keyout "$KEY_FILE" -out "$CERT_FILE"
    fi

    # NCPA drops privileges to the nagios user, so the key must be readable by
    # that group. Applied on every deploy so redeploys repair existing guests.
    /usr/bin/chown root:nagios "$KEY_FILE"
    /usr/bin/chmod 640 "$KEY_FILE"
    /usr/bin/chown root:root "$CERT_FILE"
    /usr/bin/chmod 644 "$CERT_FILE"

    if ! /usr/sbin/runuser -u nagios -- /usr/bin/test -r "$KEY_FILE"; then
        echo "NCPA TLS key is not readable by the nagios user." >&2
        exit 1
    fi

    "$SED" -i "s|^certificate = .*|certificate = $CERT_FILE,$KEY_FILE|" "$NCPA_CONFIG"

    "$NCPA_INIT" stop || true
    sleep 1
    "$NCPA_INIT" start

    # "init status" can report running while the listener is down, so probe
    # the port and make an authenticated HTTPS request, retrying briefly.
    NCPA_OK=0
    for attempt in 1 2 3 4 5 6 7 8 9 10; do
        sleep 2
        if /usr/bin/ss -ltn | grep -q ":$NCPA_PORT " && \
            "$CURL" -ksf --max-time 5 -o /dev/null \
                "https://127.0.0.1:$NCPA_PORT/api/?token=$TOKEN&check=cpu/percent"; then
            NCPA_OK=1
            break
        fi
    done

    if [ "$NCPA_OK" -ne 1 ]; then
        echo "NCPA is not listening or rejected an authenticated request on port $NCPA_PORT." >&2
        "$NCPA_INIT" status >&2 || true
        exit 1
    fi

    # Identity evidence for PinPoint's device reconciler: the machine-id, the
    # hardware MACs of physical interfaces (no loopback, bridges or virtual
    # devices) and the hostname. Only identifiers are printed, never the token.
    echo "IDENTITY_BEGIN"
    echo "machine_id=$(/usr/bin/cat /etc/machine-id 2>/dev/null || true)"
    for iface in /sys/class/net/*; do
        name="$(/usr/bin/basename "$iface")"
        if [ -e "$iface/device" ] && [ ! -d "$iface/bridge" ] && [ "$name" != "lo" ]; then
            echo "mac=$(/usr/bin/cat "$iface/address")"
        fi
    done
    echo "hostname=$(/usr/bin/hostname)"
    echo "IDENTITY_END"
    ''').lstrip('\n')

    try:

        result = run_sudo_command(
            client,
            "/usr/bin/mkdir -p /usr/local/sbin",
            password
        )

        if not result["success"]:
            return False

        sftp = client.open_sftp()

        try:
            with sftp.file(temp_path, "w") as remote_file:
                remote_file.write(helper_content)

        finally:
            sftp.close()

        result = run_sudo_command(
            client,
            f"/bin/mv {temp_path} {helper_path}",
            password
        )

        if not result["success"]:
            return False

        result = run_sudo_command(
            client,
            f"/bin/chown root:root {helper_path}",
            password
        )

        if not result["success"]:
            return False

        result = run_sudo_command(
            client,
            f"/bin/chmod 755 {helper_path}",
            password
        )

        if not result["success"]:
            return False

        result = run_sudo_command(
            client,
            (
                f"/usr/bin/test -f {helper_path} && "
                f"/usr/bin/test -x {helper_path} && "
                f"/usr/bin/stat -c '%U:%G %a' {helper_path}"
            ),
            password
        )

        if not result["success"]:
            return False

        return True

    except Exception as e:
        current_app.logger.exception(
            f"Failed to install NCPA deployment helper: {e}"
        )
        return False

    finally:
        # The temporary file should not remain if installation failed.
        try:
            cleanup = (
                f"/bin/rm -f {temp_path}"
            )
            run_sudo_command(client, cleanup, password)
        except Exception:
            current_app.logger.exception("Installation failed.")
            pass


def give_program_permissions( device_id, ncpa_deployment_status_id, ip_address, username, password ): 
    """ 
    Bootstrap the remote machine for NCPA deployment. 
    Security properties: 
    - verifies the stored SSH host key before authentication 
    - checks OS compatibility before deployment 
    - creates a dedicated deployment account 
    - installs a dedicated SSH key 
    - avoids unrestricted sudo permissions 
    - does not store the user's password 
    - does not log credentials 
    - operations are idempotent
    """ 
    client = None 
    try: 
        fingerprint = query_key_fingerprint(device_id) 
        if not fingerprint: 
            update_ncpa_deployment_info( device_id, ncpa_deployment_status_id, agent_status=AgentStatus.FAILED, error="Device has not been trust-confirmed." ) 
            return False 

        client = connect_with_fingerprint_check( ip_address, username, fingerprint, password=password, )

        if client is None:
            update_ncpa_deployment_info( device_id, ncpa_deployment_status_id, agent_status=AgentStatus.FAILED, error="Cannot reach host.") 
            return False
        
        is_compatible, os_info = check_debian_based(client)
        if not is_compatible: 
            mark_device_incompatible(device_id) 
            update_ncpa_deployment_info( device_id, ncpa_deployment_status_id, agent_status=AgentStatus.INCOMPATIBLE, error=f"Unsupported distro {os_info}." ) 
            return False 

        if not ensure_deployment_user(client, password): 
            update_ncpa_deployment_info( device_id, ncpa_deployment_status_id, agent_status=AgentStatus.FAILED, error="Unable to create deployment account.") 
            return False 

        if not install_deployment_helper(client, password): 
            update_ncpa_deployment_info( device_id, ncpa_deployment_status_id, agent_status=AgentStatus.FAILED, error="Unable to create deployment script.") 
            return False 

        if not install_deployment_key(client, password): 
            update_ncpa_deployment_info( device_id, ncpa_deployment_status_id, agent_status=AgentStatus.FAILED, error="Unable to install deployment SSH key.") 
            return False 

        if not install_restricted_sudo(client, password): 
            update_ncpa_deployment_info( device_id, ncpa_deployment_status_id, agent_status=AgentStatus.FAILED, error="Unable to configure restricted privileges.") 
            return False 

        ssh_credentials = db.session.scalar(
            sa.select(SSHCredentials)
            .where( 
                SSHCredentials.NetworkDiscoveryID == device_id 
            ) 
        ) 

        if ssh_credentials is None: 
            update_ncpa_deployment_info(device_id, ncpa_deployment_status_id, agent_status=AgentStatus.FAILED, error="SSH credential record not found.") 
            return False 

        ssh_credentials.Key_Installed = True 
        db.session.commit() 
        update_ncpa_deployment_info(device_id, ncpa_deployment_status_id, agent_status=AgentStatus.PENDING_NCPA) 
        return True 
    
    except paramiko.AuthenticationException: 
        current_app.logger.warning(f"SSH authentication failed for device {device_id}.") 
        update_ncpa_deployment_info( device_id, ncpa_deployment_status_id, agent_status=AgentStatus.FAILED, error="SSH authentication failed.") 
        return False 
    
    except paramiko.SSHException: 
        current_app.logger.exception(f"SSH error while preparing device {device_id}.") 
        update_ncpa_deployment_info( device_id, ncpa_deployment_status_id, agent_status=AgentStatus.FAILED, error="SSH connection error." ) 
        return False 
    
    except Exception: 
        db.session.rollback() 
        update_ncpa_deployment_info( device_id, ncpa_deployment_status_id, agent_status=AgentStatus.FAILED, error="An unexpected error occurred.") 
        current_app.logger.exception(f"Unexpected error while preparing device {device_id}.") 
        return False 
    
    finally: 
        password = None 
        if client is not None: 
            try: client.close() 
            except Exception: pass

def verify_ncpa_reachable(ip_address, token, timeout=5):
    """
    Verify that the Pinpoint server can reach NCPA and
    that NCPA accepts the generated authentication token.
    """

    url = f"https://{ip_address}:{NCPA_PORT}/api"

    try:
        response = requests.get(
            url,
            params={
                "token": token,
                "check": "cpu/percent"
            },
            verify=False,
            timeout=timeout
        )

        if response.status_code == 200:
            return {
                "success": True,
                "message": "NCPA is reachable and responding."
            }

        return {
            "success": False,
            "message": (
                f"NCPA responded with HTTP "
                f"{response.status_code}."
            )
        }

    except requests.exceptions.ConnectTimeout:
        return {
            "success": False,
            "message": "Connection to NCPA timed out."
        }

    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "message": f"Unable to connect to NCPA on port {NCPA_PORT}."
        }

    except requests.RequestException as e:
        current_app.logger.warning(
            "NCPA reachability check failed for %s: %s",
            ip_address,
            e
        )

        return {
            "success": False,
            "message": "NCPA reachability check failed."
        }

# Filesystem types and node names that never carry a monitorable disk.
PSEUDO_FILESYSTEMS = frozenset({
    "tmpfs", "devtmpfs", "squashfs", "overlay", "proc", "sysfs", "cgroup",
    "cgroup2", "devpts", "efivarfs", "ramfs", "swap", "iso9660",
})
DISK_PERCENT_LEAF = "percent"


def _ncpa_get(ip_address, token, path, timeout=5):
    """GET an NCPA API node (e.g. "disk/logical"); the decoded JSON, or None."""
    try:
        response = requests.get(
            f"https://{ip_address}:{NCPA_PORT}/api/{path}",
            params={"token": token},
            verify=False,
            timeout=timeout,
        )
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _is_monitorable_disk_node(name, info):
    """Mounted, real filesystems only; no swap, boot-only or pseudo nodes."""
    if not name or any(char in name for char in ("!", ";", "'", '"', " ", "\n")):
        return False
    if isinstance(info, dict):
        fstype = info.get("fstype")
        if isinstance(fstype, list):
            fstype = fstype[0] if fstype else None
        if isinstance(fstype, str) and fstype.lower() in PSEUDO_FILESYSTEMS:
            return False
    return True


def discover_disk_nodes(ip_address, token):
    """
    Ask the agent itself which logical disk nodes it serves (GET
    /api/disk/logical) and keep those that are real filesystems and whose
    percent node answers. NCPA names nodes after mount points (with "|" for
    "/"), not after lsblk partitions, so this is the only reliable source.
    Returns the node names in the agent's order.
    """
    listing = _ncpa_get(ip_address, token, "disk/logical")
    nodes = listing.get("logical") if isinstance(listing, dict) else None
    if not isinstance(nodes, dict):
        return []

    names = []
    for name, info in nodes.items():
        if not _is_monitorable_disk_node(name, info):
            continue
        if _ncpa_get(ip_address, token, f"disk/logical/{name}/{DISK_PERCENT_LEAF}") is None:
            current_app.logger.info("NCPA disk node %r has no %s value; skipped.", name, DISK_PERCENT_LEAF)
            continue
        names.append(name)
    return names


def refresh_ncpa_partitions(ncpa_deployment, ip_address):
    """
    Re-read the agent's logical disks and replace the stored
    NCPADevicePartition rows (whose Name is the NCPA node name). Used after
    install and whenever disks change. Commits. Returns the stored names.
    """
    names = discover_disk_nodes(ip_address, ncpa_deployment.Token)
    db.session.execute(
        sa.delete(NCPADevicePartition).where(
            NCPADevicePartition.NCPADeployID == ncpa_deployment.NCPADeployID
        )
    )
    for name in names:
        db.session.add(NCPADevicePartition(Name=name, NCPADeployID=ncpa_deployment.NCPADeployID))
    db.session.commit()
    return names


def _parse_identity(stdout_text: str) -> dict:
    """
    Extract the identity block the helper script prints:

        IDENTITY_BEGIN
        machine_id=<id>
        mac=aa:bb:cc:dd:ee:ff
        hostname=<name>
        IDENTITY_END

    Returns {"machine_id": str | None, "macs": [str], "hostname": str | None}.
    Only hardware (universally administered) MACs are kept, valid MACs are
    normalized, and text outside the sentinels is ignored.
    """
    identity = {"machine_id": None, "macs": [], "hostname": None}
    inside = False
    for raw_line in stdout_text.splitlines():
        line = raw_line.strip()
        if line == "IDENTITY_BEGIN":
            inside = True
            continue
        if line == "IDENTITY_END":
            break
        if not inside or "=" not in line:
            continue

        key, value = line.split("=", 1)
        value = value.strip()
        if key == "machine_id" and re.fullmatch(r"[0-9a-f]{32}", value):
            identity["machine_id"] = value
        elif key == "mac" and is_hardware_mac(value):
            mac = normalize_mac(value)
            if mac not in identity["macs"]:
                identity["macs"].append(mac)
        elif key == "hostname" and value:
            identity["hostname"] = value
    return identity


def store_deployment_identity(device_id, identity, cert_fingerprint):
    """
    Save what the deployment learned about a device as identifiers: its
    machine-id, hardware MACs and the NCPA certificate fingerprint. These let
    the device be recognised after a DHCP lease change. Evidence another
    device already owns raises a review item instead of being moved.
    Commits. Returns the list of evidence that could not be attached.
    """
    device = db.session.get(NetworkDiscovery, device_id)
    if device is None:
        return []

    evidence = []
    if identity.get("machine_id"):
        evidence.append(Evidence(IdentifierKind.MACHINE_ID, identity["machine_id"]))
    for mac in identity.get("macs", []):
        evidence.append(Evidence(IdentifierKind.MAC, mac))
    if cert_fingerprint:
        evidence.append(Evidence(IdentifierKind.NCPA_CERT, cert_fingerprint))

    rejected = record_device_evidence(device, evidence)
    db.session.commit()
    return rejected


def install_ncpa(device_id, ncpa_deployment_status_id, ip_address):

    client = None

    try:
        fingerprint = query_key_fingerprint(device_id)

        if fingerprint is None:
            update_ncpa_deployment_info(
                device_id,
                ncpa_deployment_status_id,
                agent_status=AgentStatus.FAILED,
                error="Device has not been trust-confirmed."
            )
            return False

        client = connect_with_fingerprint_check(
            ip_address,
            DEPLOYMENT_USER,
            fingerprint,
            private_key=PRIVATE_KEY_PATH
        )

        if client is None:
            update_ncpa_deployment_info(
                device_id,
                ncpa_deployment_status_id,
                agent_status=AgentStatus.FAILED,
                error="ACannot connect to device."
            )
            return None

        # A redeploy to the same device reuses its token rather than minting
        # a new one, so nothing already configured against it breaks.
        existing_deployment = db.session.scalar(
            sa.select(NCPADeployment).where(
                NCPADeployment.NetworkDiscoveryID == device_id,
                NCPADeployment.Token.is_not(None),
            )
        )
        token = existing_deployment.Token if existing_deployment is not None else secrets.token_hex(16)

        result = run_command(
            client,
            f"sudo -n {REMOTE_HELPER} {shlex.quote(token)}",
            log_command=f"sudo -n {REMOTE_HELPER} <token>"
        )

        if not result["success"]:
            update_ncpa_deployment_info(
                device_id,
                ncpa_deployment_status_id,
                agent_status=AgentStatus.FAILED,
                error=result["message"]
            )
            return False

        reachability = verify_ncpa_reachable(
            ip_address,
            token
        )

        if not reachability["success"]:
            update_ncpa_deployment_info(
                device_id,
                ncpa_deployment_status_id,
                agent_status=AgentStatus.FAILED,
                error=reachability["message"]
            )
            return False

        ncpa_deployment = db.session.scalar(
            sa.select(NCPADeployment).where(
                NCPADeployment.NetworkDiscoveryID == device_id
            )
        )

        if ncpa_deployment is None:
            update_ncpa_deployment_info(
                device_id,
                ncpa_deployment_status_id,
                agent_status=AgentStatus.FAILED,
                error="NCPA deployment record not found."
            )
            return False

        ncpa_deployment.Deployement_Method = DeploymentMethod.AUTOMATIC
        ncpa_deployment.Agent_Status = AgentStatus.DEPLOYED
        ncpa_deployment.Token = token
        ncpa_deployment.Error = None
        ncpa_deployment.NCPADeploymentStatusID = (
            ncpa_deployment_status_id
        )

        stdout_text = result.get("output", "")
        db.session.commit()

        # Disk nodes come from the agent's own API, not from lsblk. Best
        # effort: without them the config falls back to the aggregate path.
        try:
            refresh_ncpa_partitions(ncpa_deployment, ip_address)
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Could not read NCPA disk nodes after deployment.")

        # Identity evidence is best effort: the agent is already deployed, so
        # a failure here must not mark the deployment as failed.
        try:
            identity = _parse_identity(stdout_text)
            cert_fingerprint = tls_certificate_fingerprint(ip_address, NCPA_PORT)
            store_deployment_identity(device_id, identity, cert_fingerprint)
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Could not store identity evidence after NCPA deployment.")

        return True

    except paramiko.SSHException:
        db.session.rollback()
        current_app.logger.exception(
            "SSH error during NCPA installation."
        )
        update_ncpa_deployment_info(
            device_id,
            ncpa_deployment_status_id,
            agent_status=AgentStatus.FAILED,
            error="An error occurred while connecting to the device."
        )
        return False

    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "NCPA installation failed."
        )
        update_ncpa_deployment_info(
            device_id,
            ncpa_deployment_status_id,
            agent_status=AgentStatus.FAILED,
            error="An unexpected error occurred."
        )
        return False

    finally:
        if client is not None:
            client.close()


def install_process(app, user_id, device_list, stop_event):
    '''
        device_credentials: list of dicts like
        [
            {
            "device_id": 1, 
            "ip_address": "192.168.130.10",
            "username": "admin",
            "password": "password123"
            }, ...
        ]
    '''
    with app.app_context():

        ncpa_deployment_status = create_ncpa_deployment_status(user_id)

        if ncpa_deployment_status is None:
            return None
        
        ncpa_deployment_status_id = ncpa_deployment_status.NCPADeployStatusID
        processed_devices = 0
        progress = 0
        failed_deployment = []
        successful_deployment = []
        try: 
            total_devices = len(device_list)
            for entry in device_list:
                device_id = entry["device_id"]
                ip_address = entry["ip_address"]
                username = entry["username"]
                password = entry["password"]

                if stop_event.is_set():
                    update_ncpa_deployment_status(
                        ncpa_deployment_status_id,
                        DeploymentStatus.INTERRUPTED,
                        progress,
                        "NCPA deployment stopped by user."
                    )
                    return

                key_installed = give_program_permissions(device_id, ncpa_deployment_status_id, ip_address, username, password)
                if key_installed:
                    installed_ncpa = install_ncpa(device_id, ncpa_deployment_status_id, ip_address)

                    if not installed_ncpa:
                        app.logger.error(f"Cannot install ncpa in device {device_id}, {ip_address}.")
                        failed_deployment.append(device_id)
                    else:
                        successful_deployment.append(device_id)

                else:
                    app.logger.error(f"Cannot install key in device {device_id}, {ip_address}.")
                    failed_deployment.append(device_id)

                processed_devices += 1

                progress = calculate_progress(processed_devices, total_devices, 0, ADD_NCPA_PORT_PROGRESS_WEIGHT[0])
                update_ncpa_deployment_status(
                    ncpa_deployment_status_id,
                    DeploymentStatus.RUNNING,
                    progress,
                    "Deploying NCPA."
                )

            if successful_deployment:
                add_ncpa_port(app, successful_deployment, ncpa_deployment_status_id, stop_event)
                        
            if not failed_deployment:
                update_ncpa_deployment_status(
                    ncpa_deployment_status_id, DeploymentStatus.SUCCESS, 100,
                    "Successfully deployed NCPA to all devices.",
                    datetime.now(timezone.utc)
                )
            else:
                update_ncpa_deployment_status(
                    ncpa_deployment_status_id, DeploymentStatus.PARTIAL_FAILURE, 100,
                    f"Deployment completed with {len(failed_deployment)} failure(s).",
                    datetime.now(timezone.utc),
                    error=str(failed_deployment)
                )

            

        except Exception as e:
            app.logger.exception(f"NCPA Deployment failed")

            if ncpa_deployment_status_id is not None:
                update_ncpa_deployment_status(
                    ncpa_deployment_status_id,
                    DeploymentStatus.FAILED,
                    100,
                    "NCPA Deploymnet failed",
                    datetime.now(timezone.utc),
                    str(e)
                )