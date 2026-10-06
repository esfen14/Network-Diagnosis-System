# Implementation Status and Scope

**Snapshot date:** 2026-09-27

This file reports what is present in the repository. It is not a substitute for
the normative behavior in the requirement specifications.

## Implemented backend areas

- Session login/logout and current-user identity.
- Account, role, permission-option, and per-user preference APIs.
- Singleton system settings with personal/system separation and optimistic
  version conflict handling.
- Dashboard status, summary, active alerts, acknowledgement, and latest
  notifications.
- Network Health summary, metric trends, plugin grouping, host table/details,
  service table/details, and acknowledgements.
- Alerts and Notifications History list/detail routes backed by Nagios archive
  events and Pinpoint acknowledgement history.
- Header notification feed with per-user unread cursor.
- Network discovery start/stop/status and Nagios host/service config generation.
- NCPA eligibility, SSH fingerprint trust (approved key only), login checks,
  deployment with per-device outcomes, cancellation, status, run history and
  review, and trusted-device routes.
- Activity, configuration, discovery, NCPA, and export logs.
- Availability, OS, network-service, device-service, alert, and notification
  report APIs.
- Plugin Manager scanning, inventory, running checks, summaries, details,
  dependencies, enable/disable, validation, custom upload, command overrides,
  updates/rollback, history, and target configuration.
- Scheduled Nagios polling, retention purges, backups, network scans, plugin
  update scans, and security validation.

## Implemented frontend areas

- Login and authenticated application layout.
- Permission-aware sidebar and direct-route guard.
- Dashboard API integration and acknowledgement flow.
- Network Health summary/trend integration.
- Device Inventory backed by latest host-status APIs.
- Account and role management.
- System Settings and per-user preferences.
- System Logs with five backend categories.
- Reports UI for host availability and network services.
- Plugin Manager inventory/running tabs, details, scan, custom plugin, and
  administrative actions.
- NCPA Deployment page: device list, deploy wizard with host-key verification
  and per-device login checks, live progress, header bell item, and Deployment
  History with run review.
- Header notification feed/unread behavior, session timeout, maintenance banner,
  shared export UI, and network rescan workflow.

## Incomplete or mismatched work

| Area | Current state | Required direction |
|---|---|---|
| History frontend | Backend routes exist; no routed Alerts & Notifications History page exists | Build the two-tab page from `Alerts_Notifications_History_Requirements.md` and add client permission/navigation wiring |
| History permission seed | Routes require `system.history`, but the seed permission list does not include it | Add and seed the permission before relying on the routes in a normal installation |
| Auto-resolved acknowledgements | `AckAction.AUTO_RESOLVED` and model contract exist; status polling does not clean resolved active acknowledgements | On UP/OK transition, delete the active acknowledgement and append an AUTO_RESOLVED history record |
| Discovery stop permission | Stop route checks `network.discovery`; seed data defines `system.discover` | Standardize the route on the seeded permission or deliberately introduce/seed the alternate permission |
| Topology exclusion | `TopologyPage`, `/topology`, and a sidebar entry labeled “System Status” are still active | Remove the route and navigation entry while keeping source code for possible future use |
| Reports frontend breadth | Backend has six report endpoints; UI currently exposes availability and network-services views | Add other views only when product requirements call for them |
| Network Health plugin section | Backend endpoint exists; current page does not call `/network-health/plugins` | Connect it when implementing the corresponding `Display_Requirements.md` section |
| Device discovery inventory | Historical docs described `/system/hosts` and port endpoints, but those routes do not exist; current Device Inventory uses latest Nagios host status | Treat the current host-status API as implemented behavior unless a separate discovery inventory contract is approved |
| Plugin lifecycle and discovery | Generation and promotion follow Plugin Manager; the reconciler attaches and detaches services on enable, disable, scan, port edit, merge/retire and NCPA events; the Plugin Manager page shows an enable preview, a Monitoring column, each plugin's monitored services with live status and stop/resume per device. The manual apply routes, `plugin-services.cfg` writing and the `plugin.configure` permission are removed | Not yet run against a live Nagios or checked in a browser: `server/tests/plans/PLUGIN_DRIVEN_MONITORING_LAB_TEST_PLAN.md` is the checklist. Held ports (`Promotion_Held`) can only be released through the API until the client has a device ports list (plan G1, G26) |
| Custom plugins | `POST /api/plugin/custom` and its client call are commented out; the Add Custom Plugin button is greyed out | Restore both together when custom plugins enter scope |
| Plugins with no port | Enabling a plugin no longer applies it to every host: services are attached per discovered port, so a plugin that checks no port (`check_ping`, `check_load`, ...) attaches to nothing and cannot be enabled. Accepted: every host keeps the `check-host-alive` host check, and the response time and packet loss on the Dashboard come from it | None; confirm `check-host-alive` in the lab (plan G13) |
| Ports list in the client | The "not used as intended" flag and its acknowledgement exist in the backend (`PUT /system/hosts/<id>/ports/<proto>/<port>` with `acknowledge_mismatch`), but the client has no device ports list, so there is nothing to show or click yet. Phase 5 covered Plugin Manager only | Add a device ports list with an Acknowledge action (not scheduled in the plan; see G1) |
| Per-device port service UI | Services are identified by fingerprint with port rules (see `Data_Model_and_Integrations.md`); pinning one device's port and resolving `SERVICE_CHANGED` review items are API-only because no page lists a discovered device's ports | Add a discovered-ports view with pin/state controls and the review list when the device inventory contract is approved |
| NCPA port per device | `NCPA_PORT` is one global setting (config only) used by checks, probes and relocation; agents deployed on another port are not tracked | Store the deployed port per device and add a re-port action if the port ever becomes user-configurable |
| NCPA deployment cleanup | A failed install leaves the deployment account, key, sudo rule and helper on the device; the error message says so | Add an explicit cleanup action if operators need it |
| SERVICE_CHANGED auto-clear | A `SERVICE_CHANGED` review item stays open after the mismatch disappears (seen when a port rule was removed); only an operator resolves it | Resolve the item automatically when the port again matches its frozen plugin |
| NCPA token in check command | The NCPA token is a positional argument of the Nagios command, so it is visible in process listings and any transcript of the command | Review passing the token another way (for example a Nagios resource file) |
| Installer | Developed in another repository | Keep installer work out of this repository unless scope changes |

## Test approach status

Backend tests are organized under `server/tests/unit/`, `integration/`, `e2e/`,
`support/`, and `plans/`. Default pytest collection is isolated. The deterministic
browser-to-Nagios approach is recorded in
[`TEST_APPROACH_ADJUSTMENT_PLAN.md`](../server/tests/plans/TEST_APPROACH_ADJUSTMENT_PLAN.md)
as **Proposed — implementation deferred pending fixes**. Missing UI workflows,
complete orchestration and automatic disposable-instance recovery are not yet
implemented; existing harness improvements do not satisfy full acceptance.

## Explicit exclusions

- Backend network-topology computation is not part of the current release.
- The frontend topology view is not a supported current-release page. Source may
  remain dormant for future development.
- Nagios' native UI is not a Pinpoint operator surface.
- Plugin Manager does not install arbitrary agents or plugins on monitored
  devices; it manages plugins on the Pinpoint/Nagios server.

## Status maintenance

When completing an item above, update this file in the same change. When a new
route, page, model, or workflow lands, also update its owning architecture or
catalog specification. Do not preserve stale “not built” notes after the code is
implemented.
