# Issue #47: Log expected NCPA probe exits at INFO

Branch: `issue-47-ncpa-log-level`
Status: in-progress

## Finish condition

- [x] A probe that expects a non-zero exit does not log at ERROR.
- [x] A failing non-probe command still logs at ERROR and returns success: False.
- [x] Unit tests in server/tests/unit/ cover both cases.
- [x] scripts/verify.sh backend passes.

## Plan

1. [x] Add failing regression tests in server/tests/unit/test_ncpa_command_logging.py; fix helpers and id/grep call sites in server/app/ncpa_deployment/ncpa_deployment.py; run focused and backend checks.
2. [ ] Update spec files/Data_Model_and_Integrations.md, spec files/Implementation_Status.md and server/tests/README.md; verify docs and all; remove progress and open PR.

## Round log

| Round | Change made | Check run | Result |
|---|---|---|---|
| resumed | Preserved earlier unfinished patch in dedicated worktree; repaired plan | git log --oneline main..HEAD; git status | No prior commits; source modified and progress untracked. No upstream to pull. |

| 1 | Added 15 mocked SSH regressions; expected exits log INFO and retain success False | Focused pytest; scripts/verify.sh backend | Red: 7 failed/8 passed; green: 15 passed; backend: 2185 passed, 14 skipped |

## State for the next session

- Last check run (exact command): scripts/verify.sh backend > /tmp/opencode/issue-47-backend.log 2>&1
- Result: green; 2185 passed, 14 skipped in 241.12s.
- Hypothesis: Fixed return semantics preserve creation and idempotency; unexpected errors still log ERROR.
- Next action: Update owning specification and test inventory, then run docs and all checks.

## Decisions and notes

- Earlier sessions did not follow test-first/checkpoint procedure; no passing test evidence exists. This plan replaces the incomplete plan to restore test-first ordering.
- User explicitly requested continuing this narrowly described NCPA fix after the return-value bug was explained. Scope is logging only in the sensitive NCPA module; no command construction, trust, sudo permissions or credentials changes.
- Injection/secret review: preserve executed commands and log_command redaction; expected-exit INFO messages should omit stdout/stderr. No new dependency, migration or live device required.
- Local issue work copied via stash into /tmp/opencode/issue-47-ncpa; backup stash retained. Original checkout left detached at its original HEAD; no changes to main.
