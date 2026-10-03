# Live Network Discovery Harness

This directory contains the opt-in scripts, manifests, safety checks, service
controls, and reporting code used to execute
[`../NETWORK_DISCOVERY_EXTENDED_TEST_PLAN.md`](../NETWORK_DISCOVERY_EXTENDED_TEST_PLAN.md).

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
live_network_discovery/
|-- README.md
|-- config/
|   |-- lab.example.json
|   `-- plugin-cases.example.json
|-- provision/
|   `-- detect_backend.py
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

Guest/network creation remains environment-specific because VirtualBox may or
may not expose KVM. `detect_backend.py` reports whether KVM/libvirt, Incus/LXC,
or Docker is available; the executing AI must provision the two targets using
the approved available backend, then record that choice in the report.

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
cd server/tests/live_network_discovery
cp config/lab.example.json config/lab.json
cp config/plugin-cases.example.json config/plugin-cases.json
```

The harness accepts only a canonical private IPv4 network of `/28` or smaller.
Every target and the Pinpoint test address must be unique members of that
network. The real `lab.json`, private keys, and results are ignored by Git.

Credentials are read only from the environment variables named by `lab.json`:

```bash
export PINPOINT_TEST_EMAIL='test-admin@example.invalid'
export PINPOINT_TEST_PASSWORD='replace-at-runtime'
export PINPOINT_TEST_SSH_KEY='/absolute/path/to/lab-only-key'
```

Do not place the actual values in JSON, shell history, test evidence, or source
control. Pre-populate `known_hosts` for each target and verify its fingerprint;
remote service control uses strict host-key checking.

## Review and self-test

From `server/`:

```bash
.venv/bin/python -m py_compile \
  tests/live_network_discovery/runner/*.py \
  tests/live_network_discovery/services/*.py \
  tests/live_network_discovery/provision/*.py \
  tests/live_network_discovery/cleanup/*.py

.venv/bin/python -m pytest \
  tests/live_network_discovery/harness_tests.py -q
```

`harness_tests.py` is intentionally not named `test_*.py`, so the live-harness
self-tests run only when explicitly selected.

## Execution

Run the read-only checks first:

```bash
cd server/tests/live_network_discovery
python provision/detect_backend.py
python runner/run_tests.py --config config/lab.json preflight
```

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
  discover --run-id <run-id> --apply-settings
```

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
/home/tester/pinpoint-test-results/<run-id>/
```

The final report and sanitized evidence will be retrieved with SCP. Passwords,
tokens, private keys, session cookies, SNMP communities, VM disks, and real lab
configuration files must never be committed.

From the physical host:

```bash
scp -r testuser@<vm-address>:/home/tester/pinpoint-test-results/<run-id> ./
```

Keep the in-VM copy until the retrieved checksums have been verified.
