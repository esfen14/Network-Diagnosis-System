# Issue #66: Discovery does not record added ports on known devices

Branch: `issue-66-reapply-verified-fix`
Status: in-progress

## Finish condition

- [ ] A regression test fails before the fix and passes after for single and ranged TCP ports on known devices.
- [ ] VM lab J2-09 passes for app01 8080 and legacy01 2222; legacy01 is NCPA-eligible (J3-02/J3-09).
- [ ] Cause stated on issue; any wrong specification corrected.
- [ ] `scripts/verify.sh backend` passes; Implementation_Status updated if gap closes.
- [ ] Remove known defect #66 note from QA documents and record a re-test under docs/test-runs/.

## Plan

1. [x] Restore and independently run the red regression from PR #69 in `server/tests/unit/test_device_identity.py` and `server/tests/unit/test_network_discovery.py` against reverted main.
2. [x] Reapply the minimal identity fix in `server/app/network_discovery/device_identity.py`; run targeted tests and `scripts/verify.sh backend`; review injection and secret exposure.
3. [ ] Restore the previously verified VM report at `docs/test-runs/2026-10-10-issue-66/REPORT.md`, QA notes in `docs/qa/QA_Test_Plan.md` and `docs/qa/QA_Journeys_and_Scope.md`, test-run index and specifications (`Data_Model_and_Integrations.md`, `Implementation_Status.md`); verify docs. Do not claim a new lab run.
4. [ ] Run `scripts/verify.sh all`, update issue finish-condition checkboxes with evidence, remove progress file, and open a new PR.

## Round log

| Round | Change made | Check run | Result |
|---|---|---|---|
| 1 | Restored tests from PR #69 on reverted main; then restored identity reconciliation fix. | `python -m pytest tests/unit/test_device_identity.py -k known_clone_key_hosts_keep_new_tcp_ports -q` before and after; `python -m pytest tests/unit/test_network_discovery.py -k known_devices_record_newly_scanned_tcp_ports -q` | Red: two KeyErrors; green: 2+2 passed. |
| 2 | Reviewed sensitive code: no shell interpolation, new commands, secrets, or secret logging; only identifier ownership and review messages. | `scripts/verify.sh backend` | 2191 passed, 14 skipped. First run timed out at 120s, second run completed with 600s timeout. |

## State for the next session

- Last check run (exact command): `scripts/verify.sh backend`
- Result (first failing lines, or "green"): green; 2191 passed, 14 skipped.
- Hypothesis: The historical VM report accurately records the previously run lab check; it must not be presented as a new retest of this branch.
- Next action (one specific step, not "continue"): Restore the previously merged docs and report from 3b572052, then run `scripts/verify.sh docs`.

## Decisions and notes

- Issue owner explicitly requested reopening/reapplication; earlier issue comment granted sensitive-module approval. Do not run the VM or live suite in this session; preserve the historical VM report with its original commit and limitations.
- PR #65 with original QA documents remains open; PR #69 had added those docs to main and PR #71 removed them. Restore the previously authored QA documents, not invent replacements.
- The changed reconciliation logic does not invoke commands or handle secrets; review again before completion.
