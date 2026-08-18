import paramiko
from flask import current_app

PUBLIC_KEY_PATH = "/home/paeng/.ssh/pinpoint_ncpa_deploy.pub"
PRIVATE_KEY_PATH = "/home/paeng/.ssh/pinpoint_ncpa_deploy"
SSH_PORT = 22
DEPLOYMENT_USER = "pinpoint-deployment"
TOKEN = "publictest"
NCPA_PORT = "5693"

def run_command(client, command):
    stdin, stdout, stderr = client.exec_command(command, get_pty=True)

    output = stdout.read().decode('utf-8')
    errors = stderr.read().decode('utf-8')

    if stdout.recv_exit_status() != 0 or errors:
        current_app.logger.exception(
            f"Command failed: {command}\n Output: {output}\n Errors: {errors}")
        return {"success": False, "message": "An error occured. Please try again."}
    return {"success": True, "message": ""}

def run_sudo_command(client, command, password):
    stdin, stdout, stderr = client.exec_command(command, get_pty=True)
    stdin.write(password + '\n')
    stdin.flush()

    output = stdout.read().decode('utf-8')
    errors = stderr.read().decode('utf-8')

    if stdout.recv_exit_status() != 0 or errors:
        current_app.logger.exception(
            f"Command failed: {command}\n Output: {output}\n Errors: {errors}")
        return {"success": False, "message": "An error occured. Please try again."}
    return {"success": True, "message": ""}


def give_program_permissions(ip_address, username, password):
    # check if the device already has a host key in the db
    # if not, confirm if the device is correct
    # set pramiko's key policy to reject if its not part of the host keys the server
    # load the host keys /
    # connect to the client /
    # make a user for ncpa installer /
    # install our public key /
    # make give a scoped passwordless sudo for sepcific functions /
    # add the password to apply the commands /
    # discard password /

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            ip_address,
            SSH_PORT,
            username,
            password
        )

        check_user = f'id {DEPLOYMENT_USER}'
        stdin, stdout, stderr = client.exec_command(check_user)

        if stdout.channel.recv_exit_status() != 0:
            add_user = f'sudo -S useradd -m {DEPLOYMENT_USER}'
            run_sudo_command(client, add_user, password)

        with open(PUBLIC_KEY_PATH) as f:
            public_key = f.read().strip()

        if not public_key:
            return {"success": False, "message": "Failed to load private key."}

        make_dir = f'sudo -S mkdir -p ~{DEPLOYMENT_USER}/.ssh'
        result = run_sudo_command(client, make_dir, password)
        if not result['success']:
            return result

        add_key = f"sudo -S bash -c 'echo \"{public_key}\" >> ~{DEPLOYMENT_USER}/.ssh/authorized_keys'"
        result = run_sudo_command(client, add_key, password)
        if not result['success']:
            return result

        add_folder_permission = f'sudo -S chmod 700 ~{DEPLOYMENT_USER}/.ssh'
        result = run_sudo_command(client, add_folder_permission, password)
        if not result['success']:
            return result

        add_key_permission = f'sudo -S chmod 600 ~{DEPLOYMENT_USER}/.ssh/authorized_keys'
        result = run_sudo_command(client, add_key_permission, password)
        if not result['success']:
            return result

        change_folder_ownership = f'sudo -S chown -R {DEPLOYMENT_USER}:{DEPLOYMENT_USER} ~{DEPLOYMENT_USER}/.ssh'
        result = run_sudo_command(client, change_folder_ownership, password)
        if not result["success"]:
            return result

        sudoers_rule = (
            f"{DEPLOYMENT_USER} ALL=(root) NOPASSWD: "
            f"/usr/bin/apt-get, "
            f"/usr/bin/mkdir, "
            f"/usr/bin/gpg, "
            f"/usr/bin/tee, "
            f"/usr/bin/sed, "
            f"/etc/init.d/ncpa, "
            f"/usr/sbin/ufw"
        )
        sudo_setup_cmd = (
            f"sudo -S bash -c"
            f" 'echo \"{sudoers_rule}\" | sudo -S tee -a /etc/sudoers.d/pinpoint-ncpa-deploy && "
            f"chmod 440 /etc/sudoers.d/pinpoint-ncpa-deploy && "
            f"visudo -cf /etc/sudoers.d/pinpoint-ncpa-deploy'"
        )
        result = run_sudo_command(client, sudo_setup_cmd, password)
        if not result['success']:
            return result

    except paramiko.SSHException as e:
        current_app.logger.error(f'SSH Error: {e}')
        return {"success": False, "message": "An Error occured. Please try again."}
    except Exception as e:
        current_app.logger.error(f"Error {e}")
        return {"success": False, "message": "An Error occured. Please try again."}
    finally:
        client.close()

    return {"success": True, "message": "User successfully added."}

def install_ncpa(ip_address):
    # start SSH connection to the client
    # auto add the key
    # connect to the client by asking the user the username and password

    # check the distro of the machine
    # run the install commands

    # configure the ncpa config
    # generate a secret token
    # add the secret token to the device config
    # restart ncpa
    # insert into the database the secret token and other information
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(
            hostname=ip_address,
            port=SSH_PORT,
            username=DEPLOYMENT_USER,
            key_filename=PRIVATE_KEY_PATH
        )

        apt_update = "sudo apt-get update"
        result = run_command(client, apt_update)
        if not result['success']:
            return result

        install_apt_transport = "sudo apt-get install apt-transport-https"
        result = run_command(client, install_apt_transport)
        if not result['success']:
            return result

        make_keyring = "sudo mkdir -m 0755 -p /etc/apt/keyrings/"
        result = run_command(client, make_keyring)
        if not result['success']:
            return result

        get_gpg_key = (
            "curl -fsSL https://repo.nagios.com/GPG-KEY-NAGIOS-V3 | "
            "sudo -n gpg --dearmor -o /etc/apt/keyrings/GPG-KEY-NAGIOS-V3.gpg")
        result = run_command(client, get_gpg_key)
        if not result['success']:
            return result

        source_content = (
            'Types: deb\n'
            'URIs: https://repo.nagios.com/deb/$(lsb_release -cs)\n'
            'Suites: /\n'
            'Signed-By: /etc/apt/keyrings/GPG-KEY-NAGIOS-V3.gpg'
        )
        add_source = f'echo "{source_content}" | sudo -n tee /etc/apt/sources.list.d/nagios.sources > /dev/null'
        result = run_command(client, add_source)
        if not result['success']:
            return result

        apt_update = "sudo apt-get update"
        result = run_command(client, apt_update)
        if not result['success']:
            return result

        install_ncpa = "sudo -n apt-get install ncpa"
        result = run_command(client, install_ncpa)
        if not result['success']:
            return result

        configure_token = f"sudo -n sed -i 's/^community_string = .*/community_string = {TOKEN}/' /usr/local/ncpa/etc/ncpa.cfg"
        result = run_command(client, configure_token)
        if not result['success']:
            return result


        restart_ncpa = "sudo -n /etc/init.d/ncpa restart"
        result = run_command(client, configure_token)
        if not result['success']:
            return result

        add_ufw_rule = f"sudo -n ufw allow {NCPA_PORT}/tcp"
        result = run_command(client, configure_token)
        if not result['success']:
            return result

    except paramiko.SSHException as e:
        print(f'SSH Error: {e}')
        raise
    except Exception as e:
        print(f"Error {e}")
        raise
    finally:
        client.close()

    return {"success": True, "message": "NCPA successfully Deployed."}


# result = give_program_permissions(ip_address="192.168.130.9",username="paeng",password="password")
give_program_permissions("192.168.130.9","paeng","password")
result = install_ncpa("192.168.130.9")
print(result)