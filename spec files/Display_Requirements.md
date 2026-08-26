# Display Requirements — Dashboard & Network Health
**Detech-IT / 4D-G2 Capstone**
**Last Updated:** 2026-08-26 (rev. 3 — updated §2.5 plugin key derivation to reflect command map lookup)

---

## Purpose

This document defines what data should be displayed on the **Dashboard** and
**Network Health** pages, how it should be grouped, and what kind of visual
component is appropriate for each piece of data. It does not dictate specific
implementation — front-end developers have full creative liberty over layout,
color, and component details. Recommendations here are functional, not visual.

The goal of both pages is to make Nagios data digestible for network
administrators who are already in the industry but do not have the time or
expertise to interpret raw Nagios output directly. Nagios' native web UI will
be disabled — this system is the only interface to Nagios data.

---

## Definitions

| Term | Meaning in this system |
|---|---|
| **Alert** | Any host or service currently **not** in an OK/UP state (WARNING, CRITICAL, UNKNOWN, DOWN, UNREACHABLE). This is the live problem state, not a notification event. |
| **Notification** | A Nagios-generated contact event (email, SMS, etc.) sent on a state change. Tracked separately from alerts. |
| **NCPA host** | A monitored host with the NCPA agent deployed. Exposes resource metrics (CPU, disk, memory) via the NCPA API, accessed through `check_ncpa` services. |
| **Nagios server** | The machine running Nagios itself. Its own resource health is monitored by local standalone plugins (`check_load`, `check_disk`, `check_swap`) and is separate from NCPA host metrics. |
| **Always-visible metric** | A metric shown on the dashboard regardless of which plugins are configured, because it is universally relevant to any monitored network. |
| **Conditional metric** | A metric shown only when the relevant plugin or agent is present in the monitored network. |

---

## Data Sources

All data comes from the backend API. The relevant sources per section are
documented in `Backend_Data_Recommendations.md`. This document only defines
*what* to show and *how* to group it — not API structure.

---

## 1. Dashboard Page

### Goal
Give the user an immediate answer to: **"Is anything broken right now, and how
is the network doing overall?"** The dashboard is the first page seen after
login. It should be scannable in under 10 seconds. No deep analysis — that
belongs on Network Health.

---

### 1.1 Monitoring System Status

A section at the top of the page dedicated to the health of the monitoring
system itself. Always visible. This is distinct from the health of the network
being monitored.

**Nagios process data to show:**

| Field | Notes |
|---|---|
| Nagios process state | Running / Not Running |
| Nagios version | |
| Nagios uptime / start time | When the Nagios process last started |
| Last status update | When Nagios last wrote its status data |
| Active host checks enabled | Yes / No |
| Active service checks enabled | Yes / No |
| Notifications globally enabled | Yes / No |
| Flap detection enabled | Yes / No |

**API field name:** `enable_flap_detection` (bool) on the `nagios` object returned by
`GET /system/dashboard/status`. See §API Response Shapes below.

**Nagios server resource data to show** (from local `check_load`, `check_disk`,
`check_swap` services on the Nagios host):

| Metric | Source plugin | Unit | Notes |
|---|---|---|---|
| CPU load (1 min) | `check_load` → `load1` | — | Load average of the Nagios server |
| CPU load (5 min) | `check_load` → `load5` | — | |
| Disk usage | `check_disk` | % used | Per monitored mount point on the Nagios host |
| Swap usage | `check_swap` | % used | |

**Purpose:** If Nagios is not running, or its server is resource-exhausted, all
other data on the page is unreliable. The user must be able to see this at a
glance before trusting anything else.

**Behavior:**
- This section always renders on the dashboard. It is never hidden.
- If the Nagios process is not running, show a prominent warning that makes
  clear all displayed data may be stale.
- If a local resource check is not configured on the Nagios host (e.g.,
  `check_load` is absent), show a "plugin not configured" message in place of
  that metric's value rather than hiding the field. This signals to the user
  that the metric exists and can be enabled, rather than leaving them unaware
  the feature is available.

**Recommended component:** A status bar or compact card at the top of the page.
Should not dominate the layout — it is context, not the main focus.

**API — `GET /system/dashboard/status` response shape:**

```json
{
    "nagios": {
        "running":               true,
        "pid":                   12345,
        "version":               "4.4.6",
        "program_start_time":    "2026-08-25T10:00:00+00:00",
        "last_status_update":    "2026-08-26T16:30:00+00:00",
        "active_host_checks":    true,
        "active_service_checks": true,
        "notifications_enabled": true,
        "enable_flap_detection": true
    },
    "server_resources": {
        "cpu_load": {
            "configured": true,
            "load1":  0.42,
            "load5":  0.38,
            "load15": 0.31
        },
        "disk": {
            "configured": true,
            "mounts": [
                { "mount": "/", "used_bytes": 12345678, "warn": 10000000, "crit": 15000000 },
                { "mount": "/boot", "used_bytes": 345678, "warn": null, "crit": null }
            ]
        },
        "swap": {
            "configured": true,
            "swap_used_mb": 128.0,
            "warn": 512.0,
            "crit": 1024.0
        }
    }
}
```

All nullable fields are `null` when the plugin is not configured
(`configured: false`) or when no Nagios status data has been received yet.

---

### 1.2 Summary Stat Cards

Four at-a-glance counters giving the user the size and overall state of the
monitored network. Always visible.

| Card | Primary value | Supporting detail |
|---|---|---|
| Total Hosts | Count of all monitored hosts | X up, X down, X unreachable |
| Total Services | Count of all monitored services | X ok, X warning, X critical, X unknown |
| Active Alerts | Count of hosts + services currently not in OK/UP state | X critical, X warning, X unknown |
| Hosts in Downtime | Count of hosts with scheduled downtime currently active | Can include services in downtime as a sub-count |

**Notes:**
- "Active Alerts" is the most important card. It should be visually prominent
  when its count is non-zero, and clearly positive/green when the count is zero
  (i.e., "all clear" is a meaningful state, not just the absence of a problem).
- Flapping hosts and services are a secondary concern. Show flapping counts as
  a badge or footnote on the Hosts or Services card rather than a separate card.

**API — `GET /system/dashboard/summary` response shape:**

```json
{
    "hosts": {
        "total":       22,
        "up":          20,
        "down":         1,
        "unreachable":  1,
        "flapping":     0,
        "in_downtime":  2
    },
    "services": {
        "total":       148,
        "ok":          140,
        "warning":       4,
        "critical":      3,
        "unknown":       1,
        "flapping":      0,
        "in_downtime":   5
    },
    "active_alerts": {
        "total":    8,
        "critical": 4,
        "warning":  3,
        "unknown":  1
    },
    "ping_metrics": {
        "configured":          true,
        "avg_rta_ms":          12.3,
        "avg_packet_loss_pct": 0.5,
        "host_count":          20
    },
    "ncpa_metrics": null
}
```

`ping_metrics` notes:
- `configured: false` when no `rta`/`pl` perf data exists in `HostPerfData`
  (see §3.6 — ping runs as the host check, not as a separate service).
- When `host_count < 2`, `avg_rta_ms` and `avg_packet_loss_pct` are `null`
  and `insufficient_data: true` is added to the object.

`ncpa_metrics` is `null` when no NCPA services are deployed (hide the UI
block entirely). When NCPA data is present:
```json
{
    "ncpa_host_count":  12,
    "total_host_count": 22,
    "avg_cpu_pct":      45.2,
    "avg_disk_pct":     61.0,
    "avg_memory_pct":   52.8
}
```
Any average field is `null` when fewer than 2 data points are available.

**Recommended component:** Stat cards / metric tiles.

---

### 1.3 Always-Visible Network Metrics

Metrics that are shown regardless of which plugins are deployed, because they
represent the most fundamental view of network reachability. Values shown are
**network-wide averages** across all hosts that have a ping or ICMP check
configured.

| Metric | Source plugin | Unit |
|---|---|---|
| Average Latency (RTA) | `check_ping`, `check_icmp`, `check_fping` → `rta` | ms |
| Average Packet Loss | `check_ping`, `check_icmp`, `check_fping` → `pl` | % |

**Behavior:**
- This section always renders on the dashboard. It is never hidden.
- If no ping/ICMP checks are configured for any host, show a "plugin not
  configured" message in place of the value, e.g.:
  "Plugin not configured — add `check_ping` or `check_icmp` to a host to
  see latency and packet loss data."
- Averaging logic: only include hosts that have reported data within the last
  check cycle. Note how many hosts are included (e.g., "avg. across 18 hosts").

**Implementation note — data source for ping metrics:**
In Pinpoint, `check_ping` (or `check_icmp`) is configured as the **host check**
rather than as a separate service. This means ping `rta` and `pl` metrics land
in `HostPerfData` (linked to `HostStatus` rows), not in `ServicePerfData`.
The `avg_ping_metrics()` function in `statistics.py` queries `HostPerfData`
accordingly. Front-end developers do not need to handle this distinction — the
backend resolves it — but it is relevant context for anyone writing tests or
extending the data layer.

**Recommended component:** Metric tiles or a compact metric strip. Can be
grouped with or near the Summary Stat Cards (§1.2) since they are all
high-level numbers.

---

### 1.4 Conditional Resource Metrics (NCPA Hosts)

Shown only when at least one host in the network has NCPA deployed and has
active `check_ncpa` services reporting resource data. Values are
**network-wide averages** across all NCPA-enabled hosts with recent data.

These are **not** the same as the Nagios server's own resources (§1.1). These
metrics represent the devices being monitored.

| Metric | Source | NCPA metric path (example) | Unit |
|---|---|---|---|
| Average CPU usage | `check_ncpa` | `cpu/percent` | % |
| Average disk usage | `check_ncpa` | `disk/logical/{drive}/used_percent` | % |
| Average memory usage | `check_ncpa` | `memory/virtual/percent` | % |

**Notes:**
- NCPA services are registered in Nagios with descriptions that include a
  qualifier suffix: `ncpa_cpu_usage-5693-TCP`, `ncpa_memory_usage-5693-TCP`,
  `ncpa_disk_usage-5693-TCP` (or the per-partition form `ncpa-5693-TCP-disk_usage_/`).
  All of these variants resolve to the `check_ncpa` plugin key via the
  command map lookup in `statistics.py` (see §2.5 for full derivation logic).
  The backend is responsible for this normalisation — the front-end always
  sees a single `NCPA` group with combined CPU, memory, and disk data.
- If NCPA is deployed on some hosts but not all, note the coverage:
  "avg. across 12 of 30 hosts — 18 hosts have no NCPA data."
- If no hosts have NCPA deployed, show a message:
  "Resource metrics (CPU, disk, memory) require NCPA to be deployed on
  monitored hosts." Do not show empty gauges.

**Recommended component:** Gauge charts or percentage tiles for the current
average. These suit 0–100% values well. Keep them visually grouped together
and distinct from the always-visible metrics.

---

### 1.5 Service State Summary

A proportional view of the overall health of all services in the network.
Answers "what fraction of my services are healthy right now?" at a glance.

**Data to show:**
- Count and percentage of all services in each state: OK, WARNING, CRITICAL,
  UNKNOWN
- Same breakdown for hosts: UP, DOWN, UNREACHABLE

**Recommended component:** A donut/ring chart or a stacked horizontal bar.
The visual proportion matters here more than the raw numbers — the numbers are
already in §1.2. This section adds the "shape" of the problem.

---

### 1.6 Active Alerts Feed

A live list of all hosts and services currently in a problem state. This is
the most actionable section of the dashboard. "Active" means right now — not
historical.

**Data source:** `archivejson.cgi` `alertlist` query (last 7 days). The backend
reduces the full event list to the **most recent event per (hostname, service)**
and keeps only those entities whose latest state is still a problem state
(not OK / UP / RECOVERY). This gives a live view of what is currently broken,
sourced directly from Nagios' own alert history rather than the `history.db`
snapshots.

**Data to show per row:**

| Field | Notes |
|---|---|
| Host name | |
| Service name | Blank / null for host-level alerts |
| Current state | WARNING / CRITICAL / UNKNOWN / DOWN / UNREACHABLE |
| State type | SOFT or HARD (if provided by Nagios); null otherwise |
| Timestamp | UNIX timestamp of the state-change event from Nagios |
| Duration | Seconds elapsed since the state-change event |
| Plugin output | Raw plugin output text, e.g., "PING CRITICAL — Packet loss = 100%" |
| Acknowledged | Visual indicator if this alert has been acknowledged via the app (see §4) |
| Downtime | Visual indicator if the host/service is in scheduled downtime |

**Behavior:**
- Sort order applied by the API: downtime last → then by severity (CRITICAL/DOWN
  first, WARNING next, UNKNOWN/UNREACHABLE last) → then unacknowledged before
  acknowledged of the same severity → then longest duration first within each group.
  This means "new, unnoticed, severe problems" always float to the top.
- The `limit` query param controls how many rows are returned (default 15, max 100).
  Provide a "View all" link to the full service/host status tables on Network Health.
- Acknowledged alerts remain visible but are visually de-emphasized
  (e.g., muted colors). Hiding acknowledged alerts removes important context.
- Hosts/services in scheduled downtime are placed at the very bottom of the list,
  since downtime is expected and less urgent.
- If there are no active alerts, show a clear positive message:
  "All hosts and services are healthy." This is not an empty state — it is
  meaningful information.

**Query params for `GET /system/dashboard/alerts`:**

| Param | Values | Default | Notes |
|---|---|---|---|
| `limit` | 1–100 | 15 | Max rows returned |
| `ack_filter` | `all` \| `unacknowledged` \| `acknowledged` | `all` | Filter by app-side ack state |

**API — `GET /system/dashboard/alerts` response shape:**

```json
{
    "alerts": [
        {
            "type":              "host",
            "hostname":          "router-01",
            "service_name":      null,
            "state":             "DOWN",
            "state_type":        "HARD",
            "timestamp":         1724688000,
            "duration_seconds":  3720,
            "plugin_output":     "PING CRITICAL - Packet loss = 100%",
            "in_downtime":       false,
            "ack": null
        },
        {
            "type":              "service",
            "hostname":          "web-01",
            "service_name":      "http-80-TCP",
            "state":             "WARNING",
            "state_type":        "SOFT",
            "timestamp":         1724691600,
            "duration_seconds":  120,
            "plugin_output":     "HTTP WARNING: Response time 4.2s",
            "in_downtime":       false,
            "ack": {
                "comment":         "Looking into it",
                "acknowledged_by": "Jane Doe",
                "acknowledged_at": "2026-08-26T16:29:00+00:00"
            }
        }
    ],
    "total_shown": 2
}
```

Note: unlike the host/service detail panels (§2.2, §2.3), the alerts feed does
not include a `nagios_ack` field. The `archivejson.cgi` alertlist does not carry
Nagios' own acknowledgement type. The `ack` object reflects the application's
acknowledgement record only (see §4).

**Recommended component:** A compact table or feed list. Rows should be dense
enough to show 10+ items without scrolling on a standard monitor. Plugin output
can be truncated with a tooltip or expand option.

---

### 1.7 Recent Notifications

A short list of the most recent Nagios notification events. This is distinct
from active alerts — notifications are events that were sent to contacts
(e.g., an email was sent when a host went DOWN). A host can be DOWN without
a notification having been sent, and a notification can exist for a host that
has since recovered.

**Data to show per row:**

| Field | API field | Notes |
|---|---|---|
| Timestamp | `timestamp` | UNIX timestamp from Nagios archivejson |
| Type | `type` | `"HOST"` or `"SERVICE"` |
| Host / Service | `hostname`, `service_name` | `service_name` is `null` for host notifications |
| State at notification time | `state` | Sourced from `notificationreason`; falls back to Nagios `state` field if `notificationreason` is absent |
| Contact | `contact` | The Nagios contact that received the notification |
| Message | `message` | Notification text, truncated to 200 characters |

**Behavior:**
- Show the 5 most recent notifications.
- Link to the full notification history page.
- This section is secondary to the Active Alerts feed. It should not compete
  with §1.6 for visual weight.

**API — `GET /system/dashboard/notifications` response shape:**

```json
{
    "notifications": [
        {
            "timestamp":    1724688000,
            "type":         "HOST",
            "hostname":     "router-01",
            "service_name": null,
            "state":        "DOWNTIMESTART",
            "contact":      "admin",
            "message":      "Host router-01 entered scheduled downtime."
        },
        {
            "timestamp":    1724684400,
            "type":         "SERVICE",
            "hostname":     "web-01",
            "service_name": "http-80-TCP",
            "state":        "CRITICAL",
            "contact":      "admin",
            "message":      "HTTP CRITICAL: Response code = 503"
        }
    ]
}
```

`state` is populated from Nagios' `notificationreason` field. If
`notificationreason` is absent in the Nagios response, the raw `state` field
is used instead. Examples of `notificationreason` values: `"PROBLEM"`,
`"RECOVERY"`, `"DOWNTIMESTART"`, `"DOWNTIMEEND"`, `"ACKNOWLEDGEMENT"`.

**Recommended component:** A compact list or mini-feed. Not a full table.

---

### Dashboard — What Does Not Belong Here

The following are intentionally excluded. They belong on Network Health or
dedicated pages:

- Per-host or per-service performance charts and trends
- Full paginated host/service status tables
- Plugin configuration or installation
- Network discovery and device inventory
- Historical time-series data
- Per-host resource breakdowns
- Full notification history

---

## 2. Network Health Page

### Goal
Give the user a **deeper view of how the network and its services are
performing**. The user arrives here when they want to go beyond the summary
counts — to investigate a specific host or service, understand trends over
time, or get a breakdown by plugin type.

This page has more data than the dashboard, but it should still be organized
so the user can find what they need quickly. Group related data together.

---

### 2.1 Page-Level Summary Strip

A compact header repeating the core counts from the dashboard so the user has
context without navigating back. This is not a full repeat of the dashboard —
just the key numbers.

**Data to show:** Total hosts (with state breakdown), total services (with
state breakdown), active alert count.

**Recommended component:** A small stat row or info strip at the top of the
page.

---

### 2.2 Host Status Table

A full, filterable, paginated table of all monitored hosts.

**Columns:**

| Column | Notes |
|---|---|
| Host name | |
| Current state | UP / DOWN / UNREACHABLE, color-coded |
| State type | Soft / Hard |
| Last check | Relative time (e.g., "2 min ago") |
| Check latency | seconds |
| Plugin output | Truncated; full text available on expand |
| Acknowledged | Badge if acknowledged |
| In downtime | Badge if in scheduled downtime |
| Flapping | Badge if flapping |

**Filtering and search:**
- Filter by state (UP, DOWN, UNREACHABLE)
- Filter by acknowledged / not acknowledged
- Search by hostname

**Row expansion — inline host detail:**
When the user selects a host row, expand it or open a detail panel (do not
navigate away) showing:

- All current performance data for that host, with metric names in plain
  language where possible (see §2.5 for the label mapping)
- Warning and critical thresholds alongside current values, so the user
  can see how close a value is to its threshold
- A trend chart for key metrics if historical data is available
  (e.g., RTA and packet loss over the last 24 hours)
- Timestamps: last state change, last time up, last time down,
  last time unreachable
- A mini list of services associated with this host, with their current
  state badges

**API — `GET /system/network-health/hosts` query params:**

| Param | Values | Default | Notes |
|---|---|---|---|
| `page` | int ≥ 1 | 1 | Page number |
| `per_page` | 1–100 | 25 | Rows per page |
| `sort_by` | `hostname` \| `state` \| `last_check` \| `check_latency` | `hostname` | Column to sort by |
| `order` | `asc` \| `desc` | `asc` | Sort direction |
| `search` | string | — | Partial match on hostname |
| `state` | `UP` \| `DOWN` \| `UNREACHABLE` | — | Filter by state |
| `ack_filter` | `all` \| `acknowledged` \| `unacknowledged` | `all` | Filter by ack state |

**API — `GET /system/network-health/hosts` response shape:**

```json
{
    "items": [
        {
            "hostname":      "router-01",
            "state":         "Down",
            "state_type":    "Hard",
            "last_check":    "2026-08-26T16:30:00+00:00",
            "check_latency": 0.012,
            "plugin_output": "PING CRITICAL - Packet loss = 100%",
            "is_flapping":   false,
            "in_downtime":   false,
            "nagios_ack":    "No Acknowledgement",
            "ack": null
        }
    ],
    "page":     1,
    "per_page": 25,
    "pages":    3,
    "total":    72,
    "has_next": true,
    "has_prev": false
}
```

**API — `GET /system/network-health/hosts/<hostname>/detail` response shape:**

```json
{
    "hostname":               "router-01",
    "state":                  "Down",
    "state_type":             "Hard",
    "plugin_output":          "PING CRITICAL - Packet loss = 100%",
    "last_check":             "2026-08-26T16:30:00+00:00",
    "last_state_change":      "2026-08-26T15:28:00+00:00",
    "last_hard_state_change": "2026-08-26T15:30:00+00:00",
    "last_time_up":           "2026-08-26T14:00:00+00:00",
    "last_time_down":         "2026-08-26T15:28:00+00:00",
    "last_time_unreachable":  null,
    "check_latency":          0.012,
    "check_execution_time":   0.045,
    "is_flapping":            false,
    "in_downtime":            false,
    "nagios_ack":             "No Acknowledgement",
    "ack": null,
    "perf_data": [
        {
            "metric": "rta",
            "value":  0.0,
            "unit":   "ms",
            "warn":   100.0,
            "crit":   500.0,
            "min":    0.0,
            "max":    null
        },
        {
            "metric": "pl",
            "value":  100.0,
            "unit":   "%",
            "warn":   20.0,
            "crit":   60.0,
            "min":    0.0,
            "max":    null
        }
    ],
    "services": [
        {
            "service":       "http-80-TCP",
            "state":         "Ok",
            "plugin_output": "HTTP OK: Status line output matched",
            "last_check":    "2026-08-26T16:29:00+00:00"
        }
    ]
}
```

`check_execution_time` is the time Nagios spent running the plugin check
(float, seconds). It is distinct from `check_latency`, which is the time
between the scheduled check and when the check was actually run.

**Recommended component:** Expandable table rows or a master-detail split
layout. The goal is to let the user browse hosts and inspect one without losing
their place in the list.

---

### 2.3 Service Status Table

A full, filterable, paginated table of all monitored services.

**Columns:**

| Column | Notes |
|---|---|
| Host name | Which host this service belongs to |
| Service name | Service description / plugin name |
| Current state | OK / WARNING / CRITICAL / UNKNOWN, color-coded |
| State type | Soft / Hard |
| Last check | Relative time |
| Check latency | seconds |
| Plugin output | Truncated; full text on expand |
| Acknowledged | Badge |
| In downtime | Badge |
| Flapping | Badge |

**Filtering and search:**
- Filter by state
- Filter by service name / plugin type
- Filter by host name
- Filter by acknowledged / not acknowledged

**Row expansion — inline service detail:**
When the user selects a service row, show:

- All performance data for that service, labeled in plain language
  (see §2.5 for the label mapping)
- Current value, warning threshold, and critical threshold shown together
  so the user can see context (e.g., "RTA: 45ms — warn at 100ms, critical
  at 200ms")
- A trend chart for the primary metric(s) of that service if historical
  data is available
- State timestamps: last time OK, last time WARNING, last time CRITICAL,
  last time UNKNOWN

**API — `GET /system/network-health/services` query params:**

| Param | Values | Default | Notes |
|---|---|---|---|
| `page` | int ≥ 1 | 1 | Page number |
| `per_page` | 1–100 | 25 | Rows per page |
| `sort_by` | `hostname` \| `service` \| `state` \| `last_check` \| `check_latency` | `hostname` | Column to sort by |
| `order` | `asc` \| `desc` | `asc` | Sort direction |
| `search` | string | — | Partial match on hostname OR service name |
| `hostname` | string | — | Exact hostname filter (different from `search`) |
| `state` | `OK` \| `WARNING` \| `CRITICAL` \| `UNKNOWN` | — | Filter by state |
| `ack_filter` | `all` \| `acknowledged` \| `unacknowledged` | `all` | Filter by ack state |

**API — `GET /system/network-health/services` response shape:**

```json
{
    "items": [
        {
            "hostname":      "web-01",
            "service":       "http-80-TCP",
            "state":         "Warning",
            "state_type":    "Soft",
            "last_check":    "2026-08-26T16:29:00+00:00",
            "check_latency": 0.008,
            "plugin_output": "HTTP WARNING: Response time 4.2s",
            "is_flapping":   false,
            "in_downtime":   false,
            "nagios_ack":    "No Acknowledgement",
            "ack": null
        }
    ],
    "page":     1,
    "per_page": 25,
    "pages":    6,
    "total":    148,
    "has_next": true,
    "has_prev": false
}
```

**API — `GET /system/network-health/services/<hostname>/<path:service_name>/detail` response shape:**

```json
{
    "hostname":               "web-01",
    "service":                "http-80-TCP",
    "state":                  "Warning",
    "state_type":             "Soft",
    "plugin_output":          "HTTP WARNING: Response time 4.2s",
    "last_check":             "2026-08-26T16:29:00+00:00",
    "last_state_change":      "2026-08-26T16:28:00+00:00",
    "last_hard_state_change": null,
    "last_time_ok":           "2026-08-26T16:25:00+00:00",
    "last_time_warning":      "2026-08-26T16:28:00+00:00",
    "last_time_critical":     null,
    "last_time_unknown":      null,
    "check_latency":          0.008,
    "check_execution_time":   0.031,
    "is_flapping":            false,
    "in_downtime":            false,
    "nagios_ack":             "No Acknowledgement",
    "ack": null,
    "perf_data": [
        {
            "metric": "time",
            "value":  4.2,
            "unit":   "s",
            "warn":   2.0,
            "crit":   10.0,
            "min":    0.0,
            "max":    null
        }
    ]
}
```

Note: service names can contain slashes (e.g., NCPA metric paths like
`cpu/percent`). The URL rule uses `<path:service_name>` so these are routed
correctly. See also §2.5 on the `_plugin_key()` service name format.

**Recommended component:** Same pattern as the host table. Expandable rows or
master-detail. No separate page.

---

### 2.4 Network-Wide Performance Trends

A section showing aggregated performance data across the whole network over
time. Unlike the dashboard which shows a single current value, this section
shows trends so the user can see whether things are getting better or worse.

**Always-present metrics:**

| Metric | Display | Source |
|---|---|---|
| Average RTA / Latency | Line chart over time + current value | `check_ping`, `check_icmp` → `rta` |
| Average Packet Loss | Line chart over time + current value | `check_ping`, `check_icmp` → `pl` |

**Conditional metrics (if NCPA is deployed on at least one host):**

| Metric | Display | Source |
|---|---|---|
| Average CPU usage | Line chart over time | `check_ncpa` → `cpu/percent` |
| Average disk usage | Line chart or bar chart | `check_ncpa` → disk metric |
| Average memory usage | Line chart over time | `check_ncpa` → memory metric |

**Nagios server own resources (always present if local checks are configured):**

| Metric | Display | Source |
|---|---|---|
| Nagios server CPU load (1/5/15 min) | Line chart, all three on one chart | `check_load` → `load1`, `load5`, `load15` |
| Nagios server disk usage | Bar or gauge per mount point | `check_disk` |
| Nagios server swap usage | Line chart or gauge | `check_swap` |

**Time range selector:**
The user should be able to select the time window for all charts in this
section (e.g., last 1 hour, 6 hours, 24 hours, 7 days). All charts should
respond to the same selection.

**API — `GET /system/network-health/trends` query params:**

| Param | Values | Default | Notes |
|---|---|---|---|
| `hours` | `1` \| `6` \| `24` \| `168` | `24` | Time window (168 = 7 days) |
| `buckets` | 1–168 | `24` | Number of data points per chart |

**API — `GET /system/network-health/trends` response shape:**

Each `bucket` entry: `{ "bucket_start": ISO-8601, "avg_value": float | null, "unit": str | null }`
`avg_value` is `null` when no data was recorded in that bucket.

```json
{
    "hours":   24,
    "buckets": 24,
    "ping": {
        "configured":  true,
        "rta":         [ { "bucket_start": "2026-08-25T16:00:00+00:00", "avg_value": 12.3, "unit": "ms" }, "..." ],
        "packet_loss": [ { "bucket_start": "2026-08-25T16:00:00+00:00", "avg_value": 0.5,  "unit": "%" },  "..." ]
    },
    "ncpa": null,
    "nagios_server": {
        "cpu_load": {
            "configured": true,
            "load1":  [ { "bucket_start": "...", "avg_value": 0.42, "unit": null } ],
            "load5":  [ { "bucket_start": "...", "avg_value": 0.38, "unit": null } ],
            "load15": [ { "bucket_start": "...", "avg_value": 0.31, "unit": null } ]
        },
        "swap": {
            "configured": true,
            "swap": [ { "bucket_start": "...", "avg_value": 128.0, "unit": "MB" } ]
        },
        "disk": {
            "configured": true,
            "mounts": {
                "/":     [ { "bucket_start": "...", "avg_value": 12345678.0, "unit": "B" } ],
                "/boot": [ { "bucket_start": "...", "avg_value": 345678.0,  "unit": "B" } ]
            }
        }
    }
}
```

`ping.configured: false` means no ping/ICMP checks are set up — the ping
section renders as "plugin not configured" (§3.2). `ncpa: null` means no
NCPA services exist — hide that section entirely (conditional, §1.4). The
`nagios_server` sub-sections each carry their own `configured` flag.

`nagios_server.disk.mounts` is a dict keyed by mount-point path. Each value
is the same bucketed array shape. Mount points are discovered dynamically
from the `check_disk` service's perf data on the Nagios server; inode metrics
are excluded from the `mounts` dict (they are tracked separately via the
`*_inode_percent` metric keys in the raw perf data).

**Recommended component:** Line charts for time-series data. Gauges or
horizontal bar charts for current percentage-based values (disk, memory).
Group related metrics together visually.

---

### 2.5 Service Health by Plugin Type

A grouped summary showing the health of services broken down by plugin type.
Answers "are all my ping checks OK?" or "how many HTTP services are in
warning?" without scanning every row in the service table.

**How service names map to plugin groups:**

Service descriptions in the database follow the format `{name}-{port}-{protocol}`,
as generated by Pinpoint's host configuration builder. Examples:
`http-80-TCP`, `ssh-22-TCP`, `ncpa-5693-TCP`, `ncpa_cpu_usage-5693-TCP`,
`ncpa_memory_usage-5693-TCP`, `snmp-161-UDP`.

The backend resolves a service description to its check plugin via a two-step
lookup:

1. Split on `-` and take the first segment (the "dash-prefix"):
   - `http-80-TCP` → `http`
   - `ncpa_cpu_usage-5693-TCP` → `ncpa_cpu_usage`
   - `ncpa_memory_usage-5693-TCP` → `ncpa_memory_usage`
2. That dash-prefix is looked up in the combined TCP+UDP command map
   (`command_maps/tcp_commands.json` and `udp_commands.json`). If a match is
   found, the mapped command name is returned directly:
   - `http` → `check_http`
   - `ncpa_cpu_usage` → `check_ncpa`
   - `ncpa_memory_usage` → `check_ncpa`
   - `ncpa_disk_usage` → `check_ncpa`
3. If the dash-prefix is not in the map, split it again on `_` and take the
   first part, then look that up:
   - `ncpa_cpu_usage` → `ncpa` → `check_ncpa` (fallback path)
4. If still not found, fall back to `check_{prefix}`.

This means all NCPA service variants — `ncpa`, `ncpa_cpu_usage`,
`ncpa_memory_usage`, `ncpa_disk_usage` — all resolve to `check_ncpa` and are
grouped together under the **NCPA** display name.

The `display_name` is derived by stripping the `check_` prefix from the
resolved plugin key and uppercasing the result:
- `check_http` → `HTTP`
- `check_ncpa` → `NCPA`
- `check_snmp` → `SNMP`

The `display_name` field is returned directly by the API — the front-end
does not need to perform any name derivation itself.

**The command map is the single source of truth** for service-name → plugin
mappings. Both `create_host_cfg.py` (which generates Nagios config) and
`statistics.py` (which groups services for display) read from the same
`command_maps/tcp_commands.json` and `command_maps/udp_commands.json` files.
Adding a new service type requires only an entry in the appropriate map file.

**Data to show per plugin group:**

| Field | Notes |
|---|---|
| Display name | Derived from plugin key (e.g., `check_ncpa` → `NCPA`, `check_http` → `HTTP`) |
| Total services using this plugin | |
| State breakdown | Count of OK, WARNING, CRITICAL, UNKNOWN for that plugin |
| Overall health indicator | A visual indicator of the worst current state in this group |

The `display_name` field is returned directly by the API — the front-end
does not need to perform any name derivation itself.

**API — `GET /system/network-health/plugins` response shape:**

```json
{
    "groups": [
        {
            "display_name": "HTTP",
            "total":        12,
            "ok":           10,
            "warning":       2,
            "critical":      0,
            "unknown":       0,
            "worst_state":  "warning"
        },
        {
            "display_name": "NCPA",
            "total":        24,
            "ok":           24,
            "warning":       0,
            "critical":      0,
            "unknown":       0,
            "worst_state":  "ok"
        }
    ]
}
```

Note: NCPA contributes multiple service rows per host (CPU, memory, disk) but
they are all grouped under the single `NCPA` display name because all three
service description variants resolve to `check_ncpa`.

Groups are sorted by worst severity first (CRITICAL → WARNING → UNKNOWN → OK).

**Ordering:** Show plugin groups with the most severe problems first
(groups with CRITICAL services before WARNING before all-OK). Fully healthy
groups can be visually de-emphasized or collapsed.

**Recommended component:** A card grid or accordion list. Not a table — the
visual grouping and health indicator matter more than column alignment here.

---

### 2.6 Performance Data Label Reference

When displaying performance data in host and service detail panels (§2.2,
§2.3), use the following table to show metric keys in plain language. This
is a guide for front-end developers implementing the detail panels.

| Plugin | Metric key | Plain label | Unit |
|---|---|---|---|
| `check_ping`, `check_icmp`, `check_fping` | `rta` | Round-trip time | ms |
| `check_ping`, `check_icmp`, `check_fping` | `pl` | Packet loss | % |
| `check_http` | `time` | Response time | s |
| `check_http` | `size` | Response size | B |
| `check_http` | `time_connect` | Connection time | s |
| `check_http` | `time_first_byte` | Time to first byte | s |
| `check_http` | `time_transfer` | Transfer time | s |
| `check_tcp` | `time` | Connection time | s |
| `check_smtp` | `time` | Response time | s |
| `check_ssh` | `time` | Response time | s |
| `check_dns` / `check_dig` | `time` | DNS response time | s |
| `check_load` | `load1` | CPU load (1 min avg) | — |
| `check_load` | `load5` | CPU load (5 min avg) | — |
| `check_load` | `load15` | CPU load (15 min avg) | — |
| `check_disk` | `/{mount}` | Disk used | B |
| `check_disk` | `/{mount}_inode_percent` | Inode usage | % |
| `check_swap` | `swap` | Swap used | MB |
| `check_users` | `users` | Logged-in users | — |
| `check_procs` | `procs` | Process count | — |
| `check_uptime` | `uptime` | System uptime | s |
| `check_ntp_time` / `check_ntp_peer` | `offset` | NTP time offset | s |
| `check_ntp_peer` | `jitter` | NTP jitter | s |
| `check_ntp_peer` | `stratum` | NTP stratum | — |
| `check_ldap` | `time` | LDAP response time | s |
| `check_ldap` | `entries` | Entries returned | — |
| `check_pgsql` | `time` | DB connection time | s |
| `check_mysql` | `Connections` | DB connections | c |
| `check_mysql` | `Threads_connected` | Active threads | — |
| `check_mysql` | `Uptime` | DB uptime | s |
| `check_ups` | `battery` | Battery level | % |
| `check_ups` | `load` | UPS load | % |
| `check_ups` | `voltage` | Input voltage | V |
| `check_ups` | `left` | Est. runtime remaining | min |
| `check_ups` | `temp` | UPS temperature | °C |
| `check_apt` | `available_upgrades` | Pending updates | — |
| `check_apt` | `critical_updates` | Security updates | — |
| `check_ifstatus` | `up` | Interfaces up | — |
| `check_ifstatus` | `down` | Interfaces down | — |
| `check_ifstatus` | `dormant` | Interfaces dormant | — |
| `check_snmp` | varies | Use OID label from plugin output | varies |
| `check_ncpa` | varies | Use NCPA metric path, strip leading slash | varies |

For any metric not in this table, display the raw key name and unit as-is.
Do not hide unknown metrics — label them with the raw key so the user can
still see the data.

---

### Network Health — What Does Not Belong Here

- Full notification history (belongs on a dedicated Notifications page)
- Device inventory and network discovery results (belongs on Device Inventory)
- User and role management
- System settings
- Plugin installation and configuration

---

## 3. Shared Behaviors

### 3.1 Data Freshness Indicator

Both pages must show when data was last updated. If the last check timestamp
is older than the configured scan frequency (`scanFrequency` from System
Settings), display a visible staleness warning. The user must always know
whether they are looking at live or stale data.

### 3.2 Empty States and "Plugin Not Configured" States

Every data section must have a defined empty or missing-data state. Do not
show blank cards or charts with no data and no explanation.

**Always-visible sections** (§1.1, §1.3) always render on the page. If the
required plugin or check is not configured, show a "plugin not configured"
message in place of the value. Never hide these sections entirely — their
absence would give the user no indication that the feature exists or is
missing.

Examples for always-visible sections:
- `check_ping` / `check_icmp` not on any host →
  "Plugin not configured — add `check_ping` or `check_icmp` to a host to
  enable latency and packet loss monitoring."
- `check_load` not on Nagios host →
  "Plugin not configured — `check_load` is not set up on the monitoring
  server."

**Conditional sections** (§1.4 NCPA metrics) hide completely when the
condition is not met — NCPA is an optional deployment, not a missing plugin.
When hidden, no message is needed.

Other empty state examples:
- No hosts monitored → "No hosts are currently being monitored."
- No active alerts → "All hosts and services are in a healthy state."
  (Treat this as a green light, not a blank.)
- No services of a given plugin type → do not show that plugin group in §2.5.

### 3.3 State Color Convention

Apply consistently across both pages:

| State | Color intent |
|---|---|
| OK / UP | Green |
| WARNING | Yellow / Amber |
| CRITICAL / DOWN | Red |
| UNKNOWN / UNREACHABLE | Orange or Gray |
| Acknowledged problem | Muted / desaturated version of the state color |
| Scheduled downtime | Blue or Purple |
| Flapping | Animated or patterned indicator to convey instability |

### 3.4 Auto-Refresh

Both pages auto-refresh based on the `dashboardRefreshRate` value in System
Settings (default: 5 minutes). A manual refresh trigger should always be
accessible. The last-refreshed timestamp must be visible at all times on
both pages.

### 3.5 Metric Averaging Logic

When computing network-wide averages for display:
- Only include hosts or services that have reported data within the last
  check cycle. Do not average in stale or missing values.
- Always note the coverage: "avg. across 18 of 22 hosts — 4 have no recent
  data."
- Do not display an average if fewer than 2 data points are available.
  Show "Insufficient data" instead of a misleading single-host average.

---

## 4. Alert Acknowledgement

### 4.1 Purpose

Acknowledgement is the mechanism by which an authorized user signals that they
are aware of an active alert and are handling it. It does not resolve the
underlying problem — the alert remains active in Nagios terms — but it allows
the team to distinguish "known and being handled" problems from "unnoticed"
ones.

Acknowledgement is tracked entirely within this system. No acknowledgement
data is written back to Nagios.

### 4.2 Permission

Only users with the **Acknowledge Alerts** permission may acknowledge or
unacknowledge alerts. Users without this permission see the acknowledged
state of alerts (visual indicator) but do not see acknowledge/unacknowledge
controls. Permission assignment is handled by the role management system and
is not defined in this spec.

### 4.3 Where Acknowledgement Controls Appear

Acknowledge and unacknowledge controls appear in two places:

**Active Alerts Feed (§1.6 — Dashboard):**
- Each alert row has an **Acknowledge** button (or icon button). If the alert
  is already acknowledged, the button changes to **Unacknowledge**.
- A single **Acknowledge All** button appears above the feed. It acknowledges
  all alerts currently visible in the feed (i.e., after any active filters
  are applied). It does not affect alerts filtered out of view.

**Host and Service Status Tables (§2.2, §2.3 — Network Health):**
- Each row has an **Acknowledge** / **Unacknowledge** button inline or within
  the expanded row detail. Behavior is identical to the dashboard feed.
- There is no "Acknowledge All" on these tables because the tables are
  paginated and represent the full host/service list rather than a focused
  alerts feed.

### 4.4 Acknowledge Workflow

When the user clicks **Acknowledge** on a single alert:

1. A small inline form or modal appears with a required **comment** field.
   The comment must not be empty before submission is allowed.
2. The user submits the form. The system records:
   - The alert identifier (host + service, or host-only for host alerts)
   - The acknowledging user's identity
   - The timestamp of acknowledgement
   - The comment
3. The alert row updates immediately to show the acknowledged state (muted
   colors, acknowledged badge — see §3.3).
4. The alert remains visible in the feed unless the user has enabled the
   "Hide acknowledged" filter (see §4.6).

### 4.5 Acknowledge All Workflow

When the user clicks **Acknowledge All**:

1. A confirmation dialog appears stating:
   "Acknowledge all N visible alerts? This will mark all currently shown
   alerts as acknowledged. Alerts hidden by filters will not be affected."
2. The user must enter a single comment that applies to all acknowledged
   alerts in this batch.
3. On confirmation, all currently visible alerts are acknowledged in one
   operation. Each record stores the same batch comment, the same user, and
   the same timestamp.
4. The feed updates to reflect the acknowledged state on all affected rows.

### 4.6 Unacknowledge Workflow

When the user clicks **Unacknowledge** on an already-acknowledged alert:

1. A confirmation prompt appears: "Remove acknowledgement for this alert?"
   No comment is required to unacknowledge.
2. On confirmation, the acknowledgement record is removed and the alert
   reverts to its unacknowledged visual state.

### 4.7 Filter Behavior

The Active Alerts Feed (§1.6) and the status tables (§2.2, §2.3) provide a
filter toggle for acknowledgement state:

| Filter option | Behavior |
|---|---|
| Show all (default) | All active alerts visible; acknowledged alerts are muted |
| Hide acknowledged | Only unacknowledged alerts shown |
| Show only acknowledged | Only acknowledged alerts shown |

The **Acknowledge All** button on the dashboard feed always operates on
whatever is currently visible after filters are applied. If "Hide acknowledged"
is active, clicking Acknowledge All will acknowledge only the unacknowledged
alerts in view — which is the expected use case.

### 4.8 Acknowledged State Display

Consistent with §3.3:
- Acknowledged alerts use a muted / desaturated version of the state color.
- An **Acknowledged** badge is shown on the row, alongside the acknowledging
  user's name and the timestamp (e.g., "Acknowledged by admin — 14:32").
- The comment is shown as a tooltip or within the expanded row detail.
- Acknowledged alerts sort to the bottom of the Active Alerts Feed, below
  unacknowledged alerts of the same severity.

### 4.9 Persistence and Expiry

- Acknowledgements persist until explicitly removed by an authorized user, or
  until the alert resolves (host/service returns to OK/UP state). On
  resolution, the acknowledgement record is cleared automatically.
- If a resolved alert re-enters a problem state, it starts unacknowledged.
  Previous acknowledgement history is retained in the Alerts & Notifications
  History page and is not lost on resolution.

**Implementation note — data model:**
Live acknowledgement state is stored in the `ALERT_ACKNOWLEDGEMENT` table
(`system_models.py`, main DB). One row exists per currently-active
acknowledgement and is deleted on resolution or manual unacknowledge.

Every acknowledgement lifecycle event (ACKNOWLEDGED, UNACKNOWLEDGED,
AUTO_RESOLVED) is also appended to the `ACK_HISTORY` table (`system_models.py`,
main DB). This is the source of truth for the History page's "Acknowledged"
badge and detail panel. It stores: `Hostname`, `Service_Name`, `Action`,
`Actioned_At`, `ActorUserID` (FK to `USER` — safe because users are never
deleted, only deactivated), and `Comment` (populated only for ACKNOWLEDGED
actions). Both tables intentionally live in `system_models.py` — acknowledgement
data is system-generated, not Nagios-sourced, and does not belong in
`history_models.py`.

### 4.10 API Endpoint Reference

There are two sets of acknowledge/unacknowledge routes — one on the dashboard
feed and one on the network health tables. They share the same data model but
have slightly different request shapes suited to their context.

#### Dashboard routes (`dashboard.py`)

**`POST /system/dashboard/alerts/acknowledge`** — acknowledge a single alert.
```json
{ "hostname": "router-01", "service_name": null, "comment": "Looking into it" }
```
- `service_name`: `null` for host-level alerts, string for service alerts.
- Returns `201` on success. `409` if already acknowledged. `404` if no active alert.

**`POST /system/dashboard/alerts/acknowledge-all`** — acknowledge a batch.
```json
{
    "comment": "Scheduled maintenance window",
    "alerts": [
        { "hostname": "router-01", "service_name": null },
        { "hostname": "web-01",    "service_name": "http-80-TCP" }
    ]
}
```
- Already-acknowledged alerts in the list are silently skipped.
- Returns `200` with `{ "acknowledged": N, "skipped": M }`.

**`DELETE /system/dashboard/alerts/acknowledge`** — unacknowledge a single alert.
```json
{ "hostname": "router-01", "service_name": null }
```
- Returns `200` on success. `404` if no acknowledgement exists.

---

#### Network Health — host routes (`network_hosts.py`)

**`POST /system/network-health/hosts/acknowledge`** — acknowledge a host alert.
```json
{ "hostname": "router-01", "comment": "Looking into it" }
```
- No `service_name` field — this route is host-only.
- Returns `201` on success. `409` if already acknowledged or host is UP. `404` if host not found.

**`DELETE /system/network-health/hosts/acknowledge`** — unacknowledge a host.
```json
{ "hostname": "router-01" }
```
- Returns `200` on success. `404` if no acknowledgement exists.

---

#### Network Health — service routes (`network_services.py`)

**`POST /system/network-health/services/acknowledge`** — acknowledge a service alert.
```json
{ "hostname": "web-01", "service_name": "http-80-TCP", "comment": "Investigating" }
```
- `service_name` is required (unlike the dashboard route where it can be null).
- Returns `201` on success. `409` if already acknowledged or service is OK. `404` if not found.

**`DELETE /system/network-health/services/acknowledge`** — unacknowledge a service.
```json
{ "hostname": "web-01", "service_name": "http-80-TCP" }
```
- Returns `200` on success. `404` if no acknowledgement exists.

---

All acknowledge routes require the `system.acknowledge_alerts` permission.
All successful acknowledge operations return:
```json
{ "comment": "...", "acknowledged_by": "Jane Doe", "acknowledged_at": "2026-08-26T16:29:00+00:00" }
```

**Permission reference for all routes in this document:**

| Permission | Routes protected |
|---|---|
| `system.dashboard` | All `GET /system/dashboard/*` routes |
| `system.network_health` | All `GET /system/network-health/*` routes |
| `system.acknowledge_alerts` | All `POST` and `DELETE` acknowledge routes |
| `system.history` | All `GET /system/history/*` routes (defined in `Alerts_Notifications_History_Requirements.md`) |

---

## 5. Out of Scope for This Spec

The following are noted for future planning and are not defined here:

- Scheduled downtime creation and management UI
- Notification contact and rule management UI
- Dedicated Host Detail page (full per-host history view)
- Dedicated Service Detail page (full per-service history view)
- Report generation UI (already partially implemented separately)
- Dedicated Alerts & Notifications History page (defined separately in
  `Alerts_Notifications_History_Requirements.md`)
