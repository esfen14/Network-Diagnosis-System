# Data Model and Integrations

**Last verified against the repository:** 2026-09-27

## Database ownership

Pinpoint uses two SQLite databases through one Flask-SQLAlchemy `db.session`.

| Database | Bind | Model files | Ownership |
|---|---|---|---|
| `server/system.db` | Default/no bind key | `system_models.py`, `plugin_models.py` | Application-generated users, configuration, workflow, audit, acknowledgement, discovery, deployment, and plugin data |
| `server/history.db` | `history` | `history_models.py` | Nagios-sourced status and performance snapshots only |

Never place application-generated data in `history_models.py`. A record's topic
does not decide its database; its producer does. For example, application alert
acknowledgements belong in `system.db` even though they relate to Nagios alerts.

## Model inventory

### Default bind: identity, configuration, operations, and acknowledgement

- Identity/access: `Permission`, `Role`, `RolePermission`, `User`.
- Audit/logging: `ActivityLog`, `ConfigurationChanges`, `ExportLog`.
- Discovery: `NetworkDiscoveryStatus`, `SkippedService`, `NetworkDiscovery`,
  `Open_TCP_Services`, `Open_UDP_Services`.
- NCPA deployment: `SSHCredentials`, `NCPADeploymentStatus` (one row per run,
  with `Reviewed_At`/`Reviewed_By`), `NCPADeploymentResult` (one row per device
  per run), `NCPADeployment` (each device's latest agent state),
  `NCPADevicePartition`.
- Settings: singleton `SystemSettings`, one-per-user `UserPreferences`.
- Notifications/alerts: `NotificationCursor`, `AlertAcknowledgement`,
  append-only `AckHistory`.

Users are never deleted; account lifecycle uses `UserStatus`. Do not add delete
cascades to user foreign keys. `AckHistory.ActorUserID` is nullable only because
`AUTO_RESOLVED` is a system action. The existing `NotificationCursor` cascade is
a legacy inconsistency and must not be copied as a pattern.

### Settings ownership

| Scope | Fields |
|---|---|
| System general | `scanFrequency`, notification enablement, allowed export formats |
| System security | session timeout, strong-password policy, failed-login monitoring, audit logging, security-check frequency |
| System operations | update frequency, maintenance mode, automatic backups, log retention, diagnostic-history retention |
| Per-user display | theme, time zone, date/time format, font, font size, dashboard layout, dashboard refresh rate |

`SystemSettings` is row `Id=1` and carries a version/update audit stamp.
`UserPreferences` has one row per user. Do not move personal display values into
the shared singleton or system controls into user preferences.

### Default bind: Plugin Manager

`plugin_models.py` contains `Plugin`, `PluginVersion`, `PluginCommand`,
`PluginCommandOverride`, `PluginDependency`, `PluginConfiguration`,
`PluginHistory`, and `PluginScanStatus` plus their enums.

Plugin lifecycle and active monitoring are separate:

- `Plugin.Status` describes the executable/plugin lifecycle.
- `PluginConfiguration` describes whether a plugin has been wired to a scanned
  target and successfully applied to Nagios.
- Command overrides preserve an immutable snapshot of the original command.
- Plugin Manager targets existing `NetworkDiscovery` devices; free-form targets
  are out of scope.

### History bind: Nagios snapshots

`history_models.py` contains `HostStatus`, `HostPerfData`, `ServiceStatus`,
`ServicePerfData`, and `ProgramStatus` plus state enums. Every model has
`__bind_key__ = "history"`.

`Acknowledgement_Type` on host/service snapshots is Nagios' acknowledgement
state. It is not Pinpoint's `AlertAcknowledgement` record.

## Current state versus durable event history

These sources are intentionally not interchangeable:

| Question | Correct source | Access path |
|---|---|---|
| What is happening now? | Latest rows in `history.db` | `statistics.py`, dashboard, host, service, and network-health routes |
| What changed between two times? | Nagios `archivejson.cgi` event log | `nagios/notifications.py`, history/report routes |
| Who acknowledged something in Pinpoint? | `AlertAcknowledgement` and `AckHistory` in `system.db` | Acknowledgement and history routes |
| Was a notification sent? | Nagios archive notification events | Notification/history/report routes |

Periodic snapshots may miss a state that changes and recovers between polls.
Archive events should therefore never be replaced with snapshot inference.
Conversely, the active-alert count and feed must use the same latest-snapshot
source so they cannot drift from one another.

## Nagios integration

`app/nagios/status.py` reads `statusjson.cgi` and `objectjson.cgi`, normalizes
host/service/program data, strips arguments from stored service check commands
to avoid persisting secrets, and writes snapshots to `history.db`.

`app/nagios/notifications.py` reads `archivejson.cgi` for durable alert and
notification event ranges.

`Config.NAGIOS_HOST` is the CGI network host. In contrast,
`api/system/statistics.py` uses `NAGIOS_HOST = "localhost"` to identify the
Nagios server within status data. Changing either requires understanding its
different purpose.

## Aggregation rules

- Latest state is selected per host and per `(host, service)` pair.
- An active alert is a host not UP or a service not OK.
- Network-wide averages require at least two reporting hosts; otherwise return
  `null` and display “Insufficient data.”
- Trend windows are exactly 1, 6, 24, and 168 hours.
- Plugin grouping first uses stored check-command mapping, with service-name
  derivation as documented in `Display_Requirements.md`.
- Service descriptions may contain slashes.

## Scheduler and retention

`scheduler.py` runs:

- Nagios status polling every 60 seconds.
- Daily purging based on `Log_Retention_Days` and
  `Diagnostic_History_Retention_Days`.
- Settings-driven automation checks every `AUTOMATION_CHECK_MINUTES`.

`automation.py` can schedule database backups, network discovery, plugin update
scans, and plugin security validation. Maintenance mode permits backups but
stops the other automated operations. Jobs are attributed to an active user for
audit purposes.

## Network discovery and Nagios configuration

`app/network_discovery/network_discovery.py` performs host/TCP/UDP discovery.
`create_host_cfg.py` stores results, plans plugin-backed services, writes a
candidate Nagios host configuration, validates it with the Nagios binary,
backs up the running configuration, and applies only a valid candidate.

`plugin_registry.py` is the registry and renderer used to resolve discovered
services to supported plugins and variables. Unmonitorable discovered services
are recorded as `SkippedService` entries rather than silently discarded.

Network targets, ports, service overrides, NCPA metrics, SNMP defaults, and
Nagios filesystem paths live in `server/config.py` and may be environment
overridden where defined.

## NCPA deployment

`app/ncpa_deployment/ncpa_deployment.py` installs NCPA over SSH. The workflow
requires explicit SSH host-key fingerprint retrieval/confirmation, uses the
stored fingerprint for subsequent verification, records progress and per-device
results, makes the TLS key readable by the `nagios` user on every deploy, verifies
the listener with an authenticated request, and reads the agent's own logical disk
nodes (`GET /api/disk/logical`, filesystems whose `percent` node answers) into
`NCPADevicePartition.Name` (an NCPA node name such as `|` or `|boot|efi`, not an
lsblk partition).

Each run records one `NCPADeploymentResult` per device. Its `Outcome`
(`DeploymentOutcome`) moves Pending → Running → Success, Failed, Down
(`UNREACHABLE`: no answer on SSH), or Incompatible; pre-flight rejections are
Rejected and devices not started after a stop are Skipped. A rejected login is
Failed ("SSH authentication failed."), never Down. Hostname and IP are copied
into the row so history survives renames and moves. The run is Success when no
device failed, Failed when none succeeded, otherwise Partial Failure; a stop or
a Nagios config that could not be applied by `add_ncpa_port` keeps that status.

Trust confirmation saves a host key only when the live key equals the
fingerprint the user approved. A device can be deployed to when its agent is
Pending NCPA or Deployment Failed (retry); Deployed and Incompatible devices
are rejected.

Credentials, tokens, passwords, and secret-bearing command arguments must never
appear in logs, API responses, or persisted Nagios snapshot check commands.

## Alert acknowledgement lifecycle

- One active Pinpoint acknowledgement is allowed per `(hostname, service)`;
  `service = null` identifies a host alert.
- A comment is required when acknowledging.
- Acknowledgement and manual unacknowledgement append `AckHistory` records.
- When an alert resolves to UP/OK, the active acknowledgement must be removed
  and an `AUTO_RESOLVED` history row written. The model contract exists, but the
  polling cleanup is not currently wired; see `Implementation_Status.md`.

## Migrations

Model changes affect a multi-bind migration environment. From `server/`, with
the virtual environment active:

```bash
flask db migrate --multidb -m "short description"
flask db upgrade --multidb
flask sync-permissions   # after any upgrade: adds new seed permissions, grants them to Administrator
```

`flask sync-permissions` is idempotent and never changes users, other roles or
existing grants. The serving process logs an error at startup if the installed
database lacks any permission in the seed list.

If migrations have never been initialized:

```bash
flask db init --multidb
```

Migrate both databases together. Do not hand-edit generated migrations unless
the generated operations have been reviewed and a manual correction is truly
required.
