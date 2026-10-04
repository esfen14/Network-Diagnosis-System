# Pinpoint Network Diagnosis System

Pinpoint (Detech-IT / 4D-G2) is a network monitoring and administration
dashboard built around Nagios Core. It provides a Flask API and React interface
for Network Discovery, host and service monitoring, Plugin Manager workflows,
NCPA deployment, alerts, reports, user management, and system settings.

Nagios remains the monitoring engine. Pinpoint manages application state,
configuration workflows, history, and the operator experience. The production
installer is maintained separately from this repository.

## Repository guide

| Path | Purpose |
|---|---|
| [`client/`](client/) | React, TypeScript, and Vite frontend |
| [`server/`](server/) | Flask backend, Nagios integrations, migrations, and tests |
| [`spec files/`](spec%20files/) | Authoritative system specifications and implementation status |
| [`server/tests/`](server/tests/) | Backend tests and opt-in live-lab tooling |

Start with the [specification index](spec%20files/README.md) before changing
system behavior. Contributor and agent routing rules are in [AGENTS.md](AGENTS.md).

## Development setup

Use Python 3.14 for the backend. Use a current Node.js/npm installation that
can install the versions pinned by `client/package-lock.json`; package files are
the source of truth for exact frontend versions.

### Backend

```bash
cd server
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-test.txt
flask run
```

Configure local values in the Git-ignored `server/.env`. Production secrets and
credentials must never be committed.

### Frontend

```bash
cd client
npm install
npm run dev
```

## Testing

Run the isolated backend suite without probing a live Nagios installation:

```bash
cd server
.venv/bin/python -m pytest tests/unit/
```

Run frontend tests and a production build:

```bash
cd client
npm run test
npm run build
```

See the [backend test guide](server/tests/README.md) for focused test commands,
fixtures, and the optional live-Nagios checks.

### Live Network Discovery lab

Live Network Discovery testing is opt-in and separate from the normal test
suite. It uses disposable nested VMs, scans only an approved isolated subnet,
controls real services, and may apply test-specific Nagios configuration. Read
and approve these documents before starting:

- [Proposed test approach adjustment](server/tests/plans/TEST_APPROACH_ADJUSTMENT_PLAN.md)
- [Extended test plan](server/tests/plans/NETWORK_DISCOVERY_EXTENDED_TEST_PLAN.md)
- [Live harness guide](server/tests/e2e/network_discovery/README.md)
- [Disposable VM-kit guide](server/tests/e2e/network_discovery/vm_scripts/README.md)

For the retained lab, the tester first previews and applies the consolidated
privileged host preparation:

```bash
cd /opt/pinpoint/Network-Diagnosis-System/server/tests/e2e/network_discovery
bash provision/prepare_test_host.sh
sudo bash provision/prepare_test_host.sh --apply
```

The preparation script does not install missing plugins, create VMs, run
discovery, reload Nagios, or change guest services. After it passes, the tester
hands control to the AI. The AI sources the protected test environment, runs
the harness preflight, reports the result, and waits for explicit approval
before conducting live tests.

Two retained-lab distinctions are important:

- `PINPOINT_TEST_SSH_KEY` uses the dedicated VM test identity, not the separate
  NCPA deployment identity. A public-key rejection with the deployment key does
  not mean the VMs need rebuilding.
- An empty `virsh snapshot-list` does not mean recovery baselines are missing.
  The VM kit uses external baseline QCOW2 images and disposable overlays.

The live harness guide contains the detailed ACL, SSH trust, VM verification,
recovery, evidence, and SCP retrieval procedures. Do not duplicate or improvise
those sensitive steps from this overview.

## Contributing

Use a feature branch, keep behavioral specifications current, run the smallest
relevant tests while developing, and broaden verification in proportion to the
change before merging. Never commit credentials, private keys, runtime lab
manifests, VM disks, database backups, or unsanitized test evidence.

## Production settings

In production every machine-specific value comes from the environment. The
PinPoint Installer writes them to `/etc/pinpoint/pinpoint.env`. This table is
the agreed interface between this repository and the installer: when you add
a setting the app reads from the environment, add it here too.

Supported Python version: **3.14** (developed on 3.14.2).

| Variable | Default | Required in production | Purpose |
|---|---|---|---|
| `SECRET_KEY` | none | yes | Signs session cookies. The app refuses to start without it unless `FLASK_DEBUG=1`, where it uses a temporary random key. |
| `NAGIOS_HOST` | `127.0.0.1` | yes | Host of the Nagios web server. The older `host:port` form (e.g. `127.0.0.1:8081`) is still accepted, and `NAGIOS_PORT` is then ignored. |
| `NAGIOS_PORT` | `80` | yes | Port of the Nagios web server. |
| `NAGIOS_USERNAME` | none | yes | HTTP Basic user for the Nagios JSON CGIs. |
| `NAGIOS_PASSWORD` | none | yes | Password for `NAGIOS_USERNAME`. |
| `PINPOINT_NETWORKS` | `192.168.130.0/24` | yes | Comma-separated subnets that network discovery scans, e.g. `192.168.50.0/24,10.0.0.0/24`. Never include localhost. |
| `PINPOINT_DOMAIN` | `test.local` | no | Suffix for discovered host names (`<ip>.<domain>`). |
| `PINPOINT_SCHEDULER` | `0` | yes (`1` for the Gunicorn service only) | `1` starts Nagios polling, data retention and automation jobs. Leave unset for `flask` commands and scripts. Run Gunicorn with one worker, since each process would start its own scheduler. |
| `SNMP_COMMUNITY_STRING` | `public` | no | SNMP community used when polling discovered hosts. |
| `FLASK_DEBUG` | `0` | yes (`0`) | Must be `0` in production. `server/.flaskenv` sets it to `1` for development. |
| `DATABASE_URL` | `sqlite:///server/system.db` | no | Location of `system.db`. |
| `DATABASE_BACKUP_DIR` | `server/database-backups` | no | Where automatic database backups are written. |
| `NAGIOS_HOST_CFG` | `/usr/local/nagios/etc/objects/hosts.cfg` | no | Hosts file that network discovery writes. |
| `NAGIOS_MAIN_CFG` | `/usr/local/nagios/etc/nagios.cfg` | no | Main Nagios config, used for `nagios -v` validation. |
| `NAGIOS_BIN` | `/usr/local/nagios/bin/nagios` | no | Nagios binary, used for validation. |
| `NAGIOS_PLUGIN_DIR` | `/usr/local/nagios/libexec/` | no | Directory scanned by the Plugin Manager. |
| `PLUGIN_SERVICE_CFG` | `/usr/local/nagios/etc/objects/plugin-services.cfg` | no | Nagios config holding Plugin Manager's command and service objects. |

For local development, put the values you need in `server/.env` (git-ignored),
for example:

```bash
SECRET_KEY=dev-only-secret
NAGIOS_HOST=192.168.130.10
NAGIOS_USERNAME=nagiosadmin
NAGIOS_PASSWORD=password
```

## Database setup

The schema is managed by the committed `server/migrations/` folder
(multi-database: `system.db` and `history.db`). Every model change must ship
with a migration in the same commit:

```bash
cd server
flask db migrate -m "describe the change"
flask db upgrade
```

- Fresh install: `flask db upgrade`, then create the first administrator:
  `printf '%s' "$PASSWORD" | flask init-production --admin-email admin@pinpoint.lan --password-stdin`.
  It seeds permissions, roles and settings, creates no test users, and refuses
  to run if any user already exists.
- Existing install: back up both databases, then `flask db upgrade`.
- Server built earlier with `db.create_all()`: run `flask db stamp head` once,
  then upgrade normally.
- Development: `server/reset_db.sh` rebuilds both databases and runs
  `flask seed` (test users with a shared password — never use on a real server).
