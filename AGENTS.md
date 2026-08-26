# AGENTS.md — Guide for AI Agents Working on Pinpoint (Detech-IT / 4D-G2)

This document tells you what this system is, what has been built, what has not,
and the rules you must follow. Read it before touching any file.

---

## 1. What Is This System?

**Pinpoint** is a network monitoring dashboard for non-expert network
administrators. It wraps **Nagios Core** with a clean web interface so that
Nagios' native UI never needs to be used.

The system runs entirely on a single **Ubuntu Server** machine. Both Nagios
and the Pinpoint application (Flask backend + React frontend) are installed
on the same host via a custom installer. There is no cloud component.

Nagios is a standalone monitoring engine. Pinpoint reads Nagios data and
presents it — it does **not** replace Nagios. Nagios' native web UI is
intentionally disabled; Pinpoint is the only interface.

---

## 2. Repository Layout

```
/
├── client/                 React + TypeScript front-end (Vite)
│   └── src/
│       ├── components/     UI components grouped by page
│       ├── pages/          Top-level page components
│       ├── contexts/       React contexts (e.g. SystemSettingsContext)
│       ├── types/          TypeScript type definitions
│       ├── data/           Static mock/seed data (temporary — to be replaced by API)
│       └── test/           Front-end unit tests (Vitest)
│
├── server/                 Flask back-end
│   └── app/
│       ├── api/
│       │   ├── system/     All /system/* routes (main feature area)
│       │   ├── user/       /user/* routes (auth, management)
│       │   ├── helper/     Shared utilities (responses, validation, converters)
│       │   └── commands/   Flask CLI commands (e.g. seed)
│       ├── nagios/         Nagios data access (status.py, notifications.py)
│       ├── network_discovery/  Network scanning and Nagios host config generation
│       ├── ncpa_deployment/    Remote NCPA agent installation
│       ├── logging/        Activity log helpers
│       ├── history_models.py   SQLAlchemy models → history.db (Nagios data only)
│       └── system_models.py    SQLAlchemy models → system.db (application data)
│
├── spec files/
|   | 
|   ├── Display_Requirements.md                        Dashboard & Network Health page spec
|   ├── Alerts_Notifications_History_Requirements.md   History page spec
|   └── Plugins_List.md                                Available Plugins included by Pinpoint for Nagios
|
|
└── AGENTS.md               This file
```

---

## 3. Tech Stack

| Layer | Technology |
|---|---|
| Back-end language | Python 3.14 |
| Back-end framework | Flask |
| ORM | SQLAlchemy (Flask-SQLAlchemy) |
| Migrations | Flask-Migrate (Alembic) — two databases, requires `--multidb` flag |
| Auth | Flask-Login |
| Front-end language | TypeScript |
| Front-end framework | React (Vite) |
| Back-end tests | pytest (run from `server/` directory) |
| Front-end tests | Vitest |

---

## 4. The Two Databases

The system uses **two separate SQLite databases**. This is critical — putting
the wrong model in the wrong database breaks things.

| Database | File | Bound key | Purpose |
|---|---|---|---|
| `system.db` | `server/system.db` | *(default, no bind key)* | All application data: users, roles, permissions, settings, acknowledgements, deployment records, activity logs |
| `history.db` | *(configured separately)* | `"history"` | Nagios-sourced time-series snapshots: `HostStatus`, `ServiceStatus`, `HostPerfData`, `ServicePerfData`, `ProgramStatus` |

**Rule: `history_models.py` is for Nagios data only.** If you are adding a
table that the application generates (not Nagios), it goes in
`system_models.py`. Acknowledgement tracking, for example, lives in
`system_models.py` even though it relates to monitoring events.

### Running migrations

Because there are two databases, always use the `--multidb` flag:

```bash
# From server/ directory, with .venv activated
flask db migrate -m "describe the change"
flask db upgrade
```

If a `migrations/` folder does not exist yet, initialize it first:

```bash
flask db init --multidb
```

---

## 5. What Has Been Built

### Back-end (server/app/)

**Authentication & Users (`api/user/`)**
- Login / logout (`login.py`)
- User management: create, update, deactivate (`management.py`)
- Note: **users are never deleted**, only deactivated (`UserStatus.INACTIVE`).
  All foreign keys to `User` are safe permanent references.

**System Settings (`api/system/settings.py`)**
- GET / PUT for the singleton `SystemSettings` table.
- Settings include `dashboardRefreshRate` and `scanFrequency`.

**Dashboard routes (`api/system/dashboard.py`)**
- `GET /system/dashboard/status` — Nagios process health + server resources
- `GET /system/dashboard/summary` — stat cards, ping metrics, NCPA averages
- `GET /system/dashboard/alerts` — active alerts feed with ack filter
- `POST /system/dashboard/alerts/acknowledge` — single alert ack
- `POST /system/dashboard/alerts/acknowledge-all` — batch ack
- `DELETE /system/dashboard/alerts/acknowledge` — unacknowledge
- `GET /system/dashboard/notifications` — 5 most recent notifications

**Network Health routes (`api/system/network_health.py`)**
- `GET /system/network-health/summary` — page-level summary strip
- `GET /system/network-health/trends` — time-bucketed perf charts
- `GET /system/network-health/plugins` — service health by plugin type

**Host Status Table (`api/system/network_hosts.py`)**
- `GET /system/network-health/hosts` — paginated host table with filters
- `GET /system/network-health/hosts/<hostname>/detail` — host detail panel
- `POST/DELETE /system/network-health/hosts/acknowledge` — host ack/unack

**Service Status Table (`api/system/network_services.py`)**
- `GET /system/network-health/services` — paginated service table with filters
- `GET /system/network-health/services/<hostname>/<path:service_name>/detail` — service detail
- `POST/DELETE /system/network-health/services/acknowledge` — service ack/unack

**Shared aggregation helpers (`api/system/statistics.py`)**
- Pure functions, no routes. Used by dashboard and network health.
- `get_latest_hosts()`, `get_latest_services()`, `host_counts()`,
  `service_counts()`, `active_alert_count()`, `avg_ping_metrics()`,
  `ncpa_averages()`, `nagios_server_resources()`, `service_health_by_plugin()`,
  `perf_trends()`

**Device Inventory (`api/system/network_hosts.py` + `network_discovery.py`)**
- `GET /system/hosts` — paginated list of discovered devices
- `GET /system/hosts/<id>/ports/tcp` — open TCP ports for a device
- `GET /system/hosts/<id>/ports/udp` — open UDP ports for a device

**Network Discovery (`api/system/network_discovery.py`)**
- Routes for triggering network scans and reading results.

**NCPA Deployment (`api/system/ncpa_deployment.py`)**
- Routes for deploying the NCPA monitoring agent to remote hosts over SSH.

**Notifications (`api/system/notifications.py`)**
- Routes for Nagios notification history and the unread cursor.

**Logs & Reports (`api/system/log.py`, `api/system/report.py`)**
- System activity logs and report generation/export.

**Nagios data layer (`app/nagios/`)**
- `status.py` — parses Nagios `statusjson.cgi` and writes to `history.db`
- `notifications.py` — queries Nagios `archivejson.cgi`

### Front-end (client/src/)

**Pages (all exist as scaffolded components):**
- `LoginPage.tsx` — login form, connected to API
- `DashboardPage.tsx` — dashboard shell (components use static data — API integration pending)
- `NetworkHealthPage.tsx` — network health shell (static data — API integration pending)
- `DeviceInventoryPage.tsx` — device table (partially connected)
- `ManageAccountsPage.tsx` — user management (connected)
- `SettingsPage.tsx` — system settings (connected)
- `SystemLogsPage.tsx` — activity logs (connected)
- `ReportsPage.tsx` — reports (connected)
- `PluginsPage.tsx` — plugin management (static/pending)
- `TopologyPage.tsx` — network topology view (static/pending)

**Component groups:**
- `components/dashboard/` — dashboard UI components (mostly static data)
- `components/network-health/` — network health UI components (mostly static data)
- `components/device-inventory/` — device table component
- `components/manage-accounts/` — user management UI
- `components/settings/` — settings form components
- `components/layout/` — `Sidebar`, `Header`, `AdminLayout`
- `components/shared/` — reusable components across pages
- `contexts/SystemSettingsContext.tsx` — provides system settings to all pages

---

## 6. What Has NOT Been Built Yet

- **Dashboard & Network Health front-end → API connection.** The page
  components and UI exist but still use mock data from `src/data/`. The
  back-end routes are complete. The next step is connecting them.
- **Alerts & Notifications History page** — back-end routes not yet built.
  Spec is defined in `Alerts_Notifications_History_Requirements.md`. The
  `AckHistory` table in `system_models.py` is the data source for
  acknowledgement records on this page.
- **AUTO_RESOLVED ack cleanup** — when an alert returns to OK/UP,
  `AlertAcknowledgement` should be deleted and an `AckHistory` row with
  `AckAction.AUTO_RESOLVED` should be written. This logic is not yet wired
  into the Nagios status polling cycle.
- **Plugins page** — currently static. Plugin management not implemented.
- **Installer** — currently being developped in a different repository.

---

## 7. Coding Rules

### General

- **Read the relevant files before writing code.** Do not assume structure
  from memory — check `system_models.py`, `history_models.py`, and the route
  file you are modifying before making changes.
- **Match existing style.** This project uses SQLAlchemy mapped columns,
  Flask blueprints, and a consistent response pattern. Do not introduce a
  new pattern without a strong reason.
- **Write tests for new features.** Tests live in `server/tests/`. Use pytest.
  Test assuming prerequisites that depend on unbuilt features are not
  available — mock them.
- **Run `python -m py_compile <file>` after editing Python.** Catch syntax
  errors before committing.

---

### Back-end — Code Style

#### File structure

Every route file must start with a **module docstring** that explains the
purpose of the module and lists the routes it exposes. Follow the pattern
established in `log.py` and `notifications.py`:

```python
"""
Brief description of what this module handles.

Longer explanation if needed — how it works, what concepts are involved, etc.

Routes
------
GET  /system/example
    Short description of what this route returns.

POST /system/example
    Short description of what this route does.
"""
```

#### Route docstrings

Every route function must have a docstring that:
1. Explains what the route does and its behaviour in plain language.
2. Shows the expected JSON body format if the route accepts one.

Both parts belong in the same docstring — do not write one without the other
when a body is involved. For GET routes with no body, the explanation alone
is sufficient.

```python
@user_bp.put('/roles/<int:id>')
@login_required
def edit_role(id):
    """
    Update the name, description, and permission set of an existing role.
    Only active roles can be edited. Permissions are replaced entirely —
    any permission not included in the new list will be removed.

    JSON Format
    {
        "name": "name",
        "description": "description",
        "permissions": [1, 2, 4, 5]
    }
    """
```

#### Section banners

Use `# =====` banners to separate logical groups of routes within a file.
Keep them consistent in width and style:

```python
# ==========================================================
# SECTION NAME
# ==========================================================
```

#### Helper functions

Extract reusable logic into standalone helper functions in the same file.
Do **not** prefix helper function names with `_` — that convention is not
used in this project. Only extract a function when it is genuinely reusable
across more than one route, or when extracting it meaningfully improves
readability through separation of concern. Logic that is only called once
and reads clearly inline should stay inline.

Every helper function must have a plain prose docstring explaining what it
does, what it expects, and any side effects worth knowing (e.g. "does not
commit"). No formal parameter block is required — keep it short and clear:

```python
# Good — reusable, clearly named, has a docstring
def get_or_create_cursor(user_id):
    """
    Return the NotificationCursor row for this user, creating one with
    last_seen_ts=0 if it does not exist. Does not commit — caller is responsible.
    """
    ...

# Bad — only called once, trivial, and the underscore prefix is not used here
def _build_response():
    ...
```

#### Validation pattern

Validate inputs with early guard clauses that return immediately.
Use the `validate_*` helpers from `app/api/helper/validation.py` where
they exist. For custom checks, follow the same pattern — return `err` if
it is not `None`:

```python
err = validate_json_data(data)
if err is not None:
    return err

err = validate_role_exists(id)
if err is not None:
    return err
```

#### Building list responses

Use `items = []` followed by a `for` loop with `items.append({...})`.
Do not use list comprehensions for response serialization — it hurts
readability when there are many fields:

```python
items = []
for role in roles.items:
    items.append({
        "id": role.RoleID,
        "name": role.Name,
        "description": role.Description,
    })
```

#### Request body parsing

Use `request.get_json()` for required JSON bodies. Use
`request.get_json(silent=True) or {}` only when the body is genuinely
optional and the route can handle a missing body gracefully.

#### Responses

All API responses must use the standard helpers from
`app/api/helper/responses.py`:

```python
from app.api.helper import success, error

return success({"key": "value"})
return success(message="Created.", status=201)
return error("Not found.", 404)
return error("Bad input.", 400)
```

Never return raw `{"message": ...}, 200` dicts directly from routes.

Response envelope shape:
```json
{ "success": true, "data": { ... } }
{ "success": false, "message": "..." }
```

#### Permissions

Check permissions with the `@require_permission("permission.name")`
decorator. Every route that returns user or system data needs it.

#### Database sessions

Use `db.session`. Always call `db.session.rollback()` in `except` blocks
that follow a failed `db.session.commit()`.

#### Model file ownership

- `history_models.py` — Nagios-sourced snapshots only. Do not add
  application-generated tables here.
- `system_models.py` — everything else.

#### Enums

Define Python `Enum` classes for any field with a fixed set of values.
Use `sa.Enum(MyEnum)` in the column definition.

#### Users are never deleted

Do not add `ON DELETE CASCADE` or guard `nullable=True` on foreign keys
pointing at `User`. Users are only deactivated. FK references to `User`
are always safe.

---

### Sensitive modules — handle with extra care

**`app/network_discovery/`** and **`app/ncpa_deployment/`** interface with the
network and remote devices over SSH. Any changes here must:
- Validate and sanitize all inputs before they touch the network or shell
- Never expose credentials in logs or responses
- Use parameterized commands, never string interpolation for shell execution
- Be reviewed for injection risks before merging

---

### Migrations

After any change to `system_models.py` or `history_models.py`:

```bash
cd server
source .venv/bin/activate
flask db migrate --multidb -m "short description"
flask db upgrade --multidb
```

Both databases must be migrated together. Never edit migration files
manually unless you know exactly what you are doing.

---

### Front-end

- TypeScript only — no `.js` files in `client/src/`.
- Component files use `.tsx`.
- API calls should use `fetch` with the `/system/` prefix (the Flask backend
  is served at the same origin).
- Page components live in `src/pages/`. Sub-components belong in
  `src/components/<page-name>/`.
- Static mock data in `src/data/` is temporary. When connecting a page to
  the API, remove the mock data import and replace it with a real fetch.
- The `SystemSettingsContext` provides `dashboardRefreshRate` and
  `scanFrequency`. Use it — do not hardcode refresh intervals.

---

## 8. Key Facts That Are Easy to Get Wrong

- **`NAGIOS_HOST = "localhost"`** — the Nagios server identifies itself as
  `localhost` in `status.dat`. This constant is defined in `statistics.py`.
  Do not change it without also updating the Nagios config.
- **Two databases, one ORM session** — `db.session` is shared, but
  `__bind_key__ = "history"` on history models routes queries to `history.db`
  automatically. You do not need separate sessions.
- **`AcknowledgementType` on `HostStatus`/`ServiceStatus`** comes from
  Nagios — it is Nagios' own acknowledgement state, not the application's.
  The application's acknowledgement system is `AlertAcknowledgement` and
  `AckHistory` in `system_models.py`. These are separate concepts.
- **`statistics.py` contains functions, not routes.** Import from it;
  do not register it as a blueprint or add routes to it.
- **Service names can contain slashes** — NCPA service descriptions use paths
  like `cpu/percent`. Use `<path:service_name>` in Flask URL rules for any
  route that accepts a service name as a URL segment.
- **`perf_trends()` time windows** — valid `hours` values for the trends
  endpoint are `1, 6, 24, 168` (1 hour, 6 hours, 24 hours, 7 days). The
  front-end time range selector must match these values.
- **Averaging requires at least 2 data points** — per the spec (§3.5 of
  `Display_Requirements.md`), do not display a network-wide average if fewer
  than 2 hosts have reported data. Return `null` and let the front-end show
  "Insufficient data."

---

## 9. Spec Documents

Before implementing any feature on the Dashboard, Network Health, or History
pages, read the relevant spec first:

| Page | Spec file |
|---|---|
| Dashboard (`/dashboard`) | `Display_Requirements.md` §1 |
| Network Health (`/network-health`) | `Display_Requirements.md` §2 |
| Alert Acknowledgement | `Display_Requirements.md` §4 |
| Alerts & Notifications History | `Alerts_Notifications_History_Requirements.md` |

The specs define exactly what data to show, when to show it, when to hide it,
and what empty/error states look like. The back-end must serve what the spec
says — do not add fields the spec does not mention without checking with the
team first.

---

## 10. Running the Project

### Back-end

```bash
cd server
source .venv/bin/activate
flask run
```

Tests:
```bash
cd server
source .venv/bin/activate
pytest
```

### Front-end

```bash
cd client
npm install
npm run dev
```

Tests:
```bash
cd client
npm run test
```

---

## 11. What is Excluded

### Back-end
Topology - Will not be implemented in the current development of the system. May be used in future development.

### Front-end
Topology View - The topology view of the network should be removed from the front-end but keep its code, possibly to be implemented for furture use.