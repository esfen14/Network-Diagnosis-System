# Frontend Modules and Routes

**Last verified against the repository:** 2026-09-27

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
| `/login` | `LoginPage` | Public | Connected to `/api/user/login` |
| `/dashboard` | `DashboardPage` | `system.dashboard` | Connected to dashboard, trends, service, and acknowledgement APIs |
| `/network-health` | `NetworkHealthPage` | `system.network_health` | Connected to summary and trends APIs; detailed host/service UI is supplied elsewhere |
| `/device-inventory` | `DeviceInventoryPage` | `system.network_health` | Connected to the latest-host endpoints and acknowledgement API |
| `/topology` | `TopologyPage` | `system.network_health` | Still routed and shown as “System Status”; excluded from current product scope and must be removed from navigation/routing while retaining source |
| `/plugins` | `PluginsPage` | `plugin.view` | Connected to Plugin Manager inventory, running checks, details, scanning, and mutation APIs |
| `/reports` | `ReportsPage` | `system.report` | Connected for host availability and network-services views; backend exposes additional report routes |
| `/system-logs` | `SystemLogsPage` | `system.logs` | Connected to five log categories |
| `/accounts` | `ManageAccountsPage` | `account.view` | Connected to account/role APIs |
| `/manage-roles` | `ManageRolesPage` | `role.view` | Connected to role and permission APIs |
| `/settings` | `SettingsPage` | Any logged-in user; tabs are separately gated | Connected to system settings and user preferences |
| `/` | Redirect | — | Redirects to `/login` |
| unmatched path | Redirect | — | Redirects to `/login` |

There is no routed Alerts & Notifications History page yet, even though its
backend routes exist.

## Page access rules

`src/lib/pageAccess.ts` is the client route-to-permission map. The sidebar hides
pages the user cannot access, and `PageAccessGuard` prevents direct URL access.
This is usability protection only; backend permission checks remain mandatory.

The Settings page is generally available to logged-in users. Its Security and
System tabs require `settings.security` and `settings.system`, respectively.

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
| `components/device-inventory/` | Host/device table |
| `components/plugin-manager/` | Current Plugin Manager inventory, checks, details, custom upload, and configuration UI |
| `components/plugins/` | Older installed/available plugin table components; do not assume these drive the current page |
| `components/reports/` | Host availability and network-services report tables |
| `components/manage-accounts/` | Account management table/UI |
| `components/settings/` | General, security, and system settings controls |
| `components/layout/` | Authenticated application shell and global session/access behavior |
| `components/shared/` | Reusable headers, summary cards, export menu, alerts sidebar, and rescan modal |

## Contexts, hooks, types, and utilities

- `CurrentUserContext` loads `/api/user/me` and exposes identity/permissions.
- `SystemSettingsContext` merges the system singleton with per-user preferences,
  handles optimistic version conflicts, and supplies `dashboardRefreshRate` and
  `scanFrequency`.
- `useNetworkRescan` starts and polls network discovery.
- `types/` owns TypeScript API records, view models, and conversion functions.
- `formatDateTime.ts` applies display preferences to timestamps.
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
