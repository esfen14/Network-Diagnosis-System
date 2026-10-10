# Issue #66: Discovery does not record ports added to scan settings on known devices

Branch: `issue-66-discovery-new-ports`
Status: in-progress

## Finish condition

- [ ] A regression test fails before the fix and passes after: a known device, rescanned with a new single port (and a new range) in the TCP ports, gets that port recorded (`server/tests/unit/test_device_ports_route.py` or a new network-discovery test).
- [ ] Lab: QA_Test_Plan J2-09 passes on the VM lab (8080 on app01 and 2222 on legacy01 appear after the settings change and a rescan), and legacy01 becomes NCPA-eligible (J3-02, J3-09 with legacy01).
- [ ] The cause is stated in the issue (scan arguments, result handling for known devices, or the port lifecycle), and any spec sentence that was wrong is corrected (`Device_Inventory_Requirements.md` §7, §10; `Data_Model_and_Integrations.md`).
- [ ] `scripts/verify.sh backend` passes; `Implementation_Status.md` updated if a gap closes.
- [ ] The "known defect #66" note is removed from J2-09 in `docs/qa/QA_Test_Plan.md` and `docs/qa/QA_Journeys_and_Scope.md`, and a re-test is recorded under `docs/test-runs/`.

## Plan

1. [ ] Add isolated regression for repeat discovery with new single/ranged TCP ports, mocked nmap and inventory in `server/tests/unit/test_network_discovery.py`; run red.
2. [ ] Fix the demonstrated cause in `server/app/network_discovery/network_discovery.py` or `server/app/network_discovery/port_lifecycle.py`; run focused test and `scripts/verify.sh backend`.
3. [ ] Run approved VM-lab J2-09, J3-02 and J3-09 with legacy01; record new `docs/test-runs/<date>-issue-66/REPORT.md` and index in `docs/test-runs/README.md`.
4. [ ] State cause on issue; correct `spec files/Device_Inventory_Requirements.md` and `spec files/Data_Model_and_Integrations.md` if wrong; update `spec files/Implementation_Status.md`; remove defect note from `docs/qa/QA_Test_Plan.md` and `docs/qa/QA_Journeys_and_Scope.md` once present and proven; run docs and all verification.

## Round log

| Round | Change made | Check run | Result |
|---|---|---|---|
| resumed | Re-read issue and updated plan for explicit finish condition; owner approved sensitive code | `gh issue view 66 --json number,title,body,comments,labels,state,url` | Issue current; QA documents absent from checkout |

## State for the next session

- Last check run (exact command): `gh issue view 66 --json number,title,body,comments,labels,state,url`
- Result (first failing lines, or "green"): green; explicit finish condition now present and approval supplied in chat.
- Hypothesis: nmap invocation or port lifecycle handling of known devices drops newly configured ports; not yet determined.
- Next action (one specific step, not "continue"): Add and run a failing isolated regression for repeat scans with single and ranged TCP ports.

## Decisions and notes

The issue gained an explicit five-item finish condition after the initial stop; the user approved changes to sensitive network-discovery code. Plan revised to match the new issue text. The issue expressly calls for VM-lab J2/J3 checks, allowing those under the workflow's live-test exception. Injection/secret-exposure review remains required. The cited `docs/qa/` files and original dry-run report are absent from origin/main at 647247b1; do not fabricate or remove untracked work. Raised this discrepancy in the issue comment.
