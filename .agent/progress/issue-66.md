# Issue #66: Discovery does not record ports added to scan settings on known devices

Branch: `issue-66-discovery-new-ports`
Status: in-progress

## Finish condition

- [x] A regression test fails before the fix and passes after: a known device, rescanned with a new single port (and a new range) in the TCP ports, gets that port recorded (`server/tests/unit/test_device_ports_route.py` or a new network-discovery test).
- [ ] Lab: QA_Test_Plan J2-09 passes on the VM lab (8080 on app01 and 2222 on legacy01 appear after the settings change and a rescan), and legacy01 becomes NCPA-eligible (J3-02, J3-09 with legacy01).
- [ ] The cause is stated in the issue (scan arguments, result handling for known devices, or the port lifecycle), and any spec sentence that was wrong is corrected (`Device_Inventory_Requirements.md` §7, §10; `Data_Model_and_Integrations.md`).
- [ ] `scripts/verify.sh backend` passes; `Implementation_Status.md` updated if a gap closes.
- [ ] The "known defect #66" note is removed from J2-09 in `docs/qa/QA_Test_Plan.md` and `docs/qa/QA_Journeys_and_Scope.md`, and a re-test is recorded under `docs/test-runs/`.

## Plan

1. [x] Add isolated regression for repeat discovery with new single/ranged TCP ports on distinct devices that share a cloned SSH host key, in `server/tests/unit/test_network_discovery.py` or `server/tests/unit/test_device_identity.py`; run red.
2. [x] Fix the demonstrated identity reconciliation cause in `server/app/network_discovery/device_identity.py` (not nmap arguments or port lifecycle); run focused test and `scripts/verify.sh backend`.
3. [ ] Run approved VM-lab J2-09, J3-02 and J3-09 with legacy01; record new `docs/test-runs/<date>-issue-66/REPORT.md` and index in `docs/test-runs/README.md`.
4. [ ] State cause on issue; correct `spec files/Device_Inventory_Requirements.md` and `spec files/Data_Model_and_Integrations.md` if wrong; update `spec files/Implementation_Status.md`; remove defect note from `docs/qa/QA_Test_Plan.md` and `docs/qa/QA_Journeys_and_Scope.md` once present and proven; run docs and all verification.

## Round log

| Round | Change made | Check run | Result |
|---|---|---|---|
| resumed | Re-read issue and updated plan for explicit finish condition; owner approved sensitive code | `gh issue view 66 --json number,title,body,comments,labels,state,url` | Issue current; QA documents absent from checkout |
| 1 | Added mocked saved-settings repeat-scan diagnostic for single and ranged ports on existing devices | `cd server && .venv/bin/python -m pytest tests/unit/test_network_discovery.py -k known_devices -q` | Green (2 passed): does not reproduce the live failure; no implementation justified yet |
| 2 | Fresh VM appliance and targets: direct nmap and nmap3 find 8080; baseline default scan found both ports, narrow scan ran, then single-port rescan ran | `ssh ... lab@127.0.0.1 'sudo -u pinpoint /opt/pinpoint/venv/bin/python -c "... select NetDiscoveryID,Port_Number,Service_Name from OPEN_TCP_Services where Port_Number in (8080,2222) ..."'` | Scan #4 SUCCESS, config unchanged; existing app01 row 8080 and legacy01 row 2222 remain, so this cannot prove a *new* port is added. Scan #2 was cancelled, scan #3 SUCCESS; no implementation change justified |
| 3 | Reinstalled appliance, saved narrow range before first scan; added 8080/2222 then rescanned | `ssh ... lab@127.0.0.1 'sudo journalctl -u pinpoint-gunicorn --since "2026-10-10 03:25:00" --no-pager | tail -65'` | Red on lab: scan #2 SUCCESS but new ports absent; first device falsely treated four other MACs as secondary due to shared SSH key |
| 4 | Added red shared-key repeat-scan test; match existing same-address MAC owner and raise duplicate review without moving ports to key owner | `cd server && .venv/bin/python -m pytest tests/unit/test_device_identity.py -k known_clone_key_hosts -q`; `scripts/verify.sh backend` | Before: 2 failed KeyError on legacy address; after: 2 passed; full backend 2191 passed, 14 skipped |

## State for the next session

- Last check run (exact command): `scripts/verify.sh backend`
- Result (first failing lines, or "green"): green, 2191 passed / 14 skipped; targeted regression red before fix (2 KeyError), green after (2 passed).
- Hypothesis: clone SSH key was the J2-09 cause; fix keeps an existing same-address hardware MAC owner, but new clone-key devices without an existing row still need separate issue review.
- Next action (one specific step, not "continue"): Push fix then `scripts/vmlab sync` and retest narrow-to-single-and-range port rescans, followed by NCPA legacy01.

## Decisions and notes

The issue gained an explicit five-item finish condition after the initial stop; the user approved changes to sensitive network-discovery code. Plan revised to match the new issue text. The issue expressly calls for VM-lab J2/J3 checks, allowing those under the workflow's live-test exception. Injection/secret-exposure review remains required. The cited `docs/qa/` files and original dry-run report are absent from origin/main at 647247b1; do not fabricate or remove untracked work. Raised this discrepancy in the issue comment. VM diagnostic: first fresh attempt had an unattended-upgrades dpkg lock; retry healthcheck passed 60/0. The default scan included both ports; a narrowed scan did not delete them, so the subsequent single-port scan could not test *new* ports. A clean run must set narrow ports before first discovery. No secrets in logs or commits. Plan updated after clean reproduction ruled out nmap and showed identity reconciliation suppresses port persistence for clone-key hosts. This touches `device_identity.py` within the already approved sensitive module. Security review: no shell/subprocess or secret-handling changes; the review message includes only documented device addresses and generated Nagios host labels, never SSH key material. Scope is limited to known devices at the same address with matching hardware MAC; the pre-existing new-clone ambiguity is not silently merged.
