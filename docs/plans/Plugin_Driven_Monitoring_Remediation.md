# Plugin-Driven Monitoring Remediation

Source: the acceptance run `plugin-driven-monitoring-20261006` (tested commit `2b054050`, lab
`10.0.2.0/28`). 42 cases: 32 Pass, 2 Fail (O-03, L-08), 5 Blocked, 3 Skipped. Findings D-1 to D-8.

Status: **draft.** Code fixes are on branch `fix/plugin-monitoring-acceptance-defects`; none of
them has been re-run on the lab yet.

## 1. Findings and state

| # | Case | Type | Finding | State | Commit / owner |
|---|---|---|---|---|---|
| D-1 | E-00 | Test suite | `pytest tests/` failed at collection: two stray top-level tests, one with a missing import | Fixed: moved into `tests/unit/`, imports corrected | `1d906be7` |
| D-2 | O-03 | Product | Plugins had no description until a scan; `utils.sh` never got one | Fixed: list and detail fall back to the catalog; the scanner skips `utils.sh` (a shared library, not a plugin) | `1d906be7` |
| D-3 | L-08, O-8 | Product | Missing ports, Monitored ports with the plugin off, and Monitored ports with no Nagios service had no reason | Fixed: reason codes `missing`, `monitoring_inactive`, `service_missing`; shown in the Ports section | `1d906be7`, `bd18d08a` |
| D-4 | L-04 | Plan | Plan said the port "reflects the new service"; the spec keeps the service and raises `SERVICE_CHANGED` | Fixed in the plan | `b1e4e6ac` |
| D-5 | R-02, R-03 | Plan | Plan implied a blanket `nagios -v` failure | Fixed in the plan | `b1e4e6ac` |
| D-6 | C-00(c), C-11 | Plan | `grep` for `ARG[0-9]$` counted 3 command templates | Fixed in the plan: count inside `define service` blocks | `b1e4e6ac` |
| D-7 | L-06 | Behavior | Port-edit route lowercased `SSH`; settings API rejected it | Fixed: lenient everywhere (lowercased); dialog and Settings form too | `f6e1d2dc` |
| D-8 | ENV | Lab | `lab.env` `PINPOINT_TEST_SSH_KEY` points at the NCPA deploy key | Plan documents it; **the lab's `lab.env` still has to be corrected** | Lab owner |

## 2. Open work

### 2.1 Re-verify the fixes on the lab

| Check | What to confirm |
|---|---|
| L-08 | The MISSING port shows "Not seen lately..." and still has its Nagios service |
| O-03 | Descriptions show straight after an upgrade, before any scan; `utils.sh` is not listed as a new plugin |
| D-3 reasons | `monitoring_inactive` after disabling a plugin; `service_missing` after a rejected attach, cleared once discovery applies the service |
| D-7 | `SSH` is accepted and stored as `ssh` from the dialog, the port route and Settings |
| Counts | `pytest tests/` now collects 1928 tests and the backend suite expects 1915 passed, 14 skipped; update E-00 in the plan |

### 2.2 Cases the run could not complete

| Case | Needs | Objective left open |
|---|---|---|
| F-02, F-03 | Nagios API account and `PINPOINT_SCHEDULER=1` for live status chips | O-4 |
| P-03, U-01 | A browser run (reason text without an enable link; UI pass) | O-10 UI, UI stage |
| R-04 | NCPA deployed in the lab | O-9 |
| F-04 | A second SSH host | O-3 |
| J-01, J-02 | Time to run the journeys. **J-02 is a blocking case** | all |
| E-01 step 9 | The downgrade, on the backed-up dev DB | O-7 |
| Remaining C-cases | Not run in this pass | per plan §18 |

### 2.3 Loose ends

| Item | Direction |
|---|---|
| A database that already has a `utils.sh` plugin row | The scanner no longer adds it; decide whether to remove existing rows or leave them |
| `service_missing` right after Monitor | A port just marked Monitored shows it until the reconciler applies its service; confirm on the lab this does not read as an error |
| Plugin descriptions on upgrade | Fallback is display only; the stored `Description` is still null until a scan fills it |

## 3. Exit criteria

1. Section 2.1 passes on the lab with evidence stored beside the run.
2. F-02, F-03, P-03, U-01, J-01 and J-02 run, with the lab prerequisites in place.
3. `lab.env` corrected (D-8).
4. A new report shows no Fail and every blocking case passing.
5. `Implementation_Status.md` updated to match, and this file closed or removed.
