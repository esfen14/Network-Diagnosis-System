# Plan: Device Monitoring State

Status: **decisions Q1–Q3 made (2026-10-07); the requirement is `Device_Inventory_Requirements.md` §12; backend and frontend are built with tests. Not yet checked against a live Nagios or in a browser (step 5 of §10). The two open points were settled as: Retired/Merged rows stay visible with "last known status" under the chip; separate `POST /hosts/<id>/pause` and `/resume` routes.**
Follows the format of `Device_Ports_UI_Plan.md`; like it, this file is not indexed in
`AGENTS.md`.

Goal: an administrator can see which devices are **not being monitored and why**, and can
**pause** a device (stop all its Nagios checks) without retiring it, then resume it.

---

## 1. Why this is needed

| Situation | What happens today | What the admin sees |
|---|---|---|
| Device not seen for 5 scans (`MISSING`) | Still in the Nagios config, so Nagios reports DOWN / CRITICAL | A normal DOWN host; nothing says discovery lost it |
| Its IP now belongs to another device (`ADDRESS_UNKNOWN`) | In the config with `active_checks_enabled = False` and a note | Only the Nagios note |
| Missing / unknown for 30 days, or an admin retires it (`RETIRED`) | Dropped from the config; comes back if a later scan recognises it | A host whose data stops updating |
| Merged into another device (`MERGED`) | Dropped from the config | Same |
| An admin wants a device left alone for a while | **No way to do it.** `Include_Device_In_Scanning` is read in the config builder, port promotion and NCPA deployment, but nothing ever sets it (`DHCP_Device_Identity_Plan.md` §2). Retire is not durable | Nothing |

The lifecycle state (`Device_State`) is already returned by the device-identity routes
(`serialize_device_summary`), but the host list and detail routes do not carry it and the
client never uses it.

---

## 2. Decisions

| # | Question | Decision |
|---|---|---|
| Q1 | Should a paused device keep its ports and history and still be matched by scans, with only the Nagios config dropping it? | **Yes.** Pause sets `Include_Device_In_Scanning = False` and nothing else. |
| Q2 | What does the table show for a paused or retired device? | **Its host row stays visible**, with a state chip, and the table gets a **filter** for monitoring state. |
| Q3 | Which states get a label? | **Every non-Active case**: Missing, Address unknown, Retired, Merged and Paused. |

Consequence of Q1: a paused device is still found and updated by scans (address changes,
hostname, OS, identifiers) but produces no Nagios host or services, no port promotion and
no NCPA deployment. A scan must never flip the flag back on.

---

## 3. Current state (verified in the code)

| Layer | State |
|---|---|
| Model | `NetworkDiscovery.Device_State` (`DeviceState`: ACTIVE, MISSING, ADDRESS_UNKNOWN, RETIRED, MERGED) and `Include_Device_In_Scanning` (bool, default True) in `system_models.py` |
| Config | `create_host_cfg.py` includes devices with `Include_Device_In_Scanning` true and state ACTIVE / MISSING / ADDRESS_UNKNOWN; ADDRESS_UNKNOWN gets `active_checks_enabled = False` |
| Lifecycle | `device_identity.update_lifecycle()` and `apply_match()` change `Device_State` only; they do not touch the flag |
| Routes | `PUT /system/hosts/<id>` edits `display_name` and `addressing`; `POST /system/hosts/<id>/retire` and `/merge` exist (`system.hosts.edit`). Each saves, then calls `apply_config_change()` |
| Host list / detail | `GET /system/network-health/hosts` and `/hosts/<hostname>/detail` already return `device_id` (`null` when there is no device record). They do not return the state or the flag |
| Client | `DeviceInventoryPage` and `StatusDetailDrawer` show only the Nagios host / service state |

---

## 4. Scope

In scope:

- the monitoring state on the host list and detail responses;
- a pause / resume action on the device;
- a state chip in the table and the drawer, a filter, and Pause / Resume buttons with
  confirmations;
- tests and spec updates.

Out of scope: bulk pause, scheduled pause (pause until a date), confidence badges, address
history, merge UI, the "Needs review" list, and pausing a single port (already covered by
the port Stop / Ignore actions).

---

## 5. Step 1: the requirement

Per `AGENTS.md`, behaviour comes from the page specification and is approved before code.
Add a **Monitoring state** section to `Device_Inventory_Requirements.md` covering:

**One label per device**, derived in this order (first match wins):

| Label | When |
|---|---|
| Merged | `Device_State` is MERGED |
| Retired | `Device_State` is RETIRED |
| Paused | `Include_Device_In_Scanning` is false |
| Address unknown | `Device_State` is ADDRESS_UNKNOWN |
| Missing | `Device_State` is MISSING |
| Monitored | otherwise (ACTIVE) |

Each non-Monitored label has a one-line reason (wording fixed in the requirement), e.g.
Missing: "Not seen in the last N scans. Still being checked, so Nagios reports it as
down."; Address unknown: "Its address now belongs to another device. Checks are off until
it is found."; Paused: "An administrator paused monitoring. Scans still track it."

Also fixed there: who may pause / resume (`system.hosts.edit`; others see the chip only),
the confirmation wording, the filter options (All, Monitored, Not monitored, and one per
label), what the table shows for a host with no device record (no chip), and acceptance
criteria.

Open point for the requirement: Retired and Merged hosts stay in the table (Q2), but their
last Nagios snapshot goes stale. The requirement should say how that is shown (e.g. the
chip plus "last checked" time) so a stale row is not read as live.

---

## 6. Backend

1. **Read:** add `monitoring_state` (the label key above), `device_state` (the enum name)
   and `monitored` (bool, false for every label except Monitored) to the host list and
   detail responses, next to `device_id`. Compute it in one helper so both routes and the
   device summary agree. Fetch devices in the existing batch lookup in `network_hosts.py`
   so there is no per-host query.
2. **Pause / resume:** extend `PUT /system/hosts/<id>` with `"monitored": bool` (or add
   `POST /hosts/<id>/pause` and `/resume`; decide in the requirement review). Rules:
   - `system.hosts.edit`, validated JSON, user log line ("Paused device <host>").
   - Refuse on RETIRED / MERGED devices (400): they are already out of the config.
   - Saves, then returns the `apply_config_change()` result like retire does.
3. **Scans:** add a test that `reconcile_scan()` / `apply_match()` / `update_lifecycle()`
   leave `Include_Device_In_Scanning` alone, including when the device is matched at a new
   IP or becomes MISSING.
4. **Ports on a paused device:** port promotion already skips it
   (`port_lifecycle.py`); confirm the port-edit route behaviour on a paused device and
   state it in the requirement (allowed, takes effect on resume, is the recommendation).
5. **Retire interplay:** resuming a retired device is not a pause action. A retired device
   still comes back by being rediscovered, as today.

---

## 7. Frontend

- `types/host.ts`: add the new fields to the host and detail types and the mapper.
- `DeviceInventoryPage`: a Monitoring column with the chip, and a filter control that
  combines with the existing filters.
- `StatusDetailDrawer`: the chip with its reason, and Pause / Resume buttons (hidden
  without `system.hosts.edit`, disabled with a reason when the device is Retired / Merged)
  using the existing confirmation-dialog pattern from the Ports section.
- API wiring in `lib/` and a hook, following `devicePortsApi.ts` / `useDevicePorts.ts`.
- States: loading, error, "config could not be updated" warning (the change is saved but
  not yet in Nagios), same as the port actions.
- Check light and dark mode.

---

## 8. Tests

Backend (`server/tests/unit/`, following `server/tests/README.md`): the label for every
state and for combinations (paused + MISSING shows Paused); pause and resume update the
flag, write a user log and trigger `apply_config_change()`; permission and 404 / 400
cases; the paused device is absent from `build_discovered_hosts` output; the flag survives
a scan; the list route stays free of per-host queries.

Frontend: chip and reason per label, filter behaviour, buttons shown / hidden by
permission, confirmation flow, and the error and warning states.

---

## 9. Spec updates (same change)

`Backend_Modules_and_Routes.md` (response fields, pause route), `Frontend_Modules_and_Routes.md`
(page row and components), `Data_Model_and_Integrations.md` (the flag now has a writer),
`Device_Inventory_Requirements.md` (step 1), and `Implementation_Status.md` (close the
"nothing sets `Include_Device_In_Scanning`" gap and the missing state label).

---

## 10. Order of work

1. Write the requirement (§5) and get it approved.
2. Backend read fields and the label helper, with tests.
3. Pause / resume route, with tests.
4. Frontend types, chip, filter, drawer actions, with tests.
5. Spec updates and a lab check (pause a device, confirm Nagios drops it and a scan does
   not re-enable it; let one go MISSING and check the chip).
