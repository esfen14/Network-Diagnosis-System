# Nagios Plugins 2.4.12 - Complete Output Format Analysis

## Overview
This document catalogs all 57 Nagios plugins with their exact output formats, performance data structures, and status reporting patterns.

---

## 1. check_apt
**Purpose**: Check for available package updates (DebianUbuntu)
**Output Format**: `APT {OK|WARNING|CRITICAL}: {N} packages available for {upgrade_type} ({N} critical updates). {warnings/errors}`
**Performance Data**: `available_upgrades={N};;;0 critical_updates={N};;;0`
**Status Keywords**: APT OK, APT WARNING, APT CRITICAL

---

## 2. check_breeze (Perl) — `plugins-scripts/`
**Purpose**: Check Breezecom wireless equipment signal strength via SNMP
**Output Format**: `Signal Strength at: {N}%`
**Performance Data**: None
**Status Keywords**: OK, WARNING, CRITICAL (based on signal strength thresholds)
**Notes**: SNMP OID `.1.3.6.1.4.1.710.3.2.3.1.3.0`; no perf data emitted

---

## 3. check_by_ssh
**Purpose**: Execute remote commands via SSH
**Output Format**: Varies based on remote command output. In passive mode, writes to Nagios command file.
**Performance Data**: None (passthrough plugin)
**Status Keywords**: Depends on remote command

---

## 4. check_cluster
**Purpose**: Aggregate host/service cluster status
**Output Format**: `CLUSTER {OK|WARNING|CRITICAL}: {Service/Host} cluster: {N} ok, {N} warning, {N} unknown, {N} critical` (services)
**Output Format**: `CLUSTER {OK|WARNING|CRITICAL}: {Host} cluster: {N} up, {N} down, {N} unreachable` (hosts)
**Performance Data**: None
**Status Keywords**: CLUSTER OK, CLUSTER WARNING, CLUSTER CRITICAL

---

## 5. check_dbi
**Purpose**: Database-independent checks via DBI
**Output Format**: `{OK|WARNING|CRITICAL} - connection time: {N}s` (no "DBI" prefix)
**Performance Data**: `conntime={N}s;{warn};{crit};0; server_version={N};{warn};{crit};0;` plus optional `query=...` / `querytime=...`
**Status Keywords**: OK, WARNING, CRITICAL
**Notes**: `plugins/check_dbi.c:295`

---

## 6. check_dhcp (plugins-root)
**Purpose**: Test DHCP server availability
**Output Format**: `{OK|WARNING|CRITICAL|UNKNOWN}: Received {N} DHCPOFFER(s)` (no "DHCP" prefix, no "from N server(s)")
**Performance Data**: None emitted
**Status Keywords**: OK, WARNING, CRITICAL, UNKNOWN
**Notes**: Lives in `plugins-root/check_dhcp.c`, not `plugins/`

---

## 7. check_dig
**Purpose**: DNS lookup using dig command
**Output Format**: `DNS {OK|WARNING|CRITICAL} - {N}.{N} seconds response time ({msg})` ("seconds", not "second"; trailing clause is a diagnostic message, not `{expected} = {actual}`)
**Performance Data**: `time={N}s;{warn};{crit};0;0`
**Status Keywords**: DNS OK, DNS WARNING, DNS CRITICAL
**Notes**: `plugins/check_dig.c:197`

---

## 8. check_disk
**Purpose**: Check disk space and inode usage
**Output Format**: `DISK {OK|WARNING|CRITICAL} - free space: /{mount_point} {N} {unit} ({N}% inode={N}%)` (no "free" word inside the parens; doc's prior nesting was wrong)
**Performance Data**: `/{mount_point}={used_bytes};{warn};{crit};0;{total}`
**Performance Data**: `/{mount_point}_inode_percent={used_pct}%;{warn};{crit};0;100`
**Performance Data**: `/{mount_point}_inode_used={used_inodes};;;0;{total}`
**Performance Data**: `/{mount_point}_inode_free={free_inodes};;;0;{total}`
**Status Keywords**: DISK OK, DISK WARNING, DISK CRITICAL

---

## 9. check_disk_smb (Perl) — `plugins-scripts/`
**Purpose**: Check disk space on SMB/CIFS shares via smbclient
**Output Format**: `Disk ok - {N}{unit} ({N%} free) on {mount_path}`
**Output Format (warning)**: `WARNING: Only {N}{unit} ({N%} free) on {mount_path}`
**Output Format (critical)**: `CRITICAL: Only {N}{unit} ({N%} free) on {mount_path}`
**Output Format (access denied)**: `Access Denied`
**Output Format (invalid share)**: `Invalid share name \\{host}\{share}` (doc previously omitted "name")
**Performance Data**: `'share_name'={used_bytes}B;{warn_bytes};{crit_bytes};0;{total_bytes}`
**Status Keywords**: Disk ok, WARNING, CRITICAL

---

## 10. check_dns
**Purpose**: Check DNS server response
**Output Format**: `DNS {OK|WARNING|CRITICAL}: {N}.{N} second response time. {domain} returns {address}`
**Performance Data**: `time={N}s;{warn};{crit};0;0`
**Status Keywords**: DNS OK, DNS WARNING, DNS CRITICAL

---

## 11. check_dummy
**Purpose**: Return a specified state with message
**Output Format**: `{OK|WARNING|CRITICAL|UNKNOWN}: {message}`
**Performance Data**: None
**Status Keywords**: OK, WARNING, CRITICAL, UNKNOWN

---

## 12. check_flexlm (Perl) — `plugins-scripts/`
**Purpose**: Check FlexLM license server status via lmstat
**Output Format (all up)**: `License Servers running:{server1},{server2},...`
**Output Format (some down)**: `License Servers running:{server1},...\nLicense servers NOT running:{server2},...`
**Performance Data**: `flexlm::up:{N};down:{N}` — uses `:` as the label/value separator, not `=` (non-standard perfdata; parsers must special-case this)
**Status Keywords**: OK, WARNING, CRITICAL (no explicit keyword prefix — uses exit code)
**Notes**: OK if all servers up, WARNING if 1-2 of 3 down, CRITICAL if all down. `plugins-scripts/check_flexlm.pl:205`

---

## 13. check_fping
**Purpose**: Fast ping using fping
**Output Format**: `FPING {OK|WARNING|CRITICAL} - {host} (loss={N}%, rta={N} ms)`
**Output Format**: `FPING {OK|WARNING|CRITICAL} - {host} (loss={N}%)` (when no min/avg/max)
**Performance Data**: `loss={N}%;{warn};{crit};0;100 rta={N}s;{warn};{crit};0;0` (rta unit is seconds, not ms as previously stated)
**Status Keywords**: FPING OK, FPING WARNING, FPING CRITICAL
**Notes**: `plugins/check_fping.c:230`

---

## 14. check_game
**Purpose**: Check game server status via qstat
**Output Format**: `OK: {players}/{max} {type} ({map}), Ping: {N} ms` (no "GAME" prefix, no host:port; failures are `CRITICAL: ...` variants; the plugin never emits WARNING)
**Performance Data**: `players={N};;;0;{max} ping={N}ms` (no `map=` field — map only appears in the text)
**Status Keywords**: OK, CRITICAL (no WARNING state exists in the code)
**Notes**: `plugins/check_game.c:111-149`

---

## 15. check_hpjd
**Purpose**: Check HP JetDirect printer status
**Output Format**: `Printer ok - ({status_message})` for OK; for problems just the raw error text (optionally `{errmsg} ({display_message})`) with no state word or "HPJD" prefix at all
**Performance Data**: None (status-only plugin)
**Status Keywords**: (no literal "HPJD" string appears anywhere in the source)
**Notes**: `plugins/check_hpjd.c:298-310`

---

## 16. check_http
**Purpose**: Check HTTP/HTTPS web server
**Output Format**: `HTTP {OK|WARNING|CRITICAL} - {N} bytes in {N}.{N} second response time {url}` (no "string(s)"/"of body" wording)
**Performance Data**: `time={N}s;{warn};{crit};0;0 size={N}B;{warn};{crit};0;0`
**Performance Data**: `time_connect={N}s time_first_byte={N}s time_transfer={N}s`
**Status Keywords**: HTTP OK, HTTP WARNING, HTTP CRITICAL
**Notes**: `plugins/check_http.c:1511,1525`

---

## 17. check_ide_smart
**Purpose**: Check IDE/S.M.A.R.T. disk health
**Output Format**: `OK - Operational (N/N tests passed)` / `WARNING - N Harddrive Advisor(s) Detected. N/N tests failed.` / `CRITICAL - N Harddrive PreFailure(s) Detected! N/N tests failed.` (no "SMART" prefix, no device name)
**Performance Data**: None
**Status Keywords**: OK, WARNING, CRITICAL
**Notes**: `plugins/check_ide_smart.c:422-438`

---

## 18. check_icmp (plugins-root)
**Purpose**: ICMP ping with high precision
**Output Format**: `{OK|WARNING|CRITICAL} - {host}: rta {N}ms, lost {N}%` (no "ICMP" prefix, no "Packet loss ="/"RTA =" wording)
**Performance Data**: `rta={N}ms;{warn};{crit};0; pl={N}%;{warn};{crit};0;100`
**Status Keywords**: OK, WARNING, CRITICAL
**Notes**: `plugins-root/check_icmp.c:1500,1533`

---

## 19. check_ifoperstatus (Perl) — `plugins-scripts/`
**Purpose**: Check individual SNMP interface operational status
**Output Format (up)**: `OK: Interface {interface_name} (index {N}) is up.` (every outcome gets a state prefix; doc's prior "up" format used an unused leftover template)
**Output Format (down)**: `CRITICAL: Interface {interface_name} (index {N}) is down.`
**Output Format (dormant)**: `Interface {interface_name} (index {N}) is dormant.`
**Output Format (admin down)**: `Interface {interface_name} (index {N}) is administratively down.`
**Output Format (notPresent)**: `CRITICAL: Interface {interface_name} (index {N}) notPresent`
**Output Format (lowerLayerDown)**: `CRITICAL: Interface {interface_name} (index {N}) down due to lower layer being down.`
**Output Format (testing)**: `CRITICAL: Interface {interface_name} (index {N}) down (testing/unknown).`
**Output Format (name mismatch)**: `UNKNOWN: Interface name ({expected}) doesn't match snmp value ({actual})`
**Performance Data**: None
**Status Keywords**: OK, WARNING, CRITICAL, UNKNOWN

---

## 20. check_ifstatus (Perl) — `plugins-scripts/`
**Purpose**: Check bulk SNMP interface status (up/down counts)
**Output Format (OK)**: `OK: host '{host}', interfaces up: {N}, down: {N}, dormant: {N}, excluded: {N}, unused: {N}`
**Output Format (CRITICAL)**: `CRITICAL: host '{host}', interfaces up: {N}, down: {N}, dormant: {N}, excluded: {N}, unused: {N}<BR>\n{down_interface_details}`
**Performance Data**: `up={N} down={N} dormant={N} excluded={N} unused={N}`
**Status Keywords**: OK, CRITICAL

---

## 21. check_ircd (Perl) — `plugins-scripts/`
**Purpose**: Check IRC daemon user count
**Output Format (OK)**: `IRCD ok - Current Local Users: {N}`
**Output Format (WARNING)**: `Warning Number Of Clients Connected : {N} (Limit = {warn_limit})`
**Output Format (CRITICAL)**: `Critical Number Of Clients Connected : {N} (Limit = {crit_limit})`
**Output Format (error)**: `Server {host} has less than 0 users! Something is Really WRONG!`
**Output Format (timeout)**: `Something is Taking a Long Time, Increase Your TIMEOUT (Currently Set At {N} Seconds)`
**Performance Data**: None
**Status Keywords**: IRCD ok, Warning, Critical

---

## 22. check_ldap / check_ldaps
**Purpose**: Check LDAP server connection and search
**Output Format**: `LDAP {OK|WARNING|CRITICAL} - found {N} entries in {N}.{N} seconds`
**Output Format**: `LDAP {OK|WARNING|CRITICAL} - {N}.{N} seconds response time`
**Performance Data**: `time={N}s;{warn};{crit};0;0 entries={N};{warn};{crit};0;0`
**Status Keywords**: LDAP OK, LDAP WARNING, LDAP CRITICAL

---

## 23. check_load
**Purpose**: Check system load averages
**Output Format**: `{OK|WARNING|CRITICAL} - load average: {N.NN}, {N.NN}, {N.NN}` (no "Load" word; dash, not colon)
**Performance Data**: `load1={N};{warn};{crit};0; load5={N};{warn};{crit};0; load15={N};{warn};{crit};0;` (no max field)
**Status Keywords**: OK, WARNING, CRITICAL
**Notes**: `plugins/check_load.c:206`

---

## 24. check_log (Bash) — `plugins-scripts/`
**Purpose**: Scan log files for pattern matches (stateful — tracks previous runs)
**Output Format (first run)**: `Log check data initialized...`
**Output Format (no matches)**: `Log check ok - 0 pattern matches found|match={N};;;0`
**Output Format (matches found)**: `({N}) {matching_line_content}|match={N};;;0`
**Performance Data**: `match={N};;;0` (doc previously said "None" — this is wrong, perfdata is emitted)
**Status Keywords**: OK, CRITICAL
**Notes**: Requires `-F logfile -O oldlog -q query`; uses state file to track progress. `plugins-scripts/check_log.sh:229,264,267`

---

## 25. check_mailq (Perl) — `plugins-scripts/`
**Purpose**: Check mail queue length for multiple MTA backends
**Supported MTAs**: sendmail, qmail, postfix, exim, nullmailer, opensmtpd
**Output Format (sendmail, OK)**: `OK: sendmail mailq is empty`
**Output Format (sendmail, OK with threshold)**: `OK: sendmail mailq ({N}) is below threshold ({warn}/{crit})`
**Output Format (sendmail, WARNING)**: `WARNING: sendmail mailq is {N} (threshold w = {warn})`
**Output Format (sendmail, CRITICAL)**: `CRITICAL: sendmail mailq is {N} (threshold c = {crit})`
**Output Format (domain-specific WARNING)**: `WARNING: {N} messages in queue FROM {domain} (threshold W = {warn})`
**Output Format (domain-specific CRITICAL)**: `CRITICAL: {N} messages in queue TO {domain} (threshold C = {crit})`
**Output Format (qmail, OK)**: `OK: qmail-qstat reports queue is empty`
**Output Format (postfix, OK)**: `OK: postfix mailq reports queue is empty`
**Output Format (exim, OK)**: `OK: exim mailq ({N}) is below threshold ({warn}/{crit})`
**Performance Data**: `unsent={N};{warn};{crit};0`
**Status Keywords**: OK, WARNING, CRITICAL

---

## 26. check_mrtg
**Purpose**: Check MRTG log file values
**Output Format**: `{OK|WARNING|CRITICAL} - {Avg|Max}. {label} = {N} {units}`
**Performance Data**: `{label}={N};{warn};{crit};0;0`
**Status Keywords**: OK, WARNING, CRITICAL

---

## 27. check_mrtgtraf
**Purpose**: Check MRTG traffic log files
**Output Format**: `Traffic {OK|WARNING|CRITICAL} - {Avg|Max}. In = {N.N} {unit}/s, {Avg|Max}. Out = {N.N} {unit}/s`
**Performance Data**: `in={N}{unit};{warn};{crit};0;0 out={N}{unit};{warn};{crit};0;0`
**Performance Data**: `in_pct={N}%;0;0;0;100 out_pct={N}%;0;0;0;100`
**Status Keywords**: Traffic OK, Traffic WARNING, Traffic CRITICAL

---

## 28. check_mysql
**Purpose**: Check MySQL server connection and status
**Output Format**: The raw `mysql_stat()` string, e.g. `Uptime: {N} Threads: {N} Questions: {N} ...`. No "MySQL" prefix and no "second response time" text at all (the doc's prior claim was wrong for the normal path). Exception: the auth-ignored branch prints `MySQL OK - Version: {version} (protocol {N})`.
**Output Format (slave check)**: `SLOW_SLAVE {WARNING|CRITICAL}: Slave IO: {Yes/No} Slave SQL: {Yes/No} Seconds Behind Master: {N}|{perfdata}`
**Performance Data**: `Connections={N}c Qcache_hits={N}c Qcache_inserts={N}c Qcache_lowmem_prunes={N}c Qcache_not_cached={N}c Queries={N}c Questions={N}c
Table_locks_waited={N}c Uptime={N}s`
**Performance Data**: `Open_files={N} Open_tables={N} Qcache_free_memory={N} Qcache_queries_in_cache={N} Threads_connected={N} Threads_running={N}`
**Performance Data (slave)**: `seconds behind master={N}s;{warn};{crit};0;0`
**Status Keywords**: SLOW_SLAVE WARNING/CRITICAL (slave path only); normal path has no keyword prefix
**Notes**: `plugins/check_mysql.c:165,325`

---

## 29. check_mysql_query
**Purpose**: Run arbitrary SQL and check result
**Output Format**: `QUERY {OK|WARNING|CRITICAL}: '{sql}' returned {N}`
**Performance Data**: `result={N};{warn};{crit};0;0`
**Status Keywords**: QUERY OK, QUERY WARNING, QUERY CRITICAL

---

## 30. check_ncpa (Python) — `plugins-scripts/`
**Purpose**: Check metrics via NCPA (Nagios Plugin Agent) API
**Output Format**: Varies based on remote metric — passes through NCPA agent output
**Output Format (error)**: `UNKNOWN: An error occured connecting to API. (HTTP error: '{code}')`
**Output Format (timeout)**: `UNKNOWN: An error occured connecting to API. (Connection error: '{message}')`
**Output Format (no perf data, with flag)**: `{stdout} | 'status'={returncode};1;2;;`
**Performance Data**: Depends on remote metric; if none, prints `'status'={returncode};1;2;;` when `-p` flag used
**Status Keywords**: Varies — output is passthrough from NCPA agent
**Notes**: Version 1.2.4; connects to `https://{host}:{port}/api/{metric}`; supports delta checks, token auth, custom plugins

---

## 31. check_nagios
**Purpose**: Check Nagios process and status log freshness
**Output Format**: `NAGIOS {OK|WARNING}: {N} process, status log updated {N} seconds ago`
**Performance Data**: None
**Status Keywords**: NAGIOS OK, NAGIOS WARNING

---

## 32. check_nt
**Purpose**: Check Windows NT/2000/XP/2003 server via NSClient
**Output Format (client version)**: `{version_string}`
**Output Format (CPU load)**: `CPU Load: {N}% ({N} min average), {N}% ({N} min average), {N}% ({N} min average)`
**Output Format (uptime)**: `System Uptime - {N} day(s) {N} hour(s) {N} minute(s) |uptime={N}`
**Output Format (disk space)**: `{drive}: - total: {N} Gb - used: {N} Gb ({N}%) - free {N} Gb ({N}%)`
**Output Format (service/process state)**: `{service_name}: {state_message}`
**Output Format (memory)**: `Memory usage: Total: {N} MB, Used: {N} MB ({N}%), Free: {N} MB ({N}%)` (lowercase "usage:", no dash)
**Output Format (disk)**: disk line includes a literal `\` after the drive letter (e.g. `C:\ - total: ...`), which the doc previously omitted
**Performance Data (CPU)**: `'N min avg Load'={N}%;{warn};{crit};0;100`
**Performance Data (disk)**: `'drive:\\ Used Space'={N}Gb;{warn};{crit};0;{total}`
**Performance Data (memory)**: `'Memory usage'={N}MB;{warn};{crit};0;{total}` (label is `'Memory usage'`, not `'Memory Usage'`)
**Status Keywords**: Depends on check type

---

## 33. check_ntp (DEPRECATED)
**Purpose**: Deprecated — use check_ntp_time or check_ntp_peer instead
**Output Format**: `NTP {OK|WARNING|CRITICAL}: Offset {N} secs` (space, not `=`)
**Performance Data**: `offset={N}s;{warn};{crit}` (no min/max fields)
**Status Keywords**: NTP OK, NTP WARNING, NTP CRITICAL, NTP UNKNOWN (doc previously omitted UNKNOWN)
**Notes**: `plugins/check_ntp.c:905`

---

## 34. check_ntp (Perl) — `plugins-scripts/`
**Purpose**: Check NTP time offset and jitter via ntpdate + ntpq
**Output Format (OK)**: `NTP OK: Offset {offset} secs, jitter {jitter} msec, peer is stratum {N}`
**Output Format (WARNING)**: `NTP WARNING: Offset {offset} sec > +/- {warn} sec, jitter {jitter} msec`
**Output Format (CRITICAL)**: `NTP CRITICAL: Offset {offset} sec > +/- {crit} sec, jitter {jitter} msec`
**Output Format (jitter WARNING)**: `NTP WARNING: Jitter {jitter} msec> +/- {jwarn} msec, offset {offset} sec`
**Output Format (jitter CRITICAL)**: `NTP CRITICAL: Jitter {jitter} msec> +/- {jcrit} msec, offset {offset} sec`
**Output Format (server error)**: `NTP CRITICAL: Server Error and offset {offset} sec > +/- {crit} sec`
**Output Format (desynchronized)**: `NTP WARNING: Desynchronized peer server found`
**Output Format (no peer)**: `NTP CRITICAL: No suitable peer server found - {msg}`
**Performance Data**: `offset={offset}s;{warn};{crit};; jitter={jitter}s;{jwarn};{jcrit};; peer_stratum={N}` (note: jitter value is divided by 1000 and its perfdata token has no unit/thresholds)
**Status Keywords**: NTP OK, NTP WARNING, NTP CRITICAL
**Notes**: "no peer" message is a fixed literal, not a variable `{msg}` as previously implied. `plugins-scripts/check_ntp.pl:426-433`

---

## 35. check_ntp_peer
**Purpose**: Check NTP server peer health
**Output Format**: `NTP {OK|WARNING|CRITICAL}: {Server not synchronized|Server has the LI_ALARM bit set|Offset={N} secs}, jitter={N}, stratum={N}, truechimers={N}`
**Notes**: `plugins/check_ntp_peer.c:530-559`
**Performance Data**: `offset={N}s;{warn};{crit}; jitter={N};{warn};{crit};0 stratum={N};{warn};{crit};0;16 truechimers={N};{warn};{crit};0` (offset has no min/max at all; jitter/truechimers only get a min, no max)
**Status Keywords**: NTP OK, NTP WARNING, NTP CRITICAL

---

## 36. check_ntp_time
**Purpose**: Check NTP time offset
**Output Format**: `NTP {OK|WARNING|CRITICAL}: Offset {N} secs, stratum best:{N} worst:{N}` (space, not `=`)
**Performance Data**: `offset={N}s;{warn};{crit} stratum_best={N} stratum_worst={N} num_warn_stratum={N} num_crit_stratum={N}` (offset has no min/max fields)
**Status Keywords**: NTP OK, NTP WARNING, NTP CRITICAL
**Notes**: `plugins/check_ntp_time.c:711`

---

## 37. check_nwstat
**Purpose**: Check Novell NetWare server statistics
**Output Format**: Varies based on check type (LOAD, CONNS, VPF, etc.)
**Performance Data**: Varies based on check type
**Status Keywords**: Depends on check type

---

## 38. check_overcr
**Purpose**: Check Over-CR collector daemon
**Output Format (load)**: `Load {OK|WARNING|CRITICAL} - {N}-min load average = {N.NN}`
**Output Format (disk)**: `CRITICAL - Disk '{name}' non-existent or not mounted`
**Output Format (processes)**: `Process {OK|WARNING|CRITICAL} - {N} instance(s) of {name} running` (no "PROCS" word)
**Output Format (uptime)**: `Uptime {OK|WARNING|CRITICAL} - Up {N} days {N} hours {N} minutes` (dash, "Up", no commas)
**Performance Data**: Varies based on check type
**Status Keywords**: Load OK, Process OK, Uptime OK, etc.

---

## 39. check_oracle (Bash) — `plugins-scripts/`
**Purpose**: Check Oracle database status via multiple methods
**Output Format**: None of the `ORACLE TNS:`/`ORACLE DB:`/`ORACLE LOGIN:`/`ORACLE CACHE:`/`ORACLE TABLESPACE:`/`ORACLE NAMES:` prefixes shown previously exist anywhere in the script. Every check type has its own distinct wording instead, e.g.:
- reply-time check: `OK - reply time ... from {host}`
- process check: `{host} OK - N PMON process(es) running`
- tablespace check: `{host} : {tablespace} OK - N% used [...]`
**Performance Data**: Varies by check type (the doc's implied absence of perfdata was also wrong — several checks do emit it)
**Status Keywords**: OK, WARNING, CRITICAL (no "ORACLE ..." keyword prefixes)
**Notes**: `plugins-scripts/check_oracle.sh`

---

## 40. check_pgsql
**Purpose**: Check PostgreSQL database connection
**Output Format**: `{OK|WARNING|CRITICAL} - database {dbname} ({N} sec.) | time={N}s;{warn};{crit};0`
**Performance Data**: `time={N}s;{warn};{crit};0` (no max field — `maxp=FALSE` in source)
**Status Keywords**: OK, WARNING, CRITICAL
**Notes**: `plugins/check_pgsql.c:253-254`

---

## 41. check_ping
**Purpose**: Ping host and measure response time
**Output Format**: `PING {OK|WARNING|CRITICAL} - Packet loss = {N}%, RTA = {N.NN} ms` (host is not embedded up front; it's only appended at the very end, and only when `-A`/resolution display is used)
**Performance Data**: `rta={N}ms;{warn};{crit};0; pl={N}%;{warn};{crit};0;100` (rta has no max field)
**Status Keywords**: PING OK, PING WARNING, PING CRITICAL
**Notes**: `plugins/check_ping.c:160-182`

---

## 42. check_procs
**Purpose**: Check process count and resources
**Output Format**: `PROCS {OK|WARNING|CRITICAL}: {N} process{with filters}`
**Performance Data (plain)**: `procs={N};;;0;`
**Performance Data (vsz)**: `procs={N};;;0; procs_warn={N};;;0; procs_crit={N};;;0; procvsz={N};`
**Performance Data (rss)**: `procs={N};;;0; procs_warn={N};;;0; procs_crit={N};;;0; procrss={N};`
**Performance Data (cpu)**: `procs={N};;;0; procs_warn={N};;;0; procs_crit={N};;;0; procpcpu={N};`
**Performance Data (elapsed)**: `procs={N};;;0; procs_warn={N};;;0; procs_crit={N};;;0; procseconds={N};`
**Status Keywords**: PROCS OK, PROCS WARNING, PROCS CRITICAL
**Notes**: The doc previously showed real `{warn}`/`{crit}` values and min/max on every field — actually `procs`/`procs_warn`/`procs_crit` always have *empty* warn/crit fields (hardcoded `;;;0;`) and the type-specific metric (`procvsz`/`procrss`/`procpcpu`/`procseconds`) has no warn/crit/min/max at all, just a bare value. `plugins/check_procs.c:438-446`

---

## 43. check_radius
**Purpose**: Test RADIUS server authentication
**Output Format**: `{Auth OK|Auth Failed|Auth Error|Timeout|Bad Response}` — no "RADIUS" prefix or state keyword at all
**Performance Data**: None
**Status Keywords**: (none literally printed — state is conveyed only via exit code)
**Notes**: `plugins/check_radius.c:230-241`

---

## 44. check_real
**Purpose**: Check REAL/RTSP streaming server
**Output Format (OK)**: `REAL {state} - {N} second response time` (dash, not colon; integer seconds, not decimal)
**Output Format (WARNING/CRITICAL)**: the raw RTSP status line is printed verbatim, with no "REAL WARNING/CRITICAL:" prefix at all
**Performance Data**: None emitted
**Status Keywords**: REAL (OK path only)
**Notes**: `plugins/check_real.c:249-254`

---

## 45. check_rpc (Perl) — `plugins-scripts/`
**Purpose**: Check RPC program availability via rpcinfo
**Output Format (OK)**: `OK: RPC program {name} version {N} {tcp/udp} running`
**Output Format (CRITICAL)**: `CRITICAL: RPC program {name} version {N} {tcp/udp} is not running`
**Output Format (mixed)**: `CRITICAL: RPC program {name} version {N} {tcp/udp} is not running, version {M} {tcp/udp} is running`
**Performance Data**: None
**Status Keywords**: OK, CRITICAL, UNKNOWN (doc previously omitted UNKNOWN — an alarm timeout returns "ERROR: No response from RPC server (alarm)" as UNKNOWN)

---

## 46. check_sensors (Bash) — `plugins-scripts/`
**Purpose**: Check hardware sensor status via lm_sensors
**Output Format (OK)**: `SENSORS OK`
**Output Format (WARNING)**: `WARNING - sensors returned state {N}`
**Output Format (CRITICAL)**: `SENSOR CRITICAL - Sensor alarm detected!`
**Output Format (UNKNOWN - fault)**: `SENSOR UNKNOWN - Sensor reported fault`
**Output Format (UNKNOWN - no sensors)**: `SENSORS UNKNOWN - command not found (did you install lmsensors?)`
**Performance Data**: None (verbose mode only shows raw sensor data)
**Status Keywords**: SENSORS OK, SENSOR CRITICAL, SENSOR UNKNOWN

---

## 47. check_smtp
**Purpose**: Check SMTP server connection
**Output Format**: `SMTP {OK|WARNING|CRITICAL} - {N}.{N} sec. response time | time={N}s;{warn};{crit};0;`
**Performance Data**: `time={N}s;{warn};{crit};0;` (no max field)
**Status Keywords**: SMTP OK, SMTP WARNING, SMTP CRITICAL, SMTP UNKNOWN
**Notes**: `plugins/check_smtp.c:466-474`

---

## 48. check_snmp
**Purpose**: Check remote machines via SNMP
**Output Format**: `SNMP {OK|WARNING|CRITICAL} - {label}={value} {label}={value} ...`
**Performance Data**: `{label}={value};{warn};{crit}` (for each OID; no min/max — source explicitly never adds them)
**Status Keywords**: SNMP OK, SNMP WARNING, SNMP CRITICAL
**Notes**: `plugins/check_snmp.c:689-697`

---

## 49. check_ssl_validity (Perl) — `plugins-scripts/`
**Purpose**: Check SSL certificate validity, expiration, and revocation
**Output Format (OK)**: `{$oktxt — host/CN match message}, still valid for {N.N} days. Serial {serial} not found on any Certificate Revokation Lists.` (no literal "OK" word; doc's prior text omitted the `$oktxt` prefix)
**Output Format (expired)**: `CRITICAL: Certificate expired {N.N} days ago`
**Output Format (expiring critical)**: `CRITICAL: Certificate expiring in {N.N} days, but it is expired/expiring in only {N.N} days, critical limit is {crit}` (doc's prior wording was simplified/incorrect)
**Output Format (expiring warning)**: `WARNING: Certificate expiring in {N.N} days, but it is expired/expiring in only {N.N} days, warning limit is {warn}`
**Output Format (hostname mismatch)**: `CRITICAL: Host {vhost} not found in certificate`
**Output Format (CRL revoked)**: `CRITICAL: Found certificate for {vhost} on CRL {crldp} revoked at date {date}` (this is from the CRL check path, not OCSP as previously labeled)
**Output Format (OCSP good)**: `{$oktxt}; OCSP responder ({uri}) says certificate is good` (has an extra `$oktxt` prefix doc previously omitted)
**Performance Data**: None
**Status Keywords**: OK, WARNING, CRITICAL
**Notes**: `plugins-scripts/check_ssl_validity.pl`

---

## 50. check_ssh
**Purpose**: Check SSH server connection
**Output Format**: `SSH OK - {server_banner} (protocol {proto}) | time={N}s;{warn};{crit};0;0` (no "second response time" text — the server version banner and protocol are shown instead; elapsed time only appears in perfdata)
**Performance Data**: `time={N}s;{warn};{crit};0;0`
**Status Keywords**: SSH OK, SSH CRITICAL, SSH UNKNOWN (the plugin never returns WARNING)
**Notes**: `plugins/check_ssh.c:268-274`

---

## 51. check_swap
**Purpose**: Check swap space usage
**Output Format**: `SWAP {OK|WARNING|CRITICAL} - {N}% free ({N} MB out of {N} MB)` (dash, not colon; reports percent **free**, not "% used" — doc's prior metric was inverted; shows MB totals, not the `[N (N%)]` bracket form)
**Performance Data**: `swap={N}MB;{warn};{crit};0;{total}` (no `MB` suffix on the total)
**Status Keywords**: SWAP OK, SWAP WARNING, SWAP CRITICAL
**Notes**: `plugins/check_swap.c:364-372`

---

## 52. check_tcp
**Purpose**: Check TCP port connectivity
**Output Format**: `TCP {OK|WARNING|CRITICAL} - {N}.{N} second response time on {host} port {port} [{status}] | time={N}s;{warn};{crit};0;{timeout}` (doc previously omitted the "on {host} port {port}" clause)
**Performance Data**: `time={N}s;{warn};{crit};0;{timeout}` (max is the configured timeout, not a literal `0`)
**Status Keywords**: TCP OK, TCP WARNING, TCP CRITICAL
**Notes**: `plugins/check_tcp.c:348-389`

---

## 53. check_time
**Purpose**: Check time difference with remote host
**Output Format**: `TIME {OK|WARNING|CRITICAL} - {N} second time difference | time={N}s;{warn};{crit};0; offset={N}s;{warn};{crit};0;` (there's also a separate early-exit path: `TIME {state} - {N} second response time|{perf}` when the connection itself is slow)
**Performance Data**: `time={N}s;{warn};{crit};0; offset={N}s;{warn};{crit};0;` (min=0, but **no max field** on either metric)
**Status Keywords**: TIME OK, TIME WARNING, TIME CRITICAL, TIME UNKNOWN
**Notes**: `plugins/check_time.c:151-179`

---

## 54. check_ups
**Purpose**: Check UPS status via NUT
**Output Format**: `UPS {OK|WARNING|CRITICAL} - Status={status} Utility={N}V Batt={N}% Load={N}% Temp={N}{unit} Left={N}min`
**Performance Data**: `voltage={N}V;{warn};{crit};0; battery={N}%;{warn};{crit};0;100 load={N}%;{warn};{crit};0;100 temp={N};{warn};{crit};0; left={N};{warn};{crit};0;` (only `battery`/`load` have a max of 100 — `voltage`/`temp`/`left` have no max field)
**Status Keywords**: UPS OK, UPS WARNING, UPS CRITICAL
**Notes**: `plugins/check_ups.c:217-350`

---

## 55. check_uptime
**Purpose**: Check system uptime
**Output Format**: `Uptime {OK|WARNING|CRITICAL}: {N} day(s) {N} hour(s) {N} minute(s) | uptime={N};{warn};{crit};0;0`
**Performance Data**: `uptime={N};{warn};{crit};0;0`
**Status Keywords**: Uptime OK, Uptime WARNING, Uptime CRITICAL

---

## 56. check_users
**Purpose**: Check number of logged-in users
**Output Format**: `USERS {OK|WARNING|CRITICAL} - {N} users currently logged in | users={N};{warn};{crit};0;`
**Performance Data**: `users={N};{warn};{crit};0;` (no max field)
**Status Keywords**: USERS OK, USERS WARNING, USERS CRITICAL
**Notes**: `plugins/check_users.c:166-169`

---

## 57. check_wave (Perl) — `plugins-scripts/`
**Purpose**: Check wireless signal strength via SNMP (WaveLAN/Intersil)
**Output Format**: `Signal Strength at: {N}%,  SNR at {N}%`
**Performance Data**: None
**Status Keywords**: OK, WARNING, CRITICAL (based on signal strength thresholds)
**Notes**: SNMP OID `.1.3.6.1.4.1.74.2.21.1.2.1.8.1` (low), `.9.1` (medium), `.10.1` (high)

---

# Performance Data Format Summary

Most plugins follow the standard Nagios performance data convention:
```
label=value[unit];[warn];[crit];[min];[max]
```
with `warn`/`crit`/`min`/`max` frequently left empty rather than populated — many
plugins (check_load, check_pgsql, check_procs, check_ping, check_smtp, check_snmp,
check_time, check_ups, check_users, and others) omit the `min` and/or `max` field
entirely rather than emitting a literal `0`. Don't assume a fixed 5-field shape when
parsing; treat trailing fields as optional.

**check_flexlm is a documented exception to the whole convention**: it uses `:` as
the label/value separator instead of `=`, with no thresholds at all —
`flexlm::up:{N};down:{N}`. A parser built only around `label=value;...;...` will
silently drop this plugin's performance data unless it special-cases the `:` form.

Multiple data points are normally separated by spaces:
```
label1=value1;warn1;crit1;min1;max1 label2=value2;warn2;crit2;min2;max2
```

## Common Performance Metrics by Category

### Network/Connectivity
- `time` - Response time in seconds
- `rta` - Round-trip time in milliseconds
- `pl` / `loss` - Packet loss percentage
- `jitter` - Network jitter in milliseconds
