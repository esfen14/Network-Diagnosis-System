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

- Identity/access: `Permission`, `Role`, `RolePermission`, `PasswordResetRequest` (forgot-password requests; Pending until an admin resets or dismisses), `User` (`Must_Change_Password` forces a password change on a new account unless the create form unticks it, after reactivation or after an admin password reset; `Needs_Setup` is set only by `flask init-production` on the bootstrap administrator, whose installer email and password are placeholders, and is cleared by `POST /api/user/complete-setup`; migration `d3a9e6b2f741`). Each active user is a Nagios contact named and addressed by `User.Email`, so an email change regenerates the config.
- Email settings: `SmtpSettings` (`SMTP_SETTINGS`), the singleton (`Id` 1) behind Settings -> Email: `Provider`, `Host`, `Port`, `Tls`, `Username`, `Sender` and `Password_Encrypted` (Fernet via `app/secrets_store.py`; never returned by the API), with `Version`/`Updated_By`. Saving also applies the settings to `/etc/msmtprc` through the installer's root helper `/usr/local/sbin/pinpoint-apply-smtp` (`sudo -n`, JSON on stdin: `host`, `port`, `tls`, `username`, `password`, `sender`). No row means no mail transport is configured.
- Plugin settings: `PluginSettings` (`PLUGIN_SETTINGS`), one row per plugin definition (`Plugin_Name`, e.g. `snmp`) holding the variables saved from Settings -> Plugins in `Variables` (JSON), with `Version`/`Updated_By`. No row means the `config.py` defaults apply.
- Network profile: singleton `NetworkProfile` (`Id=1`) holding the editable name, reference and detail rows of the Network Health info card.
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
- `PluginConfiguration` also records which discovered service a check belongs
  to: `Port_Number`, `Protocol`, `Metric` (SNMP OID / NCPA metric),
  `Nagios_Service_Name` (e.g. `ssh-22-tcp`), `Applied_At` (first time active;
  not reset by a re-apply) and `Origin` (`Auto` for rows the plugin
  reconciler derives, `Manual` for rows created by hand, which the reconciler
  never touches, `Custom` for checks an administrator added for a plugin
  discovery cannot drive). `(PluginID, NetDiscoveryID, Nagios_Service_Name)` is unique;
  rows without a service name are not compared. The reconciler itself is
  planned, see `docs/plans/Plugin_Driven_Monitoring_Plan.md`; today every row is `Manual`.
- Command overrides preserve an immutable snapshot of the original command.
- Plugin Manager targets existing `NetworkDiscovery` devices; free-form targets
  are out of scope.
- **Monitoring state of a device.** `NetworkDiscovery.Device_State` (lifecycle) and
  `Include_Device_In_Scanning` (an administrator's pause) together give one label
  from `monitoring_state()` in `network_discovery/device_identity.py`: merged, retired,
  paused, address_unknown, missing, monitored (first match wins). Only
  `POST /hosts/<id>/pause` and `/resume` write the flag; scans and the lifecycle
  (`apply_match()`, `update_lifecycle()`) never change it. The config builder
  leaves a paused device out of `hosts.cfg`. Its `history.db` rows stop at the
  pause and are kept, but `unchecked_host_names()` (paused, retired, merged) lets
  `get_latest_hosts()` / `get_latest_services()` leave them out of the dashboard and
  Network Health counts and alerts.
- **Plugin Manager gates monitoring.** `plan_host_services()` (the planner
  behind both `hosts.cfg` and the reconciler) skips a port whose plugin
  (`plugin_for_definition()`) is not `Enabled` or `Active`, recording the reason
  ("check_ssh is not enabled in Plugin Manager.") in the skipped services, and
  the generic TCP fallback needs `check_tcp` enabled too. Ports keep their state
  and frozen plugin when a plugin is off, so enabling restores them.
- **Custom checks** (`network_discovery/custom_checks.py`, `api/plugin/custom_checks.py`;
  `docs/plans/Custom_Checks_Plan.md`): a `PluginConfiguration` row with `Origin = Custom`, no port
  (`Port_Number` and `Protocol` stay NULL), `Service_Description` the admin's name,
  `Nagios_Service_Name` `custom-<plugin>-<name>` and `Configuration_Data`
  `{"variables": {...}, "paused": bool}`. `create_host_cfg.load_custom_checks()` reads the
  unpaused rows and writes each as a service on its device in `hosts.cfg`, with one
  `pinpoint_custom_<plugin>` command per plugin used (rendered like a registry command:
  required arguments as `$ARGn$`, optional ones in the final `$ARG$`, every value single-quoted
  and checked against the registry's forbidden characters). Which plugins take one, and
  the arguments of each, are the `CUSTOM_CHECK_FIELDS` table; `PLUGIN_CLASSES` gives every
  other catalog plugin its reason for not taking one. A password field is stored encrypted in
  `Configuration_Data["secrets"]` (`app/secrets_store.py`, Fernet, key from `PINPOINT_SECRETS_KEY` or
  `SECRET_KEY`), never returned by the API, and decrypted only when `hosts.cfg` is generated, where it
  is written in plain text because Nagios needs it in the command (docs/plans/Custom_Checks_Plan.md §8b). Merging a device moves its custom
  checks to the target, dropping one whose name the target already has.
- **Server checks** are custom checks with no device (`NetDiscoveryID` empty) for the plugins in
  `SERVER_CHECK_FIELDS` (`check_apt`, `check_uptime`, `check_sensors`, `check_ide_smart`,
  `check_file_age`, `check_mailq`, `check_nagios`, `check_flexlm`). `load_server_checks()` writes
  them under "Define Server Checks" as services of the host `localhost`, named `server-<plugin>-<name>`,
  with commands that take no `-H`. `localhost.cfg` and the stock `localhost` services are never
  touched; merges and the reconciler ignore them.
- **The reconciler** (`app/api/plugin/reconcile.py`,
  `reconcile_plugin_monitoring`) keeps the `Origin = Auto` rows of
  `PluginConfiguration` equal to the services the planner generates (one per
  metric for SNMP/NCPA), promotes identified ports, calls
  `regenerate_and_apply_config_status()` once, and sets each Enabled/Active
  plugin Active when an applied row backs it. `Manual` rows are never touched
  and are not written to `hosts.cfg`. The manual path that created them
  (`monitoring_config.py`, `plugin-services.cfg`, the `/configurations` routes and
  the `plugin.configure` permission) is removed; upgraded installs keep any
  services it wrote in `plugin-services.cfg`, still loaded by Nagios, until an
  admin deletes that file's entries (see the plan, G18). If
  Nagios rejects the config the database is rolled back and the failure is
  recorded in the plugin history. Merging devices deletes the source's Auto rows
  (the reconciler rebuilds them) because the unique constraint would collide.
- Discovery scans the plugin directory first when Plugin Manager has no
  plugins (`ensure_plugin_inventory`). A fresh install enables nothing. An
  install that was already monitoring ports (it upgraded without ever scanning
  its plugins) has the plugins behind those ports enabled at that moment
  (`enable_plugins_backing_monitored_ports`), because the upgrade migration
  could not enable plugins that did not exist yet.
- Downgrading migration `a8c4e1f6b2d3` deletes the `Origin = Auto` rows: without
  the column they would look hand-made, and older code writes applied rows to
  `plugin-services.cfg` as well as `hosts.cfg`.
- `Plugin.Description` and `Plugin.Category` are filled by each plugin scan
  when empty, and never overwritten. Bundled nagios-plugins come from the
  committed catalog `plugin_catalog_data.py`, generated by
  `server/scripts/build_plugin_descriptions.py` from `Plugins_List.md` and the
  official manual pages (re-run it when either changes; a test fails if the
  committed file is stale). A plugin outside the catalog uses the first
  descriptive paragraph of its own `--help` output. The documentation link is
  derived from the catalog at read time and is not stored. The server never
  fetches documentation from the internet.

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

A host Nagios lists as pending (no check has run yet) has no state to record, so the
poller skips it without an error and records it once its first check completes; a
pending service is stored as Unknown. A host status that is not up, down, unreachable
or pending is logged as an error and that host is skipped for that poll; the rest of
the poll continues.

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
scans, and plugin security validation. Scheduled network discovery runs only if
at least one scan has already been recorded; a fresh installation waits for an
administrator to trigger the first scan manually. Maintenance mode permits backups but
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

Network targets, ports, service rules, NCPA metrics, SNMP defaults, and
Nagios filesystem paths live in `server/config.py` and may be environment
overridden where defined. Networks, ports and service rules can also be saved
from the Settings page (`DiscoverySettings`), which then takes precedence. The SNMP
OID table (`SNMP_OIDS`) and the NCPA metric table (`NCPA_METRICS`) can be saved from
Settings -> Plugins (`PluginSettings`, one row per plugin: `snmp`, `ncpa`);
`plugin_config()` in `network_discovery/plugin_settings.py` puts the saved values in
place of their `config.py` keys once per config build, for both `hosts.cfg` and the
plugin reconciler. Per-host `Plugin_Variables` overrides still win.

### Service identification

A port number is a hint, not proof of the service. The default TCP scan range
is `1-10000` (alternate ports such as 8080, 8443 and 9443 included). TCP scans
use `-sV -O --version-all`. UDP scans run in two steps: `-sU --open` finds the
ports that answer, then `-sU -sV` (with a per-host timeout) probes only those
ports; if the second step fails the port-number names are kept. `service_from_nmap()`
keeps nmap's evidence: `method="probed"` with a real name is a `FINGERPRINT`;
`method="table"` (a lookup by port number) is a `PORT_HINT`; `unknown` and
`tcpwrapped` (the port accepted and closed) are stored as `unknown` with a
`PORT_HINT`; HTTP inside `tunnel="ssl"` is reported as `https`. Discovery then
decides each port's service name, strongest first:

1. `USER`: a service an operator pinned on that device's port through
   `PUT /system/hosts/<id>/ports/<proto>/<port>`. Scans never rename it.
2. `FINGERPRINT`: nmap's probed name, e.g. `ssh` on 2222.
3. `PORT_RULE`: the Port -> Service table (`TCP_Port_Services` /
   `UDP_Port_Services`, defaults `TCP_PORT_SERVICES` / `UDP_PORT_SERVICES` in
   `config.py`), the service an admin *expects* on a port. It names a port nmap
   could not fingerprint, and agrees with a fingerprint of the same service.
   The TCP table always holds `NCPA_PORT -> ncpa`, added when the table is
   read and never stored, so it cannot drift from `NCPA_PORT`; that port always
   takes `ncpa` because deployment configures the agent there and nmap
   fingerprints it as https.
4. `PORT_HINT`: nmap's guess from the port number; never trusted on its own.

**Not used as intended.** When nmap fingerprints a service that contradicts the
table's entry (for example a web server on port 22), the port is not relabelled.
It keeps the service nmap saw, records the table's entry in
`Expected_Service_Name`, and is not monitored until an admin acknowledges it
(`Mismatch_Acknowledged_At`, set through the port-edit route). Acknowledging
accepts the port as the service nmap found. A change in what nmap sees clears
the acknowledgement; pinning the service, or choosing to monitor the port,
settles the flag. A port that is already monitored keeps running while flagged.

The result is stored in `Identified_By` on `Open_TCP_Services` /
`Open_UDP_Services` (NULL for ports recorded before it existed). Plugin Manager
is the switch for monitoring: a `SUGGESTED` port whose service is identified
(pinned, from the table, or fingerprinted) and not flagged starts being
monitored when the plugin that checks it is `Enabled` or `Active`
(`should_auto_monitor`, `promote_identified_ports`). Plugin names come from
`plugin_registry.plugin_for_definition()`. A service with no plugin of its own
is checked by the generic TCP plugin (`check_tcp`), so enabling it picks up every
identified TCP port; UDP is monitored only through a plugin that speaks its
protocol. `AUTO_MONITOR_SERVICES` no longer exists. The plugin reconciler runs
`promote_identified_ports` on plugin enable and disable, after every scan save and
after port edits. A port can be held back from promotion (`Promotion_Held`): it is set
when an admin sets a port to Suggested, and by the upgrade for the Suggested ports the
enabled plugins would otherwise start monitoring. No plugin promotes a held port;
monitoring it by hand or acknowledging a mismatch releases it. A monitored, unpinned port that
fingerprints as a service its frozen plugin does not match keeps its service and
raises a `SERVICE_CHANGED` `DeviceReviewItem`; hints never raise one, and the
NCPA port of a deployed agent is exempt.

Port lifecycle thresholds live in `config.py`: a monitored port unseen for
`PORT_MISSING_AFTER_SCANS` (5) scans becomes `MISSING` and stays monitored; after
`PORT_ARCHIVE_AFTER_DAYS` (30) days as `MISSING` it is archived and its service leaves
Nagios. `PINPOINT_PORT_ARCHIVE_AFTER_DAYS` overrides the 30 days so a test lab can
reach the archived state in minutes (fractions allowed, for example `0.001`); it
must be a number above zero or the application refuses to start, and it is left
unset in production.

The scan leaves the monitoring server out by every non-loopback IPv4 address of
its network interfaces (read with `ip -4 -o addr`) as well as the addresses its
hostname resolves to, so a second network card cannot get the server saved as a
device.

Discovery starts are serialized by an in-process lock around the running-thread
check and worker launch, so simultaneous requests cannot both start a scan. For
a scan observation at an existing address, reconciliation considers ACTIVE,
MISSING, and ADDRESS_UNKNOWN records, preferring an ACTIVE holder when multiple
records share the IP. An ADDRESS_UNKNOWN record is reactivated if the observed
identifiers do not contradict its stored identity; a truly different MAC or
host key remains an IP-reuse review case and is never silently merged. The SSH
identity probe uses the configured SSH port and every port nmap names `ssh`,
including alternate ports such as 2222. A cloned SSH key can be shared by
multiple targets: if a scan observes that key on a known, different device at
its recorded address with its own matching hardware MAC, reconciliation keeps
that device and its newly scanned ports rather than dropping the observation
as a secondary address of the key owner. It records a duplicate-identity
review item. A true second NIC of one device still belongs to its key owner.

## NCPA deployment

The SSH command helpers accept `expected_exit_codes` for probes: the account
existence check (`id`, exit 1) and authorized-key check (`grep`, exits 1 and 2)
log those results at INFO, without command output. Nonzero exits still return
`success: False`, so missing accounts and keys are created as before. Other
nonzero exits, including failing non-probe commands, continue to log at ERROR.

`app/ncpa_deployment/ncpa_deployment.py` installs NCPA over SSH. The workflow
requires explicit SSH host-key fingerprint retrieval/confirmation, uses the
stored fingerprint for subsequent verification, records progress and per-device
results, makes the TLS key readable by the `nagios` user on every deploy, verifies
the listener with an authenticated request, and reads the agent's own logical disk
nodes (`GET /api/disk/logical`, real filesystems whose `used_percent` node
answers) into `NCPADevicePartition.Name` (an NCPA node name such as `|` or
`|data`, not an lsblk partition). Pseudo filesystems (`bpf`, `tmpfs`, ...) and
the `|sys`, `|proc`, `|run`, `|dev` and `|boot|efi` trees are never recorded.
The disk metric path is `disk/logical/{partition}/used_percent`; the path is
stored raw and quoted once by the Nagios command template. If a metric cannot
be planned, the port falls back to the generic TCP check and the fallback is
listed in the run's skipped services.

The deploy helper restarts the agent through systemd, so `ncpa.service` stays
active. Pinpoint's certificate probe ends the TLS session cleanly (NCPA 3.5.0
stops listening if a client drops it), and a deployment fails with "NCPA
stopped listening after the identity check." if the port stops accepting
connections afterwards. A failed install after the bootstrap step reports that
the deployment account, its key, sudo rule and helper remain on the device;
nothing removes them automatically.

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

SSH is not assumed to be on port 22. `port_lifecycle.device_ssh_port()` picks
the device's SSH port from its recorded TCP ports (a port whose frozen plugin or
service name is `ssh`; hand-added first, then monitored, then `SSH_PORT`, then
lowest; MISSING/ARCHIVED ports are skipped) and falls back to `SSH_PORT`.
Trust confirmation reads the key from that port and stores the port in
`SSHCredentials.SSH_Port` with the approved fingerprint, because a fingerprint
only vouches for the port it was read from; every later connection (the
pre-flight key check at start, the credential check, bootstrap and install)
uses the pinned port, and paramiko host keys
for non-22 ports are registered as `[address]:port`. If SSH moves, the device
must be trust-confirmed again. The remote helper configures the agent's
`[listener]` port to `Config.NCPA_PORT`, and Pinpoint reaches the agent on that
port; deployment has no per-device NCPA port. The helper replaces any
active or commented `port` line in `[listener]` with exactly one, and fails with
"Could not set the NCPA listener port." otherwise. `NCPA_PORT` is a
deployment-time setting (not editable in the UI): changing it after agents are
deployed requires redeploying them. An invalid value is reported as "NCPA_PORT
must be an integer between 1 and 65535." (HTTP 500 from the start route). Discovery's identity probes read
the SSH host key on `SSH_PORT` and on every port nmap identified as `ssh`.

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
