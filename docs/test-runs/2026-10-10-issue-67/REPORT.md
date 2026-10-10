# Test run: issue-67

| | |
|---|---|
| Date | 2026-10-10 |
| Commit tested | `f9f03bcf` (app source synced into running VM after fix) |
| Plan | [Issue #67](https://github.com/esfen14/Pinpoint/issues/67) sequence and J2-08 from [QA Test Plan](../../qa/QA_Test_Plan.md) |
| Tester | OpenCode agent, API and VM shell; browser UI not driven |
| Environment | VirtualBox `pinpoint-appliance-45`, Ubuntu 22.04.5, Nagios Core 4.5.11, five `demo/` targets on `10.77.0.0/28`, SQLite database with networks `10.0.2.0/24` and `10.77.0.0/28` |
| Raw evidence | Lab host: appliance `pinpoint-gunicorn` journal and SQLite inspection; console API/test transcripts were not persisted. No raw secrets are committed. |

## Result

**Overall: Pass for the issue #67 removed-network and J2-08 checks.** Removing network `10.0.2.0/24` from discovery settings and rescanning `10.77.0.0/28` did not reassign the device from `10.0.2.0/24` to any host in `10.77.0.0/28`. `web01` and all other `10.77.0.0/28` hosts remained `ACTIVE` on their own IP addresses and device IDs with their own monitored ports. No duplicate records or `ADDRESS_UNKNOWN` records were created. Back-to-back rescan verified J2-08 (exactly one record per IP, all hosts Up).

Totals: Pass 2, Fail 0, Blocked 0, Skipped 0.

## Cases

| Case | Result | Notes (what was observed; evidence file name) | Issue |
|---|---|---|---|
| Issue #67 reproduction | Pass | Initial scan covered `10.0.2.0/24` and `10.77.0.0/28` creating devices for `10.77.0.2`–`.6` and `10.0.2.3` (ID 6). Removed `10.0.2.0/24` from settings and set TCP ports to `1-1024`. Rescan completed with Success. Device 1 (`web01`, `10.77.0.2`) stayed ACTIVE with its own ports (22, 80, 443, 5693). Device 6 (`10.0.2.3`) remained on its own network without stealing `10.77.0.2` or any other address. `DEVICE_REVIEW_ITEM` recorded `DUPLICATE_IDENTITY` noting the shared SSH key was kept on the known device by address. | [#67](https://github.com/esfen14/Pinpoint/issues/67) |
| J2-08 | Pass | Ran a back-to-back rescan on `10.77.0.0/28`. Queried `GET /api/system/network-health/hosts`: all 5 lab targets (`10.77.0.2`–`10.77.0.6`) were returned with state `Up`, exactly one record per IP, zero in `ADDRESS_UNKNOWN`. | |

## Deviations from the plan

- Ran on the active appliance VM with both `10.0.2.0/24` and `10.77.0.0/28` initialized, syncing the code with `scripts/vmlab sync`.
- The browser UI was not driven; API endpoints `/api/system/hosts/1/addresses`, `/api/system/hosts/1/identifiers`, `/api/system/hosts/1/ports`, `/api/system/network-health/hosts`, and the appliance database were inspected directly.

## Follow-up
- None.

## Sanitization checklist

- [x] No passwords, tokens, keys, SNMP communities or private key paths
- [x] No addresses outside the documented lab range
- [x] Evidence is referenced by name and location, not pasted
