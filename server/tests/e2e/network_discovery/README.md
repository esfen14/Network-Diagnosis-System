# Live Network Discovery Harness

This directory contains the opt-in scripts, manifests, safety checks, service
controls, and reporting code used to execute
[`../../plans/NETWORK_DISCOVERY_EXTENDED_TEST_PLAN.md`](../../plans/NETWORK_DISCOVERY_EXTENDED_TEST_PLAN.md).

The proposed [test approach adjustment](../../plans/TEST_APPROACH_ADJUSTMENT_PLAN.md)
is deferred pending fixes. This directory preserves the existing harness; it
is not yet the complete deterministic browser-to-Nagios runner.

It is deliberately separate from normal pytest collection and requires an
explicit lab configuration and command for every live action.

## Safety boundary

- Nothing in this directory may run during application installation, startup,
  scheduler initialization, or normal `pytest` collection.
- Live tests must require an explicit command and a lab configuration file.
- The runner must reject loopback, public, management, and overly broad network
  targets before invoking `nmap`.
- Scripts may modify only the named disposable lab targets and test-specific
  Nagios files.
- Secrets and generated results must remain untracked.
- Every disruptive action must have an idempotent recovery action.
- Cleanup must remove only resources created by the harness.

## Implemented layout

```text
network_discovery/
|-- README.md
|-- config/
|   |-- lab.example.json
|   `-- plugin-cases.example.json
|-- provision/
|   |-- detect_backend.py
|   |-- install_test_dependencies.py
|   `-- prepare_test_host.sh
|-- vm_scripts/                  # disposable KVM/libvirt target kit
|   |-- README.md
|   |-- fetch_image.py
|   |-- provision_lab.py
|   |-- guest_setup.py
|   |-- self_tests.py
|   `-- vm-lab.example.json
|-- services/
|   |-- configure_target01.sh
|   |-- configure_target02.sh
|   `-- remote_service.py
|-- runner/
|   |-- run_tests.py
|   |-- common.py
|   |-- discovery.py
|   |-- nagios.py
|   |-- pinpoint.py
|   `-- report.py
|-- harness_tests.py
`-- cleanup/
    `-- restore_lab.py
```

Guest/network creation uses the standalone
[`vm_scripts/`](vm_scripts/README.md) kit when nested KVM/libvirt is available.
`detect_backend.py` distinguishes command presence from usable daemon access
for KVM/libvirt, Incus/LXC (including `/snap/bin/lxc`), and Docker.
Pre-provisioned disposable targets are also supported. Record the selected
backend and its verified administrative access in the report.

The VM kit creates the isolated network, two cloud-image targets, pinned SSH
keys, baseline overlays, and harness configuration. Its `10.0.2.0/28` network
is the approved lab range for this installation, but it is valid only after the
kit proves that it does not overlap any management or reachable route. Never
scan `192.168.130.0/28` here because it overlaps the management network. Read
the kit README and run its preview and self-tests before any `--apply` command.
Do not start discovery until `provision_lab.py verify` succeeds.

When nested virtualization is enabled after an existing lab was created with
QEMU software emulation, use the VM kit's preview-first `enable-kvm` action. It
converts the owned definitions and verifies runtime KVM acceleration without
rebuilding disks or baselines; see the VM-kit guide for the commands.

After creating minimal Debian/Ubuntu guests, copy the matching bootstrap into
each guest. Both scripts are preview-only unless `--apply` is explicitly
provided:

```bash
sudo bash configure_target01.sh
sudo bash configure_target01.sh --apply

sudo bash configure_target02.sh
sudo bash configure_target02.sh --apply
```

Review the preview and script contents before `--apply`. The scripts install
only Profile A services. NCPA must still be deployed through Pinpoint so the
actual trust and deployment workflow is tested.

## Configuration

Copy the examples to their ignored runtime names and review every value:

```bash
cd server/tests/e2e/network_discovery
cp config/lab.example.json config/lab.json
cp config/plugin-cases.example.json config/plugin-cases.json
```

The harness accepts only a canonical private IPv4 network of `/28` or smaller.
Every target and the Pinpoint test address must be unique members of that
network. The real `lab.json`, private keys, and results are ignored by Git.

Credentials are read only from the environment variables named by `lab.json`:

```bash
mkdir -p ~/.config/pinpoint-tests
chmod 700 ~/.config/pinpoint-tests
test -e ~/.config/pinpoint-tests/lab.env || \
  install -m 600 /dev/null ~/.config/pinpoint-tests/lab.env
chmod 600 ~/.config/pinpoint-tests/lab.env
nano ~/.config/pinpoint-tests/lab.env
```

Add these exports to `~/.config/pinpoint-tests/lab.env`:

```bash
export PINPOINT_TEST_EMAIL='your-test-account-email'
export PINPOINT_TEST_PASSWORD='your-test-account-password'
export PINPOINT_TEST_SSH_KEY='/opt/pinpoint/Network-Diagnosis-System/.cache/pinpoint-live-test-access/test_key'
```

Before invoking the harness, the AI sources the file in the same shell:

```bash
set +x
source ~/.config/pinpoint-tests/lab.env
```

The guarded `install` command creates the file only when it does not already
exist; an unguarded repeat would truncate it. Do not enable shell tracing while
sourcing the file.

Do not place the actual values in JSON, shell history, test evidence, or source
control. Pre-populate `known_hosts` for each target and verify its fingerprint;
remote service control uses strict host-key checking.

### Nested virtualization, Nagios, and NCPA SSH access

Verify the system libvirt connection and nested-virtualization prerequisites:

```bash
virsh -c qemu:///system list --all
sudo virt-host-validate
virsh -c qemu:///system net-list --all
```

An empty domain list is normal before provisioning. QEMU/KVM failures block the
VM kit; IOMMU, secure-guest, and unused LXC warnings do not. The `default`
libvirt NAT network must be active for guest package installation. The VM kit
attaches a second isolated interface and removes the guest NAT interface before
the discovery phase.

Grant the `paeng` test account the narrowly scoped Nagios access required by
the current lab:

```bash
sudo setfacl -m u:paeng:rx /usr/local/nagios/bin/nagios
sudo setfacl -m u:paeng:rwx /usr/local/nagios/var/spool/checkresults
sudo setfacl -m u:paeng:r /usr/local/nagios/etc/resource.cfg

getfacl /usr/local/nagios/bin/nagios
getfacl /usr/local/nagios/var/spool/checkresults
getfacl /usr/local/nagios/etc/resource.cfg
/usr/local/nagios/bin/nagios -v /usr/local/nagios/etc/nagios.cfg
```

Install the OS `acl` package first if `setfacl` is unavailable. Do not broaden
these entries recursively across `/usr/local/nagios`. `resource.cfg` may contain
secret macro values: verify its ACL without printing, copying, or collecting its
contents as evidence.

Grant traversal-only access to the application SSH directory and read-only
access to the reviewed NCPA deployment key:

```bash
sudo setfacl -m u:paeng:x /opt/pinpoint/.ssh
sudo setfacl -m u:paeng:r /opt/pinpoint/.ssh/pinpoint_ncpa_deploy

getfacl /opt/pinpoint/.ssh
getfacl /opt/pinpoint/.ssh/pinpoint_ncpa_deploy
```

Do not grant directory listing or write access. Never print, copy, checksum, or
collect the private key as evidence. This deployment identity is separate from
the VM provisioning/test identity. In this lab, do not point
`PINPOINT_TEST_SSH_KEY` at `pinpoint_ncpa_deploy`; it is not authorized for the
pre-deployment `pinpoint-test` guest account.

### Existing lab access and recovery

Do not rebuild the targets merely because SSH rejects the NCPA deployment key
or `virsh snapshot-list` is empty. The existing disposable lab may still be
healthy and recoverable.

The NCPA deployment key and the VM provisioning/test key have different roles.
Using `/opt/pinpoint/.ssh/pinpoint_ncpa_deploy` for the `pinpoint-test` account
can correctly return `Permission denied (publickey)` even when both guests are
properly provisioned. Before rebuilding anything:

1. Locate the existing VM-kit state and provisioning artifacts.
2. Use the dedicated test key together with its pinned `known_hosts` file.
3. Confirm strict SSH access to both `10.0.2.2` and `10.0.2.3`.
4. Set `PINPOINT_TEST_SSH_KEY` to the dedicated test key for harness operations.
5. Run the VM kit's `status` and `verify` commands to check ownership,
   interfaces, routes, listeners, SSH trust, and baselines.

For the current retained lab, the dedicated artifacts are under:

```text
/opt/pinpoint/Network-Diagnosis-System/.cache/pinpoint-live-test-access/test_key
/opt/pinpoint/Network-Diagnosis-System/.cache/pinpoint-live-test-access/known_hosts
```

Keep the private key mode at `0600`. Never disable strict host-key checking or
copy private-key contents into reports. Verify the retained identity explicitly:

```bash
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/opt/pinpoint/Network-Diagnosis-System/.cache/pinpoint-live-test-access/known_hosts \
  -i "$PINPOINT_TEST_SSH_KEY" pinpoint-test@10.0.2.2 true

ssh -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/opt/pinpoint/Network-Diagnosis-System/.cache/pinpoint-live-test-access/known_hosts \
  -i "$PINPOINT_TEST_SSH_KEY" pinpoint-test@10.0.2.3 true
```

The current remote-service helper uses the invoking account's default
`~/.ssh/known_hosts`. Ensure it contains the same already-pinned entries before
running service cases; never replace them with unverified `ssh-keyscan` output.

An empty libvirt snapshot list does not prove that recovery baselines are
missing. The VM kit uses external baseline QCOW2 images and disposable overlays;
inspect its configured state directory for `target01-baseline.qcow2` and
`target02-baseline.qcow2`, then use the documented `restore` workflow. Rebuild
only after the provisioning artifacts, external baselines, and VM-kit
verification have actually been checked and found unusable.

A previous investigation reported rebuild blockers because it used the NCPA
deployment key, checked only libvirt-managed snapshots, and did not first inspect
the existing provisioning artifacts. Subsequent checks confirmed that the
dedicated key works on both guests, both guests have isolated routes and expected
listeners, and both external baseline images exist. No rebuild is required.

Nagios reload also requires a reviewed sudoers rule for the application account
and for whichever account invokes the harness reload. Permit exactly the
resolved absolute equivalent of `/usr/bin/systemctl reload nagios`; do not grant
wildcards, unrestricted `systemctl`, or a shell. Validate every sudoers change
with `visudo`.

## Mandatory tester handoff

Complete this gate before the AI initializes a run or conducts discovery.

1. Preview the privileged host preparation:

   ```bash
   bash provision/prepare_test_host.sh
   ```

   Review the printed accounts, paths, libvirt names, state directory, and
   sudoers destination. Override a value with the documented command-line
   option when the installed lab differs.

2. Apply and verify the preparation as an administrator:

   ```bash
   sudo bash provision/prepare_test_host.sh --apply
   ```

   The script applies only the documented ACLs and exact-command temporary
   reload rule, prepares protected runtime paths, starts the existing libvirt
   resources, and runs Nagios/manifest/isolation/VM-kit validation. It refuses
   missing or extra guest interfaces and does not create a second lab.

   It deliberately does not install missing plugins, create VMs, source
   credentials as root, run discovery, reload Nagios, change guest services,
   create the temporary NCPA bootstrap account, or modify application data.
   Those remain reviewed tester/AI steps.

   After initial preparation, the tester can re-run validation without
   reapplying ACLs or startup actions. VM verification may refresh its sanitized
   inventory evidence:

   ```bash
   sudo bash provision/prepare_test_host.sh --check
   ```

3. Review the resulting `config/lab.json`:

   - keep `10.0.2.0/28` only after its isolation check succeeds;
   - do not configure or scan `192.168.130.0/28`;
   - set `output_root` to `/home/paeng/pinpoint-test-results`;
   - confirm the Pinpoint API URL;
   - confirm `/opt/pinpoint/Network-Diagnosis-System/server/system.db`, or use
     the actual absolute database path if this installation differs;
   - leave the three credential fields as environment-variable names.

4. Populate `~/.config/pinpoint-tests/lab.env` privately if the script created
   it empty. Then hand control to the AI, which sources the protected
   environment and runs preflight:

   ```bash
   cd /opt/pinpoint/Network-Diagnosis-System/server/tests/e2e/network_discovery
   set +x
   source ~/.config/pinpoint-tests/lab.env

   /opt/pinpoint/venv/bin/python runner/run_tests.py \
     --config config/lab.json preflight
   ```

Preflight runs the tools it reports on: `nmap_sudo` executes
`/usr/local/bin/nmap-sudo --version` as the current account (a wrapper that exists
but is not executable by this user fails), and `ssh` logs in to every target with
the key named by `ssh_key_env`, using strict host-key checking against the
`known_hosts` file stored next to that key. A rejected key therefore fails
preflight instead of surfacing later.

Before preflight, check that `config/lab.json` matches this installation: the
`pinpoint.base_url` of the running backend (a `flask run` session listens on
port 5000, not necessarily the example value), the real `databases.system` path,
and an `output_root` under the account that runs the harness.

`vm_scripts/provision_lab.py verify` talks to libvirt (`qemu:///system`). Run it
as an account in the `libvirt` group, or use passwordless sudo for that one
command; it cannot answer a sudo password prompt. After restoring baseline
overlays, re-authorize the dedicated test key on the guests if it is not baked
into the baseline images, then rerun `verify`.

Every preflight value except the informational network and empty
`missing_environment` list must indicate success. On failure, stop and report
the sanitized check output. When all checks pass, tell the tester the lab is
ready and wait for an explicit instruction to resume. The later run may then
verify backups, conduct discovery, inspect and validate generated configuration,
and test application, failure, recovery, and rollback.

## Review and self-test

Harness self-tests use only the Python standard library and therefore work even
when the installed application environment does not contain pytest. From
`server/`:

```bash
.venv/bin/python -m py_compile \
  tests/e2e/network_discovery/runner/*.py \
  tests/e2e/network_discovery/services/*.py \
  tests/e2e/network_discovery/provision/*.py \
  tests/e2e/network_discovery/cleanup/*.py

<test-python> tests/e2e/network_discovery/harness_tests.py -v
```

`harness_tests.py` is intentionally not named `test_*.py`, so the live-harness
self-tests run only when explicitly selected. Passing them does not replace the
focused application regression gate, which still requires the pinned packages
from `requirements-test.txt`.

### Isolated pytest dependencies

Do not modify the application environment merely to add test tools. If pytest
is absent, install the pinned test requirements into a separate writable
directory. The helper is preview-only unless `--apply` is supplied.

With an offline wheelhouse:

```bash
python provision/install_test_dependencies.py \
  --python /opt/pinpoint/venv/bin/python \
  --target ~/pinpoint-test-work/test-deps \
  --wheelhouse /path/to/wheelhouse

python provision/install_test_dependencies.py \
  --python /opt/pinpoint/venv/bin/python \
  --target ~/pinpoint-test-work/test-deps \
  --wheelhouse /path/to/wheelhouse --apply
```

When network and DNS access have been explicitly approved, replace
`--wheelhouse ...` with `--allow-network`. Then run the focused tests with:

```bash
PYTHONPATH="$HOME/pinpoint-test-work/test-deps" \
  /opt/pinpoint/venv/bin/python -m pytest <focused-test-files> -v
```

If neither network access nor compatible offline wheels are available, record
REG-01 as blocked; do not silently skip it.

## Execution

Do not enter this section until every step in **Mandatory tester handoff** has
passed and the tester has explicitly instructed the AI to resume. Preflight is
read-only but still requires successful interface inspection, Nagios execution
and configuration access, systemd service access, API authentication, database
visibility, and the configured SSH-key reference. A mere file or command
presence is not considered a pass.

Create a result run and note the printed run ID:

```bash
python runner/run_tests.py --config config/lab.json init-run
```

After target provisioning and review, run discovery. `--apply-settings` is an
explicit authorization to replace Pinpoint's Discovery Settings with the
approved manifest values:

```bash
python runner/run_tests.py \
  --config config/lab.json \
  --cases config/plugin-cases.json \
  discover --run-id <run-id> --apply-settings
```

Discovery now requires a non-empty reviewed case manifest. It resolves each
unique plugin by exact inventory name, calls `/api/plugin/<id>/enable`, and
verifies Enabled/Active before scanning. Missing plugins or enable failures stop
the scan. `evidence/plugin-enabling.json` records safe IDs and before/after states;
Repeated discovery appends enable evidence so the original states remain available
for cleanup. `inventory-before-discovery.json` separates retained baseline data from newly
unexpected rows. This is test setup through the real API, not proof that the
product enforces Plugin Manager disable on discovery-generated checks.

The `PM-ENABLE-APPLY` service case also applies `check_dummy` to an existing target
through `/configurations`, verifies Applied and `/running`, and waits for an
executed healthy check. `apply_monitoring` requires an exact service description;
use a unique test-owned description to avoid colliding with discovery services.
Review the existing default command first; the harness never overwrites it.
No missing inventory/permission fixtures or guest permission/restart repairs may
be introduced to turn failed acceptance into a pass.

Validate Nagios. Add `--reload` only after reviewing the live configuration:

```bash
python runner/run_tests.py \
  --config config/lab.json \
  nagios-check --run-id <run-id>
```

Run one reviewed failure/recovery case at a time:

```bash
python runner/run_tests.py \
  --config config/lab.json \
  --cases config/plugin-cases.json \
  service-case --run-id <run-id> --case-id PLG-HTTP
```

Service polling normalizes state labels and rejects unexecuted checks. Stop and
recovery require new execution timestamps. UNKNOWN is not an accepted normal
outage result. NCPA CPU, memory and disk are separate cases; a prefix match must
be checked against the complete expected runtime metric set in NCPA-04. Every service case requires `expected_check_command`. The harness reads the
configured Nagios `status_file` and verifies the loaded command, execution time
and state against Pinpoint for healthy, failed and recovered phases. Generic TCP
fallbacks cannot pass a MySQL/NCPA-specific case. Runtime command arguments are
never exported. Verify executable definitions separately during CFG/MON object
inspection.

Enabling/application changes require cleanup in addition to restarting guest
units. Before execution, approve and preserve application/Nagios baselines;
afterward restore the prior plugin states and remove only configurations created
by the run using the reviewed recovery procedure, validate Nagios and verify
runtime objects. `restore_lab.py` only starts remote units; it does not restore
plugin states or configurations. No automatic DB restoration is implemented.

If a run is interrupted, restore every allow-listed unit from the manifest:

```bash
python cleanup/restore_lab.py \
  --config config/lab.json \
  --cases config/plugin-cases.json --dry-run

python cleanup/restore_lab.py \
  --config config/lab.json \
  --cases config/plugin-cases.json
```

Generate the Markdown/CSV report and checksums:

```bash
python runner/run_tests.py \
  --config config/lab.json \
  finalize --run-id <run-id>
```

## Runtime outputs

The harness will write outside the repository by default:

```text
~/pinpoint-test-results/<run-id>/
```

The final report and sanitized evidence will be retrieved with SCP. Passwords,
tokens, private keys, session cookies, SNMP communities, VM disks, and real lab
configuration files must never be committed.

From the physical host:

```bash
scp -r <vm-user>@<vm-address>:~/pinpoint-test-results/<run-id> ./
```

Keep the in-VM copy until the retrieved checksums have been verified.
