# Backend Test Failures — Tracking

Baseline run: 2026-09-26, branch `plugin-manager-final-phase`
Result: **117 failed, 894 passed, 3 skipped** (count fluctuates by 1 due to #1)
After #1, #3, #4, #5: 43 failed, 910 passed, 3 skipped
Current (everything fixed): **0 failed, 973 passed, 3 skipped**, stable across runs

Mark an item `[x]` once fixed and note whether the **test** or the **code** was changed.

---

## 0. Live system checks (before the tests)

### Device discovery
- [x] **D1. `system.db` has no discovered devices**
  `NETWORK_DISCOVERY` and `NETWORK_DISCOVERY_STATUS` were empty — discovery had
  never run against this `system.db`. Nagios still monitored 28 hosts from old configs.
  - Resolution: **ran discovery via the API** (`POST /api/system/discover/start` as
    admin@test.com) on 2026-09-26 10:48. Finished 10:51, status SUCCESS,
    "New host.cfg successfully applied". Result: 8 devices, 6 TCP / 1 UDP open ports.
    Nagios reloaded and polls the new host set.
  - Note: only 8 devices because `config.py` has `NETWORKS = ["192.168.130.0/24"]`.
    The old `10.10.99.x` hosts came from a different subnet config and are no longer
    monitored (previous hosts.cfg was backed up by the discovery run).
  - Still open: `scanFrequency` is not scheduled — discovery is manual only.

- [x] **D3. Device Inventory routes listed in AGENTS.md don't exist** — *won't restore*
  `GET /system/hosts` and `/hosts/<id>/ports/tcp|udp` were removed in d65942b1.
  - Resolution: **docs** — decision is to follow what's in the system. Restored
    routes were reverted; AGENTS.md §2/§5/§6/§7 rewritten from `app.url_map`
    (adds `/api` prefix, history, plugin, NCPA, log, report, user routes; notes
    there is no discovered-devices route).

- [x] **D2. `SYSTEM_SETTINGS` table is empty**
  The singleton row is missing, so `_purge_old_data` in `app/scheduler.py`
  returns early (retention purge never runs).
  - Root cause: `seed_system_settings()` in `app/api/commands/seed.py` was defined
    after the try/except and never called — `flask seed` never created the row.
  - Resolution: **code** — moved to a top-level helper and called from
    `seed_command`. Live `system.db` row created (defaults: scan 6h, log 30d,
    diagnostics 90d). Backup taken first. New `tests/test_seed.py` (3 tests).
    Note: the Settings API still lazily creates the row too (`settings.py`).

### Scheduler
- [x] **S1. Poll job runs** — 97 snapshots in `history.db` from 08:57 to 10:32, once per minute. Works.

### Parser (`app/nagios/status.py`) — compared against live `statusjson.cgi`
- [x] **P1. Every service is stored as `UNKNOWN`**
  Nagios sends lowercase `"ok"` / `"warning"` / `"critical"` / `"unknown"`;
  `convert_service_state_type_enum` only maps `"0"-"3"`, `"Ok"`, `"OK"`, etc.
  and falls back to UNKNOWN.
  - Resolution: **code** — mapping is now case-insensitive (`converter.py`).
    Live poll verified: 69 OK / 12 CRITICAL / 20 UNKNOWN (all UNKNOWN are P6 UDP).
- [x] **P2. Perf data never stored (0 rows in both perf tables)**
  Parser reads `performance_data`; Nagios field is `perf_data`
  (status.py:91, 152).
  - Resolution: **code** — reads `perf_data`. Live poll verified: perf rows now stored
    (e.g. localhost PING rta=0.05ms warn=100 crit=500).
- [x] **P3. `Max_Attempts` always 3**
  Parser reads `max_attempt`; Nagios field is `max_attempts` (status.py:69, 134).
  - Resolution: **code** — reads `max_attempts`. Live poll verified (localhost services = 4).
- Regression tests: new `tests/test_status.py` (6 tests) + lowercase cases in
  `test_converter.py::TestConvertServiceStateTypeEnum`. All pass with the scheduler
  stubbed; **flaky under plain `pytest` until #1 is fixed** (poller races the test DB).
- [x] **P4. `Check_Command` always NULL**
  `statusjson.cgi` servicelist does not include `check_command` (it lives in
  `objectjson.cgi`). Needs a separate lookup or accept NULL.
  - Resolution: **code** — new `get_check_commands()` in `app/nagios/status.py`
    fetches `objectjson.cgi?query=servicelist&details=true` once per poll and
    `get_status()` merges each service's `check_command` in before insert (only the
    command name is stored, as before). New config `NAGIOS_OBJECT_URL`. If the
    lookup fails the poll still stores rows with `Check_Command` NULL
    (`_plugin_key` falls back to the service name). Live lookup verified
    (e.g. localhost `Current Load` → `check_local_load`). 5 new tests in
    `test_status.py`.
- [x] **P5. `convert_plugin_status_type_enum` falls back to `OK`** for unrecognised
  values (converter.py) — should probably be `UNKNOWN`. Check before changing.
  - Resolution: **code + test** — checked: the only caller (`status.py`) passes
    `_extract_plugin_status()` output, which is always a mapped keyword, so nothing
    relied on the `OK` fallback. Now case-insensitive with an `UNKNOWN` fallback,
    matching `convert_service_state_type_enum`. `test_converter.py` updated.
- [x] **P6. UDP service checks misconfigured (config generation, not parser)**
  All `*-UDP` services output "With UDP checks, a send/expect string must be
  specified." — generated `check_udp` commands lack `-s`/`-e`.
  - Findings (2026-09-26): the UNKNOWNs came from the pre-discovery config
    (`running-host-config-backup/host-26-09-2026-10-51.cfg`: 10× domain-53,
    7× snmp-161, 1× ntp-123, all bare `check_udp!<port>`). The current registry
    (18a528b7) maps those to `check_dns` / `check_snmp` / `check_ntp_time`;
    `check_dns` verified OK against 192.168.130.1. Current scan: only UDP 53 on
    `_gateway` is open.
  - Live scan of 192.168.130.0/24 + 10.10.99.0/24: the generic `check_udp` reports
    CRITICAL even on working SNMP/DNS ports (an empty datagram is not a valid
    request), while `check_snmp`/`check_dns` return OK on the same ports.
  - Resolution: **code** — decision: skip UDP ports with no plugin (after
    `UDP_SERVICE_OVERRIDES`) and record them. `build_host_services()` no longer
    generates the generic `check_udp`, also not as a fallback when a UDP plugin
    can't be configured; TCP unchanged. Each skip is stored in the new
    `SKIPPED_SERVICE` table (`system_models.SkippedService`, linked to the
    discovery run) via `create_skipped_service_logs()`, returned as
    `details.skipped_services` by `GET /api/system/networkdiscovery`, and listed in
    the System Logs detail panel. Live `system.db`: table created (backup
    `system.db.bak-2026-09-26-skipped-service`). New `tests/test_skipped_services.py`
    (5) + 6 new/updated tests in `test_create_host_cfg.py`; `system.logs` added to
    the conftest permission list.
  - Also: live `hosts.cfg` (generated 10:51) has no `define service` blocks — it
    predates 0cca29a0. Re-run discovery to regenerate it.

---

## A. Test infrastructure

- [x] **1. Nagios poller runs during tests (flaky)**
  `app/__init__.py:40` calls `init_scheduler()` at import, so the background
  poller writes to the test DB before tables exist ("no such table:
  HOST_STATUS / SERVICE_STATUS"). Caused a setup error on
  `test_monitoring.py::TestDashboardHostsEndpoint::test_dashboard_hosts_invalid_state`.
  - Resolution: **code** — `init_scheduler()` returns early when `app.testing`
    (conftest sets TESTING before import). New `tests/test_scheduler.py`.
    Two full runs now give identical results (101 failed / 909 passed), no
    "no such table" errors.

- [x] **2. "Working outside of application context" (16 tests)**
  Helpers called directly without an app context.
  - `test_validation.py` — `TestValidatePassword` (6), `TestValidateJsonData` (3),
    `TestValidateJsonFields` (2), `TestValidateUserEmail` (1)
  - `test_plugin_monitoring_config.py::TestEnsureCfgFileDirective` (4)
  - Resolution: **test** — `test_validation.py` helpers now run inside an app
    context; `TestValidatePassword` uses `db_session` because `validate_password`
    reads the Strong Password Policy flag from `SYSTEM_SETTINGS` (no row → strict
    policy, which the tests expect). `TestEnsureCfgFileDirective` fixed in 0cca29a0.
    A `try/except RuntimeError` workaround that had been added to
    `settings_flags._get_settings()` was reverted — production code should not
    swallow a missing app context.

## B. 404s — likely stale URLs

- [x] **3. `test_monitoring.py` — all 57 tests**
  Tests hit `/api/monitoring/*` (alerts, alerts/current, notifications,
  notifications/current, network-health, dashboard, dashboard/hosts,
  dashboard/services). Current routes live under `/system/dashboard/*` and
  `/system/network-health/*`.
  - `TestMonitoringAuthGuards` (8), `TestMonitoringPermissionGuards` (8)
  - `TestAlertsEndpoint` (4), `TestAlertsCurrentEndpoint` (2)
  - `TestNotificationsEndpoint` (4), `TestNotificationsCurrentEndpoint` (1)
  - `TestNetworkHealthEndpoint` (12), `TestDashboardEndpoint` (3)
  - `TestDashboardHostsEndpoint` (6), `TestDashboardServicesEndpoint` (9)
  - Resolution: **test removed** — the `/api/monitoring` blueprint was deleted in
    5a5427d0 (2026-08-22, "removed dashboard and network health from api, replaced
    with statistics in system api"); `monitoring.*` permissions are unused by the app.
    Its replacements are already covered by passing tests incl. 401/403 guards:
    test_dashboard (46), test_network_health (25), test_network_hosts (45),
    test_network_services (51), test_history (65), test_notifications (26).
    Restore with `git checkout HEAD -- server/tests/test_monitoring.py`.

- [x] **4. `test_inventory.py` — 14 tests return 404**
- [x] **5. `test_inventory.py` — `TypeError: argument of type 'NoneType'` (2 tests)**
  - Resolution: **test removed** — the whole file tested `/api/system/inventory/*`,
    routes that no longer exist (see D3). `tests/test_inventory.py` deleted
    (`git rm`; restore with `git checkout HEAD -- server/tests/test_inventory.py`).

## C. Response shape mismatch

- [x] **6. `test_management.py` — 12 tests**
  Payload now nested under `data`; `KeyError` on `items` / `page` / `id` /
  `previous_status` / `first_name`.
  - `TestPermissionsOptions` (1), `TestRolesList` (4), `TestRolesOptions` (1),
    `TestRoleInfo` (1), `TestRoleStatusToggle` (1), `TestAccountsList` (2),
    `TestAccountInfo` (1), `TestMeEndpoint` (1)
  - Resolution: **test** — read payload from `resp.get_json()["data"]` (standard envelope).

- [x] **7. `test_ncpa.py` — 5 tests**
  `KeyError: 'devices'` / `'rejected'` (likely same nesting).
  - `TestNcpaEligibleDevices` (2), `TestDeployNcpaStart` (2), `TestTrustedDevices` (1)
  - Resolution: **test** — same envelope fix as #6.

## D. One-off logic / signature mismatches

- [x] **8. `test_auth.py::TestLogin::test_login_already_logged_in`**
  Expects "already" in message; got `"user logged in."`
  - Resolution: **code** — `login.py` returns "User already logged in." when
    `current_user.is_authenticated` instead of re-running `login_user`.

- [x] **9. `test_converter.py::TestConvertAcknowledgementTypeEnum` (2 tests)**
  `test_invalid_raises_attribute_error`, `test_display_value_raises` —
  `DID NOT RAISE AttributeError`.
  - Resolution: **test** — aligned to the none/normal/sticky ack mapping from 5cbd26fb (fixed in 0cca29a0).

- [x] **10. `test_converter.py::TestConvertToUTC::test_unix_timestamp`**
  Got 1970-01-20 instead of 2023-11-14 — seconds vs. milliseconds.
  - Resolution: **test** — Nagios sends ms timestamps; test now uses ms (fixed in 0cca29a0).

- [x] **11. `test_create_host_cfg.py::TestCreateHostCfgFile::test_each_host_gets_only_its_own_services`**
  `KeyError: 'host-a'` — possibly from commit 6109a08e (removed service
  declaration in `create_host_cfg.py`).
  - Resolution: **code** — `create_host_cfg` service generation restored (fixed in 0cca29a0).

- [x] **12. `test_create_host_cfg.py::TestCreateHostCfgFile::test_commands_defined_once_for_used_plugins_only`**
  No commands generated: `[] == ['pinpoint_nd...point_nd_ssh']`.
  - Resolution: **code** — Define Commands section restored in `create_host_cfg` (fixed in 0cca29a0).

- [x] **13. `test_create_host_cfg.py::TestServiceStatusCheckCommand` (2 tests)**
  `test_only_command_name_is_stored`, `test_missing_check_command_stored_as_null` —
  `insert_service_status_data()` now requires a `data` argument.
  - Resolution: **test** — passes `hostname` to `insert_service_status_data` (fixed in 0cca29a0).

- [x] **14. `test_plugin_enable_disable.py::TestEnablePlugin::test_enable_no_nagios_binary`**
  Got 200, expected 502.
  - Resolution: **test** — tests assumed Nagios is not installed; this host has it.
    They now point `app.config["NAGIOS_BIN"]` at a nonexistent path
    (was the `NAGIOS_BINARY_PATH` constant, moved to config on `integration`).

- [x] **15. `test_plugin_enable_disable.py::TestNagiosValidator::test_returns_false_when_binary_missing`**
  Validator returns `True` when the binary is missing.
  - Resolution: **test** — tests assumed Nagios is not installed; this host has it.
    They now point `app.config["NAGIOS_BIN"]` at a nonexistent path
    (was the `NAGIOS_BINARY_PATH` constant, moved to config on `integration`).
