# Issue #36: Resolve SERVICE_CHANGED review items

Branch: `issue-36-service-changed-autoclear`
Status: in-progress
<!-- Status is one of: in-progress | blocked | ready-for-review -->

## Finish condition

Copied from the issue. Tick an item only when a check proves it.

- [ ] A unit test covers an item that clears when the mismatch disappears
- [ ] An item that still mismatches stays open
- [ ] scripts/verify.sh all passes
- [ ] The "SERVICE_CHANGED auto-clear" row in Implementation_Status.md is updated

## Plan

Ordered steps the agent will take. Write the whole plan before changing code;
revise it in place and say why in the round log. Name the files each step touches.

1. [ ] Tests in server/tests/unit/test_service_identification.py (TestServiceChangedReview): item clears when port matches its frozen plugin again; item stays open while it still mismatches
2. [ ] Implement in server/app/network_discovery/port_lifecycle.py: flag_service_change resolves open SERVICE_CHANGED items for the port (set Resolved_At) when the observed service matches the frozen plugin
3. [ ] Docs: spec files/Data_Model_and_Integrations.md (~line 283), spec files/Implementation_Status.md row 73, Device_Inventory/Backend docs if they mention it; scripts/verify.sh docs
4. [ ] scripts/verify.sh all, delete progress file, PR

## Round log

One row per loop round, newest last.

| Round | Change made | Check run | Result |
|---|---|---|---|


## State for the next session

Everything a fresh session needs to continue without redoing work.

- Last check run (exact command):
- Result (first failing lines, or "green"):
- Hypothesis:
- Next action (one specific step, not "continue"): write the two failing tests (plan step 1)

## Decisions and notes

Choices made, things ruled out, questions for a person.
