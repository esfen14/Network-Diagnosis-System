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
3. [x] Repeat the stated sequence in an authorized lab and confirm one record at 10.77.0.6 (`docs/test-runs/2026-10-10-issue-59/REPORT.md`, `docs/test-runs/README.md`); verify any supporting isolated tests.
4. [ ] Document the corrected discovery behavior and gap status (`spec files/Data_Model_and_Integrations.md`, `spec files/Implementation_Status.md`); run docs verification and all-stage verification.

## Round log

| Round | Change made | Check run | Result |
|---|---|---|---|
| resumed | User approved sensitive discovery code and disposable VM lab; resumed branch | `gh issue view 59 --json number,title,body,comments,labels,url >/tmp/opencode/issue-59-check.json && test -s /tmp/opencode/issue-59-check.json` | green |
| 1 | Isolated tests for concurrent scan start and ADDRESS_UNKNOWN reactivation; locked discovery start and included ADDRESS_UNKNOWN in IP_MATCHABLE_STATES | `scripts/verify.sh backend` | green (2,187 passed, 14 skipped) |
| 2 | Fresh VM install, two slow scans, rejected extra start, NCPA deploy; recorded report | `scripts/vmlab ncpa` and SQLite query of `NETWORK_DISCOVERY` | 16/16 deploy checks passed; one ACTIVE row at 10.77.0.6 |

## State for the next session

- Last check run (exact command): `ssh -i "$HOME/.local/share/pinpoint-vmlab-45/id_ed25519" -p 2250 -o StrictHostKeyChecking=no lab@127.0.0.1 "python3 -c 'import sqlite3; c=sqlite3.connect(\"/opt/pinpoint/Network-Diagnosis-System/server/system.db\"); print(c.execute(\"SELECT NetDiscoveryID,IP_Address,Device_State FROM NETWORK_DISCOVERY WHERE IP_Address=?\",(\"10.77.0.6\",)).fetchall())'"`
- Result (first failing lines, or "green"): green: `[(7, '10.77.0.6', 'ACTIVE')]` after NCPA deploy.
- Hypothesis: Start race and ADDRESS_UNKNOWN exclusion are two independent duplicate paths; lab reproduced slow scan timeout but not the old ghost with this patch.
- Next action (one specific step, not "continue"): Document discovery invariants in Data_Model_and_Integrations.md and update Implementation_Status.md, then run docs and all verification.

## Decisions and notes

- `spec files/Data_Model_and_Integrations.md` §Network discovery and Nagios configuration and §NCPA deployment own this behavior.
- User approved changing sensitive discovery code after injection/secret-exposure review and running the disposable VM lab on resumption.
- Source inspection: discovery scans nmap-named SSH ports; the in-process start guard checks a thread, while `find_ip_holder` only matches Active/Missing. The root cause has not been reproduced or established.
