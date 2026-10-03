# This is the respository for Detech-IT
This is where development of 4D-G2's capstone will happen.

## Note for the developers:
Please make a branch for adding features, then merge to the main branch so as to not break things.

# Getting started:

## For the front-end
Please have npm version 11.16.0
This is usually bundled with Node.js


## For the backend
Please have Python 3.14.2


# Things that need to be address later:
1. How to connect this system to Nagios, current options:
- docker in an OS with Nagios
- running with Nagios as a service in an OS
2. How do we get data from Nagios?
3. Things needed to develop the installer

# Production settings

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
- Existing install: back up both databases, then `flask db upgrade`, then
  `flask sync-permissions` (adds any permission introduced since the install and
  grants it to Administrator; idempotent, never touches users or other roles).
- Server built earlier with `db.create_all()`: run `flask db stamp head` once,
  then upgrade normally.
- Development: `server/reset_db.sh` rebuilds both databases and runs
  `flask seed` (test users with a shared password — never use on a real server).
