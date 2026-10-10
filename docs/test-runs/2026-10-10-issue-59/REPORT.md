# Test run: issue-59

| | |
|---|---|
| Date | 2026-10-10 |
| Commit tested | Application `431f50ae` (`issue-59-discovery-duplicate-device`); installer checkout at local branch (not modified) |
| Plan | [Issue #59](https://github.com/esfen14/Pinpoint/issues/59) sequence and [VM Lab plan](../../plans/VM_Lab_Plan.md) |
| Tester | OpenCode agent, with owner authorization |
| Environment | VirtualBox `pinpoint-appliance-45`, Ubuntu 22.04.5 / Nagios Core 4.5.11; freshly restored `os-nagios-ready` snapshot and installed branch; five `demo/` targets at `10.77.0.2`–`.6`; SQLite databases initialized fresh. |
| Raw evidence | VM lab on tester's machine; `scripts/vmlab` output and SQLite state on the disposable appliance, not committed. |

## Result

**Overall: Pass for one active record at `10.77.0.6` after the issue sequence.** Discovery ran slowly: two smoke runs exceeded their 300-second wait, but the first scan later reported Success; the second scan was Running at the time of the deployment. A repeated start while it was Running returned HTTP 400 rather than starting a third scan. NCPA deployment succeeded to the one listed `legacy01` target over SSH port 2222. This run did not deliberately cause two discoveries to overlap.

Totals: Pass 6, Fail 0, Blocked 0, Skipped 1.

## Cases

| Case | Result | Notes (what was observed) | Issue |
|---|---|---|---|
| Fresh install from `431f50ae` | Pass | Installer deploy and privileges steps completed; healthcheck 60 passed, 0 failed. | #59 |
| First smoke scan | Pass | Smoke's 300-second wait timed out, but scan ID 1 subsequently reached Success; target hosts appeared monitored and Up. | #59 |
| Repeat smoke scan while host is under resource pressure | Pass | Started scan ID 2; 300-second wait timed out, but all five lab IPs were monitored and Up. | #59 |
| Third discovery start while scan ID 2 is Running | Pass | `POST /api/system/discover/start` returned HTTP 400, "Network discovery is already running." | #59 |
| Database record for `10.77.0.6` after repeat scan starts | Pass | Direct SQLite query of `NETWORK_DISCOVERY` returned one row `(7, 10.77.0.6, ACTIVE)` before NCPA deployment. | #59 |
| NCPA deploy to `10.77.0.2` and `10.77.0.6` | Pass | 16/16 checks, both outcomes Success; trust read SSH on 22 and 2222 respectively. Query after deployment still returned one `ACTIVE` row for `10.77.0.6`. | #59 |
| Force overlapping scan writes on the live appliance | Skipped | The running-scan API rejects a second start; no deliberate DB-level overlap was injected. Isolated race regression covers simultaneous starts. | #59 |

## Deviations from the plan

The smoke command timed out twice while scans continued in the background. No overlapping runs were induced; the API rejected an additional start, and the isolated concurrent-start test exercises the race. The original duplicate was reproduced in an isolated regression by marking the old record `ADDRESS_UNKNOWN` and rescanning its same IP, not on this fresh lab.

## Follow-up

- No new defect found. The first and second discovery scans taking longer than 300 seconds on this appliance are an environment limitation noted in #59; the cause of their duration was not investigated here.

## Sanitization checklist

- [x] No passwords, tokens, keys, SNMP communities or private key paths
- [x] No addresses outside the documented lab range
- [x] Evidence is referenced by name and location, not pasted
