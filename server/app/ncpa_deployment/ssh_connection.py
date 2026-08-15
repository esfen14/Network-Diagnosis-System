import paramiko

PUBLIC_KEY_PATH = "/home/paeng/.ssh/pinpoint_ncpa_deploy.pub"
PRIVATE_KEY_PATH = "/home/paeng/.ssh/pinpoint_ncpa_deploy"
SSH_PORT = 22
DEPLOYMENT_USER = "pinpoint-deployment"
TOKEN = "publictest"
NCPA_PORT = "5693"

def ssh_connect(ip_address, username, password):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            ip_address,
            SSH_PORT, 
            username, 
            password,
            timeout=10
        )
        # commands = ['touch sample-file','ls -la','','sudo -S apt update']
        # for command in commands:
        #    stdin, stdout, stderr = client.exec_command(command)
        #    stdin.write(password + '\n')
        #    print(f'Output of {command}:\n{stdout.read().decode('utf-8')}')
        #    print(f'Error output {command}: \n{stderr.read().decode('utf-8')}')
        #    exit_status = stdout.channel.recv_exit_status()
        #    print(exit_status)

        check_user = f'id {DEPLOYMENT_USER}'
        stdin, stdout, stderr = client.exec_command(check_user)

        if stdout.channel.recv_exit_status() == 0:
            return {"success": False, "message": "Deployment user already exists."}

        add_user = f'sudo -S useradd -m {DEPLOYMENT_USER}'
        stdin, stdout, stderr = client.exec_command(add_user, get_pty=True)
        stdin.write(password + '\n')
        stdin.flush()

        if stdout.channel.recv_exit_status() != 0:
            return {"success": False, "message": "User was not added."}
        
    except paramiko.SSHException as e:
        print(f'SSH Error: {e}')
    except Exception as e:
        print(f'Error {e}')
    finally :
        client.close()

def give_program_permissions(ip_address, username, password):
    # check if the device already has a host key in the db
    # if not, confirm if the device is correct
    # set pramiko's key policy to reject if its not part of the host keys the server
    # load the host keys
    # connect to the client
    # make a user for ncpa installer
    # install our public key
    # make give a scoped passwordless sudo for sepcific functions
    # add the password to apply the commands
    # discard password

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
            stdin, stdout, stderr = client.exec_command(add_user, get_pty=True)
            stdin.write(password + '\n')
            stdin.flush()

        if stdout.channel.recv_exit_status() != 0:
            return {"success": False, "message": "User was not added."}

        with open(PUBLIC_KEY_PATH) as f:
            public_key = f.read().strip()

        make_dir = f'sudo -S mkdir -p ~{DEPLOYMENT_USER}/.ssh'
        stdin, stdout, stderr = client.exec_command(make_dir, get_pty=True)
        stdin.write(password + '\n')
        stdin.flush()
        print(make_dir, " " ,stdout.read().decode('utf-8'))
        print(make_dir, " " ,stderr.read().decode('utf-8'))

        add_key = f"sudo -S bash -c 'echo \"{public_key}\" >> ~{DEPLOYMENT_USER}/.ssh/authorized_keys'"
        stdin, stdout, stderr = client.exec_command(add_key)
        stdin.write(password + '\n')
        stdin.flush()
        print(add_key, " " ,stdout.read().decode('utf-8'))
        print(add_key, " " ,stderr.read().decode('utf-8'))

        add_folder_permission = f'sudo -S chmod 700 ~{DEPLOYMENT_USER}/.ssh'
        stdin, stdout, stderr = client.exec_command(add_folder_permission, get_pty=True)
        stdin.write(password + '\n')
        stdin.flush()
        print(add_folder_permission, " " ,stdout.read().decode('utf-8'))
        print(add_folder_permission, " " ,stderr.read().decode('utf-8'))

        add_folder_permission = f'sudo -S chmod 600 ~{DEPLOYMENT_USER}/.ssh/authorized_keys'
        stdin, stdout, stderr = client.exec_command(add_folder_permission, get_pty=True)
        stdin.write(password + '\n')
        stdin.flush()
        print(add_folder_permission, " " ,stdout.read().decode('utf-8'))
        print(add_folder_permission, " " ,stderr.read().decode('utf-8'))

        add_folder_permission = f'sudo -S chown -R {DEPLOYMENT_USER}:{DEPLOYMENT_USER} ~{DEPLOYMENT_USER}/.ssh'
        stdin, stdout, stderr = client.exec_command(add_folder_permission, get_pty=True)
        stdin.write(password + '\n')
        stdin.flush()
        print(add_folder_permission, " " ,stdout.read().decode('utf-8'))
        print(add_folder_permission, " " ,stderr.read().decode('utf-8'))

        if stdout.channel.recv_exit_status() !=0:
            return {"success": False, "message": f"Adding key failed.{stderr.read().decode('utf-8')}"}

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

        stdin, stdout, stderr = client.exec_command(sudo_setup_cmd, get_pty=True)
        stdin.write(password + "\n")   # feed the password to sudo's prompt
        stdin.flush()
        exit_status = stdout.channel.recv_exit_status()
        print(sudo_setup_cmd, " " ,stdout.read().decode('utf-8'))
        print(sudo_setup_cmd, " " ,stderr.read().decode('utf-8'))
        print(sudo_setup_cmd , " " ,stdout.channel.recv_exit_status())

        password = None

        if exit_status != 0:
            return {"success": False, "message": f"Setup failed. {stderr.read().decode('utf-8')} {stdout.read().decode('utf-8')}"}

        print("Success")

    except paramiko.SSHException as e:
        print(f'SSH Error: {e}')
        raise
    except Exception as e:
        print(f"Error {e}")
        raise
    finally:
        client.close()

    return 0

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
        stdin, stdout, stderr = client.exec_command(apt_update)
        exit_status = stdout.channel.recv_exit_status()
        print(apt_update, " " ,stdout.read().decode('utf-8'))
        print(apt_update, " " ,stderr.read().decode('utf-8'))
        print(apt_update , " " ,stdout.channel.recv_exit_status())

        install_apt_transport = "sudo apt-get install apt-transport-https"
        stdin, stdout, stderr = client.exec_command(install_apt_transport)
        exit_status = stdout.channel.recv_exit_status()
        print(install_apt_transport, " " ,stdout.read().decode('utf-8'))
        print(install_apt_transport, " " ,stderr.read().decode('utf-8'))
        print(install_apt_transport , " " ,stdout.channel.recv_exit_status())

        make_keyring = "sudo mkdir -m 0755 -p /etc/apt/keyrings/"
        stdin, stdout, stderr = client.exec_command(make_keyring)
        exit_status = stdout.channel.recv_exit_status()
        print(make_keyring, " " ,stdout.read().decode('utf-8'))
        print(make_keyring, " " ,stderr.read().decode('utf-8'))
        print(make_keyring , " " ,stdout.channel.recv_exit_status())

        get_gpg_key = (
            "curl -fsSL https://repo.nagios.com/GPG-KEY-NAGIOS-V3 | "
            "sudo -n gpg --dearmor -o /etc/apt/keyrings/GPG-KEY-NAGIOS-V3.gpg")
        stdin, stdout, stderr = client.exec_command(get_gpg_key)
        exit_status = stdout.channel.recv_exit_status()
        print(get_gpg_key, " " ,stdout.read().decode('utf-8'))
        print(get_gpg_key, " " ,stderr.read().decode('utf-8'))
        print(get_gpg_key , " " ,stdout.channel.recv_exit_status())

        source_content = (
            'Types: deb\n'
            'URIs: https://repo.nagios.com/deb/$(lsb_release -cs)\n'
            'Suites: /\n'
            'Signed-By: /etc/apt/keyrings/GPG-KEY-NAGIOS-V3.gpg'
        )
        add_source = f'echo "{source_content}" | sudo -n tee /etc/apt/sources.list.d/nagios.sources > /dev/null'
        stdin, stdout, stderr = client.exec_command(add_source)
        exit_status = stdout.channel.recv_exit_status()
        print(add_source, " " ,stdout.read().decode('utf-8'))
        print(add_source, " " ,stderr.read().decode('utf-8'))
        print(add_source , " " ,stdout.channel.recv_exit_status())

        apt_update = "sudo apt-get update"
        stdin, stdout, stderr = client.exec_command(apt_update)
        exit_status = stdout.channel.recv_exit_status()
        print(apt_update, " " ,stdout.read().decode('utf-8'))
        print(apt_update, " " ,stderr.read().decode('utf-8'))
        print(apt_update , " " ,stdout.channel.recv_exit_status())

        install_ncpa = "sudo -n apt-get install ncpa"
        stdin, stdout, stderr = client.exec_command(install_ncpa)
        exit_status = stdout.channel.recv_exit_status()
        print(install_ncpa, " " ,stdout.read().decode('utf-8'))
        print(install_ncpa, " " ,stderr.read().decode('utf-8'))
        print(install_ncpa , " " ,stdout.channel.recv_exit_status())

        configure_token = f"sudo -n sed -i 's/^community_string = .*/community_string = {TOKEN}/' /usr/local/ncpa/etc/ncpa.cfg"
        stdin, stdout, stderr = client.exec_command(configure_token)
        exit_status = stdout.channel.recv_exit_status()
        print(configure_token, " " ,stdout.read().decode('utf-8'))
        print(configure_token, " " ,stderr.read().decode('utf-8'))
        print(configure_token , " " ,stdout.channel.recv_exit_status())

        restart_ncpa = "sudo -n /etc/init.d/ncpa restart"
        stdin, stdout, stderr = client.exec_command(restart_ncpa)
        exit_status = stdout.channel.recv_exit_status()
        print(restart_ncpa, " " ,stdout.read().decode('utf-8'))
        print(restart_ncpa, " " ,stderr.read().decode('utf-8'))
        print(restart_ncpa , " " ,stdout.channel.recv_exit_status())

        add_ufw_rule = f"sudo -n ufw allow {NCPA_PORT}/tcp"
        stdin, stdout, stderr = client.exec_command(add_ufw_rule)
        exit_status = stdout.channel.recv_exit_status()
        print(add_ufw_rule, " " ,stdout.read().decode('utf-8'))
        print(add_ufw_rule, " " ,stderr.read().decode('utf-8'))
        print(add_ufw_rule , " " ,stdout.channel.recv_exit_status())


    except paramiko.SSHException as e:
        print(f'SSH Error: {e}')
        raise
    except Exception as e:
        print(f"Error {e}")
        raise
    finally:
        client.close()

    return 0


# result = give_program_permissions(ip_address="192.168.130.9",username="paeng",password="password")
give_program_permissions("192.168.130.9","paeng","password")
result = install_ncpa("192.168.130.9")
print(result)