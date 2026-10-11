# Test run: qa-dry-run-j2-j3

| | |
|---|---|
| Date | 2026-10-09 |
| Commit tested | `65b63e5b` (this branch; it only adds docs). The first install was this branch. After a snapshot revert the second install reported `main` (`13076192`) because the checkout was switched by someone else mid-run; the application code is identical in both |
| Plan | docs/qa/QA_Test_Plan.md (J1-01, J2-01..10, J3-01..09) |
| Tester | Claude (agent), driven from the API and the lab shell; the browser UI was not driven |
| Environment | VM lab on VirtualBox: installer-built Ubuntu 22.04 appliance restored from snapshot `os-nagios-ready`, five Ubuntu target VMs on the lab range 10.77.0.0/28, fresh database (two fresh installs: the first was reverted, see Deviations) |
| Raw evidence | Lab host, agent scratch folder (not committed): API transcripts and the scan logs |

## Result

**Overall: Partial.** J2 and J3 can be run from the plan on the VM lab; 13 of the 20
attempted cases passed, one failed (J2-09, a possible discovery defect) and six were not
run. Several steps were not runnable as written and the plan was corrected in the same
change (see Deviations). The dry-run finish condition is met; the failed and skipped
cases are carried to the next run.

Totals: Pass 13, Fail 1, Blocked 0, Skipped 6.

## Cases

Device names are generated (`dev-xxxxxx`), so targets are identified by address:
web01 .2, web02 .3, app01 .4, snmp01 .5, legacy01 .6.

| Case | Result | Notes (what was observed; evidence file name) | Issue |
|---|---|---|---|
| J1-01 | Pass | `scripts/vmlab fresh` exit 0; healthcheck 60 passed, 0 failed | |
| J2-01 | Pass | Targets .2 to .6 monitored and Up. `vmlab smoke` failed its own "discovery finishes" check at 300 s: the first scan took about 14 min, and hosts reached the Network Health list over about 4 more min. Also listed: the lab NAT gateway and one more NAT host | |
| J2-02 | Pass | API only: status went Running (progress 6, 23, 30) to Success 100 with "New host.cfg successfully applied". The UI wording was not observed | |
| J2-03 | Pass | IP and MAC (`/hosts/<id>/identifiers`), OS (`/report/hosts-by-os`: Linux) and ports present; web01 22, 80, 443; legacy01 SSH 2222 (on the first baseline); each port has a state and a reason. "Device type" is not exposed by any route read | |
| J2-04 | Pass | Before: only `localhost` services. After enabling `check_ssh` and `check_http`: one SSH service per target, `ssh-2222-tcp` for legacy01; 24 services in all | |
| J2-05 | Skipped | Step 1 observed: an unchanged network gave "Host configuration unchanged; Nagios was not reloaded". Steps 2 and 3 (the SSH port move) were not run | |
| J2-06 | Pass | Start, stop 5 s later: ended Interrupted, log "Network discovery was cancelled."; no 403 for the administrator. The cancel took about 7 min to take effect (an nmap run was in flight) | |
| J2-07 | Pass | Pause removed snmp01 from the generated `hosts.cfg` and the Dashboard host total went 8 to 7; resume restored both. The user-log entries were not read (route not found) | |
| J2-08 | Pass | On a clean baseline, four rescans left exactly one ACTIVE record per address. #59 did not reproduce. A different duplicate appeared on the reverted first run, see Follow-up | |
| J2-09 | **Fail** | Setting saved (`1-1024` plus 8080, then 2222, then ranges `2200-2299` and `8000-8099`) and rescanned three times, each Success. nmap from the appliance shows 2222 on legacy01 and 8080 on app01 open, but neither port was ever recorded. Possible cause: ports that appear on an already-known device after a settings change are not recorded. The Configuration Change entry was not read [#66](https://github.com/esfen14/Pinpoint/issues/66) |
| J2-10 | Skipped | Unit test and Maintenance Mode banner not run | |
| J3-01 | Skipped | `GET /deployment/ncpa/devices` read: the four reachable Ubuntu targets were eligible. legacy01 was missing because of the J2-09 finding. The Incompatible/Excluded path (MOCK) was not run | |
| J3-02 | Pass | web01 and web02 (not web01 and legacy01 as written): host keys read and trusted, login and sudo ok, run Success in 60 s, both Deployed NCPA (`vmlab ncpa`, 16 of 16 checks). legacy01 could not be tried (J2-09) | |
| J3-03 | Pass | `SSH_CREDENTIALS` holds only port, key-installed flag and fingerprint; no password in the run, device or trusted-device responses. `NCPA_DEPLOYMENT` stores the NCPA token (a different secret) | |
| J3-04 | Skipped | The script's flow reads and trusts the key before login; the refusal path with an unapproved key was not tried | |
| J3-05 | Pass | Three services per deployed host (cpu, root disk, memory), real output, none CRITICAL or exit 127. web01 memory was WARNING (50.5 %), a real threshold hit | |
| J3-06 | Pass | One NCPA Deployment log entry "Deployed NCPA to 2 device(s)." with starter Admin User and outcome Success. The partial-failure wording was not seen (J3-07 not run) | |
| J3-07 | Skipped | Not run | |
| J3-08 | Skipped | Not run | |
| J3-09 | Pass | One record per address after the deployment; #59 did not reproduce | |

## Deviations from the plan

- **Lab access.** This machine's appliance is `pinpoint-appliance-45` with its own state
  folder. `scripts/vmlab` only honours `VMLAB_VM` from the config file but reads
  `VMLAB_STATE_DIR` from the environment, so the first attempts failed on SSH.
- **First run reverted.** To shorten scans I removed the NAT network from discovery and
  narrowed TCP ports to 1-1024. That produced a corrupt state (see Follow-up), so I
  reverted with `vmlab fresh` and redid the cases on a clean baseline. J1-01, J2-01,
  J2-03, J2-04, J2-06 and J2-05 step 1 were observed on the first install; the rest on
  the second.
- **Scan ports.** After the revert I kept both networks and only narrowed TCP to
  `1-1024` (a scan then takes about 6 min instead of 14). That excludes legacy01's
  SSH port 2222, which is why legacy01 had no ports on the second install; J2-09 then
  failed to add it back.
- **Fresh plugin count.** `GET /api/plugin/summary` read 0 installed for about a minute
  after a fresh install, then 65 (relevant to J4-01).
- Not driven: the browser UI (J2-02, J2-06 wording, J3-01 selection).

## Follow-up

- Defects found: [#66](https://github.com/esfen14/Pinpoint/issues/66) (1) J2-09, single ports or ranges
  added to the scan ports after a device is known are never recorded; [#67](https://github.com/esfen14/Pinpoint/issues/67) (2) removing a
  network from discovery settings reassigned the old NAT-gateway device to four lab
  hosts within one second and left web01 with an `Address Unknown` record and the
  gateway record carrying web01's address and identifiers (a #59-like duplicate with a
  different trigger).
- Plan fixes made with this report: J2-01 (smoke timeout, slow first scan, hosts appear
  late, names are generated), J2-03 (where each attribute is read; device type), J2-09
  (8080 is already in the default range 1-10000), J3-05 (memory may be WARNING), the
  plugin name `check_ncpa.py`, and the lab environment variables.
- Cases to repeat in the next run: J2-05, J2-09, J2-10, J3-01, J3-04, J3-07, J3-08 and
  J3-02/J3-09 with legacy01, and the UI parts of J2-02 and J2-06.

## Sanitization checklist

- [x] No passwords, tokens, keys, SNMP communities or private key paths
- [x] No addresses outside the documented lab range
- [x] Evidence is referenced by name and location, not pasted
