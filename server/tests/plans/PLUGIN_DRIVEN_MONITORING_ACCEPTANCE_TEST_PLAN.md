# Plugin-Driven Monitoring Acceptance Test Plan

**Status:** Draft for review
**Test level:** Live lab acceptance (manual, with the automated e2e harness where it still applies)
**Code under test:** branch `feature/plugin-driven-monitoring`
**Design:** [`Plugin_Driven_Monitoring_Plan.md`](../../../docs/plans/Plugin_Driven_Monitoring_Plan.md),
[`Device_Inventory_Requirements.md`](../../../spec%20files/Device_Inventory_Requirements.md)
**Related plans:** [`PLUGIN_DRIVEN_MONITORING_LAB_TEST_PLAN.md`](PLUGIN_DRIVEN_MONITORING_LAB_TEST_PLAN.md)
(mechanics: upgrade, Nagios rejection, `localhost.cfg`, browser),
[`NETWORK_DISCOVERY_EXTENDED_TEST_PLAN.md`](NETWORK_DISCOVERY_EXTENDED_TEST_PLAN.md),
[`NCPA_PORTS_AND_SERVICE_IDENTIFICATION_LAB_TEST_PLAN.md`](NCPA_PORTS_AND_SERVICE_IDENTIFICATION_LAB_TEST_PLAN.md)

## 1. Purpose

The unit tests (1892 backend, 383 client) prove the code does what it was written to
do, with Nagios, nmap and the browser replaced. This plan answers three different
questions on a real lab:

1. **Functional.** Does each feature work end to end against a real Nagios, real hosts and a browser?
2. **Logical.** Are the rules sensible when a person uses them? Does each reason text tell the truth,
   does each action do what its label says, and are the safe choices the default?
3. **Purpose.** Does the system do what it is for (§2), including when things go wrong?

A case passes only when the **observed result equals the expected result written here**.
If it does not, record a defect. Do not edit the expectation to match.

This plan does not repeat the mechanics cases of the lab plan. Where a case there already
proves a point, §10 says which one to run instead. This plan adds the cases that judge
the *logic* and the *objectives*, the ports UI, permissions, and the end-to-end journeys.

## 2. Objectives under test

Taken from the plan's problem statement (§1) and the Device Inventory requirements.

| ID | Objective | The system must... |
|---|---|---|
| O-1 | Catalog is independent | Record every service and port a scan finds, whether or not any plugin is on |
| O-2 | Opt-in monitoring | Monitor nothing port-based until an admin enables a plugin that can check it |
| O-3 | No manual device picking | Attach devices automatically on enable and when found later; allow excluding one device |
| O-4 | One inventory | Show one Plugin Manager list with each plugin's services, status and "running since" in its details |
| O-5 | Descriptions | Show a real description for each plugin |
| O-6 | Server stats stay in Nagios Core | Leave `localhost.cfg` and the server's own checks untouched |
| O-7 | Safe by default | Never start monitoring something the admin did not allow: guesses, mismatches, held ports and upgrades start nothing |
| O-8 | Honest | Say why a port is or is not monitored, and say so when Nagios was not updated |
| O-9 | Reversible and safe to fail | A change Nagios rejects leaves the running system as it was |
| O-10 | Admin control | Let an admin monitor, ignore, stop, hold, resume, rename and unpin a port from the device screen, with the right permission |

## 3. Environment and rules

- Use the existing isolated lab (Extended plan §4 and §8.3): `target01` (standard ports),
  `target02` (fixtures), the isolated `/28`. **Never scan the management network.**
- Credentials only from environment variables. Never put passwords, tokens or keys in
  evidence or the report.
- Back up `system.db`, `history.db`, `hosts.cfg`, `nagios.cfg`, `plugin-services.cfg`
  and `sha256sum localhost.cfg` before starting (lab plan §3).
- Use Python's `sqlite3` if the CLI is missing. Helper queries are in lab plan §3.1.
- Three accounts: **Admin** (all permissions), **Operator** (`system.hosts` view and edit, `plugin.view`,
  no `plugin.enable`), **Viewer** (`system.hosts` view only, no `plugin.view`).
- Record for every case: result (Pass/Fail/Blocked), the observed value, evidence
  (query output, `nagios -v` output, screenshot), and the defect ID on failure.

### 3.0 Lab credentials

`PINPOINT_TEST_SSH_KEY` in `lab.env` must point to the dedicated test key under `.cache/pinpoint-live-test-access/` (`test_key`), not to `pinpoint_ncpa_deploy`, which the `pinpoint-test` guest account rejects. Confirm with `ssh -i "$PINPOINT_TEST_SSH_KEY" pinpoint-test@10.0.2.2 true` before E-01 (see `e2e/network_discovery/README.md`).

### 3.1 Fixtures

| Fixture | Host | Setup | Used by |
|---|---|---|---|
| Standard | target01 | sshd 22, nginx 80/443, DNS 53 tcp+udp, NTP 123/udp, SNMP 161/udp | most cases |
| Odd port | target02 | listener on tcp 9100 that does not speak a known protocol | A-03, A-04 |
| Mismatch | target02 | sshd also on tcp 80 (NCPA plan §4.1) | L-03 |
| Pinned | target02 | nginx also on tcp 8080 | L-06 |
| Fails on demand | target01 | `systemctl stop ssh` / `start ssh` | F-03 |
| Second host | target02 | second SSH host so "devices" count is 2 | F-04 |

## 4. Order

| Stage | Cases | State |
|---|---|---|
| 0 | E-00 (regression gate), E-01 (upgrade), E-02 (clean install) | copy of real DB, then clean install |
| 1 | O-01 .. O-04 | fixtures up, nothing enabled |
| 2 | F-01 .. F-06 | `check_ssh`, `check_http` |
| 3 | L-01 .. L-08 | ports logic on target02 |
| 4 | P-01 .. P-06 | permissions |
| 5 | R-01 .. R-04 | failure injection |
| 6 | J-01, J-02 | journeys |
| 7 | U-01 | browser, light and dark |
| 8 | X-01 | cleanup |

## 5. Stage 0: regression gate and installs

### E-00: the isolated suite still passes (run first, on the lab server)

`cd server && pytest tests/ -q` and `cd client && npm test && npm run build`.

| Expected | Backend 1892 passed, 23 skipped; 1 known failure `test_automation.py::TestSecurityCheck::test_flags_broken_plugins_and_logs_summary` on Windows only (G9), none on Linux. Client 383 passed. Build succeeds |
|---|---|
| Fail if | Any other failure, or a count below the above without a recorded reason |

### E-01: upgrade a copy of the real database

Run **lab plan UPG-01 and UPG-02** unchanged. Added expectations for the *logic*:

| Step | Expected |
|---|---|
| After upgrade, open Plugin Manager | Every plugin that backed a monitored port is Enabled/Active; no other plugin changed |
| Open Dashboard before and after | Same host and service counts |
| Run discovery once | No service disappears from Nagios; no port moves from Suggested to Monitored; held ports are listed to the owner |
| Open a held port in the drawer | It sits under **Needs attention** marked **Held** with the text "Held back: left Suggested on purpose, or at an upgrade..." |

### E-02: clean install starts opt-in

Run **lab plan BOOT-02**. Expected: no network service in Nagios other than stock
`localhost`; Plugin Manager shows "No plugins enabled, so no network services are monitored".

## 6. Stage 1: objectives O-1, O-2, O-5, O-6

### O-01: the catalog fills with nothing enabled (O-1, O-2)

1. With every plugin off, run discovery on the lab.
2. Open the device drawer for web-01 (target01).

| Expected | Ports are listed with their services (ssh 22, http 80, https 443, dns, ntp, snmp). Nothing is in the Monitored group. Each Suggested row says "check_x is not enabled in Plugin Manager." `hosts.cfg` has no service for target01. `nagios -v` passes |
|---|---|
| Why it matters | The catalog exists without monitoring (O-1); nothing is monitored until a plugin is on (O-2) |

### O-02: only what a plugin can check is monitored (O-2)

1. Enable `check_ssh` only (confirm in the dialog).

| Expected | Only SSH services are created (`ssh-22-tcp` on each host with SSH). http, dns, snmp stay Suggested with "check_http is not enabled..." etc. The enable dialog counts equal the services created (lab plan PM-02) |
|---|---|

### O-03: descriptions (O-5)

Open every plugin in the inventory, one by one.

| Expected | Each shows a description of what it checks. None shows "No description available." (A plugin the scanner cannot describe is listed as a defect, not a pass) |
|---|---|

### O-04: server stats are untouched (O-6)

Run **lab plan LCL-01**. Expected: identical `localhost.cfg` hash; Dashboard server statistics still update;
`check_load`, `check_disk`, `check_swap`, `check_procs`, `check_users` show "Not service-driven" with the "Not managed here" text and cannot be enabled (409).

## 7. Stage 2: functional behavior

### F-01: enable attaches automatically, no device picking (O-3)

1. With `check_ssh` and `check_http` off, count `hosts.cfg` services for target01. Enable `check_http`.

| Expected | No device chooser appears anywhere. The dialog shows "Enabling will monitor N services on M devices". After Confirm, the Monitoring column reads "N services on M devices". Each HTTP/HTTPS port has a service. Within one check interval each shows OK |
|---|---|

### F-02: the services list is complete and correct (O-4)

Open `check_http` details.

| Expected | The list shows, per service: name, device, IP, status chip, plugin output, "Running since". Number of rows equals the Monitoring count. Search by host and by IP filters correctly. Paging works at more than one page. The status text equals the Nagios web UI for the same service |
|---|---|

### F-03: statuses are real (O-4, O-8)

1. Stop sshd on target01 (`systemctl stop ssh`) with `check_ssh` on. Then start it.
2. Enable a new plugin and look at its services at once.
3. Stop Nagios for 16 minutes.

| Step | Expected |
|---|---|
| 1 | Chip goes **Critical** with the plugin message ("Connection refused"); back to **OK** after start |
| 2 | New services show **Waiting** with "Waiting for first check", then OK |
| 3 | Chip reads **No recent data**; after Nagios restarts it recovers |

### F-04: devices found later attach by themselves (O-3)

Add a second SSH host (target02) with `check_ssh` already on, run discovery.

| Expected | Its SSH service exists after that run, with no action in Plugin Manager. The Monitoring count rises by one device |
|---|---|

### F-05: disable removes, enable restores (O-9)

1. Disable `check_ssh`. 2. Look at Nagios and the ports. 3. Enable it again.

| Expected | 1-2: SSH services leave `hosts.cfg` and Nagios; ports keep state Monitored and their plugin name; history has a row. 3: the same services return; "Running since" restarts |
|---|---|

### F-06: exclude one device and bring it back (O-3, O-10)

Stop monitoring one device from the `check_ssh` details, then resume it.

| Expected | Stop: that service leaves Nagios, the row says "Monitoring stopped for this device", others unaffected, the port is Stopped in the device drawer. Resume: it returns. A later discovery does **not** re-attach it while stopped |
|---|---|

## 8. Stage 3: the logic makes sense

These cases judge whether the rules are right, not only whether they run.

### L-01: guesses never start monitoring (O-7)

On target02 a listener on tcp 9100 that is not identified.

| Expected | Listed Suggested, marked **Guess**, text "Only guessed from the port number, so it is not monitored automatically." Enabling `check_tcp` does **not** attach it |
|---|---|
| Reasoning | An admin enabling a generic plugin must not monitor things the system merely suspects |

### L-02: identified ports get the generic check only if enabled (O-2, O-7)

Add a service the scanner identifies but no specific plugin covers. Enable `check_tcp`.

| Expected | The preview counts it. After confirm it is Monitored by `check_tcp (generic TCP check)`. With `check_tcp` off it stays Suggested with the plugin-not-enabled reason |
|---|---|

### L-03: a port not used as intended is flagged, not named (O-7, O-8)

Mismatch fixture: sshd on tcp 80 while the table expects http.

| Expected | Port 80 is recorded as **ssh** (what was seen), not monitored even with `check_ssh` on. It sits under Needs attention as **Not used as intended**, "found ssh, expected http". The action is **Acknowledge and monitor** (there is no separate Monitor). After acknowledging: Monitored by `check_ssh`, a log entry names expected and found. The system never labels it SSH just because of the number 22 or similar |
|---|---|

### L-04: acknowledgement is not permanent (O-7)

After L-03, change what is on port 80 (run nginx instead), rescan.

| Expected | The acknowledgement clears. A monitored port keeps its service and frozen plugin, so its Nagios service does not change, and a `SERVICE_CHANGED` review item is raised for the new service (Data Model spec, "monitored port keeps its service"). If what is found differs from the table again, the port is flagged again |
|---|---|

### L-05: the admin's "no" sticks (O-7, O-10)

1. **Leave suggested** on a monitored port.
2. Run discovery. 3. Disable and enable its plugin. 4. Open the enable preview.

| Expected | 1: confirmation text "...no plugin will monitor it again until you do." The service leaves Nagios; the port is Suggested and **Held** under Needs attention. 2-3: it stays Suggested. 4: the preview reports it as held and the hint "Monitor them from each device's Ports list." shows. **Monitor** releases it and it attaches |
|---|---|
| Reasoning | An explicit admin decision must beat automatic promotion everywhere |

### L-06: pin a service and remove the pin (O-10)

On port 8080 (nginx, scanned as http).

| Step | Expected |
|---|---|
| Set service `ssh` | The dialog's "Checked by" reads `check_ssh`; saving marks the row **Pinned**. If it was monitored, the warning says its Nagios service will be renamed, and after saving the service is renamed (history stays under the old name) |
| Rescan | The pinned service is **not** changed by the scan |
| `SSH` | Accepted and saved as `ssh` (names are lowercased), in the dialog, the port route and Settings |
| Invalid names (`a b`, 33 characters, empty) | Save disabled, message "Use letters, digits..." |
| UDP port with a name no plugin speaks | "Checked by: Skipped: no check exists for this UDP service" |
| Remove pin on a monitored port | Confirmation says the Nagios service is not changed; a later scan that sees a different service keeps the current one and records a review item |
| Remove pin on a non-monitored port | The service returns to what the last scan saw |

### L-07: UDP is never checked by a TCP check (O-7)

Enable `check_tcp`. Look at DNS 53/udp, NTP 123/udp, SNMP 161/udp, and an unidentified UDP port.

| Expected | No UDP port gets `check_tcp`. DNS/NTP/SNMP attach only when `check_dns`/`check_ntp_time`/`check_snmp` is on. An unidentified UDP port reads "No plugin can check this UDP service." |
|---|---|

### L-08: ports that go away, come back and are archived (O-8)

Close a monitored port on a target, rescan until the missing threshold (Extended plan ND-11).

| Expected | Port shows **Missing** with "not seen lately" and stays monitored, then is Archived after the terminal threshold (collapsed group "Archived (n)", no actions). Re-opening a missing port returns it to Monitored without a duplicate service |
|---|---|

## 9. Stage 4: permissions (O-10)

| ID | Account | Action | Expected |
|---|---|---|---|
| P-01 | Viewer | Open a device drawer | No Ports section (needs `system.hosts`) or, if shown, only "You can view ports but not change them." and no action buttons |
| P-02 | Operator without `system.hosts.edit` | Open Ports | Ports and reasons visible; no buttons; the view-only note |
| P-03 | Operator with edit, no `plugin.view` | Reason "check_ssh is not enabled" | Shown as plain text; no "Enable check_ssh" link |
| P-04 | Operator with edit | Call `PUT /api/system/hosts/<id>/ports/tcp/22` | 200; with edit removed the same call is 403 |
| P-05 | Account with only `plugin.enable` | Open a plugin | Stop monitoring not shown; the stop route returns 403 |
| P-06 | Account with only `plugin.disable` | Open a stopped service | Resume not shown; the route returns 403 |

## 10. Stage 5: failure and safety (O-8, O-9)

Make Nagios reject a config as in lab plan §6.2. Always undo it.

### R-01: a rejected change is saved honestly (O-8)

With the sabotage on, **Stop monitoring** a port from the device drawer.

| Expected | The port is saved as Stopped, and the screen shows "The change was saved but Nagios was not updated: ..." with Nagios' reason. After lifting the sabotage, one action (or the next discovery) brings Nagios in line |
|---|---|

### R-02, R-03: rejected enable and disable

Run **lab plan PM-07 and PM-08**. Expected there: disable fails (502 from the pre-check) and the plugin stays on, with a FAILED history row and the live config untouched; stop restores the port to Monitored (409).

Enable depends on what Nagios rejects. If the generated services alone are rejected, the plugin is still Enabled, `auto_apply.success` is false with the reason, no rows are kept, the live config is untouched, and a retry attaches once the config is valid. This is not a blanket `nagios -v` failure.

### R-04: the agent's port is protected (O-9)

Run **lab plan NC-02**. Expected: 409 "The NCPA port cannot be removed while an NCPA token is deployed". The drawer offers no actions on that port and says "Managed by NCPA deployment".

## 11. Stage 6: journeys that show the purpose (all objectives)

### J-01: a new administrator turns monitoring on safely

1. Fresh install (E-02). Open Plugin Manager: the banner explains nothing is monitored.
2. Enable `check_ssh`, `check_http`. Read each preview before confirming.
3. Open a device. Find one thing that needs attention and resolve it.
4. Stop one device from a plugin.

| Expected | Each step is possible without reading documentation: the banner points to what to do, previews match results, reasons name the fix, every destructive action asks first with a clear sentence. At the end Nagios shows exactly the services the admin enabled and nothing else |
|---|---|

### J-02: a month in the life (upgrade path)

On the upgraded copy (E-01): enable one new plugin, release one held port, pin one service, disable one plugin, run two discoveries.

| Expected | No surprise service appears or disappears at any point. Every change is traceable in plugin history or the port log. `nagios -v` passes after each step. Dashboard totals equal Nagios' own counts |
|---|---|

## 12. Stage 7: UI

### U-01: the screens in a browser

Run **lab plan UI-01** (Plugin Manager, NCPA, and the device Ports section; light and dark; narrow window). A clickable reference for the intended appearance is the preview artifact built for this work.

Additional expectations:

| Check | Expected |
|---|---|
| Ports section absent for `localhost` and for hosts with no `device_id` | Not rendered |
| A long service or host name | Wraps; no horizontal scroll of the drawer |
| Keyboard | Every action reachable by Tab; dialogs close on Escape and return focus; Confirm is focused by default |
| Busy | Only the affected port's buttons are disabled while a change is saved |
| Reload | After an action the list refreshes without flicker and the open group keeps its place |

## 13. Cleanup

### X-01

Run **lab plan CLEAN-03, then Extended plan CLEAN-01**. Expected: every plugin enabled by this plan is disabled; fixtures and sabotage removed; `localhost.cfg` hash matches; `nagios -v` passes; databases restored if upgraded.

## 14. Other tests to run from `server/tests/e2e`

The automated harness is [`../e2e/network_discovery/`](../e2e/network_discovery/README.md).
It is opt-in and needs the lab configuration. Use it to produce evidence, not to replace the
cases above.

| Harness part | Run for | Notes |
|---|---|---|
| `provision/detect_backend.py`, `vm_scripts/provision_lab.py verify` | Lab readiness (ENV-01..03) | Must succeed before any discovery |
| `runner/run_tests.py discover` (with `config/plugin-cases.example.json`) | ND-01 .. ND-13, CFG-01 .. CFG-04, MON-01 .. MON-04 | Gives the repeatable discovery, config apply and stop/restore evidence behind O-1, O-2, F-03, R-01 |
| `runner/run_tests.py service-case --case-id <ID>` | MON-03 / MON-04 per plugin (stop and restore a service) | **Stale for this branch:** `runner/pinpoint.py` `apply_monitoring` calls `/api/plugin/targets`, `/configurations` and `/running`, which no longer exist. Cases with `apply_monitoring: true` fail. Use enable-only cases (omit that flag); monitoring now follows from enabling |
| `harness_tests.py`, `vm_scripts/self_tests.py` | Harness safety checks | Run before live actions |
| `cleanup/restore_lab.py` | X-01 | Idempotent recovery |
| `../integration/test_live_nagios.py` | Dashboard/alerts read live Nagios (MON-02 evidence) | Skips itself if Nagios is unreachable; a skip is not a pass |

### 14.1 Gaps in the e2e directory

**Status:** all rows except the browser runner are implemented in the harness (self-tests pass; not yet run live end to end). See the README's "Plugin-driven monitoring runs" and the [adjustment plan](PLUGIN_DRIVEN_MONITORING_HARNESS_ADJUSTMENT_PLAN.md). The `service-case` stale-flow note above no longer applies.

| Needed test | Why | Proposed home |
|---|---|---|
| Update the harness for plugin-driven monitoring: after enabling, wait for `GET /api/plugin/<id>/services` to list the service and reach OK, then stop and restore the remote unit | Replaces the removed apply flow; automates F-01, F-03 | `runner/pinpoint.py`, `runner/run_tests.py` |
| Enable-preview equals result check (counts vs `PLUGIN_CONFIGURATION` and `hosts.cfg`) | Automates O-02, F-01 | new `runner/` check |
| `localhost.cfg` hash guard before and after a whole run | Automates O-04 | `runner/nagios.py` |
| Port-flag scenario: mismatch fixture, acknowledge via API, assert state | Automates L-03/L-04 | `services/` fixture plus `runner/` case |
| Held-port scenario: Leave suggested via API, discovery, disable/enable, assert still Suggested | Automates L-05 | `runner/` case |
| Rejected-config scenario using a failing `NAGIOS_BIN` | Automates R-01..R-03 | `runner/nagios.py` |
| Browser-driven check of the drawer and Plugin Manager (the "deterministic browser-to-Nagios" runner) | Automates U-01; already proposed | [`TEST_APPROACH_ADJUSTMENT_PLAN.md`](TEST_APPROACH_ADJUSTMENT_PLAN.md) |
| Permission matrix via three real sessions | Automates P-01..P-06 | `runner/pinpoint.py` |

## 15. Superseded cases

The Extended plan's **PM-01 .. PM-05** describe "Enable then apply a plugin", "Apply to multiple targets"
and "Reapply the same target". That flow was removed. Replace them with F-01, F-05, F-06 and R-02/R-03
of this plan when running the Extended plan. Update the Extended plan's table when this plan is approved.

## 16. Pass rules and report

- **Release pass:** every case Pass, or Fail/Blocked with a recorded, accepted defect. Cases E-00, O-01, O-02, O-04, L-03, L-05, R-01 and J-02 are **blocking**: any failure stops the merge.
- Map results to the gap register: G4 (E-01, R-02), G5 (E-01), G19 (lab plan §11), G23 and G24 (U-01), G25 (E-01, L-05).
- Each failure becomes a new row in the plan's §13 register, not a comment.
- The report lists, for every objective O-1 .. O-10, the cases that cover it and their results. An objective with no passing case is **not met**.

### 16.1 Traceability

| Objective | Cases |
|---|---|
| O-1 | O-01, L-08 |
| O-2 | E-02, O-01, O-02, L-02, L-07 |
| O-3 | F-01, F-04, F-06 |
| O-4 | F-02, F-03 |
| O-5 | O-03 |
| O-6 | O-04 |
| O-7 | E-01, L-01, L-02, L-03, L-04, L-05, L-07 |
| O-8 | F-03, L-03, L-08, R-01 |
| O-9 | F-05, R-01 .. R-04 |
| O-10 | F-06, L-05, L-06, P-01 .. P-06 |

## 17. Coverage of phases 0 to 6

Phase list from the plan's §7. **Covered** = the cases above prove it on the lab. **Partial** = only some of it.
**Not covered** = no case above; the cases in §18 close it.

| Phase | Change | Covered by | Status |
|---|---|---|---|
| 0 Confirm | Assumptions about Nagios, `check-host-alive`, command layout | Implied by F-01, O-04 | Partial: C-00 |
| 1 Descriptions | Scanner fills descriptions; fallback text | O-03 | Partial: C-01 (fallback, rescan) |
| 2 Data model | `PLUGIN_CONFIGURATION` columns, AUTO/MANUAL origin, one row per device and service, upgrade and downgrade | E-01 (lab UPG-01) | Partial: C-02, C-03 |
| 2b Port → Service map | One merged Settings table; resolved-plugin column; validation; `NCPA_PORT` entry follows the NCPA port; `AUTO_MONITOR_SERVICES` retired; the monitoring server's own addresses excluded; D2 promotion rule; "not used as intended" | L-03, L-04, L-07 | Partial: C-04 .. C-07 |
| 3 Reconciler and gating | Plugin off means skipped and recorded; multi-metric expansion; nothing for the monitoring server; idempotent; correct command layout | F-01, F-05 | Partial: C-08 .. C-11 |
| 4 Enable/disable and API | Preview; disable rolls back; stop/resume; non-service-driven rejected; manual and running routes removed; `plugin.configure` retired; history | F-01, F-05, F-06, R-02, R-03 | Partial: C-12 .. C-14 |
| 5 Frontend | No Running tab or Apply; Monitoring column; banner; services list; NCPA notice | U-01 (lab UI-01), F-02 | Partial: C-15 (NCPA notice, tab removal) |
| 6 Specs and verification | `check_ping` and host RTA/PL (G13/G21); promotion hold (G25); `plugin-services.cfg` (G19); scale; rehearsal | L-05, E-01 | Partial: C-16 .. C-19 |
| Ports UI (after 6) | Device drawer Ports section | L-01 .. L-08, P-01 .. P-06, U-01 | Covered |

## 18. Added cases to cover phases 0 to 6

Run these in the stage shown. Each has the steps and the expected output.

| ID | Phase | Stage | Test | Expected output |
|---|---|---|---|---|
| C-00 | 0 | 1 | Check what the design relies on. (a) `grep -A3 "command_name.*check-host-alive"` in `commands.cfg`. (b) Enable `check_ssh`, run `nagios -v`. (c) count unfilled placeholders in generated services only: `awk '/^define service/,/^}/' hosts.cfg | grep -c 'ARG[0-9]\$'` (a plain `grep -c` also counts the 3 command templates) | (a) `command_line` runs `check_ping`. (b) `nagios -v` ends "Things look okay". (c) 0 unfilled `$ARGn$` placeholders inside `define service` blocks |
| C-01 | 1 | 1 | Run a plugin scan on a directory with a plugin the catalog does not know (drop a dummy executable). Open it. Edit nothing, rescan | It is listed with a fallback description, not "No description available." or an error. Known plugins keep their catalog description. A rescan does not blank or change either |
| C-02 | 2 | 0 | Run discovery twice without changing the lab. Query the AUTO rows (lab plan §3.1) before and after | Same row count; no duplicate (device, service) pair; `Applied_At` is not re-stamped on unchanged rows; Nagios is not reloaded for the second run |
| C-03 | 2, 4 | 0 | On the upgraded copy with MANUAL rows: enable and disable a plugin, run discovery | MANUAL rows are unchanged and still shown by the query; their `plugin-services.cfg` services keep running; no AUTO row duplicates a MANUAL service name without Nagios reporting it (`nagios -v` has no duplicate-service error) |
| C-04 | 2b | 1 | Open Settings. Find the Port → Service table. Add `tcp 9101 = printer`; add `udp 5353 = mdns`. Try `tcp 70000`, `tcp 22 = SSH`, a name of 33 characters, a duplicate port. Edit while a scan is running (DS-03) | One merged table (no second "always treat port as" table). Each row shows the resolved plugin (or "none"/"generic TCP"). Valid rows save and are used by the next scan. The four bad inputs are rejected with a message and nothing is saved. Editing during a scan is rejected |
| C-05 | 2b | 1 | Change the NCPA port setting (default 5693) to another value; reopen the table | The NCPA entry in the table follows the new port, and is not editable by hand. Restore the default afterwards |
| C-06 | 2b | 1 | On the upgraded copy, find a port that was in both old tables with different services; open the new table | The old "always treat port as" entry won. No row came from `AUTO_MONITOR_SERVICES`; the setting is gone, and no port is monitored merely for being in a list |
| C-07 | 2b | 1 | Include the monitoring server's own address in the scan range (a lab `/28` that contains it, on every local interface; check `ip -o addr`). Run discovery | The server's own addresses (all of them, not only the first) never get services in `hosts.cfg`, and are not offered for monitoring. `localhost.cfg` is unchanged. A device on another address is unaffected |
| C-08 | 3 | 2 | Enable `check_ncpa` on target02 with NCPA deployed; enable `check_snmp` with several OIDs configured | NCPA yields CPU, memory and one disk service per mount, each its own service reaching OK. SNMP yields one service per configured OID. A metric that does not exist on the device ends non-OK (not silently dropped) |
| C-09 | 3 | 2 | With a plugin off, run discovery; open a port it would check | The port keeps its state (Monitored or Suggested as before). It is **not** in `hosts.cfg`. The discovery log or "skipped" record names the port and says the plugin is not enabled. Enabling the plugin then adds it with no rescan needed |
| C-10 | 3 | 2 | Run discovery three times with no changes. Diff `hosts.cfg` between runs | Identical apart from the header timestamp. No reload is performed when nothing changed, and the reply says nothing needed updating, not an error |
| C-11 | 3 | 2 | Read one generated service and its command for each enabled plugin | Every command starts with `$USER1$/`, has its arguments filled (host address, port), and no `$ARG1$` left (check `define service` blocks only; the `define command` templates keep their `$ARGn$`). Running the command by hand on the Nagios server returns the same status Nagios shows |
| C-12 | 4 | 2 | `POST /api/plugin/<id>/enable` for `check_ping`, `check_load` | 409 and the plugin keeps its status (also NS-01). The UI shows no Enable button |
| C-13 | 4 | 2 | Call the old routes: `GET /api/plugin/targets`, `GET /api/plugin/running`, `POST /api/plugin/<id>/configurations`. Open Manage Roles | Each returns 404/405. No `plugin.configure` permission is listed. Roles that had it still work |
| C-14 | 4 | 2 | Enable the same plugin twice in a row (also double-click the Confirm button). Disable twice | The second enable returns without a second set of rows or a second reload (or a clear "already enabled"). Disable twice is safe. History has one row per real change |
| C-15 | 5 | 6 | Open Plugin Manager, then NCPA Deployment with `check_ncpa` off, then on | No "Currently Running" tab and no "Apply to Device" anywhere. NCPA page shows the amber notice with a link to Plugin Manager when `check_ncpa` is off, and not when it is on. No console errors on either page |
| C-16 | 6 | 2 | With no plugin enabled, read the Dashboard average response time and packet loss, and `HOST_PERF_DATA` for a host (`rta`, `pl`) | Both are filled from the host check (`check-host-alive`), without `check_ping` enabled. `check_ping` still shows "Not service-driven" (G13/G21) |
| C-17 | 6 | 0 | Run the upgrade rehearsal on a copy with populated data (lab UPG-01 steps 7 and 9) and `pytest tests/unit/test_upgrade_rehearsal.py` on the same server | Rehearsal tests pass on the lab's Python and SQLite. Live result equals the rehearsal: no service lost, no port promoted, downgrade leaves no AUTO look-alike rows |
| C-18 | 6 | 6 | Run lab plan PF-01 (`check_tcp` on the full lab) | The Enable request and the plugin details open in a time the owner accepts (record it). No timeouts. `nagios -v` and reload succeed with the larger config |
| C-19 | 6 | 0 | Run lab plan §11 (cleaning `plugin-services.cfg`) on a copy | After cleanup `nagios -v` passes, the Dashboard and Plugin Manager counts match Nagios, no MANUAL row remains for a removed service (closes G19) |

### 18.1 Added to the traceability

| Objective | Added cases |
|---|---|
| O-1 | C-02, C-09 |
| O-2 | C-04, C-06, C-09, C-12 |
| O-3 | C-14 |
| O-4 | C-08, C-11, C-15 |
| O-5 | C-01 |
| O-6 | C-07, C-16 |
| O-7 | C-06, C-07 |
| O-8 | C-09 |
| O-9 | C-03, C-10, C-17, C-19 |
| O-10 | C-04, C-13 |

Blocking cases added: C-02, C-03, C-07, C-11, C-17.
