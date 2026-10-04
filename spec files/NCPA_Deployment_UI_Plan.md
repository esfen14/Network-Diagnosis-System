# Plan: NCPA Deployment UI

Status: **implemented on branch `feature/ncpa-deployment-ui` (2026-10-04).**
Q1 and Q2 decided; Q3–Q5 use the recommendations. Differences from this plan
are listed in §11.

Goal: one page where an administrator can deploy NCPA from start to finish
(select devices, verify SSH host keys, enter credentials, deploy, watch
progress) and a deployment history that reports each run and each device as
**Success (ready for review)**, **Failed**, or **Down (unreachable)**.

Today the backend routes exist, but no client code calls any
`/api/system/deployment/ncpa/*` route. Credentials can only be sent by calling
`POST /deployment/ncpa/start` directly.

---

## 1. Summary of work

| # | Item | Layer | Why it is needed |
|---|---|---|---|
| B1 | Per-run, per-device result table | Model + migration | `NCPADeployment` keeps one row per device and is overwritten by each run, so history cannot show what happened to a device in an earlier run |
| B2 | Outcome classification (Success / Failed / Down / Incompatible / Rejected / Skipped) | Deployment worker | "Down" is only a free-text error string today |
| B3 | Device list, run list, run detail, review routes | Routes | The UI needs IP, trust state, agent status and per-device outcomes, which no route returns |
| B4 | Fixes to existing routes | Routes + worker | Defects the UI would hit (§3) |
| F1 | `/ncpa-deployment` page, sidebar entry, page access | Client | New page |
| F2 | Deploy wizard (select → verify → credentials → confirm) | Client | The whole deployment in one flow |
| F3 | Live run banner + header notification item | Client | Progress and result notifications |
| F4 | Deployment History tab with run review | Client | Notification history |
| S1 | Spec updates | Docs | Required by `AGENTS.md` |

Recommended order: **B4 → B1 → B2 → B3 → F1 → F2 → F3 → F4 → S1.**
B4 goes first because the wizard depends on those routes behaving
correctly.

---

## 2. Current backend (what the UI builds on)

| Route | Returns today | Gap for the UI |
|---|---|---|
| `GET /deployment/ncpa/devices` | `device_id`, `hostname` for NCPA-eligible devices | No IP, trust state, agent status or last error |
| `GET /deployment/ncpa/<id>/fingerprint` | Live SHA-256 fingerprint and IP | Good; returns 502 when unreachable |
| `POST /deployment/ncpa/<id>/confirm-trust` | Re-fetches the live key and saves it | Saves whatever key it sees now, not the key the user approved (§3) |
| `POST /deployment/ncpa/start` | `started`, `rejected[]` | See §3 |
| `POST /deployment/ncpa/stop` | Stop request | Good |
| `GET /deployment/ncpa/status` | Latest run: status, progress, message, error | No per-device results; `error` is a Python list string such as `"[3, 7]"` |
| `GET /deployment/ncpa/devices/trusted` | Trusted devices with `Agent_Status == PENDING_NCPA` | Failed devices drop out and cannot be retried |
| `GET /ncpadeployment` (`system.logs`) | Paginated run list for System Logs | Wrong permission for this page; no device results |

Run statuses (`DeploymentStatus`): `Running`, `Success`, `Partial Failure`,
`Failed`, `Interrupted`.
Device agent statuses (`AgentStatus`): `Pending NCPA`, `Deployed NCPA`,
`Deployment Failed`, `Excluded`, `Incompatible`.

---

## 3. Backend fixes (B4)

1. **Trust confirmation must save the key the user approved.**
   `confirm-trust` takes `{"fingerprint": "<shown value>"}`. It saves the key
   only if the live key still matches that value; otherwise it returns 409
   "Host key changed; verify again." Today, if the key changes between viewing
   and confirming, the new key is trusted without the user seeing it.
2. **Unreachable device during confirm-trust** returns 502 "Could not reach
   device." instead of a 500.
3. **Start request validation:** if `username` or `password` is missing or
   empty, return 400 per device instead of a `KeyError` 500.
4. **Unreachable device during start:** if `get_host_key_fingerprint` raises,
   reject the device with `"Device unreachable."` instead of returning 500.
5. **No empty runs:** if every device is rejected, return 400 with the
   `rejected` list and do not start a thread. Today this creates a run that
   reports "Success".
6. **All devices failed → `Failed`**, not `Partial Failure`.
7. **Retry:** failed devices can be selected again. The deployable set is
   `Agent_Status in (PENDING_NCPA, FAILED)`.
8. Fix the typo in the error string `"ACannot connect to device."`.

---

## 4. Data model (B1)

### New `NCPADeploymentResult` (default bind, `system_models.py`)

| Column | Type | Notes |
|---|---|---|
| `NCPADeployResultID` | int PK | |
| `NCPADeploymentStatusID` | FK → `NCPA_DEPLOYMENT_STATUS`, indexed | The run |
| `NetworkDiscoveryID` | FK → `NETWORK_DISCOVERY`, indexed | The device |
| `Hostname` | str | Copied at run time so history stays readable after renames or IP changes |
| `IP_Address` | str | Same |
| `Outcome` | `sa.Enum(DeploymentOutcome)` | See below |
| `Error` | str, nullable | Safe, user-facing reason only, never credentials or command output |
| `Started_At` / `Completed_At` | datetime | |

```python
class DeploymentOutcome(Enum):
    PENDING = "Pending"            # queued in this run, not started yet
    RUNNING = "Running"
    SUCCESS = "Success"
    FAILED = "Failed"
    UNREACHABLE = "Down"           # host did not answer SSH / timed out
    INCOMPATIBLE = "Incompatible"  # unsupported OS
    REJECTED = "Rejected"          # failed pre-flight in /start (not trusted, key mismatch)
    SKIPPED = "Skipped"            # run stopped before this device
```

### Review fields on `NCPADeploymentStatus` (Q1: approved)

`Reviewed_At` (datetime, nullable) and `Reviewed_By` (FK → `User`, nullable).

Run `flask db migrate` for the multi-database setup and add the migration test
`server/tests/migration_runner.py` expects.

---

## 5. Outcome classification (B2)

`give_program_permissions` and `install_ncpa` currently return `True`/`False`
and write a free-text error. Change them to return an outcome
(`SUCCESS`, `FAILED`, `UNREACHABLE`, `INCOMPATIBLE`) with a safe message, and
have `install_process` write the `NCPADeploymentResult` row.

- `UNREACHABLE`: socket timeout, connection refused, no route to host, or
  "Cannot reach host." Paramiko `AuthenticationException` is **not**
  unreachable; it is `FAILED` with "SSH authentication failed." so the user
  knows to fix the credentials.
- `/start` writes `REJECTED` rows for pre-flight rejections and `PENDING`
  rows for accepted devices.
- When the stop event fires, remaining `PENDING` rows become `SKIPPED`.
- Each device moves `PENDING → RUNNING → final` as it is processed, so the
  live view can show per-device progress.

---

## 6. Routes (B3)

All routes: `@login_required`, `@require_permission('system.deploy.ncpa')`,
`success`/`error`, and module docstring updated.

| Route | Purpose |
|---|---|
| `GET /deployment/ncpa/devices` *(extended)* | Every NCPA-eligible, scanned device: `device_id`, `hostname`, `ip_address`, `trusted` (bool), `fingerprint` (saved value or null), `agent_status`, `last_error`, `last_run_id`, `deployable` (bool) |
| `GET /deployment/ncpa/status` *(extended)* | Adds `devices: [{device_id, hostname, ip_address, outcome, error}]` and `counts: {success, failed, down, incompatible, rejected, skipped, pending}` for the latest run. Drops the list-string `error` for partial failures |
| `GET /deployment/ncpa/runs` *(new)* | Paginated run history (`page`, `per_page`, `status`, `start_date`, `end_date`): `id`, `status`, `started_by`, `start_at`, `completed_at`, `counts`, `reviewed` |
| `GET /deployment/ncpa/runs/<id>` *(new)* | One run with all device results |
| `POST /deployment/ncpa/runs/<id>/review` *(new)* | Mark a finished run reviewed; writes an activity-log entry |
| `POST /deployment/ncpa/check-credentials` *(new)* | Body `{"devices": [{"device_id", "username", "password"}]}`. For each trusted device, opens a fingerprint-checked SSH session, tests the login and that the account can use sudo (`sudo -S -v` with the supplied password), then closes it. Returns `[{device_id, result}]` with `result` in `ok`, `auth_failed`, `no_sudo`, `unreachable`, `not_trusted`. Installs nothing, stores nothing, logs no credentials; rate-limited to one check per device per few seconds |

`/devices/trusted` stays for compatibility; the new page uses `/devices`.

---

## 7. Page design (F1–F4)

Matches existing pages: `main.ml-55 flex-1 space-y-6`, `PageHeader`, a row of
`SummaryStatCard` gradients, an underline tab bar with `#ffb100` accent and
count pills, `rounded-2xl bg-white shadow-sm dark:bg-[#171B20]` table cards,
red error banners as in `PluginsPage`, and modals in the
`AddCustomPluginModal` style (`bg-black/60` overlay, `rounded-2xl` panel,
`dark:bg-[#171B20]`). Icons come from `lucide-react`.

### Route and navigation

| Item | Value |
|---|---|
| Path | `/ncpa-deployment` |
| Page | `pages/NcpaDeploymentPage.tsx` |
| Components | `components/ncpa-deployment/` |
| Permission | `system.deploy.ncpa` (already seeded) |
| Sidebar | "NCPA Deployment", icon `ServerCog`, after "Plugins" |
| Header title | `{ section: 'Plugins', page: 'NCPA Deployment' }` |
| API wrapper | `lib/ncpaDeploymentApi.ts` on top of `lib/api.ts` |
| Types | `types/ncpaDeployment.ts` (raw snake_case → view model) |

### Page layout

```
NCPA Deployment                                   [ Deploy NCPA ]
Install the NCPA agent on discovered Linux devices over SSH.

[Eligible 12] [Ready 5] [Deployed 6] [Failed 1] [Down 0]     ← SummaryStatCard

┌ Deployment in progress ───────────────────────── 3 / 5 ─ [Stop] ┐
│ ██████████░░░░░░░░  48%   Deploying NCPA.                       │
│ web-01  ✔ Success   db-02  ⟳ Running   app-03  … Pending        │
└─────────────────────────────────────────────────────────────────┘   ← only while Running

 Devices (12)   Deployment History (8)                              ← tab bar
────────────────────────────────────────────────────────────────────
┌ Devices ───────────────────────────────────── [Search…] [Filter] ┐
│ ☐ Device   IP            Host key       Agent        Last result │
│ ☐ web-01   10.0.0.11     ✔ Trusted      Deployed     —           │
│ ☐ db-02    10.0.0.12     ⚠ Not verified Pending      —   [Verify]│
│ ☐ app-03   10.0.0.13     ✔ Trusted      Failed   SSH auth failed │
└──────────────────────────────────────── 1 selected · [Deploy] ───┘
```

Summary cards (existing gradients): Eligible (amber `#FFB100→#F59E0B`),
Ready to deploy (blue), Deployed (green), Failed (red), Down (gray
`#6B7280→#4B5563`).

Agent status badges: Pending (amber), Deployed (green), Failed (red),
Incompatible (gray), Excluded (gray, not selectable).

### Deploy wizard (F2)

Opened from **Deploy NCPA** (all deployable devices pre-listed) or from the
table's selection bar (selected devices only). One modal, four steps, with a
step indicator at the top.

```
 ① Devices ─── ② Verify host keys ─── ③ Credentials ─── ④ Confirm
```

1. **Devices:** checklist of deployable devices (Pending or Failed). Deployed,
   Incompatible and Excluded devices are not shown.
2. **Verify host keys:** for each selected device without a saved key, call
   `GET …/fingerprint` and show `SHA256:…` with **Trust** / **Skip**. Trust
   sends the shown value to `confirm-trust` (§3.1). A 502 marks the row
   **Down**, deselects it, and offers **Retry**. A 409 refreshes the key
   and asks again. Already trusted devices show their saved key and need no
   action. **Next** is enabled when every remaining device is trusted.
3. **Credentials:** hosts may use different logins, so every device in the
   step is listed by hostname and IP.
   - **Shared credentials** (one username and password) apply to every device
     that has no login of its own. With a single device, the form is titled
     "Credentials for web-01 · 10.0.20.11".
   - Each row has **Use a different login**. That opens username and password
     fields labelled with that device ("Username for app-03"). **Use shared
     login** switches it back.
   - **Check logins** calls `POST /deployment/ncpa/check-credentials` (§6)
     before anything is installed. Each row then shows **Login and sudo
     verified**, **Rejected the username or password**, **Logged in, but this
     account cannot use sudo**, or **Down**.
   - A device whose login is rejected is switched to its own login fields,
     highlighted, and focused, and a banner names every device that needs
     attention. A Down device can be **Removed** from the run.
   - Devices that need attention move to the top of the list. Each device
     name in the banner is a link that scrolls to that row and focuses its
     username field.
   - Editing a login clears that device's check result. **Next** is enabled
     only when every remaining device is verified.
   - Password fields use `type="password"` and `autoComplete="off"`. A note
     says each login is tested, used once to create the restricted
     `pinpoint-deployment` account, and not stored.
4. **Confirm:** each device with the username it will log in as (and "own
   login" where it differs), plus devices left out and why. Then
   **Deploy**. This calls `POST /start`. The response's `rejected` entries are
   shown inline with their reasons. If `started > 0` the modal closes and the
   run banner takes over.

Wizard layout: the overlay scrolls (not a fixed-height modal), so long
device lists stay reachable at any window height. The Back/Next footer is
sticky at the bottom of the visible area.

Credential handling in the client: passwords live only in wizard state. They
are cleared on submit, on close, and on unmount. They are never logged, put
in the URL, or saved to `localStorage`.

### Live run (F3)

- New hook `hooks/useNcpaDeploymentStatus.ts`, modelled on
  `useDiscoveryStatus.ts`. It polls `GET …/status` every 2 s while Running and
  every 15 s when idle. It exposes `run`, `cancel`, `hasUnseenResult`,
  `markSeen`, and listens for an `nds:ncpa-deployment-started` window event
  that the wizard fires.
- **Page banner:** progress bar (`bg-[#ffb100]`, same markup as
  `ScanStatusItem`), message, per-device chips, and **Stop** (calls `/stop`).
- **Header notification item:** `DeploymentStatusItem` in `Header.tsx`, below
  `ScanStatusItem`, shown only with `system.deploy.ncpa`. The bell shows its
  dot when `hasUnseenResult` is true, as discovery does today.

| Run status | Icon | Title | Body |
|---|---|---|---|
| Running | `ServerCog` pulsing amber | NCPA deployment in progress | progress bar + Cancel |
| Success | `CheckCircle2` green | NCPA deployed: ready for review | "4 of 4 devices deployed." + **Review** |
| Partial Failure | `AlertTriangle` amber | NCPA deployed with problems | "3 deployed, 1 failed, 1 down." + **Review** |
| Failed | `XCircle` red | NCPA deployment failed | safe error + **Review** |
| Interrupted | `XCircle` gray | NCPA deployment stopped | "Stopped after 2 of 5 devices." |

**Review** navigates to `/ncpa-deployment?tab=history&run=<id>`.

### Deployment History tab (F4): notification history

```
┌ Deployment History ──────────── [Status ▾] [From] [To] ───────────┐
│ Run      Started            By      Result            Devices      │
│ NP-0008  Oct 4, 10:12 AM    raine   ● Ready for review  4 ✔        │
│ NP-0007  Oct 3, 4:40 PM     raine   ● Partial failure   3 ✔ 1 ✖ 1 ⏻│
│ NP-0006  Oct 2, 9:05 AM     admin   ● Failed            0 ✔ 2 ✖    │
└─────────────────────────────────────────────── ‹ 1 2 3 › ──────────┘
```

- Rows come from `GET …/runs`. The run ID uses the existing `NP-0008` tag
  format from System Logs.
- Result badge: **Ready for review** (green, successful run not yet reviewed),
  **Reviewed** (gray-green), **Partial failure** (amber), **Failed** (red),
  **Stopped** (gray), **Running** (amber pulse).
- Device count icons: ✔ success, ✖ failed, ⏻ down, plus incompatible,
  rejected and skipped when non-zero.
- Clicking a row opens a right-side drawer (same pattern as
  `PluginDetailsDrawer`) from `GET …/runs/<id>`:
  - Run summary: status, started by, duration.
  - Device results table: Device, IP, Outcome badge, Reason.
  - For successful devices: "Monitoring added: `ncpa-cpu-5693-tcp`,
    `ncpa-memory-5693-tcp`, …" and a link to the Network Health host view.
  - **Retry failed devices** opens the wizard with the Failed and Down devices
    pre-selected.
  - A device that failed with "SSH authentication failed." (password changed
    after the check) has **Enter new login**, which opens the wizard at the
    Credentials step for that device only.
  - **Mark as reviewed** saves `Reviewed_At`/`Reviewed_By` and clears "Ready for review".
- The tab's count pill shows runs awaiting review.

### States (Engineering Standards)

| State | Behavior |
|---|---|
| Loading | Table rows show "Loading devices…" / "Loading history…" |
| Empty devices | "No NCPA-eligible devices yet. Run a network scan to discover Linux hosts with SSH." |
| Empty history | "No deployments have run yet." |
| Error | Red banner with the API message; the page stays usable |
| Run already in progress | Deploy buttons disabled with tooltip "A deployment is already running." |
| No permission | Hidden from sidebar; `PageAccessGuard` redirects |

---

## 8. Tests

Backend (`server/tests/`, per `server/tests/README.md`; SSH is mocked):
- confirm-trust saves only a matching key; 409 on change; 502 when unreachable.
- `/start`: missing credentials → 400; all rejected → 400 and no thread;
  unreachable → `REJECTED`/"Device unreachable."; failed devices are deployable.
- Worker: outcome per device, including auth failure → `FAILED` and timeout
  → `UNREACHABLE`; stop → `SKIPPED`; all failed → run `Failed`.
- `check-credentials`: each result code with mocked paramiko; no password in
  the response or logs; untrusted device → `not_trusted`.
- `/runs`, `/runs/<id>`, `/review`: shape, pagination, permission (403
  without `system.deploy.ncpa`).
- No password appears in any response, log record, or `NCPADeploymentResult`.
- Migration test for the new table/columns.

Frontend (`client/src/test/`):
- Page access and sidebar visibility for `system.deploy.ncpa`.
- Wizard: step gating, Down device is deselected, shared vs per-device
  credentials payload, a rejected login switches only that device to its own
  labelled fields, editing a login clears its check, Next blocked until all
  verified, rejected entries shown, password state cleared after
  submit/close.
- `useNcpaDeploymentStatus`: polling interval switch and unseen-result flag.
- Header `DeploymentStatusItem`: each status renders the right title and
  Review link.
- History tab: badges, drawer, Retry pre-selection.

---

## 9. Spec updates (S1)

- `Frontend_Modules_and_Routes.md`: route row, `components/ncpa-deployment/`
  ownership, new hook.
- `Backend_Modules_and_Routes.md`: new and changed routes.
- `Data_Model_and_Integrations.md`: `NCPADeploymentResult`,
  `DeploymentOutcome`, review fields, confirm-trust rule.
- `Implementation_Status.md`: add the NCPA deployment page to implemented
  frontend areas. Until it ships, list "NCPA deployment UI" as an open gap.
- Consider moving §7 into a normative `NCPA_Deployment_Requirements.md` and
  linking it from `README.md` and `AGENTS.md`, as the History page has.

---

## 10. Open questions

| # | Question | Recommendation |
|---|---|---|
| Q1 | What does "ready to be reviewed" end with? | **Decided:** an explicit **Mark as reviewed** action stored on the run (`Reviewed_At`/`Reviewed_By`) |
| Q2 | Where do deployment results appear? | **Decided:** a dedicated header status item plus the History tab; the Nagios notification feed is unchanged |
| Q3 | Should "Down" also be checked before deploying (fingerprint fetch in step 2 already detects it), or only reported after a run? | Both: step 2 marks it early, and the run records it if the device drops mid-run |
| Q4 | Allow redeploying to devices already `Deployed NCPA` (e.g. to repair an agent)? | Not in this version; keep the deployable set to Pending + Failed |
| Q5 | Sidebar placement and name | "NCPA Deployment" under Plugins |

---

## 11. As built

- `check-credentials` also returns `not_found` and `rate_limited`; the rate
  limit is one check per device per 3 seconds, and a request holds at most
  50 devices (the same limit applies to `/start`).
- `/start` rejects a body with a missing or malformed username or password,
  or a device sent twice, with one 400 for the whole request.
- Successful devices in the run drawer link to Network Health instead of
  listing each NCPA service name; the API does not return the service list.
- A stopped run does not add the NCPA port for devices that finished before
  the stop (unchanged `add_ncpa_port` behavior); those devices have the agent
  but no Nagios service until the next config regeneration.

