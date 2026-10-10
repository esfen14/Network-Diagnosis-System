# Pinpoint QA: Journeys and Scope

What the QA agent loop tests and what it must leave alone: nine user journeys,
six invariants, and the out-of-scope list. The cases that exercise them are in
[`QA_Test_Plan.md`](QA_Test_Plan.md). The loop mechanics (traceability, the
`qa-run` workflow, lab safety) are issue #63 and are not defined here.

| | |
|---|---|
| **Status** | Current as of 2026-10-09 against `main` at `13076192`. Team decisions are final where marked **DECIDED**; everything else is a recommendation the QA agent follows until the team changes it |
| **Sources** | The capstone paper (90 pages; "p." is the printed page number), the repository specs in `spec files/`, the application code, the installer repository (`lorraine-pangilinan/PinPoint-Installer`) and the lab run reports in `docs/test-runs/` |
| **Quality model** | ISO/IEC 25010:2023, five characteristics in scope (**DECIDED**, §5 D-2) |
| **Paper status** | The paper is not fully revised. A fact that comes only from the paper may be outdated; the repository and team decisions win |

**Tags**

- **[PAPER]** stated in the paper's text or tables.
- **[SHOT]** visible only in a prototype screenshot (pp.71-86). The team says these
  images are out of date, so confirm against the running application.
- **[REPO]** found in the specs or the code (file named).
- **[INFER]** an inference. The agent does not assert it as a requirement.

---

## 0. Authority order

When sources disagree the QA agent logs an issue (label `needs-decision` for a
source conflict) and continues. It does not stop.

1. **§5 of this file** settles every conflict listed there.
2. **Paper Scope and Limitations (pp.5-6)** decides *whether* something is in scope.
3. **The repository specs** decide *how* an in-scope feature behaves
   (`AGENTS.md` routes to them; `Implementation_Status.md` lists known gaps).
4. **The running application and screenshots** are evidence of behavior, not authority.

If the paper is silent on a feature, that does not make it out of scope; the specs
decide (§4D).

---

## 1. Objectives the journeys serve

Four product goals, from the four research questions [PAPER p.4]:

| ID | Goal | Journeys |
|----|------|----------|
| G1 | Deploy and configure a Nagios Core environment with minimal manual intervention | J1, J4 |
| G2 | One interface to manage the diverse devices of BulSU-CICT | J2, J3, J7, J9 |
| G3 | Discover active devices automatically to set up and expand monitoring | J2, J3 |
| G4 | Detect service and network faults in real time and notify administrators | J5, J6, J7, J8 |

Project objectives 2, 3 and 4 (deployment module, discovery module, dashboard)
[PAPER p.5] are QA targets. Objective 1 (architecture and database) is a design
output. Objective 5 (ISO/IEC 25010 evaluation) is covered by user acceptance
testing; the QA loop reports its results by ISO characteristic (see
`QA_Test_Plan.md` §3) but does not replace the user survey.

**"QA done" / release-ready.** All of the following hold:

- Every case in `QA_Test_Plan.md` that is not marked human has a recorded result
  in `docs/test-runs/`, and every `Fail` or `Blocked` links an issue.
- J1-J9 pass on the lab, or each failure is filed. J1's installer-ISO path is manual.
- BB-01 to BB-07 pass [PAPER pp.67-68].
- PT-01 to PT-05 meet the thresholds in §2 X6 [PAPER p.68] and the decisions in §5 D-9.
- Invariants X1-X6 hold.
- Every item in §4B has a team decision recorded.

---

## 2. Invariants (apply to every journey)

| ID | Invariant | Source |
|----|-----------|--------|
| X1 | No step requires editing a `.cfg` file or using a shell. Everything is done through the web UI. (The QA agent itself uses the shell and the API to inject faults and read evidence; that does not violate X1.) | PAPER p.6 |
| X2 | Every state-changing user action leaves a log entry (who, what, when) in the right System Logs category. Tag prefixes seen: AL- (activity), CC- (config change), ND- (discovery), NP- (NCPA deploy) | PAPER p.41; SHOT pp.79-81 |
| X3 | Counts reconcile across pages: hosts up/down agree on Dashboard, Device Inventory, Network Health and Reports. The Dashboard "Active Alerts" figure is hosts plus services not in OK/UP | REPO `Display_Requirements.md` §1; Device_Inventory §12.2 |
| X4 | Every page and API route refuses unauthenticated access. Passwords are stored hashed | PAPER pp.26, 50 |
| X5 | Every long operation (scan, deploy, report) shows progress and ends in a terminal status: Success, Failed, Partial Failure or Interrupted | PAPER pp.43, 45 |
| X6 | Performance targets: PT-01 initialisation ≤10 s; PT-02 availability check of 10 hosts ≤5 s; PT-03 dashboard refresh of 15 updates ≤3 s; PT-04 alert generation ≤3 s (clock defined in §5 D-9); PT-05 stability over a 4 h soak (§5 D-9) | PAPER p.68; §5 D-9 |

---

## 3. Journeys

Each journey names the lowest environment that can verify it:

- **mock**: Nagios and SMTP stubbed (backend unit tests, `scripts/verify.sh`).
- **docker lab**: `scripts/lab` (fast lane; no systemd, installer or NCPA install).
- **vm lab**: `scripts/vmlab` (faithful lane; real installer steps, five target VMs on
  `10.77.0.0/28`; see `docs/plans/VM_Lab_Plan.md`).
- **manual**: a human is needed.

Actors in the paper are *Network Administrator* and *Network Technician*. The product
has the roles Administrator, Manager and Staff (§4A A16); where a journey says
"administrator" it means a user holding every permission.

### J1. Install and first login
- **Actor:** Network Administrator. **Verify in:** manual for the installer ISO path;
  vm lab for the installer's own steps (`scripts/vmlab fresh`) and the healthcheck.
- **Source:** flowchart pp.48-49; BB-01 p.67; installer repo (autoinstall, first boot,
  `setup/`). The paper's wizard screens (pp.71-74) are not the real installer UI (§5 D-5).
- **Steps:** boot the ISO, answer the interactive Ubuntu prompts (identity, storage and
  the others the autoinstall leaves interactive), let first boot finish, read the
  generated web credentials, open the web UI, sign in.
- **Expect:**
  1. First boot installs Nagios Core 4.5.11, the official plugins and SNMP, and serves
     the web app through Nginx (port 80) and Gunicorn, with Apache moved to
     `127.0.0.1:8081` [installer README; `Agent_Workflow_and_CI.md`].
  2. `pinpoint-healthcheck.sh` passes (the VM lab reports 59 or 60 passed, 0 failed;
     60 after #45, which added the `check_ncpa.py runs as nagios` check).
  3. The web administrator credentials are generated (`admin-xxxxx@pinpoint.lan`),
     shown once, and removed after the administrator confirms they were recorded.
  4. The login page loads. Valid credentials lead to the Dashboard; invalid credentials
     are refused and create no session.
  5. The stored password is a hash, never plaintext [PAPER p.41].
  6. Sign out asks for confirmation, then requires a new login [SHOT p.86].
- **First-login setup (#61, open, not built).** The target behavior is that the
  installer's administrator is blocked until it sets a real email and a new password;
  later-created administrators are not blocked. Until #61 lands the agent asserts
  none of this. When it lands, add the gate to J1 (and to the VM lab scripts, which
  must complete the window).
- **Variants:** a failed install is rerun [PAPER p.49]. Credentials already removed:
  the credentials script says so and does nothing.

### J2. Discover the network
- **Actor:** Network Administrator. **Verify in:** vm lab (docker lab for the UI flow).
- **Source:** flowchart p.48; objective 3; BB-06; rescan modals p.85; discovery logs
  p.80; `Device_Inventory_Requirements.md`; `Data_Model_and_Integrations.md`.
- **Steps:** Scan Network (first run) or Rescan Network (Dashboard or Network Health),
  confirm the modal, wait through "Scanning in progress" to "Rescan successful".
- **Expect:**
  1. The run shows Running, then Success, Failed or Interrupted, with progress
     [PAPER p.43].
  2. Each host records hostname, IP, MAC, OS, device type and open TCP/UDP ports
     [PAPER pp.43-44].
  3. Ubuntu/Linux hosts are marked NCPA-eligible. Windows, routers and unmanaged
     switches are ping-only [PAPER pp.36, 44, 52].
  4. Hosts are written to Nagios. Services follow **plugins**, not just open ports: a
     discovered port is monitored only once the plugin that checks it is enabled in
     Plugin Manager (J4). Service names follow the port, for example `http-80`
     [SHOT p.77; REPO `Implementation_Status.md` "Plugin lifecycle"].
  5. Changed network: "New host.cfg successfully applied" and Nagios reloads.
     Unchanged: "Host configuration unchanged; Nagios was not reloaded" and no reload.
     Cancelled: "Network discovery was cancelled" [SHOT p.80].
  6. New hosts appear in Device Inventory and the Dashboard totals update.
  7. A paused device (`Include_Device_In_Scanning` false) is kept in the device list but
     left out of Nagios and out of Dashboard/Network Health counts
     (`Device_Inventory_Requirements.md` §12).
  8. One device record per host. **Known defect #59 (open):** a duplicate
     "Address Unknown" record can remain for one host (seen once, trigger unconfirmed).
     The agent checks for duplicates, and if it finds one it comments on #59 instead of
     filing a new issue.
- **Variants:**
  - A failed scan can be rerun [PAPER p.49].
  - Changes in Settings > Network Discovery (networks, TCP/UDP ports, service
    overrides) apply to the next scan and appear as Configuration Change entries
    [SHOT p.80].
  - A scheduled scan runs every 6 hours by default (`Scan_Frequency`, `system_models.py`)
    [SHOT p.83]. It is skipped while **Maintenance Mode** is on. Maintenance Mode is a
    system setting that stops scheduled scans, plugin update scans and security
    validation but permits backups; the UI shows a banner
    (`Data_Model_and_Integrations.md`).

### J3. Deploy NCPA agents
- **Actor:** Network Administrator. **Verify in:** vm lab (needs Ubuntu targets with SSH;
  the docker lab has no init system and cannot install NCPA).
- **Source:** flowchart pp.48-49; BB-02 p.67; ERD pp.44-46;
  `docs/test-runs/2026-10-08-ncpa-fresh-run/`.
- **Steps:** NCPA Deployment, select devices, verify host keys, enter device
  credentials, confirm. In the lab: `scripts/vmlab ncpa [ip,ip,...]` drives the same
  deployment API; the browser wizard is the thing to check.
- **Expect:**
  1. Only NCPA-eligible devices can be selected. Others show Incompatible or Excluded
     [PAPER p.46].
  2. The run goes Running, then Success, Partial Failure, Failed or Interrupted. Each
     device goes Pending NCPA, then Deployed NCPA or Deployment Failed [PAPER pp.45-46].
  3. The SSH password is not persisted. Only the port, key-installed flag and key
     fingerprint are stored [PAPER p.45].
  4. After success, NCPA checks appear for that host: CPU, memory, disk
     [PAPER pp.6, 38]. The lab shows three services per host (CPU, root disk,
     memory); the paper also lists processes, which no run has shown, so do not
     assert it. **Fixed (#45, closed 2026-10-08):** the installer now ships a
     `python3` shebang and its healthcheck runs the plugin as `nagios`; a fresh
     installer-built appliance showed all six NCPA services OK on two hosts
     (`docs/test-runs/2026-10-08-ncpa-fresh-run/`). The agent asserts this step.
     NCPA services appear only while `check_ncpa` is enabled in Plugin Manager
     (`Implementation_Status.md`); enable it first. If the services are CRITICAL
     with exit code 127 the installer fix is missing; reopen #45 rather than file a
     new issue.
  5. The run is logged under System Logs > NCPA Deployment, for example "Deployment
     completed with 1 failure(s)" [SHOT p.81].
  6. One unreachable host or bad credential fails only that device.
  7. After deployment there is still one device record per host (#59).

### J4. Enable a plugin and put it to work
- **Actor:** Network Administrator. **Verify in:** mock or vm lab.
- **Source:** flowchart p.48 ("Add Plugin"); Plugin Manager pp.78, 50, 52;
  `Plugins_List.md`; `docs/plans/Plugin_Driven_Monitoring_Plan.md`.
- **Steps:** Plugins, All Plugins, select, verify, enable (the dialog previews what will
  be monitored), save. Monitoring attaches by itself to every device with a matching
  port; there is no device picking.
- **Use a port-driven plugin** such as `check_ssh` or `check_http`. Plugins that check no
  port (`check_ping`, `check_load`, ...) attach to nothing and cannot be enabled, and
  custom plugin upload is disabled. Both are accepted in `Implementation_Status.md`, so
  they are not defects (§8 R-5).
- **Expect:**
  1. An invalid plugin fails verification. The "Validation Issues" tile counts these
     [INFER from SHOT p.78].
  2. An enabled plugin appears in Currently Running with device, IP, service and
     running-since [SHOT p.78].
  3. Its services appear in System Status and Nagios executes them.
  4. Activity Log shows `plugin.validate` and `plugin.enable` [SHOT p.79]. (The
     `plugin.configure` permission was removed; do not expect it.)
  5. **Plugin count (DECIDED, §5 D-4):** the Installed tile reads **65** on an
     installer-built appliance, and the tile, the All Plugins table and the backend
     inventory agree.
  6. "Scan for Plugins" (All Plugins tab) refreshes the inventory. The summary tiles
     (Installed, Active Capabilities, Custom, Updates Available, Validation Issues) agree
     with the tables [SHOT p.78].
  7. Disabling the plugin removes its services; enabling it again restores them.
- **Lab evidence:** plugin enablement has not been run on a real lab beyond the plugin
  scan (65 plugins, `check_ncpa.py` found; `docs/test-runs/2026-10-08-ncpa-run/`).

### J5. Break a service, see the alert
- **Actor:** Network Administrator. **Verify in:** vm lab.
- **Source:** BB-05 p.68; PT-04; Table 2 p.50; DFD p.63;
  `docs/test-runs/2026-10-08-vm-lab-remaining/`.
- **Steps:** power a target off (`scripts/vmlab targets break <target> host`; or
  `scripts/vmlab alerts [target]`, which also acknowledges and restores), or, with the
  matching plugin enabled (J4), stop a service (`scripts/vmlab targets break <target>
  <service>`, for example `ssh` or `http`). Restore with `scripts/vmlab targets fix
  <target> host|<service>|all`. Targets: `web01`, `web02`, `app01`, `snmp01`, `legacy01`.
- **Expect:**
  1. After Nagios's check and retry cycle the host or service shows DOWN or CRITICAL in
     Device Inventory and System Status. Detection delay is the check interval times
     the retries (§5 D-9; #60 makes the interval a setting).
  2. Dashboard Active Alerts rises by the same amount (X3).
  3. An in-app notification appears (bell icon) [PAPER p.63; SHOT p.77].
  4. The alert appears in History > Alerts, and the notification in History >
     Notifications (`Alerts_Notifications_History_Requirements.md`).
  5. **Email (B8): not built.** The paper says an email goes out within 3 s of detection
     [PAPER p.68]. Do not assert it (§4B B8).
  6. Alert types promised: server down, service failure, high CPU [PAPER p.50]. High CPU
     needs NCPA thresholds (J3).
  7. Restoring the service returns it to UP/OK on every page, and the History shows a
     recovery event (`Alerts_Notifications_History_Requirements.md` §3.2).
- **Evidence so far:** a powered-off target produced "CRITICAL - Host Unreachable" about
  70 s later; recovery cleared it (2026-10-08, API only). Breaking a service raised no
  alert because no service plugin was enabled; that is expected, not a defect. The
  alert UI in a browser has not been run.

### J6. Acknowledge a problem and trace it
- **Actor:** Network Administrator. **Verify in:** vm lab (API passed; browser not run).
- **Source:** SHOT pp.77, 78; `Display_Requirements.md` §4;
  `Alerts_Notifications_History_Requirements.md`. Covered by the clause "all native
  monitoring capabilities of Nagios Core through the web-interface" [PAPER p.6].
- **Steps:** Device Inventory or System Status, press Acknowledge on a DOWN or CRITICAL
  row; then open History.
- **Expect:**
  1. The Acknowledgement column shows "By <user>" and the action becomes Unacknowledge
     [SHOT p.77].
  2. Unacknowledge clears it.
  3. The acknowledgement appears in History (`/history`). `Implementation_Status.md` says
     the page has not been audited against its spec, so failures here are real findings.
  4. When the service returns to UP/OK the active acknowledgement is cleared and an
     AUTO_RESOLVED record is appended. **Known gap, do not file:** not implemented yet
     (`Implementation_Status.md` "Auto-resolved acknowledgements").
- **Evidence so far:** acknowledge, list as acknowledged and unacknowledge passed by API
  (HTTP 201, then 200).

### J7. Monitor and diagnose
- **Actor:** Network Administrator. **Verify in:** vm lab.
- **Source:** objective 4; BB-04, BB-07; PT-03; use case p.64; pp.75-77;
  `Display_Requirements.md`.
- **Steps:** Dashboard, Network Health, open the ping, packet-loss and bandwidth views,
  then Device Inventory and System Status.
- **Expect:**
  1. The Dashboard shows total hosts, latency, warnings, critical issues, an up/down
     chart, a performance chart and the Nagios status panel [SHOT p.75].
  2. Network Health shows online/offline devices, host availability, resource averages,
     and latency, packet-loss and bandwidth views with a time-range selector
     [SHOT pp.76-77]. Graphs come from PNP4Nagios [PAPER p.29].
  3. NCPA hosts show CPU, memory, disk and processes. Ping-only hosts show availability
     and latency only [PAPER pp.6, 55].
  4. Auto-refresh defaults to 5 minutes (`Dashboard_Refresh_Rate`) with a manual
     refresh. A refresh completes in ≤3 s (PT-03).
  5. Counts reconcile across pages (X3).
  6. The Network Health network card shows IP range, gateway, subnet mask, DNS server,
     ISP and location, plus a "Last Scan" time [SHOT p.76]. The paper does not say
     where these come from; assert only that the card renders without error.
  7. Bandwidth and Avg Response Time tiles show "Not configured" until set up
     [SHOT p.76]. That is expected. An admin adds bandwidth rows in Settings > Plugins >
     NCPA Metrics (`Display_Requirements.md`).
  8. System Status lists services with OK / Warning / Unknown / Critical counts, search,
     state filter, sort and acknowledgement (`TopologyPage.tsx`, route `/topology`; see
     §4B B9). It polls about every 90 s.
  9. Paused, retired and merged devices are excluded from counts (J2 step 7).

### J8. Report and export
- **Actor:** Network Administrator. **Verify in:** mock or vm lab.
- **Source:** Table 2 p.50; EXPORT_LOG p.42; Reports p.79.
- **Steps:** Report, Host Availability or Network Services, choose a period, Run Report,
  export.
- **Expect:**
  1. The table shows hostname, state, uptime %, snapshots, last check and last state
     change [SHOT p.79].
  2. Host totals match Device Inventory (X3).
  3. Export gives a readable CSV; an `.xls` that Excel opens (an HTML table saved with an
     `.xls` extension); and a print view for the browser's "Save as PDF"
     (`client/src/utils/exportData.ts`). Do not require three generated files (§8 R-6).
  4. The export is recorded in Export Log: who, report type, format, start, end, time
     [PAPER p.42].
  5. An empty period shows an empty state, not an error.
- **Note:** the Reports page also lists Hosts by OS, Device Services, Alerts and
  Notifications views in the code (`ReportsPage.tsx`), beyond the two the team decided to
  ship (B4). The agent tests Host Availability and Network Services as required and
  records the others as observed.
- **Note:** Export Log is empty in the paper's evidence [SHOT p.81], so export has never
  been shown working.

### J9. Manage accounts and roles
- **Actor:** Network Administrator. **Verify in:** mock or vm lab.
- **Source:** use case p.64; User Management p.50; SHOT pp.82-83, 86.
- **Steps:** Manage Roles (add role), Manage Accounts (add user with role), sign in as
  that user, edit, deactivate.
- **Expect:**
  1. The user appears Active with the chosen role. The Activity Log records "Created
     account for <email>" [SHOT p.79].
  2. Status is Active, Inactive or Suspended [PAPER p.41]. A non-active user cannot sign
     in.
  3. Saving an edit signs that user out ("The user will be signed out after changes are
     applied") [SHOT p.83, older screenshot; confirm the current UI].
  4. A password reset stores a new hash.
  5. **Role matrix (DECIDED, §5 D-8):** derived from `server/app/api/commands/seed.py`.
     Administrator holds all 34 seeded permissions; **Manager and Staff are seeded with
     no permissions**, so a new Manager or Staff user can open only Settings > General
     until an administrator grants permissions in Manage Roles. A role lacking a
     permission cannot open or act on the related page, in the UI and in the API.
  6. Manage Accounts has an Export button and Active/Inactive/Suspended filters
     [SHOT p.82]. The paper does not say what the export contains or whether it is
     logged in Export Log; record what happens.
  7. Settings > General mixes scopes. Theme, font, layout and refresh rate apply per
     account. Scan frequency, notifications and export formats are system-wide
     [SHOT p.83]. Verify a change by one user does or does not reach another, as
     labelled.
  8. For accounts created while #61 is open: a password reset forces a change at next
     sign-in (`Must_Change_Password`). The "Require password change at first sign-in"
     checkbox on account creation is part of #61 and is not asserted until it lands.

---

## 4. Out-of-scope list

The agent must not file defects against groups A, C and D. Group B gets at most one
`needs-decision` issue per item.

### 4A. Excluded (never file a defect)

| ID | Excluded | Source |
|----|----------|--------|
| A1 | Agent-based monitoring of Windows or macOS. They are ping-only | PAPER p.6 |
| A2 | CPU, memory, disk and process metrics on non-Linux hosts | PAPER p.6 |
| A3 | Cloud infrastructure monitoring | PAPER p.6 |
| A4 | Automated remediation of detected issues | PAPER p.6 |
| A5 | SNMP-based *discovery*. It was tried and dropped. SNMP *checks* are in the product (the installer configures SNMP; Settings > Plugins has an SNMP OID table; services like `snmp-uptime-161-udp` exist) | PAPER pp.17, 24, 6; REPO `Display_Requirements.md` |
| A6 | Passive discovery. Only active Nmap scanning is used | PAPER pp.13, 24 |
| A7 | Other discovery add-ons (NAR, blësk NDD, nmap2nagios-ng) | PAPER pp.14-18 |
| A8 | Alert channels other than the in-app feed and Nagios contact notifications (email, SMS "if available"). Telegram appears only in the literature review | PAPER pp.11, 20, 22, 28 |
| A9 | Network setups beyond Table 5: one LAN, TP-Link home routers, unmanaged switches, ICMP and SSH only | PAPER p.56 |
| A10 | Scale beyond the test tables (10 hosts, 15 data updates). The 387 devices, 3 floors and 24 rooms are context, not a test target | PAPER pp.68, 70 |
| A11 | High availability or failover. The server must stay up, and "some data may be lost temporarily" on failure | PAPER p.62 |
| A12 | The network **topology view** and topology creation. The paper promises it (pp.3, 28, 34, 64); the repository excludes it. The **System Status** page is *not* excluded (B9) | REPO `Implementation_Status.md` "Explicit exclusions" |
| A13 | "Possible root causes" and failure explanations. Not in any repository spec | PAPER pp.3, 64; REPO none |
| A14 | Device-link and interface health pages. Not in any repository spec. `client/src/pages/wagpakielaman.tsx` has an "Interface Health" heading but nothing imports it (checked 2026-10-09), so it is dead code, not a page | PAPER p.28, 64; REPO none |
| A15 | Settings > Security controls for two-factor authentication, encryption, firewall and backups. The live Security tab has session timeout, security check frequency, strong password policy, failed login monitoring and audit logging only | PAPER p.84; REPO `SecuritySettings.tsx` |
| A16 | A Network Technician role. Seeded roles are Administrator, Manager, Staff | PAPER p.64; REPO `seed.py` |

### 4B. Promised or present, needing a team decision

File one `needs-decision` issue per open item, not defects. The paper admits the
prototype is "not totally functional" [PAPER p.71].

| ID | Item | Status | What the agent does |
|----|------|--------|---------------------|
| B4 | Reports. The paper promises "downtime summary" and "alert history" reports | **DECIDED (team, 2026-10-08): ship the two current views** (Host Availability, Network Services). The backend has six report endpoints; the other four have no required screen | Tests the two views. The paper's Reports module (Table 2, p.50) must be edited to match |
| B5 | Monitoring Logs: service-check results, host status changes, alert history, downtime records [PAPER p.51] | **DECIDED (team, 2026-10-08): History is enough.** It covers alert and notification history. Service-check results and downtime records get no page | Tests History only. The paper (Table 2, p.51) must be edited to match |
| B8 | **Gmail SMTP email alerts** [PAPER pp.28, 38, 58, 62; Table 2] | **Not built.** SMTP configuration moves to the installer repository (mail transport on the appliance); the application side is the real-email requirement in #61 and `SMTP_Admin_Email_Plan.md` on branch `docs/smtp-admin-email-plan` (draft, not merged). Until both land the paper's email claims are unmet | Asserts only that a notification event appears in History > Notifications. Once built: mock SMTP server first, then real Gmail by hand (human case) |
| B9 | **"System Status" page** | **DECIDED (team, 2026-10-08): keep.** The repository implements it in `TopologyPage.tsx` at `/topology`, labelled "System Status" in the sidebar, and `Implementation_Status.md` still says to remove the route and entry | Treats the page as a core page (J5-J7). Does not remove it and does not file the `/topology` URL as a defect. Follow-up (filed separately): rename the route and file so they no longer say "topology" |
| B10 | "Forgot Password?" on the login page | **Unhandled in code (checked 2026-10-09):** `LoginPage.tsx` renders a button with no click handler, and the server has no recovery route. The only reset is an administrator resetting a password in Manage Accounts. The recovery flow belongs to the SMTP work (it needs working email) | Asserts the button is present and does nothing harmful. Files at most one `needs-decision` issue. Does not assert recovery works |

### 4C. Lab artifacts, not requirements (ignore)

| ID | Artifact | Source |
|----|----------|--------|
| C1 | VirtualBox lab: 10.0.2.x addressing, "VBOX HARDDISK" in the installer, hosts such as `10.0.2.3.test.local`, `nagios-test`, `dev-de26af.test.local` | SHOT pp.73-74, 77 |
| C2 | The `Live Test` user and the inactive `Live test no permissions` role are test leftovers, not seed data | SHOT p.82 |
| C3 | Hosts shown Down, and the 26 critical issues, are lab state, not a baseline | SHOT pp.75-77 |

### 4D. UI elements the paper never describes

Not out of scope. The specs decide; the paper cannot be used to reject them.

- "Remember me" on the login page [SHOT p.75]
- Acknowledge / Unacknowledge [SHOT p.77]
- The Nagios status panel: flap detection, hosts and services in downtime, unknown
  services [SHOT p.75]
- The notification bell with a badge [SHOT p.77]
- The Manager and Staff roles [SHOT p.82] and the History page (`/history`)
- Device Inventory's Ports section and Monitoring state
  (`Device_Inventory_Requirements.md`), and the Settings > Plugins tab

---

## 5. Source conflicts and their resolution

| ID | Conflict | Resolution |
|----|----------|------------|
| D-1 | The paper's prose says **NRPE** (pp.10, 12, 25, 28, 38, 52, 55, 56, 62-64; Table 7; installer "NRPE Agents" p.74). The schema, plugin list (`check_ncpa`), UI, flowchart and logs say **NCPA** | **NCPA wins** (repository confirmed: NRPE survives only as the legacy model name `NRPEDeployment` and a test fixture). The paper's prose must be corrected before defense |
| D-2 | Quality model: ISO/IEC 25010:**2011** with 7 characteristics (p.5) vs **2023** with 5 criteria (pp.65-70). The 2023 edition has nine characteristics | **DECIDED: ISO/IEC 25010:2023, five characteristics in scope**: Functional Suitability, Performance Efficiency, Interaction Capability, Reliability, Security. The other four (Compatibility, Maintainability, Flexibility, Safety) are excluded with reasons in `QA_Test_Plan.md` §3 |
| D-3 | "Seven modules" (pp.33, 49) vs eight rows in Table 2 (pp.49-51) | Use the eight rows; fix the paper's text |
| D-4 | Plugin counts: **66** bundle (pp.36, 50, 52) vs **58** rows in Table 10 vs **65** installed (p.78) vs **15** default at install (p.74) | **DECIDED (owner, 2026-10-09): 65.** The VM lab scan read 65 plugins with `check_ncpa.py` found (`docs/test-runs/2026-10-08-ncpa-run/`). The agent checks the Installed tile reads 65 on an installer-built appliance and that the pages agree (J4 step 5). A different number is filed once as `needs-decision`. The 66/58/15 figures are paper errors. (`Plugins_List.md` documents 58 plugins, and the description catalog has 60 entries; neither is the installed count) |
| D-5 | Installer: Subiquity unattended autoinstall (pp.35, 51) vs prototype screens that look like a Calamares wizard (pp.71-74); generated credentials (p.49) vs a password chosen in the wizard (p.73); plugin picker inside the installer (p.74) vs Plugin Manager "independent of the initial installation process" (p.36) | **Resolved by the installer repository:** an Ubuntu 22.04.5 autoinstall with interactive sections, a first-boot stage, generated credentials (J1). The Calamares-style screens are outdated |
| D-6 | Server spec: minimum 256 GB SSD, 8 GB RAM (Table 3, p.55) vs deployed VM with 60 GB (p.54) | The lab VM spec wins for QA (appliance: 4 GB RAM, 4 CPUs, 40 GB disk). Fix the paper |
| D-7 | "Results stored in SQLite" (p.28); database holds "alert records, plugin allocations" (pp.62-63) vs a 14-table ERD with none (pp.39-46) | Nagios is the source of truth for monitoring state. The repository has `system.db` (application state) and `history.db` (polled Nagios snapshots). The ERD is not an exhaustive schema |
| D-8 | Roles: Administrator and Network Technician (p.64) vs Administrator, Manager, Staff (p.82). No permission matrix anywhere | **DECIDED (owner, 2026-10-09): derive the matrix from `seed.py`.** Administrator holds every seeded permission (34); Manager and Staff are seeded with none. QA verifies this seeded state and that permissions set in Manage Roles are enforced in the UI and the API. If the team later grants Manager/Staff permissions in the seed, update J9 step 5 and `QA_Test_Plan.md` J9 cases |
| D-9 | "Real time" is undefined. Dashboard refresh ≤3 s (PT-03) vs auto-refresh every 5 minutes (p.83). Host availability reads 16.9% on Network Health (7-day window) and 51.54% on Reports (24 h) for the same hosts, with no formula given | **DECIDED (owner, 2026-10-09): PT-04 clock starts at the Nagios state change** (`last_state_change` of the host/service). Pass = the alert is visible in the app (active-alerts feed, bell) within 3 s of that timestamp. Detection delay (the check interval times the retries; 5 minutes by default today, a setting once #60 lands) is measured and reported separately, not judged against 3 s. **DECIDED: PT-05 is a 4 h agent-run soak** (`QA_Test_Plan.md` PT-05). **Still open:** one availability formula and window for Network Health and Reports. Until decided, QA checks availability sanity only (100% with no outage, lower after one), not equality between the two pages, and files one `needs-decision` |
| D-10 | Resource metrics promised for "Linux-based hosts" (p.6) vs deployment to "Ubuntu" devices only (pp.10, 56) | Ubuntu is the promised target. Other distributions are best effort; no defects filed |
| D-11 | "The system included all native monitoring capabilities of Nagios Core" (p.6) | The boundary is the specs: Nagios' own UI is not a Pinpoint operator surface (`System_Overview_and_Architecture.md`). Test features with a page in the navigation plus §4D. Do not test every Nagios feature |

---

## 6. Open items for the team

| Item | Needed from | Blocks |
|------|-------------|--------|
| One availability formula and window for Network Health and Reports (D-9) | Team | Equality check between the two pages |
| Paper text of BB-01 to BB-07 (pp.67-68). Only the mapping used in `QA_Test_Plan.md` §5 ("Black-box acceptance") is in the repository | Paper owner | Exact BB wording; the BB-03 mapping is an inference |
| Email alerts (B8) and password recovery (B10) | Installer and application owners | J5 step 5, J1/J9 recovery |
| First-login setup (#61) | Issue owner | J1 and J9 steps marked "not asserted" |
| Paper edits: Reports module (p.50), Monitoring Logs (p.51), NRPE to NCPA, email promises (pp.28, 38, 58, 62), plugin counts, outdated screenshots | Paper owner | Nothing in QA; avoids defense questions |

## 7. Known defects the agent must not duplicate

| Issue | What | Effect on journeys |
|-------|------|--------------------|
| #67 (open) | Found by the 2026-10-09 dry run: removing a network reassigns its device and duplicates web01. The J2-09 port defect was retested on the VM lab ([2026-10-10 issue-66](../test-runs/2026-10-10-issue-66/REPORT.md)) | Network-removal journey remains affected by #67 |
| #59 (open) | Discovery can leave a duplicate "Address Unknown" device record for one host; NCPA deployed to the dead record is never checked | J2 step 8, J3 step 7: comment on the issue |
| #60 (open) | The Nagios check interval is hard-coded to 5 minutes and the poller stores repeated rows | J5 detection delay, PT-04 reporting, availability figures (D-9) |
| #61 (open) | First-login setup is not built | J1 and J9 steps marked "not asserted" |
| `Implementation_Status.md` gaps | Auto-resolved acknowledgements, discovery stop permission, History audit and others | Do not file a gap that is listed there; file only when the behavior contradicts a requirement |

## 8. Repository facts checked on 2026-10-09

The paper-versus-repository statements were re-checked against the code on this date.

| ID | Statement | Result |
|----|-----------|--------|
| R-1 | Gmail SMTP alerts are not built | Confirmed. No SMTP/mail code in `server/app` or the installer scripts read; Nagios contacts are built from user emails (`create_host_cfg.py`) |
| R-2 | System Status lives in `TopologyPage.tsx` at `/topology` | Confirmed (`App.tsx`, `Sidebar.tsx`: label "System Status"; permission `system.network_health` in `pageAccess.ts`). Decision B9: keep |
| R-3 | Installer reality | Per the installer repository (D-5) |
| R-4 | NCPA services CRITICAL on installer-built appliances (#45) | **Stale; fixed.** #45 is closed and the fresh-run report shows all six services OK |
| R-5 | Plugins with no port cannot be enabled; custom plugin upload disabled | Confirmed (`Implementation_Status.md`) |
| R-6 | Export formats | Confirmed: CSV is a real file, `.xls` is an HTML table, PDF is a print view (`client/src/utils/exportData.ts`) |
| R-7 | Settings tabs | Confirmed: General Settings, Security, System, Network Discovery, Plugins (`SettingsPage.tsx`). The paper's navigation (Fig. 8) lacks the Plugins tab |
| R-8 | Dead "Forgot Password?" button | Confirmed (`LoginPage.tsx`); no server route (B10) |
| R-9 | Lab evidence | Updated: `docs/test-runs/` holds six reports. The VM lab now passes alerts, acknowledge, `break`/`fix`/`load`, `up`/`down`/`revert` (API level). Not yet run: plugin enablement beyond the scan, the alert UI in a browser, service-level alerts, load alerts |
| R-10 | `Device_Inventory_Requirements.md` missing from the router and index | Fixed in this change (`AGENTS.md`, `spec files/README.md`). Its acceptance criteria (§10, §12.4) feed J2 and J7 |
| R-11 | Seeded roles and permissions | Administrator has all 34 permissions; Manager and Staff have none (`seed.py`, `seed_roles`) |
| R-12 | Reports views | The page lists six views, including Hosts by OS, Device Services, Alerts, Notifications (`ReportsPage.tsx`); the team decided two are required (B4) |

## 9. Maintenance

Update this file when a decision in §4B or §5 changes, a defect in §7 closes, or a
journey's behavior changes. When a case's source changes, update the case in
`QA_Test_Plan.md` in the same change. Record results in `docs/test-runs/`, not here.
