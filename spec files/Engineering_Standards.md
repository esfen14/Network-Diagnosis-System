# Engineering Standards

**Last verified against the repository:** 2026-09-27

## Before changing code

- Read the relevant specifications routed by the root `AGENTS.md`.
- Inspect the actual files being changed. For backend data work, inspect the
  owning model file and route/service code instead of relying on summaries.
- Preserve unrelated user changes in a dirty worktree.
- Match established Flask blueprint, SQLAlchemy mapped-column, response, React,
  and TypeScript patterns unless a deliberate architecture change is requested.

## General delivery rules

- Write or update tests for new behavior and regressions.
- Mock prerequisites that depend on unavailable network devices or unfinished
  features.
- Keep specifications current when modules, routes, pages, models, permissions,
  settings, integrations, or feature status change.
- Do not add fields beyond a normative page specification without confirming
  the product contract.

## Backend file and docstring rules

Every route module starts with a module docstring that describes the module and
lists its routes:

```python
"""
Brief module purpose.

Routes
------
GET  /system/example
    What the route returns.
"""
```

Every route function has a prose docstring. If it accepts a body, the same
docstring includes the expected JSON shape.

Separate logical route groups with consistent banners:

```python
# ==========================================================
# SECTION NAME
# ==========================================================
```

## Helpers

Extract a helper only when it is reused or meaningfully separates a concern.
Project-local helper names do not use a leading underscore as a general style
convention, though legacy/internal modules currently contain some underscored
helpers. New route-file helpers should follow the documented convention.

Every helper needs a short prose docstring describing inputs, result, and
important side effects such as whether it commits.

## Validation and request parsing

- Validate with early guard clauses.
- Reuse `validate_*` helpers from `app/api/helper/validation.py` when available.
- Return immediately when a validator produces an error.
- Use `request.get_json()` for required JSON.
- Use silent/empty parsing only for optional bodies.
- Validate and normalize all values before they reach network calls, SSH,
  filesystem paths, subprocesses, or Nagios configuration.

## Response serialization

Use `success` and `error` from `app.api.helper`; do not return ad hoc response
dictionaries from routes.

For multi-field list serialization, prefer an explicit loop:

```python
items = []
for role in roles.items:
    items.append({
        "id": role.RoleID,
        "name": role.Name,
    })
```

## Permissions and sessions

- Protect every data-bearing route with login and the applicable
  `@require_permission("permission.name")` decorator.
- Seed new permissions in `api/commands/seed.py` and wire matching client page
  access when applicable.
- Client-side guards never replace server-side authorization.
- Users are never deleted; change their `UserStatus` instead.

## Database rules

- Use `db.session` for both binds.
- Call `db.session.rollback()` in every exception path following a failed
  commit.
- Fixed-value fields use Python `Enum` classes and `sa.Enum` columns.
- Put only Nagios-produced snapshots in `history_models.py`; all
  application-produced data belongs on the default bind.
- Run multi-database migrations after any model change.

## Sensitive modules

Changes under `app/network_discovery/`, `app/ncpa_deployment/`, Plugin Manager
filesystem/configuration code, and command execution paths require an explicit
injection and secret-exposure review.

- Never interpolate untrusted input into shell commands.
- Prefer argument lists and parameterized operations.
- Restrict file destinations to configured directories.
- Validate archive contents and executable names.
- Never log or return credentials, passwords, tokens, SNMP communities, private
  keys, or secret-bearing command arguments.
- Preserve SSH fingerprint confirmation and Nagios pre-apply validation.

## Frontend rules

- Use TypeScript only in `client/src`; components use `.tsx`.
- Put pages in `src/pages/` and feature components in matching component
  folders.
- Use the shared API client and full `/api/...` paths.
- Keep wire-record conversion in `src/types/` when API naming differs from view
  naming.
- Use `SystemSettingsContext` for refresh/display configuration.
- Implement loading, error, empty, insufficient-data, and permission states.
- Update page access, sidebar, and route tests together when navigation changes.

## Verification commands

Backend syntax after editing Python:

```bash
cd server
source .venv/bin/activate
python -m py_compile path/to/edited_file.py
```

Backend tests:

```bash
cd server
source .venv/bin/activate
pytest tests/unit/
```

Frontend tests and build:

```bash
cd client
npm run test
npm run build
```

`server/pytest.ini` defaults to isolated tests in `tests/unit/` and excludes
recursive discovery of `tests/integration/` and `tests/e2e/`. Live integration
tests require an explicit target and may probe Nagios during collection. The
end-to-end harness remains opt-in and must not run during installation/startup.
Shared builders live in `tests/support/`; test approach documents live in
`tests/plans/`. See `server/tests/README.md` for commands and coverage boundaries.

Use the smallest relevant test target during iteration, then broaden verification
in proportion to the change's risk.

## Running locally

Backend:

```bash
cd server
source .venv/bin/activate
flask run
```

Frontend:

```bash
cd client
npm install
npm run dev
```
