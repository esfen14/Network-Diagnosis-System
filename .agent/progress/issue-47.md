# Issue #47: Log expected NCPA probe exits at INFO

Branch: `issue-47-ncpa-log-level`
Status: in-progress

## Finish condition

- [ ] A probe that expects a non-zero exit does not log at ERROR.
- [ ] A failing non-probe command still logs at ERROR and returns success: False.
- [ ] Unit tests in server/tests/unit/ cover both cases.
- [ ] scripts/verify.sh backend passes.

## Plan

1. [ ] Add failing regression tests in server/tests/unit/test_ncpa_command_logging.py; fix helpers and id/grep call sites in server/app/ncpa_deployment/ncpa_deployment.py; run focused and backend checks.
2. [ ] Update spec files/Data_Model_and_Integrations.md, spec files/Implementation_Status.md and server/tests/README.md; verify docs and all; remove progress and open PR.

## Round log

| Round | Change made | Check run | Result |
|---|---|---|---|
| resumed | Preserved earlier unfinished patch in dedicated worktree; repaired plan | git log --oneline main..HEAD; git status | No prior commits; source modified and progress untracked. No upstream to pull. |

## State for the next session

- Last check run (exact command): git status --short --branch
- Result: Source modified and progress untracked; previous session backend command timed out without captured results.
- Hypothesis: Earlier patch incorrectly treats expected probe exits as successful, skipping account/key creation. Logging must change without changing return semantics.
- Next action: Add regression tests and confirm failure before correcting the patch.

## Decisions and notes

- Earlier sessions did not follow test-first/checkpoint procedure; no passing test evidence exists. This plan replaces the incomplete plan to restore test-first ordering.
- User explicitly requested continuing this narrowly described NCPA fix after the return-value bug was explained. Scope is logging only in the sensitive NCPA module; no command construction, trust, sudo permissions or credentials changes.
- Injection/secret review: preserve executed commands and log_command redaction; expected-exit INFO messages should omit stdout/stderr. No new dependency, migration or live device required.
- Local issue work copied via stash into /tmp/opencode/issue-47-ncpa; backup stash retained. Original checkout left detached at its original HEAD; no changes to main.
