# Live Test Remediation Plan

Source: `REPORT.md` (extended live network discovery test, 2026-10-03, commit `a7b12bba`).
Result was **FAIL**: 31 Pass / 8 Fail / 4 Blocked. The 8 failures and 4 blocks
trace to four product defects, two test-plan/spec gaps, and one test-fixture gap.

Status: **draft; all questions answered, decisions recorded in §9.**

## 1. Summary of work

| # | Item | Type | Severity | Report cases |
|---|---|---|---|---|
| A | Plugin Manager reload failure reported as success | Product defect | High | CFG-04 |
| B | NCPA TLS key unreadable by the `nagios` user | Product defect | High | NCPA-03, MON-01/03/04 |
| C | NCPA disk checks use invalid partition paths | Product defect | High | NCPA-04, MON-01/03/04 |
| D | `system.hosts.edit` missing from installed DB | Upgrade/seed defect | High | port promotion 400s |
| E | Service naming is inconsistent | Product change | Medium | ND-06 and all service rows |
| F | Test plan disagrees with approved lifecycle behavior | Spec/test-plan gap | Medium | ND-03, ND-11, ND-13, ND-07 |
| G | No protocol-faithful unsupported-UDP fixture | Test gap | Low | ND-08 |
| H | Live-daemon rollback and Network Discovery `copystat` EPERM | Hardening | Medium | CFG-04 |

Recommended order: **D → A → E → B → C → H → F → G → re-run.** D is first because
it blocks the UI promotion workflow in every environment; A is a small, isolated
fix; E touches names that B/C also generate, so it lands before them.

## 2. Service naming standard (item E)

### Required format

```
{service}-{port number}-{protocol}
```

Examples: `ssh-22-tcp`, `http-80-tcp`, `dns-53-tcp`, `dns-53-udp`, `ntp-123-udp`,
`snmp-161-udp`, `tcp-9000-tcp`.

### Current behavior (from `create_host_cfg.py`)

- `finalize_service_names()` emits the bare base name (`ssh`, `http`, `ncpa`) and
  appends `-TCP`/`-UDP` **only** when the same base name exists on both
  transports. Result: `ssh` but `dns-TCP`/`dns-UDP`; the port number is never in
  the name. (The report shows `dns-53-TCP`; confirm whether the VM ran older
  code, since current source does not add the port.)
- A numeric collision suffix (`-2`, `-3`) is added for any remaining duplicates.
- Multi-check plugins (SNMP OIDs, NCPA metrics) build names from
  `ServiceCheck.metric` in `plugin_registry.py`.
- Name parts pass through `sanitize_name_part()`.

### Target rules

1. Every generated service description is `{service}-{port}-{protocol}`; the
   suffix is always present, not only on collision.
2. `{service}` is the plugin name when a protocol plugin is used (`ssh`, `ftp`,
   `smtp`, `http`, `https`, `mysql`, `dns`, `ntp`, `snmp`, `ncpa`), otherwise the
   sanitized discovered service name, falling back to `tcp` for the generic TCP
   check. Normalized to one case (see Q1).
3. `{port}` is the actual monitored port, so a service moved to a different port
   (e.g. NCPA 5693, HTTP 9001) produces a distinct, truthful name.
4. `{protocol}` is `tcp` or `udp`.
5. Because name + port + protocol is unique per host, the `-2` collision counter
   is removed. A residual duplicate is a bug and must raise, not silently
   suffix.
6. Multi-check plugins (NCPA metrics, SNMP OIDs) use
   `{service}-{metric}-{port}-{protocol}`, e.g. `ncpa-cpu-5693-tcp`,
   `ncpa-disk_root-5693-tcp`, `snmp-uptime-161-udp` (decided, Q2). Single-check
   services keep `{service}-{port}-{protocol}`. All parts lowercase (Q1).
7. Reject any name Nagios would reject; keep the existing illegal-character
   sanitizing.

### Work items

- Rewrite `finalize_service_names()` and `plan_plugin_services()` call sites in
  `server/app/network_discovery/create_host_cfg.py` to build names from
  `(label, port, transport)`; drop the `base_name`-collision logic.
- Update the NCPA/SNMP metric naming in `plugin_registry.py`.
- Apply the same helper to Plugin Manager-generated services in
  `server/app/api/plugin/monitoring_config.py` so there is one naming function.
- Audit consumers that match on service name: `server/app/api/system/statistics.py`
  (NCPA CPU/disk/memory averages), `dashboard.py`, `network_health.py`,
  `network_services.py`, `history.py`, `report.py`, and the frontend. Replace
  name matching with `plugin`/`port`/`protocol` fields wherever possible.
- **Align every other file that mentions or depends on a service name** with the
  new format. Checklist found by searching the repo:
  - `server/config.py`: comments describe `snmp-<metric>-<port>` and
    `ncpa-<metric>-<port>`; change to `{service}-{metric}-{port}-{protocol}`.
    `AUTO_MONITOR_SERVICES`, `TCP_/UDP_SERVICE_OVERRIDES` hold the *service*
    part only (`ssh`, `http`, `ncpa`) and stay lowercase; verify nothing
    else expects the port or protocol inside those values. Note
    `UDP_SERVICE_OVERRIDES` lists ssh/http/https on UDP, which would now produce
    names like `ssh-22-udp`; review those entries.
  - `server/app/api/system/statistics.py`: matches by `check_command`
    (`check_ncpa`), not by name, so logic is safe; fix the docstring example
    `ncpa_cpu_usage-5693-TCP` and the `display_name` examples.
  - `server/app/api/plugin/service.py`: `PluginConfiguration.Service_Description`
    (search, uniqueness check in `apply_plugin_configuration`, the
    `service_description` returned to the UI) must use the shared naming helper
    and the same uniqueness rule per host.
  - `server/app/api/plugin/monitoring_config.py` (`render_service_object`) and the
    templates `service.cfg.tpl` / `muti_host_service.cfg.tpl`: they only render the
    name they are given; no change except tests.
  - `server/app/nagios/status.py` and history/alert code keyed on
    `(hostname, service_description)`: add the old-to-new name mapping used for
    regenerated hosts so history and alerts stay joined.
  - `server/app/network_discovery/plugin_registry.py`: `ServiceCheck.metric`
    naming and docstrings; `port_lifecycle.py` and `device_identity.py` where
    `Service_Name` is stored (keep `Service_Name` as the bare service part, and
    derive the full Nagios name only at config-generation time).
  - Frontend: `client/src/components/plugin-manager/RunningChecksTable.tsx`,
    `PluginTargetsSection.tsx`, `client/src/lib/pluginApi.ts`,
    `client/src/types/plugin.ts`, and the related tests, for any hard-coded
    names or placeholders.
  - Live harness: `server/tests/live_network_discovery/` (`runner/nagios.py`,
    `runner/discovery.py`, `runner/common.py`, `services/remote_service.py`)
    and the extended test plan, which look services up by name (`dns-53-TCP`,
    etc.); update expected names to the lowercase form.
  - Specs: `Display_Requirements.md`, `Backend_Modules_and_Routes.md`,
    `Data_Model_and_Integrations.md`, `Plugins_List.md`.
  - Tests with name literals: `test_create_host_cfg.py`, `test_plugin_registry.py`,
    `test_plugin_monitoring_config.py`, `test_port_lifecycle.py`,
    `test_history.py`, `test_device_config.py`, `test_statistics.py`,
    `test_dashboard.py`, `test_skipped_services.py`.
  Rule: no file builds a service name by hand; all call the one helper, and
  anything that must find a service uses plugin/port/protocol fields rather than
  parsing the name.
- **Migration:** existing hosts hold old-named services in Nagios object data and
  in history/alert records. Decide rename vs. keep history (Q3). The default
  plan: regenerate config (one reload), and keep old names in history with a
  display mapping so alert history stays continuous.
- Tests: update `test_create_host_cfg.py`, `test_network_services.py`,
  `test_statistics.py`, `test_dashboard.py`, `test_history.py`; add a naming
  test table covering every nine families, TCP/UDP pairs, a relocated port,
  and sanitizer edge cases.
- Specs: `Backend_Modules_and_Routes.md`, `Data_Model_and_Integrations.md`,
  `Display_Requirements.md` (names shown to users), `Plugins_List.md`.

## 3. Item A: Plugin Manager reload failure reported as success

**Cause** (`server/app/api/plugin/monitoring_config.py:274-289`):
`apply_plugin_services_config()` logs a nonzero `systemctl reload` exit code but
only rolls back inside `except`. A subprocess that exits nonzero does not raise,
so the function returns `True` and leaves the bad file in place. Network
Discovery was already fixed for this in commit `8117949b`.

**Fix**
1. After `subprocess.run`, treat `returncode != 0` as failure: restore the backup
   (or remove the file if none existed), include trimmed stderr in the message,
   return `False`.
2. Re-run the reload after rollback so the daemon matches the restored file, and
   report if that second reload also fails.
3. Extract one shared `apply_with_rollback(live_path, candidate, backup_dir)`
   used by both Network Discovery and Plugin Manager so the two cannot drift
   again.
4. Add a regression test in `server/tests` mirroring the Network Discovery
   nonzero-exit test (reload exit 42 → `applied=False`, prior bytes restored).

**Acceptance:** report's `isolated-reload-faults.json` scenario returns
`applied=false` and restores the prior file for both helpers.

## 4. Item B: NCPA TLS key permissions

**Cause** (`server/app/ncpa_deployment/ncpa_deployment.py:416-427`): the key is
created by root with mode 600, but NCPA drops privileges to `nagios`, so it
cannot read the key. The listener also later disappeared while `init status`
still said "running".

**Fix**
1. After creating the key: `chown root:nagios` and `chmod 640` the key;
   `chown root:root`, `chmod 644` the cert. Apply on **every** deploy, not only
   when files are first created, so redeploys repair existing guests.
2. Verify readability as the service user before starting, e.g.
   `sudo -u nagios test -r "$KEY_FILE"`; fail deployment with a clear message if
   not.
3. Replace the `init status | grep running` check with a real post-start probe:
   confirm the listener on the NCPA port (`ss -ltn`) and an authenticated
   HTTPS request to `/api/` succeeds, retrying for a few seconds.
4. Fix status handling: clear the old `Error` text when a deployment reaches
   DEPLOYED and set `completed_at`.
5. Investigate the later listener loss (report: "root cause not established"). On
   a VM, capture `/usr/local/ncpa/var/log/ncpa_passive.log` and
   `ncpa_listener.log` after a deploy, then after 10 minutes; check whether the
   passive/listener process exits on a config reload or a log-rotation event.
   Add a watchdog or a systemd drop-in (`Restart=on-failure`) only if the cause
   is process exit. Do not close this item on the permission fix alone.

**Acceptance:** first-attempt deploy on a clean baseline succeeds with no manual
`chmod`; CPU/memory checks stay OK for at least 15 minutes; failed status text is
cleared.

## 5. Item C: NCPA disk checks use invalid partition paths

> **Update 2026-10-05:** node discovery was implemented, and the metric leaf is now
> `used_percent` (NCPA 3.5.0 has no `percent` node). See
> `Data_Model_and_Integrations.md` (NCPA deployment).

**Cause:** the deploy script records `lsblk` `TYPE=part` names (`vda1`, `vda14`,
`vda15`) and `ncpa_checks()` substitutes them into `disk/logical/{partition}/...`.
NCPA's logical disk nodes are keyed by **mount point / device as NCPA reports
them**, not by raw partition name, and some partitions (BIOS boot, EFI, unmounted)
have no logical node at all. The report shows `disk/logical/vda1/percent` returns
"node does not exist".

**Fix**
1. Stop deriving paths from `lsblk`. At deploy time, call the NCPA API itself
   (`GET /api/disk/logical`) using the token and store the node names it
   actually returns (e.g. `|`-escaped mount names).
2. Keep only nodes that are mounted filesystems; skip unmounted, boot, swap, and
   pseudo filesystems.
3. Store these in `NCPADevicePartition` (rename the field's meaning in docs; a
   schema rename is optional) and build `metric_path` from the stored node name,
   URL-encoding as NCPA requires.
4. Before generating a disk service, probe the path once; if it returns "node
   does not exist" do not generate the service and record a visible skipped
   entry (consistent with the existing skipped-services mechanism).
5. Add a refresh action so partitions are re-read after disk changes.
6. Tests: unit-test the path builder with NCPA fixture JSON for mounted, unmounted,
   and `/boot/efi` cases.

**Acceptance:** every generated NCPA disk service reaches OK on the VM; no disk
service ends UNKNOWN; MON-01/03/04 pass for NCPA disk as well as CPU/memory.

## 6. Item D: missing `system.hosts.edit` in installed database

**Cause:** `seed.py:35` defines it, but the installed DB never received it, so
every port promotion returned 400 "Permission does not exist".

**Fix**
1. Add an idempotent upgrade step (migration or seed-on-upgrade command) that
   inserts missing permissions from the seed list and grants them to the roles the
   seed assigns them to; never removes or alters existing grants.
2. Make the route's failure explicit: a missing permission row at startup should
   log a clear error rather than surface as a 400 to end users.
3. Add a startup/health check comparing the seed permission list with the DB.
4. Test: start from a DB lacking the permission, run the upgrade, assert the
   permission exists and the admin role holds it; run again, assert no change.
5. Document the upgrade step in `Implementation_Status.md` and the installer notes.

## 7. Item H: rollback hardening

- Network Discovery's live attempt failed at `shutil.copy2` → `copystat` with
  EPERM before reload. `copy2` copies metadata that the service user may not be
  allowed to set on root-owned files. Switch to `shutil.copyfile` plus an explicit
  permission policy, or write the candidate and use an atomic `os.replace` into
  the same directory.
- Add a live-daemon forced-reload-failure test on a disposable VM (a candidate that
  passes `nagios -v` but makes the reload command fail) to prove rollback against
  the real systemd unit, not only isolated helpers.

## 8. Items F and G: test plan and fixtures

**F: plan versus lifecycle (ND-03, ND-07, ND-11, ND-13).** The product behavior is
newer than the plan. Update `server/tests/NETWORK_DISCOVERY_EXTENDED_TEST_PLAN.md`
so that expectations match the approved lifecycle (and decide each point below
in Q4):
- Non-auto-monitored services are `SUGGESTED` until explicitly promoted (ND-07).
- A single missed scan retains a monitored port and increments `Missed_Scans`
  (ND-11). Define the expected value after 1 and 2 misses.
- A host becomes missing after 2 missed scans; define the retire/archive step and
  the 30-day retention rule so ND-13 can pass or fail objectively.
- ND-03 must not assume exactly two global hosts: assert on the target hosts and
  allow the monitoring bridge host; reset the baseline inventory or scope the
  assertion by network prefix.
- Commit the untracked `spec files/DHCP_Device_Identity_Plan.md` (or fold it into
  the specs) so plan cases can cite it.

**G: unsupported UDP (ND-08).** Nmap reports `open|filtered` for UDP services that
ignore empty probes, so the echo listener on 69 was never "open". Add a fixture
that replies to nmap's protocol probe (a real TFTP responder on 69, or SNMP/NTP
on a non-standard port) so the case exercises the skipped-service path. Separately,
decide whether `open|filtered` UDP ports should be recorded as skipped with that
reason (Q5).

## 9. Decisions and remaining questions

Decided:
1. Names are all lowercase.
2. Multi-check names: `{service}-{metric}-{port}-{protocol}`.
3. Existing hosts are **regenerated** with the new names (one reload). Keep a
   display mapping so history/alerts stay continuous.
4. Lifecycle: **5 missed scans**, then **30-day retirement**. Update
   `port_lifecycle.py` (currently 2 for hosts) and the ND-11/ND-13 plan cases.
5. UDP `open|filtered` ports are **recorded as skipped** (reason: unconfirmed).
6. `10.0.2.0/28` is a substitute for testing only, not a permanent range (see
   Q-b below).
7. **One branch per item** (A, B, C, D, E, H, plus test-plan work F/G), each
   branched from `main`. Because B and C generate NCPA service names, merge E first and
   rebase B/C onto it to avoid naming conflicts.

Also decided:
- **Q-a:** 5 missed scans applies to **both** a single port and a whole host.
- **Q-b:** `10.0.2.0/28` is a substitute/testing subnet only, not a permanent lab
  range; the test plan keeps the subnet as a per-run setting and records why the
  preferred `192.168.130.0/28` is avoided (overlap with management).

- **KVM:** the host supports KVM, but the existing guests run under QEMU software
  emulation. The re-run must switch the libvirt domains to `type='kvm'`
  (confirm `/dev/kvm` exists and the user is in the `kvm` group) and record the
  accelerator in the evidence, so ENV-01 can pass. Add an ENV-01 check that fails
  if a guest reports `qemu` instead of `kvm` as its domain type.

No questions remain open.

## 10. Verification and re-run

1. Backend suite (`server/tests`) green, including new tests for A, C, D, E.
2. Re-run the live harness from clean qcow2 baselines in the order: ENV, DS, ND,
   CFG, MON, PM, NCPA, SNMP, AUTH, SEC, CLEAN.
3. Close criteria: every core case Pass, including the four Blocked cases
   (ENV-01 pending Q6, ND-13 pending Q4, CFG-04 via item H, SEC-01 with a full
   journal read), so Stage F permits the extended profiles.
4. Update `Implementation_Status.md` as each item completes, and the specs listed
   under items E and D.

## 11. Risks

- Renaming services (E) breaks name-matching code and alert history continuity
  if the audit in §2 is incomplete; do it behind tests before touching NCPA.
- NCPA fixes (B, C) can only be validated against a real agent; budget VM time
  for them rather than relying on unit tests.
- The listener-loss cause in item B may be separate from permissions; do not mark
  the item done on a green first deploy alone.
