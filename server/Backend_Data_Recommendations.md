# Backend Data Recommendations for Frontend

This document defines what data the backend should expose to the frontend,
derived from the plugin output structures in `Plugins_List.md` and the database
schema in `history_models.py` and `system_models.py`.

---

## 1. Dashboard / Overview

The frontend needs a high-level snapshot on load. The backend should provide:

### 1.1 Nagios Program Status
Source: `PROGRAM_STATUS` table

| Field | Type | Notes |
|---|---|---|
| `nagiosPID` | int | Whether Nagios is running |
| `daemonMode` | bool | Is Nagios running as a daemon |
| `programStartTime` | datetime | When Nagios started |
| `enableNotifications` | bool | Global notification switch |
| `enableFlapDetection` | bool | Global flap detection switch |
| `activeHostChecksEnabled` | bool | |
| `activeServiceChecksEnabled` | bool | |
| `passiveHostChecksEnabled` | bool | |
| `passiveServiceChecksEnabled` | bool | |
| `version` | string | Nagios version string |
| `updateAvailable` | bool | Whether a Nagios update is available |
| `newVersion` | string \| null | Version string of the available update |
| `lastUpdateCheck` | datetime | When the last update check occurred |
| `timestamp` | datetime | When this record was written |

### 1.2 Summary Counts
Derived from `HOST_STATUS` and `SERVICE_STATUS` tables.
These give the frontend its at-a-glance counters.

| Field | Type | Notes |
|---|---|---|
| `totalHosts` | int | Total distinct monitored hosts |
| `hostsUp` | int | Hosts in `UP` state |
| `hostsDown` | int | Hosts in `DOWN` state |
| `hostsUnreachable` | int | Hosts in `UNREACHABLE` state |
| `totalServices` | int | Total monitored services |
| `servicesOk` | int | Services in `OK` state |
| `servicesWarning` | int | Services in `WARNING` state |
| `servicesCritical` | int | Services in `CRITICAL` state |
| `servicesUnknown` | int | Services in `UNKNOWN` state |
| `hostsFlapping` | int | Hosts with `Is_Flapping = true` |
| `servicesFlapping` | int | Services with `Is_Flapping = true` |
| `hostsInDowntime` | int | Hosts with `Scheduled_Downtime_Depth > 0` |
| `servicesInDowntime` | int | Services with `Scheduled_Downtime_Depth > 0` |

---

## 2. Host Status List

Source: `HOST_STATUS` + `HOST_PERF_DATA`

Each host entry should contain:

| Field | Type | Notes |
|---|---|---|
| `hostStatusId` | int | Primary key |
| `timestamp` | datetime | When the record was written |
| `hostname` | string | Host identifier |
| `currentState` | enum | `Up`, `Down`, `Unreachable` |
| `pluginStatus` | enum | `Ok`, `Warning`, `Critical`, `Unknown` |
| `pluginOutput` | string | Raw plugin output text (e.g., `PING OK - Packet loss = 0%`) |
| `stateType` | enum | `Soft` or `Hard` |
| `currentAttempt` | int | Current retry attempt number |
| `maxAttempts` | int | Max retries before hard state |
| `lastCheck` | datetime | |
| `nextCheck` | datetime | |
| `lastStateChange` | datetime \| null | |
| `lastHardStateChange` | datetime \| null | |
| `lastTimeUp` | datetime \| null | |
| `lastTimeDown` | datetime \| null | |
| `lastTimeUnreachable` | datetime \| null | |
| `checkLatency` | float | Seconds |
| `checkExecutionTime` | float | Seconds |
| `isFlapping` | bool | |
| `acknowledgementType` | enum | `No Acknowledgement`, `Normal Acknowledgement`, `Sticky Acknowledgement` |
| `scheduledDowntimeDepth` | int | 0 means no downtime scheduled |
| `notificationEnabled` | bool | |
| `perfData` | array | See §2.1 below |

### 2.1 Host Performance Data (nested in host entry)
Source: `HOST_PERF_DATA`

Each item in `perfData`:

| Field | Type | Notes |
|---|---|---|
| `metric` | string | e.g., `rta`, `pl`, `load1` |
| `measuredValue` | float | The current value |
| `unit` | string \| null | e.g., `ms`, `%`, `s`, `MB` |
| `warningThreshold` | float \| null | |
| `criticalThreshold` | float \| null | |
| `minimum` | float \| null | |
| `maximum` | float \| null | |

---

## 3. Service Status List

Source: `SERVICE_STATUS` + `SERVICE_PERF_DATA`

Each service entry should contain:

| Field | Type | Notes |
|---|---|---|
| `serviceStatusId` | int | Primary key |
| `timestamp` | datetime | When the record was written |
| `hostname` | string | Which host this service belongs to |
| `service` | string | Service name / plugin name (e.g., `check_ping`, `check_http`) |
| `currentState` | enum | `Ok`, `Warning`, `Critical`, `Unknown` |
| `pluginOutput` | string | Raw plugin output text |
| `stateType` | enum | `Soft` or `Hard` |
| `currentAttempt` | int | |
| `maxAttempts` | int | |
| `lastCheck` | datetime | |
| `nextCheck` | datetime | |
| `lastStateChange` | datetime \| null | |
| `lastHardStateChange` | datetime \| null | |
| `lastTimeOk` | datetime \| null | |
| `lastTimeWarning` | datetime \| null | |
| `lastTimeCritical` | datetime \| null | |
| `lastTimeUnknown` | datetime \| null | |
| `checkLatency` | float | Seconds |
| `checkExecutionTime` | float | Seconds |
| `isFlapping` | bool | |
| `acknowledgementType` | enum | `No Acknowledgement`, `Normal Acknowledgement`, `Sticky Acknowledgement` |
| `scheduledDowntimeDepth` | int | |
| `notificationEnabled` | bool | |
| `perfData` | array | See §3.1 below |

### 3.1 Service Performance Data (nested in service entry)
Source: `SERVICE_PERF_DATA`

Same shape as Host Performance Data (§2.1):

| Field | Type | Notes |
|---|---|---|
| `metric` | string | e.g., `time`, `size`, `load1`, `swap`, `pl` |
| `measuredValue` | float | |
| `unit` | string \| null | |
| `warningThreshold` | float \| null | |
| `criticalThreshold` | float \| null | |
| `minimum` | float \| null | |
| `maximum` | float \| null | |

---

## 4. Plugin-Specific Performance Metrics Reference

The following table maps each plugin to the metrics expected in `perfData`.
This helps the frontend know what metrics to expect for a given service name
so it can render the right charts or labels.

| Plugin | Metric(s) | Unit(s) |
|---|---|---|
| `check_ping` / `check_icmp` / `check_fping` | `rta`, `pl` | `ms`, `%` |
| `check_http` | `time`, `size`, `time_connect`, `time_first_byte`, `time_transfer` | `s`, `B` |
| `check_tcp` / `check_smtp` / `check_ssh` | `time` | `s` |
| `check_dns` / `check_dig` | `time` | `s` |
| `check_load` | `load1`, `load5`, `load15` | *(none)* |
| `check_disk` | `/{mount}`, `/{mount}_inode_percent`, `/{mount}_inode_used`, `/{mount}_inode_free` | `B`, `%` |
| `check_swap` | `swap` | `MB` |
| `check_users` | `users` | *(none)* |
| `check_procs` | `procs`, `procs_warn`, `procs_crit`, `procvsz`/`procrss`/`procpcpu`/`procseconds` | *(varies)* |
| `check_uptime` | `uptime` | *(seconds)* |
| `check_ntp_time` / `check_ntp_peer` | `offset`, `jitter`, `stratum` | `s` |
| `check_ldap` | `time`, `entries` | `s` |
| `check_pgsql` | `time` | `s` |
| `check_mysql` | `Connections`, `Queries`, `Threads_connected`, `Threads_running`, `Uptime`, etc. | `c`, `s` |
| `check_snmp` | varies by OID | varies |
| `check_ups` | `voltage`, `battery`, `load`, `temp`, `left` | `V`, `%`, *(none)* |
| `check_apt` | `available_upgrades`, `critical_updates` | *(none)* |
| `check_ifstatus` | `up`, `down`, `dormant`, `excluded`, `unused` | *(none)* |
| `check_mrtgtraf` | `in`, `out`, `in_pct`, `out_pct` | varies, `%` |
| `check_ncpa` | varies (passthrough from NCPA agent) | varies |
| `check_dbi` | `conntime`, `querytime` | `s` |
| `check_sensors` | *(none — status only)* | — |

> Note: Plugins that produce no performance data (`check_breeze`, `check_by_ssh`,
> `check_cluster`, `check_dhcp`, `check_dummy`, `check_hpjd`, `check_ide_smart`,
> `check_nagios`, `check_radius`, `check_real`, `check_rpc`, `check_ssl_validity`,
> `check_wave`) will have an empty `perfData` array.

---

## 5. Network Discovery Data

### 5.1 Discovery Run Status
Source: `NETWORK_DISCOVERY_STATUS`

| Field | Type | Notes |
|---|---|---|
| `discoveryStatusId` | int | |
| `status` | enum | `Running`, `Success`, `Failed`, `Interrupted` |
| `progress` | int | 0–100 percentage |
| `message` | string | Human-readable status message |
| `startAt` | datetime | |
| `completedAt` | datetime \| null | |
| `error` | string \| null | Error message if failed |

### 5.2 Discovered Device
Source: `NETWORK_DISCOVERY`

| Field | Type | Notes |
|---|---|---|
| `netDiscoveryId` | int | |
| `hostname` | string \| null | Resolved hostname |
| `ipAddress` | string | e.g., `192.168.1.10` |
| `network` | string | Subnet, e.g., `192.168.1.0` |
| `macAddress` | string \| null | |
| `osType` | string \| null | e.g., `Linux`, `Windows` |
| `deviceType` | string \| null | e.g., `Router`, `Server`, `Workstation` |
| `ncpaEligible` | bool | Whether NCPA can be deployed |
| `scannedAt` | datetime | |
| `includeDeviceInScanning` | bool | Whether host is included in Nagios monitoring |
| `openTcpPorts` | array | See §5.3 |
| `openUdpPorts` | array | See §5.3 |
| `ncpaDeployment` | object \| null | See §5.4 |

### 5.3 Open Ports (nested in device)
Source: `OPEN_TCP_Services` / `OPEN_UDP_Services`

| Field | Type |
|---|---|
| `portNumber` | int |
| `serviceName` | string |

### 5.4 NCPA Deployment (nested in device)
Source: `NCPA_DEPLOYMENT`

| Field | Type | Notes |
|---|---|---|
| `ncpaDeployId` | int | |
| `deploymentMethod` | enum \| null | `Automatic`, `Manual` |
| `agentStatus` | enum \| null | `Pending NCPA`, `Deployed NCPA`, `Deployment Failed`, `Excluded`, `Incompatible` |
| `error` | string \| null | |

---

## 6. Activity & Audit Logs

### 6.1 Activity Log
Source: `ACTIVITY_LOG` + `USER`

| Field | Type | Notes |
|---|---|---|
| `logId` | int | |
| `actionType` | string | Description of the action |
| `performedAt` | datetime | |
| `userId` | int | |
| `userFullName` | string | `First_Name + Last_Name` from `USER` |

### 6.2 Configuration Changes
Source: `CONFIGURATION_CHANGES`

| Field | Type | Notes |
|---|---|---|
| `confChangesId` | int | |
| `confType` | string | e.g., `host`, `service`, `system` |
| `parameterName` | string | Which setting changed |
| `oldValue` | string | |
| `newValue` | string | |
| `changedAt` | datetime | |
| `logId` | int | FK back to activity log |

### 6.3 Export Log
Source: `EXPORT_LOG`

| Field | Type | Notes |
|---|---|---|
| `exportId` | int | |
| `reportType` | string | What was exported |
| `exportFormat` | enum | `csv`, `pdf` |
| `startDate` | datetime | Report range start |
| `endDate` | datetime | Report range end |
| `exportedAt` | datetime | |

---

## 7. User & Role Management

### 7.1 User
Source: `USER` + `ROLE`

| Field | Type | Notes |
|---|---|---|
| `userId` | int | |
| `firstName` | string | |
| `lastName` | string | |
| `email` | string | |
| `status` | enum | `Active`, `Inactive`, `Suspended` |
| `createdAt` | datetime | |
| `updatedAt` | datetime | |
| `role` | object | See §7.2 |

> **Never include `Hashed_Password` in any response.**

### 7.2 Role (nested in user)
Source: `ROLE`

| Field | Type | Notes |
|---|---|---|
| `roleId` | int | |
| `name` | string | |
| `description` | string \| null | |
| `isActive` | bool | |
| `permissions` | array of string | List of permission names from `PERMISSION` |

---

## 8. System Settings

Source: `SYSTEM_SETTINGS` (singleton — always ID = 1)

The existing `to_dict()` method on `SystemSettings` already serializes this
correctly. The frontend expects the following shape (camelCase):

```json
{
  "systemLanguage": "English",
  "theme": "dark",
  "timeZone": "UTC+08:00",
  "dateTimeFormat": "DD/MM/YYYY",
  "systemFont": "Default",
  "systemFontSize": "medium",
  "dashboardRefreshRate": 5,
  "scanFrequency": 6,
  "dashboardLayout": "default",
  "notifications": true,
  "exportFormats": ["CSV", "PDF"],
  "sessionTimeout": 30,
  "strongPasswordPolicy": true,
  "failedLoginMonitoring": true,
  "auditLogging": true,
  "securityCheckFrequency": "weekly",
  "systemUpdateFrequency": "monthly",
  "maintenanceMode": false,
  "automaticBackups": true,
  "logRetentionDays": 30,
  "diagnosticHistoryRetentionDays": 90,
  "version": 1,
  "updatedAt": "2026-08-26T01:22:44+00:00"
}
```

---

## 9. Notifications

Source: Nagios log / parsed notification events + `NOTIFICATION_CURSOR`

Each notification item:

| Field | Type | Notes |
|---|---|---|
| `id` | string / int | Unique notification identifier |
| `timestamp` | datetime | When the notification was raised |
| `type` | enum | `HOST` or `SERVICE` |
| `hostname` | string | |
| `service` | string \| null | null for host notifications |
| `state` | string | e.g., `DOWN`, `CRITICAL`, `RECOVERY` |
| `message` | string | Notification text / plugin output |
| `isRead` | bool | Derived: `timestamp > last_seen_ts` from `NOTIFICATION_CURSOR` for current user |

The backend should also expose the unread count:

| Field | Type |
|---|---|
| `unreadCount` | int |

---

## 10. Historical Trends (Time-Series)

For charting purposes, the frontend will need time-series queries over past
`HOST_STATUS` and `SERVICE_STATUS` records filtered by host/service and a
time range. The response for each data point should be:

| Field | Type | Notes |
|---|---|---|
| `timestamp` | datetime | |
| `state` | enum | Host or service state at that time |
| `perfData` | array | Same shape as §2.1 / §3.1 |

---

## 11. Pagination & Filtering Conventions

All list endpoints (hosts, services, discovery, logs) should support:

| Query Parameter | Type | Purpose |
|---|---|---|
| `page` | int | Page number (1-indexed) |
| `pageSize` | int | Items per page (default 25) |
| `hostname` | string | Filter by hostname |
| `state` | string | Filter by current state |
| `service` | string | Filter by service name (services only) |
| `from` | datetime (ISO 8601) | Time range start |
| `to` | datetime (ISO 8601) | Time range end |
| `sort` | string | Field to sort by |
| `order` | `asc` / `desc` | Sort direction |

All list responses should include:

```json
{
  "data": [...],
  "total": 150,
  "page": 1,
  "pageSize": 25,
  "totalPages": 6
}
```

---

## 12. SSH Credentials

Source: `SSH_CREDENTIALS`

> Expose only connection metadata — **never expose private key material**.

| Field | Type | Notes |
|---|---|---|
| `sshId` | int | |
| `sshPort` | int | |
| `keyInstalled` | bool | Whether a key has been deployed to the device |
| `keyFingerprint` | string \| null | Public key fingerprint only |
| `createdAt` | datetime \| null | |
| `networkDiscoveryId` | int | FK to the device |
