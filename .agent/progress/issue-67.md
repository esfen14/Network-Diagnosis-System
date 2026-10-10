# Issue #67: Removing a network reassigns its device to another network

Branch: `issue-67-network-identity`
Status: blocked

## Finish condition

- [x] A regression test fails before the fix and passes after: a device whose only address is in network A does not move to hosts in B when A is removed; an existing B host keeps its record (`server/tests/unit/test_device_identity.py` or a new case).
- [ ] No two records are ACTIVE or ADDRESS_UNKNOWN for one IP after the reproduction; the NAT gateway is untouched or missing and its ports are not monitored under another host's address.
- [ ] VM lab: repeat the issue steps, record results under `docs/test-runs/`; QA_Test_Plan J2-08 still passes.
- [x] State the cause in issue #67; identity rules in `spec files/Device_Inventory_Requirements.md` §12 and `spec files/Data_Model_and_Integrations.md` match fixed behavior.
- [x] `scripts/verify.sh backend` passes; check against #59.

## Plan

1. [x] Add a regression case for removed network A and already-recorded hosts in B in `server/tests/unit/test_device_identity.py`; run that case red.
1a. [x] Strengthen that regression with gateway port ownership and per-IP address-state assertions in `server/tests/unit/test_device_identity.py`; run red against the pre-fix revision, then green on this branch.
2. [x] Make the smallest identity-resolution correction in `server/app/network_discovery/device_identity.py` (and only necessary discovery caller code); review injection and secret exposure, run focused tests and `scripts/verify.sh backend`.
3. [ ] Repeat the exact fresh-install gateway reproduction and two-rescan J2-08 on the VM lab, recording a new sanitized report and index row in `docs/test-runs/<date>-issue-67-retest/REPORT.md` and `docs/test-runs/README.md` against the exact tested commit.
4. [x] State the established cause in GitHub issue #67; update `spec files/Device_Inventory_Requirements.md` §12 and `spec files/Data_Model_and_Integrations.md` with the verified identity rule; update `spec files/Implementation_Status.md` if a gap closes.
5. [ ] Complete verification and finish-condition evidence with `scripts/verify.sh docs` and `scripts/verify.sh all`, remove this progress file and mark existing draft PR #70 ready when proven.

## Round log

| Round | Change made | Check run | Result |
|---|---|---|---|
| 1 | Add regression test `test_removed_network_device_not_reassigned_to_hosts_in_scanned_network` in `test_device_identity.py` and fix in `device_identity.py` | `pytest server/tests/unit/test_device_identity.py` and `./scripts/verify.sh backend` | 57 passed in unit test; 2192 passed in full backend suite (OK) |
| resumed | Prior progress file was prematurely deleted; restored it and corrected overclaimed VM/J2-08 evidence | `scripts/verify.sh backend > /tmp/opencode/issue67-resume-backend.log 2>&1` | 2192 passed, 14 skipped; live finish conditions outstanding |
| 2 | Strengthened #67 regression with gateway-port ownership and per-IP state counts | Pre-fix selected pytest in detached worktree; `server/.venv/bin/python -m pytest server/tests/unit/test_device_identity.py -q`; `scripts/verify.sh backend > /tmp/opencode/issue67-strong-backend.log 2>&1` | Red KeyError for missing B host before fix; green 57 tests and 2192 backend tests after |
| 3 | Attempted fresh VM installation of pushed branch; stopped before discovery | `scripts/vmlab fresh issue-67-network-identity`; `scripts/vmlab setup-admin`; VM USER email inspection | Health 60/0, but setup-admin HTTP 401; installer email differs from VM database user, so cannot attest fresh lab state |

## State for the next session

- Last check run (exact command): `scripts/vmlab setup-admin`
- Result (first failing lines, or "green"): `login with the installer credentials failed (HTTP 401)`; VM USER table contains `ops@vmlab-corp.com`, not the installer's newly printed admin email. Backend recheck green: 2192 passed, 14 skipped.
- Hypothesis: The VM is using a persisted or externally configured database/admin from another run despite `scripts/vmlab fresh`, so the snapshot/repro state is not trustworthy. Do not reset that data or credentials without owner decision.
- Next action (one specific step, not "continue"): Ask the owner how to obtain a truly disposable fresh VM/database and matching admin credentials for issue #67's live reproduction.

## Decisions and notes

- Relevant specifications: `spec files/Data_Model_and_Integrations.md` “Network discovery and Nagios configuration” identity paragraph; `spec files/Device_Inventory_Requirements.md` §12 monitoring-state consequences. The existing identifier priority permits a strong owner to match across networks; issue #67 expects no reassignment in the removed-network scenario. The precise rule and cause are not yet established.
- `spec files/Engineering_Standards.md` calls `app/network_discovery/` sensitive and requires an explicit injection/secret-exposure review. The existing fix has already been committed; do not change that module further without the procedure's person decision. The issue explicitly requests the VM lab.
- Prior progress file was deleted prematurely while PR #70 became draft. Restored because fresh gateway reproduction and correctly counted J2-08 were not done. The original regression was red against `c50edc34` (KeyError for a B host) and green on the fix; the original test omitted explicit gateway-port ownership and per-IP state counts. The earlier run in `docs/test-runs/2026-10-10-issue-67/REPORT.md` is Partial and must not be revised to Pass; make a new report for the retest.
- Existing specifications already describe the proposed behavior; `Implementation_Status.md` marks live verification as pending.
- Blocker for person: `scripts/vmlab fresh issue-67-network-identity` reported a healthy install, yet `setup-admin` returned HTTP 401 using its installer-provided credentials; inspection showed the VM USER table contains an unexpected existing operator account. Which disposable snapshot/database and login should be used? Do not overwrite this unknown account or infer a password. No discovery was run in this resumed VM session.
