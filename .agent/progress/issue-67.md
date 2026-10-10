# Issue #67: Removing a network reassigns its device to another network

Branch: `issue-67-network-identity`
Status: in-progress

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

## State for the next session

- Last check run (exact command): `scripts/verify.sh backend > /tmp/opencode/issue67-strong-backend.log 2>&1`
- Result (first failing lines, or "green"): green; 2192 passed, 14 skipped in 264.70s
- Hypothesis: Keeping known devices in scanned network when cross-network strong identifier matches prevents stealing addresses of existing devices when a network is removed; the earlier VM run did not establish the fresh-gateway behavior.
- Next action (one specific step, not "continue"): Fresh-install the issue branch on the VM lab and establish a persisted standalone `10.0.2.2` gateway before removing its network.

## Decisions and notes

- Relevant specifications: `spec files/Data_Model_and_Integrations.md` “Network discovery and Nagios configuration” identity paragraph; `spec files/Device_Inventory_Requirements.md` §12 monitoring-state consequences. The existing identifier priority permits a strong owner to match across networks; issue #67 expects no reassignment in the removed-network scenario. The precise rule and cause are not yet established.
- `spec files/Engineering_Standards.md` calls `app/network_discovery/` sensitive and requires an explicit injection/secret-exposure review. The existing fix has already been committed; do not change that module further without the procedure's person decision. The issue explicitly requests the VM lab.
- Prior progress file was deleted prematurely while PR #70 became draft. Restored because fresh gateway reproduction and correctly counted J2-08 were not done. The original regression was red against `c50edc34` (KeyError for a B host) and green on the fix; the original test omitted explicit gateway-port ownership and per-IP state counts. The earlier run in `docs/test-runs/2026-10-10-issue-67/REPORT.md` is Partial and must not be revised to Pass; make a new report for the retest.
- Existing specifications already describe the proposed behavior; `Implementation_Status.md` marks live verification as pending.
