# Backend Modules and Route Catalog

**Last verified against the repository:** 2026-09-27

## API composition

`server/app/api/__init__.py` mounts the API blueprint at `/api`. Its child
blueprints are:

| Blueprint | Prefix | Owning package |
|---|---|---|
| `user_bp` | `/api/user` | `app/api/user/` |
| `system_bp` | `/api/system` | `app/api/system/` |
| `plugin_bp` | `/api/plugin` | `app/api/plugin/` |

All protected routes use the Flask-Login session cookie. Permission-protected
routes add `@require_permission(...)` to `@login_required` behavior.

The seed command currently defines these permissions:

```text
role.edit, role.view, role.info, role.list
account.view, account.edit, account.info
system.discover, system.deploy.ncpa, system.hosts, system.logs
system.report, system.notifications, system.services, system.network_health
system.acknowledge_alerts, system.dashboard
plugin.scan, plugin.view, plugin.enable, plugin.disable
plugin.command_override, plugin.command_restore, plugin.validate
plugin.custom_add, plugin.update, plugin.update_rollback, plugin.configure
settings.security, settings.system
```

Some seeded permissions are not attached to a current route, and the history
routes require an unseeded `system.history` permission. Those facts are tracked
as current-state inventory rather than treated as intended permission design.

## Response and request conventions

- API routes use `success(...)` and `error(...)` from
  `app/api/helper/responses.py`.
- Success envelope: `{ "success": true, "data": ... }`.
- Error envelope: `{ "success": false, "message": "..." }`.
- A required JSON body is read with `request.get_json()`.
- `request.get_json(silent=True) or {}` is reserved for genuinely optional
  bodies.
- Collection routes generally use `page` and `per_page` and return pagination
  metadata; the route docstring and tests own exact query validation.
- Every route returning user or system data must require login and, where a
  defined permission exists, that permission.

## User API

### `app/api/user/login.py`

| Method and path | Permission | Purpose |
|---|---|---|
| `POST /api/user/login` | Public | Validate credentials and establish a session |
| `POST /api/user/logout` | Login | End the current session |

### `app/api/user/management.py`

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /api/user/permissions/options` | `role.edit` | List permissions available for role editing |
| `POST /api/user/roles` | `role.edit` | Create an active role and assign permissions |
| `GET /api/user/roles` | `role.view` | Paginated role list |
| `GET /api/user/roles/options` | `role.list` | Compact role choices for forms |
| `GET /api/user/roles/<id>` | `role.info` | Role detail and permission set |
| `PUT /api/user/roles/<id>` | `role.edit` | Replace role metadata and permissions |
| `PUT /api/user/roles/<id>/status` | `role.edit` | Change role active status |
| `POST /api/user/accounts` | `account.edit` | Create a user account |
| `GET /api/user/accounts` | `account.view` | Paginated account list |
| `GET /api/user/accounts/<id>` | `account.info` | Account detail |
| `PUT /api/user/accounts/<id>` | `account.edit` | Edit account details/status; users are not deleted. `password`/`confirm_password` are optional (omit to keep the password, so suspend/deactivate needs none). Setting a password on another account, or returning an account to Active from Suspended/Inactive, sets `Must_Change_Password` |
| `GET /api/user/me` | Login | Return the current user, permissions and `must_change_password` |
| `POST /api/user/change-password` | Login | Change the caller's own password (`current_password`, `new_password`, `confirm_password`); clears `Must_Change_Password`. While that flag is set every other `/api` route except login, logout and `/me` returns 403 (`enforce_password_change`). A user whose status is no longer Active is signed out on their next request |

### `app/api/user/preferences.py`

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /api/user/preferences` | Login | Read the caller's display preferences |
| `PUT /api/user/preferences` | Login | Save the caller's display preferences |

## System API

### `app/api/system/settings.py`

The `system_bp` root makes these paths `/api/system`.

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /api/system` | Login | Return singleton system settings |
| `PUT /api/system` | Login, field-level settings permissions | Save the full settings object with optimistic version handling |

Security and system setting fields are restricted with `settings.security` and
`settings.system`; personal fields are handled by `/api/user/preferences`.

### `app/api/system/dashboard.py`

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /api/system/dashboard/status` | `system.dashboard` | Nagios process and monitoring-server resource health |
| `GET /api/system/dashboard/summary` | `system.dashboard` | Host/service counts, active-alert counts, ping and NCPA summaries |
| `GET /api/system/dashboard/alerts` | `system.dashboard` | Active alerts from the latest snapshot, with acknowledgement filters |
| `POST /api/system/dashboard/alerts/acknowledge` | `system.acknowledge_alerts` | Acknowledge one host or service alert |
| `POST /api/system/dashboard/alerts/acknowledge-all` | `system.acknowledge_alerts` | Acknowledge a supplied batch of alerts |
| `DELETE /api/system/dashboard/alerts/acknowledge` | `system.acknowledge_alerts` | Remove one application acknowledgement |
| `GET /api/system/dashboard/notifications` | `system.dashboard` | Return the five latest Nagios notifications |

Detailed fields and behavior are normative in `Display_Requirements.md`.

### `app/api/system/network_health.py`

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /api/system/network-health/summary` | `system.network_health` | Network Health header totals and last-scan information |
| `GET /api/system/network-health/trends` | `system.network_health` | Bucketed ping and NCPA metric trends |
| `GET /api/system/network-health/plugins` | `system.network_health` | Service health grouped by plugin type |

Valid trend windows are `hours=1`, `6`, `24`, or `168`.

### `app/api/system/network_hosts.py`

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /api/system/network-health/hosts` | `system.network_health` | Paginated/filterable latest host snapshot |
| `GET /api/system/network-health/hosts/<hostname>/detail` | `system.network_health` | Host detail panel data |
| `POST /api/system/network-health/hosts/acknowledge` | `system.acknowledge_alerts` | Acknowledge a host alert |
| `DELETE /api/system/network-health/hosts/acknowledge` | `system.acknowledge_alerts` | Unacknowledge a host alert |

### `app/api/system/network_services.py`

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /api/system/network-health/services` | `system.network_health` | Paginated/filterable latest service snapshot |
| `GET /api/system/network-health/services/<hostname>/<path:service_name>/detail` | `system.network_health` | Service detail panel data |
| `POST /api/system/network-health/services/acknowledge` | `system.acknowledge_alerts` | Acknowledge a service alert |
| `DELETE /api/system/network-health/services/acknowledge` | `system.acknowledge_alerts` | Unacknowledge a service alert |

### `app/api/system/history.py`

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /api/system/history/alerts` | `system.history` | Paginated Nagios state-change events |
| `GET /api/system/history/alerts/detail` | `system.history` | Full detail for one alert event |
| `GET /api/system/history/notifications` | `system.history` | Paginated notification events from Nagios and Pinpoint; every item has `source` (`nagios` or `pinpoint`), filterable with `source=`. Pinpoint items are finished network scans (`type: scan`, state SUCCESS/FAILED/CANCELLED) read from `NETWORK_DISCOVERY_STATUS`; host/service/contact/type filters exclude them |
| `GET /api/system/history/notifications/detail` | `system.history` | Full detail for one notification event; Pinpoint events use `source=pinpoint&id=<DiscoveryStatusID>` |

The route implementation exists, but `system.history` is not currently present
in the seed permission list. This is tracked in `Implementation_Status.md`.

### `app/api/system/notifications.py`

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /api/system/notifications` | `system.notifications` | Recent notifications from Nagios (`source: nagios`) and Pinpoint itself (`source: pinpoint`, network scan results) annotated with per-user read state |
| `GET /api/system/notifications/unread-count` | `system.notifications` | Count events after the user's cursor |
| `POST /api/system/notifications/mark-read` | `system.notifications` | Advance the user's notification cursor |

### `app/api/system/network_discovery.py`

| Method and path | Permission | Purpose |
|---|---|---|
| `POST /api/system/discover/start` | `system.discover` | Start a background discovery/config-generation job |
| `GET /api/system/discover/status` | `system.discover` | Current or most recent discovery job status |
| `POST /api/system/network-discovery/stop` | `network.discovery` in current code | Request cancellation of the running discovery job |

The stop-route permission differs from the seeded `system.discover` permission;
this is a documented implementation mismatch, not a recommended convention.

### `app/api/system/ncpa_deployment.py`

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /api/system/deployment/ncpa/devices` | `system.deploy.ncpa` | List NCPA-eligible devices |
| `GET /api/system/deployment/ncpa/<device_id>/fingerprint` | `system.deploy.ncpa` | Fetch live SSH host-key fingerprint |
| `POST /api/system/deployment/ncpa/<device_id>/confirm-trust` | `system.deploy.ncpa` | Store the confirmed fingerprint |
| `POST /api/system/deployment/ncpa/<device_id>/refresh-disks` | `system.deploy.ncpa` | Re-read the agent's logical disks, store them, regenerate the Nagios config |
| `POST /api/system/deployment/ncpa/start` | `system.deploy.ncpa` | Start deployment to one or more devices |
| `POST /api/system/deployment/ncpa/stop` | `system.deploy.ncpa` | Request deployment cancellation |
| `GET /api/system/deployment/ncpa/status` | `system.deploy.ncpa` | Current or most recent deployment status |
| `GET /api/system/deployment/ncpa/devices/trusted` | `system.deploy.ncpa` | List trusted devices ready for deployment |

### `app/api/system/log.py`

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /api/system/log` | `system.logs` | User activity logs |
| `GET /api/system/configurationchange` | `system.logs` | Configuration-change logs |
| `GET /api/system/networkdiscovery` | `system.logs` | Discovery-run logs |
| `GET /api/system/ncpadeployment` | `system.logs` | NCPA deployment logs |
| `POST /api/system/exportlog` | Login | Record an export action |
| `GET /api/system/exportlog` | `system.logs` | Export history |

### `app/api/system/report.py`

| Method and path | Permission | Purpose |
|---|---|---|
| `GET /api/system/report/availability` | `system.report` | Host availability for a period |
| `GET /api/system/report/hosts-by-os` | `system.report` | Host availability grouped by OS |
| `GET /api/system/report/network-services` | `system.report` | Network-wide service health report |
| `GET /api/system/report/device-services` | `system.report` | Per-device service health report |
| `GET /api/system/report/alerts` | `system.report` | Alert events/count from Nagios archives |
| `GET /api/system/report/notifications` | `system.report` | Notification events/count from Nagios archives |

## Plugin API

All routes are implemented in `app/api/plugin/manager.py`; supporting logic is
split across `scanner.py`, `service.py`, `monitoring_config.py`, validators,
command defaults, and update/custom-plugin modules.

| Method and path | Permission | Purpose |
|---|---|---|
| `POST /api/plugin/scan` | `plugin.scan` | Start plugin-directory scan |
| `GET /api/plugin/scan/status` | `plugin.scan` | Read latest scan status |
| `GET /api/plugin` | `plugin.view` | Paginated plugin inventory |
| `GET /api/plugin/running` | `plugin.view` | Checks currently configured in Nagios |
| `GET /api/plugin/summary` | `plugin.view` | Plugin-manager summary counts |
| `GET /api/plugin/history` | `plugin.view` | Plugin audit/history records |
| `GET /api/plugin/<plugin_id>` | `plugin.view` | Plugin detail |
| `GET /api/plugin/<plugin_id>/commands` | `plugin.view` | Commands and active overrides |
| `GET /api/plugin/<plugin_id>/dependencies` | `plugin.view` | Dependency status |
| `POST /api/plugin/<plugin_id>/enable` | `plugin.enable` | Enable a plugin, then apply it to every monitoring target (`apply_running_plugins_to_all_targets`: one rebuild of `plugin-services.cfg`, status becomes Active). The same sync runs after every successful network discovery so new hosts pick up running plugins. A failed auto-apply does not undo the enable; the response carries `auto_apply` |
| `POST /api/plugin/<plugin_id>/disable` | `plugin.disable` | Disable a plugin |
| `POST /api/plugin/<plugin_id>/commands/<command_id>/override` | `plugin.command_override` | Save a command override |
| `POST /api/plugin/<plugin_id>/commands/<command_id>/restore-default` | `plugin.command_restore` | Disable the active override |
| `GET /api/system/network-profile` | `system.network_health` | Editable network name, reference tag and detail rows for the Network Health card (defaults until saved) |
| `PUT /api/system/network-profile` | `settings.discovery` | Save the network profile (descriptive only) |
| `POST /api/plugin/<plugin_id>/validate` | `plugin.validate` | Validate executable, permissions, and dependencies |
| ~~`POST /api/plugin/custom`~~ | `plugin.custom_add` | **Disabled** — route commented out in `manager.py` (and the client call in `pluginApi.ts`); not part of the current release |
| `POST /api/plugin/<plugin_id>/update` | `plugin.update` | Update from an archive |
| `POST /api/plugin/<plugin_id>/update/rollback` | `plugin.update_rollback` | Restore the backed-up version |
| `GET /api/plugin/<plugin_id>/configurations` | `plugin.view` | List monitoring targets/configurations |
| `POST /api/plugin/<plugin_id>/configurations` | `plugin.configure` | Validate and apply a target configuration to Nagios |

## Non-route backend modules

| Module | Responsibility |
|---|---|
| `api/system/statistics.py` | Shared current-state aggregation for dashboard and network health; never a blueprint |
| `api/helper/responses.py` | Standard response envelopes |
| `api/helper/validation.py` | Shared guard-clause validation and permission decorator |
| `api/helper/settings_flags.py` | Reads security/logging/session settings without importing route modules |
| `api/helper/database_access/` | User, role, and permission lookup helpers |
| `api/commands/seed.py` | Seeds permissions, roles, settings, and development users |
| `nagios/status.py` | Polls status/object CGI data and writes snapshot models |
| `api/plugin/plugin_descriptions.py` | One-line descriptions for the 58 bundled plugins; the scan fills a plugin's empty `Description` from it, and never overwrites an edited one |
| `nagios/notifications.py` | Queries archive CGI alerts and notification events |
| `nagios/pinpoint_events.py` | Pinpoint's own notifications (finished network scans) shaped like notification events |
| `network_discovery/` | Scans networks and builds/applies host/service configuration |
| `ncpa_deployment/` | Fingerprint-pinned SSH workflow and remote NCPA installation |
| `logging/` | Writes activity and subsystem audit records |
| `scheduler.py` | Polling, retention purge, and automation scheduling |
| `automation.py` | Settings-driven discovery, plugin/security checks, and database backups |

## Shared statistics contract

`statistics.py` exposes `get_latest_hosts()`, `get_latest_services()`,
`host_counts()`, `service_counts()`, `active_alert_count()`,
`avg_ping_metrics()`, `ncpa_averages()`, `nagios_server_resources()`,
`service_health_by_plugin()`, and `perf_trends()`.

The Nagios server host is identified by the statistics module's `NAGIOS_HOST`
constant (`localhost` for status snapshots). Do not confuse it with
`Config.NAGIOS_HOST`, which is the network address used to construct CGI URLs.
