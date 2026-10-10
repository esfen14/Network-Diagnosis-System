# Issue #59: Discovery leaves a duplicate device record for the same IP

Branch: `issue-59-discovery-duplicate-device`
Status: in-progress

## Finish condition

- [ ] Reproduce, then find the cause (overlapping discoveries, or identity matching for a host with SSH on a non-default port)
- [ ] Fix with a test, and document it in the discovery spec
- [ ] A repeat of the sequence above leaves one record for `10.77.0.6`

## Plan

1. [ ] Reproduce the fresh-install observation in an isolated regression test and distinguish sequential identity mismatch from overlapping scans (`server/tests/unit/test_device_identity.py`, `server/tests/unit/test_network_discovery.py`, `server/tests/support/identity_helpers.py` if needed).
2. [ ] Make the smallest safe discovery/identity correction and verify the focused test and backend stage (`server/app/network_discovery/device_identity.py`, `server/app/network_discovery/identity_probes.py` or `server/app/api/system/network_discovery.py` as evidence dictates; corresponding unit test).
3. [ ] Repeat the stated sequence in an authorized lab and confirm one record at 10.77.0.6 (`docs/test-runs/<date>-issue-59/REPORT.md`); verify any supporting isolated tests.
4. [ ] Document the corrected discovery behavior and gap status (`spec files/Data_Model_and_Integrations.md`, `spec files/Implementation_Status.md`); run docs verification and all-stage verification.

## Round log

| Round | Change made | Check run | Result |
|---|---|---|---|

## State for the next session

- Last check run (exact command): `gh issue view 59 --json number,title,body,comments,labels,url`
- Result (first failing lines, or "green"): green; issue finish conditions retrieved.
- Hypothesis: `find_ip_holder` excludes `ADDRESS_UNKNOWN`, so after a transient contradictory observation displaces a host, a later scan with missing/different evidence may create a new record rather than recover the old; overlapping scans are guarded in-process but not across workers.
- Next action (one specific step, not "continue"): Obtain approval for changes to sensitive discovery code and for the live VM-lab repeat, then add an isolated failing regression test.

## Decisions and notes

- `spec files/Data_Model_and_Integrations.md` §Network discovery and Nagios configuration and §NCPA deployment own this behavior.
- The workflow's needs-a-person condition applies: `app/network_discovery/` is sensitive under `Engineering_Standards.md`, and the stated repeat requires a live VM/network device. Do not change this module or run that lab until a person authorizes it.
- Source inspection: discovery scans nmap-named SSH ports; the in-process start guard checks a thread, while `find_ip_holder` only matches Active/Missing. The root cause has not been reproduced or established.
