# Agent Workflow and CI

**Last verified against the repository:** 2026-10-08

How work is picked up, verified and merged, by people and by coding agents.
Origin: the 2026-10-07 mentoring session (source of truth must be readable by
agents; loop engineering; last-mile checks in CI; reproducible environments).

## Where documents live

| Kind | Location |
|---|---|
| Specifications (current behavior and constraints) | `spec files/` |
| Plans, proposals, acceptance and remediation reports | `docs/plans/` |
| Operator and user manuals | `docs/manuals/` |
| Test plans and live-lab plans | `server/tests/plans/` |
| Tasks and open defects | GitHub issues |

See `docs/README.md` for the rules and lifecycle.

## One checkout per agent

Two agents (or an agent and a person) must never share a working tree: they move each
other's branches, mix uncommitted files into the wrong commit and can end up with a
stray commit on someone else's pull request. Give each agent its own git worktree:

```bash
scripts/agent-worktree.sh <name>     # creates ../<repo>-<name> on branch qa/<name>, with its own .venv and node_modules
```

Start the agent from that folder. It creates its own `issue-<n>-<slug>` branches from
`origin/main` (the workflow never runs `git checkout main`, which fails when `main` is
checked out in another folder). A branch can be checked out in only one worktree at a
time. Remove a worktree with `git worktree remove ../<repo>-<name>`; the issue
branches and their pull requests are unaffected.

## Source of truth

1. Tasks live in GitHub Issues, created from the **Task** template
   (`.github/ISSUE_TEMPLATE/task.yml`): title, problem and reproduction, finish
   condition, references. Chat messages are not a task record.
2. Behavior lives in `spec files/` (routed by `AGENTS.md`). A task that changes
   behavior names the spec section it changes.
3. Current gaps live in `Implementation_Status.md`.

## The agent loop

The executable version is `.agent/workflows/work-issue.md`, written for any agent.
Claude Code (`.claude/skills/work-issue/`) and OpenCode (`.opencode/commands/work-issue.md`)
load it through thin adapters, run as `/work-issue <issue number>`; any other agent is
told to follow the file. It carries the loop, the 5-round limit and the stop conditions
below. Change the procedure only in that file; the adapters must stay a few lines long
so they cannot drift.

For every task, an agent repeats until the finish condition holds:

1. **Read** the issue and check that its finish condition covers every requirement
   it states (a gap is raised with a person, not skipped), then the **Required** documents for the area (`AGENTS.md`)
   and the source files they name.
2. **Write or update the test first** when behavior changes (TDD); the test
   encodes the finish condition.
3. **Implement** the smallest change.
4. **Verify** with the smallest relevant target, then `scripts/verify.sh <stage>`.
   Fix and repeat; do not widen scope to make a check pass.
5. **Update docs** in the same change: the owning spec, and
   `Implementation_Status.md` if a gap opened or closed.
6. **Verify the finish condition meets the issue**: re-read the issue and name,
   then run, the check that proves each requirement.
7. **Open a PR** from the template. CI is the last-mile check; a PR is done when
   CI is green, not when it works locally.

Stop and ask a person instead of looping when: a spec and the code disagree and
the user has not chosen, the change touches a sensitive module
(`Engineering_Standards.md`), or the same check has failed three times with
different fixes.

## Progress file and resuming

An agent that stops mid-job (session ended, limit hit, blocked on a question)
must not force the next session to start over. All job state is kept in
`.agent/progress/issue-<n>.md`, created from `.agent/progress/TEMPLATE.md`, on
the issue branch, and checkpointed after every round.

| Section | Holds |
|---|---|
| Header | Issue, branch, `Status:` (`in-progress`, `blocked`, `ready-for-review`) |
| Finish condition | The issue's items as checkboxes; ticked only when a check proves them |
| Plan | The whole plan, written before any code, as ordered checkboxes naming the files each step touches |
| Round log | One row per round: change, check run, result |
| State for the next session | Last command run, its result, hypothesis, and one specific **Next action** |
| Decisions and notes | Choices, things ruled out, questions for a person |

Rules:

- Write the plan first and push it (`scripts/agent_checkpoint.sh <n> "plan"`),
  so even a session that dies in the first minute leaves something to resume.
- After every round, update the file, then run
  `scripts/agent_checkpoint.sh <n> "<what changed>"`. The script validates the
  file, commits as `wip(#<n>): ...` and pushes. It refuses to run on `main`.
- To resume, run `/work-issue <n>` again (or tell your agent to follow the workflow file for issue `<n>`). It finds the branch, reads the file,
  re-runs the last check to see the real state, and continues at "Next action"
  without redoing ticked steps.
- The file is scaffolding, not documentation. Delete it (`git rm`) before the
  pull request is ready for review. CI fails a non-draft pull request that still
  contains one, and passes a draft. If the job is unfinished, open a draft PR
  and keep the file.
- `scripts/check_agent_progress.py` checks the structure (valid status, all
  sections, no template placeholders, a non-empty Next action). It runs in
  `scripts/verify.sh docs`.

## Test results

Where results go is defined in [`docs/test-runs/README.md`](../docs/test-runs/README.md):

| Result | Location |
|---|---|
| CI test output | JUnit XML in the `backend-test-results` and `frontend-test-results` artifacts of the Actions run, kept 30 days |
| Local test output | `test-results/` (git-ignored) |
| Live-lab and acceptance runs | A committed, sanitized `docs/test-runs/<date>-<slug>/REPORT.md` from `scripts/new_test_run.sh`, naming the commit tested, one row per case and an issue for every failure |
| Raw lab evidence | The harness `output_root` on the lab host; never committed |

## Test environments

| Layer | What it needs | How |
|---|---|---|
| Unit and mocked API tests | Nothing | `scripts/verify.sh`, and CI on every PR |
| Local lab (fast lane) | Docker | `scripts/lab up`, `scripts/lab smoke`; see [`docs/manuals/Local_Lab.md`](../docs/manuals/Local_Lab.md). A real Nagios and five target servers on an isolated network; not the installer, systemd, DHCP or NCPA installs |
| Real appliance and VM lab | Installer build, VirtualBox (this laptop) or libvirt (the retained lab) | `scripts/vmlab` with the `demo/` target VMs; plan in [`docs/plans/VM_Lab_Plan.md`](../docs/plans/VM_Lab_Plan.md). The snapshot holds Ubuntu + Nagios only, so it cannot go stale. The libvirt e2e harness in `server/tests/e2e/network_discovery/` is separate. Manual or scheduled, never on pull requests from forks |

An agent loop may use the local lab; it must not run the real-lab harness.
Record results of lab runs in `docs/test-runs/`.

## Verification commands

| Stage | Command | Notes |
|---|---|---|
| Docs | `scripts/verify.sh docs` | Agent progress files are well formed; relative links resolve; environment variables match the README table; browser routes match `App.tsx`, `pageAccess.ts` and the spec. Standard library only |
| Backend | `scripts/verify.sh backend` | Route and client-API drift checks, then `pytest tests/unit` in `server/` with `FLASK_DEBUG=1`; ~4 min, 2,167 passed / 14 skipped on 2026-10-08 |
| Frontend | `scripts/verify.sh frontend` | `npm run test`, `npm run build`, `npm run lint` (errors fail; warnings do not) |
| Everything | `scripts/verify.sh all` | Same stages as CI |

Live tests (`server/tests/integration/`, `server/tests/e2e/`) are never part of
CI or an agent loop without explicit approval; they need a lab Nagios.

## Continuous integration

`.github/workflows/ci.yml` runs on every pull request and on pushes to `main`.

| Job | Runs | Blocking |
|---|---|---|
| `docs` | `scripts/verify.sh docs` | yes |
| `backend` | Python 3.14, install `requirements*.txt`, `scripts/verify.sh backend` | yes |
| `frontend` | Node 22, `npm ci`, test, build, lint | yes |

Rules: CI uses no secrets and no network devices; every setting comes from the
environment (see the production settings table in `README.md`); a failing job
is fixed in the PR, never skipped. Protect `main` by requiring the three jobs.

Each test job uploads its JUnit XML as an artifact (`if: always()`, so failures keep
their results).

Not yet automated (see `Implementation_Status.md`): deployment, installer ISO
build and install test, spec-vs-code drift checks.

## Drift checks

A drift check fails when documentation and code disagree, so an agent can trust
the specs. Each is a script in `scripts/`; when one fails, fix the document (or
the code) in the same change.

| Script | Compares | Stage |
|---|---|---|
| `check_route_drift.py` | Every `/api` route registered in Flask against the `METHOD /api/...` entries in `Backend_Modules_and_Routes.md`. A first cell struck through with `~~` marks a documented-disabled route | backend |
| `check_client_api_drift.py` | Every `/api/...` string in `client/src` (including `${CONST}` prefixes) against the routes Flask serves, with the HTTP method when the call states it. A `${...}` placeholder matches any one segment | backend |
| `check_frontend_route_drift.py` | `<Route>` paths and page components in `App.tsx`, `PAGE_PERMISSIONS` in `pageAccess.ts` and the "Browser route catalog" table in `Frontend_Modules_and_Routes.md` | docs |
| `check_env_drift.py` | Environment variables the server reads (`os.environ`, `os.getenv`, `env_*` helpers) against the README "Production settings" table, which the installer builds `pinpoint.env` from | docs |
| `check_doc_links.py` | Relative markdown links in `AGENTS.md`, `README.md` and `spec files/` | docs |

Rules the checks rely on: put each route in its own table row (a combined row
such as "`/pause` and `/resume`" cannot be checked); a new environment variable
gets a README row in the commit that adds it.

Not yet checked: seeded permissions versus `require_permission` calls, the
permission list in `Backend_Modules_and_Routes.md` and the client permissions
(`Implementation_Status.md` already lists one known mismatch, the discovery stop
permission); component and module inventories; model inventories.

## Reproducible environment

`.devcontainer/devcontainer.json` gives Python 3.14 and Node 22 with
dependencies installed, so "works on my machine" differences are removed
before CI. Do not create bespoke VMs for development checks.

## Deployment environment (installer contract)

The installer repository (`lorraine-pangilinan/PinPoint-Installer`) builds an
Ubuntu Server 22.04.5 LTS appliance with Nagios Core 4.5.11, then clones `main`
into `/opt/pinpoint/Network-Diagnosis-System`, runs `npm ci && npm run build`
in `client/`, and runs `server/` under Gunicorn (1 worker, 4 threads, as the
`pinpoint` user) behind Nginx. Nagios's web UI moves to `127.0.0.1:8081`.

This repository's side of the contract, all implemented as of 2026-10-08:

- Settings come from `/etc/pinpoint/pinpoint.env` (table in `README.md`); a
  setting added to `server/config.py` is added to that table in the same change.
- `server/migrations/` is committed; every model change ships with a migration.
  The installer runs `flask db upgrade` (multi-database).
- `flask init-production` creates reference data and one administrator, flagged
  `Needs_Setup`: the installer's email (`admin-xxxxx@pinpoint.lan`) and password are
  placeholders, and the first sign-in must replace both through the setup window
  (`POST /api/user/complete-setup`). The VM lab's `setup-admin` completes it.
- `PINPOINT_SCHEDULER=1` only for the Gunicorn service.
- The `pinpoint` account may write `hosts.cfg` and `plugin-services.cfg`, runs
  `nagios -v`, and may `sudo systemctl reload nagios`; nothing else. Writing to
  the plugin directory is intentionally not granted.

A change that breaks any item above breaks every installed server on upgrade;
raise it with the installer owners first. Installer code stays in its own
repository (`Implementation_Status.md`).
