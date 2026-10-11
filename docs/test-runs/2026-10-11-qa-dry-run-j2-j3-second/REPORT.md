# Test run: qa-dry-run-j2-j3-second

| | |
|---|---|
| Date | 2026-10-11 session; appliance timestamps 2026-10-10 UTC |
| Commit tested | `ebb5aea3010331e5264937443047d7c3f48231d7`, confirmed on appliance as its repository owner |
| Plan | [QA_Test_Plan.md](../../qa/QA_Test_Plan.md), Phase 0 of owner's execution plan |
| Tester | OpenCode; earlier observations explicitly attributed to owner-provided handoff |
| Environment | Existing Ubuntu installer-built VirtualBox appliance `pinpoint-appliance-45`, Nagios lab; five targets on `10.77.0.0/28`; inherited database, not reset this session |
| Raw evidence | Owner scratchpad `issue-62-lab-handoff.md`; live API/SSH observations in the OpenCode session. No raw export committed |

## Result

**Overall: Partial.** In-flight state restored and J2-09 ports observed. Duplicate records persist on a build containing the #59/#66/#67 fixes; the creation trigger was not isolated. Browser portions were not run.

Case totals: Pass 5 (all handoff-only), Fail 1, Partial 3, Skipped 2.
The owner's Phase 0 plan explicitly requires Partial for J2-05/J2-10; this is a
reporting exception to the normal four-result case vocabulary, not full case sign-off.

## Cases

| Case | Result | Notes (observed evidence and limits) | Issue |
|---|---|---|---|
| J2-02 | Skipped | Browser progress/modal not driven; API terminal status observed incidentally, not full UI coverage | — |
| J2-05 | Partial | From handoff, not re-observed: stable unchanged rescan passed; physical SSH move followed by one scan left config unchanged; restored afterward. Current session confirmed live web02 22 open and 2222 refused. Five-scan lifecycle not run; corrected one-rescan expectation using spec and source | — |
| J2-06 | Skipped | Browser cancel not driven | — |
| J2-09 | Partial | Run 5 narrowed-port scan was already Success. Run 6 used `1-1024`,2222,8080 on lab range only; Success at appliance 16:47:15 UTC, unchanged config. Active app01 ID 5 records 8080/tcp with fresh last-seen 16:47:15; active legacy01 ID 7 records 2222/tcp with fresh last-seen. Handoff IDs 10/12 are now Address Unknown and retain stale port timestamps. Ports already existed, so this proves refresh/presence, not first insertion of a new port. Configuration-log UI not re-observed | [#66](https://github.com/esfen14/Pinpoint/issues/66) (closed comparison), [#86](https://github.com/esfen14/Pinpoint/issues/86) (identity confounder) |
| J2-10 | Partial | From handoff, not re-observed: `test_maintenance_mode_pauses_tasks` passed. Maintenance banner skipped; no setting toggled this session | — |
| J3-01 | Pass (API + MOCK only) | From handoff, not re-observed: deployable list and incompatible/deployed rejection tests passed (`test_ncpa_deployment_runs.py::test_deployed_and_incompatible_devices_are_rejected`, `test_device_identity.py -k "eligibility or incompatible"`). UI selection skipped; not whole-browser-case sign-off | — |
| J3-02 | Pass | From handoff, not re-observed: web02 and legacy01 trusted, credentials accepted, Success in 48 s, both deployed; legacy01 SSH pinned at 2222. web02 substituted for plan's web01 | — |
| J3-04 | Pass | From handoff, not re-observed: untrusted credential check returned `not_trusted`; start returned 400, no devices deployable, not trust-confirmed. Browser prevention skipped | — |
| J3-07 | Pass | From handoff, not re-observed: bad web02 login failed only that device; app01 deployed; Partial Failure; web02 later redeployed successfully | — |
| J3-08 | Pass | From handoff, not re-observed: stop after 2 seconds ended Interrupted; completed web01 stayed deployed, snmp01 skipped/Pending; deployment log NP-0002 recorded interruption | — |
| J3-09 | Fail | Re-observed after run 6 and repeated read once: two rows per target. Monitored/Address Unknown IDs: .2 3/8; .3 4/9; .4 5/10; .5 11/6; .6 7/12. Also violates J2-08 assertion; not a complete two-rescan J2-08 rerun | [#86](https://github.com/esfen14/Pinpoint/issues/86) |

## Deviations from the plan

- The handoff claimed all IDs 3–7 were Address Unknown and 8–12 monitored. Current observations supersede that only where re-observed above; do not infer when identities changed.
- Contrary to the execution plan's uncertainty, `git merge-base --is-ancestor` confirms PR #68 (`647247b1`), #70 (`27ebe46d`), and #75 (`076a592a`) are ancestors of deployed `ebb5aea3`. This run includes #59/#67/#66 fixes, but predates the later main updates (#81/#84). No app sync or fresh install performed.
- Original settings included a VirtualBox NAT network outside the allowed scan range. Owner approved temporarily narrowing to the lab range; this is an identity confounder. No new scan targeted the NAT range. Its saved setting was restored without scanning it.
- Inherited run 5 completed at 16:33:04 UTC. TCP range restored from version 2 `1-1024` to version 3 `1-10000` before any new test. Version 4 was the lab-only J2-09 configuration; the API normalizes singleton ports to integers, so the scratch helper's first string-equality assertion failed before any scan started. Readback verified normalized values before run 6.
- After run 6, restored original networks and TCP `1-10000`, version 5. No scan Running; VM and targets left up. web02 listener restoration was independently confirmed before run 6; no SSH-port mutation this session.
- Repeating duplicate reads and one rescan proves persistence, not which scan first created duplicates. Fresh reset is deferred for owner approval; no claim of fresh reproduction.
- Optional five-scan and browser checks skipped; browser tooling not available in this run. Owner approved saving results for later draft review instead of stopping at the Phase 0 review gate.

## Follow-up

- [#86](https://github.com/esfen14/Pinpoint/issues/86): isolate duplicate creation and deployment ownership; searched open and closed #59/#67 before filing. No product fix in this run.
- Repeat J2-09 from a clean, unique-identity baseline to prove first-time port insertion rather than refresh.
- Run browser portions and five-scan lifecycle separately. Handoff-only results must not become newly observed passes in future traceability.
- J3-02 already states legacy01 port 2222; no wording change needed.

## Sanitization checklist

- [x] No passwords, tokens, keys, SNMP communities or private key paths
- [x] No addresses outside the documented lab range
- [x] Evidence summarized rather than raw secret-bearing responses pasted
