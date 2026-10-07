# Building the demo servers by hand

Five standalone scripts that turn a plain Ubuntu Server 24.04 VM into one of the demo
lab's servers. Use them instead of `../demo_lab.py` if you want to create the VMs
yourself. Each script gives the VM its lab address and services, so Pinpoint's network
discovery finds it.

The scripts have only passed a syntax check (`bash -n`). They have not yet been run on a
VM, so treat the first run as a rehearsal.

## The servers

| Script | Hostname | Lab address | Services | Shows up in Nagios as |
|---|---|---|---|---|
| [`web01.sh`](web01.sh) | web01 | 10.77.0.2 | ssh 22, http 80, https 443 (self-signed certificate) | ssh, http, https |
| [`web02.sh`](web02.sh) | web02 | 10.77.0.3 | ssh 22, http 80 | ssh, http |
| [`app01.sh`](app01.sh) | app01 | 10.77.0.4 | ssh 22, http **8080** | ssh, http on 8080 |
| [`snmp01.sh`](snmp01.sh) | snmp01 | 10.77.0.5 | ssh 22, snmp 161/udp (community `public`, read-only) | ssh, SNMP metrics |
| [`legacy01.sh`](legacy01.sh) | legacy01 | 10.77.0.6 | ssh on **2222** only (nothing on 22) | ssh on 2222 |

You do not have to build all five. `web01` and `legacy01` together cover a normal SSH
server and a non-standard SSH port.

## Minimum resources per VM

These are the sizes used and measured when `../demo_lab.py` built and ran two of the
servers. Lower values were not tried.

| | Minimum tested | Measured |
|---|---|---|
| RAM | 512 MiB | `web01` used about 200 MiB with nginx and SSH running |
| CPU | 1 | Load stayed under 2 at idle |
| Disk | 8 GiB, dynamically allocated | The install took 2.8 GiB of a 12 GiB disk |
| Video memory | 8 MiB | Enough for a console; no GUI is installed |
| Network | 2 adapters | See below |

The Ubuntu installer needs more RAM than the finished server. Give the VM 1 GiB while
installing, then lower it to 512 MiB. All five servers at 512 MiB need about 2.5 GiB of
RAM in total.

## Before you run a script

1. **OS:** Ubuntu Server 24.04 (the scripts use `apt`, `netplan` and systemd).
2. **Two network adapters:**
   - Adapter 1: **NAT**, so the script can install packages.
   - Adapter 2: **Internal Network** named `pinpoint-demo`, the lab network
     `10.77.0.0/28`. Your own Pinpoint VM must be on the same network with
     `10.77.0.1/28`; see section 3 of [`../README.md`](../README.md).
3. **A user with sudo** and SSH password login. Pinpoint's NCPA wizard connects with a
   username and password.
4. **Distinct MAC addresses.** If you clone a VM, let VirtualBox generate new MAC
   addresses for both adapters.

## Running a script

Copy the script into the VM (for example with `scp`, or paste it into a file), find the
name of Adapter 2, and run it as root:

```bash
ip -br link                      # Adapter 2 is the one with no IPv4 address, e.g. enp0s8
sudo bash web01.sh enp0s8        # the argument is optional; the default is enp0s8
```

Each script:
- installs its packages with `apt`;
- sets the hostname;
- writes `/etc/netplan/60-demo-lan.yaml` with the lab address on Adapter 2, with no
  gateway and no DNS, so it does not compete with NAT's default route;
- configures and starts its services;
- ends by printing the ports it is listening on.

Running a script again is meant to be safe: it rewrites the same files.

## Checking it worked

On the server:

```bash
ip -br addr show enp0s8          # the lab address, e.g. 10.77.0.2/28
ss -ltn                          # the TCP ports from the table above
ss -lun | grep 161               # snmp01 only
```

From another lab VM, or from your Pinpoint VM:

```bash
ping -c 2 10.77.0.2
curl -sI http://10.77.0.2/       # web01, web02
curl -sI http://10.77.0.4:8080/  # app01
curl -skI https://10.77.0.2/     # web01 (self-signed, so -k)
ssh -p 2222 USER@10.77.0.6       # legacy01
```

## Notes

- **legacy01 and port 22.** Ubuntu 24.04 starts SSH through `ssh.socket`, which ignores
  `Port` in the SSH config. `legacy01.sh` turns that socket off so SSH really moves to
  2222. Afterwards, log in on port 2222 or use the VM console.
- **apt downloads fail with `Connection reset by peer`.** Some networks reset plain http
  to the Ubuntu mirrors while https works. The lab built by `demo_lab.py` uses https. For
  these scripts, switch the VM before running one:

  ```bash
  sudo sed -i 's|http://|https://|' /etc/apt/sources.list.d/ubuntu.sources
  sudo apt-get update
  ```
- **Firewall.** Ubuntu Server ships with `ufw` disabled. If you turned it on, allow the
  ports in the table.
- **Showing a failure in a demo.** `sudo systemctl stop nginx` on `web01` takes both
  http and https down; `sudo systemctl start nginx` brings them back. For `snmp01`, use
  `snmpd`. Pinpoint raises an alert after its next check; with the shipped Nagios
  timings that can take about 7 minutes (see section 3 of [`../README.md`](../README.md)).
- **What these scripts do not do:** the `demo_lab.py` extras (the live service board on
  the VM console, the management SSH on the NAT side, and the break/fix/reset controls).
