# Alerts & Notifications History Requirements
**Detech-IT / 4D-G2 Capstone**
**Last Updated:** 2026-08-26

---

## Purpose

This document defines the requirements for the **Alerts & Notifications
History** page. This is a dedicated browsing interface for viewing past and
current alert activity and Nagios notification events. It is distinct from
the Dashboard and Network Health pages, which focus on the current live state
of the network.

The history page answers questions like:
- "When did this host first go DOWN last night?"
- "Was a notification sent when this service went CRITICAL?"
- "Who acknowledged this alert and when?"
- "How long was this host in a problem state before it recovered?"

This page is for **browsing and investigation**. Export and report generation
are handled separately by the existing reports system and are not defined here.

---

## Definitions

| Term | Meaning in this document |
|---|---|
| **Alert event** | A recorded state change for a host or service (e.g., OK → CRITICAL, DOWN → UP). Each transition is one event. |
| **Active alert** | A host or service currently in a problem state. Also visible on the Dashboard (§1.6 of Display_Requirements). |
| **Notification event** | A Nagios-generated contact event (email, SMS, etc.) sent on a state change. Stored separately from alert state. |
| **Acknowledgement record** | A record created when a user acknowledges an alert (see §4 of Display_Requirements). Stored in the `ACK_HISTORY` table in `system_models.py` (main DB). |

---

## 1. Access and Permission

Access to the Alerts & Notifications History page is controlled by the
**View Alert & Notification History** permission.

- Users without this permission do not see the page in navigation and receive
  an access-denied response if they navigate to it directly.
- This permission is separate from the **Acknowledge Alerts** permission
  defined in Display_Requirements §4.2. A user can have one without the other.
- By default, this permission is granted to all roles. Administrators can
  restrict it per role through the role management system.

Permission assignment and role management are out of scope for this spec.

---

## 2. Page Layout and Structure

The page is divided into two primary tabs:

| Tab | Content |
|---|---|
| **Alerts History** | Log of all alert state-change events |
| **Notifications History** | Log of all Nagios notification events |

Both tabs share the same general layout: a filter bar at the top, a paginated
table below, and an expanded row or detail panel for individual records.

---

## 3. Alerts History Tab

### 3.1 What Is Shown

Each row in the alerts history table represents a **state change event** for
a host or service. This is not a snapshot of current state — it is a
chronological record of every transition.

**Columns:**

| Column | Notes |
|---|---|
| Timestamp | When the state change occurred |
| Type | HOST or SERVICE |
| Host name | |
| Service name | Blank for host-level events |
| Previous state | The state before the transition |
| New state | The state after the transition |
| State type | Soft or Hard |
| Duration in previous state | How long the host/service was in the previous state before this change |
| Plugin output | Nagios plugin output at time of event, truncated |
| Acknowledged | Badge if this alert event was acknowledged at any point while active |

### 3.2 Row Expansion — Alert Detail

When a row is selected or expanded, show:

- Full plugin output (untruncated)
- If the event was acknowledged (query `ACK_HISTORY` in `system_models.py`
  for rows matching this hostname + service where `Action = ACKNOWLEDGED`):
  - Acknowledging user's name (join `ActorUserID` → `USER` table)
  - Acknowledgement timestamp (`Actioned_At`)
  - Acknowledgement comment (`Comment`)
- If the event was a recovery (new state = OK/UP):
  - Total time the host/service was in the problem state from first detection
    to recovery
- Any notification events associated with this alert (linked from the
  Notifications History tab)

### 3.3 Filtering and Search

| Filter | Options |
|---|---|
| Time range | Preset: last 1 hour, 6 hours, 24 hours, 7 days, 30 days. Custom date/time range picker. |
| Type | All, Host only, Service only |
| Host | Search / select from list of monitored hosts |
| Service | Search / select from list of service names |
| New state | Filter by resulting state: OK/UP, WARNING, CRITICAL/DOWN, UNKNOWN/UNREACHABLE |
| Acknowledged | All, Acknowledged only, Unacknowledged only |
| State type | All, Hard only, Soft only |

All filters apply simultaneously. The table updates as filters change or on
explicit apply, depending on implementation preference.

### 3.4 Sorting

Default sort: timestamp descending (most recent events first).

The user can sort by any column. Secondary sort is always timestamp descending.

### 3.5 Pagination

Paginate at 25, 50, or 100 rows per page (user-selectable). Show total
matching record count above the table (e.g., "Showing 1–50 of 342 events").

---

## 4. Notifications History Tab

### 4.1 What Is Shown

Each row represents a **Nagios notification event** — a contact event sent
to one or more recipients when a state change occurred.

**Columns:**

| Column | Notes |
|---|---|
| Timestamp | When the notification was sent |
| Type | HOST or SERVICE |
| Host name | |
| Service name | Blank for host-level notifications |
| State at notification time | e.g., DOWN, CRITICAL, RECOVERY |
| Contact(s) notified | The contact name(s) that received the notification |
| Notification method | e.g., email, SMS — if available from Nagios data |
| Message | Notification text, truncated |

### 4.2 Row Expansion — Notification Detail

When a row is selected or expanded, show:

- Full notification message (untruncated)
- All contacts notified in this event (if multiple)
- A link to the related alert event in the Alerts History tab (if the
  corresponding state change record exists)

### 4.3 Filtering and Search

| Filter | Options |
|---|---|
| Time range | Same presets as §3.3 plus custom date/time range picker |
| Type | All, Host only, Service only |
| Host | Search / select |
| Service | Search / select |
| State | Filter by state at notification time |
| Contact | Filter by notified contact name |

### 4.4 Sorting and Pagination

Same behavior as §3.4 and §3.5. Default sort: timestamp descending.

---

## 5. Shared Behaviors

### 5.1 Empty States

- No records matching filters: "No events match the current filters."
  Show a "Clear filters" shortcut.
- No history data at all: "No alert history is available yet. Events will
  appear here as hosts and services change state."

### 5.2 Data Freshness

The history page does not auto-refresh in the background. A manual
**Refresh** button is always accessible. Show when the data was last loaded.

### 5.3 Timestamps

All timestamps display in the local browser timezone. Show both relative
time (e.g., "3 hours ago") and absolute time (e.g., "2026-08-26 09:45:12")
— relative as the primary display, absolute on hover or in the detail panel.

### 5.4 Linking Between Tabs

Where a notification event corresponds to a known alert event (same host,
same service, same time window), provide a link from the notification row
to the related alert event row, and vice versa. This lets the user quickly
answer "was a notification sent for this alert?" and "which alert triggered
this notification?"

---

## 6. Out of Scope for This Spec

- Export and report generation (handled by the existing reports system)
- Editing or deleting historical records
- Real-time alert feed (belongs on Dashboard §1.6 of Display_Requirements)
- Full current host/service status tables (belongs on Network Health §2.2,
  §2.3 of Display_Requirements)
- Notification rule and contact configuration
- Creating or modifying scheduled downtime
