# Issue #60: Make the Nagios check interval one system setting, and stop storing repeated status rows

Branch: `issue-60-check-interval`
Status: in-progress

## Finish condition

- [x] Repeated polls of an unchanged check add no rows (test)
- [x] Saving a new Check interval changes `check_interval` in generated `hosts.cfg` for hosts and services, through the shared writer (faked Nagios test)
- [ ] On the VM lab checks run at the new interval after save, and the config backup exists
- [ ] Failed validation or reload leaves the old interval running, restores the setting and shows the error (API rollback tested; live running-config proof pending)
- [x] Status text and stale fallback follow the setting
- [ ] Rows per host per hour measured on the VM lab before and after
- [x] Default Dashboard Refresh Rate hint follows Check interval; per-user rate unchanged (test)
- [x] `Data_Model_and_Integrations.md` documents the three rates and their relationship
- [x] `Display_Requirements.md` documents the hint and relationship

Requirement coverage (every requirement the issue states, and the check that proves it):

| Issue requirement | Finish-condition item | Proof (test or command) |
|---|---|---|
| A: store host/service result only on changed Last_Check | 1 | `server/tests/unit/test_status.py` |
| B: admin-only fixed-list setting, column/migration, host/service template and shared validate/backup/reload/rollback writer | 2, 3, 4 | settings/config tests, migration round trip, VM run |
| C: plugin status text and stale fallback | 5 | `server/tests/unit/test_plugin_services_api.py` |
| C: default hint follows check interval; per-user refresh and 60 s poller remain independent | 7 | frontend settings/context tests and unchanged scheduler |
| Document rates and relationship | 8, 9 | specs and `scripts/verify.sh docs` |
| VM checks and backups, rows/hour before and after | 3, 6 | sanitized `docs/test-runs/<date>-issue-60/REPORT.md` |
| Out of scope: change poller interval or per-user rate options/Nagios coupling | Out of scope | inspect `server/app/scheduler.py` and preference code |

## Plan

1. [x] Test repeated host/service polls then deduplicate by Last_Check in `server/tests/unit/test_status.py`, `server/app/nagios/status.py`.
2. [x] Test the fixed-list, authorized setting and rollback, then implement model, migration, API and shared writer/template generation in `server/tests/unit/test_settings_permissions.py`, `server/tests/unit/test_create_host_cfg.py`, `server/app/system_models.py`, `server/migrations/versions/`, `server/app/api/system/settings.py`, `server/app/network_discovery/host_config_templates.py`, `server/app/network_discovery/templates/{host,service}.cfg.tpl`, `server/app/network_discovery/create_host_cfg.py`.
3. [x] Test plugin status text and stale fallback, then implement in `server/tests/unit/test_plugin_services_api.py`, `server/app/api/plugin/service.py`.
4. [x] Test frontend setting, error display and refresh hint, then implement in `client/src/test/`, `client/src/types/settings.tsx`, `client/src/contexts/SystemSettingsContext.tsx`, `client/src/components/settings/{SystemSettings,GeneralSettings}.tsx`.
5. [x] Test documentation checks and update `spec files/{Data_Model_and_Integrations,Display_Requirements,Backend_Modules_and_Routes,Frontend_Modules_and_Routes,Implementation_Status}.md`; run `scripts/verify.sh docs`.
6. [ ] Run approved VM lab verification and rows/hour measurement; record sanitized `docs/test-runs/<date>-issue-60/REPORT.md` and index `docs/test-runs/README.md`.

## Round log

| Round | Change made | Check run | Result |
|---|---|---|---|
| resumed | Owner approved sensitive changes; installer issue requested before implementation | `git status --short` | clean |
| 1 | Filed installer prerequisite issue #4; added repeated-check host/service regression and deduplication | `python -m pytest server/tests/unit/test_status.py -q`; `scripts/verify.sh backend` | 17 passed; 2234 passed, 14 skipped |
| 2 | Added fixed-list system setting, migration, host/service template values and shared-writer save path | `python -m pytest server/tests/unit/test_create_host_cfg.py server/tests/unit/test_settings_permissions.py -q`; `scripts/verify.sh backend` | 72 passed; 2245 passed, 14 skipped |
| 3 | Made plugin waiting text and stale fallback read the Check interval | `python -m pytest server/tests/unit/test_plugin_services_api.py -q`; `scripts/verify.sh backend` | 69 passed; 2247 passed, 14 skipped |
| 4 | Wired settings UI and dynamic browser-refresh hint; displayed apply failures rather than conflict retry | `npm test -- --run src/test/SystemSettingsConflict.test.tsx`; `scripts/verify.sh frontend` | 7 passed; frontend verify initially 472 passed and build/lint green; targeted rerun after error handling green |
| 5 | Documented discovery vs Nagios checks vs polling vs browser refresh; corrected freshness contract | `scripts/verify.sh docs` | green (55 documents, routes and progress valid) |

## State for the next session

- Last check run (exact command): `scripts/verify.sh docs`
- Result (first failing lines, or "green"): green (55 documents, routes and progress valid)
- Hypothesis: Code and specs align for four schedules; migration upgrade and live Nagios behavior remain unverified.
- Next action (one specific step, not "continue"): Check VM-lab prerequisites and run the approved #60 cadence, backup, rollback and rows/hour measurement.

## Decisions and notes

- Issue finish condition now covers the previously missing hint and two specification updates. Owner comment asks whether deduplication already exists; inspected `server/app/nagios/status.py`: both insertion paths add rows unconditionally.
- The owner approved the sensitive Nagios configuration change and settings-column migration. No implementation attempted yet.
- The owner requests explicit documentation of discovery scan frequency versus data polling frequency. For freshness use the Nagios check interval plus the 60 s polling delay, not the discovery schedule; update Display Requirements §3.1 accordingly.
- Installer prerequisites were planned from its `setup/deploy-pinpoint-web.sh`, `setup/configure-pinpoint-privileges.sh`, and `setup/configure-nagios.sh`; filed https://github.com/lorraine-pangilinan/PinPoint-Installer/issues/4. The installer already migrates DBs and grants validate/reload, but its Nagios `interval_length=60` assumption needs live confirmation and upgrade acceptance. Do not add restart or a second writer.
- Injection/secret review to perform after approval: fixed integer whitelist before template formatting, no shell interpolation, no secret-bearing config or subprocess output in logs/progress, preserve shared writer's candidate validation and rollback.
