# Custom Checks and NCPA Name Fix Acceptance Test Plan

**Status:** Draft for review
**Test level:** Live lab acceptance (manual)
**Code under test:** `fix/plugin-name-normalization` (PR #31) and `feature/custom-checks`, merged into one test build
**Design:** [`Custom_Checks_Plan.md`](../../../spec%20files/Custom_Checks_Plan.md),
[`Plugin_Driven_Monitoring_Plan.md`](../../../spec%20files/Plugin_Driven_Monitoring_Plan.md) (§2.2, §2.5, gap G27)
**Related plans:** [`PLUGIN_DRIVEN_MONITORING_ACCEPTANCE_TEST_PLAN.md`](PLUGIN_DRIVEN_MONITORING_ACCEPTANCE_TEST_PLAN.md)
(environment, accounts and fixtures are reused from it),
[`PLUGIN_DRIVEN_MONITORING_LAB_TEST_PLAN.md`](PLUGIN_DRIVEN_MONITORING_LAB_TEST_PLAN.md)
(§6.2 shows how to make Nagios reject a config)

## 1. Purpose

The unit tests (backend 2093 passed, client 439 passed) replace Nagios, SSH and the
browser. They prove the code does what it was written to do. This plan answers what they
cannot:

1. Does Nagios accept the generated config, run the checks, and report their results?
2. Can an administrator enable NCPA in Plugin Manager, and does it then really monitor the agent?
3. Do the new screens read correctly and behave safely in a browser?

A case passes only when the **observed result equals the expected result written here**. If it
does not, record a defect. Do not edit the expectation to match.

## 2. What is under test

| ID | Change | Branch |
|---|---|---|
| CH-1 | A plugin stored as `check_ncpa.py` matches the registry, so it can be enabled and disabled | `fix/plugin-name-normalization` |
| CH-2 | Seven port-driven plugins join the registry: `check_pgsql`, `check_ldap`, `check_ldaps`, `check_rpc`, `check_ircd`, `check_time`, `check_ntp_peer` | `feature/custom-checks` |
| CH-3 | Custom checks: an administrator runs a plugin that probes a device (`check_by_ssh`, `check_ups`, ...) against one chosen device | `feature/custom-checks` |
| CH-4 | The drawer says why other plugins take no custom check (server-local, host-level, needs a password) | `feature/custom-checks` |
| CH-5 | New `plugin.custom_check` permission and new database origin value | `feature/custom-checks` |

## 3. Environment and rules

- Use the isolated lab of the acceptance plan (§3, §3.1): `target01`, `target02`, the isolated
  `/28`. **Never scan the management network and never run these cases on production.**
- Credentials only from environment variables; never put passwords, tokens or keys in evidence.
- Build: merge both branches into a throwaway branch (for example `test/custom-checks-lab`),
  deploy it to the lab server, and record the commit hash with the results.
- Back up before starting: `system.db`, `history.db`, `hosts.cfg`, `nagios.cfg`, and
  `sha256sum localhost.cfg`. Keep `system.db` until the cleanup case.
- Accounts (acceptance plan §3): **Admin** (every permission), **Operator** (`plugin.view`,
  `system.hosts`, no `plugin.custom_check`), **Viewer** (no `plugin.view`).
- Record for every case: Pass, Fail or Blocked, the observed value, evidence (query output,
  `nagios -v` output, screenshot) and the defect ID on failure.

### 3.1 Fixtures

| Fixture | Setup | Used by |
|---|---|---|
| NCPA device | One lab host with NCPA deployed through the NCPA Deployment page (token stored, port 5693 listening) | N-01 .. N-08 |
| SSH target | `target01`, reachable over SSH by the Nagios server with the lab key at `$PINPOINT_TEST_SSH_KEY`; user `pinpoint-test` | C-02 .. C-09 |
| Second SSH host | `target02`, same key | C-10, C-11 |
| Port services | `target02`: a listener on tcp 6667 named `irc`, on tcp 111 named `rpcbind`, and on tcp 5432 named `postgresql` (a plain TCP listener is enough) | R-01 .. R-04 |
| No `python` | The Nagios server without a `python` command (as found) | N-05 |

Helper queries (Python `sqlite3` if the CLI is missing):

```sql
-- custom checks
select PluginConfigurationID, PluginID, NetDiscoveryID, Nagios_Service_Name, Service_Description,
       Origin, Status, Applied_At, Configuration_Data from PLUGIN_CONFIGURATION where Origin = 'CUSTOM';
-- plugin history
select Action, Result, Message from PLUGIN_HISTORY order by PluginHistoryID desc limit 5;
```

## 4. Order

| Stage | Cases | State |
|---|---|---|
| 0 | E-00 .. E-03 | build, upgrade of a copy of the real database |
| 1 | N-01 .. N-08 | NCPA, nothing else enabled |
| 2 | R-01 .. R-04 | new registry plugins |
| 3 | C-01 .. C-14 | custom checks |
| 4 | P-01 .. P-03 | permissions |
| 5 | U-01 | browser, light and dark |
| 6 | X-01 | cleanup |

## 5. Stage 0: build and upgrade

### E-00: the isolated suites still pass

`cd server && pytest tests/ -q`; `cd client && npm test && npm run build`.

| Expected | Backend: all pass except the known Windows-only `test_automation.py::TestSecurityCheck::test_flags_broken_plugins_and_logs_summary` (none on Linux). Client: 439 passed. Build succeeds |
|---|---|
| Fail if | Any other failure |

### E-01: upgrade a copy of the real database

1. Copy `system.db` and run `flask db upgrade` on the copy.

| Expected | Ends at revision `b4e8d1a7c629` with no error. Every existing `PLUGIN_CONFIGURATION` row keeps its `Origin` (`AUTO` or `MANUAL`). The `PLUGIN` table is unchanged |
|---|---|

### E-02: permission installed and granted

1. `flask sync-permissions`.

| Expected | Output lists `plugin.custom_check` as added and granted. Administrator holds it; Manager and Staff roles do not. Running it again reports nothing added |
|---|---|

### E-03: downgrade and upgrade again, on the copy

1. Add one custom check (after C-02), then `flask db downgrade -1`, then `flask db upgrade`.

| Expected | The downgrade deletes only the `CUSTOM` row; `AUTO` and `MANUAL` rows stay. The upgrade succeeds and the origin value is available again |
|---|---|

## 6. Stage 1: the NCPA fix (CH-1)

### N-01: the plugin is recognised

1. Plugin Manager → open `check_ncpa.py`.

| Expected | The drawer does **not** show "Not service-driven". It shows Enable and Disable buttons (Disable greyed until enabled), the category **Agents** and the description "Check metrics via NCPA (Nagios Cross-Platform Agent) API." The inventory row's Monitoring column shows `—`, not "Not service-driven" |
|---|---|
| Not a defect | Version `—` and the stored command still reading `check_ncpa.py -H $HOSTADDRESS$` on a database scanned before the fix: Nagios uses the registry's command, not the stored one (N-04) |

### N-02: enabling attaches the agent's checks

1. With an NCPA agent deployed on the NCPA device, click **Enable** and read the preview.
2. Confirm.

| Expected | The preview counts one device and the number of NCPA services (one per configured metric, e.g. cpu, memory and one per recorded partition). After confirming, status is **Enabled**, then **Active** once applied. `select ... where Origin='AUTO'` shows `ncpa-cpu-5693-tcp`, `ncpa-memory-5693-tcp`, `ncpa-disk_<partition>-5693-tcp` as `APPLIED`. The drawer's Monitored services list shows them with a status chip |
|---|---|

### N-03: the device ports card tells the truth

1. Open the NCPA device's drawer → Ports, before and after N-02.

| Expected | Before: `tcp/5693 ncpa` shows "check_ncpa is not enabled in Plugin Manager, so nothing is checking this port." with an **Enable check_ncpa** link. After: that sentence is gone; the card shows the port as Monitored with its services |
|---|---|

### N-04: Nagios accepts the config and runs the real file

1. `grep -n "check_ncpa" <hosts.cfg dir>/*.cfg` and `nagios -v nagios.cfg`.

| Expected | The command definition is `command_line $USER1$/check_ncpa.py -H $HOSTADDRESS$ -P '$ARG1$' -t '$ARG2$' -M '$ARG3$' $ARG4$` (the exact flag order follows the registry; the executable name ends in `.py`). `nagios -v` reports 0 errors. `/usr/local/nagios/libexec/check_ncpa.py` exists |
|---|---|
| Fail if | The command says `check_ncpa` without `.py` (Nagios would run a file that does not exist) |

### N-05: the plugin can run (the `python` shebang)

1. As the Nagios user, run the plugin by hand against the agent:
   `sudo -u nagios /usr/local/nagios/libexec/check_ncpa.py -H <agent ip> -P 5693 -t <token> -M cpu/percent`.

| Expected | A normal NCPA result (`OK: ...` with performance data), not `/usr/bin/env: 'python': No such file or directory`. The service in Nagios is OK, not UNKNOWN |
|---|---|
| If it fails with the shebang error | This is a server setup problem, not the code. Install a `python` command (or change the shebang to `python3`), record it as an environment finding, and repeat N-05 |

### N-06: disabling removes the checks

1. Click **Disable**.

| Expected | The `ncpa-*` services leave `hosts.cfg` and Nagios; the rows are deleted; status is **Disabled**. The ports card returns to "check_ncpa is not enabled…". The port itself is still Monitored (source NCPA), not demoted |
|---|---|

### N-07: Settings → Plugins sees the plugin

1. Settings → Plugins tab.

| Expected | The NCPA metrics table is editable and not marked "not installed". Saving a metric change rebuilds the config (with `check_ncpa` enabled, the service list changes accordingly) |
|---|---|

### N-08: no token still falls back to a plain check

1. On a device with port 5693 open but **no** deployed token, with `check_ncpa` and `check_tcp` enabled.

| Expected | The port is checked by the generic TCP service (`ncpa-5693-tcp` on `pinpoint_nd_tcp`), not by `check_ncpa` |
|---|---|

## 7. Stage 2: the new registry plugins (CH-2)

Enable one plugin at a time; run discovery or **Rescan** after enabling. Fixtures: §3.1.

### R-01: ports with nothing else needed

1. Enable `check_rpc`, then `check_ircd`, then `check_time` (each in turn).

| Expected | tcp/111 (`rpcbind`) becomes service `rpc-111-tcp` with command `pinpoint_nd_rpc!111!portmapper!`. tcp/6667 (`irc`) becomes `ircd-6667-tcp` with `pinpoint_nd_ircd!6667!`. A port named `time` on tcp/37 becomes `time-37-tcp`. Nagios runs each and reports a real state. `nagios -v` passes |
|---|---|

### R-02: postgres and ldap fall back without what they need

1. Enable `check_pgsql` and `check_ldap` and `check_tcp`.

| Expected | tcp/5432 (`postgresql`) and tcp/389 (`ldap`) are each monitored by the generic TCP service (`postgresql-5432-tcp` and `ldap-389-tcp` on `pinpoint_nd_tcp`), because no login name or search base is set. The reason text does not claim `check_pgsql` or `check_ldap` is checking them |
|---|---|
| With `check_tcp` off | Those ports stay Suggested with the reason "check_tcp is not enabled in Plugin Manager" |

### R-03: configured, they use their own plugin

1. Set the device's plugin variables (`system.db`, `NETWORK_DISCOVERY.Plugin_Variables`) to
   `{"pgsql": {"user": "nagios"}, "ldap": {"base": "dc=lab,dc=local"}}`, then apply (Rescan).

| Expected | `pgsql-5432-tcp` uses `pinpoint_nd_pgsql!5432!nagios!` and `ldap-389-tcp` uses `pinpoint_nd_ldap!389!dc=lab,dc=local!`. The plugins appear Active |
|---|---|

### R-04: ntp_peer is reached by choosing it

1. On a UDP 123 port, **Set service…** to `ntp_peer`; enable `check_ntp_peer`.

| Expected | The port becomes `ntp_peer-123-udp` (plugin `check_ntp_peer`). The Set service suggestions list `ntp_peer`. Without that choice, UDP 123 is still checked by `check_ntp_time` |
|---|---|

## 8. Stage 3: custom checks (CH-3, CH-4)

### C-01: each plugin class shows the right thing

Open each plugin in the drawer as Admin.

| Plugin | Expected in the drawer |
|---|---|
| `check_by_ssh`, `check_ups`, `check_clamd` | "Not service-driven. There is no port for discovery to attach this plugin to. Add a custom check to run it against a device." and a **Custom checks** section with **Add check**. No Enable button |
| `check_apt`, `check_uptime`, `check_sensors` | "Not service-driven. Runs on the Nagios server. Not available yet." No Custom checks section |
| `check_ping`, `check_icmp` | "Not service-driven. Checks the device itself rather than a port. Not available yet." |
| `check_radius`, `check_mysql_query`, `check_nt`, `check_disk_smb` | The Custom checks section; the password field is masked and the dialog carries an amber note about where passwords go |
| `check_dbi`, `check_oracle` | "Not service-driven. Its password cannot be passed to the plugin yet." No section |
| `check_load`, `check_disk` | "Checks the Nagios server itself through Nagios Core. Not managed here." |
| `check_ssh` | Enable and Disable buttons; no Custom checks section |

### W-01: a password is stored encrypted and is never shown

1. Set `PINPOINT_SECRETS_KEY` (or confirm `SECRET_KEY` is fixed in `/etc/pinpoint/pinpoint.env`) and restart. Open `check_radius` (or `check_mysql_query`) → **Add check**, device target01, a password `Lab-Pw_1`, and the other required fields.
2. Query the row: `select Configuration_Data from PLUGIN_CONFIGURATION where Origin='CUSTOM' order by 1 desc limit 1;`. Also open the list in the UI and `GET /api/plugin/<id>/custom-checks`.

| Expected | The stored JSON has `"secrets": {"password": "v1:..."}` and does not contain `Lab-Pw_1` anywhere. The list and the API show `-p ••••••` and `secrets_set: ["password"]`, never the password; the browser's network tab shows it only in the request that added it. The plugin history message and `journalctl -u pinpoint-gunicorn` do not contain it. The list shows no warning (`secrets_readable` true) |
|---|---|

### W-02: Nagios gets the password; the file is protected

1. `grep -n "pinpoint_custom_check_radius" hosts.cfg` and `ls -l hosts.cfg`; then check the Nagios web UI's service command view.

| Expected | The service command contains the password in plain text (this is how Nagios plugins work). `hosts.cfg` is not readable by users outside the Nagios user and group; if it is world-readable the Pinpoint log has "holds a custom check password and is readable by every user" (record it and run `chmod 640` with the right group). The check reaches a real state |
|---|---|

### W-03: change, keep, replace, remove

| Step | Expected |
|---|---|
| **Change** the check; leave the password blank; save | Saved; the check keeps working; the password field showed "Stored. Leave blank to keep it" |
| Type a new password; save | The new password is used (the command in `hosts.cfg` changes); the old one is gone from the file |
| `check_mysql_query` (password optional): tick "Remove the stored mysql password"; save | The password is removed and the check runs without `-p`; the list shows no stored password. For a required password there is no such option |
| Add a password containing `'` or `;` | Refused: the button is disabled and the API returns 400 naming the argument without echoing the value |

### W-04: the key changes

1. Change `SECRET_KEY` (or `PINPOINT_SECRETS_KEY`) and restart the service.

| Expected | The check is no longer in `hosts.cfg` after the next apply (Pinpoint logs a warning with no password). The drawer shows "A stored password can no longer be read, so this check is not running." Opening **Change** shows the same message; saving without typing the password is refused; typing it again restores the check |
|---|---|

### W-05: no fixed key, no passwords

1. Start the backend in debug mode with no `SECRET_KEY` and try to add a check that has a password.

| Expected | Refused: "Passwords cannot be stored because the server has no fixed SECRET_KEY…". Nothing is saved. A check without passwords is still accepted |
|---|---|

### C-02: add a check and watch it run (the key case)

1. `check_by_ssh` → **Add check**. Device: target01. Name: `Disk test`. Command: `/bin/true`.
   SSH user: `pinpoint-test`. Identity file: the lab key path on the Nagios server.
2. Click **Add check**.

| Expected | The dialog closes. The list shows **Disk test**, `target01 · <ip>`, arguments `-C /bin/true -l pinpoint-test -i <path>`, status **Waiting** with "Waiting for first check…". The database row: `Origin=CUSTOM`, `Status=APPLIED`, `Nagios_Service_Name=custom-by_ssh-disk_test`, `Port_Number` and `Protocol` empty, `Applied_At` set. Plugin history has a `Configure` / `Success` row "Added check 'Disk test' on <host>." |
|---|---|
| Config | `hosts.cfg` has a service `custom-by_ssh-disk_test` under target01 with `check_command pinpoint_custom_check_by_ssh!/bin/true!<flags>`, and one command `pinpoint_custom_check_by_ssh` with `command_line $USER1$/check_by_ssh -H $HOSTADDRESS$ -C '$ARG1$' $ARG2$`. `nagios -v` reports 0 errors |
| After ≤ 5 minutes | Status becomes **OK** (the remote command exits 0) and the service shows in Nagios and in Network Health |
| Fail if | Nagios rejects the config, the service never leaves Waiting, or the check shows on the wrong device |

### C-03: a failing remote command is reported honestly

1. Add a second check on target01: name `Always warns`, command `/bin/false`, same SSH arguments.

| Expected | After the next check the status is **Warning** (exit code 1) with the plugin's output. The first check is unaffected |
|---|---|

### C-04: names and arguments are validated

| Step | Expected |
|---|---|
| Add a check named `Disk test` again on target01 | Refused: "This device already has a check named 'Disk test'." Nothing saved |
| The same name on target02 | Accepted |
| Type `a'b` in Command | The **Add check** button is disabled; calling the API directly returns 400 "Variable 'command' contains a forbidden character." and the response does not contain the value |
| Leave Command empty | Disabled; the API returns 400 "'Command to run on the device' is required." |
| Send an argument the plugin does not have (API) | 400 "Unknown argument 'password'." |
| A name of 61 characters, or `no/slash` | Refused with the name rule's message |

### C-05: Nagios rejects the change

1. Make Nagios reject the next reload (lab plan §6.2), then add a check.

| Expected | The dialog stays open with "Nagios did not accept the change, so nothing was changed: …". No row was saved; `hosts.cfg` and the running Nagios are unchanged; plugin history has a `Configure` / `Failed` row. After removing the cause, the same request succeeds |
|---|---|
| Repeat for | **Pause**, **Remove** and **Change** while Nagios rejects: each returns the same message and leaves the check exactly as it was |

### C-06: change a check

1. **Change** `Disk test`: rename to `Disk test 2` and change Command to `/bin/false`.

| Expected | The dialog shows the device as text with "To check another device, remove this check and add a new one." (no device picker). After saving, the service name becomes `custom-by_ssh-disk_test_2`, the old service is gone from Nagios, and the new one runs (Warning after the next check). History records "Changed check 'Disk test 2'." |
|---|---|

### C-07: pause and resume

1. **Pause** `Always warns`, check Nagios and the database; then **Resume**.

| Expected | After Pause: status chip "Paused", text "Paused. Nothing is checking this."; the service is gone from `hosts.cfg` and Nagios; the row stays (`Configuration_Data` has `"paused": true`). Pausing again changes nothing. After Resume: the service is back, status Waiting then a real state, "Running since" is the original time |
|---|---|

### C-08: remove

1. **Remove** `Always warns` and confirm; then click Remove again on another check and **cancel** the confirmation.

| Expected | The first: the row, the service and the command line (if it was the plugin's last check) leave `hosts.cfg`; history records the removal. The cancelled one: nothing happens |
|---|---|

### C-09: the check survives discovery and reconcile

1. Run **Rescan**. Then enable and disable `check_ssh`. Then edit a port on target01.

| Expected | The custom checks are untouched by each of these: same rows, same services in `hosts.cfg`, no duplicate. The reconciler never lists or deletes a `CUSTOM` row |
|---|---|

### C-10: two devices, same check name

1. Add `Disk test` on target02 as well (C-04).

| Expected | Both appear in the list, sorted by device then name; search "target02" filters to one; per page is 5 and the page counter reads "Page 1 of N · M checks" |
|---|---|

### C-11: merging devices

1. Give target01 checks `A` and `B`, and target02 a check `B`. Merge target01 into target02 (device screen).

| Expected | After the merge target02 has `A` and `B` once each (the target's own `B` wins, the source's `B` is dropped). The source is Merged. `hosts.cfg` has no service for the merged host and each service once on target02. No error and no duplicate service name |
|---|---|

### C-12: retire a device that has a check

1. Retire a device that has a custom check.

| Expected (as built) | The device leaves `hosts.cfg`, so its custom services leave Nagios. The check stays listed in the plugin drawer with status Waiting and is not removed. If the device is brought back, the check returns |
|---|---|
| Note | `Custom_Checks_Plan.md` §2.5 says checks follow the retire rules, but the code only removes services (it does not delete the row). If the owner wants the row removed on retire, record this as a defect against the plan |

### C-13: where the result shows

1. Open Network Health and the Dashboard after C-02.

| Expected | The service appears under its plugin group as **BY_SSH** (the plugin name without `check_`, uppercased, as other plugins are grouped), with its host and state. It does not show as a port service. Alerts: a Critical custom service raises an alert like any service |
|---|---|

### C-14: inventory coverage

1. Plugin Manager inventory.

| Expected | `check_by_ssh`'s Monitoring column reads `N services on M devices` (it was "Not service-driven" before the first check). After removing every check it goes back to "Not service-driven". The Plugin Details drawer's "Monitoring usage" line matches |
|---|---|

## 9. Stage 4: permissions (CH-5)

### P-01: Operator

1. Sign in as Operator and open `check_by_ssh`.

| Expected | The drawer shows "Not service-driven…" and **no** Custom checks section, no Add check. Calling `GET /api/plugin/<id>/custom-checks` and `POST` returns 403 "User has no permission." The plugin inventory still lists the plugin and its Monitoring count |
|---|---|

### P-02: Viewer

| Expected | Plugin Manager is not reachable (as today). The custom check routes return 403 |
|---|---|

### P-03: granting by role

1. As Admin grant `plugin.custom_check` to the Operator role and have Operator reload.

| Expected | The section and Add check appear, and an Operator can add and remove a check. Revoking it removes them again. Neither change touches `plugin.enable` or `plugin.disable` behaviour |
|---|---|

## 10. Stage 5: browser

### U-01: the new screens, light and dark, desktop and narrow

| Check | Expected |
|---|---|
| Custom checks section | Header, search box and **Add check** fit without overlap at 1280 px and at about 400 px; check cards wrap; the three buttons (Change, Pause/Resume, Remove) wrap instead of overflowing |
| Dialog | Centered, scrolls when taller than the window, the device list scrolls; text is readable in both themes; Escape is not required to work (Cancel closes it) |
| Status chips | OK green, Warning amber, Critical red, Waiting blue, Paused grey; the same colors in the services list |
| `check_by_ssh` warning | The amber note about running a command over SSH shows in the dialog for `check_by_ssh` only |
| Focus and keyboard | The first field is focused when the dialog opens; Tab reaches every control; **Add check** has the first problem as its tooltip while disabled |
| Empty and error states | "No checks yet. Add one to run this plugin against a device."; a failed list load shows a red message and does not break the drawer |

## 11. Cleanup

### X-01

1. Remove the test checks and restore the backups.

| Expected | `nagios -v` passes; `sha256sum localhost.cfg` equals the value recorded at the start (this feature never touches it); no `CUSTOM` row remains; Plugin Manager is back to its starting state |
|---|---|

## 12. Traceability

| Change | Cases |
|---|---|
| CH-1 (`check_ncpa.py` name) | N-01 .. N-08 |
| CH-2 (seven registry plugins) | R-01 .. R-04 |
| CH-3 (custom checks) | C-02 .. C-14, E-03 |
| CH-4 (why a plugin takes none) | C-01, U-01 |
| CH-5 (permission, migration) | E-01 .. E-03, P-01 .. P-03 |
| Plan gaps and open points | C-12 (retire), N-05 (python on the server) |

## 13. Defect log

| ID | Case | Observed | Expected | Severity | Status |
|---|---|---|---|---|---|
| | | | | | |

## 14. Exit criteria

- Every case is Pass, or Fail with a defect logged and triaged, or Blocked with a reason.
- C-02 and N-04 both pass: Nagios accepts and runs what the code generates. These two are
  the reason this plan exists; if either fails, the feature does not ship.
- No case changed `localhost.cfg` (X-01).
