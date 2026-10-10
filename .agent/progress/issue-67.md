# Issue #67: Removing a network reassigns its device to another network

Branch: `issue-67-network-identity`
Status: in-progress

## Finish condition

- [ ] A regression test fails before the fix and passes after: a device whose only address is in network A does not move to hosts in B when A is removed; an existing B host keeps its record (`server/tests/unit/test_device_identity.py` or a new case).
- [ ] No two records are ACTIVE or ADDRESS_UNKNOWN for one IP after the reproduction; the NAT gateway is untouched or missing and its ports are not monitored under another host's address.
- [ ] VM lab: repeat the issue steps, record results under `docs/test-runs/`; QA_Test_Plan J2-08 still passes.
- [ ] State the cause in issue #67; identity rules in `spec files/Device_Inventory_Requirements.md` §12 and `spec files/Data_Model_and_Integrations.md` match fixed behavior.
- [ ] `scripts/verify.sh backend` passes; check against #59.

## Plan

1. [x] Add a regression case for removed network A and already-recorded hosts in B, including ports and address-state assertions, in `server/tests/unit/test_device_identity.py`; run that case red.
2. [x] Make the smallest identity-resolution correction in `server/app/network_discovery/device_identity.py` (and only necessary discovery caller code); review injection and secret exposure, run focused tests and `scripts/verify.sh backend`.
3. [ ] Repeat the reproduction and J2-08 on the VM lab, recording a sanitized report and index row in `docs/test-runs/<date>-issue-67/REPORT.md` and `docs/test-runs/README.md` against the exact tested commit.
4. [ ] State the established cause in GitHub issue #67; update `spec files/Device_Inventory_Requirements.md` §12 and `spec files/Data_Model_and_Integrations.md` with the verified identity rule; update `spec files/Implementation_Status.md` if a gap closes.
5. [ ] Complete verification and finish-condition evidence with `scripts/verify.sh docs` and `scripts/verify.sh all`, remove this progress file and open a PR from `.github/pull_request_template.md`.

## Round log

| Round | Change made | Check run | Result |
|---|---|---|---|
| 1 | Add regression test `test_removed_network_device_not_reassigned_to_hosts_in_scanned_network` in `test_device_identity.py` and fix in `device_identity.py` | `pytest server/tests/unit/test_device_identity.py` and `./scripts/verify.sh backend` | 57 passed in unit test; 2192 passed in full backend suite (OK) |

## State for the next session

- Last check run (exact command): `./scripts/verify.sh backend`
- Result (first failing lines, or "green"): green; 2192 passed, 14 skipped in 232.47s
- Hypothesis: Keeping known devices in scanned network when cross-network strong identifier matches prevents stealing addresses of existing devices when a network is removed.
- Next action (one specific step, not "continue"): Complete the VM lab test report in `docs/test-runs/2026-10-10-issue-67/REPORT.md` and update `docs/test-runs/README.md`.

## Decisions and notes

- Relevant specifications: `spec files/Data_Model_and_Integrations.md` “Network discovery and Nagios configuration” identity paragraph; `spec files/Device_Inventory_Requirements.md` §12 monitoring-state consequences. The existing identifier priority permits a strong owner to match across networks; issue #67 expects no reassignment in the removed-network scenario. The precise rule and cause are not yet established.
- `spec files/Engineering_Standards.md` calls `app/network_discovery/` sensitive and requires an explicit injection/secret-exposure review. The work-issue procedure §4 says to stop for a person if a change touches a sensitive module; its hard limit also forbids touching the VM lab unless the issue says to. This issue explicitly requests the VM lab, but owner approval for sensitive code is still needed.
