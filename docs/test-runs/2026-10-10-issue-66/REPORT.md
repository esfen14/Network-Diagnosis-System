# Test run: issue-66

| | |
|---|---|
| Date | 2026-10-10 |
| Commit tested | `c1f8fa74` (app source synced into fresh VM after baseline and failing repeat scan) |
| Plan | J2-09, J3-02 and J3-09 from `docs/qa/QA_Test_Plan.md` (PR #65); issue #66 |
| Tester | OpenCode agent, API and VM shell; browser UI not driven |
| Environment | VirtualBox `pinpoint-appliance-45`, Ubuntu 22.04.5, Nagios Core 4.5.11, five `demo/` targets on 10.77.0.0/28, fresh SQLite databases from `os-nagios-ready` snapshot |
| Raw evidence | Lab host: appliance `pinpoint-gunicorn` journal and SQLite inspection; console API/test transcripts were not persisted. No raw secrets are committed. |

## Result

**Overall: Pass for the issue #66 port and NCPA checks.** With narrow ports before the baseline scan, neither 8080 nor 2222 was recorded. After adding them to the saved scan settings, the pre-fix rescan ended Success but recorded neither. The synced fix recorded both on their original device IDs; range rescan retained both; legacy01 became eligible and deployment succeeded on SSH port 2222.

Totals: Pass 3, Fail 0, Blocked 0, Skipped 0.

## Cases

| Case | Result | Notes | Issue |
|---|---|---|---|
| J2-09 | Pass | On a fresh install, saved TCP `1-1024` before first scan. app01 (10.77.0.4, device 3) lacked 8080 and legacy01 (10.77.0.6, device 5) lacked 2222. Saved `1-1024,8080,2222`; pre-fix scan #2 returned Success/unchanged config but both ports remained absent. Appliance nmap3 confirmed both open. Synced `c1f8fa74`, rescanned (#3): `GET /api/system/hosts/3/ports` showed 8080/tcp HTTP and `/hosts/5/ports` showed 2222/tcp SSH; both IDs stayed stable. Changed to `1-1024,8000-8099,2200-2299`, rescanned (#4): Success, both ports remained. Settings PUT was observed; the appliance `CONFIGURATION_CHANGES` table recorded three `TCP_Ports` / `discovery_settings` edits. | [#66](https://github.com/esfen14/Pinpoint/issues/66) |
| J3-02 (legacy01) | Pass | NCPA target list included legacy01 after scan #3. `scripts/vmlab ncpa 10.77.0.2,10.77.0.6` verified SSH host key on 2222, trust, SSH login/sudo, successful two-device run in 150 seconds, and legacy01 `Deployed NCPA`; 16 checks passed, 0 failed. | |
| J3-09 (legacy01) | Pass | After the range rescan and NCPA deployment, database still showed exactly one ACTIVE device at 10.77.0.6 (ID 5), NCPA-eligible, with 2222/tcp; no duplicate record for that address. | |

## Deviations from the plan

- Set TCP `1-1024` and UDP `[161]` and only the lab network before the first scan to establish the absence of both ports and avoid the slow NAT scan. The first diagnostic install was inconclusive because its initial default scan had already recorded both ports; it was reverted before this run.
- First fresh-install attempt encountered an unrelated unattended-upgrades package lock; the successful install healthcheck reported 60 passed / 0 failed. This run used the subsequent fresh install and synced the pushed fix into that live instance after the failing rescan.
- The UI was not driven; Configuration Change was inspected in the appliance database rather than through the UI. The issue's requested API port and NCPA outcomes were observed.

## Follow-up

- The root cause was cloned SSH host keys on different MAC-addressed targets: identity reconciliation treated every observation sharing the key as a secondary address of the first device, discarding their port observations. The fix prefers an existing device with the observed hardware MAC at the observed address and adds a review item for the shared identity. New clone-key devices without a pre-existing address/MAC owner remain a separate ambiguity.
- Repeat J2-09 after PR #65's QA documents land on `main` to verify the documentation's Configuration Change detail and browser UI if desired.

## Sanitization checklist

- [x] No passwords, tokens, keys, SNMP communities or private key paths
- [x] No addresses outside the documented lab range
- [x] Evidence location named; raw transcripts and journal not pasted
