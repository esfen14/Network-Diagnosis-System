# Pinpoint demo lab: five small servers

A script that builds five tiny VirtualBox servers for Pinpoint's network
discovery to find, so you can demo discovery, Nagios monitoring, alerts and NCPA
deployment. **Pinpoint itself is not part of this**: you deploy your own Pinpoint
VM and point it at the lab network (section 3).

Everything is run by hand with [`demo_lab.py`](demo_lab.py) (Python 3.10+,
`VBoxManage` and `ssh`; no pip packages). Commands that create or delete things
print a plan and change nothing until you add `--apply`.

**Status:** tested on VirtualBox 7.2.14 with a real Ubuntu 24.04 install. The base VM
built unattended in about 8 minutes, and all five servers came up with every service
answering over the lab network (including an SNMP query and SSH on 2222). `break`,
`fix`, `ssh-port`, `load`, host power-off and `reset` all worked. [`smoke_test.py`](smoke_test.py)
passes 59 checks. **Not yet verified here:** anything on the Pinpoint side (discovery,
Nagios, the NCPA wizard), because the test machine had no Pinpoint VM. Treat your first
demo as a rehearsal (section 9).

## 1. The servers

Every service below is one Pinpoint turns into a Nagios check on its own after
discovery (ssh, http, https, snmp), so everything the servers run shows up in
Nagios. After you deploy NCPA to a server, CPU, memory and disk checks appear too.

| Server | Address | Runs | Shows up in Nagios as | Why it is there |
|---|---|---|---|---|
| `web01` | 10.77.0.2 | ssh, http 80, https 443 | ssh, http, https | Web server; NCPA deployment with normal SSH |
| `web02` | 10.77.0.3 | ssh, http 80 | ssh, http | A second, simpler web server |
| `app01` | 10.77.0.4 | ssh, http **8080** | ssh, http on 8080 | A web service on a non-standard port, found by fingerprint |
| `snmp01` | 10.77.0.5 | ssh, snmp 161/udp | ssh, SNMP metrics | Network-device style monitoring |
| `legacy01` | 10.77.0.6 | ssh on **2222** | ssh on 2222 | NCPA deployment over a non-standard SSH port |

MariaDB, DNS and NTP are left out on purpose: Pinpoint only lists them as
"suggested" ports (promoting one is API-only today), so they would not appear in
Nagios.

**Small VMs.** Each server gets 512 MiB RAM, 1 CPU and 8 MiB of video memory, so
five servers need about 2.5 GiB of RAM in total. They are linked clones of one
base image, so they take little disk. Use `--memory 768` if a server struggles
with the NCPA install, or `--targets web01,legacy01` to run fewer. The RAM figures
are expected, not measured: confirm them in your first rehearsal.

## 2. How it works

- **A private network `pinpoint-demo`, `10.77.0.0/28`.** Your laptop is not on it,
  so discovery can never scan your real network.
- **Two NICs per server.** NIC 1 is NAT (internet for the NCPA install, plus a
  management SSH forwarded to `127.0.0.1` only). NIC 2 is the lab network.
- **Two SSH servers per server.** The *monitored* SSH is on the lab address and is
  what Pinpoint scans, trusts and deploys through. A separate key-only *management*
  SSH on the NAT side runs the demo controls, so breaking or moving the monitored
  SSH never cuts your control.
- **One base image, linked clones, powered-off snapshots.** `reset` returns every
  server to its `demo-ready` snapshot, so each demo starts clean.
- Only VMs named `pinpoint-demo-*` are ever created, changed or deleted.

## 3. Before you start

Needed: VirtualBox 7.x, the Ubuntu 24.04 live-server ISO (default
`~/Downloads/ubuntu-24.04.5-live-server-amd64.iso`, or pass `--iso`), about 20 GiB
free disk and about 3.5 GiB free RAM.

Your own Pinpoint VM needs three things, none of which the script touches:

1. A network adapter on the VirtualBox **Internal Network** named `pinpoint-demo`
   (Settings, Network). If you already use another internal network, pass
   `--lan-name NAME` to every command instead.
2. The address `10.77.0.1/28` on that adapter (leave `.1` free for it).
3. In Pinpoint: Settings, Discovery, Networks: `10.77.0.0/28`. Raising the session
   timeout also helps so nobody is logged out mid-demo.

### Setting up your Pinpoint VM's network

Give the Pinpoint VM **two** adapters (VM powered off, Settings, Network):

| Adapter | Attached to | Used for |
|---|---|---|
| Adapter 1 | Whatever you already use (NAT with a port forward, or Bridged) | Your browser, package installs and updates. Leave it as it is |
| Adapter 2 | **Internal Network**, name `pinpoint-demo` | Discovery and monitoring of the five servers |

The internal network has no DHCP, so the second adapter needs a fixed address.
Start the VM, find the new adapter's name, and give it `10.77.0.1/28`:

```bash
ip -br link                      # the adapter with no IPv4 address, e.g. enp0s8
sudo tee /etc/netplan/60-pinpoint-demo.yaml >/dev/null <<'EOF'
network:
  version: 2
  ethernets:
    enp0s8:                      # replace with the name from the line above
      addresses: [10.77.0.1/28]  # no gateway: this network is lab-only
EOF
sudo chmod 600 /etc/netplan/60-pinpoint-demo.yaml
sudo netplan apply
ip -br addr show enp0s8          # should list 10.77.0.1/28
```

Do not add a gateway or DNS to this adapter: it would compete with Adapter 1's
default route. Once the servers are up (section 4), check from the Pinpoint VM:
`ping -c 2 10.77.0.2`.

Optional, for demos: Pinpoint's shipped Nagios timings (`check_interval 5`,
`max_check_attempts 3` in the service template) can take about 7 minutes to alert.
Setting them to 1 and 1 on your lab Pinpoint makes alerts show within a couple of
minutes. That is a change on your Pinpoint VM, not in this repository.

## 4. Build it (once)

Run these from the `demo/` directory.

```bash
python3 demo_lab.py preflight                # fix every FAIL it reports
python3 demo_lab.py build-base               # prints the plan
python3 demo_lab.py build-base --apply       # unattended Ubuntu install, 10 to 25 minutes
python3 demo_lab.py create                   # prints the plan
python3 demo_lab.py create --apply           # clones and sets up the five servers
```

`build-base` installs Ubuntu without your help, sets it up, reboots once to check
it, and takes a `base-ready` snapshot. `create` clones five servers, boots each one
briefly to give it its role, powers it off and takes its `demo-ready` snapshot. You
will see `waiting for ... N min` lines while it works. If a step is interrupted or
fails, fix the cause and run the same command again: it skips what already exists.

Then start the lab and look at it:

```bash
python3 demo_lab.py up --gui                 # starts the five servers, one console window each
python3 demo_lab.py wall                     # live board; every service should show UP
```

## 5. Before each demo (about 10 minutes ahead)

```bash
python3 demo_lab.py reset --apply --up --gui    # asks you to type yes, then starts the lab clean
python3 demo_lab.py wall                        # leave this on the presenter screen
python3 demo_lab.py creds                       # the login for Pinpoint's NCPA wizard
```

Also restore your own Pinpoint VM to its clean state (the script does not manage
it), and check that it can reach the servers: `ping 10.77.0.2` from the Pinpoint VM.

## 6. Showing the servers working

Use all three at once:

| View | What it shows |
|---|---|
| Pinpoint in your browser | The product: devices, services, alerts, the NCPA wizard |
| `python3 demo_lab.py wall` | Every server and service, live, from outside the VMs |
| The VM console windows (`up --gui`) | Each server's own screen: a live service board that turns red the moment you break something |

## 7. Run of show (about 15 minutes)

The NCPA install takes a few minutes, so start it early and use the wait.

| # | You do | The audience sees | Time |
|---|---|---|---|
| 1 | Show the wall and the console windows | Five servers up, every service green | 1 min |
| 2 | In Pinpoint, start a rescan | The five servers appear with their services, including http on 8080 and ssh on 2222 | 2 min |
| 3 | Run the NCPA wizard for `web01` (`creds` gives the login), approve the fingerprint, deploy | Progress, then CPU, memory and disk checks | start now, 3 min |
| 4 | While it runs: `python3 demo_lab.py break web01 http` | web01's console shows http DOWN at once; Pinpoint raises an alert (1 to 3 minutes with the faster timings; talk meanwhile) | 3 min |
| 5 | Acknowledge the alert, then `python3 demo_lab.py fix web01 http` | The alert recovers; history shows both events | 2 min |
| 6 | `python3 demo_lab.py load web01 --seconds 90` | The CPU check climbs and crosses its threshold | 2 min |
| 7 | Run the NCPA wizard for `legacy01` | The fingerprint is read from port 2222 and the deployment succeeds over it | 3 min |
| 8 | Optional: `break app01 host`, then `fix app01 host` | The VM window closes; Pinpoint shows the host down, then up | 2 min |

`break web01 http` stops nginx, so https goes down with it; say so.
`ssh-port` can move a server's monitored SSH live, but Pinpoint keeps preferring the
port it knew until that port has been missing for five scans, so use it only to show
the change on the wall, never right before an NCPA deployment.

## 8. Commands

Options go before the command: `--lan-name`, `--lan-prefix`, `--targets`,
`--memory`, `--iso`, `--state-dir`. `python3 demo_lab.py -h` lists everything.

| Command | What it does |
|---|---|
| `preflight` | Read-only checks of this machine and the VMs |
| `build-base`, `create`, `snapshot`, `reset`, `destroy` | Print a plan; change nothing without `--apply`. `reset` and `destroy` also ask you to type `yes` (`--yes` skips that) |
| `up [--gui]`, `down` | Start or stop the servers |
| `status`, `wall [--once]` | Status table, or the live board |
| `break VM SERVICE` | Stop a service so Pinpoint alerts. `SERVICE` is one the server runs (`ssh`, `http`, `https`, `snmp`) or `host` to power the VM off |
| `fix VM SERVICE` | Start it again (`all` or `host` also work) |
| `ssh-port VM PORT` | Move the monitored SSH (`22` puts it back); see the note in section 7 |
| `load VM [--seconds N]` | Burn CPU on a server |
| `shell VM`, `creds` | A management shell in a server; the NCPA wizard login |
| `self-test` | Checks the script's own logic (no VirtualBox needed) |

`python3 smoke_test.py [--no-boot]` is the separate end-to-end check of the
VirtualBox side. It creates throwaway `pinpoint-demo-*` VMs without installing an
OS, tests them and deletes everything. It needs about 1.6 GiB of free RAM for its
boot stage and refuses to run if a demo lab already exists.

The demo's SSH key and generated password live in `~/.local/share/pinpoint-demo/`
(mode 600), never in the repository. The servers' management SSH is reachable only
at `127.0.0.1:2200` to `2205`, and the demo user has passwordless sudo inside the
disposable lab VMs.

## 9. If something goes wrong

The build and the controls have been tested, but not against your Pinpoint VM, so expect
to fix small things on the first rehearsal.

| What you see | What to do |
|---|---|
| `preflight`: a folder from an earlier lab is still on disk | VirtualBox cannot create a VM whose folder already exists. Delete the folder it names (if it holds a `.vdi`, run `VBoxManage closemedium disk FILE --delete` first) |
| `build-base`: the installer stops at `apt-get update`, or apt downloads fail with `Connection reset by peer` | Some networks reset plain http to the Ubuntu mirrors while https works. The lab already uses `https://archive.ubuntu.com`; check that `curl -I https://archive.ubuntu.com/ubuntu/` works from this machine |
| `VERR_SVM_IN_USE` when a VM starts | Another hypervisor holds AMD-V. Close it, then `sudo modprobe -r kvm_amd kvm` |
| `build-base`: the VM stops, or did not answer on SSH within 45 minutes | Open the console: `VBoxManage startvm pinpoint-demo-base --type separate`. Look for an installer error or a missing network. Fix it, then run `build-base --apply` again to resume |
| `build-base`: management SSH did not come up after the reboot | The base was left running. Check the console. The two SSH servers share port 22 by address (NAT side vs lab side); `systemctl status demo-mgmt-sshd ssh` shows which failed |
| `create`: `did not answer on its management SSH` | Look at that server's console window; run `status`. Run `create --apply` again |
| `wall` shows a server but Pinpoint cannot see it | Check your Pinpoint VM is on internal network `pinpoint-demo` with `10.77.0.1/28`, and `ping 10.77.0.2` from it. In the server: `ip -br addr` should show `lan0` |
| Alerts take about 7 minutes | The shipped Nagios timings; see section 3 |
| Not enough RAM | Power off other VMs, or use `--targets web01,legacy01`, or lower `--memory` carefully |
| Start over | `python3 demo_lab.py destroy --apply`, then build again |

## 10. Cleanup

```bash
python3 demo_lab.py down
python3 demo_lab.py destroy --apply          # asks you to type yes; deletes only pinpoint-demo-* VMs
rm -rf ~/.local/share/pinpoint-demo          # the demo key and password
```

`destroy` never touches your Pinpoint VM, your other VMs or the ISO.

## 11. Building the servers by hand (no `demo_lab.py`)

If you would rather make the VMs yourself, [`manual/`](manual/README.md) has one standalone
setup script per server (`web01.sh`, `web02.sh`, `app01.sh`, `snmp01.sh`,
`legacy01.sh`). Each gives the VM its lab address and services from section 1.

For each server, create an Ubuntu Server 24.04 VM with two adapters: Adapter 1 NAT
(to install packages) and Adapter 2 on the Internal Network `pinpoint-demo`. Create a
user with sudo and allow password login over SSH, because the NCPA wizard needs it.
Then copy the script in and run it:

```bash
ip -br link                          # the Adapter 2 name, e.g. enp0s8
sudo bash web01.sh enp0s8
```

Resources (measured with `demo_lab.py`: web01 used about 200 MiB of its 512 MiB, and
the install took 2.8 GiB of a 12 GiB disk):

| | Minimum that was tested | Note |
|---|---|---|
| RAM | 512 MiB per server | The Ubuntu installer needs more: give 1 GiB while installing, then lower it |
| CPU | 1 | |
| Disk | 8 GiB, dynamically allocated | |
| Video memory | 8 MiB | Headless use needs no more |

Lower values were not tried. The scripts in `manual/` have passed a syntax check only;
they have not yet been run on a VM.
