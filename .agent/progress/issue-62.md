# Issue #62: Bring the QA journeys and test plans in line with the paper and ISO/IEC 25010:2023

Branch: `issue-62-qa-journeys-test-plan`
Status: in-progress
<!-- Status is one of: in-progress | blocked | ready-for-review -->

## Finish condition

- [x] Journeys document in `docs/qa/`, linked from `AGENTS.md`, updated for #45, lab runs, #61, SMTP move, #59/#60/#61, B10, final decisions
- [x] Repo specs aligned: Device_Inventory_Requirements in router and index, System Status kept (only topology view excluded), Settings tabs, paper-vs-code claims re-checked
- [x] `docs/qa/QA_Test_Plan.md`: J1-J9, X1-X6, PT-01..05, BB-01..07; stable IDs, ISO tag, coverage table, exclusions, fate of old plans, run outputs
- [x] Every case runnable by an agent from written steps; lab commands named; human cases marked (not yet proven by a dry run)
- [x] Dry run of J2 and J3 from the plan alone recorded on the VM lab (`docs/test-runs/2026-10-09-qa-dry-run-j2-j3/`): 13 pass, 1 fail, 6 not run; unrunnable steps fixed in the plan
- [x] Team decisions recorded (PT-04 clock, PT-05 4 h, roles from seed, plugins 65); availability formula still open
- [x] `scripts/verify.sh docs` passes (run with a python3 shim: only `python` exists on this Windows machine)

## Plan

1. [x] Read required specs, plans, lab plan, run reports; verify paper-vs-code claims
2. [x] Write `docs/qa/QA_Journeys_and_Scope.md` (folds section 8 into the body)
3. [x] Write `docs/qa/QA_Test_Plan.md` (84 cases + 7 BB aggregates)
4. [x] Router/index/spec edits: `AGENTS.md`, `spec files/README.md`, `docs/README.md`, `Agent_Workflow_and_CI.md`, `Frontend_Modules_and_Routes.md`, `Implementation_Status.md`
5. [x] Map old plans in `server/tests/plans/README.md` and plan section 7
6. [x] `scripts/verify.sh docs`
7. [x] Dry run J2/J3 on the VM lab (done 2026-10-09 on the owner's machine)
8. [ ] Owner decisions: run the cases left over (defects filed as #66 and #67); delete this file before the PR leaves draft

## Round log

| Round | Change made | Check run | Result |
|---|---|---|---|
| 1 | Research only | | |
| 2 | Wrote journeys doc, test plan, router/spec edits | `scripts/verify.sh docs` | green |
| 4 | Dry run of J1-01, J2, J3 on the VM lab; wrote the run report and index row; corrected J2-01, J2-03, J2-09, J3-05 and the lab notes in the plan | lab run (see report) | Partial: 13 pass, 1 fail, 6 not run |
| 5 | Resumed; pulled the dry-run commits; re-ran docs check | `scripts/verify.sh docs` | green |
| 3 | Opened PR as ready; CI `docs` failed only on the progress-file gate. Converted to draft; pushed this update to trigger a fresh run (a re-run reuses the old event data) | CI `docs` | pending |

## State for the next session

- Last check run (exact command): `PATH="$TEMP/shim:$PATH" bash scripts/verify.sh docs`
- Result (first failing lines, or "green"): green (re-run in round 5)
- Hypothesis: n/a
- Next action: confirm CI `docs` is green on the pushed branch, then ask the owner whether to run J2-05, J2-09, J2-10, J3-01, J3-04, J3-07, J3-08 in a second run; mark the PR ready only after the owner deletes this file

## Decisions and notes

Owner decisions 2026-10-09 (relayed in the session): PT-04 clock starts at the Nagios
state change; PT-05 is a 4 h agent-run soak; role matrix comes from `seed.py`; plugin
count is 65 (observed in `docs/test-runs/2026-10-08-ncpa-run/`).

Closed 2026-10-10: the paper's BB-01..BB-07 wording (pp.124-125) is now in the plan, BB-03 corrected; the mapping in the
plan is still the author's reading. Open: one availability formula/window for Network Health
and Reports (D-9). PT-01 "initialisation" is defined by inference in the plan.
Delete this file before the PR leaves draft.

Dry run (2026-10-09): the checkout was switched to `main` by someone else mid-run (stashes
exist in `git stash list`, made at 22:53 and 22:55 +0800, holding deletions of tracked files);
I did not touch them. The lab VM `pinpoint-appliance-45` needs `VMLAB_STATE_DIR` in the
environment. Two defects found and filed: #66 (J2-09: ports added to the scan settings after a
device is known are never recorded) and #67 (duplicate/identity corruption after removing a
network from discovery settings).

Facts found while checking the code that differ from the source document: the Dashboard
host total includes the Nagios `localhost` (6, not 5); Manager and Staff are seeded with
no permissions; NCPA shows three services per host, not four; #45 is closed.
