# Test run: vm-lab-first-run

| | |
|---|---|
| Date | 2026-10-08 |
| Commit tested | Application `1540545` (`main`, installed by the installer's deploy step). Lab tooling `04caffdf` plus uncommitted `smoke.py` and `sync` changes on `feat/vm-lab` |
| Plan | [`docs/plans/VM_Lab_Plan.md`](../../plans/VM_Lab_Plan.md) |
| Tester | Claude Code, supervised by the project owner |
| Environment | VirtualBox 7.2.14 on Debian 13. Appliance: Ubuntu 22.04.5, 4 GB, 4 CPUs, NAT plus internal network `pinpoint-demo` (`10.77.0.1/28`). Nagios Core 4.5.11 and plugins built by the installer's own steps (installer repo commit `f0323ea`, local clone, unmodified). Targets: five Ubuntu 24.04 VMs from `demo/demo_lab.py` at `10.77.0.2` to `.6`. Database: fresh |
| Raw evidence | Author's machine: `~/pinpoint-test-results/2026-10-08-vm-lab-first-run/` (install logs and smoke output; not committed) |

## Result

**Overall: Pass for the lab tooling, with one application defect found.** The VM lab
works end to end: an unattended appliance install, the installer's setup steps run
directly over SSH, a snapshot below the application, a fresh installation of `main`
on that snapshot, the installer's healthcheck, and discovery plus monitoring of five
real VMs. Alerting, NCPA and the `break` commands were not exercised.

Totals: Pass 16, Fail 0, Blocked 0, Skipped 5, plus 1 observation (see the table). One
earlier smoke run failed for reasons in the test script, listed under deviations.

## Cases

| Case | Result | Notes | Issue |
|---|---|---|---|
| Unattended appliance install (`vmlab create`) | Pass, after a fix | Ubuntu 22.04.5 installed; VirtualBox's post-install step did not install the SSH key on 22.04. `create` now installs it by password | |
| Installer steps 1 to 5 over SSH (`vmlab provision`) | Pass | All five ran non-interactively from a local installer clone; snapshot `os-nagios-ready` taken | |
| Fresh install of `main` on the snapshot (`vmlab fresh main`) | Pass | Installer's deploy and privilege steps; healthcheck: **59 passed, 0 warnings, 0 failed** | |
| Healthcheck: database at latest migration | Pass | Revision `b4e8d1a7c629` | |
| Healthcheck: Gunicorn on loopback only, 1 worker, scheduler on | Pass | | |
| Healthcheck: nmap SYN scan as `pinpoint`, `nmap-sudo` | Pass | | |
| Healthcheck: Nagios reload through sudo, config validation | Pass | | |
| Installer default discovery range | Observed | `10.0.2.0/24` (the NAT subnet); lab network must be added | |
| Administrator login (`vmlab setup-admin`) | Pass | One-time credentials replaced; new password stored privately | |
| Targets reachable from the appliance over the lab network | Pass | 5 of 5 answer ping; ports 22, 80, 443, 8080 and 2222 open | |
| Discovery of the lab network | Pass | Finished in 124 to 128 s; "New host.cfg successfully applied" | |
| `10.77.0.2` monitored and Up | Pass | | |
| `10.77.0.3` monitored and Up | Pass | | |
| `10.77.0.4` monitored and Up | Pass | | |
| `10.77.0.5` monitored and Up | Pass | Appeared late in the first run; see the defect below | #43 |
| `10.77.0.6` monitored and Up | Pass | | |
| `vmlab sync` | Pass | File arrived owned by `pinpoint`, databases kept, Gunicorn restarted and answered. Needed a `tar` fallback because `rsync` is absent | |
| `vmlab sync --client` | Skipped | Not run | |
| `vmlab up` / `down` / `revert` as separate commands | Skipped | Exercised only inside `fresh` and `provision` | |
| Plugin enablement, alerts, acknowledgement | Skipped | Needs services attached after enabling plugins; not run | |
| NCPA deployment | Skipped | The point of the VM lane; not run | |
| `demo_lab.py break` / `fix` / `load` | Skipped | Not run | |

## Deviations from the plan

- The first smoke run reported 5 failures: the test matched hosts by name, but
  Pinpoint names hosts `dev-xxxxxx.test.local`, and its "6 up" count was satisfied by
  an unrelated host from the installer's default range. The script now checks each
  target's address. The second run passed 9 of 9.
- `sync` was changed from `rsync` to `tar` over SSH. Deleted files stay on the VM
  until the next `fresh`.
- The default web port moved from 8080 to 18080 (another program on the test machine
  holds 8080).

## Follow-up

- Defect found: [#43](https://github.com/esfen14/Network-Diagnosis-System/issues/43), the status poller fails for hosts Nagios reports as pending (`HostStateType` has no `PENDING`). 26 tracebacks in about 3 minutes after discovery added five hosts; the hosts are skipped until their first check completes.
- Cases to run next: NCPA deployment through the wizard, plugin enablement and alerts, `break` and `fix`, `sync --client`.

## Sanitization checklist

- [x] No passwords, tokens, keys, SNMP communities or private key paths
- [x] No addresses outside the documented lab ranges (`10.77.0.0/28`, the NAT `10.0.2.0/24`)
- [x] Evidence is referenced by name and location, not pasted
