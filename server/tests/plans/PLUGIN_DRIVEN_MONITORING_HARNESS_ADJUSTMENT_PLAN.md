# Plugin-Driven Monitoring: E2E Harness Adjustment Plan

**Status:** Phases 1 to 5 implemented; harness self-tests pass (54). Not yet run live end to end. Phase 6 (browser) remains a separate plan.
**Deviation:** `restore_lab.py` stops fixtures but does not deactivate `e2e-pdm-*` accounts (it has no API login); the `PERMISSIONS` scenario deactivates them in teardown, and a leftover pair is cleaned by running that scenario again.
**Scope:** `server/tests/e2e/network_discovery/` only. No product code changes.
**Driven by:** [`PLUGIN_DRIVEN_MONITORING_ACCEPTANCE_TEST_PLAN.md`](PLUGIN_DRIVEN_MONITORING_ACCEPTANCE_TEST_PLAN.md) §14 and §14.1, and the
first live run (`~/pinpoint-test-results/plugin-driven-monitoring-20261006/`, 32 Pass, 2 Fail, 5 Blocked, 3 Skipped), which was done by hand
through the API because the harness could not run these cases.

## 1. Why the harness must change

| # | Gap found | Evidence |
|---|---|---|
| H-1 | `PinpointClient.apply_monitoring` and the `apply_monitoring` branch of `service-case` call `/api/plugin/targets`, `/configurations`, `/running`. All return 404 on this branch. | `runner/pinpoint.py:83-115`, `runner/run_tests.py:289-294`; live C-13 |
| H-2 | No client methods for the new routes: `enable-preview`, `<id>/services`, `services/stop`, `services/resume`, `hosts/<id>/ports` (GET/PUT). | `runner/pinpoint.py` |
| H-3 | Nothing guards `localhost.cfg` (O-6) or compares the enable preview with what was created (O-2, F-01). | no code |
| H-4 | No scenario runner, so mismatch, held-port, pin, rejected-config and permission cases (L-03..L-06, R-01..R-03, P-01..P-06) are manual only. | acceptance plan §14.1 |
| H-5 | The harness assumes a running app with scheduler and Nagios API account. Without them, services stay "Waiting" and `service-case` times out as a Fail instead of reporting Blocked. | live F-02/F-03 |
| H-6 | `preflight` does not catch the problems that cost most time live: Nagios binary not executable by the test user, `PINPOINT_TEST_SSH_KEY` pointing at the NCPA deploy key, target VMs off, app at a different revision from the checked-out branch. | live run |
| H-7 | `report.py` hard-codes the title and file name "Network Discovery Extended Test Report" and has no objective traceability. | `runner/report.py` |
| H-8 | No fixture control beyond allow-listed systemd units (`services/remote_service.py`), so second sshd on 80, plain HTTP on 8080 and the silent listener on 9100 need a human. | live L-01/L-03/L-06 |
| H-9 | `harness_tests.py` has apply tests (`test_apply_*`) that encode the removed flow. | `harness_tests.py:128-146` |

## 2. Principles

- Keep the existing safety model: reviewed manifests, allow-listed actions, credentials only from named environment variables, strict pinned host keys, no raw DBs or cookies in evidence, results written outside the repo.
- Every new check is written against a fake client first (offline, in `harness_tests.py`), then dry-run, then live.
- A case that cannot run because a prerequisite is missing is **Blocked** with the reason, never Fail and never a timeout.
- A successful API response alone is never a pass: confirm in Nagios (`status.dat` or `nagios -v`) as the harness already does.
- Case IDs in the ledger are the acceptance plan's IDs, so reports map to its traceability table without translation.

## 3. Phases

### Phase 0: decisions (needs the owner; see §6)

Decided: own-port branch app (1), scheduler and Nagios API account in the baseline (2), harness-created accounts (3), `lab.env` corrected (5). Open: archive-step approach (4, see §6.1).

### Phase 1: remove the stale flow, add the new client calls (fixes H-1, H-2, H-9)

| Change | File |
|---|---|
| Delete `apply_monitoring`. A manifest case that sets `apply_monitoring` is rejected with a clear `HarnessError` ("removed; monitoring follows from enabling"). | `runner/pinpoint.py`, `runner/run_tests.py` |
| Add `enable_preview(id)`, `plugin_services(id, search, page)`, `stop_service(id, device, proto, port)`, `resume_service(...)`, `device_ports(device_id)`, `set_port(device_id, proto, port, body)`, `disable_plugin(id)`. | `runner/pinpoint.py` |
| `service-case`: after enabling, wait for the service via `plugin_services` (exists, `monitored: true`), then keep the existing wait-for-state and `nagios.verify_services` cycle. Enable-only cases need no manifest flag. | `runner/run_tests.py` |
| Remove the `apply_monitoring` keys from `config/plugin-cases.example.json` if present. | `config/` |
| Replace `test_apply_*` with tests for the new calls and for the rejection of `apply_monitoring`. | `harness_tests.py` |

**Exit:** `service-case` passes MON-03/MON-04 per plugin on the lab with enable-only cases.

### Phase 2: guards and preflight (fixes H-3, H-5, H-6)

| Change | Detail |
|---|---|
| `localhost.cfg` guard | `nagios.py`: record the SHA-256 at `init-run`, re-check after every case and at `finalize`. Any change fails the run (O-6, O-04). |
| Preview equals result | New helper: GET `enable-preview`, enable, then compare `matched_services` and `matched_devices` with `plugin_services` total and distinct devices, and with `define service` count delta in `hosts.cfg` (O-02, F-01). |
| `nagios -v` after every mutating step | Reuse `nagios.validate`; record in evidence. |
| Preflight additions | (a) Nagios binary executable by the test user, else Blocked with the README ACL commands. (b) Warn when `PINPOINT_TEST_SSH_KEY` is the NCPA deploy key. (c) Target VMs running (`virsh list`) and reachable on 22. (d) App revision equals `git rev-parse HEAD` of the checkout (expose a version/commit, or compare `alembic current` with the head). (e) Status feed ready: scheduler on and Nagios API account set; otherwise mark status cases Blocked. |
| Status-feed fallback | Where Pinpoint's list cannot show state, still verify Nagios state from `status.dat` (already implemented in `nagios.verify_services`) and record the Pinpoint side as Blocked. |

**Exit:** preflight output names exactly what blocks which cases; a deliberately wrong lab config yields Blocked, not Fail.

### Phase 3: scenario runner (fixes H-4, H-8)

New subcommand `scenario --run-id <id> --scenario <ID>` driven by a reviewed `config/plugin-scenarios.json`. Each scenario lists fixture setup, steps, assertions and guaranteed teardown (like the existing stop/restore `finally`).

| Scenario | Covers | Notes |
|---|---|---|
| `PORT-FLAG` | L-03, L-04 | Second sshd on 80; assert recorded `ssh`, not monitored, expected `http`; acknowledge; assert monitored and log entry; replace with HTTP; assert ack cleared and `SERVICE_CHANGED` review item. |
| `PORT-HELD` | L-05 | Leave suggested; discovery; disable then enable; assert held and preview `held_ports`; monitor releases. |
| `PORT-GUESS` | L-01, L-02, L-07 | Silent listener on 9100; assert guess text, not attached by `check_tcp`; no UDP gets `check_tcp`. |
| `PORT-PIN` | L-06 | Pin, rescan, invalid names, unpin. |
| `PORT-LIFECYCLE` | L-08 | Close port, five scans to MISSING, reopen; after the fifth missed scan, wait the configured archive time, scan, then assert ARCHIVED and the service gone from Nagios. Preflight reads the app's setting and Blocks the archive step if it is still 30 days. |
| `REJECT-CONFIG` | R-01 to R-03, PM-07, PM-08 | See §4. |
| `STOP-RESUME` | F-06, C-14 | Stop, discovery does not re-attach, resume, double enable and disable. |
| `LOCALHOST` | O-04, C-12, C-13 | Hash unchanged, 409 for non-service plugins, removed routes 404. |

Fixtures: extend `services/remote_service.py` with an allow-list of **fixture listeners** (second sshd on 80, HTTP on 8080, silent 9100), each with `start`, `stop` and a verified-absent check. Nothing runs arbitrary remote commands. Add fixture removal to `cleanup/restore_lab.py` so recovery is idempotent.

### Phase 4: permission matrix (fixes P-01..P-06)

Decision 3: the harness creates its own roles and accounts. The API can create them (`POST /api/user/roles`, `POST /api/user/accounts`)
but has **no delete**, only deactivation (`PUT /roles/<id>/status`, `PUT /accounts/<id>`). The design therefore avoids leaving residue
that grows with every run:

- Fixed, recognisable names: roles `e2e-pdm-operator`, `e2e-pdm-viewer`, `e2e-pdm-enable-only`, `e2e-pdm-disable-only`, and one account per role
  (`e2e-pdm-<role>@<lab domain>`). Created once, **reused** on later runs (look up by name first), so the count never grows.
- Account passwords are generated per run in memory, set through the admin API, and never written to evidence or the ledger.
- Before each check the harness sets the role's permissions exactly (`PUT /roles/<id>`) and reads them back; a mismatch is Blocked.
- Teardown in `finally`: roles and accounts are set inactive and the role permissions emptied, so a leftover account can do nothing.
- Admin credentials come from the environment as today. The harness only touches objects whose names start with `e2e-pdm-`, and refuses to
  modify anything else.
- `restore_lab.py` deactivates any `e2e-pdm-` account or role left by an interrupted run.
- Assertions are the acceptance plan's P-01 to P-06 (ports GET/PUT, plugin list, enable, stop, resume status codes).

Risk accepted: the lab database keeps four inactive roles and accounts after the first run. Documented in the e2e README.

### Phase 5: reporting (fixes H-7)

| Change | Detail |
|---|---|
| Title and file name | Optional `report_title` and `report_name` in the config; defaults unchanged so the discovery harness output is identical. |
| Traceability | Optional `config/plugin-traceability.json` mapping objectives O-1..O-10 to case IDs; `report.py` appends the table and marks an objective Not met when no case passed. |
| Blocking cases | List the plan's blocking cases and their results. |
| Findings | Include `evidence/findings.md` when present (defect IDs, plan-wording issues), kept out of the pass/fail counts. |
| Checksums | Unchanged; written last. |

### Phase 6: browser runner (U-01, P-03)

Out of scope here. It is already proposed in `TEST_APPROACH_ADJUSTMENT_PLAN.md`; this plan only keeps the ledger and report compatible with it, so browser results can be appended with the same `CaseResult` format.

## 4. Rejected-config injection (REJECT-CONFIG)

The failure must reach the apply step, not the pre-check. A blanket failing `nagios -v` is stopped earlier by the enable pre-check (502, nothing attempted), so it does not test attach rollback. The harness therefore uses a **wrapper script** as `NAGIOS_BIN` that exits 1 only when a candidate `cfg_file` (argument 2 of `-v`) contains a marker service name, controlled by a flag file. The wrapper is generated by the harness into the run directory. Because the app reads `NAGIOS_BIN` at start, the lab owner starts the app under test with that wrapper (documented in the e2e README); preflight verifies it by calling the wrapper with the flag set and checking the exit code. If it is not in place, the scenario is Blocked.

## 5. Test strategy and definition of done

1. **Offline:** every new client call, guard and scenario step has a `harness_tests.py` case using the existing fake-client pattern; `python -m unittest harness_tests` and `vm_scripts/self_tests.py` pass.
2. **Dry run:** `--dry-run` prints each scenario's fixtures, requests and assertions without contacting the lab.
3. **Live:** run the full set against the lab and compare results case by case with the manual run in `plugin-driven-monitoring-20261006`; any difference is explained or fixed.
4. **Done when:** `service-case` and all scenarios run without hand steps, preflight reports blockers precisely, `localhost.cfg` guard and preview check run on every enable, the report carries traceability, and cleanup returns the lab to baseline.
5. **Docs:** update `e2e/network_discovery/README.md`, `server/tests/README.md`, the acceptance plan §14 and §14.1 (mark closed gaps), and `plans/README.md`. No spec-file change is needed because no product behaviour changes.

## 6. Decisions

| # | Question | Decision |
|---|---|---|
| 1 | Which app does the harness test? | **The checked-out branch on its own port.** `lab.json` gets `base_url` for it; preflight compares the app's Alembic revision with the checkout's head and Blocks on a mismatch. |
| 2 | Is a Nagios API account and `PINPOINT_SCHEDULER=1` part of the lab baseline? | **Yes.** The tester handoff and the e2e README add both; preflight Blocks status cases when either is missing. The app under test is started with `PINPOINT_SCHEDULER=1` and the account in its environment. |
| 3 | Operator and Viewer accounts? | **Created by the harness** (Phase 4: fixed `e2e-pdm-` names, reused, deactivated at teardown, because the API has no delete). |
| 4 | Archive step (30-day threshold) | **Option C, implemented.** `PINPOINT_PORT_ARCHIVE_AFTER_DAYS` (number above zero, fractions allowed, default 30) in `server/config.py`, with unit tests in `tests/unit/test_config.py` and a note in `Data_Model_and_Integrations.md`. The harness starts the branch app with a small value (for example `0.001`, about 90 seconds). Not yet exercised on the live lab. |
| 5 | Correct `lab.env`? | **Done:** `PINPOINT_TEST_SSH_KEY` now points at the dedicated test key (backup kept next to the file). Preflight still warns if the NCPA deploy key is used. |

### 6.1 Information for decision 4: testing the 30-day archive

What the step is: a MONITORED port that has been unseen for `PORT_MISSING_AFTER_SCANS` (5) scans becomes MISSING and stays monitored; once it has been
MISSING for `PORT_ARCHIVE_AFTER_DAYS` (30, hard-coded in `server/config.py`) it becomes ARCHIVED and its service leaves Nagios. L-08 asks the lab to show that end state.
The first four scans are quick to do live; waiting 30 real days is not possible.

What is already covered: `tests/unit/test_port_lifecycle.py` tests archiving with the threshold patched to 30 and with ports older and younger than it.
What is not covered: that the real lab shows the archived state, that the service actually leaves Nagios, and that the Ports section has no actions for it.

| Option | How | Pros | Cons |
|---|---|---|---|
| A. Skip on the lab | Record "Skipped due to resource limit" with the unit-test reference | No risk, no change | The Nagios removal and API state are never checked live |
| B. Backdate in a scratch DB | Harness edits `Closed_At` of the MISSING row directly (what I did by hand) | No product change; real code path runs | Writes to the app's database from outside the app, ties the harness to the schema, and is only safe when the harness owns the DB (own-port branch app with its own DB, per decision 1). Must never be done to a shared or deployed database |
| C. Make the threshold configurable | `PORT_ARCHIVE_AFTER_DAYS` read from an environment variable like the other settings in `config.py` (default 30); the lab app runs with `0` or `1` | Clean, no direct DB writes, also useful for other tests | A small product change (one line plus a spec note in Data_Model_and_Integrations.md), needs approval; a mis-set value in production would archive ports early, so it should reject values below 1 outside test |

Recommendation: **C** if you accept a one-line config change, otherwise **B** restricted to the branch app's own scratch DB; keep **A** as the default when neither is available.
Decided: **C**.

## 7. Order and effort

| Phase | Effort | Depends on |
|---|---|---|
| 1 Stale flow and client calls | S | none |
| 2 Guards and preflight | M | 1 |
| 3 Scenario runner and fixtures | L | 1, 2 |
| 4 Permission matrix | S | 1; decision 3 |
| 5 Reporting | S | none (can run early) |
| 6 Browser runner | separate plan | |

Recommended start: Phase 1 and Phase 5 together (small, independent, and Phase 1 restores a harness command that fails today), then Phase 2, Phase 4, Phase 3.

## 8. Risks

- Scenarios that start listeners as root on the targets widen the harness's remote reach. Mitigation: fixed allow-list, no free-form commands, teardown in `finally`, idempotent restore.
- The wrapper `NAGIOS_BIN` changes how the app under test runs. Mitigation: used only in the REJECT-CONFIG scenario, verified by preflight, never in a normal run.
- Tests that depend on scan timing (MISSING needs five scans) are slow; keep them in a separate scenario that can be skipped with a recorded reason.
- Harness changes must not alter discovery-plan results; defaults stay as they are and `harness_tests.py` keeps its existing cases.
