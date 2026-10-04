# NCPA, SSH-Port and Service-Identification Lab Test Plan

**Status:** Draft for review
**Test level:** Live manual lab (supplements the Tier 2 plan; nothing here is automated yet)
**Code under test:** branch `fix/ncpa-merge`, which contains the per-device SSH
port, the configurable NCPA port, fingerprint-based service identification and
the repaired NCPA deployment page
**Companion plan:** [`NETWORK_DISCOVERY_EXTENDED_TEST_PLAN.md`](NETWORK_DISCOVERY_EXTENDED_TEST_PLAN.md)

## 1. Purpose and scope

The unit tests for these changes mock nmap, SSH, paramiko and Nagios. This plan
checks what they cannot: real nmap output, a real SSH server on a non-standard
port, a real NCPA install with a changed listener port, a real database
upgrade, and the NCPA deployment page after the merge repair.

### 1.1 Already covered: not repeated here

These cases already exist and use the standard ports (SSH 22, NCPA 5693). They
stay as they are. Where this plan needs them on the new target, it says
**repeat** and adds only the extra evidence.

| Existing case | Where | This plan |
|---|---|---|
| NCPA-01 fingerprint trust, NCPA-02 changed fingerprint, NCPA-03 deploy, NCPA-04 metrics | Extended plan §11 | Repeat on the non-standard-port target (§7.1) |
| NCPA deployment, logical disks, runtime provenance | Extended plan §16 | Repeat on the non-standard-port target |
| `PLG-NCPA-CPU/MEMORY/DISK` | `plugin-cases.example.json` | Unchanged |
| ND-05 UDP services, ND-07 TCP 9000, ND-09 unchanged rescan | Extended plan §11 | Extra assertions only (SVC-02, SCAN-02, MIG-01) |
| DS-01..03 discovery settings, SEC-01 secret screening, CLEAN-01 restore | Extended plan §11 | Run as written; SEC-01 must include the new runs |
| Deployment page unit tests (wizard, runs, review) | `spec files/NCPA_Deployment_UI_Plan.md` §8 | Mocked only; lab acceptance is DEP-01 |

### 1.2 New in this plan

| Area | Cases |
|---|---|
| Database upgrade and first boot of this branch | MIG-01, BOOT-01 |
| What nmap really reports (gate for the next group) | SVC-00 |
| Services identified by fingerprint, port rules, pinning, review items | SVC-01 .. SVC-06 |
| Scan range and UDP cost | SCAN-01, SCAN-02 |
| NCPA over a non-standard SSH port | NCPA-05 .. NCPA-09 |
| Deployment page on the real server | DEP-01 |
| Non-default NCPA listener port | NCPA-10 |
| Cleanup specific to this plan | CLEAN-02 |

## 2. Unverified assumptions this plan exists to check

If one of these fails, record it as a defect rather than adjusting the case.

1. nmap marks a probed service `method="probed"` and TLS-wrapped HTTP
   `tunnel="ssl"` (SVC-00). The classifier depends on both.
2. (Corrected after the 2026-10-05 run.) Stock `ncpa.cfg` has only a commented
   `# port =` under `[listener]`; the install script now replaces any port line
   with exactly one, so the agent must listen on `NCPA_PORT` only (NCPA-10).
3. Deploying with port 22 closed succeeds only if the pinned port is used
   everywhere, including paramiko's host-key lookup (NCPA-08).
4. `-sU -sV` does not make discovery unacceptably slower (SCAN-02).
5. The install script does not open a firewall port, so a non-default
   `NCPA_PORT` is blocked on hosts running `ufw` unless opened by hand (NCPA-10).

## 3. Preconditions

- Complete the existing tester handoff (Extended plan §8.3). Use the existing
  isolated `/28`. Never scan the management network. Do not create a second lab.
- Credentials come from environment variables only. Never paste passwords,
  NCPA tokens or private keys into shell history, evidence or the report.
- Back up before anything else: `cp server/system.db server/system.db.pre-ports`.
- Record `git log -1 --oneline` of the deployed code and
  `sqlite3 server/system.db "select version_num from alembic_version"` as the
  starting revision.
- The `sqlite3` CLI may be missing on the host: use Python's `sqlite3` module for
  the queries below.
- NCPA deployment needs internet on the guest (`apt`, `repo.nagios.com`); attach a
  temporary NAT interface to the target for deployments and detach it before scans.
- The deployment API logs in with a username and password, but the guests allow
  key login only: create throwaway password accounts for the test and remove them
  afterwards (they are removed by restoring the baseline).
- The deploy key pair is read from `$HOME/.ssh/pinpoint_ncpa_deploy(.pub)` of the
  user running the app; a `flask run` session needs one.
- Baseline restores recreate the live overlay on `*-baseline.qcow2`; re-authorize
  any test SSH key that is not in the baseline image.
- Keep hypervisor console access to the guests. Moving sshd (NCPA-05..09) closes
  port 22, so recovery must not depend on SSH.
- Use **target01** only for the existing standard-port cases. Use **target02** for
  everything new, and restore its baseline between stages as the table in §4 says.

### 3.1 Helper queries

```bash
DB=server/system.db
# Ports of a device and how each service was decided
sqlite3 $DB "select Port_Number, Service_Name, Identified_By, Port_State, Plugin_Name, Source
             from OPEN_TCP_Services where NetDiscoveryID=<id> order by 1;"
# SSH trust: pinned port and whether a key is stored
sqlite3 $DB "select SSH_Port, Key_Fingerprint is not null from SSH_CREDENTIALS where NetworkDiscoveryID=<id>;"
# Review items
sqlite3 $DB "select Kind, Message, Resolved_At from DEVICE_REVIEW_ITEM order by ReviewID;"
# Deployment run and per-device results
sqlite3 $DB "select r.Hostname, r.IP_Address, r.Outcome, r.Error from NCPA_DEPLOYMENT_RESULT r order by r.NCPADeployResultID;"
```

Enums are stored by name (`FINGERPRINT`, `MONITORED`, `PORT_RULE`, ...).

## 4. Fixtures and order

### 4.1 Fixtures on target02

| Port | Listener | Command (run as root on target02) | Purpose |
|---:|---|---|---|
| 80 | A second **sshd**, not a web server | `/usr/sbin/sshd -p 80 -o PidFile=/run/sshd-80.pid` | Fingerprint must beat the port number |
| 8080 | Plain HTTP | `python3 -m http.server 8080 --directory /tmp` | Plain HTTP on an alternate port |
| 8443 | HTTP over TLS | `openssl req -x509 -newkey rsa:2048 -nodes -keyout /tmp/k.pem -out /tmp/c.pem -days 2 -subj /CN=lab; openssl s_server -accept 8443 -cert /tmp/c.pem -key /tmp/k.pem -www` | TLS must be detected |
| 5666 | Accepts, then closes | `socat TCP-LISTEN:5666,reuseaddr,fork SYSTEM:true` | Nothing for nmap to fingerprint; falls back to the configured name |
| 5667 | Accepts, then closes | `socat TCP-LISTEN:5667,reuseaddr,fork SYSTEM:true` | A second guess-only port, kept unpromoted for SVC-03 |
| 9443 | HTTP over TLS | As 8443, with `-accept 9443` | Inside the default range, above 6000 |
| 10050 | Plain HTTP | `python3 -m http.server 10050` | Just outside the default range |
| 40000 | Plain HTTP | `python3 -m http.server 40000` | Ephemeral range, must not be recorded |
| 8444 | HTTP over TLS | As 8443, with `-accept 8444`; **start only when SVC-04 says so** | Port-rule precedence |

These are for Stages 1-2, with sshd still on port 22. The non-standard sshd of
Stages 3-4 is set up separately in 4.2. Start the fixtures in the background and
record which are running before each scan.
Target01 keeps its existing manifest, including the unknown listener on 9000.

### 4.2 Moving sshd to 2222 (target02)

On Ubuntu 22.10 and later sshd is socket-activated, and changing `Port` in
`sshd_config` alone has no effect. Either turn the socket off first
(`systemctl disable --now ssh.socket && systemctl enable --now ssh.service`) or
override `ListenStream`. Then set `Port 2222` in
`/etc/ssh/sshd_config.d/99-lab.conf`, restart, and confirm with
`ss -ltn | grep -E ':(22|2222) '` that **only 2222** listens. Use the hypervisor
console if the session drops.

### 4.3 Order

| Stage | Cases | Target02 state |
|---|---|---|
| 0 | MIG-01, BOOT-01 | any |
| 1 | SVC-00 (gate) | fixtures running, SSH on 22 |
| 2 | SVC-01 .. SVC-06, SCAN-01, SCAN-02 | fixtures running, SSH on 22 |
| 3 | Restore baseline, then move SSH (4.2) | SSH on 2222 only |
| 3 | NCPA-05, NCPA-06, NCPA-07, then NCPA-02 repeat (§7.1) | SSH on 2222, then moved to 2022 and left there |
| 4 | DEP-01 sub-cases c, d, e | not yet deployed |
| 4 | NCPA-08 (deployment; also DEP-01 sub-cases a, g) | SSH on 2022 only |
| 4 | DEP-01 sub-cases b, f, h, i; repeat table 7.1; NCPA-09 and the NCPA-07 probe (optional) | deployed |
| 5 | Restore baseline, SSH on 22 | pre-NCPA, standard SSH |
| 5 | NCPA-10 | SSH on 22 |
| 6 | CLEAN-02, then CLEAN-01 | restored |

Stop after SVC-00 if its gate fails (see SVC-00).

## 5. Stage 0: upgrade and boot

### MIG-01: upgrade a copy of the real database

1. Work on a copy. Record the starting revision.
2. `flask db heads` prints exactly one head, `f3b7d2e8a614`. Two heads mean the
   merge migration is missing.
3. `flask db upgrade` (upgrades both databases; `--multidb` is not an option), then check `alembic_version` equals
   `f3b7d2e8a614`.
4. `OPEN_TCP_Services` and `OPEN_UDP_Services` have `Identified_By`;
   `DISCOVERY_SETTINGS` has `TCP_Forced_Services` and `UDP_Forced_Services`;
   `NCPA_DEPLOYMENT_RESULT` exists.
5. Existing ports keep their state and plugin, and `Identified_By` is `NULL`.
6. Start the app, then run an unchanged scan (as ND-09). No duplicate hosts or
   services appear, and no existing service is renamed.
7. Any `SERVICE_CHANGED` review item raised by that rescan must be explained by a
   real mismatch between a port's frozen plugin and what nmap now reports.
   Record each one.

**Pass:** one head, all columns present, existing monitoring unchanged.

### BOOT-01: a clean install of this branch starts

1. From a fresh clone: `python -m compileall -q app` exits 0, and
   `SECRET_KEY=x FLASK_DEBUG=1 python -c "import app"` prints no error.
2. On an empty database, `flask db upgrade` (upgrades both databases; `--multidb` is not an option) reaches `f3b7d2e8a614`.
3. `flask run` serves the login page; the log has no traceback at startup.
4. If the installer is available, run it against this branch. First boot must
   get past the step that failed on `main` and create the admin account and the
   credentials file.

**Pass:** the app imports and boots on a clean database.

## 6. Service identification (Stages 1-2)

### SVC-00: capture what nmap really reports (gate)

Run the same options the scanner uses, against target02 with SSH on 22 and the
fixtures running, and save the XML as evidence:

```bash
sudo /usr/local/bin/nmap-sudo -sV -O --version-all --open \
  -p 22,80,5666,8080,8443,9443 -oX tcp.xml <target02-ip>
sudo /usr/local/bin/nmap-sudo -sU -sV --open -p 53,123,161 -oX udp.xml <target02-ip>
```

| Port | Expected `<service>` |
|---:|---|
| 22, 80 (sshd) | `name="ssh"` `method="probed"` |
| 8080 | `name="http"` `method="probed"` |
| 8443, 9443 | `name="http"` `tunnel="ssl"` `method="probed"` |
| 5666 | `tcpwrapped`, `unknown`, or `method="table"` (anything but a probed, named service) |
| UDP 53, 123, 161 | named services; record `method` |

**Gate:** if SSH on 80 is not `method="probed"` as `ssh`, or TLS HTTP lacks
`tunnel="ssl"`, stop. The classifier's assumptions are wrong; attach the XML and
raise a defect before running SVC-01..06.

### SVC-01: fingerprint beats the port number

Run discovery. Expected for target02:

| Port | `Service_Name` | `Identified_By` | `Port_State` | Nagios service / command |
|---:|---|---|---|---|
| 80 | `ssh` (not `http`) | `FINGERPRINT` | `MONITORED` | `ssh-80-tcp`, `check_ssh -p 80`; no `http-80-tcp` |
| 8080 | `http` | `FINGERPRINT` | `MONITORED` | `http-8080-tcp`, `check_http -p 8080` |
| 8443, 9443 | `https` | `FINGERPRINT` | `MONITORED` | `https-8443-tcp`, command `pinpoint_nd_https` with `-S`; state OK |

Verify the live command in Nagios' status data (as the provenance rule in §16),
not only the service description.

### SVC-02: a guess is a suggestion (extends ND-07)

- Port 5666 (accepts and closes) on target02 is stored with
  `Identified_By = PORT_HINT` and `Port_State = SUGGESTED`. Port 9000 on target01
  is probed by nmap as `echo`, so it is `FINGERPRINT` / `SUGGESTED`; for the
  guess-only case use a listener nmap cannot name. A port that accepts and closes
  (`tcpwrapped`) is stored with service name `unknown`.
- Neither appears in the generated Nagios config.
- Promote 5666 through `PUT /api/system/hosts/<id>/ports/tcp/5666` with
  `{"state": "MONITORED"}` (the existing ND-07 flow). It becomes monitored.

### SVC-03: a guess confirmed later starts monitoring

1. Port 5667 (accepts and closes) is discovered and left alone: `PORT_HINT`,
   `SUGGESTED`, not in Nagios. Do not promote it.
2. Stop that listener and start `python3 -m http.server 5667`.
3. Rescan. Expected: `Service_Name` `http`, `Identified_By` `FINGERPRINT`,
   `Port_State` `MONITORED`, `Plugin_Name` `http`, and a new `http-5667-tcp` service.

### SVC-04: an "always treat port as" rule wins

1. Settings → Discovery. By default **Always Treat Port As** shows TCP
   `5693 → ncpa`. If it does not, saved settings are overriding the defaults.
   Use "Reset to Defaults" and record that.
2. Start the 8444 TLS fixture. Add the rule TCP `8444 → http`. Save, then rescan.
3. Expected: port 8444 is `http`, `Identified_By = PORT_RULE`, `MONITORED`, with
   service `http-8444-tcp` using `check_http` **without** `-S`. Against a TLS
   server this check is expected to fail; record its state. The point is that
   the rule beat the fingerprint (`https`).

### SVC-05: a service change is flagged, not applied

1. Remove the `8444 → http` rule and rescan twice.
2. Expected: the port keeps `Service_Name = http` and its plugin;
   `Observed_Service_Name` is `https`; exactly **one** unresolved
   `SERVICE_CHANGED` item says port 8444 is monitored as `http` but now
   identifies as `https`. The second rescan adds no duplicate.
3. `POST /api/system/discover/review/<id>/resolve` clears it. A later rescan
   raises it again only while the mismatch remains.

### SVC-06: pin one device's port

| Step | Request | Expected |
|---|---|---|
| Pin and monitor | `PUT /api/system/hosts/<id>/ports/tcp/5666` `{"service_name": "labsvc", "state": "MONITORED"}` (5666 is already monitored from SVC-02) | 200; `identified_by` `USER`; service renamed `labsvc-5666-tcp` with `check_tcp -p 5666`, OK while the listener accepts |
| Rescan twice | none | `Service_Name` stays `labsvc`; `Observed_Service_Name` shows nmap's guess; no review item |
| Bad names | `{"service_name": "Bad Name"}`, `"x;rm"`, a 40-character name, `7` | 400 each; database unchanged |
| Unknown port | pin `9999` | 404 |
| Not permitted | a user without `system.hosts.edit` | 403 |
| Log | Activity log | An entry "Pinned tcp port 5666 on <host> as labsvc and set it to Monitored" |

### SCAN-01: scan range

1. With the default `1-10000`: 9443 is discovered; 10050 is not.
2. Set TCP ports to `1-65535`, rescan: 10050 is discovered; 40000 is **not**
   recorded (ephemeral range).
3. Record the per-host TCP scan time for both ranges (from the discovery
   status timestamps and the log). Reset to defaults afterwards.

### SCAN-02: UDP cost (extends ND-05)

Run ND-05 as written, and also record `Identified_By` for UDP 53, 123 and 161.
Record the UDP phase time per host and the total discovery time. Compare with
the 2026-10-03 report. Investigate, do not automatically fail, if the total is
roughly double or more.

## 7. NCPA over a non-standard SSH port (Stages 3-4)

Setup: baseline-restore target02 (the §4.1 fixtures are not needed here), then
move sshd to 2222 per 4.2 so **only** 2222 listens. Keep the operator's console
open.

### NCPA-05: discovery picks the port

1. Run discovery. Target02 is a Linux device, so it gets SSH/NCPA placeholders.
2. Expected: port 2222 stored as `ssh`, `FINGERPRINT`, `MONITORED`; `ssh-2222-tcp`
   uses `check_ssh -p 2222` and is OK; port 22 is absent. The device is listed by
   `GET /api/system/deployment/ncpa/devices` as eligible.
3. `SSH_CREDENTIALS.SSH_Port` is still `22` at this point (the placeholder).

### NCPA-06: trust is read from, and pinned to, 2222 (extends NCPA-01)

1. `GET /api/system/deployment/ncpa/<id>/fingerprint`: `data.ssh_port` is `2222`.
   The fingerprint equals one of the target's host keys:
   `for k in /etc/ssh/ssh_host_*_key.pub; do ssh-keygen -lf $k -E sha256; done`
   (sshd offers several; record which matched).
2. `POST .../confirm-trust` with that fingerprint: 200. `SSH_CREDENTIALS` now has
   `SSH_Port = 2222` and the key; `DEVICE_IDENTIFIER` has an `SSH_HOST_KEY` row.
3. Post a fingerprint that is not the live one: 409 with `data.fingerprint` set to
   the live key, and nothing saved.
4. Power off the target (or drop 2222) and confirm: 502, nothing saved.

### NCPA-07: SSH moves after trust

1. With trust pinned to 2222, move sshd to **2022** (a lower number) and rescan.
2. `POST .../start`: 400 with `data.rejected` reason "Device unreachable.". No
   thread starts and no run is recorded.
3. `GET .../fingerprint` now reports `ssh_port` 2022 (both ports are monitored
   at this point and the lowest wins). Re-confirm trust: `SSH_Port` becomes 2022.
   `POST .../check-credentials` with valid credentials returns `ok`.
4. **Leave sshd on 2022.** Do not move it back: until the old port has been
   missing for `PORT_MISSING_AFTER_SCANS` (5) scans, 2022 still outranks 2222 by
   being lower, so trust could not be re-confirmed on 2222.

The next case deploys over this moved port.

### NCPA-08: deploy over the moved SSH port (extends NCPA-03)

SSH is on 2022 only, and 22 and 2222 are closed, so success proves every
connection used the pinned port:

1. `POST .../check-credentials`: correct login → `ok`; wrong password →
   `auth_failed`; an account without sudo → `no_sudo`. No password appears in the
   responses or the Pinpoint log.
2. Start the deployment (API or DEP-01). Expected: run finishes Success; the
   device's result row is `SUCCESS`; `NCPA_DEPLOYMENT.Agent_Status` is `DEPLOYED`.
   Driving this step from the browser is DEP-01 sub-cases a and g.
3. On target02: `ss -ltn` shows `5693`; the `pinpoint-deployment` user and
   helper exist; the target's `sshd` log shows the Pinpoint host logging in on the
   2022 listener.
4. Rescan. Port 5693 is stored `ncpa`, `Source = NCPA`, `Identified_By =
   FINGERPRINT`, `MONITORED`, plugin `ncpa`. `NCPADevicePartition` rows exist.

### NCPA-09: choosing between SSH ports (optional, after NCPA-08)

Run these only with `GET .../fingerprint`. Do not confirm trust on the deployed
device, except where a step expects it to fail.

1. **Standard port wins ties.** Start a second sshd on 22 (`systemctl start ssh`
   after re-enabling it, or `sshd -p 22`), rescan: the route reports 22.
2. **Hand-added port wins.** Add `2200` as ssh (`PUT .../ports/tcp/2200`
   `{"state": "MONITORED", "service_name": "ssh"}`) with nothing listening: the
   route reports 2200, and confirm-trust fails with 502. Record that a hand-added
   port that does not answer blocks trust. Then archive it (`{"state":
   "ARCHIVED"}`) and confirm the route reports 22 again.
3. **Known-limitation probe.** Stop the sshd on 22, move the other to **2300** (a
   higher number than 2022) and rescan once. By design the old port stays
   monitored until it has been missing for 5 scans, and the lowest candidate
   wins, so the route may still report 2022. Record what it reports after 1 scan
   and after 5. This is not pass/fail; the result decides whether a "SSH moved"
   flow is needed.

### 7.1 Repeat existing cases on the non-standard-port target

| Case | Extra evidence required |
|---|---|
| NCPA-02 changed fingerprint | Run it **between NCPA-07 and NCPA-08**, while the device is still undeployed (once deployed, `start` rejects with "NCPA is already deployed." before it looks at the key). Regenerate target02's host keys (`rm /etc/ssh/ssh_host_*; ssh-keygen -A`, restart sshd). `start` must reject "Host key mismatch."; `confirm-trust` with the old approval must return 409. Then fetch the new fingerprint, confirm it, and carry on to NCPA-08 |
| NCPA-04 metrics | CPU, memory and every logical disk service OK; record that SSH was on a non-standard port throughout |
| §16 disks and runtime provenance | Service commands are `check_ncpa`; `Identified_By` of the NCPA port is `FINGERPRINT` |
| SEC-01 secrets | Include the deployment logs and the check-credentials responses for these runs |

## 8. Deployment page on the real server

### DEP-01: wizard and run history (browser, Stage 4)

Use a user with `system.deploy.ncpa`. Not a repeat of NCPA-01..04: those prove
the API path; this proves the page and the run records the merge repair
restored.

Sub-cases c, d, e and g need a device that is not deployed yet. Run them in this
order on target02 (SSH on 2022, trusted): **c**, then **d**, then **e** (select
target01 and target02 together and stop right after the run starts; target01
must be at its pre-NCPA baseline for this), then **a/g**, which is the
successful deployment of NCPA-08. Run **b, f, h, i** afterwards.

| Sub-case | Action | Expected |
|---|---|---|
| a. Happy path | Select target02, approve the shown fingerprint, verify credentials, start | Progress is shown; the header status item appears; the run lists the device Pending → Running → Success |
| b. Run records | `NCPA_DEPLOYMENT_RESULT` after (a) | One row per device with hostname and IP copied, `Outcome` `SUCCESS`, `Error` empty |
| c. Wrong password | Verify the login, then change that account's password on the target, then Start | The device is `FAILED` "SSH authentication failed.", not Down |
| d. Host off | Verify the login, power the target off, then Start | Rejected "Device unreachable." before the run, or `DOWN` if it dropped mid-run. Power it back on afterwards |
| e. Stop | Stop during a multi-device run | Unstarted devices are `SKIPPED`; the run keeps its status |
| f. Already deployed | Start again for a deployed device | Rejected "NCPA is already deployed." |
| g. Retry | Retry a failed device after fixing the cause | It is deployable and succeeds |
| h. Review | History tab → mark the run reviewed | `Reviewed_At` set; the unseen-result flag clears; a second review is harmless |
| i. Permission | A user without `system.deploy.ncpa` | The page is hidden; the routes return 403 |

## 9. Non-default NCPA port (Stage 5)

### NCPA-10: listener on a configured port

Setup: baseline-restore target02 (pre-NCPA, SSH on 22).

1. In `server/config.py` set `NCPA_PORT = "5800"` (it is not read from the
   environment). Restart Flask. In Settings → Discovery use "Reset to Defaults",
   otherwise saved settings still force `5693` and hide the change. Confirm
   **Always Treat Port As** now shows `5800 → ncpa`.
2. If `ufw` is active on target02, allow `5800/tcp` yourself first; the install
   script does not open ports. Record whether it was needed.
3. Trust and deploy as in NCPA-06 and NCPA-08.
4. Expected on target02:
   - `sed -n '/^\[listener\]/,/^\[/p' /usr/local/ncpa/etc/ncpa.cfg` shows
     `port = 5800` (and no other section's `port` changed);
   - `ss -ltn` shows 5800 listening and **nothing** on 5693.
5. Deployment succeeds. If it fails with "NCPA is not listening ... on port 5800",
   the `[listener]` edit did not match the real file. Attach the listener section
   of `ncpa.cfg`.
6. Rescan: port 5800 is stored `ncpa`; services are named `ncpa-cpu-5800-tcp` and
   so on, run `check_ncpa -P 5800`, and are OK. `DEVICE_IDENTIFIER` has an
   `NCPA_CERT` row read from 5800.
7. Invalid values (optional): `NCPA_PORT = "0"`, `"70000"`, `"abc"` make the
   start route refuse with HTTP 500 and "NCPA_PORT must be an integer between 1
   and 65535." **before** any run or result row exists. Nothing is installed.

**After:** set `NCPA_PORT` back to `"5693"`, restart, use "Reset to Defaults".

## 10. Evidence, pass rules and cleanup

Use the evidence and sanitisation rules in the extended plan (§13, §14). For
every case keep: the exact request or command, the relevant database rows,
the Nagios object or command line where one is named, and the nmap XML for
SVC-00. Redact tokens, passwords and community strings before export.

The run passes when every case has a recorded result, SVC-00 passed, MIG-01 and
BOOT-01 passed, and every failure has evidence. A failed case is a finding, not
a reason to change the case.

### CLEAN-02: undo what this plan changed

- `NCPA_PORT` back to `"5693"`; discovery settings reset; Flask restarted.
- Fixture listeners stopped (`pkill` the ones started in 4.1); the second sshd on
  port 80 stopped.
- sshd back on port 22 on target02; hypervisor baselines restored for target02.
- Keep `server/system.db.pre-ports` until the findings are reviewed.
- Then run CLEAN-01 as written.
