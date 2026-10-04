# Pinpoint demo lab

A plan and a script for building a small VirtualBox lab and using it to show
Pinpoint working: discovery, monitoring, alerts, NCPA deployment and the
non-standard SSH port feature. Everything is driven by
[`demo_lab.py`](demo_lab.py) (Python 3.10+ and `VBoxManage`; no pip packages).

**Status:** smoke-tested on this laptop's VirtualBox 7.2.14 with
[`smoke_test.py`](smoke_test.py): 37 checks pass. They cover creating the base VM
(including the unattended-install setup), the linked clones, networks, port
forwards, snapshots, `reset`, `destroy`, and a short real boot of the two empty
targets. **Not yet verified:** the Ubuntu install itself, the guest scripts
running, SSH into the guests, and everything on the Pinpoint side. Treat the first
real build as a rehearsal (see section 9).

## 1. What the audience sees

| View | What it shows |
|---|---|
| Pinpoint in a browser (`http://127.0.0.1:8480`) | The product: devices, services, alerts, NCPA wizard |
| `demo_lab.py wall` in a terminal | Every VM and its services, live, from outside the VMs |
| The VM console windows (`up --gui`) | Each VM's own screen: a live service board that turns red the moment you break something |

## 2. Design

- **VirtualBox, not KVM.** This laptop has no `/dev/kvm`. The KVM kit under
  `server/tests/e2e/network_discovery/vm_scripts/` builds the *test* lab inside
  the Pinpoint VM and is left untouched.
- **A private network, `10.77.0.0/28`.** Pinpoint `.1`, web01 `.2`, infra01 `.3`.
  The laptop is not on it, so discovery can never scan your real network.
- **Two NICs per target.** NIC 1 is NAT (internet for the NCPA install, plus a
  management SSH forwarded to `127.0.0.1` only). NIC 2 is the lab network.
- **Two SSH servers per target.** The *monitored* SSH is on the lab address and
  is what Pinpoint scans, trusts and deploys through. A separate key-only
  *management* SSH on the NAT side runs the demo controls. Breaking or moving the
  monitored SSH never cuts the demo's control.
- **One base image, linked clones, powered-off snapshots.** The base is built
  once from your Ubuntu ISO; web01 and infra01 are small clones; `reset` restores
  every VM to its `demo-ready` snapshot, so each run starts clean.
- **Your Pinpoint VM is copied, never changed.** The server in the lab is a
  linked clone of your installed Pinpoint VM at a snapshot named `demo-ready`.

```text
  laptop (127.0.0.1)                   VirtualBox internal network "pinpoint-demo"  10.77.0.0/28
  :8480  -> Pinpoint UI                +---------------------------------------------------+
  :2201  -> Pinpoint SSH               |  pinpoint-demo-server  10.77.0.1   Nagios + app   |
  :2202  -> web01 mgmt SSH   NAT ----->|  pinpoint-demo-web01   10.77.0.2   ssh http https |
  :2203  -> infra01 mgmt SSH           |                                    mariadb        |
                                       |  pinpoint-demo-infra01 10.77.0.3   ssh dns ntp    |
                                       |                                    snmp           |
                                       +---------------------------------------------------+
```

## 3. Resources

| VM | RAM | vCPU | Disk |
|---|---:|---:|---|
| `pinpoint-demo-server` | 4096 MiB | 2 | linked clone (small) |
| `pinpoint-demo-web01` | 1024 MiB | 1 | linked clone (small) |
| `pinpoint-demo-infra01` | 1024 MiB | 1 | linked clone (small) |
| `pinpoint-demo-base` | 1024 MiB | 1 | 12 GiB sparse, powered off after the build |

The lab needs about 6 GiB of free RAM. On this laptop the running `Nagios-Test`
VM holds roughly 10 GiB, so power it off before the demo. `preflight` checks this.

## 4. One-time setup

Run the commands from the repository root.

### Step 0: prerequisites

- The NCPA merge repair is merged to `main` and a Pinpoint install from it boots
  (the installer clones `main`).
- `~/Downloads/ubuntu-24.04.5-live-server-amd64.iso` exists (override with `--iso`).

### Step 1: a working Pinpoint VM with a `demo-ready` snapshot

`Pinpoint-installer-testing` no longer exists in VirtualBox (its folder is gone),
so build a Pinpoint VM first. Use any name and pass it with `--source-vm NAME`.

1. Install it from `~/Downloads/PinPoint-Installer-v1.1.iso` as you normally do.
   Its first boot needs internet (it clones `main`), so give NIC 1 NAT or bridged,
   and add NIC 2 as an *Internal Network* (any name). Wait for first boot to
   finish and log in to the UI once.
2. Inside the VM, give the second NIC the lab address. Find its name with
   `ip -br link`, then write `/etc/netplan/60-demo-lan.yaml` (match by name, not
   MAC, because the clone gets new MACs) and run `sudo netplan apply`:

   ```yaml
   network:
     version: 2
     ethernets:
       enp0s8:                      # the second NIC; check the name
         addresses: ["10.77.0.1/28"]
   ```
3. In Pinpoint: Settings, Discovery, Networks: set `10.77.0.0/28` and save. Raise
   the session timeout (System settings) so nobody is logged out mid-demo, and
   create the presenter account.
4. Find the port the UI listens on inside the VM (`ss -ltn`). If it is not 80,
   pass `--ui-guest-port N` to `create`.
5. **Optional, recommended:** shorten the Nagios checks so alerts show quickly.
   In the VM, edit
   `/opt/pinpoint/Network-Diagnosis-System/server/app/network_discovery/templates/service.cfg.tpl`
   and set `check_interval 1` and `max_check_attempts 1` (the shipped values are 5
   and 3, which can take about 7 minutes to alert). Rescan once so the config is
   regenerated. This is a demo-only change on the lab VM; do not commit it.
6. Shut the VM down. In VirtualBox take a snapshot named exactly `demo-ready`.

### Step 2: check this machine

```bash
python3 demo/demo_lab.py preflight
```

Fix every `FAIL`. The expected `warn` for other running VMs means: power them off.

### Step 3: build the base VM (about 10 to 25 minutes, unattended)

```bash
python3 demo/demo_lab.py build-base            # prints the plan only
python3 demo/demo_lab.py build-base --apply
```

It installs Ubuntu unattended, provisions every role's packages, verifies the
management SSH after a reboot, and takes the `base-ready` snapshot. Re-running
resumes an interrupted build.

### Step 4: create the lab (about 5 minutes)

```bash
python3 demo/demo_lab.py create                # plan
python3 demo/demo_lab.py create --apply
python3 demo/demo_lab.py up --gui
python3 demo/demo_lab.py wall
```

Do one full rehearsal now. If the Pinpoint VM needs changes afterwards, shut the
lab down (`down`) and run `snapshot --apply pinpoint` to make the new state the
clean one.

## 5. Before each demo (about 10 minutes ahead)

```bash
python3 demo/demo_lab.py reset --apply --up --gui   # clean state, all VMs started
python3 demo/demo_lab.py wall                       # leave on the presenter screen
python3 demo/demo_lab.py creds                      # the login for the NCPA wizard
```

Check that the wall shows every service `UP`, that `http://127.0.0.1:8480` loads
and is logged in, and that the VM windows show their service boards.

## 6. Run of show (about 15 minutes)

The NCPA install takes a few minutes, so start it first and use the wait.

| # | You do | The audience sees | Time |
|---|---|---|---|
| 1 | Show the wall and the two VM windows | Four machines running, each service up | 1 min |
| 2 | Pinpoint: start a rescan | web01 and infra01 appear with their services. infra01's SSH is on **2222**, and Pinpoint still finds and monitors it | 2 min |
| 3 | Pinpoint: open the NCPA wizard for web01 (`creds` gives the login), approve the fingerprint, deploy | Progress, then CPU, memory and disk checks appear | start now, 3 min |
| 4 | While it runs: `break web01 http` | web01's console shows http DOWN at once; Pinpoint raises an alert (about 1 to 3 minutes; talk meanwhile) | 3 min |
| 5 | Acknowledge the alert, then `fix web01 http` | The alert recovers; notifications and history show both events | 2 min |
| 6 | `load web01 --seconds 90` | The CPU check climbs and crosses its threshold | 2 min |
| 7 | Run the NCPA wizard for infra01 | The fingerprint is read from port 2222 and the deployment succeeds over it; this is the non-standard SSH port feature | 3 min |
| 8 | Optional: `break web01 host`, then `fix web01 host` | The VM window closes; Pinpoint shows the host down, then up | 2 min |

Notes:

- infra01's monitored SSH starts on port 2222 on purpose. `ssh-port` can move it
  live to show the change on the wall, but Pinpoint keeps preferring the port it
  knew until that port has been missing for five scans, so do not deploy NCPA
  right after a live move.
- `break web01 http` stops nginx, so https goes down with it; say so. SSH,
DNS, NTP, SNMP and MariaDB can be broken the same way. Only ssh, http, https, snmp
and NCPA are monitored automatically; MariaDB, DNS and NTP appear in Pinpoint
only as suggested ports.

## 7. Commands

| Command | What it does |
|---|---|
| `preflight` | Read-only checks of this machine and the VMs |
| `build-base`, `create`, `snapshot`, `reset`, `destroy` | Print a plan; change nothing without `--apply` |
| `up [--gui]`, `down` | Start or stop the lab |
| `status`, `wall [--once]` | Status table, or the live board |
| `break VM SERVICE`, `fix VM SERVICE\|all` | Stop or start a service. `SERVICE` is `ssh`, `http`, `https`, `mariadb` (web01), `ssh`, `dns`, `ntp`, `snmp` (infra01) or `host` |
| `ssh-port VM PORT` | Move the monitored SSH (`22` puts it back); see the note in section 6 |
| `load VM [--seconds N]` | Burn CPU |
| `shell VM`, `creds` | A management shell; the wizard login |
| `self-test` | Checks the script's own logic (no VirtualBox needed) |

`python3 demo/smoke_test.py [--no-boot]` is the separate end-to-end check of the
VirtualBox side. It creates throwaway `pinpoint-demo-*` VMs without installing an
OS, tests them, and deletes everything. It needs about 2.6 GiB of free RAM for its
boot stage (`--no-boot` skips that) and refuses to run if a demo lab already
exists, because it deletes demo VMs when it finishes.

Options before the command: `--state-dir`, `--iso`, `--source-vm`,
`--ui-guest-port`, `--ui-host-port`.

The demo's SSH key and generated password live in `~/.local/share/pinpoint-demo/`
(mode 600), never in the repository.

## 8. Safety

- Only VMs named `pinpoint-demo-*` are created, changed or deleted; `destroy`
  refuses any other name and never touches your Pinpoint VM or the ISOs.
- The host forwards only to `127.0.0.1`. The monitored SSH allows password login
  because Pinpoint's wizard needs it, but only on the isolated lab network.
- The demo user has passwordless sudo inside the lab VMs. They are disposable.

## 9. What has not been verified

The smoke test proves the VirtualBox commands, but no guest has run the install
or the scripts yet. Expect to fix small things during the first rehearsal. The
likely ones:

1. **Unattended install and the post-install command.** It must install
   `openssh-server` and the key inside the installer. If `build-base` times out,
   open the console: `VBoxManage startvm pinpoint-demo-base --type separate`.
2. **The two SSH servers.** Ubuntu 24.04 starts SSH from a systemd socket;
   the base script turns that off so both daemons can bind. After the first
   `create`, check that `break web01 ssh` leaves `shell web01` working.
3. **The lab network address** is set by netplan from the NIC's MAC address.
   If `wall` shows a target but Pinpoint cannot see it, check `ip -br addr` in it.
4. **The Pinpoint UI port** inside its VM (step 1.4) and the installer's own
   behaviour on a cloned VM.
5. **Alert speed.** Without step 1.5 the shipped Nagios timings can take about 7
   minutes to alert.
6. **RAM.** Power off other VMs; the lab needs about 6 GiB free.

If a build step fails, `build-base` and `create` can be re-run: they skip what
exists. `destroy --apply` removes the demo VMs so you can start over.

## 10. Cleanup

```bash
python3 demo/demo_lab.py down
python3 demo/demo_lab.py destroy --apply
rm -rf ~/.local/share/pinpoint-demo        # the demo key and password
```
