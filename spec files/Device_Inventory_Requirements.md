# Device Inventory Requirements — Ports
**Detech-IT / 4D-G2 Capstone**
**Status:** Approved by the owner with the answers to O1–O3 (2026-10-06): a **Remove pin** action and route are included. Built (backend and drawer); the browser check in light and dark mode is still to do on the lab.
**Companion:** [`Device_Ports_UI_Plan.md`](Device_Ports_UI_Plan.md) (how and in what order it is built)

---

## Purpose

This document defines what the **Ports** section of the Device Inventory page
shows and what an administrator can do in it. It is the requirement the plan asks
the owner to approve before any code is written (`AGENTS.md`; the same rule is
noted in `DHCP_Device_Identity_Plan.md` §11).

`Display_Requirements.md` covers the Dashboard and Network Health. This file covers
**only** the Ports section of the Device Inventory page. The rest of that page (the
host table, its filters, the status drawer and acknowledgement) is unchanged.

As in `Display_Requirements.md`, layout, colour and component details are left to the
front-end developers. What is fixed here is the data shown, the grouping, the wording
of reasons and confirmations, who may do what, and the acceptance criteria in §10.

The goal: an administrator can open a device, see every port discovery found on it and
**why each one is or is not monitored**, and change that, without calling the API by
hand.

---

## Definitions

| Term | Meaning |
|---|---|
| **Port** | One TCP or UDP port discovery found open on a device, with the service name discovery decided for it. |
| **Monitored** | The port has a Nagios service, provided the plugin that checks it is enabled in Plugin Manager. |
| **Missing** | A monitored port not seen in the last several scans. It keeps its service, so Nagios reports it as CRITICAL. |
| **Suggested** | Found, but not monitored. It is waiting for a plugin or for an administrator. |
| **Ignored** | An administrator stopped monitoring it. It is hidden from "needs attention". |
| **Archived** | Gone for good (not seen for a long time). Shown only if present; no actions. |
| **Not used as intended** | nmap found a different service on the port than the Port → Service setting expects. Not monitored until an administrator acknowledges it. |
| **Held** | An administrator left the port Suggested on purpose, or an upgrade held it so it would not start being monitored. No plugin promotes a held port. |
| **Pinned** | An administrator fixed the port's service on this device. Scans never rename it. |
| **Check plugin** | The Plugin Manager plugin that checks the port's service (for example `check_ssh`). |

---

## Data Sources

Ports come from the device record (`Open_TCP_Services`, `Open_UDP_Services`); the
reason text is computed by the server. The route contract is in
`Backend_Modules_and_Routes.md` once built. This document defines *what* to show, not
API structure beyond §8.

---

## 1. Where it appears

- In the **device detail drawer** that opens from a row of the Device Inventory host
  table (the existing drawer, below the host state and services). It is not a new page,
  tab or drawer.
- It is shown only when the user has `system.hosts` **and** the host is a discovered
  device. A host that has no device record (for example the monitoring server itself,
  `localhost`) shows no Ports section.
- It is read-only unless the user has `system.hosts.edit` (§5), or the device is
  Retired or Merged (§7).

---

## 2. What each port shows

One row per port:

| Item | Notes |
|---|---|
| Protocol and port | for example `tcp/22` |
| Service | the service name; when flagged, "found {service}, expected {expected}" |
| State badge | Monitored, Missing ("not seen lately"), Suggested, Ignored, Archived |
| How it was identified | Fingerprint (nmap probed it), Port rule (the Port → Service setting), Pinned (an administrator), Guess (only from the port number) |
| Check plugin | for example `check_ssh`; "none" when no plugin checks it |
| Flags | "Not used as intended", "Held" |
| Reason | the sentence from §4, for Suggested and Ignored ports, a Missing port and a Monitored port whose plugin is off, and a Monitored port with no service |
| Last seen | relative time, with the exact time on hover |

---

## 3. Grouping and order

Groups are shown in this order, each with a count in its header. A group with no ports
is not shown.

1. **Needs attention**: Suggested ports whose reason is *Not used as intended* or *Held*.
2. **Monitored**: Monitored, then Missing.
3. **Suggested**: the remaining Suggested ports.
4. **Stopped**: Ignored ports.
5. **Archived**: collapsed by default.

Inside a group, ports are ordered by protocol (TCP, then UDP) and port number.

---

## 4. Reasons

Shown for **Suggested** and **Ignored** ports, plus the three Missing and Monitored cases at the end of the table. Exactly one applies; the first match wins.

| Order | Condition | Text |
|---|---|---|
| 1 | Not used as intended, not yet acknowledged | "Not used as intended: expected {expected}, found {service}. Not monitored until acknowledged." |
| 2 | Held | "Held back: left Suggested on purpose, or at an upgrade. No plugin will monitor it until you do." |
| 3 | Identified only by a guess | "Only guessed from the port number, so it is not monitored automatically." |
| 4 | UDP service no plugin can check | "No plugin can check this UDP service." |
| 5 | Its check plugin is not enabled | "{check_plugin} is not enabled in Plugin Manager." |
| 6 | Device is excluded from scanning | "This device is excluded from scanning." |
| 7 | Ignored | "Monitoring stopped by an administrator." |
| 8 | Missing | "Not seen lately: no recent scan found this port. Its service stays in Nagios until the port is archived." |
| 9 | Monitored, but its check plugin is not enabled (the port keeps its frozen plugin) | "{check_plugin} is not enabled in Plugin Manager, so nothing is checking this port." |
| 10 | Monitored, its plugin is enabled, but no Applied Nagios service exists for the port (a configuration problem, for example a rejected config) | "Marked Monitored, but no Nagios service exists for it. This is a configuration problem: check the activity log for a rejected configuration, then run discovery again." |

A Suggested port that matches none of these is about to be monitored by the next
reconcile; the reason reads "Will be monitored by the next update."

---

## 5. Actions

Shown only with `system.hosts.edit`. Without it the section is view-only and says so
once ("You can view ports but not change them.").

| Port | Action | Effect | Confirmation |
|---|---|---|---|
| Suggested, *Not used as intended* | **Acknowledge and monitor** | Accepts the service nmap found and monitors it if its plugin is enabled | none |
| Suggested (any reason except *Not used as intended*) | **Monitor** | Monitors the port (releases a hold, accepts a flag). If its plugin is not enabled it will produce a service only once the plugin is, and the row says so | none |
| Suggested, reason *plugin not enabled* | link **Enable {check_plugin}** | Opens Plugin Manager | none |
| Suggested | **Ignore** | Hides it from "needs attention"; no service | "Ignore {protocol}/{port} on {host}? It will not be monitored." |
| Monitored or Missing | **Stop monitoring** | Becomes Ignored; its Nagios service is removed | "Stop monitoring {service} on {host}? Its Nagios service is removed; history is kept." |
| Monitored or Missing | **Leave suggested** | Becomes Suggested and **held**; its service is removed and no plugin will monitor it again until an administrator does | "Leave {protocol}/{port} suggested? Its Nagios service is removed and no plugin will monitor it again until you do." |
| Ignored | **Resume** | Becomes Monitored again, checked by the plugin for its service | none |
| Any except Archived | **Set service…** | See §6 | see §6 |
| Pinned, any except Archived | **Remove pin** | Lets scans decide the service again (§6) | "Let scans decide the service for {protocol}/{port} on {host} again?" plus the sentence for its state from §6 |

For a *Not used as intended* port, **Acknowledge and monitor** is shown instead of Monitor, because both would do the same thing.

Not available:

- **The NCPA port of a device with a deployed agent**: no Stop, Ignore, Leave suggested
  or archive; the row reads "Managed by NCPA deployment". Set service and Remove pin are not offered.
- **Archived ports**: no actions.

---

## 6. Set service (pin)

"Set service…" fixes what the port is **on this device**: "always treat this port as X".

**Dialog** titled "Set service for {protocol}/{port} on {host}":

- A text field for the service name with suggestions of the services Pinpoint knows
  (for example ssh, http, https, snmp, ncpa, ftp, smtp, mysql, dns, ntp). Any other
  valid name is allowed.
- Validation: lowercase letters, digits, `-` or `_`; starts with a letter or digit;
  at most 32 characters. The same rule as the Port → Service setting.
- A live "Checked by" line under the field:
  - a known service: its check plugin (for example "check_http");
  - any other name on TCP: "check_tcp (generic TCP check)";
  - any other name on UDP: "Skipped: no check exists for this UDP service".
- Text always shown: "Scans will no longer change this port's service on this device.
  You can change it again or use Remove pin."
- Extra text when the port is Monitored or Missing: "Its Nagios service will be renamed
  (for example http-8080-tcp becomes ssh-8080-tcp). History stays under the old name."
- Buttons **Cancel** and **Save**; Save is disabled while the name is invalid or unchanged.

**Effect:** the service name is saved and marked Pinned. A port that is already monitored
is re-checked with the new service's plugin. A Suggested port stays Suggested (and keeps
its hold); pinning never promotes. Pinning clears a "Not used as intended" flag on that
port, because the administrator has decided.

### Remove pin

Shown on a port whose service is Pinned. It undoes "Set service…" and lets scans decide the
service again.

- A **Suggested, Ignored or Archived** port goes back to the service the last scan saw and
  follows scans from now on. Confirmation sentence: "The service goes back to what the last
  scan saw."
- A **Monitored or Missing** port keeps its service and its Nagios service unchanged.
  Confirmation sentence: "Its Nagios service is not changed. If a later scan sees a different
  service, the current one is kept and a review item is recorded."
- A hold is never changed by removing a pin, and neither is the port's state.
- It is refused for a port that is not pinned ("This port is not pinned.").

---

## 7. After a change, and states

**After any action:**

- The ports reload from the server; the server's state is what is shown.
- If the change was saved but Nagios was not updated, show the server's message:
  "The change was saved but Nagios was not updated: {message}".
- A refused change (for example the protected NCPA port) shows the server's message and
  changes nothing.
- While an action runs, its button is disabled.

**States of the section:**

| State | Shown |
|---|---|
| Loading | a loading indicator in the section |
| Error | the error text with **Retry** |
| No ports | "No ports discovered yet. Run a scan from Network Discovery." |
| View-only | the note in §5 |
| Retired or Merged device | the list is read-only and says "This device is retired/merged." |
| Plugin Manager link | "Enable {check_plugin}" appears only for users who can view Plugin Manager (`plugin.view`) |

The Plugin Manager enable dialog's "N identified port(s) are held back" gets the added
line "Monitor them from each device's Ports list."

---

## 8. Data the screen needs

(Contract details go in `Backend_Modules_and_Routes.md` when built.)

- **A read route for a device's ports** (`system.hosts`): per port the protocol, number,
  service, observed service, state, source, how identified, check plugin and whether it
  is enabled, expected service and acknowledgement, held flag, first/last seen, missed
  scans and the reason code and text of §4; counts per state; and the list of known
  service names with their check plugin for §6.
- **`device_id` on the Device Inventory host list and host detail**, empty for hosts
  without a device record.
- The existing port-edit route for every action. It gains one option, `unpin`, for Remove pin (§6); nothing else it accepts changes.

---

## 9. Out of scope

The needs-review list and `SERVICE_CHANGED` items; device confidence badges, address
history, merge, retire and static/DHCP marking; bulk actions;
pagination or a filter box for ports; any change to the Port → Service setting or to
Plugin Manager beyond the one hint line in §7.

---

## 10. Acceptance criteria

1. The Ports section appears in the device drawer for a discovered device when the user
   has `system.hosts`, and not for a host with no device record.
2. Ports are grouped and ordered as in §3, with counts; empty groups are not shown.
3. Each row shows the items in §2.
4. Every reason in §4 is produced for the right port and the first match wins (a port
   that is both held and flagged reads "Not used as intended").
5. Without `system.hosts.edit` no action is shown and the view-only note appears.
6. Each action in §5 sends the matching request and then reloads the list.
7. Stop, Ignore and Leave suggested ask for confirmation with the §5 wording; the
   others do not.
8. Cancelling a confirmation changes nothing.
9. The NCPA port of a deployed agent offers no destructive action and shows "Managed by
   NCPA deployment".
10. Archived ports are collapsed and have no actions.
11. Acknowledge and monitor on a flagged port monitors it (when its plugin is enabled) and
    clears the flag; Monitor on a held port clears the hold.
12. Leave suggested holds the port: after the next scan and after its plugin is disabled
    and enabled again it is still Suggested.
13. Set service: the field validates as §6; the "Checked by" line is correct for a known
    service, an unknown TCP name and an unknown UDP name; the warning texts appear; Save
    is disabled for an invalid or unchanged name.
14. Pinning a monitored port renames its service; pinning a Suggested port does not
    monitor it; a scan does not undo a pin.
15. A saved-but-not-applied change shows the server's message; a refused change shows the
    server's message and changes nothing.
16. Loading, error with Retry, no-ports, view-only and retired/merged states are shown as
    in §7.
17. "Enable {check_plugin}" appears only for users with `plugin.view`.
18. The Plugin Manager enable dialog shows the extra hint when ports are held.
19. Light and dark mode are both usable and the section works at a narrow width.
20. No existing Device Inventory behaviour (host table, filters, acknowledgement,
    services list) changes.
21. Remove pin is shown only on pinned ports (not Archived, not the protected NCPA port) and asks
    for confirmation with the §6 wording for the port's state.
22. Removing a pin on a Suggested port returns it to the last scanned service; on a Monitored
    port the Nagios service is unchanged; the port's state and hold are never changed by it.
23. Remove pin on a port that is not pinned is refused with "This port is not pinned."; a scan
    after the pin is removed may change the service again.

---

## 11. Decisions on the open points (owner, 2026-10-06)

| # | Point | Decision |
|---|---|---|
| O1 | A pin cannot be removed | **Add an unpin route.** Remove pin is included (§5, §6, criteria 21–23) |
| O2 | "Ignore" (Suggested port) and "Stop monitoring" (Monitored port) both end Ignored | **Keep both labels** |
| O3 | A held Suggested port can still be pinned and stays held | **Keep** |
