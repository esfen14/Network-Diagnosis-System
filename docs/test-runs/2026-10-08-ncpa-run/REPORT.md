# Test run: ncpa-run

| | |
|---|---|
| Date | 2026-10-08 |
| Commit tested | Application `1540545` (`main`, installed by the installer's deploy step); installer repo `f0323ea`; lab tooling `5cc98d41` plus the `ncpa` command added in this change |
| Plan | [`docs/plans/VM_Lab_Plan.md`](../../plans/VM_Lab_Plan.md) (section 6, "NCPA deployment") |
| Tester | Claude Code, supervised by the project owner |
| Environment | The VM lab from [`2026-10-08-vm-lab-first-run`](../2026-10-08-vm-lab-first-run/REPORT.md): installer-built appliance (Ubuntu 22.04.5, Nagios Core 4.5.11) and the `demo/` targets (Ubuntu 24.04, 512 MB each) at `10.77.0.2` to `.6` |
| Raw evidence | Author's machine: `~/pinpoint-test-results/2026-10-08-ncpa-run/` (not committed) |

## Result

**Overall: Partial.** Deploying NCPA through Pinpoint's deployment API works, including to a
target whose SSH listens on port 2222, and the agents answer correctly. But the six NCPA
services Pinpoint then attached to Nagios are all **CRITICAL (return code 127)** on an
installer-built appliance, so NCPA monitoring does not work out of the box. Cause and
proof below; filed as #45. With a one-package workaround applied to the running VM, all six
checks return real values and Pinpoint shows the CPU data.

The deployment wizard was driven through its API (`lab/ncpa_run.py`), not in a browser.

Totals: Pass 15, Fail 1, Blocked 0, Skipped 5 (see the table).

## Cases

| Case | Result | Notes (what was observed; evidence file name) | Issue |
|---|---|---|---|
| Both targets listed as NCPA-eligible (`Pending NCPA`) | Pass | `10.77.0.2` and `10.77.0.6` | |
| Read the SSH host key of `web01` | Pass | SSH port 22 | |
| Read the SSH host key of `legacy01` | Pass | SSH port **2222**, found by discovery | |
| Trust both host keys | Pass | "Device fingerprint saved." | |
| SSH login and sudo check for both | Pass | result `ok` for both | |
| Start a deployment for 2 devices | Pass | HTTP 202, no rejections | |
| The run completes | Pass | `Success`, 100%, **70 s** for two devices (`ncpa-run1.log`) | |
| Both devices show `Deployed NCPA` | Pass | | |
| Agents answer directly on port 5693 | Pass | CPU and memory returned over HTTPS from the appliance, with the stored token (not recorded here) | |
| Targets without an agent refuse port 5693 | Pass | `.3`, `.4`, `.5`: connection refused | |
| Plugin scan finds `check_ncpa.py` | Pass | Plugin id 2, status Ready, 65 plugins unchanged | |
| Enable preview | Pass | "Enabling will monitor 6 service(s) on 2 device(s)" | |
| Enabling applies the Nagios config | Pass | 6 services applied, config reloaded | |
| Nagios runs the six NCPA checks | **Fail** | All six `CRITICAL`: "Return code of 127 is out of bounds. Check if plugin exists" (`nagios-ncpa-status-poll.log`, 10 minutes, no change). Cause: `check_ncpa.py` starts with `#!/usr/bin/env python`; Ubuntu 22.04 has no `python` command, so the plugin cannot start for the `nagios` or `pinpoint` user. The installer's verify step runs `python3 check_ncpa.py` and its healthcheck only tests the file exists, so neither caught it | #45 |
| After installing `python-is-python3` on the running VM, the checks return values | Pass | CPU 4% and 2%, root disk 25.9% (both), memory 50.2% (warning at the 50% threshold) and 49.9%. Workaround applied to the live VM only; not in the snapshot | #45 |
| Pinpoint shows the NCPA CPU data | Pass | After the workaround: current 2.0%, 24 buckets, both NCPA hosts listed; summary 14 services (12 OK, 1 warning, 1 critical, which is not an NCPA service) | |
| Wizard in a browser | Skipped | Driven through the API only | |
| Failure paths: wrong password, no sudo, changed host key | Skipped | Rejection reasons not exercised | |
| Redeploy to an already-deployed device | Skipped | | |
| CPU load alert on an NCPA threshold (`demo_lab.py load`) | Skipped | Needs the checks to be healthy first; rerun after #45 | |
| Disk refresh (`refresh-disks`) and trusted-device list | Skipped | | |

## Deviations from the plan

- The deployment was driven through the API with `lab/ncpa_run.py` instead of the wizard UI.
- The workaround for #45 was applied by hand on the running appliance to prove the diagnosis.

## Follow-up

- Defect: [#45](https://github.com/esfen14/Network-Diagnosis-System/issues/45), NCPA services are CRITICAL on installer-built appliances. The fix belongs mainly in the installer repository (install `python-is-python3`, or use a `python3` shebang, and make its verify step and healthcheck run the plugin as the `nagios` user); an application-side option is described in the issue.
- Known, already in `Implementation_Status.md`: the NCPA token is a positional argument of the Nagios command, so it is visible in the generated config and in process listings. Observed again here; token values are not recorded in this report.
- Rerun after #45 is fixed: the monitoring cases above, the CPU load alert, and the skipped failure paths.

## Sanitization checklist

- [x] No passwords, tokens, keys, SNMP communities or private key paths
- [x] No addresses outside the documented lab ranges
- [x] Evidence is referenced by name and location, not pasted
