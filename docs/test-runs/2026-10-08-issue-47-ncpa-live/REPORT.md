# Test run: issue-47-ncpa-live

| | |
|---|---|
| Date | 2026-10-08 |
| Commit tested | `7735fc1e` (`issue-47-ncpa-log-level`, PR #54) |
| Plan | [`docs/plans/VM_Lab_Plan.md`](../../plans/VM_Lab_Plan.md) (NCPA deployment case) |
| Tester | OpenCode, supervised by the project owner |
| Environment | VM lab: installer-built `pinpoint-appliance` from snapshot `os-nagios-ready` (Ubuntu 22.04.5, Nagios Core 4.5.11) plus demo targets on `10.77.0.0/28`; fresh install of PR branch through `scripts/vmlab fresh issue-47-ncpa-log-level` |
| Raw evidence | Command transcript in this OpenCode session; appliance logs inspected with `journalctl` only. No raw secrets or full logs committed. |

## Result

**Overall: Pass for issue #47.** A fresh VM-lab install of the PR branch deployed
NCPA to two SSH targets, including the target whose SSH listens on port 2222, and
the run completed successfully. The Gunicorn journal for the deployment window had
no `Command failed` or `NCPA deployment to ... ended as ...` lines from the
expected `id` / `grep` probes.

Totals: Pass 9, Fail 0, Blocked 0, Skipped 1.

## Cases

| Case | Result | Notes (what was observed; evidence file name) | Issue |
|---|---|---|---|
| Fresh-install PR branch in appliance VM | Pass | `scripts/vmlab fresh issue-47-ncpa-log-level`; second attempt succeeded after an unrelated apt/dpkg lock cleared; healthcheck 59 passed, 0 failed | |
| Prepare administrator login | Pass | `scripts/vmlab setup-admin`; password stored only in the private VM-lab state directory | |
| Discover VM-lab targets | Pass | `scripts/vmlab smoke` timed out after 300 s while discovery was still running; polling `/api/system/discover/status` later showed `Success`, 100%, `New host.cfg successfully applied` after about 13 minutes | |
| Both requested targets listed as NCPA deployment targets | Pass | `10.77.0.2` and `10.77.0.6`, both `Pending NCPA` | |
| Read and trust SSH host keys | Pass | `10.77.0.2` on SSH port 22 and `10.77.0.6` on SSH port 2222 | |
| SSH login and sudo check | Pass | Both devices returned `ok` from `/api/system/deployment/ncpa/check-credentials` | |
| Start and complete NCPA deployment | Pass | `scripts/vmlab ncpa 10.77.0.2,10.77.0.6`; HTTP 202, no rejections, run id 1; completed `Success` in 372 s | |
| Per-device outcomes and final state | Pass | Both outcomes `Success`; both devices show `Deployed NCPA` | |
| Expected probe failures do not create ERROR log noise | Pass | `journalctl -u pinpoint-gunicorn --since "2026-10-08 06:46:43" ... | grep -E "Command failed|Expected probe exit|NCPA deployment to"` returned no matches. This proves the previous `Command failed (exit 1): id pinpoint-deployment` and grep ERROR lines did not recur in this successful deployment. INFO-level expected-probe messages may be below the journal's configured level. | #47 |
| NCPA Nagios monitoring checks | Skipped | This run targeted issue #47's deployment-log behavior only. Monitoring was previously known partial because of #45 and was not re-exercised here. | #45 |

## Deviations from the plan

- The deployment wizard was driven through the API by `lab/ncpa_run.py`, not in a browser.
- The first `scripts/vmlab fresh` attempt hit an unrelated apt/dpkg lock from `unattended-upgr`; after the lock cleared, restoring the snapshot and re-running `fresh` succeeded.
- `scripts/vmlab smoke` uses a 300 s discovery timeout; this scan completed later, so status polling was used to confirm success before NCPA deployment.

## Follow-up

- Defects found: none for #47.
- Existing follow-up remains #45 for NCPA Nagios monitoring on installer-built appliances.
- Consider increasing the VM-lab smoke discovery timeout for the faithful lane; the fresh scan can exceed 300 s.

## Sanitization checklist

- [x] No passwords, tokens, keys, SNMP communities or private key paths
- [x] No addresses outside the documented lab range
- [x] Evidence is referenced by name and location, not pasted
