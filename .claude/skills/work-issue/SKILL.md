---
name: work-issue
description: Work one GitHub issue end to end in a verify loop with a written plan and a progress file, so a stopped job can be resumed. Use when asked to work, fix, implement or resume an issue by number.
---

# Work one issue

Input: an issue number (`$ARGUMENTS`), called `<n>` below. Read it with
`gh issue view <n>`. If it has no finish condition, stop and ask for one; do not
invent it.

State lives in `.agent/progress/issue-<n>.md` on the issue branch, committed and
pushed after every round. A session that dies loses nothing that was
checkpointed. Never keep the plan only in your head or in chat.

## Start or resume

1. Look for an existing branch and progress file:
   `git fetch -q && git branch -a --list "*issue-<n>-*"`.
2. **Resume** if one exists: check out the branch, pull it, read
   `.agent/progress/issue-<n>.md` fully, then `git log --oneline main..HEAD` and
   `git status`. Re-run the check named under "Last check run" to see the real
   current state. Continue at "Next action". Add a line to the round log:
   `resumed`. Do not redo ticked plan steps; do not rewrite the plan unless the
   evidence shows it is wrong, and then say why in "Decisions and notes".
   If `Status: blocked` and the issue has no new comment answering the blocker,
   stop and say so.
3. **Start** otherwise: create `issue-<n>-<short-slug>` from an up-to-date
   `main`, then read the **Required** documents for the affected area in
   `AGENTS.md` and the source files they name. Copy
   `.agent/progress/TEMPLATE.md` to `.agent/progress/issue-<n>.md` and fill it:
   - **Finish condition**: the issue's items as checkboxes.
   - **Plan**: every step you expect, in order, as checkboxes naming the files
     each touches. Write the whole plan before changing code.
   - `Status: in-progress` and a concrete **Next action**.
   Run `scripts/agent_checkpoint.sh <n> "plan"` so the plan is saved remotely.

## Loop (max 5 rounds per session)

Each round works on the first unticked plan step:

1. **Test first.** Add or update a test that fails for the right reason.
2. **Implement** the smallest change that satisfies it.
3. **Verify** the narrowest target first (one test file), then
   `scripts/verify.sh <backend|frontend|docs>` for the stage you touched.
4. **Record**, before anything else: tick the plan step if it is done, add a row
   to the round log (change, check, result), and rewrite "State for the next
   session" (exact command, first failing lines or "green", hypothesis, next
   action).
5. **Checkpoint**: `scripts/agent_checkpoint.sh <n> "<what changed>"`.
6. If green and steps remain, start the next round. If red, change one thing and
   go again. If every finish-condition item is proven, go to Finish.

## Stop conditions

Stop the loop when ANY of these is true, and first set `Status:` and "Next
action" in the progress file and checkpoint:

- **Done:** every finish-condition item is checked and verify passes. Go to
  Finish.
- **Stuck:** the same check failed in 3 rounds with different fixes, or 5 rounds
  have passed this session. Set `Status: blocked` (or leave `in-progress` if a
  new session could simply continue), report what you tried, the exact failing
  output and your best hypothesis. Do not keep guessing.
- **Needs a human:** the spec and code disagree; the change touches a sensitive
  module (see `Engineering_Standards.md`); a fix needs a new dependency, a
  migration of existing data, a live Nagios or network device, or a secret. Set
  `Status: blocked` and write the question under "Decisions and notes".
- **Scope creep:** the fix requires changing something not named in the issue.
  Note it as a new issue instead.

Never skip, delete or weaken a test to get green. Never run live tests
(`server/tests/integration`, `server/tests/e2e`).

## Finish

1. Update the owning spec in `spec files/`, and `Implementation_Status.md` if a
   gap opened or closed. Run `scripts/verify.sh docs`.
2. Run `scripts/verify.sh all` once, since CI runs everything.
3. Delete the progress file: `git rm .agent/progress/issue-<n>.md`. CI fails a
   pull request that is ready for review while it exists. Commit and push.
4. Open the pull request from the template with `Closes #<n>`, tick the
   checklist honestly and list anything not verified. If you are not done, open
   it as a **draft** instead and keep the progress file.
5. Report: PR link, finish-condition checklist, what you did not verify.
