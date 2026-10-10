# Issue #60: Make the Nagios check interval one system setting, and stop storing repeated status rows

Branch: `issue-60-check-interval`
Status: blocked

## Finish condition

- [ ] Repeated polls of an unchanged check add no rows (test)
- [ ] Saving a new Check interval changes `check_interval` in generated `hosts.cfg` for hosts and services, through the shared writer (faked Nagios test)
- [ ] On the VM lab checks run at the new interval after save, and the config backup exists
- [ ] Failed validation or reload leaves the old interval running, restores the setting and shows the error
- [ ] Status text and stale fallback follow the setting
- [ ] Rows per host per hour measured on the VM lab before and after
- [ ] Default Dashboard Refresh Rate hint follows Check interval; per-user rate unchanged (test)
- [ ] `Data_Model_and_Integrations.md` documents the three rates and their relationship
- [ ] `Display_Requirements.md` documents the hint and relationship

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

1. [ ] Test repeated host/service polls then deduplicate by Last_Check in `server/tests/unit/test_status.py`, `server/app/nagios/status.py`.
2. [ ] Test the fixed-list, authorized setting and rollback, then implement model, migration, API and shared writer/template generation in `server/tests/unit/test_settings_permissions.py`, `server/tests/unit/test_create_host_cfg.py`, `server/app/system_models.py`, `server/migrations/versions/`, `server/app/api/system/settings.py`, `server/app/network_discovery/host_config_templates.py`, `server/app/network_discovery/templates/{host,service}.cfg.tpl`, `server/app/network_discovery/create_host_cfg.py`.
3. [ ] Test plugin status text and stale fallback, then implement in `server/tests/unit/test_plugin_services_api.py`, `server/app/api/plugin/service.py`.
4. [ ] Test frontend setting, error display and refresh hint, then implement in `client/src/test/`, `client/src/types/settings.tsx`, `client/src/contexts/SystemSettingsContext.tsx`, `client/src/components/settings/{SystemSettings,GeneralSettings}.tsx` (actual matching test files to identify before editing).
5. [ ] Test documentation checks and update `spec files/{Data_Model_and_Integrations,Display_Requirements,Backend_Modules_and_Routes,Frontend_Modules_and_Routes,Implementation_Status}.md`; run `scripts/verify.sh docs`.
6. [ ] Run approved VM lab verification and rows/hour measurement; record sanitized `docs/test-runs/<date>-issue-60/REPORT.md` and index `docs/test-runs/README.md`.

## Round log

| Round | Change made | Check run | Result |
|---|---|---|---|

## State for the next session

- Last check run (exact command): `git status --short`
- Result (first failing lines, or "green"): green (clean branch before progress file)
- Hypothesis: The settings/UI/config writer and migration need an explicit sensitive-module and existing-data approval before code changes. The display spec currently calls scanFrequency a freshness threshold, whereas this issue would use Check interval.
- Next action (one specific step, not "continue"): Ask the owner to approve the sensitive Nagios configuration change and existing-database migration, and resolve the §3.1 freshness rule; then start plan step 1.

## Decisions and notes

- Issue finish condition now covers the previously missing hint and two specification updates. Owner comment asks whether deduplication already exists; inspected `server/app/nagios/status.py`: both insertion paths add rows unconditionally.
- `app/network_discovery/` is sensitive under Engineering Standards §Sensitive modules, and a new `SystemSettings` column requires migrating existing databases. Workflow §4 requires a person before this change. No implementation attempted.
- `Display_Requirements.md` §3.1 currently treats `scanFrequency` (discovery schedule) as a freshness threshold; the issue calls for check interval to govern checks. Need explicit decision whether §3.1 should use check interval (possibly accounting for the 60 s poll delay).
- Injection/secret review to perform after approval: fixed integer whitelist before template formatting, no shell interpolation, no secret-bearing config or subprocess output in logs/progress, preserve shared writer's candidate validation and rollback.
