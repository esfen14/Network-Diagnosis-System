# Bug Findings — Network Discovery & Plugin Monitoring Config
**Date:** 2026-09-26  
**Branch:** `plugin-manager-final-phase`  
**Test run:** `pytest tests/test_network_discovery.py tests/test_create_host_cfg.py tests/test_plugin_registry.py tests/test_plugin_scanner.py tests/test_plugin_monitoring_config.py tests/test_plugin_service.py`  
**Result:** 144 passed, **8 failed**

---

## Summary

| # | File | Class | Failing Tests | Root Cause |
|---|------|-------|---------------|------------|
| 1 | `app/network_discovery/create_host_cfg.py` | `TestCreateHostCfgFile` | 2 | `build_host_services()` never called in host loop — no `define service` or `define command` blocks written |
| 2 | `tests/test_create_host_cfg.py` | `TestServiceStatusCheckCommand` | 2 | Test calls `insert_service_status_data(service, data)` but the function signature requires `(hostname, service, data)` |
| 3 | `tests/test_plugin_monitoring_config.py` | `TestEnsureCfgFileDirective` | 4 | `ensure_cfg_file_directive()` called outside a Flask app context — `current_app` is unbound |

---

## Bug 1 — `_create_host_cfg_file` does not emit service or command blocks

**File:** `server/app/network_discovery/create_host_cfg.py`  
**Function:** `_create_host_cfg_file(discovered_hosts)`  
**Failing tests:**
- `TestCreateHostCfgFile::test_each_host_gets_only_its_own_services`
- `TestCreateHostCfgFile::test_commands_defined_once_for_used_plugins_only`

### What the code does now

The function initialises `plugin_facts = load_host_plugin_facts()` and `used_plugins = set()` at the top of the host loop, then iterates hosts and writes only `define host` blocks. Neither `build_host_services()` nor `render_command_definition()` is ever called. The `used_plugins` set stays empty and the `plugin_facts` dict is never consumed.

```python
# Current (broken) host loop — services never generated
for hosts in discovered_hosts.values():
    for ip, host_data in hosts.items():
        host_config.append(create_host(host))
        host_config.append(_add_space(4))
        # Assigns hostgroup's list to be used in creating hostgroups
        host_config.append(_add_space(4))
        # <-- build_host_services() should be called here
```

### What it should do

For each host, call `build_host_services(host_data, plugin_facts, current_app.config)` to resolve each discovered port into `(service_name, check_command, plugin_name)` tuples, write a `define service` block for each via `create_service()`, collect the plugin name in `used_plugins`, then — after the host loop — write one `define command` block per used plugin via `render_command_definition()`.

### Test error
```
KeyError: 'host-a'
# services_by_host() found no define service blocks at all, so the dict is empty
```

### Fix required (production code)

In `_create_host_cfg_file`, inside the inner `for ip, host_data in hosts.items()` loop, add:

1. A call to `build_host_services(host_data, plugin_facts, current_app.config)`.
2. For each `(service_name, check_command, plugin_name)` returned, append a `create_service(...)` block and add `plugin_name` to `used_plugins`.
3. After both loops, append a `# Define Commands` section and write one `render_command_definition(plugin)` block per entry in `used_plugins`.

---

## Bug 2 — `insert_service_status_data` called with wrong number of arguments

**File:** `server/tests/test_create_host_cfg.py`  
**Class:** `TestServiceStatusCheckCommand`  
**Failing tests:**
- `TestServiceStatusCheckCommand::test_only_command_name_is_stored`
- `TestServiceStatusCheckCommand::test_missing_check_command_stored_as_null`

### What the tests do now

```python
# Current (broken) — 2 positional args
insert_service_status_data(
    "ncpa-cpu-5693", self.service_payload("pinpoint_nd_ncpa!5693!secrettoken!cpu/percent!")
)
```

### What the function signature actually is

```python
# server/app/nagios/status.py
def insert_service_status_data(hostname, service, data):
    ...
```

The function takes **three** positional arguments: `hostname`, `service` (the service description string), and `data` (the payload dict). The test passes only two — a service name and the payload — omitting `hostname`.

### Test error
```
TypeError: insert_service_status_data() missing 1 required positional argument: 'data'
```

### Fix required (test code only)

Update both test calls to pass a `hostname` as the first argument:

```python
# Fixed — 3 positional args
insert_service_status_data(
    "host-b",
    "ncpa-cpu-5693",
    self.service_payload("pinpoint_nd_ncpa!5693!secrettoken!cpu/percent!")
)

insert_service_status_data(
    "host-b",
    "ssh-22",
    self.service_payload(None)
)
```

---

## Bug 3 — `ensure_cfg_file_directive()` called outside a Flask app context

**File:** `server/tests/test_plugin_monitoring_config.py`  
**Class:** `TestEnsureCfgFileDirective`  
**Failing tests:**
- `TestEnsureCfgFileDirective::test_adds_directive_when_missing`
- `TestEnsureCfgFileDirective::test_idempotent_second_call_no_duplicate`
- `TestEnsureCfgFileDirective::test_creates_empty_service_cfg_if_missing`
- `TestEnsureCfgFileDirective::test_backs_up_nagios_cfg_before_modifying`

### What the tests do now

Each test uses `_patched_config(app, **paths)` as a context manager, which calls `app.config.update(overrides)`. This updates the config dict but does **not** push a Flask application context. `ensure_cfg_file_directive()` calls `current_app.config` internally, which requires an active app context.

```python
# Current (broken) — config patched but no app context pushed
def test_adds_directive_when_missing(self, app, tmp_path):
    paths = _patch_nagios_paths(tmp_path)
    with _patched_config(app, **paths):
        result = ensure_cfg_file_directive()   # RuntimeError here
```

### Test error
```
RuntimeError: Working outside of application context.
```

### Fix required (test code only)

Wrap each `ensure_cfg_file_directive()` call in `app.app_context()`, nested inside the existing `_patched_config` block:

```python
# Fixed — app context pushed first, then config patched inside it
def test_adds_directive_when_missing(self, app, tmp_path):
    paths = _patch_nagios_paths(tmp_path)
    with app.app_context():
        with _patched_config(app, **paths):
            result = ensure_cfg_file_directive()
    assert result is True
    ...
```

Apply the same `with app.app_context():` wrapper to all four tests in this class.

---

## Plugin Import from `/usr/local/nagios/libexec/` — PASS

Tested separately via direct Python invocation and via the live API:

- `/usr/local/nagios/libexec/` exists and contains 114 items.
- The scanner (`scanner.py`) detected **101 executable files**.
- All `check_*` plugins imported at **v2.4.12** (plus `check_ncpa.py` at v1.2.5, `check_ssl_validity` at v5.38.2).
- `POST /api/plugin/scan` returned `202` and completed with status `"Success"`.
- Final inventory: **101 plugins added**, 0 updated, 0 unchanged.

**Note:** The scanner also picks up non-plugin executable files that are present in `libexec/` (e.g. `configure`, `Makefile.am`, `AUTHORS`, `README`). These are source/build artefacts that should not be in `libexec/` in a clean production install. They are registered with `version unknown` and do not affect monitoring functionality, but they pollute the plugin inventory.

---

## Network Discovery — Not fully testable in this environment

`POST /api/system/discover/start` triggers a live nmap scan. The configured networks are defined in `server/config.py`. The discovery pipeline itself (`discover_network_create_hosts`) runs correctly up to `_create_host_cfg_file`, where Bug 1 means the generated `.cfg` file will contain `define host` blocks but **no** `define service` or `define command` blocks. This means Nagios would monitor host up/down state but would not run any plugin checks on discovered services until Bug 1 is fixed.
