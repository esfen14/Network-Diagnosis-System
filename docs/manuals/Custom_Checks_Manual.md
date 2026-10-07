# Custom Checks Manual

For Pinpoint administrators. It explains how to run Nagios plugins that discovery cannot attach to a
port: how to enable the port-driven ones, and how to add device checks, server checks and checks that
need a password.

**Applies to:** the build with `feature/host-level-checks`, `feature/server-host-checks` and
`feature/custom-check-secrets` (and the earlier custom checks work) merged. Design and decisions are in
[`Custom_Checks_Plan.md`](../plans/Custom_Checks_Plan.md); lab test cases are in
[`CUSTOM_CHECKS_AND_NCPA_ACCEPTANCE_TEST_PLAN.md`](../../server/tests/plans/CUSTOM_CHECKS_AND_NCPA_ACCEPTANCE_TEST_PLAN.md).

---

## 1. Which kind of plugin do I have?

Open **Plugin Manager** and click a plugin. The note under "Monitoring usage" tells you which kind it is.

| What the drawer shows | Kind | What you do |
|---|---|---|
| **Enable** and **Disable** buttons | Port-driven: discovery finds a port it can check | Click **Enable** (section 3). Nothing else to set up |
| "Not service-driven. There is no port… Add a custom check to run it against a device." and a **Custom checks** section | Device check: it probes a device but needs arguments | Add a check on a device (section 4) |
| "Not service-driven. This plugin checks the Nagios server itself. Add a server check…" and a **Server checks** section | Server check: it looks at the machine Nagios runs on | Add a server check (section 5) |
| "Checks the Nagios server itself through Nagios Core. Not managed here." | One of the five stock checks (`check_load`, `check_disk`, `check_swap`, `check_procs`, `check_users`) | Nothing: Nagios Core runs them and Pinpoint does not touch them |
| "Needs arguments Pinpoint cannot build yet." | `check_log`, `check_mrtg`, `check_mrtgtraf`, `check_dummy`, `check_dhcp` | Not available |
| "Its password cannot be passed to the plugin yet." | `check_dbi`, `check_oracle` | Not available |
| "Aggregates other services…" / "Replaced by check_ntp_time…" | `check_cluster`, `check_ntp` | Not available |

A plugin that takes custom checks never has an Enable button: enabling only attaches a plugin to ports
that discovery found, and these have none.

---

## 2. Before you start (once per installation)

1. **Update the code and run the migrations.** On the Pinpoint server, as the service user, from the `server`
   folder (back up `system.db` and `history.db` first):
   ```bash
   flask db upgrade
   flask sync-permissions
   ```
   `sync-permissions` creates `plugin.custom_check` and grants every permission to the role named exactly
   **Administrator**. If your admin role has another name, tick `plugin.custom_check` for it in **Manage Roles**.
2. **Restart the backend and sign out and in again.** Permissions are read at sign-in; without this the
   Custom checks section stays hidden.
3. **Set a fixed `SECRET_KEY`** in the service's environment file (for example `/etc/pinpoint/pinpoint.env`), or
   `PINPOINT_SECRETS_KEY`. Passwords are encrypted with it (section 7). Do not change it later without
   reading section 7.
4. **Restrict the Nagios host file.** If you will store passwords, the generated host file holds them in plain
   text (section 7). Make it readable only by the Nagios user and group, for example `chmod 640` with the right
   group.
5. **Check the Nagios server can reach what you will check:** a device on the network, the SSH key you will
   name, or the files and devices of the Nagios server itself.

Who can do this: only roles that hold `plugin.custom_check` see the sections and can use the routes. A
superuser is not special: if a role should have it, grant it.

---

## 3. Enable a port-driven plugin

These plugins are checked automatically on every discovered port they understand:

`check_tcp`, `check_udp`, `check_snmp`, `check_ncpa`, `check_http`, `check_ssh`, `check_ftp`, `check_smtp`,
`check_mysql`, `check_dns`, `check_ntp_time`, and, new in this build, `check_pgsql`, `check_ldap`, `check_ldaps`,
`check_rpc`, `check_ircd`, `check_time`, `check_ntp_peer`.

1. Plugin Manager → the plugin → **Enable**. The dialog counts what would be monitored; confirm.
2. The plugin becomes **Enabled**, then **Active** once a service is applied. Its services are listed under
   **Monitored services**.
3. Disable removes its services again; ports keep their state.

Notes for the new ones:

- `check_pgsql` needs a login name and `check_ldap` / `check_ldaps` need a search base. Until the device has
  them set, those ports are checked by the plain TCP check (so `check_tcp` must be enabled too). Reason texts say
  which plugin is checking a port.
- `check_ntp_peer` is an alternative to `check_ntp_time`. Choose it for a UDP 123 port with **Set service…** →
  `ntp_peer`.
- `check_ncpa` is stored as the file `check_ncpa.py`; it enables like any other plugin. It needs a `python`
  command on the Nagios server (or a `python3` shebang in the file).

---

## 4. Device checks: run a plugin against one device

Use this for `check_by_ssh`, `check_ups`, `check_clamd`, `check_hpjd`, `check_ifstatus`, `check_ifoperstatus`,
`check_breeze`, `check_wave`, `check_ssl_validity`, `check_nt`, `check_nwstat`, `check_overcr`, `check_real`,
`check_game`, `check_disk_smb`, `check_radius`, `check_mysql_query`, and the ping family (`check_ping`,
`check_icmp`, `check_fping`, `check_dig`).

### 4.1 Add a check

1. Plugin Manager → the plugin → scroll to **Custom checks** (below **Update**, above **Commands**).
2. Click **Add check**.
3. **Name:** letters, numbers, spaces, `.`, `_`, `-` (up to 60). It must be unique on that device.
4. **Device:** type part of a name or IP and click the device in the list. Only discovered, active devices appear.
5. Fill in the arguments. Required ones are marked `*`; the flag next to each label is the plugin option it
   becomes. See the tables in section 8.
6. Click **Add check**. The button stays disabled, with the first problem as its tooltip, until the form is valid.

What happens: Pinpoint writes the check into the Nagios host file, validates the whole configuration with
Nagios, and reloads it. If Nagios refuses, the form stays open with Nagios's message and **nothing is saved**.

### 4.2 Read the result

The check shows a status chip:

| Chip | Meaning |
|---|---|
| **Waiting** | Applied, not checked yet. Checks run about every 5 minutes |
| **OK**, **Warning**, **Critical**, **Unknown** | The plugin's last result, with its output beneath |
| **No recent data** | The last result is older than three check intervals (Nagios may be down or paused) |
| **Paused** | You paused it; nothing is checking |

The same service also appears in Network Health grouped under the plugin's name (`BY_SSH`, `UPS`, `PING`, …),
in the **Added plugins** widgets, and raises alerts like any other service.

### 4.3 Change, pause, resume, remove

- **Change:** rename it or edit its arguments. The device cannot change; remove the check and add it again.
- **Pause:** the service leaves Nagios but the check stays in the list. **Resume** puts it back.
- **Remove:** asks for confirmation, then deletes the check and its service.

Each of these is applied to Nagios the same way as adding. If Nagios refuses, the check stays exactly as it was.

### 4.4 Recipes

**Prove the whole path with `check_by_ssh`** (a good first test):
name `SSH works`, device any lab host, Command `/bin/true`, SSH user the account on that host, Identity file the
path of the key on the Nagios server (readable by the Nagios user). It goes Waiting → **OK** within about five
minutes. Change the command to `/bin/false` and it becomes **Warning**.

**A UPS:** `check_ups`, UPS name `ups1`, optional warning `50` and critical `20` (battery %).

**Interface status:** `check_ifoperstatus`, Interface index `2`, SNMP community if not `public`.

**Latency of one device:** `check_ping`, warning `100.0,20%`, critical `500.0,60%` (round trip ms, loss %).
Every host already has a host-alive check; use this when you want a separate service and graph for a device.

**A certificate:** `check_ssl_validity`, port `443`, warning `30`, critical `7` (days).

---

## 5. Server checks: run a plugin on the Nagios server

Use this for `check_apt`, `check_uptime`, `check_sensors`, `check_ide_smart`, `check_file_age`, `check_mailq`,
`check_nagios` and `check_flexlm`. They look at the machine Nagios runs on and are shown under the **Nagios
server** host. There is no device to choose.

1. Plugin Manager → the plugin → **Server checks** → **Add check**.
2. Name it (unique among the server's checks), fill in the arguments, **Add check**.
3. Everything else (status chips, Change, Pause, Remove, Nagios validation and rollback) is the same as for
   device checks.

Good to know:

- The check runs as the Nagios user on the Nagios server, so paths and devices are read by that account. Only
  roles with `plugin.custom_check` can add one.
- Pinpoint writes the service on the host named `localhost`. It never edits `localhost.cfg`, and the stock
  `localhost` services keep running as before. If your Nagios server's host object has another name, Nagios
  rejects the change with a clear message and nothing is saved; tell the administrator which name to use.
- The service name starts with `server-` (for example `server-apt-weekly_updates`).

Recipes: **pending updates:** `check_apt`, warning `10`. **A backup that must be fresh:** `check_file_age`,
file `/var/backups/db.sql`, critical `90000` (seconds). **Mail queue:** `check_mailq`, warning `50`,
critical `200`, mail system `postfix`. **Nagios itself:** `check_nagios`, status log
`/usr/local/nagios/var/status.dat`, longest age `5`, process `/usr/local/nagios/bin/nagios`.

---

## 6. What happens to checks over time

| Event | Result |
|---|---|
| A network **Rescan** or the scheduled scan | Checks are untouched |
| Enabling or disabling a port plugin | Checks are untouched |
| **Merging** two devices | The source's checks move to the target. If the target already has one with the same name, the target's stays and the source's is dropped |
| **Retiring** a device | Its services leave Nagios (the device is no longer in the host file). The check stays in the list as Waiting and returns if the device is brought back. Remove it yourself if you no longer want it |
| Server checks | Not tied to any device: merges, retires and rescans never touch them |
| Nagios rejects any change | The database and Nagios are left as they were and a Failed row is added to the plugin history |

Every add, change, pause, resume and remove is written to the plugin's history and the activity log.

---

## 7. Passwords

Plugins that need a password (`check_radius`, `check_mysql_query`, and optionally `check_nt` and
`check_disk_smb`) show a masked box and a note about where the password goes.

How it is handled:

- **Stored encrypted.** The database holds only an encrypted value. The key comes from `PINPOINT_SECRETS_KEY` if
  set, otherwise from `SECRET_KEY`.
- **Never shown again.** The list shows `-p ••••••`; the API never returns it; it is not written to logs or the
  plugin history. An invalid value is reported by argument name only.
- **Changing a check:** leave the box blank to keep the stored password. Type a new one to replace it. An
  optional password has a "Remove the stored …" box; a required one cannot be removed.
- **Passwords are written to the Nagios host file.** Nagios needs the password in the check's command, so it is in
  plain text in that file, in the Nagios web UI's command view, and in the process list while the check runs. Keep
  the host file readable only by the Nagios user and group. Pinpoint logs a warning when a host file that holds a
  password is readable by everyone.

If the key changes:

- Stored passwords can no longer be read. Those checks are **left out of the Nagios host file** (Pinpoint logs a
  warning, never the password), and the list says "A stored password can no longer be read, so this check is not
  running."
- Open **Change** on each affected check, type the password again, and save. The check returns.
- So: choose a fixed key once and keep it with your backups of `pinpoint.env`.

If the server has **no fixed key** (a debug session with no `SECRET_KEY`), Pinpoint refuses to store a password
("Passwords cannot be stored because the server has no fixed SECRET_KEY…"). Checks without passwords still work.

---

## 8. What each plugin takes

Labels are what the form shows; the flag is the plugin option it becomes. Values may not contain these
characters: `'` `"` `` ` `` `!` `$` `;` `\` or a line break. A port must be 1–65535.

#### Device checks

| Plugin | Required | Optional |
|---|---|---|
| `check_by_ssh` | Command to run on the device (`-C`) | SSH port (`-p`); SSH user (`-l`); Identity file (path on the Nagios server) (`-i`) |
| `check_breeze` | Warning (% signal strength) (`-w`); Critical (% signal strength) (`-c`) | SNMP community (`-C`) |
| `check_wave` | Warning (% signal strength) (`-w`); Critical (% signal strength) (`-c`) | none |
| `check_hpjd` | none | SNMP community (`-C`); SNMP port (`-p`) |
| `check_ifstatus` | none | SNMP community (`-C`); SNMP port (`-p`) |
| `check_ifoperstatus` | Interface index (`-k`) | SNMP community (`-C`); SNMP port (`-p`) |
| `check_ups` | UPS name (`-u`) | NUT port (`-p`); Warning battery level (%) (`-w`); Critical battery level (%) (`-c`) |
| `check_ssl_validity` | none | Port (`-p`); Warn if it expires in fewer than N days (`-w`); Critical if it expires in fewer than N days (`-c`) |
| `check_nt` | Variable (CPULOAD, UPTIME, USEDDISKS, ...) (`-v`) | NSClient port (`-p`); Warning threshold (`-w`); Critical threshold (`-c`); Additional parameters (for example a drive letter) (`-l`); NSClient password (`-s`, password) |
| `check_nwstat` | Variable (LOAD1, CONNS, ...) (`-v`) | Port (`-p`); Warning threshold (`-w`); Critical threshold (`-c`) |
| `check_overcr` | Variable (LOAD, DISK, PROCS, UPTIME) (`-v`) | Port (`-p`); Warning threshold (`-w`); Critical threshold (`-c`) |
| `check_real` | URL of the content to check (`-u`) | RTSP port (`-p`); Warning response time (s) (`-w`); Critical response time (s) (`-c`) |
| `check_game` | Game type (qstat name) (`-G`) | Game server port (`-P`) |
| `check_clamd` | none | Port (`-p`); Warning threshold (`-w`); Critical threshold (`-c`) |
| `check_ping` | Warning (round trip ms, loss %) (`-w`); Critical (round trip ms, loss %) (`-c`) | Packets to send (`-p`) |
| `check_icmp` | Warning (round trip ms, loss %) (`-w`); Critical (round trip ms, loss %) (`-c`) | Packets to send (`-n`) |
| `check_fping` | Warning (loss %, round trip ms) (`-w`); Critical (loss %, round trip ms) (`-c`) | Packets to send (`-n`) |
| `check_dig` | none | DNS record to look up (`-l`); Record type (`-T`); Expected address in the answer (`-a`); DNS port (`-p`); Warning response time (s) (`-w`); Critical response time (s) (`-c`) |
| `check_radius` | Username to test with (`-u`); Password to test with (`-p`, password); RADIUS config file (path on the Nagios server) (`-F`) | RADIUS port (`-P`) |
| `check_mysql_query` | SQL query (`-q`); Warning threshold (`-w`); Critical threshold (`-c`) | MySQL user (`-u`); MySQL password (`-p`, password); Database (`-d`); MySQL port (`-P`) |
| `check_disk_smb` | Share name (`-s`) | SMB user (`-u`); Workgroup or domain (`-W`); Warning free-space threshold (%) (`-w`); Critical free-space threshold (%) (`-c`); SMB password (`-p`, password) |

#### Server checks

| Plugin | Required | Optional |
|---|---|---|
| `check_apt` | none | Warn if this many packages need upgrading (`-w`); Only packages matching this regex (`-i`); Skip packages matching this regex (`-e`); Timeout (s) (`-t`) |
| `check_uptime` | none | Warning threshold (`-w`); Critical threshold (`-c`); Unit of the thresholds (`-u`); Timeout (s) (`-t`) |
| `check_sensors` | none | none |
| `check_ide_smart` | Block device (`-d`) | none |
| `check_file_age` | File to check (`-f`) | Warn if older than (s) (`-w`); Critical if older than (s) (`-c`); Warn if smaller than (bytes) (`-W`); Critical if smaller than (bytes) (`-C`) |
| `check_mailq` | Warning queue length (`-w`); Critical queue length (`-c`) | Mail system (`-M`) |
| `check_nagios` | Nagios status log file (`-F`); Longest age of the status log (minutes) (`-e`); Nagios process to look for (`-C`) | none |
| `check_flexlm` | FlexLM license.dat file (`-F`) | none |

Some arguments to know:

- `check_by_ssh`: **Command** runs on the device over SSH. Use a command you trust. The **Identity file** is a path
  on the Nagios server; no private key or password is stored by Pinpoint.
- Thresholds follow each plugin's own syntax (for `check_ping`: `round trip ms,loss %`; for `check_fping`:
  `loss %,round trip ms`).
- `check_dig` needs nothing; with no lookup name it asks for the device's own name.

---

## 9. Troubleshooting

| What you see | Likely cause and fix |
|---|---|
| No **Custom checks** or **Server checks** section | Your role lacks `plugin.custom_check`, or you have not signed in again since it was granted (section 2). The plugin may also be one that takes none: check its note (section 1) |
| The note is the old "This plugin does not check a service that discovery finds on a port…" | The backend is still the old build: restart it |
| "Nagios did not accept the change, so nothing was changed: …" | Nagios rejected the generated config. Read its message: an unknown host `localhost` (server checks) means your server's host object has another name; a missing plugin file means the plugin is not installed in the Nagios plugin folder |
| The check stays **Waiting** for more than ten minutes | Nagios is not running checks (stopped or paused), or the plugin file is missing. Check the Nagios log and run the plugin by hand as the Nagios user |
| **Unknown**, "(Return code of 127 is out of bounds)" or "No such file" | The plugin file is not where Nagios looks (`$USER1$`), or has no interpreter (`check_ncpa.py` needs a `python` command) |
| **Critical** from `check_by_ssh` with a connection or permission error | The Nagios user cannot log in: check the user name, that the key path is readable by the Nagios user, and that the device accepts the key |
| "This device already has a check named …" / "The Nagios server already has a check named …" | Names are unique per device (and among server checks). Choose another |
| "Choose a device." | A device check needs a device; pick one in the list |
| "… checks the Nagios server, so it takes no device." | Server plugins take no device |
| "Variable '…' contains a forbidden character." | Remove `'` `"` `` ` `` `!` `$` `;` `\` or line breaks from that argument |
| "A stored password can no longer be read…" | The server key changed (section 7): type the password again |
| "Passwords cannot be stored because the server has no fixed SECRET_KEY…" | Set `SECRET_KEY` or `PINPOINT_SECRETS_KEY` in the service environment and restart |
| A check disappeared from Nagios after you retired its device | By design (section 6); it returns if the device does |

---

## 10. For administrators: permission and API

- **Permission:** `plugin.custom_check`, separate from `plugin.enable`, `plugin.disable` and `plugin.custom_add`.
  It is required to see the sections and for every route below.
- **Routes** (all under `/api/plugin`): `GET /custom-check-devices?search=`; `GET /<id>/custom-checks`;
  `POST /<id>/custom-checks` (`{device_id, name, variables}`; server plugins take no `device_id`);
  `PUT /<id>/custom-checks/<check_id>` (`{name, variables, clear_secrets?}`); `POST …/pause` and `…/resume`;
  `DELETE …/<check_id>`. The plugin details (`GET /<id>`) carry `custom_checks`: `class`, `supported`, `target`
  (`device` or `server`), `note` and `fields`.
- **Data:** a check is a row of `PLUGIN_CONFIGURATION` with `Origin = CUSTOM`. A server check has no device. Arguments
  are in `Configuration_Data["variables"]`, encrypted passwords in `["secrets"]`, and `["paused"]` is the pause flag.
- **Host file:** device checks are written under their device's host; server checks under "Define Server Checks".
  One `pinpoint_custom_<plugin>` command is defined per plugin in use.
- **What it does not do:** Pinpoint does not edit `localhost.cfg` or `resource.cfg`, does not store SSH keys, and
  does not run a check anywhere but the Nagios server.
