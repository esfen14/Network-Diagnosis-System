# Network Discovery and Extended Nagios Service Test Plan

**Status:** Draft for review
**Test level:** Live Tier 2 Extended
**Target environment:** One VirtualBox VM with 8 vCPUs, 12 GB RAM, and
80 GB storage
**Result retrieval:** SCP

## 1. Purpose

This plan verifies that Pinpoint can discover hosts and their services, build
and safely apply Nagios monitoring configuration, receive live Nagios results,
and display service failures and recoveries. It also exercises additional
Nagios plugins that can be tested safely within the available lab resources.

Tier 1 Plugin Manager inventory testing has already been completed and is not
repeated here. This plan focuses on live behavior.

## 2. Objectives

The test must determine whether Pinpoint can:

- Discover only the expected hosts on an isolated network.
- Detect TCP and UDP services and associate them with the correct host.
- Avoid duplicate records after an unchanged rescan.
- Add newly opened services and remove stale services on a rediscovered host.
- Generate, validate, back up, and safely apply Nagios configuration.
- Display Nagios checks and state changes through Pinpoint.
- Add monitoring through Plugin Manager where the plugin contract supports it.
- Deploy and monitor NCPA after explicit SSH fingerprint confirmation.
- Monitor SNMP without exposing its community string.
- Recover from invalid configuration and Nagios reload failures.
- Produce a sanitized Markdown report and evidence bundle for SCP retrieval.

## 3. Scope

### 3.1 Included

- Discovery Settings validation and concurrency control.
- Discovery start, status polling, cancellation, and repeated scans.
- Real `nmap` scans against an isolated lab subnet.
- All active Network Discovery plugin mappings.
- Generic TCP fallback and unsupported UDP skipped-service behavior.
- Nagios candidate generation, validation, backup, apply, reload, and rollback.
- Nagios and Pinpoint service visibility.
- Controlled service failure and recovery.
- NCPA deployment and CPU, memory, and disk checks.
- SNMP OID checks.
- Practical network, database, directory, file, sharing, and local plugins.
- Authentication, authorization, and secret-exposure checks.
- Automated evidence collection, Markdown reporting, and SCP retrieval.

### 3.2 Previously verified

- Plugin directory scanning and inventory visibility (Tier 1).

The live run may confirm that required executables still exist, but it must not
repeat the complete Tier 1 suite.

### 3.3 Excluded

Unless the required real infrastructure is available, the following are out of
scope:

- Windows-only checks.
- Oracle, UPS, physical printer, and FlexLM checks.
- Physical sensor and SMART checks that the VM cannot expose faithfully.
- DHCP checks that could interfere with the lab network.
- Production systems and production network ranges.
- Networks larger than the isolated test subnet.
- Large-scale load and topology testing.

An unavailable prerequisite is reported as **Not Applicable**, not as a product
failure.

## 4. Lab architecture

Pinpoint and Nagios run directly in the main VirtualBox VM. The AI test runner
also runs there and creates two isolated targets.

```text
VirtualBox VM (8 vCPU, 12 GB RAM, 80 GB disk)
|-- Pinpoint, Nagios, databases, and AI test runner
|-- target01: application, database, directory, and NCPA services
`-- target02: DNS, NTP, SNMP, lifecycle, and network-failure tests
```

### 4.1 Resource allocation

| Component | Planned RAM |
|---|---:|
| Main OS, Pinpoint, Nagios, and test runner | 6-7 GB |
| `target01` | 1.5-2 GB |
| `target02` | 1-1.5 GB |
| Safety reserve | Approximately 2 GB |

KVM/libvirt is preferred when `/dev/kvm` is available. Incus/LXC or Docker
containers with dedicated addresses are acceptable fallbacks. `target01`
should be a full VM when possible for SSH fingerprint and NCPA deployment
testing.

Before provisioning, verify that VirtualBox is exposing nested virtualization
and that the invoking account can use the system libvirt connection:

```bash
virsh -c qemu:///system list --all
sudo virt-host-validate
virsh -c qemu:///system net-list --all
```

The QEMU hardware-virtualization, `/dev/kvm`, `/dev/vhost-net`, and
`/dev/net/tun` checks must pass. IOMMU and secure-guest warnings do not block
this lab because it does not use device passthrough or encrypted guests. LXC
controller failures do not block the run when QEMU/KVM is the selected backend.
An empty domain list is expected before the disposable targets are created.
Use `qemu:///system` consistently; do not accidentally provision into the
invoking user's separate `qemu:///session` connection.

### 4.2 Network

The approved isolated network for this installation is `10.0.2.0/28`:

| Address | System |
|---|---|
| `10.0.2.1` | Pinpoint and Nagios |
| `10.0.2.2` | `target01` |
| `10.0.2.3` | `target02` |

A management/NAT interface may be used to install packages. Network Discovery
must be configured only for the isolated subnet and must never scan the
management or production network.

The main VirtualBox VM uses its VirtualBox NAT adapter for internet access. The
nested targets each initially use two libvirt interfaces:

- the active libvirt `default` NAT network, using DHCP, for package downloads;
- an isolated libvirt network, with static lab addresses and no default gateway
  or DNS route.

The provisioning workflow must remove the nested targets' temporary NAT
interfaces after package installation and before discovery. Pinpoint retains
internet access through the outer VirtualBox NAT adapter, while discovery is
restricted to the isolated libvirt bridge.

Read-only interface and route inspection must still prove that `10.0.2.0/28`
belongs only to the disposable libvirt lab before every run. The management
network overlaps `192.168.130.0/28`, so the tester must not configure or scan
that range. Never assume that a private address is isolated merely because it
is private. Any future subnet change requires a new documented isolation
review and corresponding updates to both lab manifests.

## 5. Target services

### 5.1 `target01`

| Port | Protocol | Service |
|---:|---|---|
| 21 | TCP | FTP |
| 22 | TCP | SSH |
| 25 | TCP | SMTP |
| 80 | TCP | HTTP |
| 443 | TCP | HTTPS |
| 3306 | TCP | MariaDB/MySQL |
| 5693 | TCP | NCPA |
| 9000 | TCP | Unknown/custom listener for generic TCP fallback |

Enable these heavier services only during their test profile:

- PostgreSQL.
- OpenLDAP and LDAPS.
- Samba.
- RPC.
- Optional RADIUS.

Attach a small secondary disk when possible to exercise NCPA partition checks.

### 5.2 `target02`

| Port | Protocol | Service |
|---:|---|---|
| 53 | TCP | DNS |
| 53 | UDP | DNS |
| 123 | UDP | NTP |
| 161 | UDP | SNMP |
| 69 or 514 | UDP | Unsupported service for skipped-service testing |

Reuse this target for ICMP blocking, firewall changes, shutdown/restart, and
host-retention testing.

## 6. Service profiles

To remain within the memory limit, do not run every heavy service at once.

### Profile A: core discovery

- FTP, SSH, SMTP, HTTP, HTTPS, MariaDB, and NCPA.
- DNS, NTP, and SNMP.
- Custom TCP and unsupported UDP listeners.

### Profile B: extended protocols

Stop unnecessary Profile A services before enabling PostgreSQL, OpenLDAP,
LDAPS, Samba, RPC, and optional RADIUS.

### Profile C: monitoring-server checks

Run safe local checks on the Pinpoint/Nagios server. Place their temporary
Nagios definitions in a dedicated test file and remove it during cleanup.

## 7. Plugin coverage

### 7.1 Required Network Discovery mappings

| Plugin/check | Live service |
|---|---|
| `check_tcp` | TCP 9000 custom listener |
| `check_ssh` | OpenSSH |
| `check_ftp` | FTP server |
| `check_smtp` | SMTP server |
| `check_http` | HTTP and HTTPS |
| `check_mysql` | MariaDB/MySQL |
| `check_dns` | DNS over TCP and UDP |
| `check_ntp_time` | NTP |
| `check_snmp` | SNMP |
| `check_ncpa` | NCPA CPU, memory, and disk |

Unknown UDP must be recorded as skipped; Network Discovery intentionally does
not create an unreliable generic UDP check for it.

### 7.2 Additional network plugins

Test these when the executable and safe prerequisites are available:

- `check_ping`, `check_fping`, and `check_icmp`.
- `check_dig`.
- `check_ntp_peer` and `check_time`.
- `check_ssl_validity`.
- `check_by_ssh`.
- `check_rpc`.

### 7.3 Database and directory plugins

- `check_mysql_query` using a read-only account and query.
- `check_pgsql` using a small test database.
- `check_dbi` when its driver is installed.
- `check_ldap` and `check_ldaps` against a test directory.

### 7.4 File, mail, and sharing plugins

- `check_disk_smb` against a read-only test share.
- `check_mailq` against the test SMTP queue.
- `check_file_age` against a dedicated test file.
- `check_log` against a dedicated test log.

### 7.5 Local monitoring-server plugins

- `check_apt`, `check_disk`, `check_load`, and `check_procs`.
- `check_swap`, `check_users`, `check_uptime`, and `check_nagios`.
- `check_file_age`, `check_log`, `check_mailq`, and `check_dummy`.

`check_dummy` must exercise OK, WARNING, CRITICAL, and UNKNOWN without causing
a real outage. Local checks must be labeled as monitoring-server checks and
must not be misleadingly attributed to a remote target.

### 7.6 Optional plugins

Run `check_radius`, `check_ircd`, `check_real`, or `check_game` only after all
required cases pass and sufficient time, memory, and dependencies remain.

## 8. Preconditions

- Pinpoint and Nagios are installed and operational.
- The required plugin executables are present.
- The harness standard-library self-tests pass with the installed interpreter.
- The pinned pytest dependencies are available either through an isolated
  writable directory or a reviewed offline wheelhouse; absence blocks REG-01.
- The application databases are backed up or disposable.
- The AI has controlled administrative access inside the lab.
- The execution context permits read-only interface/route inspection, Nagios
  validation, configuration reads, and systemd status checks.
- `/usr/local/bin/nmap-sudo` works with the application's privileges.
- Nagios validation and non-interactive reload are available.
- Test users and permissions exist.
- Target packages and static addresses are configured.
- The test subnet is isolated from production.
- A usable disposable-target backend or two pre-provisioned targets exist.
- The configured user-relative evidence directory is writable.
- Baseline Nagios configuration hashes and VM snapshots exist.
- Secrets are stored outside source control.

### 8.1 Test credential environment

Create a user-only environment file outside the repository. The `install`
command below is for first-time creation; do not rerun it over an existing file
because doing so would truncate the saved values.

```bash
mkdir -p ~/.config/pinpoint-tests
chmod 700 ~/.config/pinpoint-tests
test -e ~/.config/pinpoint-tests/lab.env || \
  install -m 600 /dev/null ~/.config/pinpoint-tests/lab.env
chmod 600 ~/.config/pinpoint-tests/lab.env
nano ~/.config/pinpoint-tests/lab.env
```

Store only the runtime exports in that file:

```bash
export PINPOINT_TEST_EMAIL='your-test-account-email'
export PINPOINT_TEST_PASSWORD='your-test-account-password'
export PINPOINT_TEST_SSH_KEY='/opt/pinpoint/Network-Diagnosis-System/.cache/pinpoint-live-test-access/test_key'
```

The AI sources the file into the same shell that invokes the harness, with shell
tracing disabled so values are not echoed:

```bash
set +x
source ~/.config/pinpoint-tests/lab.env
```

`config/lab.json` must contain the environment-variable names, never these
values. The environment file must remain outside Git and must not be copied into
the result bundle.

### 8.2 Nagios and NCPA SSH access for the test operator

The harness must be able to execute Nagios validation and use its check-result
spool. Grant only the required access to the test account (`paeng` in this lab):

```bash
sudo setfacl -m u:paeng:rx /usr/local/nagios/bin/nagios
sudo setfacl -m u:paeng:rwx /usr/local/nagios/var/spool/checkresults
sudo setfacl -m u:paeng:r /usr/local/nagios/etc/resource.cfg
```

If `setfacl` is unavailable, install the operating system's `acl` package first.
Verify the resulting entries without printing any credentials:

```bash
getfacl /usr/local/nagios/bin/nagios
getfacl /usr/local/nagios/var/spool/checkresults
getfacl /usr/local/nagios/etc/resource.cfg
/usr/local/nagios/bin/nagios -v /usr/local/nagios/etc/nagios.cfg
```

Do not recursively grant access to the whole Nagios installation. Do not print,
copy, or include `resource.cfg` in evidence because it may contain secret macro
values. Reload access must remain a separately reviewed, non-interactive
administrative capability.
The application account needs permission for exactly:

```text
/usr/bin/systemctl reload nagios
```

The sudoers entry must use the resolved absolute `systemctl` path, be validated
with `visudo`, and must not grant a shell, wildcard service names, or unrestricted
`systemctl` access. The account running `nagios-check --reload` needs the same
exact capability.

The test account also needs traversal access to the application SSH directory
and read access to the existing NCPA deployment key:

```bash
sudo setfacl -m u:paeng:x /opt/pinpoint/.ssh
sudo setfacl -m u:paeng:r /opt/pinpoint/.ssh/pinpoint_ncpa_deploy
getfacl /opt/pinpoint/.ssh
getfacl /opt/pinpoint/.ssh/pinpoint_ncpa_deploy
```

Do not grant directory listing or write access, and never print, copy, checksum,
or include the private key in test evidence. The NCPA deployment key is not the
VM provisioning/test identity and must not be assigned to
`PINPOINT_TEST_SSH_KEY` for this lab. Use the retained dedicated test key and its
pinned `known_hosts` file for harness access to the `pinpoint-test` accounts.

### 8.3 Mandatory tester handoff before discovery

The tester must complete this gate before asking the AI to conduct the live
run. Preview the consolidated privileged preparation first:

```bash
cd /opt/pinpoint/Network-Diagnosis-System/server/tests/live_network_discovery
bash provision/prepare_test_host.sh
```

After reviewing every printed account, path, libvirt name, and destination, the
tester applies it:

```bash
sudo bash provision/prepare_test_host.sh --apply
```

The script consolidates the approved ACLs, exact-command temporary Nagios reload
rule, protected environment/config/result paths, existing libvirt network and
domain startup, Nagios validation, interface isolation checks, and VM-kit
verification. It is idempotent for resources that are already active and
refuses to continue when a guest has an extra interface or the reviewed VM state
is unavailable.

The script must not install missing plugins, create VMs, read credentials or
private-key contents, run discovery, reload Nagios, change guest services,
create NCPA bootstrap credentials, or modify application data. Those actions
remain separate and require their applicable review.

Review `tests/live_network_discovery/config/lab.json` against the running lab:

- keep the verified isolated `10.0.2.0/28` network;
- never scan `192.168.130.0/28`, because it overlaps the management network;
- set `output_root` to `/home/paeng/pinpoint-test-results`;
- confirm `http://127.0.0.1:5000` or replace it with the actual Pinpoint API URL;
- confirm the absolute system database path, normally
  `/opt/pinpoint/Network-Diagnosis-System/server/system.db` for this install;
- keep `PINPOINT_TEST_EMAIL`, `PINPOINT_TEST_PASSWORD`, and
  `PINPOINT_TEST_SSH_KEY` as environment-variable references, not secret values.

Finally run the read-only preflight from the installed clone:

```bash
cd /opt/pinpoint/Network-Diagnosis-System/server/tests/live_network_discovery
set +x
source ~/.config/pinpoint-tests/lab.env

/opt/pinpoint/venv/bin/python runner/run_tests.py \
  --config config/lab.json preflight
```

All preflight checks must report success. If any check fails, stop and return
the sanitized failure details to the tester; do not initialize a run or start
discovery. Once every check passes, the AI must tell the tester it is ready and
wait for an explicit instruction to resume. Only then may it verify the lab and
backups, run discovery, inspect and validate generated configuration, and test
application, failure, recovery, and rollback.

## 9. Automation requirements

The live harness under `tests/live_network_discovery/` must be manifest-driven.
Each case should define its test ID, plugin, target, setup, failure, recovery,
expected Nagios and Pinpoint states, timeout, and evidence destinations.

The runner must:

1. Verify prerequisites and network scope before making changes.
2. Apply one controlled action at a time.
3. Poll Nagios locally until the expected state or a bounded timeout.
4. Query Pinpoint after Nagios reaches the expected state.
5. Write verbose output to evidence files.
6. Return a short machine-readable result to the AI.
7. Restore the service before continuing.
8. Support resuming a run and selecting an individual case.

Scripts must be idempotent, must not contain secrets, and must clean up only
resources they created. Every disruptive action needs a corresponding recovery
action.

## 10. Execution stages

### Stage A: isolated regression gate

Run the focused pytest modules for Network Discovery, Discovery Settings, host
configuration, plugin registry, skipped services, Plugin Manager monitoring
configuration, and NCPA. A critical regression blocks the live run unless the
user approves an exception.

### Stage B: provision and inventory

Complete the mandatory tester handoff, start the existing isolated network and
targets, then use the reviewed scripts under
`tests/live_network_discovery/vm_scripts/` to verify their ownership and state.
Do not create a second lab. Confirm Profile A, removal of temporary guest NAT
adapters, actual listening ports and routes, isolation, pinned SSH trust, and
external baseline QCOW2 images. An empty `virsh snapshot-list` does not establish
that those baselines are missing. Do not begin discovery until the kit's
`verify` command and the harness preflight both succeed and the tester explicitly
says to resume.

### Stage C: core discovery

Configure the `/28` network and a short explicit port list, start discovery,
poll to completion, and compare database results with the target manifest.

### Stage D: Nagios application

Inspect the candidate, run `nagios -v`, confirm backup creation, apply it,
verify the reload exit status, and confirm Nagios remains active with the
expected runtime objects.

### Stage E: Pinpoint visibility and state transitions

For each required mapping, verify Nagios and Pinpoint visibility, stop the real
service, observe the non-OK state, restore it, and observe recovery.

### Stage F: extended plugins

Run Profiles B and C after all core cases pass. Stop optional expansion if
resources, time, or the AI token budget approaches its limit.

### Stage G: rescan and failure handling

Exercise unchanged scans, added and closed services, filtering, target
shutdown, cancellation, invalid candidates, reload failure, and recovery to
the last-known-good configuration.

### Stage H: report and cleanup

Restore services and firewall rules, remove temporary test objects, validate
Nagios one final time, sanitize the evidence, generate checksums and the
Markdown report, then prepare it for SCP retrieval.

## 11. Core test cases

| ID | Test | Expected result |
|---|---|---|
| ENV-01 | Verify CPU, RAM, disk, and backend | Minimum lab requirements are met |
| ENV-02 | Verify network isolation | Only the isolated subnet can be scanned |
| ENV-03 | Capture target listeners | Actual listeners match the manifest |
| REG-01 | Run focused pytest gate | Required isolated tests pass |
| DS-01 | Save valid discovery settings | Values are stored and used by the next scan |
| DS-02 | Submit unsafe network/port input | Input is rejected before reaching `nmap` |
| DS-03 | Edit settings during discovery | Update is rejected while the scan is active |
| ND-01 | Start discovery | Scan starts and reports progress |
| ND-02 | Start a concurrent scan | Second request is rejected |
| ND-03 | Discover both targets | Exact expected host set is stored |
| ND-04 | Verify TCP services | Ports belong only to their owning host |
| ND-05 | Verify UDP services | DNS, NTP, and SNMP are detected correctly |
| ND-06 | Discover DNS over TCP and UDP | Unique service descriptions are generated |
| ND-07 | Discover TCP 9000 | Generic TCP monitoring is generated |
| ND-08 | Discover unsupported UDP | A skipped-service record is created |
| ND-09 | Repeat an unchanged scan | No duplicate hosts or services are created |
| ND-10 | Cancel a scan | Status becomes `Interrupted` and keeps progress |
| ND-11 | Close a port and rescan | The stale service is removed for that host |
| ND-12 | Open a new port and rescan | The new service is added |
| ND-13 | Shut down a complete target | Result matches the approved retention policy |
| CFG-01 | Validate the candidate | `nagios -v` returns success |
| CFG-02 | Apply the candidate | Backup exists, reload succeeds, Nagios stays active |
| CFG-03 | Supply an invalid candidate | Live configuration remains unchanged |
| CFG-04 | Force reload failure | Last-known-good configuration is restored |
| MON-01 | Inspect Nagios objects | Expected hosts and services are loaded |
| MON-02 | Inspect Pinpoint services | Expected services are visible through the API/UI |
| MON-03 | Stop each required service | Matching check becomes non-OK |
| MON-04 | Restore each required service | Matching check returns to OK |
| PM-01 | Apply an enabled plugin | Configuration becomes `Applied` |
| PM-02 | Apply one plugin to multiple targets | Existing configurations are preserved |
| PM-03 | Reapply the same target | Configuration updates without duplication |
| PM-04 | Apply a disabled plugin | Operation is rejected |
| PM-05 | Force plugin validation failure | Live plugin config remains safe |
| NCPA-01 | Fetch and confirm SSH fingerprint | Trust is stored only after confirmation |
| NCPA-02 | Change the fingerprint | Deployment is blocked |
| NCPA-03 | Deploy NCPA | Agent becomes reachable |
| NCPA-04 | Generate metrics | CPU, memory, and disk checks belong to `target01` |
| SNMP-01 | Query configured OIDs | Expected SNMP services are generated |
| SNMP-02 | Use an incorrect community | Check fails without exposing the secret |
| AUTH-01 | Use an unauthorized user | Protected operations are forbidden |
| AUTH-02 | Exercise the stop permission | Result matches the approved permission contract |
| SEC-01 | Inspect logs, responses, and snapshots | No secrets are exposed |
| CLEAN-01 | Restore the baseline | Lab and Nagios return to a valid state |

## 12. Extended plugin acceptance standard

Each extended plugin receives, when practical:

1. Executable and dependency validation.
2. Valid Nagios configuration.
3. A successful live execution.
4. Visibility in Nagios.
5. Visibility in Pinpoint.
6. One controlled failure.
7. Recovery after restoring the dependency.

OK, WARNING, CRITICAL, and UNKNOWN are required for `check_dummy` and for safe
threshold-based checks such as disk, load, processes, file age, ping, and NCPA.
Other plugins require at least OK, failure, and recovery.

## 13. Results and evidence

Each run writes to:

```text
~/pinpoint-test-results/<run-id>/
|-- Network_Discovery_Extended_Test_Report.md
|-- checksums.sha256
`-- evidence/
    |-- environment.md
    |-- target-manifest.yaml
    |-- automated-tests.txt
    |-- discovery-settings.json
    |-- discovery-status.json
    |-- discovered-hosts.csv
    |-- discovered-services.csv
    |-- skipped-services.csv
    |-- nagios-validation.txt
    |-- nagios-runtime.json
    |-- pinpoint-services.json
    |-- plugin-results.csv
    |-- config-diffs/
    |-- sanitized-logs/
    `-- screenshots/
```

The report must identify the tested commit, environment, resource use, target
inventory, execution time, discovery results, plugin results, failure/recovery
results, security findings, defects, exclusions, and final recommendation.

Its main result table is:

| Test ID | Plugin/service | Target | Discovered | Config valid | Nagios visible | Pinpoint visible | Failure detected | Recovery detected | Result |
|---|---|---|---|---|---|---|---|---|---|

Valid result labels are **Pass**, **Fail**, **Blocked**, **Not Applicable**,
**Skipped due to resource limit**, and **Previously verified**.

## 14. SCP retrieval

Retrieve a complete run from the physical host with:

```bash
scp -r <vm-user>@<vm-address>:~/pinpoint-test-results/<run-id> ./
```

Retrieve only the Markdown report with:

```bash
scp <vm-user>@<vm-address>:~/pinpoint-test-results/<run-id>/Network_Discovery_Extended_Test_Report.md ./
```

Before export, redact passwords, session cookies, NCPA tokens, SNMP community
strings, private keys, and secret environment values. Do not export raw
databases unless the user explicitly requests them. Generate SHA-256 checksums,
and retain the in-VM copy until the user confirms successful retrieval.

## 15. Pass, fail, and exit rules

A live service passes only when the target listener, discovery database,
generated configuration, Nagios runtime, and Pinpoint result agree. An API
success response alone is insufficient.

The run is complete when:

- Every required case and active discovery mapping has a recorded result.
- Required failure, recovery, validation, rollback, and secret checks pass or
  have a user-approved exception.
- Nagios remains operational and the lab is restored.
- The sanitized report and evidence are generated with checksums.
- The user successfully retrieves the results through SCP.

## 16. Known implementation risks to test early

- The discovery stop route currently differs from the seeded discovery
  permission.
- New Linux-host persistence may reference the SSH port before it is assigned.
- Rediscovered Linux devices may lose NCPA eligibility.
- A nonzero Nagios reload may be logged without failing the apply operation.
- A completely missing host may remain monitored after a later scan.

When confirmed, these are product defects rather than lab-environment failures.
