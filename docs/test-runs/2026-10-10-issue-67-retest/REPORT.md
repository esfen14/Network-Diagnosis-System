# Test run: issue-67-retest

| | |
|---|---|
| Date | 2026-10-10 |
| Commit tested | `72b51602` (`issue-67-network-identity`, fresh installer checkout) |
| Plan | [Issue #67](https://github.com/esfen14/Pinpoint/issues/67) sequence and [QA Test Plan J2-08](../../qa/QA_Test_Plan.md) |
| Tester | OpenCode agent, API and VM shell; browser UI not driven |
| Environment | Owner-authorized reset of VirtualBox `pinpoint-appliance-45` to `os-nagios-ready`, followed by `scripts/vmlab fresh issue-67-network-identity`; Ubuntu 22.04.5, Nagios Core 4.5.11, five running `demo/` targets on `10.77.0.0/28`; freshly initialized SQLite database (zero device rows before the first scan). |
| Raw evidence | Console API/SQLite observations during the run; transcripts were not committed. VM state and journal are on the lab host. |

## Result

**Overall: Pass for #67's gateway/address/port outcomes and J2-08 on this fresh VM.** The initial combined-network scan persisted gateway at `10.0.2.2` separately from web01 at `10.77.0.2`. After removing the NAT network and scanning with TCP `1-1024`, gateway stayed at its original address with its ports; web01 kept its own ID, address and ports. Two subsequent rescans kept one ACTIVE record per lab IP and no ADDRESS_UNKNOWN record. Network Health eventually returned all five lab targets Up with one item per IP.

Totals: Pass 2, Fail 0, Blocked 0, Skipped 0.

## Cases

| Case | Result | Notes (what was observed) | Issue |
|---|---|---|---|
| Issue #67 fresh gateway reproduction | Pass | Healthcheck 60/0 after the fresh install. Initial scan of `10.0.2.0/24` and `10.77.0.0/28` with default TCP `1-10000` completed Success. SQLite showed gateway ID 1 ACTIVE at `10.0.2.2`, web01 ID 3 ACTIVE at `10.77.0.2`, and four other lab hosts with distinct IDs. Gateway alone had TCP 2201–2205 and 2250; 8080 belonged to gateway and app01, not web01. After saving only `10.77.0.0/28` and TCP `1-1024`, scan returned Success. Gateway still ID 1 ACTIVE at `10.0.2.2` with zero missed scans; web01 still ID 3 ACTIVE at `10.77.0.2`. Direct SQLite check showed no ACTIVE or ADDRESS_UNKNOWN duplicate IPs and no NAT-only ports on any lab host. API `/hosts/1/addresses`, `/hosts/1/identifiers`, `/hosts/3/identifiers`, `/hosts/1/ports`, `/hosts/3/ports` returned 200; gateway address history had only its open `10.0.2.2` row. | [#67](https://github.com/esfen14/Pinpoint/issues/67) |
| J2-08 back-to-back rescans | Pass | Two more scans of `10.77.0.0/28` with TCP `1-1024` returned Success. Final SQLite inventory IDs 1–7 remained ACTIVE at their original seven unique addresses: gateway and the second NAT host, plus lab `.2`–`.6`; zero ADDRESS_UNKNOWN. Gateway's NAT-only TCP ports remained attached only to ID 1. `GET /api/system/network-health/hosts` was parsed from `data.items`; after a short Nagios status lag following the removal scan, both subsequent rescans returned five distinct lab IPs, all Up. | |

## Deviations from the plan

- Settings and checks were driven through authenticated API and appliance SQLite rather than browser UI. The application generated Nagios status was verified via Network Health. Nagios initially omitted web02 immediately after the removal scan, then returned it Up with the other four targets on both J2-08 rescans; the persisted inventory never lost web02.
- The gateway's observed NAT ports were `SUGGESTED`, not `MONITORED`, because this fresh install had not enabled the corresponding plugins. The port-ownership check covered both states; no gateway-only ports appeared on web01. The issue's wrong-monitoring symptom was therefore not recreated as a monitored-port condition in this run.

## Follow-up

- No additional defect observed in this run. Browser UI actions were not driven; the saved settings and host detail endpoints were exercised through the API.

## Sanitization checklist

- [x] No passwords, tokens, keys, SNMP communities or private key paths
- [x] No addresses outside the documented lab range
- [x] Evidence is summarized rather than pasted
