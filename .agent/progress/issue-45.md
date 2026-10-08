# Issue #45: NCPA services are CRITICAL on installer-built appliances: check_ncpa.py needs a 'python' command

Branch: `issue-45-ncpa-installer-verification`
Status: in-progress
<!-- Status is one of: in-progress | blocked | ready-for-review -->

## Finish condition

Copied from the issue. Tick an item only when a check proves it.

- [ ] On a fresh `scripts/vmlab fresh main`, after NCPA is deployed and the plugin enabled, the NCPA services report OK or a real threshold state, never return code 127
- [ ] The installer's verify step or healthcheck fails when the plugin cannot be started by the `nagios` user
- [ ] `docs/test-runs/` records the repeat run

## Plan

Ordered steps the agent will take. Write the whole plan before changing code; revise it in place and say why in the round log. Name the files each step touches.

1. [ ] Verify the updated installer fix for the NCPA shebang/healthcheck contract; document the exact installer commit/branch in `docs/test-runs/<date>-ncpa-repeat-run/REPORT.md`.
2. [ ] Run the approved VM-lab flow with the updated installer clone (`scripts/vmlab fresh main`, `scripts/vmlab ncpa`, and targeted Nagios/NCPA service checks), then record sanitized evidence in `docs/test-runs/<date>-ncpa-repeat-run/REPORT.md`.
3. [ ] Update owning status/spec documents for the closed installer gap: `spec files/Implementation_Status.md` and, if needed, `spec files/Agent_Workflow_and_CI.md`.
4. [ ] Run docs verification with `scripts/verify.sh docs`, then full verification with `scripts/verify.sh all`; update `docs/test-runs/<date>-ncpa-repeat-run/REPORT.md` or docs if verification reveals drift.
5. [ ] Remove `.agent/progress/issue-45.md`, open a PR with `Closes #45`, and report the issue finish-condition checklist.

## Round log

One row per loop round, newest last.

| Round | Change made | Check run | Result |
|---|---|---|---|
| plan | Created issue branch, read issue #45, required workflow/spec docs, Data Model/NCPA spec, Implementation Status, and inspected installer branch `fix/check-ncpa-python3-shebang` at `e471a1b876502df6b951956e2efb8c0d9aeb536f`. | `git diff origin/main..FETCH_HEAD -- setup/install-nagios-plugins.sh setup/pinpoint-healthcheck.sh` in installer clone | Installer update rewrites `#!/usr/bin/env python` to python3, verifies by direct execution as `nagios`, and healthcheck directly executes `check_ncpa.py` as `nagios`; no application code changed yet. |

## State for the next session

Everything a fresh session needs to continue without redoing work.

- Last check run (exact command): `git diff origin/main..FETCH_HEAD -- setup/install-nagios-plugins.sh setup/pinpoint-healthcheck.sh` in `/tmp/opencode/pinpoint-installer-issue45`
- Result (first failing lines, or "green"): green for inspection; diff contains the intended installer checks and no failing command output.
- Hypothesis: The installer-side fix satisfies the second finish condition statically, but issue #45 still needs a fresh VM-lab repeat run and committed sanitized `docs/test-runs/` report in this repository.
- Next action (one specific step, not "continue"): Create `docs/test-runs/2026-10-08-ncpa-repeat-run/REPORT.md` from the test-run rules, then run the VM-lab commands using `VMLINUX_INSTALLER_DIR=/tmp/opencode/pinpoint-installer-issue45` after checking out installer branch `fix/check-ncpa-python3-shebang`.

## Decisions and notes

- User said the installer repository was updated and asked to verify PR 51, then resolve issue #45. GitHub PR #51 in this repository is unrelated (`feat/remove-domain-suffix`); the installer repository has only PR #1 visible. I treated "PR 51" as "confirm the current application PR state and updated installer repo before working #45" and focused #45 on the installer update.
- Installer repository branch `fix/check-ncpa-python3-shebang` exists at `e471a1b876502df6b951956e2efb8c0d9aeb536f` and directly addresses issue #45. Main is `54aa6c916908e7516111682e7ed2b0fbb321b685`.
- Per workflow hard limits, live VM lab commands are only allowed because issue #45 explicitly names `scripts/vmlab fresh main` and asks for the repeat run.
