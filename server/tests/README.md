# Backend Test Suite

**Last verified against the repository:** 2026-10-04

**Current isolated collection:** 1,590 collected tests

This directory contains the pytest suite for the Flask backend. It covers API
authorization and contracts, database models, Nagios parsing and aggregation,
network discovery, NCPA deployment, scheduled automation, and Plugin Manager
workflows.

The draft live-lab plan is in
[`plans/NETWORK_DISCOVERY_EXTENDED_TEST_PLAN.md`](plans/NETWORK_DISCOVERY_EXTENDED_TEST_PLAN.md).
Its opt-in automation lives under
[`e2e/network_discovery/`](e2e/network_discovery/). That harness is separate
from normal pytest collection and must never run during installation or
application startup.

The exact number of collected tests will change as parametrized cases and new
features are added. Use `pytest --collect-only` when an exact current count is
needed.

## Directory boundaries

| Directory | Purpose |
|---|---|
| `unit/` | Isolated regression suite, including unit tests and mocked Flask API/database integration tests; these are not all pure unit tests |
| `integration/` | Explicitly selected live Nagios CGI tests; not full end-to-end acceptance |
| `e2e/network_discovery/` | Opt-in live harness, fixtures, recovery scripts and self-tests; the complete deterministic browser runner remains proposed |
| `support/` | Shared isolated builders and migration subprocess helper |
| `plans/` | Proposed test approach, live test plan and historical findings |

`server/pytest.ini` defaults to `unit/` and prevents recursive collection of
`integration/` and `e2e/`, even with `pytest tests/`. Explicitly targeting
`tests/integration/` still works and may contact Nagios during collection.
`server/conftest.py` remains the shared fixture entry point.

See [test plans](plans/README.md) and the
[proposed approach adjustment](plans/TEST_APPROACH_ADJUSTMENT_PLAN.md).

## Quick start

Run commands from `server/`, which contains the root `conftest.py`.

Install the backend and test dependencies into the existing virtual environment:

```bash
.venv/bin/pip install -r requirements.txt -r requirements-test.txt
```

Run the default isolated suite (live tests are excluded):

```bash
.venv/bin/python -m pytest tests/ -v
```

Run the normal isolated suite without probing a live Nagios server:

```bash
.venv/bin/python -m pytest tests/unit/
```

Run one module, class, test, or keyword selection:

```bash
.venv/bin/python -m pytest tests/unit/test_notifications.py -v
.venv/bin/python -m pytest tests/unit/test_notifications.py::TestGetNotifications -v
.venv/bin/python -m pytest tests/unit/test_notifications.py::TestGetNotifications::test_requires_login -v
.venv/bin/python -m pytest tests/ -k "login" -v
```

List tests without executing them:

```bash
.venv/bin/python -m pytest tests/ --collect-only -q
```

## Test-suite map

Basenames below live under `unit/`, except `integration/test_live_nagios.py`.

### Authentication, users, roles, settings, and shared helpers

| File | Coverage |
|---|---|
| `test_auth.py` | Login/logout success, invalid credentials/input, inactive users, and authentication guards |
| `test_management.py` | Permission options, role CRUD/status, account CRUD/status, and `GET /api/user/me` |
| `test_session_timeout.py` | Cookie-backed idle timeout, activity refresh, logout cleanup, and configured/default timeout values |
| `test_settings_permissions.py` | General/security/system settings authorization and inactive-role permission behavior |
| `test_seed.py` | System-settings creation and idempotence through the `flask seed` command |
| `test_converter.py` | State conversion, UTC/UNIX conversion, performance-data parsing, date ranges, and email normalization |
| `test_validation.py` | Password, JSON-body, field, and email validation helpers |

### Dashboard, health, history, notifications, and reports

| File | Coverage |
|---|---|
| `test_dashboard.py` | Dashboard auth guards, monitoring status, summary, active alerts, acknowledgement workflows, and recent notifications |
| `test_network_health.py` | Summary, trend windows/buckets, plugin grouping, last-scan metadata, and auth guards |
| `test_network_hosts.py` | Latest-host listing/filtering/pagination, host details, and host acknowledgement |
| `test_network_services.py` | Latest-service listing/filtering/pagination, service details, slash-containing names, and service acknowledgement |
| `test_statistics.py` | Latest-state aggregations, counts, active alerts, ping/NCPA averages, Nagios-server resources, plugin groups, and trends |
| `test_history.py` | Alert/notification history lists and details, filters, pagination, acknowledgement annotation, and auth guards |
| `test_notifications.py` | Notification feed, unread count, per-user cursor, and mark-read behavior |
| `test_report_notifications_alerts.py` | Nagios-backed alert and notification report periods, filters, response shapes, and upstream failures |
| `test_status.py` | Nagios status/object CGI parsing, state mapping, performance data, max attempts, and safe check-command storage |
| `integration/test_live_nagios.py` | Optional real-Nagios CGI and Flask-route integration checks |

### Network discovery, generated monitoring, NCPA, and scheduling

| File | Coverage |
|---|---|
| `test_network_discovery.py` | Discovery start/stop/status endpoints and job-state guards |
| `test_create_host_cfg.py` | SNMP/NCPA/TCP/UDP service planning, per-host isolation, service naming, config generation, and stored command names |
| `test_plugin_registry.py` | Plugin resolution, variable validation, command rendering, SNMP checks, and NCPA checks |
| `test_skipped_services.py` | Persistence and log presentation for discovered ports that cannot become monitored services |
| `test_ncpa.py` | Eligible/trusted devices, SSH fingerprint confirmation, deployment start/stop/status, and validation |
| `test_automation.py` | Due-time helpers, automation-user selection, maintenance mode, backups, discovery/update scheduling, and security checks |
| `test_scheduler.py` | Scheduler suppression in the test environment and initialization behavior |

### Plugin Manager

| File | Coverage |
|---|---|
| `test_plugin_models.py` | Plugin, version, command override, dependency, configuration, and history ORM behavior |
| `test_plugin_command_defaults.py` | Curated defaults for the bundled plugin catalog |
| `test_plugin_descriptions.py` | Generated description/category/documentation catalog (coverage, limits, generator freshness), `--help` fallback parsing, fill-if-empty rules, scanner backfill, and the plugin detail fields |
| `test_plugin_scanner.py` | Filesystem scanning, executable detection, inventory synchronization, scan routes/status, and real permission checks where supported |
| `test_plugin_service.py` | Inventory, summary, details, history, commands, and dependency read APIs |
| `test_plugin_enable_disable.py` | Enable/disable transitions, Nagios validation, history, rollback behavior, and permission guards |
| `test_plugin_command_management.py` | Command override/restore routes, validation, immutable originals, and audit history |
| `test_plugin_validation.py` | Executable, permission, execution, and dependency checks plus validation-state transitions |
| `test_plugin_custom.py` | Custom-plugin upload staging, validation, collision handling, install rollback, and atomic registration |
| `test_plugin_update.py` | Download URL/SSRF protection, safe archive extraction, update workflow, failure state, and manual rollback |
| `test_plugin_reconcile.py` | The plugin reconciler: attaching discovered ports of enabled plugins, idempotence, disable/enable, manual rows untouched, the monitoring server, writer failures and rollback, and the callers that trigger it |
| `test_upgrade_rehearsal.py` | A populated pre-upgrade database taken through every migration, the first reconcile, a downgrade and an upgrade again: monitoring survives, nothing is duplicated, no look-alike manual rows after a downgrade |
| `test_plugin_scale.py` | 300 devices / 3,600 services: reconcile and services-list correctness and loose time limits |
| `test_promotion_hold.py`, `test_promotion_hold_migration.py` | Held ports: an admin's Suggested is respected, an upgrade starts nothing new, how a hold is released, the enable preview's held count, and the migration's data step |
| `test_plugin_services_api.py` | Service-driven plugins, the enable preview, a plugin's monitored services with live status, stop/resume of one port, disable rollback, and the removed manual routes |
| `test_plugin_config_migration.py`, `test_port_service_map_migration.py`, `test_retire_permission_migration.py` | Alembic round trips with populated data for the plugin-driven monitoring migrations |

## Test environment

### Root `conftest.py`

`server/conftest.py` configures the application before it is imported:

1. It points the default and `history` binds at in-memory SQLite databases.
2. It sets `TESTING=True`, disables CSRF, and supplies a test secret key.
3. It prevents the application scheduler from starting during tests.
4. It creates and drops both binds for every test through `db_session`.
5. It provides users, roles, permissions, and authenticated test clients.

No real `system.db` or `history.db` file should be changed by the isolated
suite.

### Shared fixtures

| Fixture | Provides |
|---|---|
| `app` | Session-scoped configured Flask singleton |
| `client` | Unauthenticated Flask test client |
| `db_session` | Fresh default and history database schemas, dropped after the test |
| `seeded_permissions` | All names in `PERMISSION_NAMES`, returned as a name-to-model mapping |
| `admin_role` | Active role containing every test permission |
| `regular_role` | Active limited role containing only `system.inventory` |
| `admin_user` | Active administrator account |
| `regular_user` | Active limited account |
| `inactive_user` | Inactive account used by authentication tests |
| `logged_in_client` | Client authenticated as `admin_user` |
| `limited_client` | Client authenticated as `regular_user` |

Fixtures are function-scoped unless their decorator says otherwise. Because
`db_session` creates and drops the complete schema, tests that touch models or
routes should request it directly or indirectly through another fixture.

### Realistic monitoring seed helpers

`tests/support/seed_helpers.py` creates realistic host, service, performance, and
program snapshots for dashboard/network-health tests. Prefer these helpers when
the behavior depends on relationships across several history models.

### Temporary files and mocked infrastructure

Filesystem-heavy Plugin Manager and Nagios-config tests use pytest's `tmp_path`
and redirect application configuration to temporary directories. External
processes, SSH, Nagios CGI requests, and network scanning are mocked unless a
test explicitly exercises a safe local file/permission operation or belongs to
`test_live_nagios.py`.

Patch a dependency where the module under test looks it up:

```python
from unittest.mock import patch

with patch(
    "app.api.system.history.request_alerts_range",
    return_value=[],
):
    response = logged_in_client.get("/api/system/history/alerts")
```

Patching only the dependency's original definition may not replace a name that
the route module imported earlier.

## Live Nagios integration tests

`test_live_nagios.py` is the only test module intended to contact a real
Nagios installation. At collection time it probes both `statusjson.cgi` and
`archivejson.cgi`; all of its tests are skipped if either endpoint is
unreachable.

Configure and run it explicitly:

```bash
NAGIOS_URL=http://nagios-host/nagios \
NAGIOS_USER=nagiosadmin \
NAGIOS_PASSWORD=secret \
.venv/bin/python -m pytest tests/integration/test_live_nagios.py -v
```

The module uses bounded CGI time windows and request timeouts. Some assertions
may skip when the live instance has no recent alerts. A notification route case
is marked expected-failure because large Nagios notification histories can time
out.

Do not put real credentials in source, test output, or documentation.

## Live Network Discovery lab

`plans/NETWORK_DISCOVERY_EXTENDED_TEST_PLAN.md` defines the resource-constrained
VirtualBox test of real Network Discovery mappings and selected additional
Nagios checks. `e2e/network_discovery/` is reserved for its explicitly invoked
provisioning, service-control, polling, evidence, reporting, and cleanup tools.
Its [README](e2e/network_discovery/README.md) documents configuration,
self-tests, isolated/offline test-dependency setup, guarded execution, recovery,
report generation, and SCP retrieval. The harness self-tests use `unittest` and
do not require pytest; the application regression gate still uses the pinned
packages in `requirements-test.txt`.

The disposable nested-VM provisioner is under
[`e2e/network_discovery/vm_scripts/`](e2e/network_discovery/vm_scripts/README.md).
Its own README documents the libvirt networks, cloud image, previews,
verification, baselines, and generated SSH/harness artifacts.

Before handing a live run to the AI, the tester can preview and apply the
consolidated privileged host preparation:

```bash
cd /opt/pinpoint/Network-Diagnosis-System/server/tests/e2e/network_discovery
bash provision/prepare_test_host.sh
sudo bash provision/prepare_test_host.sh --apply
```

The script performs only the reviewed ACL, exact-command sudoers, protected
runtime-path, existing-libvirt-startup, and validation steps. It never installs
missing plugins, runs discovery, reloads Nagios, or creates VMs.

The live lab is not part of the isolated pytest suite. It may create disposable
guests or containers, scan an isolated subnet, alter test-only Nagios
configuration, stop services, and reload Nagios. Read and approve the plan and
the harness configuration before running it.

## Adding or updating tests

1. Name new isolated modules `test_<feature>.py` under `server/tests/unit/`.
2. Add a new route permission to `PERMISSION_NAMES` in `server/conftest.py`
   when the administrator fixture must receive it.
3. Cover authentication, authorization, validation, success, empty-data, and
   upstream-failure behavior that applies to the feature.
4. Assert the standard API envelope as well as feature-specific data.
5. Mock Nagios, SSH, scans, subprocesses, remote downloads, and production
   filesystem paths.
6. For database writes, assert rollback/atomicity when a later operation fails.
7. Run the focused module, then the isolated suite.
8. Update this README when a new test module or testing convention is added.

A typical protected route test includes:

```python
class TestMyRoute:
    def test_requires_login(self, client, db_session):
        response = client.get("/api/system/my-route")
        assert response.status_code in (401, 302)

    def test_requires_permission(self, limited_client, db_session):
        response = limited_client.get("/api/system/my-route")
        assert response.status_code == 403

    def test_happy_path(self, logged_in_client, db_session):
        response = logged_in_client.get("/api/system/my-route")
        assert response.status_code == 200
        body = response.get_json()
        assert body["success"] is True
```

## Related files

- `server/requirements-test.txt` pins pytest and pytest-flask.
- `server/tests/plans/historical/TEST_FAILURES.md` is a historical remediation log. Its counts
  are not the current suite inventory.
- `spec files/Engineering_Standards.md` contains repository-wide testing rules.
- `spec files/Backend_Modules_and_Routes.md` is the current API route catalog.

### Live-report regression coverage (2026-10-03)

The live harness now requires plugin enabling through actual Plugin Manager APIs
before discovery. Its manifest includes an enable/apply/running case and separate
NCPA CPU, memory and disk acceptance. Harness self-tests cover enable gating, exact
inventory lookup, pending/stale checks, titlecase states and baseline inventory.
The extended plan tracks reload rollback, NCPA deployment/path failures, missing
installed permissions and lifecycle thresholds from the previous live report.
No live outcome is implied by passing these isolated self-tests.
