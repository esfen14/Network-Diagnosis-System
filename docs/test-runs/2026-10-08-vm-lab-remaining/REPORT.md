# Test run: vm-lab-remaining

| | |
|---|---|
| Date | 2026-10-08 |
| Commit tested | Application: `issue-43-pending-hosts` at `d8dc63e0` (fresh install) and `main` at `483c8bdc`; lab tooling `483c8bdc` plus the `alerts` command added in this change |
| Plan | [`docs/plans/VM_Lab_Plan.md`](../../plans/VM_Lab_Plan.md) |
| Tester | Claude Code, supervised by the project owner |
| Environment | The VM lab from [`2026-10-08-vm-lab-first-run`](../2026-10-08-vm-lab-first-run/REPORT.md): installer-built appliance (Ubuntu 22.04.5, Nagios Core 4.5.11) and the `demo/` targets at `10.77.0.2` to `.6`. Database state: fresh install each time |
| Raw evidence | Author's machine: `~/pinpoint-test-results/2026-10-08-alerts-run/` (not committed) |

## Result

**Overall: Pass.** The lab cases left over from the first VM run now pass: a fresh install of the
#43 fix, the swap fix, `sync --client`, the alert lifecycle, `break`/`fix`/`load`, and
`up`/`down`/`revert`. NCPA monitoring is still open (#45) and was not repeated here.

Totals: Pass 12, Fail 0, Blocked 0, Skipped 3 (see the table).

## Cases

| Case | Result | Notes (what was observed; evidence file name) | Issue |
|---|---|---|---|
| `fresh` of the #43 branch, installer healthcheck | Pass | 59 passed, 0 failed | |
| Pending hosts no longer raise errors (#43 fix) | Pass | 0 tracebacks in the Gunicorn journal during discovery and the first Nagios checks | #43 |
| Appliance has swap after `fresh` | Pass | 1 GB swap file; Nagios `localhost` "Swap Usage" is OK ("100% free"), it was CRITICAL without swap | |
| Smoke test after `fresh` | Pass | 9 of 9 on the re-run. The first run failed on one host that had not had its first Nagios check yet (still `pending`, so not yet in the host table); the host appeared within a minute | |
| `sync --client` | Pass | Built and copied the client and restarted Gunicorn in about 10 s | |
| Take a target down: an alert appears | Pass | "CRITICAL - Host Unreachable" in the active alerts feed about 70 s after the target was powered off (`alerts-final.log`) | |
| Acknowledge, list as acknowledged, unacknowledge | Pass | HTTP 201 then 200; the `ack_filter` views follow each change | |
| Alert clears when the target is back | Pass | | |
| State changes appear in alert history | Pass | `GET /api/system/history/alerts` returned 200 | |
| `demo_lab.py break` / `fix` (host) | Pass | Used by the alert run | |
| `demo_lab.py load` | Pass | Load average on the target rose during the 90 s burn | |
| `up`, `down`, `revert` | Pass | `down` powered off; `up` and the healthcheck passed 59/0; `revert` restored the snapshot (no Pinpoint, Nagios active) | |
| Alert for a stopped service (`break <target> http`) | Skipped | Pinpoint monitors only host reachability on newly discovered hosts until a service plugin is enabled, so no alert is expected | |
| Load alert from NCPA thresholds | Skipped | Needs working NCPA checks (#45) | #45 |
| Browser checks of the alert UI | Skipped | Driven through the API only | |

## Deviations from the plan

The alert case uses a powered-off target (host down). Breaking a service produced no alert
because no service check exists on those hosts.

## Follow-up

- Defects found: none new. Open and relevant: #45 (installer, NCPA checks need `python`).
- Cases to repeat in the next run: NCPA monitoring and load alerts after #45; the alert UI in a browser.
- The smoke test checks hosts right after discovery and can fail for hosts still `pending`; it passes on a re-run.

## Sanitization checklist

- [x] No passwords, tokens, keys, SNMP communities or private key paths
- [x] No addresses outside the documented lab range
- [x] Evidence is referenced by name and location, not pasted
