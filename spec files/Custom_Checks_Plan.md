# Plan: Custom Checks for Plugins That Discovery Cannot Drive

Status: **decisions Q-C1 to Q-C7 answered by the owner (2026-10-07); phases C0b to C3 built on `feature/custom-checks` and unit-tested; C4 (lab run) and C5 (server-host checks) remain.** The plugin audit the owner asked for (Q-C2) is §2.4, and its result changes which plugins this plan is for.
Follows the format of `Device_Ports_UI_Plan.md`; like it, this file is not indexed in
`AGENTS.md`. Behaviour rules belong in the specs listed in §10 once decisions are made.

Closes (once built): a new gap, G28 in `Plugin_Driven_Monitoring_Plan.md` §13: "Plugins that
are not service-driven cannot be used for anything".

Goal: an administrator can run a plugin that discovery cannot attach to a port (for example
`check_apt`, `check_by_ssh`, `check_cluster`, `check_clamd`) against a chosen device, with
arguments they supply, and see the result in the same places as any other service
(Plugin Manager, Network Health, Alerts), without bringing back the manual path that was
retired.

---

## 1. Problem

Plugin Manager enables a plugin only by attaching it to discovered ports
(`Plugin_Driven_Monitoring_Plan.md` §2.4). The registry covers 11 plugins. The other ~60
installed plugins show "Not service-driven", offer no Enable or Disable, and are never run
(§2.5). The retired manual path ("Apply to Device") is the only thing that used to run them.

Two kinds of plugin are affected, and they need different things:

| Kind | Examples | Why discovery cannot drive it |
|---|---|---|
| Needs arguments only an admin knows | `check_by_ssh -C <cmd>`, `check_log`, `check_mailq`, `check_file_age`, `check_dummy` | No port, and no safe default argument |
| Checks a thing, not a service | `check_apt`, `check_cluster`, `check_clamd`, `check_breeze` | There is no port for it; the target is a device or a group of services |

Some of the ~49 are in neither group: discovery could drive them and the registry simply
does not list them (§2.4 audits every one). Those should become registry entries, not
custom checks.

Checks of the Nagios server itself (`check_apt` on the server, `check_uptime`,
`check_sensors`, ...) are a separate follow-up feature (§2.6). The five stock local
plugins (`check_load`, `check_disk`, `check_swap`, `check_procs`, `check_users`) stay with
Nagios Core (§2.6 of the monitoring plan, decision Q6/Q7).

---

## 2. Design

> **Built differently from the draft in three places** (the rest is as written):
> 1. A custom command is generated from the plugin's argument table
>    (`CUSTOM_CHECK_FIELDS`), the way the registry builds its commands, not from the plugin's
>    stored Commands row. So a command Override in Plugin Manager does not change a custom
>    check; this keeps every argument validated and quoted by one code path.
> 2. Pause is a flag in `Configuration_Data` (`{"paused": true}`), not a new column or status.
> 3. A device picker needs its own route, `GET /api/plugin/custom-check-devices`, under
>    `plugin.custom_check`, so the form does not depend on the Network Health permission.

### 2.1 What a custom check is

One row per check: *plugin + device + name + arguments (+ optional warn/crit)*. It
produces exactly one Nagios service on that device.

- Stored in `PLUGIN_CONFIGURATION` with a new `Origin` value `CUSTOM`. `MANUAL` is not
  reused: it means legacy rows with NULL service names that nothing may touch, and the
  reconciler already skips it. `AUTO` rows stay the reconciler's alone, so the two never
  fight over a row.
- `Nagios_Service_Name` is `custom-<plugin>-<slug>` (e.g. `custom-apt-weekly-updates`),
  unique per device. `Port_Number` and `Protocol` stay NULL.
- Arguments live in `Configuration_Data` as a list of strings, never one free-text
  command line.

### 2.2 How it reaches Nagios

Through the same writer as everything else (`regenerate_and_apply_config_status`):
the generator adds the custom services to the device's host block in `hosts.cfg`, the
config is validated with Nagios's own check, and a rejected config rolls back. No second
config file, so the retired `plugin-services.cfg` problems (drift, second host object) do
not return.

Each plugin gets one generated command, `pinpoint_custom_<plugin>`, built from the plugin's
argument table (`check_by_ssh` is `$USER1$/check_by_ssh -H $HOSTADDRESS$ -C '$ARG1$' $ARG2$`).
Required arguments are passed as `$ARG1$..$ARGn$` and the optional ones are rendered together
into the last `$ARG$`, exactly as the registry does.

### 2.3 Safety

Arguments end up in a shell-executed command line, so this is the risky part:

- Reuse the registry's rules (`FORBIDDEN_VALUE_CHARACTERS`, single quoting, no `!`, `$`,
  `;`, backticks) on every argument. Error messages name the argument, never its value.
- A new **permission** (not a role), `plugin.custom_check`, added to the seed list in
  `api/commands/seed.py` and installed on existing databases by `flask sync-permissions`.
  It is separate from `plugin.enable`, and from the existing `plugin.custom_add`, which
  is reserved for uploading a custom plugin file (its route is commented out).
  Routes use `require_permission("plugin.custom_check")`, and the UI hides the section
  from users without it. Every create, edit, pause and delete is written with
  `record_plugin_action` and the activity log, as enable and disable are today.
- **Administrator.** The code has no superadmin and no bypass: `_has_permission` only
  checks the role's `RolePermission` rows. The owner confirmed the intent is the
  Administrator role (Q-C5), so `plugin.custom_check` is granted to Administrator in the
  seed, and `flask sync-permissions` adds it to Administrator on existing databases (verified
  in C1: that command creates every missing permission and grants all of them to Administrator).

### 2.4 Audit: which plugins really are not service-driven (Q-C2)

The owner asked to double-check, because some may be port-driven and just missing from the
registry. All 49 catalog plugins outside the registry were sorted by what they need to run,
using their default command in `plugin_command_defaults.py`. Four outcomes:

| Class | Meaning | Plugins | What happens |
|---|---|---|---|
| **A. Port-driven, missing from the registry** | Check a well-known port and can run with only host and port | `check_pgsql` (5432), `check_ldap` / `check_ldaps` (389 / 636; they need a base DN, so without one they fall back to the generic TCP check, as MySQL does without a user), `check_ircd` (6667), `check_rpc` (111), `check_time` (37), `check_ntp_peer` (UDP 123, an alternative to `check_ntp_time`) | **Add to the registry**, not as custom checks. Each is a `PluginDefinition`, a Port → Service rule and tests; enabling then works like `check_ssh`. These seven are the approved set (Q-C6) |
| **B. Host-driven** | Probe the device, not a port | `check_ping`, `check_icmp`, `check_fping`, `check_dig` (a lookup, overlaps `check_dns`) | Not custom checks. Host aliveness is already a Nagios host check; a per-host service is a separate small feature (Q-C7). Until then they stay inventory-only |
| **C. Probes a device over the network but needs arguments or credentials** | The target is the device; only an admin knows the arguments | `check_by_ssh`, `check_breeze`, `check_wave`, `check_hpjd`, `check_ifstatus`, `check_ifoperstatus` (needs an interface index), `check_ups` (needs the UPS name), `check_nt`, `check_nwstat`, `check_overcr` and `check_real` (rare services that each need a mandatory argument: `-v` or `-u`; Q-C6), `check_radius` (needs a shared secret), `check_ssl_validity`, `check_disk_smb` (needs a share), `check_mysql_query`, `check_oracle`, `check_dbi`, `check_game`, `check_clamd` | **Custom checks** (this plan). Those that need a secret (`check_radius`, database passwords) are blocked until a secrets store exists (§9), and the dialog says so |
| **D. Checks the machine it runs on** | Local to the Nagios server, whatever device you pick | `check_apt`, `check_uptime`, `check_sensors`, `check_ide_smart`, `check_file_age`, `check_log`, `check_mailq`, `check_mrtg`, `check_mrtgtraf`, `check_flexlm`, `check_nagios`, `check_dummy`, and the five stock local plugins | **Not offered on other devices**, because the result would be the server's, filed under another device's name. They wait for the server-host feature (§2.6). `check_cluster` (aggregates service states) is out of scope for now |

Where the audit table in code (`PLUGIN_CLASSES`) differs from the list above: `check_dhcp` is
class D (it broadcasts from the server's own interface), and the deprecated `check_ntp` has a
class of its own, `replaced`, because `check_ntp_time` already covers it. A test fails when a
catalog plugin has no class, which is how `check_ntp` was found.

Rules the audit gives us:
- A plugin is class C only if its default command takes `$HOSTADDRESS$` (`-H`). The dialog
  offers custom checks for class C and nothing else; class D never appears in it.
- The classes live in one table, `CUSTOM_CHECK_PLUGINS`, next to the registry, with the
  field hints for each plugin. Moving a plugin between classes is a code change reviewed
  with the spec, not a database setting, so the list cannot drift from what the UI offers.
- Anything the audit got wrong is fixed by moving it between classes; no schema change.
- The four rare plugins (`check_nt`, `check_nwstat`, `check_overcr`, `check_real`) are
  therefore not lost: they get no registry entry and no automatic discovery, but an
  administrator who runs one of those services can still monitor it as a custom check on
  that device. If one becomes common, moving it to class A is a registry entry and nothing
  else.

### 2.5 Targets

A target is a discovered device (`NetworkDiscovery`), as in `PluginConfiguration`'s own
docstring: Plugin Manager must never create host objects. A check on a retired or merged
device is removed with it (reuse the cleanup the reconciler already does for AUTO rows;
CUSTOM rows follow the same merge and retire rules).

The monitoring server itself is **not** a target in this plan. The reconciler is not
allowed to write anything for it (§2.3, §2.6 of the monitoring plan). That is the
server-host feature, §2.6 below.

### 2.6 Server-host checks: a separate follow-up (Q-C1, agreed)

Class D plugins (`check_apt` and friends) belong to the Nagios server, so they need their
own feature, planned separately and built after this one. What this plan fixes now, so the
two do not conflict:

- The server-host feature will add Pinpoint-owned services on the server's own host
  object. It must not edit `localhost.cfg`, and must not reuse a device-targeted custom
  check. The two features share the argument validator and the permission, and nothing
  else.
- Open questions for that plan: where its services are written (a Pinpoint-owned file or
  the shared `hosts.cfg` writer), how the server's host object is identified, and whether
  its checks appear in Network Health beside device checks.
- Until then the plugin drawer shows class D plugins as "Runs on the Nagios server. Not
  available yet" instead of the generic "Not service-driven".

---

## 3. UI

In the plugin drawer, the "Not service-driven" note depends on the class from §2.4. Class C
plugins get a **Custom checks** section (same layout as `PluginServicesSection`), shown
only to users with `plugin.custom_check`. Class D plugins get "Runs on the Nagios server.
Not available yet", class B keeps "Not service-driven", and class A plugins can be enabled
once they are in the registry. The Custom checks section:

- A list of checks: name, device, status chip (reuse the existing chips), last result,
  Pause / Resume, Edit, Remove. Empty state: "No checks yet. Add one to run this plugin
  against a device."
- **Add check** opens a dialog: device picker (search by hostname or IP), name, the
  plugin's arguments, optional warning and critical. Saving shows the same "applied or
  not" notice the enable flow uses, including Nagios's message if config was rejected.
- The inventory table's Monitoring column shows "N custom checks / M devices" for these
  plugins instead of "Not service-driven" once any exist.

The Monitoring column wording and the drawer note change, so
`Frontend_Modules_and_Routes.md` and the Plugin Manager component tests change with it.

---

## 4. Backend work

| Area | Change |
|---|---|
| `plugin_models.py` + migration | `PluginConfigurationOrigin.CUSTOM`; no new table. Batch-mode migration like the existing ones |
| `api/plugin/custom_checks.py` (new) | create / update / pause / delete, argument validation, name uniqueness per device |
| `api/plugin/manager.py` | `GET/POST /api/plugin/<id>/custom-checks`, `PUT/DELETE .../custom-checks/<check_id>`, pause and resume; `plugin.custom_check` permission |
| `network_discovery/create_host_cfg.py` | emit CUSTOM services in the host block and the `pinpoint_custom_*` commands; they must survive a rescan and a reconcile |
| `reconcile.py` | leave CUSTOM rows alone, and include them in the single apply so there is still one write |
| `service.py` | inventory counts and `service_driven` stay as they are; add `custom_checks` count; services list includes CUSTOM rows |
| statistics / Network Health | `_plugin_key` already maps `pinpoint_` commands; confirm custom services group under their plugin and are not mistaken for discovered ports |

---

## 5. Phases

| Phase | Content | Done when |
|---|---|---|
| C0 | One-hour spike: render one `check_by_ssh` service for a lab device and validate it | **Not done on a live Nagios.** The generated service and command are checked in unit tests only; the spike's `nagios -v` is the first item of C4 |
| C0b | **Done.** Add the approved class A plugins to the registry (a `PluginDefinition`, Port → Service rule and tests each). Independent of the rest, so it can ship first | Enabling each one attaches it to a lab port, as `check_ssh` does |
| C1 | **Done.** Migration, model, argument validator, unit tests | Validator rejects every forbidden character; migration upgrades and downgrades |
| C2 | **Done.** Routes, permission, generator, reconcile coexistence | A custom check survives rescan, reconcile, merge and retire; rejected config rolls back |
| C3 | **Done.** Frontend section, dialog, class notes, Monitoring column | Component tests; manual check in a browser |
| C4 | Specs (done), acceptance plan and lab run (open) | Cases in §7 pass on the lab |
| C5 | Server-host checks (§2.6): its own plan, written after C4 | Separate plan approved |

C0 comes first because the one-service-per-check model and the shared writer are
assumptions until a real config validates.

---

## 6. Risks

| Risk | Mitigation |
|---|---|
| Argument injection into a shell command | §2.3 validation plus quoting, admin-only permission, audit log |
| `check_by_ssh` used to run destructive commands | Warning in the dialog, admin-only, every change logged; no secrets stored |
| A bad custom check makes Nagios reject `hosts.cfg` and blocks all monitoring | Existing validate-and-rollback; the check is saved as Failed with Nagios's message |
| Custom services confuse Network Health grouping | C2 test: a `custom-apt-*` service groups under `check_apt` and never appears as a port |
| A local plugin (`check_apt`) is attached to another device and reports the server's state under that device | Class D plugins are not offered; only plugins that take `-H` are |
| The audit misclassifies a plugin | One table, one place to move it; a test asserts every catalog plugin has exactly one class |
| A role other than Administrator is assumed to have the permission | It is granted to Administrator only; other roles get it by editing the role |
| Plugin file named with an extension (`check_ncpa.py`) | Already handled by `normalize_plugin_name`; the generated command must use the real filename |

---

## 7. Testing

- Unit: every catalog plugin has exactly one class (A, B, C or D), every class C plugin's default command takes `$HOSTADDRESS$`, and the registry contains every approved class A plugin; argument validator (every forbidden character, empty, too long), name
  uniqueness, CUSTOM rows untouched by `reconcile_plugin_monitoring`, kept on merge and
  deleted on retire, generator output for one and several checks.
- Route tests: permission, 404 for a missing device or plugin, 409 for a service-driven
  plugin, rollback on a rejected config.
- Frontend: section render states, dialog validation, Monitoring column wording.
- Lab: add `check_apt` against a device, see the service in Nagios and Network Health,
  pause it, remove it, retire the device.

---

## 8. Decisions

Answered by the owner (2026-10-07):

| # | Question | Answer |
|---|---|---|
| Q-C1 | Can the monitoring server be a target? | Agreed: not in this plan; a separate server-host feature (§2.6) |
| Q-C2 | Which plugins may take a custom check? | Double-check first, because some may be service-driven and missed. Done in §2.4: class A moves to the registry, class C takes custom checks, B and D do not |
| Q-C3 | Who may create checks? | A **permission**, not a role. The superadmin is expected to hold every permission natively (see Q-C5) |
| Q-C4 | Scheduling options in scope? | Agreed: not now |

Answered by the owner, second round:

| # | Question | Answer |
|---|---|---|
| Q-C5 | The code has no superadmin or permission bypass; how is "holds every permission" met? | The owner meant the **Administrator** role. It gets every permission in the seed and in `sync-permissions`, including `plugin.custom_check`; `_has_permission` is not changed |
| Q-C6 | Which class A plugins go into the registry? | The first seven: `check_pgsql`, `check_ldap`, `check_ldaps`, `check_rpc`, `check_ircd`, `check_time`, `check_ntp_peer`. The rarer four become class C custom checks (§2.4) |
| Q-C7 | A per-host ping or lookup service (class B)? | A future feature; not part of this plan |

---

## 8b. Passwords (built on `feature/custom-check-secrets`)

A password field of a plugin (`secret` in `CUSTOM_CHECK_FIELDS`) is handled as follows.

- **Stored encrypted.** `app/secrets_store.py` encrypts it with Fernet; the key is derived (HKDF-SHA256)
  from `PINPOINT_SECRETS_KEY` when set, otherwise from the app's `SECRET_KEY`. The token is kept in
  `Configuration_Data["secrets"]` as `v1:<token>`. No migration is needed.
- **Never returned or logged.** The API lists only `secrets_set` (which are stored) and
  `secrets_readable`; history messages, errors and logs never contain a value (an invalid value is
  reported by argument name only).
- **Write-only in the UI.** A masked box; on a change, blank keeps the stored password and an optional
  one can be removed (`clear_secrets`). A required password cannot be removed.
- **Decrypted only to build the command**, when `hosts.cfg` is generated. If it cannot be read (the key
  changed), the check is left out of the file with a warning, the list says so, and the administrator types
  the password again. Without a fixed `SECRET_KEY` (the debug session's random one) nothing is stored.
- **What it does not protect.** Nagios needs the password in the check's command, so it is in `hosts.cfg`
  in plain text, in the Nagios web UI's command view, and in the process list while the check runs. Keep
  `hosts.cfg` readable only by the Nagios user and group; Pinpoint logs a warning when a host file that
  holds a password is world-readable (POSIX). Moving passwords into Nagios resource macros is a possible
  later step; it would mean editing `resource.cfg`, which Pinpoint does not touch.
- **Plugins.** `check_radius` and `check_mysql_query` (previously "needs a password") now take custom
  checks, and `check_nt` (`-s`) and `check_disk_smb` (`-p`) gain an optional password. `check_dbi` and
  `check_oracle` stay unavailable: their credentials are not passed as a plain argument.

## 9. Out of scope

Server-local checks (§2.6, its own plan), per-check notification rules, check groups or templates,
importing existing Nagios services, keeping passwords out of `hosts.cfg` (§8b), and plugins that need a daemon or
install step. The five stock local plugins stay "Not managed here".

---

## 10. Specifications to update in the same change

`Plugin_Driven_Monitoring_Plan.md` (§2.5 and §13 gap), `Backend_Modules_and_Routes.md`,
`Data_Model_and_Integrations.md` (the new Origin value), `Frontend_Modules_and_Routes.md`, `Plugins_List.md` (the class of each plugin), the seed permission list,
`Implementation_Status.md`, and `server/tests/README.md` for any new test files.
