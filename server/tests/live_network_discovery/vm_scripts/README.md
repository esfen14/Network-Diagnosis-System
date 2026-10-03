# Disposable Pinpoint test VMs

This standalone kit creates the two Profile A targets used by the Network
Discovery Extended Test Plan. It never runs discovery or modifies Pinpoint or
Nagios. It is intended to be invoked manually, outside normal pytest collection.

| Guest | Address | RAM | CPUs | Disk | Services |
|---|---|---|---|---|---|
| `pinpoint-lab-target01` | `10.0.2.2` | 2 GiB | 2 | 12 GiB sparse | FTP, SSH, SMTP, HTTP, HTTPS, MariaDB, TCP 9000 |
| `pinpoint-lab-target02` | `10.0.2.3` | 1.5 GiB | 2 | 12 GiB sparse | SSH, TCP/UDP DNS, NTP, SNMP, UDP 69 |

NCPA is deliberately absent. Deploy it through Pinpoint's fingerprint-confirmed
workflow before expecting port 5693. Extended PostgreSQL, LDAP and Samba profiles
are not provisioned by this kit.

The default network is the approved `10.0.2.0/28` internal bridge. The script
requires that it does not overlap any management route or interface. A separate
NAT adapter is used only for package installation; the script removes it, removes
the guest default route, saves a powered-off baseline, and boots an isolated
overlay. KVM is used when accessible; otherwise QEMU software emulation is used.
Software emulation can take 15–30 minutes to configure both guests.

## Prerequisites

On an Ubuntu/Debian monitoring VM, install the host tools if absent:

```bash
sudo apt-get update
sudo apt-get install qemu-system-x86 qemu-utils libvirt-daemon-system libvirt-clients cloud-image-utils openssh-client python3
```

Use an administrator account with libvirt and image-directory access. The commands
below use `sudo` consistently so disk ownership changes by libvirt do not prevent
resuming or baseline creation. Python 3.10 or newer is sufficient; no pip packages
are required on the host.

The package-install network must already be an active libvirt NAT network named
`default` (or the configured equivalent). The provisioner validates it but never
changes it. Guest packages are downloaded from Ubuntu repositories.

**The two VMs already created in this session occupy `.2` and `.3`.** Do not run
this kit alongside them on the same addresses. Stop those existing disposable
guests first, or choose a separate isolated subnet and matching addresses. This
kit uses new names and refuses to adopt existing domains with different UUIDs.

## Create the lab

From this scripts directory:

```bash
cp vm-lab.example.json vm-lab.json
```

Review `vm-lab.json`, particularly network, bridge, target addresses and application
URL. Keep generated disks and keys outside the source directory. For example:

```bash
LAB_STATE=/var/lib/libvirt/images/pinpoint-lab
LAB_IMAGES=/var/lib/libvirt/images/pinpoint-image-cache
```

Run the self-tests and inspect a preview. Preview commands do not create files or
contact libvirt or download images:

```bash
python3 self_tests.py
python3 fetch_image.py --output-dir "$LAB_IMAGES"
python3 provision_lab.py up --config vm-lab.json --state-dir "$LAB_STATE"
```

Download and verify the official Ubuntu 22.04 cloud image. The checksum is fetched
over HTTPS from the official Ubuntu image directory and stored alongside the
image. An existing image with a different current checksum is never overwritten.

```bash
sudo python3 fetch_image.py --output-dir "$LAB_IMAGES" --apply
```

Create or validate/start the explicitly named isolated network. It has no
forwarding or DHCP. An existing incompatible network is rejected:

```bash
sudo python3 provision_lab.py network --config vm-lab.json --state-dir "$LAB_STATE" --apply
```

Prepare the images and boot/configure the two guests:

```bash
LAB_SHA256=$(sudo cat "$LAB_IMAGES/jammy-server-cloudimg-amd64.img.sha256")
sudo python3 provision_lab.py up --config vm-lab.json --state-dir "$LAB_STATE" \
  --image "$LAB_IMAGES/jammy-server-cloudimg-amd64.img" --sha256 "$LAB_SHA256" --apply
```

For offline image preparation, supply an existing cloud image and its trusted
SHA-256 instead of running `fetch_image.py`. Guest package installation still
needs NAT access to repositories unless you configure an offline apt mirror.

`prepare --apply` runs the image/seed preparation without booting. After successful
preparation, `up --apply` can omit `--image` and `--sha256` and use its pinned cache.
Do not edit the VM configuration after preparation; use a new state directory for
different settings. To resume an interrupted first preparation, repeat the
original command including image/checksum.

## Verify and reuse

```bash
sudo python3 provision_lab.py status --config vm-lab.json --state-dir "$LAB_STATE"
sudo python3 provision_lab.py verify --config vm-lab.json --state-dir "$LAB_STATE"
sudo python3 provision_lab.py stop --config vm-lab.json --state-dir "$LAB_STATE" --apply
sudo python3 provision_lab.py up --config vm-lab.json --state-dir "$LAB_STATE" --apply
```

`verify` checks the saved ownership UUIDs, runtime adapters, guest routes, active
systemd services and actual TCP/UDP listening sockets. It writes `inventory.json`.
It does not claim Nagios/Pinpoint visibility, protocol success, or failure/recovery
acceptance. Run the full test harness separately for those checks.

Restore both VMs to the configured pre-NCPA baselines:

```bash
sudo python3 provision_lab.py restore --config vm-lab.json --state-dir "$LAB_STATE"
sudo python3 provision_lab.py restore --config vm-lab.json --state-dir "$LAB_STATE" --apply
```

Restoration cleanly shuts down each owned guest, preserves its current overlay as
`targetXX-retired-<id>.qcow2`, creates a fresh overlay and boots it. Baselines remain
unchanged. Repeated restoration retains old overlays, so account for disk usage.
No script deletes guests, disks, unrelated networks or host firewall rules.

`stop` remains available if the lab/NAT network is down. If initial provisioning
fails, the guest may still have its temporary NAT adapter; stop the owned guests
or rerun `up` to finish isolation. Never begin discovery before `verify` succeeds.
Guest setup failures produce `/root/pinpoint-setup-error.txt` inside that guest.
After correcting the failure, rerun `sudo python3 /root/pinpoint-guest-setup.py`
inside the guest, then resume `up` on the host.

## SSH and harness integration

The kit generates the guest SSH host keys locally and supplies them through
cloud-init. `known_hosts` therefore pins the expected keys before any connection;
it does not trust keys learned from a network scan. It uses a separate lab-only
client key, and does not change your global SSH trust file.

```bash
sudo ssh -i "$LAB_STATE/lab_key" \
  -o UserKnownHostsFile="$LAB_STATE/known_hosts" \
  -o StrictHostKeyChecking=yes pinpoint-test@10.0.2.2
```

Generated files include:

- `lab.json`: settings for the existing live Network Discovery harness. Set the
  absolute application `system.db` path and verify `pinpoint.base_url` before use.
  NCPA port 5693 is listed as an eventual expectation, not a provisioned service.
- `plugin-variables.private.json`: per-host MySQL/DNS/SNMP overrides. Apply them
  through the application's supported configuration workflow before checking
  these mappings. No application database is modified automatically.
- `lab_key`, `known_hosts`, cloud-init seeds, and private `state.json`.
- `targetXX-baseline.qcow2` and the current disposable disk overlays.
- `inventory.json`: listener/route evidence suitable for review.

The current harness's `remote_service.py` uses the invoking account's default SSH
trust file. For that harness, add the kit's pinned public host keys to that
account's `known_hosts`, and set `PINPOINT_TEST_SSH_KEY` to its accessible lab key.
Resolve any existing entry for the same disposable address deliberately; do not
disable strict checking. Pinpoint login credentials remain environment references
`PINPOINT_TEST_EMAIL` and `PINPOINT_TEST_PASSWORD`; this kit does not create users.

MySQL uses a generated password and an account with SELECT access only to
`pinpoint_test`, restricted to the monitoring address. SNMP uses a generated
community, also restricted to that address. DNS has a local `test.local` zone and
the normal `localhost` lookup. SMTP delivers locally and trusts only loopback for
relaying. The self-signed HTTPS certificate is a lab fixture.

**Do not commit or export the state directory, disks, seeds or private plugin
variables.** They contain secrets. If adding these scripts to the repository,
ignore runtime `vm-lab.json`, image caches and state directories. Keep secrets out
of test reports; export the generated inventory and sanitized harness evidence.

Application discovery bugs and a missing host plugin executable are separate
gates: provisioning the VMs does not bypass the regression rule in the test plan.

## Files to add to the repository

Place the kit under the opt-in live harness's `provision/` directory and document
it in the live harness README. `guest_setup.py` and `vm-lab.example.json` must stay
beside `provision_lab.py`. `self_tests.py` is deliberately outside normal pytest
collection and can be run explicitly. Update the relevant test documentation when
you add the kit.
