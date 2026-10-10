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

### Phase 0: approved execution plan (2026-10-11)

- [x] Restore in-flight TCP settings and verify web02 SSH listener before new tests.
- [x] Finish J2-09 with a guarded lab-only scan; restore original settings (Partial: port refresh observed, first insertion not proven).
- [x] Re-observe duplicate records, check fix ancestry and search issues before linking findings (#86).
- [x] Correct J2-05/J3-02 wording only where supported by spec and source (J3-02 already correct).
- [x] Record the handoff and new observations in an indexed second-run report.
- [x] Verify docs, checkpoint, clean up the throwaway checkout after pushing (owner waived review stop).

### Phase 1: #62 and #82 (PR #65)

- [x] 1.1 Merge origin/main, preserve both sides' docs, verify docs, update snapshot SHA (semantic reconciliation tracked below).
- [x] 1.2 Inspect merged specs/tests and record new-feature coverage inventory here.
- [ ] 1.3 Update journey cases and ISO coverage in both QA documents.
- [ ] 1.4 Correct installer/app SMTP ownership and add in-repo email cases.
- [ ] 1.5 Add runnable controlled full-hour #82 case; leave measurement pending.
- [ ] 1.6 Link QA docs from spec index; file rename follow-up; ensure needs-decision label.
- [ ] 1.7 Record unresolved owner decisions in draft; retain draft status.
- [ ] 1.8 Record/defer additional lab coverage honestly; no fresh reset without approval.
- [ ] 1.9 Re-read issues, prove requirements, run docs/all verification; keep PR draft and progress while blocked.

## Round log

| Round | Change made | Check run | Result |
|---|---|---|---|
| Phase 1 / 2 | Resumed inventory; inspected regression coverage; corrected premature current-status claims to draft reconciliation pending | `scripts/verify.sh docs`; source/spec/test inspection | docs green; case changes next, no runtime pass inferred |
| Phase 1 / 1 | Merged main at a55ae595, preserved report index rows | `scripts/verify.sh docs` | green; merge f9271feb, semantic drift remains for next steps |
| Phase 0 / 2 | Guarded scan 6; restored settings; indexed second report; corrected J2-05; filed #86 | API ports/status/settings; merge-base ancestry; `scripts/verify.sh docs` | Partial lab evidence; docs verification recorded below |
| Phase 0 / 1 | Resumed; restored TCP ports, confirmed web02 listener, moved issue branch to released lab checkout; returned PR #65 to draft | discovery status/settings API; appliance TCP probes; `scripts/verify.sh docs` | green; run 5 terminal; ports restored at version 3; no new scan |
| 1 | Research only | | |
| 2 | Wrote journeys doc, test plan, router/spec edits | `scripts/verify.sh docs` | green |
| 4 | Dry run of J1-01, J2, J3 on the VM lab; wrote the run report and index row; corrected J2-01, J2-03, J2-09, J3-05 and the lab notes in the plan | lab run (see report) | Partial: 13 pass, 1 fail, 6 not run |
| 5 | Resumed; pulled the dry-run commits; re-ran docs check | `scripts/verify.sh docs` | green |
| 3 | Opened PR as ready; CI `docs` failed only on the progress-file gate. Converted to draft; pushed this update to trigger a fresh run (a re-run reuses the old event data) | CI `docs` | pending |

## State for the next session

- Last check run (exact command): `scripts/verify.sh docs`
- Result (first failing lines, or "green"): green (Phase 1 inventory resume, Linux; 61 documents).
- Hypothesis: merged branch still has semantic documentation drift; source/test inventory identifies changes needed, not runtime passes.
- Next action: implement step 1.3 case/journey updates from the inventory, inspect Forgot Password source before asserting its flow, then step 1.4 SMTP wording; retain owner questions and draft status.

## Decisions and notes

### Phase 1 coverage inventory (2026-10-11; inspection, not test passes)

Merged `origin/main` at `a55ae595` in `f9271feb`. Docs verification passes, but a
clean textual merge is not semantic agreement: the old branch retained stale Email,
Forgot Password, Settings and #66 wording. Reconcile these in steps 1.3/1.4 before
claiming the QA documents are current. Prior final message overstated completion of
the specification updates; status headers now explicitly say draft/reconciliation pending.
Current working checkout is `Network-Diagnosis-System-qa-62`; the throwaway lab
worktree and its `qa/issue-62-lab` branch were removed after pushing the report.

| Feature on main | Inspected source/spec and regression evidence | Journey/invariant | Case state / action |
|---|---|---|---|
| #61 first-run gate and optional first-sign-in password change | Backend route catalog `complete-setup`; `server/tests/unit/test_admin_setup.py` gate, validation, contact update and checkbox tests; `server/app/api/user/management.py` | J1, J9 | Placeholder is J1-07, NOT J1-03 as execution snapshot says. Replace it; extend J9-02/J9-07 with default true, false opt-out, reset still forces change. No email deliverability assertion |
| #59 repeated-discovery identity | Data spec discovery; `test_device_identity.py::Test...` tests `test_address_unknown_host_reactivates_when_seen_again_at_same_ip`, `test_a_rescan_at_the_same_address_adds_no_rows`; discovery start lock source | J2-08, J3-09, X3 | Cases exist; remove stale open-#59 wording, link closed fixes and new #86 persistence finding; do not treat inherited duplicate state as a clean baseline |
| #66 ports added on known devices | Data spec cloned-key/MAC reconciliation; `test_device_identity.py` `test_known_clone_key_hosts_keep_new_tcp_ports` | J2-09 | Exists; mark retest, restore main's issue-66 report reference; distinguish insertion from refreshing already-present ports |
| #67 removed-network identity | Device Inventory AC35; `test_device_identity.py` `test_removed_network_device_not_reassigned_to_hosts_in_scanned_network`, `test_devices_on_networks_that_were_not_scanned_are_left_alone` | J2 | Add J2-11; use MOCK regression for multiple networks outside permitted VM scan scope, no NAT-range scan |
| #60 check interval / status dedup | Data spec Monitoring schedules; `test_settings_permissions.py` interval validation/permission/apply/rollback; `test_create_host_cfg.py` interval rendering; `test_status.py` same-check tests for hosts/services | J7, X3, PT | Add J7-09 setting/rollback and refresh hint; PT-06 controlled measurement. Dedup key is Last_Check, NOT state/output change; unchanged state on a new check still records a row |
| #72 super-admin protection | `management.py` rejects Suspended/Inactive and inactive role; `test_management.py` `test_super_admin_cannot_be_suspended_or_inactivated`, `test_other_accounts_can_still_be_suspended` | J9 | Add J9-10, assert 400 and unchanged Active state; preserve ability to suspend other users |
| PR #81 Settings Email | Backend SMTP route catalog; `test_smtp_settings.py` save/version/helper failure/secret handling/send-error tests; `EmailSettings.tsx`; frontend permission rules | J5, B8 | Replace stale not-built email case; Gmail-only STARTTLS 587; settings.email gate; test HTTP 200 may carry ok:false; real inbox HUMAN; installer provisioning separate |
| #80 per-user email alerts | Backend account route catalog; `management.py`; `test_email_alerts.py` default/permission/contact rebuild/audit/failure tests | J5, J9 | Add J9-11: default true, opting out requires account.alerts; changing flag requires it, resending current value does not; apply failure keeps account mutation and reports notice |
| #79 per-host recipients | Known out-of-scope issue from owner plan | None | Do not add recipient-per-host expectations |
| Additional drift: Forgot Password already implemented | Frontend login route catalog and `server/tests/unit/test_password_requests.py`; source `management.py`/login UI requires follow-up inspection | J1/J9, B10 | Old inert-button claim cannot remain; inspect request/admin reset flow before adding expectations (not SMTP self-service recovery) |

Questions remain in draft: availability formula/window; fresh reset for #86 trigger;
Playwright installation approval (planning only approved); human-only cases. No new
product decision made by this inventory. Subagent unavailable; inspection done directly.


Latest owner instruction clears the Phase 0 review stop: save results for later draft
review, continue unblocked work, leave product decisions in draft. Playwright approval
is planning/documentation only; do not install dependencies/browser yet. Human tests and
fresh-reset approval remain pending. No PR merges authorized.

Phase 0 report: `docs/test-runs/2026-10-11-qa-dry-run-j2-j3-second/REPORT.md`.
Overall Partial. Run 6 terminal Success; original networks/TCP restored at version 5.
Active IDs 5/7 refresh app01 8080 and legacy01 2222; handoff IDs 10/12 now stale
Address Unknown. Repeated duplicate observations filed as #86 after searching closed
#59/#67; deployed SHA verified and all #59/#66/#67 merge commits are ancestors.
First duplicate-creation scan remains unisolated; fresh reset deferred, not silently
approved. Optional browser/five-scan checks skipped. Step 8 remains unticked because
Phase 1 and owner decisions are unfinished. VM left up by default.


Phase 0 owner approval (2026-10-11): proceed under existing default tool permissions,
including unattended existing-lab use and issue comments/filing; never change permission
settings. Owner approved temporarily narrowing discovery to the documented lab range,
restoring the original networks without scanning them, and recording this as a confounder.
Owner released the clean main checkout: detached at `ebb5aea3`; the existing lab worktree
now holds `issue-62-qa-journeys-test-plan`. No new appliance or fresh install authorized.

Restoration observed before any new test: discovery run 5 was Success, completed
2026-10-10 16:33:04 UTC, progress 100, new host.cfg applied. TCP settings were version 2,
`1-1024`; restored to `1-10000`, version 3. The saved network list also includes the
VirtualBox NAT network (outside allowed scan scope), so no scan was started. Read-only
TCP probes from the appliance to web02 confirmed 22 open and 2222 refused. Device 9's
API state is now ADDRESS_UNKNOWN (not the handoff's monitored state); its SSH port rows
are Suggested with the plugin off. Do not describe those rows as actively monitored.
VM remains running. Handoff helper scripts were not at the named scratchpad paths;
used an in-memory cookie session and state-folder credentials without printing them.


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
