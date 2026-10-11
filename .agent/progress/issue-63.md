# Issue #63: Make the repo ready for a QA agent loop (traceability matrix, qa-run workflow, rules, lab safety, Playwright)

Branch: `issue-63-qa-loop-readiness`
Status: in-progress
<!-- Status is one of: in-progress | blocked | ready-for-review -->

## Finish condition

Copied from the issue. Tick an item only when a check proves it.

- [ ] `Requirements_Traceability.md` exists with every in-scope row from #62 and passes `scripts/check_traceability.py`
- [ ] `qa-run.md` and both adapters exist; `work-issue.md` and `Agent_Workflow_and_CI.md` no longer contradict it
- [ ] Labels and rules exist
- [ ] Playwright is installed in `client/`, Vitest ignores `client/e2e/`, and one smoke spec logs in as each role against the lab and passes
- [ ] A dry run: one agent round on J2/J3, recorded in `docs/test-runs/`, which files a deliberately planted failure and does not file a known gap
- [ ] `scripts/verify.sh docs` passes

Requirement coverage (every requirement the issue states, and the check that proves it):

| Issue requirement | Finish-condition item | Proof (test or command) |
|---|---|---|
| Traceability matrix with in-scope rows from #62 | `Requirements_Traceability.md` exists | `python3 -I scripts/check_traceability.py` |
| Drift check for traceability matrix | passes `scripts/check_traceability.py` | `scripts/verify.sh docs` |
| `.agent/workflows/qa-run.md` and adapters | `qa-run.md` and both adapters exist | File existence & schema check in `scripts/verify.sh docs` |
| Harmonized rules in `work-issue.md` and `Agent_Workflow_and_CI.md` | `work-issue.md` and `Agent_Workflow_and_CI.md` no longer contradict | Markdown review and link checks |
| Rules, labels, and severity rubric | Labels and rules exist | `gh label list`, rubric documented in `Agent_Workflow_and_CI.md` |
| Lab safety rules, 10.77.0.0/28 guard | Lab safety rules defined | Documented in `Agent_Workflow_and_CI.md`, `qa-run.md`, `vmlab` guard |
| Retest loop on closed `qa-found` issues | Retest loop defined | Documented query in `qa-run.md` and `Requirements_Traceability.md` |
| Playwright E2E configuration and Vitest exclusion | Playwright installed, Vitest ignores e2e | Vitest run passes without e2e, Playwright config present, teammate setup doc |
| Smoke specs per role against lab/mock | One smoke spec logs in as each role | Playwright execution against mock/lab |
| QA-run dry run with planted defect | Dry run recorded in `docs/test-runs/` | Planted failure recorded and closed, no known gap filed |

## Plan

Ordered steps the agent will take:

1. [ ] Traceability matrix: Create `docs/qa/Requirements_Traceability.md` covering all cases from `QA_Test_Plan.md` and repository specs, seeded with observed statuses from test run reports.
2. [ ] Traceability drift check: Create failing unit test for `scripts/check_traceability.py`, implement `scripts/check_traceability.py`, wire it into `scripts/verify.sh docs`, and document in `spec files/Agent_Workflow_and_CI.md`.
3. [ ] Labels and rules: Ensure `qa-found` and `needs-decision` labels exist; document the 3-level severity rubric, repeat-once rule, and safety constraints in `spec files/Agent_Workflow_and_CI.md`.
4. [ ] Workflow and adapters: Write `.agent/workflows/qa-run.md`, `.claude/skills/qa-run/SKILL.md`, `.opencode/commands/qa-run.md`, and update `check_agent_progress.py` to recognize `qa-run.md` if needed.
5. [ ] Environment & safety: Harmonize `work-issue.md` and `Agent_Workflow_and_CI.md` to allow lab commands (`scripts/vmlab`, `scripts/lab`) for QA finding/verification while strictly forbidding libvirt harness; specify 10.77.0.0/28 range guard and document permission rules.
6. [ ] Retest loop: Specify closed-issue retest query in `qa-run.md` and `Requirements_Traceability.md`.
7. [ ] Playwright E2E automation: Configure `client/playwright.config.ts`, `client/vitest.config.ts` exclusion, install `@playwright/test`, add auth state setup, write teammate setup documentation (`docs/qa/Playwright_Setup.md`), and smoke tests in `client/e2e/`.
8. [ ] Dry run: Execute dry run of `qa-run` on J2/J3 with planted defect, record report in `docs/test-runs/`, file and close planted finding.
9. [ ] Verification & PR: Run `scripts/verify.sh all`, verify clean state, push branch `issue-63-qa-loop-readiness`, and open PR to `issue-62-qa-journeys-test-plan` (or `main` when #65 merges).

## Round log

One row per loop round, newest last.

| Round | Change made | Check run | Result |
|---|---|---|---|
| 1 | Created issue-63 branch and initialized progress file | `scripts/check_agent_progress.py` | Initialized |

## State for the next session

Everything a fresh session needs to continue without redoing work.

- Last check run (exact command): `scripts/check_agent_progress.py`
- Result (first failing lines, or "green"): green
- Hypothesis: Progress file established, ready to implement Step 1 (Requirements_Traceability.md).
- Next action (one specific step, not "continue"): Build `docs/qa/Requirements_Traceability.md` with in-scope rows mapped from `docs/qa/QA_Test_Plan.md`.

## Decisions and notes

- Departed from `work-issue.md` step 2.1 by branching from `origin/issue-62-qa-journeys-test-plan` instead of `origin/main` because #63 depends directly on the test plans and journeys produced in #62 (PR #65), which are not yet merged to main.
- PR #63 will be opened as a draft targeting `issue-62-qa-journeys-test-plan` so the diff only reflects #63 additions until PR #65 merges.
- User explicitly approved unattended lab use, issue filing, and Playwright installation with teammate documentation.
