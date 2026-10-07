# Work one issue

This is the single source for how any coding agent (Claude Code, OpenCode, Codex or
another) works a GitHub issue in this repository. Tool-specific commands such as
`/work-issue` only load this file; they must not add or change steps. The rules the
loop relies on are in `spec files/Agent_Workflow_and_CI.md`.

Input: an issue number, written `<n>` below. You need `git`, `gh` (signed in) and a
shell. If your tool has a task list, mirror the plan there, but the progress file
(below) is the source of truth because it survives a stopped session.

## Hard limits (always)

- Work only on a branch named `issue-<n>-<short-slug>`. Never commit or push to `main`.
- Never merge a pull request, change branch protection, edit `.github/workflows/`,
  or force-push.
- Never skip, delete or weaken a test to get green.
- Never run live tests (`server/tests/integration/`, `server/tests/e2e/`) or touch the
  VM or Docker labs unless the issue says to.
- Never write secrets, tokens or passwords into files, commits, logs or the progress file.
- Stay inside the issue. If the fix needs something the issue does not name, write it
  down as a new issue and stop that thread.

## 1. Read the issue

```bash
gh issue view <n>
```

If it has no finish condition, stop and ask for one. Do not invent it.

## 2. Start or resume

State lives in `.agent/progress/issue-<n>.md` on the issue branch, committed and
pushed after every round.

```bash
git fetch -q
git branch -a --list "*issue-<n>-*"
```

**If a branch exists, resume:**

1. Check it out and pull it.
2. Read `.agent/progress/issue-<n>.md` in full, then run `git log --oneline main..HEAD`
   and `git status`.
3. Re-run the command under "Last check run" to see the real current state.
4. Add a round-log row `resumed`, then continue at "Next action". Do not redo ticked
   plan steps. Change the plan only when the evidence shows it is wrong, and say why
   under "Decisions and notes".
5. If `Status: blocked` and the issue has no new comment answering the blocker, stop
   and say so.

**Otherwise, start:**

1. Create the branch from the latest `origin/main`:
   `git fetch -q origin && git checkout -b issue-<n>-<short-slug> origin/main`
   (Not `git checkout main`: in a worktree, `main` may be checked out in another folder.)
2. Read `AGENTS.md`. Find the row for the area you will change, and read every document
   it marks **Required**, then the source files those documents name. Note the
   specification section the change touches. Read nothing else until you need it.
3. Copy `.agent/progress/TEMPLATE.md` to `.agent/progress/issue-<n>.md` and fill it in:
   - **Finish condition:** the issue's items as checkboxes.
   - **Plan:** every step you expect, in order, as checkboxes, each naming the files it
     touches. Write the whole plan before changing any code.
   - `Status: in-progress` and a specific **Next action**.
4. Save it remotely: `scripts/agent_checkpoint.sh <n> "plan"`.

## 3. The loop (at most 5 rounds per session)

Each round works the first unticked plan step:

1. **Test first.** Add or update a test that fails for the right reason. Run it and
   confirm it fails.
2. **Implement** the smallest change that makes it pass.
3. **Verify,** narrowest first: the one test file, then `scripts/verify.sh <stage>` for
   the stage you touched (`backend`, `frontend` or `docs`).
4. **Record, before anything else:** tick the plan step if it is done, add a round-log
   row (change, check, result), and rewrite "State for the next session": the exact last
   command, its result (first failing lines, or "green"), your hypothesis, and one
   specific next action.
5. **Checkpoint:** `scripts/agent_checkpoint.sh <n> "<what changed>"`.
6. Green with steps left: next round. Red: change one thing and go again. Every
   finish-condition item proven: go to section 5.

## 4. Stop conditions

Stop the loop when ANY of these is true. First set `Status:` and a specific "Next
action" in the progress file, then checkpoint.

- **Done:** every finish-condition item is checked and verification passes. Go to
  section 5.
- **Stuck:** the same check failed in 3 rounds with different fixes, or 5 rounds have
  passed this session. Report what you tried, the exact failing output and your best
  hypothesis. Do not keep guessing. Use `Status: blocked` only if a person must act;
  otherwise leave `in-progress` so a new session can continue.
- **Needs a person:** the specification and the code disagree; the change touches a
  sensitive module (see `spec files/Engineering_Standards.md`); the fix needs a new
  dependency, a migration of existing data, a live Nagios or network device, or a
  secret. Set `Status: blocked` and write the question under "Decisions and notes".
- **Scope creep:** see "Hard limits".

## 5. Finish

1. Update the owning specification in `spec files/`, and `spec files/Implementation_Status.md`
   if a gap opened or closed. Run `scripts/verify.sh docs`.
2. Run `scripts/verify.sh all` once. CI runs everything, so it must pass here too.
3. Delete the progress file and push: `git rm .agent/progress/issue-<n>.md`, commit, push.
   CI rejects a pull request that is ready for review while the file exists.
4. Open the pull request from `.github/pull_request_template.md` with `Closes #<n>`:
   `gh pr create --base main --fill` then edit the body. Tick the checklist honestly and
   list anything you did not verify. If you are not done, open it as a **draft**
   (`gh pr create --draft`) and keep the progress file.
5. Report in this shape, and nothing longer:
   - PR link
   - Finish-condition checklist (ticked or not, each with the check that proves it)
   - What you did not verify
   - Anything a person must decide
