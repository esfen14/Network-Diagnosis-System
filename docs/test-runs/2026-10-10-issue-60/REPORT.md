# Test run: issue-60

| | |
|---|---|
| Date | 2026-10-10 |
| Commit tested | app `bcf5f614`; installer `2859361` |
| Plan | Issue #60 finish condition; isolated appliance clone of `os-nagios-ready` |
| Tester | OpenCode agent |
| Environment | Ubuntu 22.04 installer-built VirtualBox appliance; fresh install on isolated clone, `interval_length=60`; demo targets on documented `10.77.0.0/28` lab range. Baseline is a separate existing pre-#60 appliance, so the rows/hour comparison is indicative rather than a controlled before/after on one database. |
| Raw evidence | Local host `/tmp/opencode/vmlab-60-{fresh,deploy,privileges,health,smoke}.log` (not committed); appliance databases and Nagios files remain on the isolated VM. |

## Result

**Overall: Partial.** The fresh appliance accepted the new setting, validated/reloaded generated host and service definitions, and retained its prior settings/config on injected validation and reload failures. Ten-minute row-count windows show deduplication, but a controlled full-hour baseline and after window on one appliance was not captured. The smoke harness timed out waiting for discovery, which later completed successfully; the harness timing is not a product failure.

Totals: Pass 4, Fail 0, Blocked 0, Skipped 1.

## Cases

| Case | Result | Notes | Issue |
|---|---|---|---|
| Fresh install prerequisites | Pass | Fresh installer migrated the new system column; appliance `interval_length=60`; health check 60 passed, 0 failed. Initial installer attempt hit a transient unattended-upgrade dpkg lock, then the same deploy steps succeeded. | #60 |
| Save new interval, generated objects and backup | Pass | Authenticated system API changed 5 to 2 minutes (HTTP 200). Live `hosts.cfg` had seven host and twelve service objects, all with interval 2; backup directory contained the previous interval-5 config. Host checks at 11:19:58, 11:21:58, 11:23:58 UTC and service checks at 11:20:58, 11:22:58, 11:24:58 UTC demonstrate steady 120-second spacing after reload. | #60 |
| Validation failure rollback | Pass | Injected invalid directive into Nagios main configuration, then attempted 10-minute save. HTTP 422 showed validation failure. Restored the main config in a `finally` cleanup. System setting stayed 2, live `hosts.cfg` digest stayed unchanged, daemon active. | #60 |
| Reload failure rollback | Pass | Temporarily removed only the appliance's Pinpoint reload sudoers grant, then attempted 10-minute save. HTTP 422 showed rollback; restored sudoers in a `finally` cleanup. Setting stayed 2, live `hosts.cfg` digest matched its prior value, daemon active. Following both injections, host `Last_Check` advanced at 11:30:03, 11:32:03 and 11:34:03 UTC, confirming the old 2-minute cadence kept running. | #60 |
| Rows per monitored host per hour, before and after | Skipped | Ten-minute 11:20–11:30 UTC windows: pre-#60 appliance six generated hosts each had 9 rows (54 total, extrapolated **54 rows/host/hour**); isolated #60 appliance six generated hosts had 4–5 each (28 total, extrapolated **28 rows/host/hour** at 2-minute checks). Five service objects on the new appliance had 4–6 rows (25 total, extrapolated **30 rows/service/hour**); old appliance had no matching generated service checks, so no service before/after comparison. These are two different VMs at different intervals, and extrapolation is not a measured full hour. An exact paired full-hour measurement remains unverified. | #60 |

## Deviations from the plan

- An isolated clone was used so another issue's running appliance and work were not overwritten. NAT ports were remapped on the clone; private connection details are not included here.
- The standard smoke harness timed out after 300 seconds while nmap discovery was still progressing. Database status subsequently became `SUCCESS` and generated hosts/services were checked directly.
- No full-hour pre/post measurement or upgraded-appliance migration was run. The fresh installer migration succeeded; upgrade safety remains tracked by the installer prerequisite issue.

## Follow-up

- Defects found: none attributed to issue #60 in this run. Installer prerequisite: https://github.com/lorraine-pangilinan/PinPoint-Installer/issues/4.
- Cases to repeat: controlled full-hour row measurement, ideally on the same appliance at matching check cadence.

## Sanitization checklist

- [x] No passwords, tokens, keys, SNMP communities or private key paths
- [x] No addresses outside the documented lab range
- [x] Evidence is referenced by name and location, not pasted
