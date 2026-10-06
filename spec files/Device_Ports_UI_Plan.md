# Plan: Device Ports UI

Status: **decisions Q1–Q5 made and the requirement approved with changes (2026-10-06); phase P2 (backend) is done; P3 (frontend) is next.** The requirement is
[`Device_Inventory_Requirements.md`](Device_Inventory_Requirements.md). That file is the
authority for what the screen shows, its wording and its acceptance criteria; this plan is
only how and in what order it is built. If they disagree, the requirement wins.
Follows the format of `NCPA_Deployment_UI_Plan.md`; like it, this file is not
indexed in `AGENTS.md`.

Closes: gaps **G1** and **G26** in `Plugin_Driven_Monitoring_Plan.md` §13, and the
`Implementation_Status.md` rows "Ports list in the client" and "Per-device port
service UI". It is the ports half of the unbuilt "Device Inventory UI" in
`DHCP_Device_Identity_Plan.md` §11 (Phase 4).

Goal: an administrator can open a device, see every port discovery found on it and
**why each one is or is not monitored**, and act on it (monitor, stop, leave it
Suggested, release a hold, acknowledge a "not used as intended" port, pin its
service) without calling the API by hand.

---

## 1. Why this is needed

Ports decide what Nagios checks, and several of them now wait on a person:

| Situation | What the port is waiting for | Who can see it today |
|---|---|---|
| A service nmap found is not what the Port → Service table expects ("not used as intended") | An admin to acknowledge it | Nobody in the UI (API only) |
| An admin set a port back to Suggested, or an upgrade held it (`Promotion_Held`) | An admin to monitor it | Nobody in the UI; the enable dialog only says "N held back" |
| A port is Suggested because its plugin is not enabled, or because nmap only guessed from the number | A plugin to be enabled, or a decision | Nobody in the UI |
| A port was stopped for one device | A "Resume" | Only inside the plugin's services list, and only if it was once monitored |

Without a list, a port can sit unmonitored with no visible reason; the only sign is a
service that is missing from Nagios.

---

## 2. Current state (verified in the code)

| Layer | State |
|---|---|
| Data | `Open_TCP_Services` / `Open_UDP_Services`: state, service, `Identified_By`, frozen `Plugin_Name`, `Expected_Service_Name`, `Mismatch_Acknowledged_At`, `Promotion_Held`, first/last seen, missed scans |
| Write route | `PUT /api/system/hosts/<id>/ports/<proto>/<port>` (`system.hosts.edit`): `state`, `service_name` (pin), `acknowledge_mismatch`; returns the port and whether the config was applied |
| Read route | **None.** `GET /system/hosts/<id>/addresses` and `/identifiers` exist, but no ports route |
| Page | `DeviceInventoryPage` (`system.network_health`) lists hosts from the Nagios snapshot, keyed by **Nagios host name**; `StatusDetailDrawer` shows host state, perf data and services |
| Device id | **Not available to the client.** `GET /system/network-health/hosts` and `/hosts/<hostname>/detail` carry the host name only, and the port routes need `NetDiscoveryID` |
| Client use of `/api/system/hosts/<id>/...` | **None.** The whole device-identity API (addresses, identifiers, edit, merge, retire, ports, review items) has no UI |
| Spec | `Display_Requirements.md` covers the Dashboard and Network Health only and says device inventory belongs elsewhere; there is **no Device Inventory requirement** |

---

## 3. Scope

In scope (this plan):

- a read route for a device's ports with the reason each one is in its state;
- the device id on the host list and detail so the page can reach it;
- a **Ports** section in the existing device detail drawer with the actions in §6,
  including **Set service… (pin)** and **Remove pin** (a new `unpin` option on the port-edit route);
- permission, error and empty states, tests and spec updates.

Out of scope (separate follow-ups, listed in §10): confidence badges,
address history, merge/retire/static-DHCP actions, the "Needs review" list, the
`SERVICE_CHANGED` review items from the DHCP plan §11, bulk actions, and any paging or
filtering of ports.

---

## 4. First step: the page requirement

`AGENTS.md` says behaviour comes from the page specification, and the DHCP plan
(§11 note) says new device-page sections must be added to `Display_Requirements.md`
before they are built. There is no Device Inventory section, so this plan **starts
with a requirement, not code**:

1. **Done:** `Device_Inventory_Requirements.md` (a new file, Q1) covers §5 and §6 below
   and ends with 20 acceptance criteria and three open points (O1–O3).
2. The owner approves it, or asks for changes.
3. Only then start §7.

Do not add fields beyond the approved requirement (`Engineering_Standards.md`).

---

## 5. Data contract

### 5.1 `GET /api/system/hosts/<id>/ports` (new, `system.hosts`)

Returns every port of a device, grouped by state and then by port number.

```json
{
  "device": {"id": 4, "nagios_host_name": "web-01", "ip_address": "192.168.130.20", "state": "ACTIVE"},
  "ports": [
    {
      "protocol": "tcp", "number": 22,
      "service_name": "ssh", "observed_service_name": "ssh",
      "state": "MONITORED", "source": "SCAN", "identified_by": "FINGERPRINT",
      "plugin_name": "ssh", "check_plugin": "check_ssh", "plugin_enabled": true,
      "expected_service_name": null, "mismatch_acknowledged": false,
      "promotion_held": false,
      "first_seen_at": "2026-10-01T09:00:00+00:00", "last_seen_at": "2026-10-05T09:30:00+00:00",
      "missed_scans": 0,
      "reason": null
    }
  ],
  "counts": {"MONITORED": 6, "MISSING": 0, "SUGGESTED": 3, "IGNORED": 1, "ARCHIVED": 0},
  "service_options": [
    {"name": "ssh", "plugin": "check_ssh", "kind": "plugin"},
    {"name": "domain", "plugin": "check_dns", "kind": "plugin"}
  ]
}
```

`reason` is computed on the server for **Suggested** and **Ignored** ports so the UI
never has to re-derive it. Exactly one applies, first match wins:

| Order | `reason.code` | Text shown |
|---|---|---|
| 1 | `not_used_as_intended` | "Not used as intended: expected {expected}, found {service}. Not monitored until acknowledged." |
| 2 | `held` | "Held back: left Suggested on purpose (or at an upgrade). No plugin will monitor it until you do." |
| 3 | `guessed` | "Only guessed from the port number, so it is not monitored automatically." |
| 4 | `plugin_not_enabled` | "{check_plugin} is not enabled in Plugin Manager." |
| 5 | `no_udp_plugin` | "No plugin can check this UDP service." |
| 6 | `ephemeral` / `device_excluded` | the reason it is skipped |
| — | `stopped` (Ignored) | "Monitoring stopped by an administrator." |

`service_options` lists every service name and alias the plugin registry knows with the
check plugin it leads to (the same shape as `resolution` in the Settings response). It
feeds the Set service dialog's suggestions and its "Checked by" line; any other valid name
is checked by the generic TCP plugin (TCP) or skipped (UDP).

Errors: 404 for an unknown device; 403 without `system.hosts`. No pagination at
first (a device has dozens of ports, not thousands; the scan range is `1-10000`);
revisit if a lab measures otherwise (Q4).

**P2 as built.** `GET /system/hosts/<id>/ports`, `device_id` on the host list and detail
(`device_ids_by_host_name`, one lookup per page), the `unpin` option and
`port_lifecycle.unpin_port_service()`, `port_lifecycle.port_reason()` and
`plugin_registry.service_options()`. Two differences from this plan's first draft: the UDP
"no plugin can check this" reason now comes **before** "plugin not enabled" (enabling `check_udp`
would do nothing for such a port), and the response carries `managed_by_ncpa` and
`pinned` so the screen does not have to derive them. Unpin is refused for the NCPA port of a deployed
agent; pinning that port is not (that is existing behaviour, left unchanged).

### 5.2 Device id on the host list and detail (B2)

`GET /system/network-health/hosts` and `/hosts/<hostname>/detail` gain
`device_id` (nullable). It is looked up by Nagios host name
(`Nagios_Host_Name`, falling back to `Hostname` as `nagios_host_name()` does). It is
`null` for hosts with no device row, such as `localhost`; the UI then shows no Ports
section. One grouped query for the page, not one per row.

### 5.3 Port-edit route: one new option

`PUT /api/system/hosts/<id>/ports/<proto>/<port>` already returns the port,
`promotion_held`, `expected_service_name`, `config_applied` and `config_message`. It gains
`"unpin": true` (Remove pin, owner decision O1). `unpin_port_service()` in `port_lifecycle.py`:

- refuses a port that is not pinned (`Identified_By` is not `USER`) with 400;
- cannot be combined with `service_name`;
- a Suggested, Ignored or Archived port gets `Service_Name` back from `Observed_Service_Name`
  and its identification is reset to a guess, so the next scan decides it again;
- a Monitored or Missing port keeps its `Service_Name` and frozen `Plugin_Name` (its Nagios
  service does not change); the next scan treats it like any unpinned monitored port, raising a
  `SERVICE_CHANGED` review item if nmap sees something else;
- never changes `Port_State` or `Promotion_Held`, and writes an activity-log entry.

---

## 6. UI

### 6.1 Placement

A **Ports** section in the device detail drawer (`StatusDetailDrawer`), shown when
the user has `system.hosts` and the host has a `device_id`. If Q2 prefers a separate
drawer it moves unchanged. Grouped, with counts in the headers, in this order:

1. **Needs attention** — Suggested ports with a `not_used_as_intended` or `held` reason
2. **Monitored** (and Missing, marked "not seen lately")
3. **Suggested**
4. **Stopped** (Ignored)

Each row: protocol/port, service name (and "found X, expected Y" when flagged), a
state badge, how it was identified (Fingerprint / Port rule / Pinned / Guess), the
frozen check plugin, the `reason` text, and last seen.

### 6.2 Actions (all need `system.hosts.edit`; hidden otherwise)

| Port state / reason | Actions shown | Request |
|---|---|---|
| Suggested, `not_used_as_intended` | **Acknowledge and monitor** | `{"acknowledge_mismatch": true}` |
| Suggested, `held` | **Monitor** (releases the hold) | `{"state": "MONITORED"}` |
| Suggested, `plugin_not_enabled` | **Monitor** (will only produce a service once the plugin is on); link "Enable {plugin}" to Plugin Manager | `{"state": "MONITORED"}` |
| Suggested, `guessed` | **Monitor**, **Set service…** (pin) | `{"state": "MONITORED"}` / `{"service_name": "..."}` |
| Suggested, any | **Ignore** | `{"state": "IGNORED"}` |
| Monitored / Missing | **Stop monitoring**, **Leave suggested** (holds it) | `{"state": "IGNORED"}` / `{"state": "SUGGESTED"}` |
| Ignored | **Resume** | `{"state": "MONITORED"}` |
| Any except Archived | **Set service…** (pin; dialog and wording in the requirement §6) | `{"service_name": "..."}` |
| Pinned | **Remove pin** | `{"unpin": true}` (new) |
| NCPA port with a deployed token | no destructive actions and no Set service; "Managed by NCPA deployment" | — |

Rules:

- **Confirm** only for Stop, Ignore and Leave suggested, with one sentence saying what
  happens to the Nagios service. Monitor and Acknowledge need no confirmation.
- "Leave suggested" and "Ignore" differ and the labels say so: Suggested is kept in the
  list as a decision still to make; Ignored is hidden from "needs attention".
- After a change reload the ports and show the response's `config_message` when
  `config_applied` is false ("The change was saved but Nagios was not updated: ...").
- A 409 (for example the protected NCPA port) shows the server message and changes
  nothing.
- A device whose state is Retired or Merged shows the list read-only.

### 6.3 States

Loading, error with retry, "No ports discovered yet" with the scan hint, a permission
note ("You can view ports but not change them"), and an empty group is not rendered.
Dark mode uses the existing badge colours (`StatusDetailDrawer` / Plugin Manager chips).

### 6.4 Plugin Manager link

The enable dialog's "N identified port(s) are held back" gets a short hint pointing at
the device Ports section ("Monitor them from each device's Ports list"). No new data.

---

## 7. Work, in order

| Phase | Work | Exit check |
|---|---|---|
| P1. Requirement | **Written**: `Device_Inventory_Requirements.md`; Q1–Q5 answered (§9). Waiting for the owner to approve it (including O1–O3) | Owner approval of the requirement |
| P2. Backend | **Done** (see below).  B1 `GET /system/hosts/<id>/ports` with `reason`, `counts` and `service_options`; B2 `device_id` on host list and detail; B3 `unpin` on the port-edit route; module docstring and route tests; spec updates in `Backend_Modules_and_Routes.md` | `pytest tests/unit/` green: every reason code, every state, ordering, permissions (login, `system.hosts`), 404, UDP and TCP, the NCPA port, a device with no ports, `device_id` null for `localhost`, query count does not grow with rows |
| P3. Frontend | `devicePortsApi.ts`, types with wire conversion, `DevicePortsSection` (groups, rows, actions, confirmations, states) and the Set service dialog, `useDevicePorts` hook; wire into the drawer; the enable-dialog hint | Vitest for every state/reason, every action's request, permission hiding, error/409/`config_applied` false, confirmation flows, no section without `device_id`; `npm run build`; no new lint error |
| P4. Specs and lab | `Frontend_Modules_and_Routes.md`, `Implementation_Status.md` (close both rows), `Plugin_Driven_Monitoring_Plan.md` (G1, G26 closed), `Plugin_Driven_Monitoring_Plan` §7.x notes; lab cases added to `PLUGIN_DRIVEN_MONITORING_LAB_TEST_PLAN.md` (MM-01 and GT-01 become UI steps) | Browser check in light and dark mode on the lab |

Each phase ends with both suites green, `main` fetched and merged, an Alembic head
check (no migration is expected), and the gap register reviewed, as in the plugin plan.
Estimated size: about the same as Phase 5 of the plugin plan (one new route, one
changed response, one component with its tests).

---

## 8. Tests

- **Backend (`server/tests/unit/`)**: new `test_device_ports_route.py`; extend
  `test_device_identity_routes.py` for the unchanged PUT contract; extend
  `test_network_hosts.py` for `device_id`. Reasons are tested one by one, including the
  first-match order (a held port that is also flagged reports `not_used_as_intended`).
- **Frontend (`client/src/test/`)**: `DevicePortsSection.test.tsx`,
  `useDevicePorts.test.ts`, drawer integration in `StatusDetailDrawer` tests.
- **Lab**: the two lab cases in §7 P4; no new fixtures.
- Follow `server/tests/README.md` and `Engineering_Standards.md`.

---

## 9. Decisions (questions answered)

| # | Question | Decision (owner, 2026-10-06) |
|---|---|---|
| Q1 | Where does the page requirement live? | **A new file**, `Device_Inventory_Requirements.md` |
| Q2 | Where does the Ports section appear? | **In the same device detail drawer** |
| Q3 | Which actions are in the first version? | **All of them including Set service… (pin)** (option B). This adds the service-name dialog, the `service_options` list in the route, and the pin wording in the requirement §6 |
| Q4 | Pagination or a filter box? | **Neither for now**; add a state filter only if a lab device shows more than about 50 ports |
| Q5 | Include the needs-review items? | **No**; a separate follow-up |
| O1 | Add a route to remove a pin? | **Yes**: `unpin` on the port-edit route (§5.3) |
| O2 | Keep both Ignore and Stop monitoring labels? | **Yes** |
| O3 | May a held Suggested port still be pinned (and stay held)? | **Yes** |

---

## 10. Follow-ups (not in this plan)

- Device identity UI: confidence badges, address history, merge, retire, static/DHCP,
  and the "Needs review" list (`DHCP_Device_Identity_Plan.md` §11).
- Auto-resolving `SERVICE_CHANGED` items (an existing `Implementation_Status.md` row).
- A bulk action for held ports ("monitor all held ports of this plugin").

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| The host list is keyed by Nagios name and a device with no stable name matches the wrong row | Use the same `nagios_host_name()` rule as the generator; test the fallback and `null` cases |
| `reason` drifts from what the reconciler really does | Compute it from the same helpers (`has_unacknowledged_mismatch`, `Promotion_Held`, `plugin_for_definition`, `enabled_plugin_names`); one test per code against the real `promote_identified_ports` result |
| An admin "monitors" a Suggested port whose plugin is off and sees nothing happen | The reason text and the "Enable {plugin}" link say so; the response's `config_message` is shown |
| Acting on a stale list (a scan changed a port since it loaded) | Reload after every change; the server remains the authority and returns its own state |
| Building a section the owner has not approved | P1 is a hard gate; no code before it |
