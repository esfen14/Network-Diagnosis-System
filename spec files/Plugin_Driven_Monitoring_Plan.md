# Plugin-Driven Monitoring Implementation Plan

Status: **in progress.** Decisions Q1–Q7 are answered (§10). Phase 0 is done
(results in §7.1). Phase 1 (descriptions) is implemented on the feature branch
and not yet committed. Phases 2–6 are not started. The port → service → plugin map (§2.7) is fully decided
(Q8 in §10). No questions are open.
Branch: `feature/plugin-driven-monitoring` (cut from `main`; see §9).
Owning specs to update with this work: `Data_Model_and_Integrations.md`,
`Backend_Modules_and_Routes.md`, `Frontend_Modules_and_Routes.md`,
`Implementation_Status.md`.

## 1. Problem statement

Requested behavior:

1. Network scans always record the services a device uses and the ports they
   use. That record is a *catalog* and does not depend on plugins.
2. A service is **monitored only when a plugin that can check it is enabled in
   Plugin Manager**. Plugin Manager is the on/off switch for monitoring, and
   nothing port-based is monitored until an admin enables a plugin (opt-in).
3. Plugin Manager must **not ask an admin to pick devices by hand**. When a
   plugin is enabled, the devices whose discovered services/ports it can check
   are attached automatically, and new devices found later are attached too.
   An admin can exclude a single device from an enabled plugin.
4. The **"Currently Running" tab is removed.** Plugin Manager is one plugin
   inventory. The services a plugin is monitoring are listed in that plugin's
   details as `service · device · IP · status/metric · running since`.
5. The plugin details view must show a real **description** of the plugin.
6. The monitoring server's own statistics (load, disk, swap, processes, users)
   stay with **Nagios Core's built-in `localhost.cfg`**. Pinpoint does not
   generate, adopt, display or edit those services, and users get no access to
   that file through Pinpoint. It only applies to Nagios Core itself.

What the code does today (verified by reading, not by running):

| # | Current behavior | Where |
|---|---|---|
| a | Discovery builds Nagios services itself from its own `PluginDefinition` registry and falls back to the generic `tcp` plugin for any unmatched TCP port. It never reads `Plugin.Status`. Disabling or never enabling a plugin changes nothing. | `network_discovery/create_host_cfg.py` `build_host_services()`, `plugin_registry.py`; already recorded as a gap in `Implementation_Status.md` ("Plugin lifecycle and discovery") |
| b | Plugin Manager "Apply to Device" is a manual device picker. It writes a *second* file (`plugin-services.cfg`) with its own `pinpoint_<plugin>` commands. | `api/plugin/service.py` `apply_plugin_configuration()`, `monitoring_config.py`, `PluginTargetsSection.tsx` |
| c | Plugin Manager commands are bare (`check_ping -H $HOSTADDRESS$`, no `$USER1$/`), keep `$ARG1$` placeholders that are never filled (the service passes no `!args`), and `configuration_data` is stored but never rendered. Discovery's registry does this correctly. | `plugin_command_defaults.py`, `monitoring_config.py`; contrast `plugin_registry.py:189` |
| d | Disable only flips `Plugin.Status`; applied checks keep running. There is no route to remove a configuration. | `service.py` `disable_plugin()` |
| e | The Running tab shows Plugin, Device, IP, Service (free text typed by the admin), Applied time. No live state. "Running since" is `PluginConfiguration.Updated_At`, which changes on every re-apply. | `RunningChecksTable.tsx`, `service.py` `get_running_checks()` |
| f | `Plugin.Description`, `Author`, `Category` exist but the scanner never fills them, so the drawer says "No description available." | `scanner.py`, `PluginDetailsDrawer.tsx` |
| g | The server's own statistics come from **stock Nagios `localhost` services** (`Current Load`, `Root Partition`, `Swap Usage`, `Total Processes`, `Current Users`; commands `check_local_*`) defined by Nagios Core's `localhost.cfg`, outside this repository. The Dashboard reads their results from the status snapshots by host `localhost`. This is **unchanged by this plan**. | `api/system/statistics.py`, `test_statistics.py` |

Root cause of (a)–(d): two parallel systems (Network Discovery registry and
Plugin Manager) both generate Nagios services, with different command layouts
and no shared lifecycle.

## 2. Target design

### 2.1 Single owner per concern

| Concern | Owner |
|---|---|
| What exists on the network (devices, ports, services) | Network Discovery (`Open_TCP_Services`, `Open_UDP_Services`) |
| *How* to check a service (command layout, variables, metrics) | `PluginDefinition` registry (`plugin_registry.py`) |
| *Whether* a plugin may be used | Plugin Manager (`Plugin.Status` is `Enabled` or `Active`) |
| Writing Nagios config for discovered devices | One generator: discovery's `regenerate_and_apply_config()` and its validate/backup/reload/rollback pipeline |
| The Nagios server's own checks | Nagios Core (`localhost.cfg`); out of Pinpoint's scope (§2.6) |

`PluginConfiguration` becomes a **derived record** of "plugin X is monitoring
device D port P", maintained by a reconciler (§2.3). Admins no longer create
it by hand.

### 2.2 Registry → Plugin Manager mapping

The registry names a definition (`ssh`); Plugin Manager names an executable
(`check_ssh`). Add one explicit mapping in code, not inferred by string:

| Registry definition | Plugin Manager plugin (executable) |
|---|---|
| `tcp` | `check_tcp` (also the generic fallback) |
| `udp` | `check_udp` (discovery does not generate it today; stays skipped) |
| `snmp` | `check_snmp` |
| `ncpa` | `check_ncpa` |
| `http`, `https` | `check_http` (one plugin enables both) |
| `ssh` / `ftp` / `smtp` / `mysql` | `check_ssh` / `check_ftp` / `check_smtp` / `check_mysql` |
| `dns` | `check_dns` |
| `ntp` | `check_ntp_time` |

A definition with no enabled Plugin Manager plugin is **not monitored**.

### 2.3 Reconciler

New function `reconcile_plugin_monitoring()` (new module
`api/plugin/reconcile.py`). Idempotent. It computes the desired set and makes
the database match:

```
for each device (Include_Device_In_Scanning, not Retired/Merged,
                 not the monitoring server itself)
for each open port with Port_State in (Monitored, Missing)   # CONFIG_STATES
resolve definition (frozen Plugin_Name, else resolve_plugin_name)
map to Plugin Manager plugin
keep if that plugin is Enabled/Active
expand to one entry per metric (SNMP OIDs, NCPA metrics)
```

- **Promotion comes first.** Before computing the set, identified `Suggested`
  ports whose plugin is Enabled/Active become `Monitored` (rules in §2.7), so
  enabling a plugin attaches its ports and new devices found later are covered
  by the same step.
- Creates a `PluginConfiguration` per desired entry, removes/closes ones no
  longer desired, and never touches rows it did not derive.
- Never creates anything for the monitoring server (host `localhost` and the
  addresses from `get_monitoring_server_ips()`), so it cannot duplicate or
  interfere with the stock `localhost.cfg` services.
- A port whose plugin is not enabled keeps its `Port_State` and its frozen
  `Plugin_Name` (it is not demoted); it is simply left out of the generated
  config and recorded with a reason ("check_ssh is not enabled"), reusing
  `SkippedService` so the Discovery log shows it. Gating happens at generation,
  not by rewriting port states (§7.1 finding 2).
- It sets `Plugin.Status = Active` when a plugin has at least one applied
  configuration, and back to `Enabled` when it has none.
- Triggers: end of every discovery run, plugin enable/disable, port state
  change (`PUT /api/system/hosts/<id>/ports/...`), NCPA deployment finishing.
- After reconciling it calls the existing `regenerate_and_apply_config()` once,
  under `config_write_lock`. No new Nagios writer.

### 2.4 Enable / disable semantics

- **Enable** returns a preview first: `matched_services` and `matched_devices`
  counts. Confirming enables the plugin, reconciles, applies. If it matches
  nothing the plugin is simply `Enabled` with "No matching services yet".
- **Disable** removes that plugin's services from Nagios (reconcile with the
  plugin off); the affected ports keep their state and frozen plugin so
  re-enabling restores them, with a history row. This closes gap (d).
- **Exclude one device**: in the plugin details, "Stop monitoring" on a matched
  service sets that port to the existing `Ignored` state (same effect as
  `PUT /api/system/hosts/<id>/ports/...`) and reconciles. Re-including sets it
  back to `Monitored`.
- All of these keep the `nagios -v` gate and the existing failure rollback.

### 2.5 What happens to the manual path

- Remove `POST /api/plugin/<id>/configurations`, `GET /api/plugin/targets`, and
  the "Apply to Device" UI (`PluginTargetsSection`). The manual path is gone;
  there is no "Advanced" fallback.
- Plugins that are not port-driven have nothing to attach to. They stay in the
  inventory and can be validated, updated and have their command overridden,
  but show **"Not service-driven"**, offer no Enable/Disable, and are never
  attached. This covers the local-statistics plugins (§2.6) and plugins with
  required arguments and no safe default, such as `check_dummy`, `check_log`,
  `check_mailq`, `check_nagios`, `check_apt`, `check_ide_smart`, `check_dhcp`.
- `plugin-services.cfg` and `monitoring_config.py` are retired. This also
  removes defect (c), because discovery's command layout is used.

### 2.6 The Nagios server's own checks stay with Nagios Core

Decision (Q6/Q7): Pinpoint leaves `localhost.cfg` alone.

- Pinpoint does not generate, adopt, enable, disable, display or edit the stock
  `localhost` services (`PING`, `Root Partition`, `Current Users`, `Total
  Processes`, `Current Load`, `Swap Usage`, `SSH`, `HTTP`). There is no
  Pinpoint screen, route or permission that touches `localhost.cfg`, because it
  only applies to Nagios Core.
- Nagios Core keeps running them. The Dashboard keeps reading their results
  from the status snapshots exactly as it does today; no code in
  `statistics.py` changes.
- In Plugin Manager the five plugins behind the stock local checks
  (`check_load`, `check_disk`, `check_swap`, `check_procs`, `check_users`) are
  ordinary inventory rows marked "Not service-driven", with a short note:
  "Checks the Nagios server itself through Nagios Core. Not managed here."
  They are not auto-enabled and show no monitored services. This supersedes
  the earlier idea of auto-enabling them (Q2).
- Consequence: the Plugin Manager "Active Capabilities" count and Monitoring
  column describe only services Pinpoint manages on discovered devices.
- The reconciler and generator must never write anything for the monitoring
  server (§2.3), so a plugin such as `check_ssh` never adds a second SSH
  service to `localhost`. Today the scan skips the server by the IPv4 addresses
  its hostname resolves to (`get_monitoring_server_ips()`), so a second network
  card could be missed and the server saved as a device. The fix is to widen
  that exclusion to every local interface address in the existing scan code,
  not to add a separate guard in the reconciler.

### 2.7 One port → service → plugin map

Settings → Network Discovery is the single place where the network admin says
which service runs on which port. It currently keeps two tables per protocol,
stored in `DiscoverySettings` and defaulted from `config.py`:

| Table (UI title) | Keys | Behavior today |
|---|---|---|
| Always Treat Port As | `TCP_/UDP_FORCED_SERVICES` | Wins over what nmap detected (`PORT_RULE`); default forces `NCPA_PORT` to `ncpa` |
| Fallback Service Names | `TCP_/UDP_SERVICE_OVERRIDES` | Used only when nmap could not identify the port and only guessed from its number (`PORT_HINT`); defaults 22 ssh, 80 http, 443 https, 5666 nrpe, UDP 161 snmp (the UDP list also carries 22/80/443, a copy of the TCP list) |

Port numbers are also set elsewhere: `NCPA_PORT` and `SNMP_PORT` in
`config.py`, each plugin's default port in `plugin_registry.py`, and the
`AUTO_MONITOR_SERVICES` list.

**Decided (D1, D3, D4):**

- **One table per protocol: Port → Service.** Every entry always wins over
  nmap (D1): the mapped service replaces whatever nmap reported and the port is
  recorded as `PORT_RULE`. This replaces both tables above. Service-name
  validation is unchanged.
- **The chain is** port → service name → plugin → Plugin Manager state →
  Nagios service. The service name comes from, strongest first: an operator's
  per-device pin, the Port → Service table, nmap's fingerprint, nmap's guess
  from the port number (a hint, never trusted on its own). The plugin comes
  from the registry (plugin name or alias, otherwise the generic TCP plugin).
  The service is generated only if that plugin is enabled in Plugin Manager.
- **`AUTO_MONITOR_SERVICES` is retired (D3).** Plugin Manager's enabled state
  replaces the hard-coded list.
- **`NCPA_PORT` stays the one place for the agent's port (D4).** The table
  always contains `NCPA_PORT → ncpa`, derived at read time and shown read-only,
  so the rule can no longer drift from `NCPA_PORT`.
- **Migration.** The four stored columns become two (`TCP_Port_Services`,
  `UDP_Port_Services`, JSON `{port: service}`); entries from both old tables
  are kept and, if a port was in both, the "Always Treat Port As" entry wins as
  it does today. API keys `tcpPortServices` / `udpPortServices` replace the four
  old ones. The downgrade writes everything back as "Always Treat Port As".
- **Behavior change to call out.** The former fallback defaults (22 ssh, 80
  http, 443 https, 5666 nrpe, UDP 161 snmp) now always win. A non-SSH service
  on port 22 would be labelled `ssh`. Stored tables migrate verbatim; for new
  installs the UDP 22/80/443 defaults are dropped from `config.py` because they
  mean nothing on UDP.
- **UI.** The two Settings sections become one. Each row shows which plugin the
  service name resolves to, and warns when it resolves to none ("monitored with
  the generic TCP check" or, on UDP, "skipped").

**Decided: consent (D2).** With `AUTO_MONITOR_SERVICES` gone, which ports a
plugin picks up when an admin enables it:

- An **identified** port is one whose service came from the Port → Service
  table, an operator's pin, or an nmap fingerprint. A port whose service is only
  nmap's guess from its number (including `unknown` and `tcpwrapped`) is **not**
  identified: it never starts monitoring and stays Suggested. Ports in the
  ephemeral ranges are never recorded.
- **A plugin with its own service is consent for those ports.** Enabling
  `check_mysql` monitors every identified `mysql` port on every device, and
  disabling it stops them.
- **The generic TCP plugin picks up every identified port** that has no plugin
  of its own (for example an nmap-identified `http-proxy` on 8080 and a
  `printer` the admin mapped on 9100). This can create many services, so the
  enable preview shows the counts first (§2.4), the list is paginated (§5), and
  a port can be excluded individually with "Stop monitoring".
- UDP is unchanged: a UDP port is monitored only through a plugin that speaks
  its protocol (`dns`, `ntp`, `snmp`), because a generic UDP check cannot tell a
  healthy port from a dead one.
- Ports a plugin picked up are recorded as `Monitored` with their plugin frozen
  (`Plugin_Name`), as today, so a later nmap guess cannot rename the service.

## 3. Data model changes (Alembic migration)

Single new migration; verify one Alembic head before and after (§9).

`PLUGIN_CONFIGURATION` add:

| Column | Purpose |
|---|---|
| `Port_Number`, `Protocol` | Which service port this check belongs to |
| `Metric` (nullable) | SNMP OID / NCPA metric name for multi-check plugins |
| `Nagios_Service_Name` | Final name, e.g. `ssh-22-tcp` (from `finalize_service_names`) |
| `Applied_At` | First time this became active; **not** reset by re-apply. Backs "Running since" |
| `Origin` | `Auto` (reconciler); legacy manual rows are marked `Manual` |

Add a unique constraint on `(PluginID, NetDiscoveryID, Nagios_Service_Name)`.

`DISCOVERY_SETTINGS`: merge `TCP_Service_Overrides` + `TCP_Forced_Services` into
`TCP_Port_Services`, and the UDP pair into `UDP_Port_Services` (§2.7).

`PLUGIN` needs **no new column** for descriptions: the documentation link is
derived from the catalog at read time (§6). Existing `Description`,
`Category`, `Author` are reused.

Upgrade behavior (important): on upgrade, plugins that currently back
monitored ports must be marked `Enabled` by the migration or data step so
existing monitoring does not vanish the first time discovery runs after
deploying. Existing manual `PluginConfiguration` rows have no port data; they
are kept as `Origin = Manual` and listed in the plugin details as legacy
entries until an admin removes them. (There is no manual route afterwards, so
provide a one-time cleanup in the migration notes.)

## 4. Backend work

| Area | Change |
|---|---|
| `plugin_registry.py` | Add the registry→plugin mapping (§2.2) and helper `plugin_for_definition(name)`; mark which plugins are service-driven |
| `create_host_cfg.py` | `build_host_services()` takes the set of enabled plugins and skips (records) ports whose plugin is not enabled. Remove the unconditional generic-`tcp` fallback; `check_tcp` must be enabled to be used. Leave the monitoring server out |
| `api/plugin/reconcile.py` (new) | Reconciler (§2.3) and `preview_enable(plugin_id)` |
| `api/plugin/scanner.py` | Fill descriptions (§6) |
| `api/plugin/service.py` | `enable_plugin` / `disable_plugin` call the reconciler; add `get_plugin_services(plugin_id, page, per_page, search)` with live status (§5); add inventory counts (`services`, `devices`, `service_driven`); remove `get_running_checks()` and the manual apply code; reject enable/disable for non-service-driven plugins (409) |
| `api/plugin/manager.py` | Add `GET /api/plugin/<id>/enable-preview` and `GET /api/plugin/<id>/services`; add exclude/include for a monitored service; **remove** `GET /api/plugin/running`, `POST /api/plugin/<id>/configurations`, `GET /api/plugin/<id>/configurations`, `GET /api/plugin/targets` |
| Startup/ordering | If the plugin inventory is empty when discovery runs, run a plugin scan first. Otherwise nothing would be monitored on a fresh install |
| NCPA deployment | `add_ncpa_port` and relocation go through the same gate; deploying NCPA while `check_ncpa` is disabled surfaces a clear message |

`localhost.cfg`, `commands.cfg` and the installer's Nagios setup are **not**
touched by any change in this plan.

Permissions: reuse `plugin.enable`, `plugin.disable`, `plugin.view`. Retire
`plugin.configure` (no route uses it after this); the seed and migration impact
must follow `Engineering_Standards.md`.

## 5. Monitored services list and status (in plugin details)

With the Currently Running tab removed, the per-service view lives in the
plugin details drawer, as a paginated, searchable **Monitored services** list.
One row = one monitored service (`PluginConfiguration`), in this order:

| Column | Source |
|---|---|
| Service | `Nagios_Service_Name`, e.g. `ssh-22-tcp` |
| Device | `Display_Name` / Nagios host name |
| IP address | `NetworkDiscovery.IP_Address` |
| Status | Live state + detail (below) |
| Running since | `Applied_At` |
| Action | "Stop monitoring" / "Resume" (§2.4) |

This answers "why are there two names": the **service** is the monitored thing
(`ssh-22-tcp` on a device); the **plugin** is the program that checks it
(`check_ssh`). The drawer is already about one plugin, so rows show only the
service.

The inventory table gains a **Monitoring** column (e.g. "12 services on 5
devices", or "Not service-driven") so admins can see coverage without opening
each plugin. The "Active Capabilities" summary card stays.

**Status** is read from the latest `ServiceStatus` row in `history.db`, matched
on host name + service description. `history.db` is a separate bind, so do two
queries and merge in Python (the same approach `statistics.py` uses; SQLite
cannot join across the files):

| Situation | Shown |
|---|---|
| Row exists | `OK` / `WARNING` / `CRITICAL` / `UNKNOWN` chip + `Plugin_Output` text (the metric, e.g. "SSH OK - 0.012s response") |
| No row yet | "Waiting for first check. Applied {time}; checks run every 5 min." |
| Row older than 3x check interval | "No recent data. Last check {time}. Nagios may be down or paused." |
| Config `Failed` | "Not running: {reason from the apply failure}" |
| Port set to Ignored | "Monitoring stopped for this device." |

Status refreshes on the same cadence as the page (no new scheduler). Search
covers service, device and IP. A plugin such as `check_tcp` can match hundreds
of services, hence the pagination.

## 6. Plugin description

- **Source of truth at build time, not runtime.** The server must not fetch
  from the internet on page load (offline installs, SSRF surface, latency).
**Implemented in Phase 1:**

- `server/app/api/plugin/plugin_catalog_data.py` is a committed, *generated*
  catalog of `{name: {description, category, documentation_url}}` for the 60
  plugins in the bundled nagios-plugins 2.4.12 set plus `check_ftp` and
  `check_udp`. `server/scripts/build_plugin_descriptions.py` builds it from the
  `Purpose` lines in `Plugins_List.md`, the official manual pages (for the two
  plugins the catalog lacks), and a hand-curated category map; `--check` fails
  when the file is stale, and a unit test runs it.
- `plugin_descriptions.py` holds the hand-written helpers (lookup, `--help`
  parsing, fill-if-empty).
- `sync_plugin_inventory()` fills `Description` and `Category` for new plugins
  and for existing ones whose fields are **empty**; it never overwrites a value
  an admin or custom upload set. It does not store the documentation link.
- Unknown or custom executables fall back to the first descriptive paragraph of
  their own `--help` output (same timeout and error handling as
  `extract_version`), read at scan time and only for plugins outside the
  catalog.
- `GET /api/plugin/<id>` returns `documentation_url`, derived from the catalog;
  it is `null` for plugins outside it. The drawer shows the description, a
  Category field and a "Documentation" link. Existing installs are backfilled
  on the next plugin scan.
- `check_ncpa` links to the NCPA project page, because the nagios-plugins
  manual has no page for it. Every other link was checked against the manual's
  index; individual pages were not all opened.

## 7. Implementation phases

Each phase is one or more commits on the feature branch and must leave
`pytest` and the frontend tests green.

| Phase | Work | Exit check |
|---|---|---|
| 0. Confirm | **Done**, see §7.1 | Notes in §7.1 |
| 1. Descriptions | **Implemented, uncommitted.** §6. Independent, low risk, can merge first | Drawer shows descriptions after a scan; unit tests for catalog and fallback (done) |
| 2. Data model | §3 migration and models, upgrade data step | `flask db upgrade` and `downgrade` both clean on a copy of a real DB |
| 2b. Port → Service map | §2.7: merge the two Settings tables (migration, settings API and validation, one Settings section with the resolved-plugin column), retire `AUTO_MONITOR_SERVICES`, derive the `NCPA_PORT` entry; widen the monitoring-server exclusion to all local interface addresses (§2.6). Implements the D2 promotion rule | `test_discovery_settings.py`, `test_port_lifecycle.py`, `test_service_identification.py` updated; migration round-trips with both old tables populated; the NCPA entry follows `NCPA_PORT` |
| 3. Reconciler and gating | §2.1–2.3, §4 discovery changes | Unit tests: plugin off → port keeps its state but is not in generated cfg and is recorded as skipped; on → service generated; multi-metric expansion; nothing generated for the monitoring server; idempotent |
| 4. Enable/disable and API | §2.4, §2.5, new routes, remove manual and running routes | Enable preview counts correct; disable removes services and rolls back on reload failure; exclude/include works; non-service-driven plugins reject enable/disable |
| 5. Frontend | Remove the Currently Running tab (`RunningChecksTable`, `getRunningChecks`, running count, tab state); §5 services list in the drawer; Monitoring column and "Not service-driven" state; remove `PluginTargetsSection`; enable-preview confirm | Component tests updated (`PluginsTabs` loses the running tab; replace `PluginTargetsSection` tests); manual check in browser |
| 6. Specs and verification | Update the four specs and `Implementation_Status.md`; live lab re-run (§8) | Lab report attached to the PR |

### 7.1 Phase 0 results

Read from the code, not run against a live Nagios.

1. **`Suggested` means "found, not monitored", as assumed.**
   `network_discovery/port_lifecycle.py` documents `SUGGESTED` as "seen, not
   monitored yet → not in Nagios". Only `CONFIG_STATES` (`MONITORED`,
   `MISSING`) produce Nagios services.
2. **The auto-monitor rule is stricter than this plan first assumed.** A new
   port starts `Suggested` and is monitored automatically only when its
   service is in `AUTO_MONITOR_SERVICES` (default `ssh`, `http`, `https`,
   `snmp`, `ncpa`) and was identified by more than its port number
   (`should_auto_monitor`). A port number alone ("port hint") never starts
   monitoring; other services (`mysql`, `ftp`, `smtp`, `dns`, `ntp`, generic
   TCP) wait for an operator to promote them. **Corrections made to this
   plan:** the reconciler works from `CONFIG_STATES`, not from `Suggested`
   ports (otherwise it would defeat the port-hint safeguard), and disabling a
   plugin gates the service at generation instead of demoting ports. This
   raises Q8.
3. **The monitoring server is already excluded.** `_save_discovered_hosts`
   passes `get_monitoring_server_ips()` to `reconcile_scan(..., skip_ips=...)`
   (`create_host_cfg.py`, `device_identity.py`), so the server never gets a
   `NetworkDiscovery` row and the generator has nothing to emit for it.
   Limit: that set is the non-loopback IPv4 addresses the server's hostname
   resolves to, so an address that lookup does not return would not be
   skipped. Phase 2b widens that exclusion to every local interface address
   (§2.6) instead of adding a guard in the reconciler.
4. **Catalog coverage.** Every registry plugin is in `Plugins_List.md` except
   `check_ftp` and `check_udp` (the registry source already says so). Phase 1
   covers both from the official manual pages. `Plugins_List.md` also lists
   `check_ntp` twice and `check_ldap`/`check_ldaps` together; the generator
   merges them.
5. **Test baseline (Windows dev machine).** The isolated backend suite on a
   clean `main` checkout gives 1 failed, 1531 passed, 23 skipped. The one
   failure, `test_automation.py::TestSecurityCheck::test_flags_broken_plugins_and_logs_summary`
   (`(failed, total)` is `(2, 2)` instead of `(1, 2)`), exists before any
   change here and looks like a file-permission check that behaves differently
   on Windows; it was not investigated further. With Phase 1 applied the suite
   gives the same single failure and 1566 passed (35 new tests). The client
   type check and the plugin component tests pass.

## 8. Testing

- **Unit** (`server/tests/unit/`): new `test_plugin_reconcile.py`; extend
  `test_create_host_cfg.py` for gating and for leaving the monitoring server
  out; update `test_plugin_enable_disable.py`; delete or rewrite tests for the
  removed routes (`test_plugin_monitoring_config.py`, running-checks and
  targets tests in `test_plugin_service.py`); catalog tests for descriptions;
  keep `test_statistics.py` passing, since it protects the Dashboard's server
  stats.
- **Integration/e2e**: re-run the network discovery lab harness
  (`server/tests/e2e/network_discovery/`) with these cases: plugin disabled →
  port listed but no Nagios service; enable → service appears and reaches OK;
  disable → service removed; exclude one device; new device appears →
  auto-attached; NCPA deployment with `check_ncpa` off; the server's own
  statistics still appear on the Dashboard and `localhost.cfg` is byte-for-byte
  unchanged after enabling and disabling plugins.
- **Frontend**: Vitest for the drawer's service-list states in §5, the
  Monitoring column, the "Not service-driven" state and the enable-preview
  dialog; confirm no Running tab remains.
- Follow `server/tests/README.md` and `Engineering_Standards.md`.

## 9. Branching and merge strategy (do not affect `main`)

`main` must not change until this is reviewed and verified.

1. Work only on `feature/plugin-driven-monitoring`, created from `main`:
   ```
   git fetch origin
   git switch -c feature/plugin-driven-monitoring origin/main
   git push -u origin feature/plugin-driven-monitoring
   ```
   (Do not reuse the older `feature/plugin-manager-phase1` or `plugin-manager-*`
   branches; they are stale.)
2. Never commit or push directly to `main`. One commit per logical step, in the
   phase order of §7, so any phase can be reverted alone.
3. Keep the branch current: periodically `git merge origin/main` into the
   feature branch (no rebase/force-push once a PR is open) and resolve
   conflicts there, not on `main`.
4. Before opening the PR, check there is exactly one Alembic head after the
   merge (other branches also add migrations) and that migration `downgrade`
   works.
5. Open a PR into `main` only when: all tests pass, the lab re-run (§8) passes,
   and the specs (§11) are updated in the same PR.
6. If problems appear after merge, revert the merge commit; the migration
   includes a `downgrade`, and the upgrade data step in §3 is the only
   data-changing part, so note its reverse in the PR description.
7. Optional safety: land Phase 1 (descriptions) as its own small PR first; it
   does not depend on the rest.

## 10. Decisions

| # | Question | Decision |
|---|---|---|
| Q1 | Fresh installs: monitor nothing until plugins are enabled? | **Yes, opt-in.** Banner "No plugins enabled, no network services are monitored" on Plugin Manager. Upgrades preserve current monitoring (§3) |
| Q2 | Plugins with no port | **Superseded by Q7.** They are shown as "Not service-driven" and are not attached or auto-enabled (§2.5, §2.6) |
| Q3 | Exclude one device from an enabled plugin? | **Yes**, via the existing `Ignored` port state, shown as "Stop monitoring" (§2.4) |
| Q4 | "Currently Running" tab | **Removed.** Per-service view moves into plugin details (§5) |
| Q5 | Custom plugin upload (disabled) and the stale claim in `Implementation_Status.md` | **Leave as is.** Out of scope for this plan |
| Q6 | Stock Nagios `localhost` services | **Leave `localhost.cfg` alone.** Pinpoint does not generate, adopt, show or edit them, and gives users no access to it; it only applies to Nagios Core (§2.6) |
| Q7 | Local-statistics plugins and their defaults | **Nothing to configure in Pinpoint.** Nagios Core's stock checks keep providing the server's statistics; the Dashboard reads them as today (§2.6) |
| Q8 | One port → service → plugin map, and which ports a plugin picks up when enabled | **Decided (§2.7).** D1: one table, every entry always wins. D2: enabling a plugin is the consent for its own ports, and enabling the generic TCP plugin picks up every identified port. D3: `AUTO_MONITOR_SERVICES` retired. D4: `NCPA_PORT` stays the one place for the agent port and the table entry is derived from it |


## 11. Specifications to update in the same PR

- `Data_Model_and_Integrations.md`: ownership table in §2.1, derived
  `PluginConfiguration`, new columns, monitoring now gated by plugin status,
  the Nagios server's checks stay with Nagios Core, description catalog.
- `Backend_Modules_and_Routes.md`: Plugin API table (new preview/services/
  exclude routes; removed running, configure and targets routes), permission
  list.
- `Frontend_Modules_and_Routes.md`: Plugin Manager components (no Running tab,
  drawer services list, Monitoring column, removal of `PluginTargetsSection`).
- `Implementation_Status.md`: remove the "Plugin lifecycle and discovery" gap
  and note the disable-does-not-stop-checks gap as closed. The stale
  custom-upload claim is left untouched per Q5.
- Network Discovery settings (in `Data_Model_and_Integrations.md`,
  `Backend_Modules_and_Routes.md` and `Frontend_Modules_and_Routes.md`): the
  single Port → Service table, the retired `AUTO_MONITOR_SERVICES`, the derived
  NCPA entry, and the new settings API keys.
- `AGENTS.md`: no change unless a new spec file is added (this plan follows the
  `NCPA_Deployment_UI_Plan.md` precedent and is not indexed).

## 12. Risks

| Risk | Mitigation |
|---|---|
| Upgrade silently drops monitoring | Migration marks plugins backing monitored ports `Enabled`; lab test of upgrade from a populated DB |
| Fresh install with empty plugin inventory monitors nothing | Auto-run a plugin scan before discovery when inventory is empty; banner (Q1) |
| A plugin such as `check_ssh` duplicates a stock `localhost` service | Reconciler and generator skip the monitoring server (§2.3); unit and lab tests assert nothing is generated for it |
| Admins expect `check_load`/`check_disk` to be manageable | Clear "Not service-driven: checked by Nagios Core, not managed here" note and no Enable/Disable buttons (§2.6) |
| Enabling a broad plugin (`check_tcp`) attaches hundreds of services | Enable preview with counts and confirm step; paginated list (§2.4, §5) |
| Removing routes breaks callers | Search client and tests for `running`, `targets`, `configurations` usages before deleting; update specs together |
| Former fallback entries (22 ssh, 80 http, 443 https) now always win and mislabel an unrelated service on that port | Called out in §2.7; the Settings table shows the resolved plugin; admins can remove or change an entry, and a per-device pin still outranks the table |
| Reload failure leaves Nagios broken | Reuse the existing validate/backup/reload/rollback pipeline unchanged |
| Two Alembic heads from parallel branches | Check before PR (§9) |
| Cross-bind join between `system.db` and `history.db` | Merge in Python as `statistics.py` does |
