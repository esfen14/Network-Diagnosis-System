# Issue #62: Bring the QA journeys and test plans in line with the paper and ISO/IEC 25010:2023

Branch: `issue-62-qa-journeys-test-plan`
Status: in-progress
<!-- Status is one of: in-progress | blocked | ready-for-review -->

## Finish condition

- [x] Journeys document in `docs/qa/`, linked from `AGENTS.md`, updated for #45, lab runs, #61, SMTP move, #59/#60/#61, B10, final decisions
- [x] Repo specs aligned: Device_Inventory_Requirements in router and index, System Status kept (only topology view excluded), Settings tabs, paper-vs-code claims re-checked
- [x] `docs/qa/QA_Test_Plan.md`: J1-J9, X1-X6, PT-01..05, BB-01..07; stable IDs, ISO tag, coverage table, exclusions, fate of old plans, run outputs
- [x] Every case runnable by an agent from written steps; lab commands named; human cases marked (not yet proven by a dry run)
- [ ] Dry run of J2 and J3 from the plan alone recorded on the VM lab (`docs/test-runs/`)
- [x] Team decisions recorded (PT-04 clock, PT-05 4 h, roles from seed, plugins 65); availability formula still open
- [x] `scripts/verify.sh docs` passes (run with a python3 shim: only `python` exists on this Windows machine)

## Plan

1. [x] Read required specs, plans, lab plan, run reports; verify paper-vs-code claims
2. [x] Write `docs/qa/QA_Journeys_and_Scope.md` (folds section 8 into the body)
3. [x] Write `docs/qa/QA_Test_Plan.md` (84 cases + 7 BB aggregates)
4. [x] Router/index/spec edits: `AGENTS.md`, `spec files/README.md`, `docs/README.md`, `Agent_Workflow_and_CI.md`, `Frontend_Modules_and_Routes.md`, `Implementation_Status.md`
5. [x] Map old plans in `server/tests/plans/README.md` and plan section 7
6. [x] `scripts/verify.sh docs`
7. [ ] Dry run J2/J3 on the VM lab (needs the lab owner's machine: no vmlab state on this one)

## Round log

| Round | Change made | Check run | Result |
|---|---|---|---|
| 1 | Research only | | |
| 2 | Wrote journeys doc, test plan, router/spec edits | `scripts/verify.sh docs` | green |
| 3 | Opened PR as ready; CI `docs` failed only on the progress-file gate. Converted to draft; pushed this update to trigger a fresh run (a re-run reuses the old event data) | CI `docs` | pending |

## State for the next session

- Last check run (exact command): `PATH="$TEMP/shim:$PATH" bash scripts/verify.sh docs`
- Result (first failing lines, or "green"): green
- Hypothesis: n/a
- Next action: run J2-01..J2-09 and J3-01..J3-09 from `docs/qa/QA_Test_Plan.md` on the VM lab (`scripts/new_test_run.sh qa-dry-run-j2-j3 docs/qa/QA_Test_Plan.md`), fix any step that is not runnable as written, and record the report

## Decisions and notes

Owner decisions 2026-10-09 (relayed in the session): PT-04 clock starts at the Nagios
state change; PT-05 is a 4 h agent-run soak; role matrix comes from `seed.py`; plugin
count is 65 (observed in `docs/test-runs/2026-10-08-ncpa-run/`).

Open: BB-01..BB-07 wording is not in the repository (paper pp.67-68); the mapping in the
plan is inferred and BB-03 is a guess. One availability formula/window for Network Health
and Reports (D-9). PT-01 "initialisation" is defined by inference in the plan.
`gh` is not installed on this machine, so no PR can be opened from here; nothing has been
committed or pushed. Delete this file before the PR leaves draft.

Facts found while checking the code that differ from the source document: the Dashboard
host total includes the Nagios `localhost` (6, not 5); Manager and Staff are seeded with
no permissions; NCPA shows three services per host, not four; #45 is closed.
