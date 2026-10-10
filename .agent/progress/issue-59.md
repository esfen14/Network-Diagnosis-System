# Issue #59: Discovery leaves a duplicate device record for the same IP

Branch: `issue-59-discovery-duplicate-device`
Status: in-progress

## Finish condition

- [ ] Reproduce, then find the cause (overlapping discoveries, or identity matching for a host with SSH on a non-default port)
- [ ] Fix with a test, and document it in the discovery spec
- [ ] A repeat of the sequence above leaves one record for `10.77.0.6`

## Plan

1. [x] Reproduce the fresh-install observation in an isolated regression test and distinguish sequential identity mismatch from overlapping scans (`server/tests/unit/test_device_identity.py`, `server/tests/unit/test_network_discovery.py`, `server/tests/support/identity_helpers.py` if needed).
2. [x] Make the smallest safe discovery/identity correction and verify the focused test and backend stage (`server/app/network_discovery/device_identity.py`, `server/app/network_discovery/identity_probes.py` or `server/app/api/system/network_discovery.py` as evidence dictates; corresponding unit test).
3. [ ] Repeat the stated sequence in an authorized lab and confirm one record at 10.77.0.6 (`docs/test-runs/<date>-issue-59/REPORT.md`); verify any supporting isolated tests.
4. [ ] Document the corrected discovery behavior and gap status (`spec files/Data_Model_and_Integrations.md`, `spec files/Implementation_Status.md`); run docs verification and all-stage verification.

## Round log

| Round | Change made | Check run | Result |
|---|---|---|---|
| resumed | User approved sensitive discovery code and disposable VM lab; resumed branch | `gh issue view 59 --json number,title,body,comments,labels,url >/tmp/opencode/issue-59-check.json && test -s /tmp/opencode/issue-59-check.json` | green |
| 1 | Isolated tests for concurrent scan start and ADDRESS_UNKNOWN reactivation; locked discovery start and included ADDRESS_UNKNOWN in IP_MATCHABLE_STATES | `scripts/verify.sh backend` | green (2,187 passed, 14 skipped) |

## State for the next session

- Last check run (exact command): `scripts/verify.sh backend`
- Result (first failing lines, or "green"): green (2,187 passed, 14 skipped)
- Hypothesis: Dual root cause verified: (1) `start_discovery_thread` lacked a lock to prevent concurrent start requests from both launching scans, and (2) `IP_MATCHABLE_STATES` excluded `ADDRESS_UNKNOWN`, preventing rescans from matching and reactivating an `ADDRESS_UNKNOWN` device by IP.
- Next action (one specific step, not "continue"): Push checkpoint, run the VM-lab sequence (`scripts/vmlab fresh`, `smoke`, `ncpa`), and record test-run evidence.

## Decisions and notes

- `spec files/Data_Model_and_Integrations.md` §Network discovery and Nagios configuration and §NCPA deployment own this behavior.
- User approved changing sensitive discovery code after injection/secret-exposure review and running the disposable VM lab on resumption.
- Source inspection: discovery scans nmap-named SSH ports; the in-process start guard checks a thread, while `find_ip_holder` only matches Active/Missing. The root cause has not been reproduced or established.
