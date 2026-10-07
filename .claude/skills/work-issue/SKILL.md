---
name: work-issue
description: Work one GitHub issue end to end in a verify loop (read specs, test first, implement, verify, update docs, open PR). Use when asked to work, fix or implement an issue by number.
---

# Work one issue

Input: an issue number (`$ARGUMENTS`). Read it with `gh issue view <n>`. If it
has no finish condition, stop and ask for one; do not invent it.

## Setup (once)

1. Create a branch `issue-<n>-<short-slug>` from an up-to-date `main`.
2. Read the **Required** documents for the affected area in `AGENTS.md`, then the
   source files they name. Note the spec section the change touches.
3. Write the finish condition as a checklist in your first message.

## Loop (max 5 rounds)

Each round:

1. **Test first.** Add or update a test that fails for the right reason.
2. **Implement** the smallest change that satisfies it.
3. **Verify** the narrowest target first (one test file), then
   `scripts/verify.sh <backend|frontend|docs>` for the stage you touched.
4. If green, go to Finish. If red, read the failure, change one thing, and
   start the next round. Record in one line what failed and what you changed.

## Stop conditions

Stop the loop when ANY of these is true:

- **Done:** every finish-condition item is checked and verify passes.
- **Stuck:** the same check failed in 3 rounds with different fixes, or 5 rounds
  have passed. Report what you tried, the exact failing output and your best
  hypothesis. Do not keep guessing.
- **Needs a human:** the spec and code disagree; the change touches a sensitive
  module (see `Engineering_Standards.md`); a fix needs a new dependency, a
  migration of existing data, a live Nagios or network device, or a secret.
- **Scope creep:** the fix requires changing something not named in the issue.
  Note it as a new issue instead.

Never skip, delete or weaken a test to get green. Never run live tests
(`server/tests/integration`, `server/tests/e2e`).

## Finish

1. Update the owning spec in `spec files/`, and `Implementation_Status.md` if a
   gap opened or closed. Run `scripts/verify.sh docs`.
2. Run `scripts/verify.sh all` once, since CI runs everything.
3. Commit, push the branch and open a PR from the template with `Closes #<n>`.
   Tick the checklist honestly; list anything not verified.
4. Report: PR link, finish-condition checklist, what you did not verify.
