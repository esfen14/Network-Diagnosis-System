# System Overview and Architecture

**Last verified against the repository:** 2026-09-27

## Product purpose

**Pinpoint** (Detech-IT / 4D-G2) is a network monitoring and administration
dashboard aimed at network administrators who should not need to use Nagios'
native interface. Nagios Core remains the monitoring engine. Pinpoint collects,
stores, aggregates, and presents Nagios data; it does not replace Nagios.

The production target is one Ubuntu Server host containing Nagios Core, the
Flask backend, the React frontend, and local SQLite databases. There is no cloud
component. The installer is developed in a separate repository.

## System boundaries

- Nagios owns monitoring execution, check state, and notification events.
- Pinpoint owns users, roles, settings, acknowledgements, discovery/deployment
  records, plugin administration, audit logs, and the web experience.
- Nagios' native web UI is intentionally not the operator interface.
- Network topology is excluded from the current release. Its source may remain
  for future work, but it must not be presented as a supported feature.

## Runtime architecture

```text
React/Vite browser client
        |
        | same-origin /api requests, cookie session
        v
Flask application
  |-- /api/user/*    authentication, accounts, roles, preferences
  |-- /api/system/*  monitoring views, history, reports, logs, settings,
  |                  discovery, and NCPA deployment
  |-- /api/plugin/*  server-side Nagios plugin management
  |
  |-- system.db      application-generated state
  |-- history.db     polled Nagios status snapshots
  |-- Nagios JSON CGI endpoints (status, object, archive)
  |-- Nagios config files and plugin executable directory
  |-- remote devices through nmap and SSH/NCPA workflows
  `-- APScheduler background polling, retention, and automation
```

## Technology stack

| Layer | Technology |
|---|---|
| Backend | Python 3.14, Flask 3, Flask-Login, Flask-SQLAlchemy, SQLAlchemy 2 |
| Migrations | Flask-Migrate/Alembic with multiple database binds |
| Scheduling | APScheduler |
| Remote access | Paramiko; nmap integration for discovery |
| Frontend | React 19, TypeScript 6, Vite 8, React Router 7 |
| UI/data display | Tailwind CSS, Lucide React, Recharts |
| Backend tests | pytest |
| Frontend tests | Vitest and Testing Library |
| Persistence | SQLite: `system.db` and `history.db` |

Use lockfiles and requirements files as the source of truth for exact versions.

## Repository layout

```text
/
|-- AGENTS.md                    specification router only
|-- spec files/                 authoritative system specifications
|-- demo/                       VirtualBox demo lab plan and script (no product code)
|-- client/                     React + TypeScript application
|   `-- src/
|       |-- pages/              top-level routed pages
|       |-- components/         page and shared UI components
|       |-- contexts/           current-user and settings state
|       |-- hooks/              reusable client workflows
|       |-- lib/                API and access-control utilities
|       |-- types/              TypeScript contracts and adapters
|       |-- data/               legacy/static reference data
|       `-- test/               Vitest tests
`-- server/                     Flask application
    |-- app/
    |   |-- api/user/           /api/user routes
    |   |-- api/system/         /api/system routes and statistics helpers
    |   |-- api/plugin/         /api/plugin routes and services
    |   |-- api/helper/         responses, validation, and data helpers
    |   |-- api/commands/       Flask CLI commands
    |   |-- nagios/             Nagios CGI ingestion/query code
    |   |-- network_discovery/  scan and host/service config generation
    |   |-- ncpa_deployment/    remote NCPA installation
    |   |-- logging/            audit-log writers
    |   |-- system_models.py    application models on the default bind
    |   |-- plugin_models.py    plugin application models on the default bind
    |   |-- history_models.py   Nagios snapshot models on the history bind
    |   |-- scheduler.py        periodic jobs
    |   `-- automation.py       settings-driven scheduled operations
    |-- pytest.ini              isolated collection defaults
    `-- tests/
        |-- unit/               isolated unit and mocked API/database tests
        |-- integration/        opt-in real Nagios CGI tests
        |-- e2e/                opt-in live lab tooling
        |-- support/            shared builders and migration helper
        `-- plans/              proposed approach, live plan, historical findings
```

## Architectural invariants

1. Current state and historical events are different products and use different
   Nagios sources. See `Data_Model_and_Integrations.md`.
2. Application-generated records never belong in `history_models.py`.
3. Both databases use the same `db.session`; the model bind selects the file.
4. Users are deactivated or suspended, not deleted. User foreign keys are
   expected to remain valid.
5. Service names may contain `/`; Flask service-name route parameters must use
   `<path:service_name>`.
6. Server-side plugins run on the Pinpoint/Nagios host. A plugin being installed
   is not the same as that plugin actively monitoring a target.
7. Sensitive network, SSH, credential, command, and filesystem operations must
   validate their input and must not expose secrets in logs or responses.
