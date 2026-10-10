# Test run: issue-67

| | |
|---|---|
| Date | 2026-10-10 |
| Commit tested | `f9f03bcf` (app source synced into an already-running VM; not a fresh install) |
| Plan | [Issue #67](https://github.com/esfen14/Pinpoint/issues/67) sequence and J2-08 from [QA Test Plan](../../qa/QA_Test_Plan.md) |
| Tester | OpenCode agent, API and VM shell; browser UI not driven |
| Environment | VirtualBox `pinpoint-appliance-45`, Ubuntu 22.04.5, Nagios Core 4.5.11, five `demo/` targets on `10.77.0.0/28`; pre-existing SQLite data from prior runs, including address history and NCPA deployment |
| Raw evidence | Console API and SQLite queries during the run were not persisted; observations below are limited to the conversation transcript. No raw secrets are committed. |

## Result

**Overall: Partial.** The rescan after removing the NAT network succeeded and the observed database rows stayed on their respective networks. This was **not** a fresh-install reproduction of the reported gateway reassignment: the persisted NAT-network device was `10.0.2.3` (ID 6), not the `10.0.2.2` gateway, while `10.0.2.2` appeared only as a closed address-history row on device 1 from an earlier run. The run cannot establish that the gateway's ports were not monitored under web01, nor a full J2-08 pass.

Totals: Pass 1, Fail 0, Blocked 0, Skipped 2.

## Cases

| Case | Result | Notes (what was observed) | Issue |
|---|---|---|---|
| Removed-network rescan on existing appliance | Pass | Settings were changed from both networks to `10.77.0.0/28` and TCP `1-1024`; the scan returned Success. A subsequent SQLite query showed IDs 1–5 ACTIVE at `10.77.0.2`–`.6` and ID 6 ACTIVE at `10.0.2.3`, with no `ADDRESS_UNKNOWN` record in that queried table. This supports address stability on this pre-existing dataset only. | [#67](https://github.com/esfen14/Pinpoint/issues/67) |
| Exact issue #67 fresh-install gateway/port sequence | Skipped | The database was not reset; the initial combined-network scan did not leave a gateway record at `10.0.2.2`. Device 1 already had a historical `10.0.2.2` address row and pre-existing NCPA data. No before/after assertion established that NAT gateway ports were absent from web01's record; the inspected ports for device 1 were 22, 80, 443 and 5693 at the time. | [#67](https://github.com/esfen14/Pinpoint/issues/67) |
| J2-08 two back-to-back rescans and record counts | Skipped | Only one additional scan after the removal scan was run. The scripted count read `data.hosts`, but the API actually returns `data.items`, so the apparent zero-duplicate assertion counted an empty list. A later response displayed five lab IPs as Up, but the documented inventory/API duplicate and `ADDRESS_UNKNOWN` checks were not completed for the required two rescans. | [#67](https://github.com/esfen14/Pinpoint/issues/67) |

## Deviations from the plan

- Used `scripts/vmlab sync` on an existing appliance instead of a fresh install. The first scan used a shortened TCP port list rather than the issue's initial default settings; the removal rescan did set `1-1024`.
- The browser UI was not driven. API responses and database rows were inspected directly, but the network-health count script parsed the wrong response key.
- The earlier version of this report incorrectly marked the exact issue reproduction and J2-08 as Pass. This correction retracts those conclusions; a fresh run and correctly parsed counts are still needed.

## Follow-up

- Repeat on a fresh appliance/database with the gateway `10.0.2.2` actually persisted before removing its network; assert device IDs, all ACTIVE/ADDRESS_UNKNOWN rows by IP, address history and NAT-port ownership before and after.
- Run the two J2-08 rescans, count `data.items` from Network Health **and** inventory device rows, and check target state.

## Sanitization checklist

- [x] No passwords, tokens, keys, SNMP communities or private key paths
- [x] No addresses outside the documented lab range
- [x] Evidence is described without raw transcripts
