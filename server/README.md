# Pinpoint Backend

## Start for development

From the repository root:

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-test.txt
flask run
```

The development API runs on
[http://127.0.0.1:5000](http://127.0.0.1:5000). `.flaskenv` points Flask at
`server.py` and enables debug mode.

For an existing environment, the shorter startup is:

```bash
cd server
source .venv/bin/activate
flask run
```

Useful commands:

```bash
pytest                                      # run the backend suite
pytest tests/test_dashboard.py -v           # run one test module
flask seed                                  # add missing seed data
flask sync-permissions                      # upgrade: add new permissions, grant to Administrator
```

Do not use `flask seed --reset` on data you need to keep; it drops and rebuilds
the databases.

After changing models, use the multi-bind migration workflow. If this checkout
does not yet have a `migrations/` directory, initialize it first:

```bash
flask db init --multidb
flask db migrate --multidb -m "description"
flask db upgrade --multidb
```

## What this side does

The backend is the Flask API and integration layer for Pinpoint. It authenticates
users, enforces permissions, reads and aggregates Nagios monitoring data,
manages alerts and notifications, runs network discovery and NCPA deployment,
generates reports and logs, and manages server-side Nagios plugins.

The API is mounted under three prefixes:

- `/api/user/*` — authentication, accounts, roles, and preferences
- `/api/system/*` — dashboard, health, history, reports, logs, settings,
  discovery, and NCPA deployment
- `/api/plugin/*` — Plugin Manager inventory and administration

## Important parts

- `app/__init__.py` creates the Flask app, database, login manager, blueprints,
  CLI command, and scheduler.
- `app/api/` contains route blueprints and shared API helpers.
- `app/system_models.py` owns application data in `system.db`.
- `app/plugin_models.py` owns Plugin Manager data in `system.db`.
- `app/history_models.py` contains only Nagios-sourced snapshots in
  `history.db`.
- `app/nagios/` reads Nagios status, object, and archive JSON CGI endpoints.
- `app/network_discovery/` scans networks and generates validated Nagios host
  and service configuration.
- `app/ncpa_deployment/` performs fingerprint-verified remote NCPA deployment.
- `app/scheduler.py` polls Nagios, purges retained data, and triggers
  settings-driven automation.
- `config.py` contains database, Nagios, scan, plugin, and filesystem settings.

## Folder structure

```text
server/
|-- app/
|   |-- api/
|   |   |-- user/              authentication, roles, accounts, preferences
|   |   |-- system/            monitoring, history, reports, logs, settings
|   |   |-- plugin/            Plugin Manager routes and services
|   |   |-- helper/            responses, validation, conversion, DB lookups
|   |   `-- commands/          Flask CLI commands such as seed
|   |-- nagios/                Nagios CGI readers and snapshot ingestion
|   |-- network_discovery/     scanning and Nagios config generation
|   |-- ncpa_deployment/       SSH/NCPA installation workflow
|   |-- logging/               audit and subsystem log writers
|   |-- system_models.py       default-bind application models
|   |-- plugin_models.py       default-bind plugin models
|   |-- history_models.py      history-bind Nagios snapshot models
|   |-- scheduler.py           recurring jobs
|   `-- automation.py          settings-driven scheduled tasks
|-- tests/                     pytest suite and test documentation
|-- config.py                  runtime configuration
|-- conftest.py                shared pytest environment and fixtures
|-- server.py                  Flask entry point and shell context
|-- requirements.txt          runtime dependencies
|-- requirements-test.txt     test dependencies
|-- system.db                 application-generated state
`-- history.db                Nagios monitoring snapshots
```

## Data and integration notes

The two SQLite databases share one SQLAlchemy session but have different
ownership:

- `system.db` stores users, roles, settings, acknowledgements, logs,
  discovery/deployment state, and Plugin Manager records.
- `history.db` stores polled host, service, performance, and Nagios program
  snapshots.

Current monitoring state comes from the latest `history.db` snapshots.
Historical state-change and notification events come from Nagios'
`archivejson.cgi`; these sources are intentionally not interchangeable.

Network discovery, SSH deployment, plugin installation, and Nagios
configuration touch external systems. Development and tests should use mocks or
temporary paths unless a live integration run is intentional.

## Testing

Tests use in-memory databases and suppress the background scheduler. See the
[backend test-suite guide](tests/README.md) for fixtures, module coverage, live
Nagios tests, and focused test commands.

## Further documentation

- [Backend Modules and Routes](../spec%20files/Backend_Modules_and_Routes.md)
- [Data Model and Integrations](../spec%20files/Data_Model_and_Integrations.md)
- [Engineering Standards](../spec%20files/Engineering_Standards.md)
