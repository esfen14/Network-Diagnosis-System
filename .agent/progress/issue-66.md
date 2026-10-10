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
| 1 | Added mocked saved-settings repeat-scan diagnostic for single and ranged ports on existing devices | `cd server && .venv/bin/python -m pytest tests/unit/test_network_discovery.py -k known_devices -q` | Green (2 passed): does not reproduce the live failure; no implementation justified yet |
| 2 | Fresh VM appliance and targets: direct nmap and nmap3 find 8080; baseline default scan found both ports, narrow scan ran, then single-port rescan ran | `ssh ... lab@127.0.0.1 'sudo -u pinpoint /opt/pinpoint/venv/bin/python -c "... select NetDiscoveryID,Port_Number,Service_Name from OPEN_TCP_Services where Port_Number in (8080,2222) ..."'` | Scan #4 SUCCESS, config unchanged; existing app01 row 8080 and legacy01 row 2222 remain, so this cannot prove a *new* port is added. Scan #2 was cancelled, scan #3 SUCCESS; no implementation change justified |

## State for the next session

- Last check run (exact command): `ssh -i "$HOME/.local/share/pinpoint-vmlab-45/id_ed25519" -p 2250 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR lab@127.0.0.1 'sudo -u pinpoint /opt/pinpoint/venv/bin/python -c "import sqlite3; c=sqlite3.connect(\"/opt/pinpoint/Network-Diagnosis-System/server/system.db\"); print(c.execute(\"select NetDiscoveryID,IP_Address,Device_State from NETWORK_DISCOVERY where IP_Address in (\\\"10.77.0.4\\\",\\\"10.77.0.6\\\")\").fetchall()); print(c.execute(\"select NetDiscoveryID,Port_Number,Service_Name from OPEN_TCP_Services where Port_Number in (8080,2222)\").fetchall())"'`
- Result (first failing lines, or "green"): scan #4 SUCCESS with unchanged config; ports present on the two original device IDs, but were already present from default scan #1 and persisted across narrowed scan, so not a valid reproduction.
- Hypothesis: J2-09's initial default scan may already have stored the target ports; the reported disappearance is from a different state/branch or identity issue. Real nmap3 confirms combined arguments discover 8080.
- Next action (one specific step, not "continue"): Fresh-install VM again; narrow settings before first scan, then scan and add one port, checking device IDs and rows before/after.

## Decisions and notes

The issue gained an explicit five-item finish condition after the initial stop; the user approved changes to sensitive network-discovery code. Plan revised to match the new issue text. The issue expressly calls for VM-lab J2/J3 checks, allowing those under the workflow's live-test exception. Injection/secret-exposure review remains required. The cited `docs/qa/` files and original dry-run report are absent from origin/main at 647247b1; do not fabricate or remove untracked work. Raised this discrepancy in the issue comment. VM diagnostic: first fresh attempt had an unattended-upgrades dpkg lock; retry healthcheck passed 60/0. The default scan included both ports; a narrowed scan did not delete them, so the subsequent single-port scan could not test *new* ports. A clean run must set narrow ports before first discovery. No secrets in logs or commits.
