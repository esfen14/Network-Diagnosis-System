# Plugin-Driven Monitoring Lab Test Plan

**Status:** Draft for review
**Test level:** Live manual lab (supplements the Tier 2 plan; nothing here is automated)
**Code under test:** branch `feature/plugin-driven-monitoring`
**Design:** [`Plugin_Driven_Monitoring_Plan.md`](../../../spec%20files/Plugin_Driven_Monitoring_Plan.md)
**Companion plans:** [`NETWORK_DISCOVERY_EXTENDED_TEST_PLAN.md`](NETWORK_DISCOVERY_EXTENDED_TEST_PLAN.md),
[`NCPA_PORTS_AND_SERVICE_IDENTIFICATION_LAB_TEST_PLAN.md`](NCPA_PORTS_AND_SERVICE_IDENTIFICATION_LAB_TEST_PLAN.md)

## 1. Purpose and scope

The unit tests for this work mock Nagios (`regenerate_and_apply_config_status` is
replaced), nmap and the browser. They prove the logic: which services are planned,
which rows are written, how failures roll back, what each route returns, and that a
populated database survives the migration chain (`test_upgrade_rehearsal.py`). This
plan checks what they cannot:

- a real `nagios -v`, reload and rollback;
- real service results reaching the "Monitored services" list, including the
  waiting, stale and critical states;
- a real upgrade of a copy of a production database;
- the Plugin Manager and NCPA pages in a browser, light and dark;
- that Nagios Core's own `localhost.cfg` is left alone.

It closes the open items G4, G5, G19 and G23 in the plan's gap register (§13) when
it passes. Record the result of each case there.

### 1.1 What is not repeated

Network discovery (ND-*), service identification (SVC-*), the NCPA deployment cases
(NCPA-*, DEP-*) and settings (DS-*) keep their own plans. Where this plan needs
their fixtures it says so.

## 2. Assumptions this plan checks

If one fails, record a defect; do not adjust the case.

1. `nagios -v` accepts the generated `hosts.cfg` with services only for enabled plugins,
   including when a plugin is switched off and its services disappear (PM-05).
2. A reconcile that Nagios rejects leaves the running config, the plugin state and the
   port states as they were (PM-07, PM-08).
3. The statuses in the services list come from the same `SERVICE_STATUS` rows the
   Dashboard uses, matched on the stable Nagios host name (PM-03).
4. An upgraded install keeps every service it had (UPG-01), and the first discovery
   after upgrade does not drop monitoring on an install that never scanned its plugins
   (UPG-02).
5. Enabling the generic TCP plugin on a fresh install attaches every identified port with no
   plugin of its own (intended). An upgrade holds back the ports it would have picked up, so it
   starts nothing new (gap G25; UPG-01 step 7 and GT-01).

## 3. Preconditions

- Complete the existing tester handoff (Extended plan §8.3). Use the existing isolated
  `/28`. Never scan the management network.
- Credentials come from environment variables only. Never paste passwords, NCPA tokens
  or private keys into shell history, evidence or the report.
- Back up first: `cp server/system.db server/system.db.pre-plugins` and the same for
  `history.db`. Also copy `hosts.cfg`, `nagios.cfg` and, if it exists,
  `plugin-services.cfg`.
- Record `git log -1 --oneline` of the deployed code and
  `alembic_version` before and after.
- The `sqlite3` CLI may be missing: use Python's `sqlite3` module for the queries below.
- Use **target02** for new fixtures (as in the NCPA plan §4.1) and **target01** for the
  standard ports. Restore the baseline between stages where the table in §4 says so.
- Keep hypervisor console access to the guests.

### 3.1 Helper queries

```bash
DB=server/system.db
# What each plugin is doing
sqlite3 $DB "select Name, Status from PLUGIN where Name in ('check_ssh','check_http','check_tcp','check_snmp','check_ncpa') order by 1;"
# Automatic services behind a plugin (the services list in the drawer reads these)
sqlite3 $DB "select p.Name, d.Nagios_Host_Name, c.Nagios_Service_Name, c.Status, c.Applied_At
             from PLUGIN_CONFIGURATION c join PLUGIN p on p.PluginID=c.PluginID
             join NETWORK_DISCOVERY d on d.NetDiscoveryID=c.NetDiscoveryID
             where c.Origin='AUTO' order by 1,2,3;"
# Hand-made rows left from the old manual path
sqlite3 $DB "select p.Name, d.Nagios_Host_Name, c.Service_Description from PLUGIN_CONFIGURATION c
             join PLUGIN p on p.PluginID=c.PluginID join NETWORK_DISCOVERY d on d.NetDiscoveryID=c.NetDiscoveryID
             where c.Origin='MANUAL';"
# Ports and how they are flagged
sqlite3 $DB "select Port_Number, Service_Name, Port_State, Plugin_Name, Expected_Service_Name, Mismatch_Acknowledged_At
             from OPEN_TCP_Services where NetDiscoveryID=<id> order by 1;"
# Plugin history
sqlite3 $DB "select h.Action, h.Result, h.Message from PLUGIN_HISTORY h order by h.PluginHistoryID desc limit 10;"
```

```bash
# localhost.cfg must never change (LCL-01)
sha256sum /usr/local/nagios/etc/objects/localhost.cfg
# The live service list as Nagios sees it
curl -s -u "$NAGIOS_USER:$NAGIOS_PASS" "http://localhost/nagios/cgi-bin/statusjson.cgi?query=servicelist&hostname=<host>"
```

Enums are stored by name (`AUTO`, `MANUAL`, `MONITORED`, `ENABLED`, ...).

## 4. Order

| Stage | Cases | State |
|---|---|---|
| 0 | UPG-01, UPG-02, BOOT-02, LCL-01 (baseline hash) | copy of the real database; then a clean install |
| 1 | NS-01, PM-01, PM-02 | fixtures running, nothing enabled |
| 2 | PM-03, PM-04, PM-05, PM-06 | `check_ssh` and `check_http` |
| 3 | PM-07, PM-08 | a way to make Nagios reject a config (§6.2) |
| 4 | MM-01, GT-01 | target02 fixture with SSH on port 80 |
| 5 | NC-01, NC-02 | restore target02 baseline, then NCPA |
| 6 | LCL-01 (compare), UI-01, PF-01 | all of the above applied |
| 7 | CLEAN-03, then CLEAN-01 | restored |

## 5. Stage 0: upgrade, boot and the stock server checks

### UPG-01: upgrade a copy of the real database

1. Work on a copy. Record the starting revision and these counts before touching it:
   monitored/missing ports (`OPEN_TCP_Services`, `OPEN_UDP_Services`), plugins by status,
   `PLUGIN_CONFIGURATION` rows, the discovery settings tables, and whether
   `plugin-services.cfg` exists and what it defines.
2. `flask db heads` prints exactly one head. `flask db upgrade` reaches it.
3. Plugins that back a monitored or missing port are `ENABLED`. Plugins in a failure state,
   plugins with only suggested ports and plugins that check no port are unchanged.
4. Every old `PLUGIN_CONFIGURATION` row is `MANUAL`; applied ones have `Applied_At`.
5. `DISCOVERY_SETTINGS` has `TCP_Port_Services` and `UDP_Port_Services`, with the old
   "always treat port as" entries winning where a port was in both tables.
6. The permission `plugin.configure` and its role grants are gone; Manage Roles no longer
   lists it.
7. Start the app and run discovery. Record, per device, every service that was in Nagios
   before and is not after (expected: none), and every port that moved from `SUGGESTED`
   to `MONITORED` (expected: none; the upgrade holds the Suggested ports its enabled plugins
   would have promoted). List the held ports with
   `select Port_Number, Service_Name from OPEN_TCP_Services where Promotion_Held = 1` (and the UDP
   table) and give them to the owner: they stay Suggested until promoted by hand, e.g.
   `PUT /api/system/hosts/<id>/ports/tcp/<port>` with `{"state": "MONITORED"}`.
8. Run `nagios -v` and confirm Nagios reloaded without a duplicate-service error.
9. Downgrade the copy one revision at a time to the starting revision and confirm no
   `AUTO` rows are left behind as look-alike manual rows, then upgrade again.

**Pass:** one head; no service lost; every difference in step 7 explained.

### UPG-02: upgrade an install that never scanned its plugins

On a copy where `PLUGIN` is empty but ports are monitored (delete the rows if needed):

1. Upgrade. The migration enables nothing (there is nothing to enable).
2. Run discovery. The plugin inventory is scanned first and the plugins behind monitored
   ports are `ENABLED` (see `ensure_plugin_inventory`); Nagios keeps every service.
3. A fresh database with no monitored ports enables nothing (BOOT-02).

**Pass:** monitoring is unchanged after the first discovery.

### BOOT-02: a clean install starts opt-in

1. Empty database; `flask db upgrade` reaches the head; the app serves the login page.
2. First discovery on the lab network scans the plugin directory when the inventory is
   empty. Plugin Manager lists the plugins, none enabled.
3. The page shows "No plugins enabled, so no network services are monitored".
4. Nagios has the stock `localhost` services and **no** services for discovered devices.
   The discovered ports exist in the database as `SUGGESTED`/`MONITORED` ports.

**Pass:** nothing port-based is monitored until a plugin is enabled.

### LCL-01: Nagios Core's own checks are left alone

1. Record `sha256sum localhost.cfg` and the Dashboard's server statistics (load, disk,
   swap, processes, users) now.
2. After PM-03 .. PM-08 and NC-01: the hash is **identical**, the statistics still update,
   and no service for host `localhost` was added by Pinpoint (`hosts.cfg` has no
   `localhost`).
3. `check_load`, `check_disk`, `check_swap`, `check_procs` and `check_users` show
   "Not service-driven ... Checks the Nagios server itself through Nagios Core. Not managed
   here." and cannot be enabled (NS-01).

**Pass:** byte-for-byte unchanged hash; Dashboard statistics unaffected.

## 6. Plugin Manager as the switch

### NS-01: plugins that check no port

1. Open `check_ping`, `check_load`, `check_dummy`: "Not service-driven", no Enable button,
   no services list; the Monitoring column says "Not service-driven".
2. `POST /api/plugin/<id>/enable` returns 409 and the plugin keeps its status.
3. A plugin that was `Active` before the upgrade can still be disabled.
4. Nothing is lost by `check_ping` not attaching (gap G13). On the Nagios server run
   `grep -A3 "command_name.*check-host-alive" /usr/local/nagios/etc/objects/commands.cfg`
   (find the file with `grep -E "^cfg_file|^cfg_dir" /usr/local/nagios/etc/nagios.cfg` if it is
   elsewhere): `command_line` should run `check_ping`. Then confirm the Dashboard's average
   response time and packet loss are filled in and that a host has `rta` and `pl` rows in
   `HOST_PERF_DATA` (history.db) without any plugin enabled.

### PM-01: nothing is monitored until a plugin is on

1. With no plugin enabled, run discovery on the lab. Ports appear (Network Services
   report / device ports) but `hosts.cfg` defines no service for them.
2. Plugin Manager's Monitoring column shows "—" for every plugin.

### PM-02: the enable preview matches the result

For `check_ssh`, then `check_http`, then `check_tcp`:

1. Open the plugin; **Enable** shows a dialog with the services and devices counts.
2. Cancel: nothing changes (status, ports, `PLUGIN_CONFIGURATION`).
3. Enable again and confirm; the counts shown equal the rows created
   (`select count(*), count(distinct NetDiscoveryID)` from the AUTO query) and the number
   of new services in `hosts.cfg`.
4. For `check_tcp` the preview lists many services; confirm only identified ports are
   included (guessed `unknown` ports are not).

### PM-03: services appear, run, and show live status

1. After enabling `check_ssh`: every discovered SSH port has a service
   (`ssh-22-tcp`, ...); `nagios -v` passes; the services reach OK in Nagios.
2. Plugin details shows the Monitored services list: service, device, IP, "running since",
   and a status chip with the real plugin output.
3. Immediately after enabling, new services show **Waiting** with "Waiting for first
   check"; within one check interval they show OK.
4. Stop the service on target02 (for example `systemctl stop ssh` via the console): the
   chip goes **Critical** with the plugin's message. Restart it: OK again.
5. Pause Nagios (`systemctl stop nagios`) for more than 15 minutes: the chip reads
   **No recent data**. Restart it.

### PM-04: devices found later are attached automatically

1. With `check_ssh` enabled, add a new lab device that runs SSH and run discovery.
2. Its SSH service is created by that run, without any action in Plugin Manager; the
   drawer list and Monitoring count include it.

### PM-05: disabling removes the services

1. Disable `check_ssh`. The SSH services leave `hosts.cfg` and Nagios; the drawer list is
   empty or shows stopped ports only.
2. The ports keep their state (`MONITORED`) and frozen plugin (`ssh`).
3. Enable again: the same services return. ("Running since" restarts because the rows are
   recreated.) A history row exists for each action.

### PM-06: stop and resume one device

1. In the `check_ssh` drawer, **Stop monitoring** on one device. Its service leaves Nagios
   and the list row shows "Not monitored / Monitoring stopped for this device"; the other
   devices are unaffected. The port is `IGNORED`.
2. **Resume**: the service returns with its frozen plugin.
3. Log in as a user with only `plugin.enable`: Stop is not shown. With only
   `plugin.disable`: Resume is not shown.

### PM-07: Nagios rejects a disable

1. Make Nagios reject the next reload (see 6.2), then **Disable** an enabled plugin.
2. The route fails with "Nagios did not accept the change, so the plugin is still on".
   The plugin keeps its status, its services keep running, and a failed history row
   exists. Remove the sabotage; the same action then succeeds.

### PM-08: Nagios rejects an enable or a stop

1. With the same sabotage, **Enable** a plugin: the plugin is `Enabled`, the dialog's
   result says Nagios was not updated and why, and no rows or promotions were kept.
2. **Stop monitoring** one device: the route fails and the port is back to `MONITORED`.
3. Lift the sabotage and press Enable again: it attaches normally.

#### 6.2 Making Nagios reject a config

Pick one and undo it afterwards: point `NAGIOS_BIN` (in the app's environment) at a script
that exits 1 for `-v`; or add a deliberately invalid line to a copy of `hosts.cfg` only if
you can restore the live file immediately. Never leave the lab with a broken live config.

## 7. Port flags and the generic check

### MM-01: a service that is not what the table expects

1. Fixture: on target02 run a second sshd on port 80 (NCPA plan §4.1), with the Port →
   Service table expecting `http` on 80 (the default).
2. Discovery records port 80 as `ssh` (what nmap saw) with `Expected_Service_Name = http`,
   not monitored, even with `check_ssh` enabled.
3. `PUT /api/system/hosts/<id>/ports/tcp/80` with `{"acknowledge_mismatch": true}` makes it
   monitored as `ssh`; `Mismatch_Acknowledged_At` is set and a log entry names the
   expected and found services.
4. Make nmap see something else on 80 and rescan: the acknowledgement clears.
5. Do steps 2 and 3 from the device drawer: the Ports section lists port 80 under "Needs attention" with "Not used as intended: expected http, found ssh", and **Acknowledge and monitor** monitors it. Check the same from the API.

### GT-01: the generic TCP plugin

1. With `check_tcp` off, a port such as `9100 printer` stays suggested.
2. The preview for `check_tcp` counts it; enabling attaches it; Stop monitoring one such
   port and confirm it does not come back on the next discovery.
3. In the device drawer's Ports section use **Leave suggested** on a monitored port. It moves to
   "Needs attention" marked Held, stays Suggested after the next discovery and after disabling and
   enabling its plugin, and the enable preview reports it as held. **Monitor** releases it and it
   attaches. Repeat once with the API (`{"state": "SUGGESTED"}` then `{"state": "MONITORED"}`).

## 8. NCPA

### NC-01: deploying without `check_ncpa`

1. With `check_ncpa` not enabled, the NCPA Deployment page shows the amber notice with a
   link to Plugin Manager.
2. Deploy NCPA to target02. The agent installs, the NCPA port is `MONITORED`, but no
   `ncpa-*` service exists (the skipped-services log says `check_ncpa` is not enabled).
3. Enable `check_ncpa` (preview first): the CPU, memory and disk services appear and reach
   OK. The notice disappears.

### NC-02: the agent's port is protected

`POST .../services/stop` for the NCPA port of a deployed agent returns 409 "The NCPA port
cannot be removed while an NCPA token is deployed", and the port stays monitored.

## 9. Browser and scale

### UI-01: the Plugin Manager and NCPA pages in a browser

Check in both light and dark mode, at desktop width and a narrow window:

- there is no "Currently Running" tab and no "Apply to Device";
- the Monitoring column, the "no plugins enabled" banner (and that it does not flash
  before data loads) and the Not service-driven text;
- the enable dialog (counts, wording, Cancel, Confirm) and the notices after enable and
  disable (success, nothing matched, Nagios not updated);
- the services list in the drawer: status chips for each state, long service and host
  names wrap, search, paging, Stop and Resume;
- the NCPA notice;
- statuses do not refresh by themselves (G24): note whether that is acceptable;
- the device drawer's Ports section: groups and counts, the reason texts, the Nagios-not-updated notice, the
  confirmation dialogs, the Set service dialog (suggestions, "Checked by" line, warnings) and Remove pin, in light
  and dark mode and at a narrow width; the section is absent for `localhost`.

Attach screenshots of each state to the report.

### PF-01: scale on the lab network

Enable `check_tcp` on the full lab. Record the time the Enable request takes, the time to
open a plugin with the most services, and any slowness of the drawer list. The unit
benchmark (`test_plugin_scale.py`) puts 3,600 services at about half a second without
Nagios; the figure to watch here is Nagios' own validate and reload.

## 10. Cleanup

### CLEAN-03

1. Re-run PM-05 for every plugin enabled by this plan so the lab returns to opt-in.
2. Remove the throwaway fixtures (second sshd, listeners) and any sabotage from §6.2.
3. Confirm `localhost.cfg` still has the recorded hash and `nagios -v` passes.
4. If the lab database was upgraded, restore the pre-test copies of `system.db`,
   `history.db`, `hosts.cfg`, `nagios.cfg` and `plugin-services.cfg` before CLEAN-01.

## 11. Cleaning up `plugin-services.cfg` on an upgraded install (G19)

Older releases wrote the manual path's services to `plugin-services.cfg` and added a
`cfg_file=` line for it to `nagios.cfg`. Upgrading does not remove them: Nagios keeps
running those services, they are `MANUAL` rows with no screen to remove them, and the
Dashboard still recognises their `pinpoint_` commands. To clean up:

1. List them: the "Hand-made rows" query in §3.1, and `grep -c "define service"
   plugin-services.cfg`.
2. Decide per service whether it is still wanted. Most duplicate something discovery now
   monitors through an enabled plugin.
3. Back up `plugin-services.cfg` and `nagios.cfg`.
4. Remove the unwanted `define service` blocks (or the file and its `cfg_file=` line),
   run `nagios -v`, reload Nagios.
5. Delete the matching `PLUGIN_CONFIGURATION` rows where `Origin = 'MANUAL'`.
6. Confirm the Dashboard and the Plugin Manager counts.

Rehearse this in UPG-01 before running it on a production install.

## 12. Report

For each case record pass/fail, the evidence (query output, `nagios -v` output, screenshots)
and the gap it closes: G4 (live Nagios, real database copy, Linux `ip` parsing), G5
(UPG-02), G19 (§11), G23 (UI-01), G24 (UI-01 note), G25 (UPG-01 step 7, GT-01 step 3). Anything that
fails goes into the plan's gap register as a new row, not into a comment.
