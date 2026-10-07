# Plugin Manager End-to-End Test Plan

**Status:** Draft for review. Layers 1 to 3 below have been run; the live lab (layer 4) has not.
**Test level:** Layered: scripted self-tests, the real app over HTTP, the live lab harness, and a browser check
**Code under test:** `main` at and after the merge of custom checks (`6cc36c26`), including the `check_ncpa.py`
name fix, the seven new registry plugins, device checks, server checks and passwords
**Design:** [`Custom_Checks_Plan.md`](../../../spec%20files/Custom_Checks_Plan.md),
[`Custom_Checks_Manual.md`](../../../spec%20files/Custom_Checks_Manual.md)
**Harness:** [`../e2e/network_discovery/`](../e2e/network_discovery/README.md), the same runner, lab, fixtures,
report and traceability as the plugin-driven monitoring acceptance run
**Related plans:** [`PLUGIN_DRIVEN_MONITORING_ACCEPTANCE_TEST_PLAN.md`](PLUGIN_DRIVEN_MONITORING_ACCEPTANCE_TEST_PLAN.md)
(enable, ports, permissions, failure injection),
[`CUSTOM_CHECKS_AND_NCPA_ACCEPTANCE_TEST_PLAN.md`](CUSTOM_CHECKS_AND_NCPA_ACCEPTANCE_TEST_PLAN.md) (the manual
lab checklist for the same features)

## 1. Purpose

Plugin Manager now does three things for a plugin: **enable** it (port-driven plugins), **add a check** of it on a
device or on the Nagios server (plugins discovery cannot attach to a port), and **keep a password** for it. This
plan states how each is proven and what result is expected, in the harness's own scenario and case style, so the
cases run without hand steps wherever the lab allows.

A case passes only when the **observed result equals the expected result written here**. A difference is a
defect: record it, do not change the expectation to fit.

Case IDs here start with `CK-` so they never collide with the `E-`, `O-`, `F-`, `L-`, `P-`, `R-` and `J-` cases
of the acceptance plan.

## 2. The four layers

| Layer | What it proves | Where it runs | State |
|---|---|---|---|
| 1. Scripted self-tests | Each scenario passes when the product behaves and says so when it does not | Anywhere, standard library only: `harness_plugin_manager_tests.py` (32 tests) | **Run: pass** |
| 2. The real app over HTTP | The scenarios agree with the real API, validation, permissions and encryption, with Nagios and the lab replaced | Anywhere with the app's test dependencies: `tests/unit/test_plugin_manager_scenarios_live_app.py` (10 tests) | **Run: pass** |
| 3. The application's own suites | The code behaves | `pytest tests/unit` and `npm test` | **Run: pass** (one known failure, see §8) |
| 4. The live lab | Nagios accepts the generated config, runs the checks, and the numbers are real | The lab server with `run_tests.py scenario` and the manual cases | **Not run** |

Layers 1 to 3 cannot show whether a real Nagios loads the file or reports a state. That is layer 4's job and the
reason two cases (CK-01 and CK-51) are marked blocking.

## 3. Scenarios and cases

Every harness scenario is in `config/plugin-scenarios.example.json` and implemented in `runner/scenarios.py`.
The **Layer 4 command** column is run with
`python runner/run_tests.py --config config/lab.json --scenarios config/plugin-scenarios.json scenario --run-id <id> --scenario <ID>`.

| Case | Harness scenario | What it covers | Needs |
|---|---|---|---|
| CK-01 | `CUSTOM-DEVICE` | A device check is added, written to `hosts.cfg`, accepted by Nagios, run, paused, resumed, removed | SSH target, key readable by the Nagios user |
| CK-06 | `CUSTOM-SURVIVES` | A rescan and a port plugin enable/disable leave the check alone | A fixture host |
| CK-10 | `CUSTOM-SERVER` | A server check needs no device, is written on `localhost`, and leaves `localhost.cfg` untouched | Nothing |
| CK-20 | `CUSTOM-RULES` | Bad requests are refused and nothing changes | A fixture host |
| CK-30 | `CUSTOM-PERMISSIONS` | Only `plugin.custom_check` opens the routes | Admin password; the permission synced |
| CK-40 | `CUSTOM-PASSWORD` | A password is encrypted at rest, never returned, kept on a blank change, removed with the check | `E2E_CHECK_PASSWORD`; `databases.system` |
| CK-50 | `REGISTRY-ENABLE` | The seven new registry plugins are recognised, previewed, enabled and disabled | Nothing |
| CK-51 | `NCPA-NAME` | `check_ncpa.py` is recognised, enabled, disabled and runs the `.py` file | Optionally a deployed NCPA agent |
| CK-60 | `PLUGIN-CLASSES` | Every plugin kind reports the class and note the drawer shows | Nothing |
| CK-70 to CK-75 | (browser) | The screens, light and dark, narrow and wide | A browser |

### CK-01 Device check lifecycle (`CUSTOM-DEVICE`, blocking)

1. The plugin (`check_by_ssh`) is not service-driven, offers device checks, and enabling it returns 409.
2. Add a check named `e2e ssh true` on `target01` with command `/bin/true`, user `pinpoint-test` and the identity file.

| Expected | The reply carries an id, `paused` false, and a service named `custom-by_ssh-e2e_ssh_true`. The live `hosts.cfg` has that service on the device's host with `check_command pinpoint_custom_check_by_ssh!…`. `nagios -v` passes. Within the timeout (default 7 minutes) the check's status leaves `waiting` and is `ok` |
|---|---|
| Then | **Pause**: `paused` true, the service is gone from `hosts.cfg`, pausing again reports `changed` false. **Resume**: the service is back. **Remove**: the check is no longer listed and the service is gone. `nagios -v` passes after each step |
| Fail if | Nagios rejects the file, the service is on another host, the state is not `ok`, or a paused check is still in `hosts.cfg` |
| Blocked if | `hosts.cfg` cannot be read, or the app lacks the scheduler and Nagios account so every check stays `waiting` (state it; do not call it a pass) |

### CK-06 A check survives other changes (`CUSTOM-SURVIVES`)

| Expected | After a **Rescan**, after enabling `check_ssh`, and after disabling and enabling it again, the check is still listed and its service is still in `hosts.cfg`; `nagios -v` passes |
|---|---|

### CK-10 Server check (`CUSTOM-SERVER`, blocking)

1. `check_uptime` offers server checks. Adding one **with** a device returns 400.
2. Add `e2e uptime` with no device.

| Expected | The reply's device is the Nagios server (no id), the service is named `server-uptime-e2e_uptime`, and it is in `hosts.cfg` on host `localhost` with `check_command pinpoint_custom_check_uptime!…`. The command has no `-H`. The status becomes `ok`. Pause, resume and remove behave as in CK-01. **`localhost.cfg` has the same SHA-256 before and after** (the runner checks this for every scenario) |
|---|---|
| Fail if | The service is under a device, `localhost.cfg` changed, or the product accepts a device |

### CK-20 Rules (`CUSTOM-RULES`, blocking)

| Request | Expected |
|---|---|
| Plugin that takes no custom check (`check_load`) | 400 |
| Missing required argument | 400 |
| Forbidden character (`a'b`) | 400, and the reply does not repeat `a'b` |
| An argument the plugin does not have | 400 |
| Device plugin with no device; server plugin with a device; unknown device | 400 each |
| Name with `/`, 61 characters, or empty | 400 each |
| `page=0` on the list | 400 |
| Change or remove a check that does not exist | 404 |
| The same name twice on one device | 400 on the second |
| After all of it | `hosts.cfg` has the same SHA-256 as before, and no check was left behind |

### CK-30 Permissions (`CUSTOM-PERMISSIONS`, blocking)

The harness creates two roles and accounts named `e2e-pdm-custom-viewer` (`system.hosts`, `plugin.view`) and
`e2e-pdm-custom-admin` (the same plus `plugin.custom_check`).

| Expected | Viewer: list, add, remove and device search return 403; the plugin's details still return 200 (CK-30). Permission holder: list and device search return 200, a bad add returns 400 (CK-31), and **enabling a plugin returns 403**, because `plugin.custom_check` grants no right to enable (CK-32). The roles are emptied and the accounts deactivated afterwards |
|---|---|

### CK-40 Passwords (`CUSTOM-PASSWORD`)

Set `E2E_CHECK_PASSWORD` to a throwaway value before the run. The scenario never writes it to evidence.

| Expected | The add reply and the list never contain the password; `secrets_set` names the password field and `secrets_readable` is true. The stored value in `system.db` contains `v1:` and not the password. `hosts.cfg` **does** contain the password in the check's command (Nagios needs it; this is documented) and on Linux its mode has no world-read bit (`hosts_cfg_mode` in the evidence). A **change with the password left blank** keeps it, in the list and in the command. For a plugin whose password is required, clearing it returns 400. After removing the check the database row and the password in `hosts.cfg` are gone, and `nagios -v` passes |
|---|---|
| Fail if | The password appears in any reply or in the database as text, a blank change drops it, or `hosts.cfg` is readable by every user |
| Blocked if | `E2E_CHECK_PASSWORD` or `databases.system` is missing |

### CK-50 New registry plugins (`REGISTRY-ENABLE`)

For `check_pgsql`, `check_ldap`, `check_ldaps`, `check_rpc`, `check_ircd`, `check_time` and `check_ntp_peer`:

| Expected | The plugin is service-driven, its enable preview says so, **Enable** succeeds and the plugin is Enabled or Active, `nagios -v` passes, and afterwards each is put back to the state it had |
|---|---|
| Note | The plugins attach only to ports of their kind. Lab fixtures for these services are not in the allow-list, so this case proves recognition and safe enabling, not that a service is created. Create a service by setting a port's service name with **Set service…** on a fixture port, if a listener is available |

### CK-51 `check_ncpa.py` (`NCPA-NAME`, blocking)

| Expected | The plugin stored as `check_ncpa.py` is found by `check_ncpa`, is service-driven, has class `service` and a category (the catalog lookup works). Enable succeeds, the plugin is Enabled or Active, and `nagios -v` passes. With `expect_services` true (an agent is deployed): services named `ncpa-…` are attached and the `pinpoint_nd_ncpa` command line runs `check_ncpa.py`. After the run the plugin is back to its earlier state |
|---|---|
| Not a code defect | `/usr/bin/env: 'python'` in the check output. Install a `python` command or point the file's shebang at `python3`, and record it as an environment finding |

### CK-60 Plugin classes (`PLUGIN-CLASSES`)

| Plugin | Class | Supported | Note |
|---|---|---|---|
| `check_ssh`, `check_ncpa.py` | `service` | no | (they are enabled, not checked) |
| `check_by_ssh`, `check_ping`, `check_radius` | `custom` | yes, target `device`, with fields | none |
| `check_apt`, `check_uptime` | `server` | yes, target `server` | none |
| `check_load` | `stock` | no | "Checks the Nagios server itself through Nagios Core. Not managed here." |
| `check_dhcp` | `advanced` | no | "Needs arguments Pinpoint cannot build yet." |
| `check_dbi` | `credentials` | no | "Its password cannot be passed to the plugin yet." |
| `check_cluster` | `unsupported` | no | an explanation |
| `check_ntp` | `replaced` | no | an explanation |

### CK-70 to CK-75 Browser

| Case | Expected |
|---|---|
| CK-70 Section placement | **Custom checks** (device) or **Server checks** (server) is below **Update** and above **Commands**, only for a user with `plugin.custom_check`, and only for plugins that take them |
| CK-71 Add dialog | No device picker for a server plugin; a device list that filters by name or IP for a device plugin; the **Add check** button stays disabled with the first problem as its tooltip until the form is valid; the amber SSH warning shows for `check_by_ssh` only |
| CK-72 Passwords | The password box is masked; the amber note about where passwords go is shown; on a change the box reads "Stored. Leave blank to keep it"; an optional stored password has a "Remove the stored …" box and a required one does not |
| CK-73 Status | Chips are Waiting (blue), OK (green), Warning (amber), Critical (red), Paused (grey); a check whose password cannot be read shows the red "can no longer be read" notice |
| CK-74 Layout | No horizontal scrolling at about 400 px or 1280 px, in light and dark; the three buttons wrap; the dialog scrolls when taller than the window |
| CK-75 Drawer notes | Each plugin kind shows the note in the table of CK-60; the old generic "does not check a service that discovery finds on a port" text appears only for a plugin the audit does not cover |

## 4. Environment and preconditions (layer 4)

Follow the harness README's mandatory handoff first. Then for these scenarios:

- The app runs the checked-out build on its own port and database, with `PINPOINT_SCHEDULER=1` and the Nagios API
  account, so checks leave `waiting`. `databases.system` in `config/lab.json` is that app's `system.db`, at the
  migration head (`b4e8d1a7c629`), and `plugin.custom_check` has been synced (`flask sync-permissions`).
- `nagios.host_config` is the live `hosts.cfg` the app writes and the harness can read; `nagios.localhost_config`
  is set so the SHA-256 guard is meaningful.
- For `CUSTOM-DEVICE` and `CUSTOM-SURVIVES`: the Nagios user can SSH to `target01` as `pinpoint-test` with the key
  named in `variables.identity`. Set that path in your private `config/plugin-scenarios.json`; the example value
  is a placeholder. This key belongs to the Nagios user on the lab server, not the dedicated test key under
  `PINPOINT_TEST_SSH_KEY`, which authenticates the harness, not Nagios.
- For `CUSTOM-PASSWORD`: `export E2E_CHECK_PASSWORD='<throwaway>'` in the protected `lab.env`. The password is never
  written to results.
- `hosts.cfg` should be readable only by the Nagios user and group before `CUSTOM-PASSWORD`.
- Never run these against production or the management network (the harness guards enforce this).

## 5. How to run

```bash
# Layer 1: no lab needed (from server/)
python tests/e2e/network_discovery/harness_plugin_manager_tests.py -v
python tests/e2e/network_discovery/harness_tests.py -v          # the original harness self-tests

# Layer 2 and 3: the application suites (from server/ and client/)
python -m pytest tests/unit/test_plugin_manager_scenarios_live_app.py -v
python -m pytest tests/unit -q ; (cd ../client && npm test)

# Layer 4: the lab (from server/tests/e2e/network_discovery, with lab.env sourced)
python runner/run_tests.py --config config/lab.json preflight
python runner/run_tests.py --config config/lab.json init-run --run-id ck-1
for S in PLUGIN-CLASSES REGISTRY-ENABLE NCPA-NAME CUSTOM-RULES CUSTOM-SERVER CUSTOM-DEVICE CUSTOM-SURVIVES CUSTOM-PERMISSIONS CUSTOM-PASSWORD; do
  python runner/run_tests.py --config config/lab.json --scenarios config/plugin-scenarios.json \
    scenario --run-id ck-1 --scenario "$S"
done
python runner/run_tests.py --config config/lab.json finalize --run-id ck-1 --traceability config/plugin-traceability.json
```

`--dry-run` after `scenario` prints a scenario's parameters and steps without running it. The scenarios restore
what they change in a `finally`, record Pass, Fail or Blocked, and leave the four inactive `e2e-pdm-*` roles and
accounts the permission cases use.

## 6. Traceability

| Objective (in `plugin-traceability.json`) | Cases |
|---|---|
| CK-1 A plugin discovery cannot attach can still be used | CK-01, CK-06, CK-10, CK-40 |
| CK-2 Server checks never touch Nagios Core's own config | CK-10 |
| CK-3 Bad input is refused and nothing changes | CK-20, CK-40 |
| CK-4 Custom checks need their own permission | CK-30 |
| CK-5 Registry additions, the `check_ncpa.py` fix and the plugin classes | CK-50, CK-51, CK-60 |

Blocking cases for the report: CK-01, CK-10, CK-20, CK-30, CK-51.

## 7. Results so far (2026-10-07)

| Layer | Result |
|---|---|
| 1. Scenario self-tests | 32 tests, all pass |
| 1. Original harness self-tests | 56 pass; 1 error (`test_rejection_wrapper_rejects_only_changed_candidates_while_flagged`), which writes a Windows path into a shell wrapper and was failing before this work; it passes only on Linux |
| 2. Scenarios against the real app | 10 tests, all pass: device, server, rules, permissions, password (optional and required), registry, `check_ncpa.py`, classes, manifest |
| 3. Backend suite | 2,162 passed, 24 skipped, 1 failed (`test_automation.py::TestSecurityCheck::test_flags_broken_plugins_and_logs_summary`, failing before this work, Windows-related) |
| 3. Frontend | 455 tests pass, `tsc` clean, `npm run build` succeeds |
| 4. Live lab | Not run |

Running the scenarios against the real app found one wrong expectation in the scenario (a holder of only
`plugin.custom_check` gets 403, not 409, on enable, because the permission is checked first). The scenario now
expects 403 and says that `plugin.custom_check` must not grant the right to enable.

## 8. Known gaps and risks

- **Nothing here has run on a real Nagios.** Layers 1 to 3 replace it. CK-01, CK-10 and CK-51 are the first to run.
- **`CUSTOM-DEVICE` and `CUSTOM-SURVIVES` depend on a key the Nagios user can read.** Without it the check goes
  `critical` with "Permission denied", which is correct behaviour but fails the case.
- **Retiring a device** (manual case C-12 in the acceptance checklist) leaves the check listed while its service
  leaves Nagios. The harness has no scenario for it; the design plan says retired devices' checks follow the retire
  rules, so the owner should decide whether the row should be removed.
- **The 1 known Windows-only failure** in each suite hides nothing here, but run the full suite on Linux before the
  lab run.
- **The registry plugins' services** cannot be created by the lab's allow-listed fixtures; CK-50 proves they are
  recognised and safe to enable, not that they check a real PostgreSQL or LDAP server.

## 9. Exit criteria

- Every case is Pass, or Fail with a defect logged and triaged, or Blocked with the reason stated.
- CK-01, CK-10, CK-20, CK-30 and CK-51 pass on the lab; they are the cases that decide whether the feature ships.
- `localhost.cfg` has the same SHA-256 at the end of the run (the report records it as `O-04`).
- No result, report or log contains a password.

## 10. Defect log

| ID | Case | Observed | Expected | Severity | Status |
|---|---|---|---|---|---|
| | | | | | |
