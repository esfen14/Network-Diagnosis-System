# Frontend Modules and Routes

**Last verified against the repository:** 2026-10-08

## Application shell

The client is a React/TypeScript Vite application. `src/App.tsx` owns browser
routes. `AdminLayout` supplies the authenticated shell, and `Sidebar`, `Header`,
`PageAccessGuard`, `SessionTimeoutWatcher`, and `MaintenanceBanner` implement
cross-page behavior.

All API calls are same-origin and send the Flask session cookie. Shared JSON
requests use `src/lib/api.ts`; Plugin Manager wrappers live in
`src/lib/pluginApi.ts`.

## Browser route catalog

| Browser path | Page | Required client permission | Current data source/status |
|---|---|---|---|
| `/login` | `LoginPage` | Public | Connected to `/api/user/login`. "Forgot Password?" opens a dialog that posts the email to `/api/user/forgot-password`; an administrator is notified and sets the password |
| `/dashboard` | `DashboardPage` | `system.dashboard` | Connected to dashboard, trends, service, and acknowledgement APIs |
| `/network-health` | `NetworkHealthPage` | `system.network_health` | Connected to summary and trends APIs; detailed host/service UI is supplied elsewhere |
| `/device-inventory` | `DeviceInventoryPage` | `system.network_health` | Connected to the latest-host endpoints and acknowledgement API. The host table has an IP Address column (`—` for a host with no discovered device). The host drawer also shows a Ports section (see `Device_Inventory_Requirements.md`) for users with `system.hosts` when the host has a `device_id`; actions need `system.hosts.edit`. The host table has a Monitoring column and filter, and the drawer a Monitoring section with Pause / Resume (`Device_Inventory_Requirements.md` §12) |
| `/history` | `HistoryPage` | `system.history` | Connected to the alert and notification history list and detail routes (`/api/system/history/...`); sidebar entry "History". Not audited against `Alerts_Notifications_History_Requirements.md` |
| `/topology` | `TopologyPage` | `system.network_health` | The **System Status** page (sidebar label “System Status”): a service-status table with OK / Warning / Unknown / Critical counts, search, state filter, sort, paging and acknowledgement. It is a supported page (team decision 2026-10-08). Only the network *topology view* is excluded from the release; the route and file names still say “topology” and are to be renamed |
| `/plugins` | `PluginsPage` | `plugin.view` | Connected to Plugin Manager inventory (with a Monitoring column and a banner while no plugin is enabled), plugin details with an enable confirmation that previews what will be monitored, the plugin's monitored services with live status and per-device stop/resume, scanning, and mutation APIs. There is no Currently Running tab and devices are never picked by hand |
| `/ncpa-deployment` | `NcpaDeploymentPage` | `system.deploy.ncpa` | Warns, through `useNcpaPluginState`, when `check_ncpa` is not enabled in Plugin Manager (the agent's checks are monitored only while it is). Connected to the NCPA deployment routes: device list, deploy wizard (host-key trust, login checks, start), live run banner, Deployment History tab and run review drawer (`?tab=history&run=<id>`) |
| `/reports` | `ReportsPage` | `system.report` | Connected for host availability and network-services views; backend exposes additional report routes |
| `/system-logs` | `SystemLogsPage` | `system.logs` | Connected to five log categories |
| `/accounts` | `ManageAccountsPage` | `account.view` | Connected to account/role APIs. The table shows each user's Email Alerts (On/Off); the add and edit forms show a "Send this user email alerts" checkbox only with `account.alerts`, and a failed Nagios apply is shown as a notice |
| `/manage-roles` | `ManageRolesPage` | `role.view` | Connected to role and permission APIs |
| `/settings` | `SettingsPage` | Any logged-in user; tabs are separately gated | Connected to system settings and user preferences. Tabs: General Settings, Security, System, Network Discovery and Plugins |
| `/` | Redirect | — | Redirects to `/login` |
| unmatched path | Redirect | — | Redirects to `/login` |

## Page access rules

`src/lib/pageAccess.ts` is the client route-to-permission map. The sidebar hides
pages the user cannot access, and `PageAccessGuard` prevents direct URL access.
This is usability protection only; backend permission checks remain mandatory.

The Settings page is generally available to logged-in users. Its Security,
System, Network Discovery, Plugins and Email tabs require `settings.security`,
`settings.system`, `settings.discovery`, `settings.plugins` and `settings.email`, respectively.

`AdminLayout` replaces the whole shell with a blocking window while the account
is flagged: `FirstRunSetup` when `needsSetup` (bootstrap administrator: current
password, new email, new password with confirmation; cannot be skipped, only
signed out of; a failed Nagios apply is shown as a warning after the account is
saved) and otherwise `ForcePasswordChange` when `mustChangePassword`. The Add
User form has a "Require password change at first sign-in" checkbox, ticked by
default, sent as `require_password_change`.

When adding a page:

1. Add the page component under `src/pages/`.
2. Add its route in `App.tsx`.
3. Add the sidebar entry if it is navigable.
4. Add the permission mapping in `pageAccess.ts`.
5. Add or update route/access tests.
6. Update this specification and `Implementation_Status.md`.

## Component ownership

| Path | Responsibility |
|---|---|
| `components/dashboard/` | Dashboard metrics, resource views, alerts, charts, and outage presentation |
| `components/network-health/` | Trend/metric cards, network health summaries, insight panels, and graph modal |
| `components/device-inventory/` | Host/device table; the host detail drawer; `DevicePortsSection` (a device's ports in groups with the reason each is or is not monitored, and the Monitor / Acknowledge / Ignore / Stop / Leave suggested / Resume / Set service / Remove pin actions with confirmations), `SetServiceDialog`, and `devicePortsLogic.ts` (grouping, which actions apply, wording); `DeviceMonitoringSection` (the monitoring label, its reason and Pause / Resume with confirmation) and `monitoringState.ts` (labels, reasons, styles, filter options). Data comes from `lib/devicePortsApi.ts`, `lib/deviceMonitoringApi.ts` and `hooks/useDevicePorts.ts` |
| `components/plugin-manager/` | Plugin inventory table, details drawer (enable preview dialog, "Not service-driven" state, attach notices), `PluginServicesSection` (paginated, searchable monitored services with status chips and Stop/Resume), `PluginCustomChecksSection` and `CustomCheckDialog` (a plugin's custom checks with Add, Change, Pause/Resume and Remove, shown only to `plugin.custom_check`, and only for plugins whose details report `custom_checks.supported`; password fields are masked, write-only and say where the password ends up; the drawer's "Not service-driven" note says why other plugins take none; for a plugin whose `custom_checks.target` is `server` the section is titled "Server checks" and the dialog has no device picker), and the disabled custom-upload modal |
| `components/ncpa-deployment/` | NCPA device table, deploy wizard, run banner, history table, run drawer, outcome badges and the header bell item |
| `components/plugins/` | Older installed/available plugin table components; do not assume these drive the current page |
| `components/reports/` | Host availability and network-services report tables |
| `components/manage-accounts/` | Account management table/UI |
| `components/settings/` | General, security, and system settings controls; the Network Discovery tab edits networks, scan ports and one Port → Service table per protocol (NCPA's port fixed, each entry showing the check it leads to); the Plugins tab (`PluginSettings`) shows one editable table per installed plugin: SNMP OIDs (description, OID) once `check_snmp` is installed and NCPA metrics (description, metric path, optional warning, critical, units, query args) once `check_ncpa` is installed. Cells edit in place, Add appends an empty row, rows can be removed, Reset restores the `config.py` defaults; each table warns when its plugin is not Enabled/Active and that a new or renamed description starts a new Nagios service; the Email tab (`EmailSettings`) edits the Gmail account notification mail uses: a locked Gmail preset (`smtp.gmail.com`, 587, STARTTLS), the Gmail address, a sender that follows it (warning when changed, because Gmail rewrites From), an "App password" field (`xxxx xxxx xxxx xxxx`, sent exactly as typed, write-only, blank keeps the saved one) with help text and a new-tab link to `https://myaccount.google.com/apppasswords`, and a "Send test email" card that shows a plain-language message for each failure (rejected login, blocked port, unknown host) with a technical explanation and the server's own response under "Details" |
| `components/layout/` | Authenticated application shell and global session/access behavior |
| `components/shared/` | Reusable headers, summary cards, export menu, alerts sidebar, and rescan modal |

## Contexts, hooks, types, and utilities

- `CurrentUserContext` loads `/api/user/me` and exposes identity/permissions.
- `SystemSettingsContext` merges the system singleton with per-user preferences,
  handles optimistic version conflicts, and supplies `dashboardRefreshRate` and
  `scanFrequency`.
- `useNetworkRescan` starts and polls network discovery.
- `useNcpaDeploymentStatus` polls the latest NCPA run (2 s running, 15 s idle)
  for the page and the header bell, which shows a dedicated deployment item
  for users with `system.deploy.ncpa`. NCPA wrappers live in
  `src/lib/ncpaDeploymentApi.ts`; `ApiError.data` carries an error envelope's
  `data`.
- `types/` owns TypeScript API records, view models, and conversion functions.
- `formatDateTime.ts` applies display preferences to timestamps. The Time Zone preference is a fixed UTC offset or `Browser` (the viewer's own zone). `parseServerDate` reads API timestamps that carry no offset as UTC. Components get formatters from `hooks/useDisplayTime.ts`; do not call `toLocaleString` for displayed times.
- `exportData.ts` performs client-side exports and records export actions.

## Frontend rules

- Use TypeScript; source components use `.tsx`, utilities use `.ts`.
- Page components live in `src/pages/`; subcomponents live under the matching
  `src/components/<feature>/` directory.
- Use the shared API client or a focused wrapper built on it.
- Use `/api/system/`, `/api/user/`, or `/api/plugin/` paths exactly as mounted by
  Flask. Do not omit the `/api` prefix in client code.
- Use `SystemSettingsContext` for refresh and display preferences; do not
  hardcode refresh intervals.
- Preserve loading, empty, access-denied, and error states required by the
  relevant page specification.
- Do not introduce new mock data when an API exists. Remove stale mock imports
  when connecting a feature.
- Service names in URL paths must be encoded, and backend routes must retain the
  Flask `path` converter because names may contain `/`.
