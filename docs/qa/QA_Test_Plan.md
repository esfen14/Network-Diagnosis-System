# Pinpoint QA Test Plan

The master plan for the QA agent loop: every case has a stable ID, an ISO/IEC
25010:2023 tag, a place to run, written steps and a judgeable expected result.
What the cases are *for* (journeys, invariants, scope, decisions) is in
[`QA_Journeys_and_Scope.md`](QA_Journeys_and_Scope.md); read it first, especially §4
(out of scope) and §7 (known defects). Results go in
[`docs/test-runs/`](../test-runs/README.md), never in this file.

**Status:** current as of 2026-10-10 against `main` at `a55ae595`, aligned with the October 2026 paper draft (162 pages). Sources are named
per case; where the journeys file and a spec disagree, the journeys file §0 order applies.

---

## 1. How to use this plan

1. Prepare the baseline **B0** (§4), or the Docker lab where a case says `DOCKER`.
2. Run cases in ID order within a journey. Run cases tagged **destructive** last in
   their journey and restore state afterwards (each case says how).
3. For each case record exactly one result: `Pass`, `Fail`, `Blocked` or `Skipped`
   (`docs/test-runs/README.md`). `Pass` means the behavior was observed running;
   reading code is not a test.
4. Apply §6 to every `Fail`, `Blocked` and `Skipped`.
5. Stop a case at its first unmet **Expect** line; record that line number in the notes.

**Case header:** `[ISO] · environment · executor`

| Key | Meaning |
|---|---|
| `[FS] [PE] [IC] [RE] [SE]` | The one primary ISO/IEC 25010:2023 characteristic (§3) |
| `MOCK` | Backend unit/API tests and mocked Nagios (`scripts/verify.sh backend`), or a scratch script against the Flask test client |
| `DOCKER` | `scripts/lab` (fast lane; docs/manuals/Local_Lab.md). No systemd, no NCPA install |
| `VM` | `scripts/vmlab` with the `demo/` targets (faithful lane; `docs/plans/VM_Lab_Plan.md`) |
| `HUMAN` | A person must act (physical console, real mail account, judgment of a printed page). The loop skips it, records `Skipped (human)` and does not count it toward "QA done" until a person records a result |
| `agent` | The QA agent can run it from the steps alone |

---

## 2. Rules that apply to every case

- **Observe, don't infer.** A pass needs a value read from the running system: an API
  response, a Nagios `status.dat` field, a log line, or what the page shows.
- **Do not duplicate known issues.** Check [`QA_Journeys_and_Scope.md`](QA_Journeys_and_Scope.md)
  §7 and `spec files/Implementation_Status.md` first. A behavior listed there is
  recorded as `Skipped (known gap: <ref>)` or commented on the open issue, not filed.
- **Out-of-scope groups A, C, D are never defects** (journeys §4).
- **Discovered hosts are named `dev-xxxxxx`,** not by target name. Map a host to its
  target by IP (`web01` 10.77.0.2, `web02` .3, `app01` .4, `snmp01` .5, `legacy01` .6).
- **Credentials and evidence:** never print passwords, tokens, keys or SNMP communities;
  keep raw evidence outside the repository (`docs/test-runs/README.md`).
- **Lab limits:** one appliance at a time; scan only `10.77.0.0/28`; do not run the
  libvirt e2e harness or `server/tests/integration/` (`Agent_Workflow_and_CI.md`).

---

## 3. ISO/IEC 25010:2023 coverage

ISO/IEC 25010:2023 defines nine characteristics. The team decided to evaluate five
(journeys §5 D-2).

| Tag | Characteristic | What the loop checks | Cases |
|---|---|---|---|
| FS | Functional Suitability | The feature does what the spec says, completely and correctly | 45: J1-02, J1-06, J2-01, J2-03, J2-04, J2-07, J2-09, J3-01, J3-02, J4-01, J4-02, J4-03, J4-06, J4-07, J4-08, J5-02, J5-03, J5-04, J5-08, J6-01, J6-02, J6-03, J6-04, J7-01, J7-02, J7-03, J7-06, J7-07, J7-08, J8-01, J8-02, J8-03, J8-04, J9-01, J9-02, J9-09, X3-01, X3-02, X3-03, BB-01, BB-02, BB-03, BB-04, BB-06, BB-07 |
| PE | Performance Efficiency | Time behavior and stability under the paper's targets (Table 11, p.126) | 4: PT-01, PT-02, PT-03, PT-04 |
| IC | Interaction Capability (the paper's "Usability") | A user can complete the task through the UI; messages, states, navigation | 9: J1-05, J2-06, J7-04, J7-05, J8-05, J8-07, J9-06, J9-08, X1-01 |
| RE | Reliability | Faults are detected, failures stay contained, recovery works, the system stays up | 17: J1-01, J2-02, J2-05, J2-08, J2-10, J3-05, J3-07, J3-08, J3-09, J4-04, J5-01, J5-05, J5-06, J5-07, X5-01, PT-05, BB-05 |
| SE | Security | Authentication, authorization, secret handling, audit trail | 16: J1-03, J1-04, J1-07, J3-03, J3-04, J3-06, J4-05, J5-09, J6-05, J8-06, J9-03, J9-04, J9-05, J9-07, X2-01, X4-01 |

**Not evaluated, with reasons**

| Characteristic | Why it is excluded from the QA loop |
|---|---|
| Compatibility | One supported stack: the Ubuntu 22.04.5 appliance with Nagios Core 4.5.11 and Ubuntu targets (paper Tables 4 and 5, p.108; journeys A9). Interoperability with other systems is not a stated requirement |
| Maintainability | Code quality is enforced by CI (`scripts/verify.sh`: tests, lint, drift checks), not by exercising the running system |
| Flexibility | Scalability and adaptability beyond the test tables are out of scope (journeys A10, A11); installability is covered functionally by J1 |
| Safety | A monitoring dashboard has no physical-harm or hazard scenario; remediation is excluded (A4) |

Counts per characteristic are generated from the case headers (see §9 for the check).

---

## 4. Environment and commands

### 4.1 Baseline B0 (VM lab)

```bash
scripts/vmlab status                 # appliance state, snapshot stamp vs installer
scripts/vmlab targets up             # the five target VMs (10.77.0.2 to .6)
scripts/vmlab fresh                  # restore snapshot os-nagios-ready, install the pushed branch, run the healthcheck
scripts/vmlab setup-admin            # new administrator password, kept privately in the state folder (never printed)
scripts/vmlab smoke                  # sign in, add 10.77.0.0/28, run discovery, wait until the five targets are Up
```

Web UI and API: `http://127.0.0.1:18080` (same origin, cookie session). Sign in through the
login page, or `POST /api/user/login` with `{"email", "password"}`. Read the stored
administrator email and password only from the vmlab state folder
(`~/.local/share/pinpoint-vmlab/admin-email`, `admin-password`) without echoing them.
**Smoke can finish with a host still `pending`**; if a target is missing, wait a minute
and re-run `scripts/vmlab smoke` (`2026-10-08-vm-lab-remaining` report). The first scan also
takes about 14 min (the default networks include the VirtualBox NAT range and TCP ports
1-10000), so smoke reports "discovery finishes" as failed at 300 s: poll
`GET /api/system/discover/status` instead of starting a second scan. Hosts reach the
Network Health list a few minutes after the scan ends. Narrowing TCP ports to `1-1024`
cuts a scan to about 6 min but drops legacy01's SSH port 2222 (add it back as a range such
as `2200-2299` only after J2-09 is fixed). If the appliance VM was built by another state
folder (for example `pinpoint-appliance-45`), export `VMLAB_STATE_DIR` in the environment;
it is not read from the config file.

Appliance shell (read-only evidence): `ssh -i ~/.local/share/pinpoint-vmlab/id_ed25519 -p 2250 lab@127.0.0.1`.
App directory `/opt/pinpoint/Network-Diagnosis-System`; settings `/etc/pinpoint/pinpoint.env`;
Nagios status file `/usr/local/nagios/var/status.dat` (Nagios Core install prefix; confirm
with `scripts/vmlab health` output on the first run).

### 4.2 Lab commands used by cases

| Need | Command |
|---|---|
| Power a target off / on | `scripts/vmlab targets break <target> host` / `scripts/vmlab targets fix <target> host` |
| Stop / start one service | `scripts/vmlab targets break <target> <ssh\|http\|snmp>` / `scripts/vmlab targets fix <target> <service\|all>` |
| Move monitored SSH to another port | `scripts/vmlab targets ssh-port <target> <port>` (22 = back) |
| Burn CPU for NCPA threshold tests | `scripts/vmlab targets load <target> --seconds 90` |
| Deploy NCPA through the API | `scripts/vmlab ncpa [ip,ip,...]` (default web01 and legacy01) |
| Alert lifecycle by API | `scripts/vmlab alerts [target]` |
| Login for the NCPA wizard | `scripts/vmlab targets creds` |
| Installer healthcheck | `scripts/vmlab health` |
| Copy working tree, restart Gunicorn | `scripts/vmlab sync [--client]` (no migrations) |
| Reset to the snapshot | `scripts/vmlab revert` then `scripts/vmlab fresh` |
| Docker lab equivalents | `scripts/lab up`, `scripts/lab smoke`, `scripts/lab break <target> <ssh\|http\|snmp\|all>`, `scripts/lab fix …`, `scripts/lab reset` (targets 10.78.0.x; seeded login in Local_Lab.md) |

### 4.3 Fixtures

- **F-ENABLE:** `check_ssh` and `check_http` enabled in Plugin Manager (J4-03) so services exist to break.
- **F-NCPA:** NCPA deployed to `web01` and `legacy01` and `check_ncpa` enabled (J3-02, J3-05).
- **F-USERS:** a role `qa-view` holding only `system.dashboard`, and an active user `qa-viewer@example.test` with that role (J9-01, J9-02). Remove them after the run.

---

## 5. Cases

Journey and invariant cases are grouped by journey. Detailed lab cases that already exist
in `server/tests/plans/` are referenced as **Detail:** and are not copied (§8).

### J1. Install and first login

#### J1-01 Installer steps complete on a clean snapshot
`[RE]` · VM · agent
- **Pre:** appliance exists and `scripts/vmlab status` shows snapshot `os-nagios-ready` with no staleness warning.
- **Steps:** 1. `scripts/vmlab fresh`. 2. Read the final healthcheck summary.
- **Expect:** 1. The command exits 0. 2. The healthcheck reports **0 failed** (60 passed on `main` after #45; a different pass count is recorded but is not a failure if failed is 0).

#### J1-02 Services are wired as the installer says
`[FS]` · VM · agent
- **Pre:** J1-01 passed.
- **Steps:** 1. On the appliance, list listeners (`ss -ltnp`) and unit states (`systemctl is-active nagios nginx apache2 pinpoint*`; use the unit names the healthcheck prints). 2. `curl -sI http://127.0.0.1:18080/` from the host.
- **Expect:** 1. Nginx listens on port 80; Apache on `127.0.0.1:8081`; Gunicorn is running as the `pinpoint` user; Nagios is active. 2. The host gets an HTTP response from the web app, not the Nagios UI.

#### J1-03 Sign in succeeds and fails correctly
`[SE]` · VM · agent
- **Pre:** B0.
- **Steps:** 1. On `/login`, submit the administrator credentials. 2. Sign out and submit a wrong password. 3. Submit an unknown email.
- **Expect:** 1. Redirect to the Dashboard. 2. and 3. The login is refused with an error message, no session cookie is set, and `GET /api/user/me` returns 401. The two refusals do not reveal which of email or password was wrong.

#### J1-04 Passwords are stored hashed
`[SE]` · VM · agent
- **Pre:** B0.
- **Steps:** On the appliance, read the administrator's `Hashed_Password` column from the application database (`DATABASE_URL` in `/etc/pinpoint/pinpoint.env`, else `server/system.db`) without printing it to the report.
- **Expect:** The value is a Werkzeug hash with a scheme prefix (`scrypt:` by default; `pbkdf2:` on older Werkzeug) and does not equal the password. Record only "hashed" in the report.

#### J1-05 Sign out asks for confirmation
`[IC]` · VM · agent
- **Pre:** signed in.
- **Steps:** Press Sign out; cancel; press it again and confirm.
- **Expect:** Cancel keeps the session. Confirm ends it and the next protected URL redirects to `/login`.

#### J1-06 Installer ISO path, generated credentials and cleanup
`[FS]` · MANUAL · HUMAN
- **Pre:** `PinPoint-Installer-v1.1.iso` (or the release candidate) and a blank VM.
- **Steps:** Boot the ISO; answer the interactive Ubuntu prompts; let first boot finish; read the generated web credentials (shown once); confirm they were recorded; reopen the credentials script.
- **Expect:** The credentials are `admin-xxxxx@pinpoint.lan` plus a password; after confirmation they are removed and the credentials script says so and does nothing; the web UI is reachable at the VM's address and the healthcheck passes. A failed install can be rerun.

#### J1-07 First-login setup window (#61)
`[SE]` · VM · agent
- **Status:** `Skipped (not built: #61)`. When #61 lands: a fresh-install administrator is blocked by a setup window until a real email and a new password are set; a later-created administrator is not; the Nagios contact then uses the new address. Replace this case with the issue's tests.

### J2. Discover the network

**Detail:** `NETWORK_DISCOVERY_EXTENDED_TEST_PLAN.md`, `NCPA_PORTS_AND_SERVICE_IDENTIFICATION_LAB_TEST_PLAN.md`, `Device_Inventory_Requirements.md` §10 and §12.4.

#### J2-01 First scan finds every target
`[FS]` · VM · agent
- **Pre:** `scripts/vmlab fresh`, `setup-admin`; no discovery run yet; targets up.
- **Steps:** 1. `scripts/vmlab smoke` (it adds `10.77.0.0/28`, starts discovery and waits for hosts). 2. `GET /api/system/network-health/hosts`.
- **Expect:** 1. Exit 0 (or a re-run passes; see §4.1). 2. Hosts with IPs 10.77.0.2 to .6 are listed with state UP. The list also holds the Nagios server's own `localhost`, so judge the targets by address, not by a total count. Hosts are named `dev-xxxxxx`: web01 is .2, web02 .3, app01 .4, snmp01 .5, legacy01 .6. The appliance's lab address (10.77.0.1) is not one of the five.

#### J2-02 Scan progress and terminal status
`[RE]` · VM · agent (UI)
- **Pre:** B0.
- **Steps:** Press Rescan Network on the Dashboard; confirm the modal; poll `GET /api/system/discover/status` every 5 s until it stops changing.
- **Expect:** The UI shows "Scanning in progress" and then "Rescan successful". The status moves from running to exactly one of Success, Failed, Interrupted. Progress is shown while running (X5).

#### J2-03 Each host records its attributes
`[FS]` · VM · agent
- **Pre:** J2-01.
- **Steps:** Open the Device Inventory drawer for `web01` and `legacy01`; read `GET /api/system/hosts/<id>/ports`, `GET /api/system/hosts/<id>/identifiers` (IP, MAC) and `GET /api/system/report/hosts-by-os` (OS).
- **Expect:** Hostname, IP, MAC and OS are present (no route read exposed a device type; record what the drawer shows). `web01` lists ports 22/tcp and 80/tcp and 443/tcp; `legacy01` lists SSH on 2222/tcp. Each port shows a state and a reason (Device Inventory §2, §4).

#### J2-04 Services follow plugins, not just ports
`[FS]` · VM · agent
- **Pre:** J2-01 and no plugin enabled (clean install).
- **Steps:** Read the services list (`GET /api/system/network-health/services`) before and after enabling `check_ssh` (J4-03).
- **Expect:** Before: no `ssh-22` service on discovered hosts (only the host check). After: one SSH service per discovered host that has port 22 or the pinned SSH port.

#### J2-05 Changed network is applied and reloaded; unchanged is not
`[RE]` · VM · agent
- **Pre:** J2-01 passed; identities have settled with one active device per target; TCP scan settings include 22 and 2222. Record the plugin state and existing port states first.
- **Steps:** 1. Run a rescan with no change to the lab. 2. Run `scripts/vmlab targets ssh-port web02 2222`, wait one minute, rescan once. Inspect the port rows and System Logs > Network Discovery. 3. Restore with `scripts/vmlab targets ssh-port web02 22` even on failure; rescan only after the preceding scan is terminal and confirm the live listener and port observations are restored.
- **Expect:** 1. "Host configuration unchanged; Nagios was not reloaded." 2. The newly found SSH port is recorded, but one missed scan does not remove the old port or force an SSH-port switch. An unchanged config is valid when no enabled plugin changes the generated services. The old port is preferred until its lifecycle excludes it: after 5 missed scans a Suggested port archives, while a Monitored port becomes Missing and retains its Nagios service. Judge reload versus no reload against an actual generated-config change, not the physical move alone (`Data_Model_and_Integrations.md`, port lifecycle; `port_lifecycle.py`, `age_unseen_port` and `device_ssh_port`). 3. The live SSH listener is back on 22. A separate five-scan lifecycle run is not implied by this one-rescan case. Mark `destructive`: always restore step 3.

#### J2-06 Cancel a scan
`[IC]` · VM · agent
- **Pre:** B0.
- **Steps:** Start a rescan; press Stop immediately.
- **Expect:** The run ends as Interrupted and System Logs shows "Network discovery was cancelled". (The stop route checks `network.discovery` in code and seeds `system.discover`; see `Implementation_Status.md`. If the administrator gets 403, record it as the listed known gap, not a new defect.)

#### J2-07 Pause and resume a device
`[FS]` · VM · agent
- **Pre:** B0, user holds `system.hosts.edit`.
- **Steps:** Pause `snmp01` from the drawer (confirm); read the Dashboard total and the Nagios `hosts.cfg`; resume (confirm).
- **Expect:** While paused the device shows the Paused label and "last known status", is left out of Dashboard and Network Health counts and of the active alerts, and is removed from the generated Nagios config; after resume it counts again. A user-log entry exists for each action (Device Inventory §12.3, ACs 27, 30–34).

#### J2-08 One record per host after rescans
`[RE]` · VM · agent
- **Pre:** J2-01.
- **Steps:** Run two rescans back to back; list `GET /api/system/network-health/hosts` and the device list; count records per IP.
- **Expect:** Exactly one record per IP, none in "Address Unknown" while its target is up. **Known defect #59:** if a duplicate appears, comment on #59 with the sequence and `Skipped (known: #59)`; do not file a new issue.

#### J2-09 Discovery settings apply to the next scan
`[FS]` · VM · agent
- **Pre:** B0, `settings.discovery`.
- **Steps:** In Settings > Network Discovery narrow TCP ports to `1-1024`, rescan, then add `8080`; save; rescan. (8080 is already inside the default range 1-10000, so adding it alone proves nothing.)
- **Expect:** A Configuration Change entry records the edit; `app01` (HTTP on 8080) shows a 8080/tcp port after the rescan. Restore the ports afterwards. **Dry run 2026-10-09 failed this** (the port was never recorded): known defect #66.

#### J2-10 Maintenance Mode suppresses scheduled scans
`[RE]` · MOCK · agent
- **Pre:** none.
- **Steps:** `scripts/verify.sh backend`; read `server/tests/unit/test_automation.py` for the maintenance case. On the lab, turn Maintenance Mode on in Settings > System.
- **Expect:** The unit test for maintenance passes. The UI shows the maintenance banner while the setting is on; turn it off afterwards. (Waiting for a 6-hour scheduled scan is not part of the loop.)

### J3. Deploy NCPA agents

**Detail:** `CUSTOM_CHECKS_AND_NCPA_ACCEPTANCE_TEST_PLAN.md` (N-01 to N-08),
`NCPA_PORTS_AND_SERVICE_IDENTIFICATION_LAB_TEST_PLAN.md`,
`docs/test-runs/2026-10-08-ncpa-fresh-run/` for the evidence format.

#### J3-01 Eligibility and selection
`[FS]` · VM · agent (UI)
- **Pre:** B0, `system.deploy.ncpa`.
- **Steps:** Open NCPA Deployment; read `GET /api/system/deployment/ncpa/devices`; try to select a device that is not eligible.
- **Expect:** Ubuntu targets are eligible and selectable. A device that is not eligible shows Incompatible or Excluded and cannot be selected. The lab has only Ubuntu targets, so exercise the Incompatible path in `MOCK` with `server/tests/unit/` NCPA eligibility tests and record which test names passed.

#### J3-02 Deploy to two targets
`[FS]` · VM · agent
- **Pre:** B0; `scripts/vmlab targets creds` for the login.
- **Steps:** In the wizard select `web01` and `legacy01`, verify and approve each host key, enter the device login, confirm. Or drive the same API with `scripts/vmlab ncpa`.
- **Expect:** The run ends Success; each device goes Pending NCPA then Deployed NCPA; `legacy01` deploys over its SSH port 2222.

#### J3-03 The SSH password is not persisted
`[SE]` · VM · agent
- **Pre:** J3-02.
- **Steps:** Inspect the deployment run and trusted-device records (`GET /api/system/deployment/ncpa/runs/<id>`, `/devices/trusted`) and the application database.
- **Expect:** Only port, key-installed flag and key fingerprint are stored; no password appears in any response or table. Report "not persisted" without printing values.

#### J3-04 Host key must be approved
`[SE]` · VM · agent
- **Pre:** B0.
- **Steps:** Start the wizard for a device and try to continue without approving its fingerprint; where the API allows, call `check-credentials` before `confirm-trust`.
- **Expect:** The wizard blocks until the fingerprint is approved; the API refuses an unapproved key.

#### J3-05 The NCPA services are OK
`[RE]` · VM · agent
- **Pre:** J3-02; `check_ncpa` (listed as `check_ncpa.py`) enabled in Plugin Manager (J4); wait for one Nagios check cycle.
- **Steps:** Read the NCPA services from `GET /api/system/network-health/services` or Nagios `status.dat`.
- **Expect:** Three NCPA services per deployed host (CPU, root disk, memory in the 2026-10-08 run; the paper also lists running processes, p.10, which that run did not show), each with real output, normally OK (a WARNING is a genuine threshold hit, for example memory near 50 %); none CRITICAL with exit code 127. If 127 appears, the installer fix for #45 is missing: reopen #45.

#### J3-06 Deployment is logged
`[SE]` · VM · agent
- **Pre:** J3-02.
- **Steps:** Read System Logs > NCPA Deployment.
- **Expect:** An entry per run with who started it, time, and the outcome (for example "Deployment completed with 1 failure(s)" for a partial run).

#### J3-07 One bad device fails only that device
`[RE]` · VM · agent
- **Pre:** B0, `web02` not yet deployed.
- **Steps:** Deploy to `web02` and `app01` with a deliberately wrong login for `web02` only (use a throwaway wrong value; never log it).
- **Expect:** The run ends Partial Failure; `web02` is Deployment Failed with a readable reason; `app01` is Deployed NCPA. Then redeploy `web02` correctly or revert it.

#### J3-08 Cancel a deployment
`[RE]` · VM · agent
- **Pre:** B0.
- **Steps:** Start a deployment and press Stop.
- **Expect:** The run ends Interrupted; devices not yet reached stay Pending NCPA or return to their previous state; the log records the interruption.

#### J3-09 One record per host after deployment
`[RE]` · VM · agent
- **Pre:** J3-02, J2-08.
- **Steps:** Count device records for 10.77.0.6.
- **Expect:** One. **Known defect #59** applies exactly as in J2-08.

### J4. Enable a plugin and put it to work

**Detail:** `PLUGIN_DRIVEN_MONITORING_ACCEPTANCE_TEST_PLAN.md`, `PLUGIN_DRIVEN_MONITORING_LAB_TEST_PLAN.md`, `CUSTOM_CHECKS_AND_NCPA_ACCEPTANCE_TEST_PLAN.md`.

#### J4-01 Plugin inventory is consistent and reads 65
`[FS]` · VM · agent
- **Pre:** B0, `plugin.view`.
- **Steps:** Open Plugins; read the Installed tile, the All Plugins table row count and `GET /api/plugin/summary`.
- **Expect:** All three agree and read **65** on an installer-built appliance (journeys D-4). A different number: record it, file one `needs-decision`, and judge only that the three agree.

#### J4-02 Scan for Plugins refreshes the inventory
`[FS]` · VM · agent
- **Pre:** J4-01.
- **Steps:** Press Scan for Plugins; poll `GET /api/plugin/scan/status`.
- **Expect:** The scan reaches a terminal status; the tiles (Installed, Active Capabilities, Custom, Updates Available, Validation Issues) equal the counts in the tables; Installed still reads 65.

#### J4-03 Enable a port-driven plugin
`[FS]` · VM · agent
- **Pre:** J2-01; `plugin.enable`.
- **Steps:** Open `check_ssh`; read the enable preview (`GET /api/plugin/<id>/enable-preview`); enable it; repeat for `check_http`.
- **Expect:** The preview names the services and devices; after enabling, exactly those services exist (Currently Running lists device, IP, service and running-since); Nagios loads the config (no reload error) and the services leave Pending within two check cycles.

#### J4-04 Enabled services report real status
`[RE]` · VM · agent
- **Pre:** J4-03.
- **Steps:** Read the service states from `GET /api/system/network-health/services`.
- **Expect:** `ssh` services on the five targets (`legacy01` on port 2222) are OK with plugin output text; `http` services are OK on `web01` and `web02` (port 80). `app01` serves HTTP on 8080: record whether the enable preview attached a service to it, and judge that service OK only if it did. The Nagios server's own `localhost` services are unaffected.

#### J4-05 Plugin actions are logged
`[SE]` · VM · agent
- **Pre:** J4-03.
- **Steps:** Read the Activity Log.
- **Expect:** Entries for `plugin.enable` (and `plugin.validate` if a validation was run) with user and time. No `plugin.configure` entry is expected.

#### J4-06 Disable removes the services; enable restores them
`[FS]` · VM · agent · destructive
- **Pre:** J4-03; `plugin.disable`.
- **Steps:** Disable `check_http`; read the services; enable it again.
- **Expect:** Disabled: no `http` services and no `http` alerts. Enabled again: the same services come back.

#### J4-07 A plugin with no port cannot be enabled
`[FS]` · VM · agent
- **Pre:** J4-01.
- **Steps:** Open `check_ping` or `check_load` and try to enable it.
- **Expect:** The UI shows "Not service-driven" and no enable action. **Not a defect** (`Implementation_Status.md` "Plugins with no port").

#### J4-08 Validation Issues tile matches the table
`[FS]` · MOCK · agent
- **Pre:** none.
- **Steps:** Run the plugin validation unit tests (`scripts/verify.sh backend`; `server/tests/unit/` plugin validator tests).
- **Expect:** The validator tests pass. On the lab, the Validation Issues tile equals the number of plugins marked as having validation issues. (There is no UI to create an invalid plugin, because custom upload is disabled.)

### J5. Break a service, see the alert

**Detail:** `PLUGIN_DRIVEN_MONITORING_ACCEPTANCE_TEST_PLAN.md` F-03, F-05; `docs/test-runs/2026-10-08-vm-lab-remaining/` for the evidence format.

#### J5-01 A host going down raises an alert
`[RE]` · VM · agent · destructive
- **Pre:** B0. Record the active alerts first (`GET /api/system/dashboard/alerts?limit=100`).
- **Steps:** `scripts/vmlab targets break web01 host`; poll the alerts every 15 s for up to the check interval times retries plus 2 minutes.
- **Expect:** A new alert for 10.77.0.2's host appears, state DOWN or CRITICAL. Record the elapsed time from the break command to the alert as the **detection delay** (reported, not judged; journeys D-9). Always run `scripts/vmlab targets fix web01 host` at the end.

#### J5-02 Counts rise by the same amount everywhere
`[FS]` · VM · agent · destructive
- **Pre:** J5-01 while web01 is down.
- **Steps:** Read the Dashboard summary, Device Inventory totals, Network Health summary and the System Status counts.
- **Expect:** Hosts down rise by one on every page; Dashboard Active Alerts rises by the number of hosts plus services newly not OK/UP (X3).

#### J5-03 In-app notification appears
`[FS]` · VM · agent · destructive
- **Pre:** J5-01 while web01 is down; `system.notifications`.
- **Steps:** `GET /api/system/notifications/unread-count` before and after; open the bell.
- **Expect:** The unread count increases and the bell lists an entry for the host.

#### J5-04 Alert and notification appear in History
`[FS]` · VM · agent · destructive
- **Pre:** J5-01.
- **Steps:** `GET /api/system/history/alerts` and `/history/notifications`; open History in the UI.
- **Expect:** The state change to DOWN is in Alerts History with timestamp and state; a matching event is in Notifications History when Nagios recorded one. If Notifications History has none, record that observation and do not file it unless `Alerts_Notifications_History_Requirements.md` §4 requires one for this event.

#### J5-05 A stopped service raises a service alert
`[RE]` · VM · agent · destructive
- **Pre:** F-ENABLE (J4-03).
- **Steps:** `scripts/vmlab targets break web01 http`; poll the alerts; then `scripts/vmlab targets fix web01 http`.
- **Expect:** A CRITICAL `http` service alert for web01 appears within the check interval; it clears after the fix. Without F-ENABLE no service alert is expected (not a defect).

#### J5-06 Recovery clears every page and is recorded
`[RE]` · VM · agent · destructive
- **Pre:** J5-01 or J5-05 followed by the fix command.
- **Steps:** Wait for the state to recover; read all pages and History.
- **Expect:** UP/OK everywhere (X3 holds again); Alerts History shows a recovery event with the recovery duration (`Alerts_Notifications_History_Requirements.md` §3.2).

#### J5-07 High CPU raises an alert from NCPA thresholds
`[RE]` · VM · agent · destructive
- **Pre:** F-NCPA and J3-05.
- **Steps:** `scripts/vmlab targets load web01 --seconds 90`; poll the CPU service state for 5 minutes.
- **Expect:** The NCPA CPU service moves to WARNING or CRITICAL while load is high and returns to OK afterwards. (Skipped in earlier runs; first lab run of this case.)

#### J5-08 Email within 3 seconds
`[FS]` · VM · agent
- **Status:** `Blocked (B8, not built)`. Recorded every run so the gap stays visible. When SMTP exists: mock SMTP server first, then a real Gmail account by hand as a `HUMAN` case.

#### J5-09 Alert path for a Staff user without acknowledge permission
`[SE]` · MOCK · agent
- **Pre:** none.
- **Steps:** Run the permission unit tests (`scripts/verify.sh backend`).
- **Expect:** `POST /api/system/dashboard/alerts/acknowledge` without `system.acknowledge_alerts` returns 403 in the tests.

### J6. Acknowledge a problem and trace it

**Detail:** `Display_Requirements.md` §4; `Alerts_Notifications_History_Requirements.md`.

#### J6-01 Acknowledge a DOWN or CRITICAL row
`[FS]` · VM · agent · destructive
- **Pre:** an active alert (J5-01 or J5-05).
- **Steps:** In Device Inventory or System Status press Acknowledge; confirm.
- **Expect:** The row shows "By <user>" and the action becomes Unacknowledge; `GET /api/system/dashboard/alerts?ack_filter=acknowledged` lists it. (API passed 2026-10-08; this case adds the browser.)

#### J6-02 Unacknowledge
`[FS]` · VM · agent · destructive
- **Pre:** J6-01.
- **Steps:** Press Unacknowledge.
- **Expect:** The acknowledgement is cleared on every page.

#### J6-03 The acknowledgement appears in History
`[FS]` · VM · agent
- **Pre:** J6-01 and J6-02 done.
- **Steps:** Open History.
- **Expect:** The acknowledge and unacknowledge actions appear with the acting user and time (Alerts History row detail: acknowledging user). A missing or wrong entry is a finding: the page is unaudited.

#### J6-04 Automatic resolution on recovery
`[FS]` · VM · agent
- **Pre:** an acknowledged alert whose target is then fixed.
- **Steps:** Fix the target; wait for UP/OK; read the active acknowledgement and History.
- **Expect (per spec):** the active acknowledgement is removed and an AUTO_RESOLVED record is appended. **Known gap:** not implemented. Record `Skipped (known gap: Implementation_Status "Auto-resolved acknowledgements")`.

#### J6-05 No acknowledge without permission
`[SE]` · VM · agent
- **Pre:** F-USERS with `qa-view` (dashboard only).
- **Steps:** Sign in as `qa-viewer`; look for the Acknowledge action; call the acknowledge route.
- **Expect:** No Acknowledge action is shown; the API returns 403.

### J7. Monitor and diagnose

**Detail:** `Display_Requirements.md` (Dashboard §1, Network Health §2); `Device_Inventory_Requirements.md` §10 and §12.4 (acceptance criteria 1–34).

#### J7-01 Dashboard content
`[FS]` · VM · agent
- **Pre:** B0 and F-ENABLE.
- **Steps:** Open the Dashboard; read `GET /api/system/dashboard/status` and `/summary`.
- **Expect:** Total hosts is 6 (the five targets plus the Nagios server's `localhost`; the smoke script expects the same); latency, warnings, critical issues, the up/down chart, the performance chart and the Nagios status panel render with values from the API and no error banner.

#### J7-02 Network Health content and time ranges
`[FS]` · VM · agent
- **Pre:** B0.
- **Steps:** Open Network Health; switch the time range for the latency, packet-loss and bandwidth views; read `GET /api/system/network-health/summary` and `/trends`.
- **Expect:** Online/offline devices, host availability and resource averages render; each view redraws for each range without error; averages are shown only with at least two data points.

#### J7-03 NCPA hosts show resources; ping-only hosts do not
`[FS]` · VM · agent
- **Pre:** F-NCPA.
- **Steps:** Open the host detail of `web01` (NCPA) and `snmp01` (no NCPA).
- **Expect:** `web01` shows CPU, memory and disk values; `snmp01` shows availability and latency only (and SNMP services if enabled).

#### J7-04 Refresh behavior
`[IC]` · VM · agent
- **Pre:** B0.
- **Steps:** Read the Dashboard refresh rate in Settings > General (default 5 min); press the manual refresh and measure the time to render.
- **Expect:** The default is 5 minutes; manual refresh updates the data. The 3-second budget is judged in PT-03.

#### J7-05 Network card and "Not configured" tiles
`[IC]` · VM · agent
- **Pre:** B0.
- **Steps:** Read the Network Health network card and the Bandwidth and Avg Response Time tiles; in Settings > Plugins > NCPA Metrics add a bandwidth row.
- **Expect:** The card renders its fields (IP range, gateway, subnet mask, DNS server, ISP, location, Last Scan) without error; the tiles read "Not configured" until set up, then show data once the row exists and NCPA reports it. Remove the row afterwards.

#### J7-06 System Status
`[FS]` · VM · agent
- **Pre:** F-ENABLE.
- **Steps:** Open `/topology` ("System Status"); filter by state, search by service name, sort, page.
- **Expect:** The OK / Warning / Unknown / Critical cards add up to the total; filters, search and sort change the rows; acknowledgement works on a non-OK row. The route name is not a defect (B9).

#### J7-07 Device Inventory table and drawer
`[FS]` · VM · agent
- **Pre:** B0.
- **Steps:** Open Device Inventory; use search and filters; open a drawer.
- **Expect:** Host table with IP, state, Monitoring chip, filter opening on Monitored; summary cards count monitored hosts only; the drawer shows host state, services and the Ports section. Check acceptance criteria 1–5 and 33 of `Device_Inventory_Requirements.md`.

#### J7-08 Ports section actions
`[FS]` · VM · agent
- **Pre:** J7-07, `system.hosts.edit`.
- **Steps:** On `app01` use Monitor, Ignore, Leave suggested, Set service and Remove pin on an HTTP-8080 port, confirming where asked; then repeat read-only as a user without `system.hosts.edit`.
- **Expect:** Each action behaves as `Device_Inventory_Requirements.md` §5–§6 and criteria 6–23 describe; a view-only user sees no action and the view-only note.

### J8. Report and export

#### J8-01 Host Availability report
`[FS]` · VM · agent
- **Pre:** B0 with several minutes of history.
- **Steps:** Report > Host Availability, Last 24 hours, Run Report; `GET /api/system/report/availability`.
- **Expect:** One row per monitored host with state, uptime %, snapshots, last check and last state change; uptime values are 0 to 100; the host total equals Device Inventory (X3).

#### J8-02 Network Services report
`[FS]` · VM · agent
- **Pre:** F-ENABLE.
- **Steps:** Report > Network Services, Run Report.
- **Expect:** One row per service name with an aggregate of OK/Warning/Critical across hosts; totals match the System Status counts.

#### J8-03 CSV export
`[FS]` · VM · agent
- **Pre:** J8-01.
- **Steps:** Export as CSV.
- **Expect:** A downloaded `.csv` with a header row and as many data rows as the table shows; it opens as text.

#### J8-04 Excel export
`[FS]` · VM · agent
- **Pre:** J8-01.
- **Steps:** Export as Excel.
- **Expect:** A `.xls` file (an HTML table, per `exportData.ts`) with the same rows; Excel opening it is a `HUMAN` check recorded in the notes. Do not require a binary `.xls`.

#### J8-05 PDF export is a print view
`[IC]` · VM · HUMAN
- **Pre:** J8-01.
- **Steps:** Export as PDF; use the browser's Save as PDF.
- **Expect:** A print-formatted window opens with the same rows; the saved PDF is readable. A person judges layout.

#### J8-06 Exports are logged
`[SE]` · VM · agent
- **Pre:** J8-03 to J8-05 done.
- **Steps:** Read System Logs > Export Log (`GET /api/system/exportlog`).
- **Expect:** One entry per export: who, report type, format, start, end, time (X2).

#### J8-07 Empty period
`[IC]` · VM · agent
- **Pre:** B0.
- **Steps:** Run the report for a period with no data (a custom range before the install).
- **Expect:** An empty state, not an error and not a blank page.

### J9. Manage accounts and roles

#### J9-01 Create a role with chosen permissions
`[FS]` · VM · agent
- **Pre:** B0.
- **Steps:** Manage Roles > add role `qa-view` with `system.dashboard` only.
- **Expect:** The role appears Active with exactly that permission; the Activity Log records the creation.

#### J9-02 Create a user with that role
`[FS]` · VM · agent
- **Pre:** J9-01.
- **Steps:** Manage Accounts > add `qa-viewer@example.test`, role `qa-view`, Active.
- **Expect:** The user appears Active with the role; Activity Log records "Created account for qa-viewer@example.test".

#### J9-03 Seeded role matrix
`[SE]` · MOCK · agent
- **Pre:** none.
- **Steps:** Read `server/app/api/commands/seed.py`; on the lab, `GET /api/user/roles` and `/api/user/roles/<id>` for each seeded role.
- **Expect:** Administrator holds all 34 seeded permissions; Manager and Staff hold none (journeys D-8). A new Manager or Staff user can open only Settings (General).

#### J9-04 Enforcement in the UI and the API
`[SE]` · VM · agent
- **Pre:** J9-02.
- **Steps:** Sign in as `qa-viewer`; open each sidebar page by URL; call one route per permission area (for example `GET /api/system/log`, `/api/system/report/availability`, `/api/user/accounts`, `POST /api/system/discover/start`).
- **Expect:** Only the Dashboard (and Settings) opens; other URLs redirect away; the API returns 403 for each route outside `system.dashboard`.

#### J9-05 Inactive and suspended users cannot sign in
`[SE]` · VM · agent
- **Pre:** J9-02.
- **Steps:** Set the user Inactive, then Suspended; try to sign in each time; set Active again.
- **Expect:** Sign-in is refused for both states; works when Active.

#### J9-06 Editing signs the user out
`[IC]` · VM · agent
- **Pre:** J9-02, the user signed in in a second browser session.
- **Steps:** Edit the user (change the role) and save.
- **Expect:** The edit dialog warns the user will be signed out; the second session is signed out on its next request. (The warning wording came from an older screenshot; judge the behavior.)

#### J9-07 Password reset stores a new hash and forces a change
`[SE]` · VM · agent
- **Pre:** J9-02.
- **Steps:** An administrator resets the user's password; sign in as the user.
- **Expect:** The old password no longer works; the new one signs in and the user is forced to change it (`Must_Change_Password`); the stored value is a different hash. The first-sign-in checkbox on creation belongs to #61 and is not asserted.

#### J9-08 Account list filters and export
`[IC]` · VM · agent
- **Pre:** J9-02.
- **Steps:** Use the Active, Inactive and Suspended filters; press Export.
- **Expect:** Each filter shows only that status; Export downloads a file. Record the format and whether an Export Log entry appears (the paper does not say; SHOT p.147 only shows the button).

#### J9-09 Settings scope
`[FS]` · VM · agent
- **Pre:** two users, both able to open Settings.
- **Steps:** User A changes theme and Dashboard refresh rate; administrator changes scan frequency; read both users' Settings.
- **Expect:** Theme and refresh rate change only for user A; scan frequency changes for everyone, as the labels say.

### Invariants

#### X1-01 The main path needs no shell and no `.cfg` edit
`[IC]` · VM · agent
- **Pre:** B0 fresh.
- **Steps:** Starting from a signed-in browser, complete discover (J2-02), enable `check_ssh` (J4-03) and see the alert (J5-01) using only the web UI for every user action. The agent may use the shell for fault injection and evidence only.
- **Expect:** Every user action in the path was possible in the UI; no step required SSH to the appliance or editing a Nagios file.

#### X2-01 State-changing actions are logged
`[SE]` · VM · agent
- **Pre:** the actions of J2-05, J3-02, J4-03, J8-03, J9-01, J9-02 performed.
- **Steps:** Read System Logs: Activity, Configuration Change, Network Discovery, NCPA Deployment, Export.
- **Expect:** Each action appears once in the category matching its type, with who, what and when.

#### X3-01 Counts reconcile at rest
`[FS]` · VM · agent
- **Pre:** B0, all five targets up, F-ENABLE.
- **Steps:** Read hosts up/down from the Dashboard, Device Inventory, Network Health and the Host Availability report.
- **Expect:** Identical hosts up and down on all four pages (six hosts up: the five targets and `localhost`). Dashboard Active Alerts equals the number of non-OK/UP hosts plus services.

#### X3-02 Counts reconcile with one host down
`[FS]` · VM · agent · destructive
- **Pre:** X3-01.
- **Steps:** `scripts/vmlab targets break app01 host`; wait for the alert; read the same four pages; fix.
- **Expect:** Hosts down is 1 on all four pages and hosts up is 5; Active Alerts rose by the same number on the Dashboard as the hosts and services that changed.

#### X3-03 Availability sanity
`[FS]` · VM · agent
- **Pre:** X3-02 complete and at least 30 minutes of history.
- **Steps:** Read availability for `app01` and an untouched host on Network Health and on Reports.
- **Expect:** The untouched host is at or near 100% on both; `app01` is lower than the untouched host on both; every value is between 0 and 100. **Equality between the two pages is not asserted** (journeys D-9 open); file one `needs-decision` if they differ.

#### X4-01 Unauthenticated access is refused
`[SE]` · VM · agent
- **Pre:** B0, no session.
- **Steps:** Request each browser route and each `/api` route in `Backend_Modules_and_Routes.md` without a cookie (read-only requests; do not send `POST` bodies that change data except `login`).
- **Expect:** Protected pages redirect to `/login`; protected APIs return 401; only `/login` and `POST /api/user/login` are public.

#### X5-01 Long operations end in a terminal status
`[RE]` · VM · agent
- **Pre:** B0.
- **Steps:** Observe a scan (J2-02), a deployment (J3-02) and a report run (J8-01).
- **Expect:** Each shows progress or a running state and ends in exactly one of Success, Failed, Partial Failure or Interrupted (a report ends in data or an error message).

### Performance and stability

#### PT-01 Initialisation ≤ 10 s
`[PE]` · VM · agent
- **Definition [INFER; the paper says only "System initialization ≤ 10 seconds", p.126]:** from starting the web service to the first successful authenticated response of `GET /api/system/dashboard/summary`.
- **Pre:** B0.
- **Steps:** On the appliance, restart the Pinpoint service (unit name from the healthcheck output); time until `GET /api/user/me` with a fresh session returns 200 and the dashboard summary returns data; repeat three times.
- **Expect:** The median of three runs is ≤ 10 s.

#### PT-02 Availability check of 10 hosts ≤ 5 s
`[PE]` · MOCK · agent
- **Definition:** server time for the availability endpoints with 10 monitored hosts. The lab has 5 targets (journeys A10), so use a fixture with 10 hosts.
- **Pre:** a scratch script using the Flask test client (`server/tests/support/` builders) that seeds 10 hosts with history rows.
- **Steps:** Time `GET /api/system/network-health/availability` and `GET /api/system/report/availability` ten times each.
- **Expect:** The 95th percentile of each is ≤ 5 s. Also record the same on the VM lab with 5 hosts as information.

#### PT-03 Dashboard refresh of 15 updates ≤ 3 s
`[PE]` · VM · agent
- **Pre:** at least 15 hosts and services reporting. Count them from `GET /api/system/dashboard/summary`; if F-ENABLE and F-NCPA give fewer than 15, enable more port-driven plugins (J4-03) until the Dashboard lists 15.
- **Steps:** In the browser press the Dashboard manual refresh; measure from click to the last Dashboard request finishing (Performance API or devtools network timings); repeat five times.
- **Expect:** The median of five is ≤ 3 s.

#### PT-04 Alert visible ≤ 3 s after the Nagios state change
`[PE]` · VM · agent · destructive
- **Definition (DECIDED, journeys D-9):** the clock starts at the Nagios `last_state_change` of the host or service; it stops when the alert appears in `GET /api/system/dashboard/alerts` (and the bell).
- **Pre:** B0.
- **Steps:** `scripts/vmlab targets break web02 host`; poll the Pinpoint alerts every second and Nagios `status.dat` for web02's `last_state_change`; stop when the alert appears; fix web02. Repeat twice.
- **Expect:** (alert seen time − `last_state_change`) is ≤ 3 s in both runs. Also report the detection delay (break command to `last_state_change`) separately. If the app polls Nagios only every 60 s, a longer lag is the finding; file it with the measured numbers.

#### PT-05 Stability over a 4-hour soak
`[RE]` · VM · agent
- **Definition:** the paper lists PT-05 as "Continuous" "System stability" with no threshold (p.126); the criteria below are the team's.
- **Pre:** B0 with F-ENABLE and F-NCPA; no other VMs competing for RAM (the appliance has 4 GB, below the paper's 8 GB minimum; journeys D-6).
- **Steps:** 1. Record the start time, appliance `uptime`, the Gunicorn and Nagios PIDs and free memory. 2. Every 5 minutes for 4 hours: `GET /api/user/me` (after login), `GET /api/system/dashboard/summary`, free memory, and the count of new log lines containing a traceback or HTTP 500 in the Gunicorn journal. 3. At the end repeat step 1.
- **Expect:** No Gunicorn or Nagios restart (same PIDs, uptime unbroken); no traceback or unhandled HTTP 500 in the journal; the API answered 200 at every sample; fresh status rows were added in each hour (scheduler alive); free memory did not fall by more than 30% from start to end without recovering. Any miss is a `Fail` with the sample time.

### Black-box acceptance (paper pp.124-125)

The black-box cases restate the paper's acceptance tests (Core Functionality Test Cases, pp.124-125) as aggregates of the cases above, so there is one definition of each behavior. The module, input and expected output columns are the paper's words; the *Passes when* column is the mapping to cases. The paper owner should confirm the mapping.

| ID | Paper module / input → expected output | Passes when | ISO | Env |
|---|---|---|---|---|
| BB-01 | Automated Nagios Deployment: administrator initiates deployment → Nagios Core installed and configured | J1-01, J1-02, J1-03 pass (J1-06 by a human before release) | FS | VM |
| BB-02 | Agent Installation: deployment commands sent to hosts → monitoring agent installed and configured automatically | J3-02 and J3-05 pass | FS | VM |
| BB-03 | Device Monitoring: client device connected to the monitoring server → system detects host availability and status | J2-03 and J7-07 pass | FS | VM |
| BB-04 | Service Monitoring: monitoring service enabled → system displays service health and status | J4-03 and J4-04 pass | FS | VM |
| BB-05 | Alert Notification System: service failure detected → system generates alert notification | J5-05 and J5-03 pass (J5-01 covers a host; J5-08 stays `Blocked` until B8) | RE | VM |
| BB-06 | Network Discovery: discovered devices → structured view of the network | J2-01 and J2-03 pass | FS | VM |
| BB-07 | Dashboard Visualization: data collected from devices → summarized network health information | J7-01 and J7-02 pass (J7-03 and J7-06 add detail) | FS | VM |

---

## 6. Run outputs

1. **Report.** Start with `scripts/new_test_run.sh <slug> docs/qa/QA_Test_Plan.md`. One row per case ID with `Pass`, `Fail`, `Blocked` or `Skipped` and a note of what was observed. Sanitize before committing (`docs/test-runs/README.md`).
2. **Failure → issue.** For each `Fail`: search open issues for the case ID and the symptom first. If none, file one issue whose title begins with the case ID (for example `J5-01: host down raises no alert`), with the commit tested, the steps, expected vs observed, and the evidence file name. Link it in the report row.
3. **Known gap.** Record `Skipped (known gap: <ref>)` and comment on the open issue instead of filing.
4. **Source conflict.** When the plan, a spec and the code disagree and the journeys file §0 order does not settle it, file one issue labelled `needs-decision`, record the case as `Blocked`, and **continue with the next case**. The loop never stops for a conflict.
5. **Human cases.** `Skipped (human)` with the reason; they stay on the release checklist.
6. **Retest.** A new run, a new report; never edit an old result (`docs/test-runs/README.md`).

(Labels `qa-found` and `needs-decision`, the severity rubric and the loop's resume and stop rules are part of issue #63 and are not defined here.)

---

## 7. Detail plans: what happens to them

The existing plans in `server/tests/plans/` are lab procedures for one subsystem. They
stay beside the tests they drive. This plan does not copy their cases; it names the ones
the loop reuses and says what is retired.

| Plan | Decision | Used by |
|---|---|---|
| `NETWORK_DISCOVERY_EXTENDED_TEST_PLAN.md` | **Keep as appendix** (libvirt lab procedures; the loop uses the VM lab instead). Its PM-01 to PM-05 are already superseded by the acceptance plan | J2 |
| `NCPA_PORTS_AND_SERVICE_IDENTIFICATION_LAB_TEST_PLAN.md` | **Keep as appendix** | J2, J3, J7-08 |
| `PLUGIN_DRIVEN_MONITORING_LAB_TEST_PLAN.md` | **Keep as appendix** (manual, upgrade and rollback cases the loop does not run) | J4 |
| `PLUGIN_DRIVEN_MONITORING_ACCEPTANCE_TEST_PLAN.md` | **Keep as appendix;** its F-, L-, and permission cases are the deep versions of J4, J5, J9 | J4, J5, J9 |
| `CUSTOM_CHECKS_AND_NCPA_ACCEPTANCE_TEST_PLAN.md` | **Keep as appendix;** N-04 and C-02 (Nagios accepts and runs what the code generates) are release-gating | J3, J4 |
| `PLUGIN_DRIVEN_MONITORING_HARNESS_ADJUSTMENT_PLAN.md` | **Keep, not a test plan.** A proposal for the libvirt harness; nothing in it is run by the loop | none |
| `TEST_APPROACH_ADJUSTMENT_PLAN.md` | **Keep, not a test plan.** The proposed deterministic browser-to-Nagios runner; superseded in spirit by #63's Playwright setup but not retired until that lands | none |
| `historical/TEST_FAILURES.md` | **Keep as history** | none |

Nothing is deleted. When a deep case from an appendix becomes part of the loop, add a
case here with a new ID and link it; do not renumber the appendix.

---

## 8. Cases a human must run

| Case | Why |
|---|---|
| J1-06 | Physical console, the installer ISO's interactive screens |
| J8-05 | Judging a printed page; the browser's PDF dialog |
| J8-04 (Excel opens the file) | Needs Excel |
| J5-08 (when built) | A real mail account |
| PT-05 sign-off at release (optional) | The loop runs 4 h; a person may extend to 24 h for release |

---

## 9. Maintenance and checks

- **Adding a case:** give it the next free ID in its group, a single ISO tag, an environment and an executor, a precondition, steps and an **Expect** a machine can judge. Never reuse or renumber an ID.
- **Coverage table (§3):** regenerate the case counts after any change with the command below; the table lists the IDs per tag.
- **Drift:** `scripts/verify.sh docs` checks that relative links here resolve. A check that every traceability row cites an existing case ID is part of #63.

```bash
python3 -I - <<'EOF'
import re, pathlib
text = pathlib.Path("docs/qa/QA_Test_Plan.md").read_text(encoding="utf-8")
tags = {}
for m in re.finditer(r"^#### ([A-Z]+\d*-\d+)[^\n]*\n`\[([A-Z]{2})\]`", text, re.M):
    tags.setdefault(m.group(2), []).append(m.group(1))
for tag in ("FS", "PE", "IC", "RE", "SE"):
    print(tag, len(tags.get(tag, [])), ", ".join(tags.get(tag, [])))
EOF
```
