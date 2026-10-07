# Agent Workflow and CI

**Last verified against the repository:** 2026-10-08

How work is picked up, verified and merged, by people and by coding agents.
Origin: the 2026-10-07 mentoring session (source of truth must be readable by
agents; loop engineering; last-mile checks in CI; reproducible environments).

## Source of truth

1. Tasks live in GitHub Issues, created from the **Task** template
   (`.github/ISSUE_TEMPLATE/task.yml`): title, problem and reproduction, finish
   condition, references. Chat messages are not a task record.
2. Behavior lives in `spec files/` (routed by `AGENTS.md`). A task that changes
   behavior names the spec section it changes.
3. Current gaps live in `Implementation_Status.md`.

## The agent loop

For every task, an agent repeats until the finish condition holds:

1. **Read** the issue, then the **Required** documents for the area (`AGENTS.md`)
   and the source files they name.
2. **Write or update the test first** when behavior changes (TDD); the test
   encodes the finish condition.
3. **Implement** the smallest change.
4. **Verify** with the smallest relevant target, then `scripts/verify.sh <stage>`.
   Fix and repeat; do not widen scope to make a check pass.
5. **Update docs** in the same change: the owning spec, and
   `Implementation_Status.md` if a gap opened or closed.
6. **Open a PR** from the template. CI is the last-mile check; a PR is done when
   CI is green, not when it works locally.

Stop and ask a person instead of looping when: a spec and the code disagree and
the user has not chosen, the change touches a sensitive module
(`Engineering_Standards.md`), or the same check has failed three times with
different fixes.

## Verification commands

| Stage | Command | Notes |
|---|---|---|
| Docs | `scripts/verify.sh docs` | Relative links in `AGENTS.md`, `README.md`, `spec files/` resolve |
| Backend | `scripts/verify.sh backend` | `pytest tests/unit` in `server/`, with `FLASK_DEBUG=1`; ~4 min, 2,167 passed / 14 skipped on 2026-10-08 |
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

Not yet automated (see `Implementation_Status.md`): deployment, installer ISO
build and install test, spec-vs-code drift checks.

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
- `flask init-production` creates reference data and one administrator.
- `PINPOINT_SCHEDULER=1` only for the Gunicorn service.
- The `pinpoint` account may write `hosts.cfg` and `plugin-services.cfg`, runs
  `nagios -v`, and may `sudo systemctl reload nagios`; nothing else. Writing to
  the plugin directory is intentionally not granted.

A change that breaks any item above breaks every installed server on upgrade;
raise it with the installer owners first. Installer code stays in its own
repository (`Implementation_Status.md`).
