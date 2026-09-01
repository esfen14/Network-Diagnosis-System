# Nagios Plugins 2.4.12 - Complete Output Format Analysis

## Overview
This document catalogs all 57 Nagios plugins with their exact output formats, performance data structures, status reporting patterns, and required/optional arguments.

---

## 1. check_apt
**Purpose**: Check for available package updates (Debian/Ubuntu)
**Output Format**: `APT {OK|WARNING|CRITICAL}: {N} packages available for {upgrade_type} ({N} critical updates). {warnings/errors}`
**Performance Data**: `available_upgrades={N};;;0 critical_updates={N};;;0`
**Status Keywords**: APT OK, APT WARNING, APT CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-t` | `--timeout=INTEGER` | No | Seconds before plugin times out (default: 10) |
| `-u` | `--update[=opts]` | No | Run `apt-get update` first; optional apt-get options |
| `-U` | `--upgrade[=opts]` | No | Check for upgrades (default behavior) |
| `-n` | `--no-upgrade` | No | Do not check for upgrades (security only) |
| `-d` | `--dist-upgrade[=opts]` | No | Use `dist-upgrade` instead of `upgrade` |
| `-i` | `--include=PATTERN` | No | Include only packages matching this regex |
| `-e` | `--exclude=PATTERN` | No | Exclude packages matching this regex |
| `-c` | `--critical=PATTERN` | No | Return CRITICAL if a matching package is pending |
| `-o` | `--only-critical` | No | Only warn about critical (security) updates |
| `-w` | `--packages-warning=INTEGER` | No | Return WARNING if N or more packages need upgrading |
| N/A | `--input-file=FILE` | No | Read package list from FILE instead of running apt |
| `-v` | `--verbose` | No | Verbose output |

---

## 2. check_breeze (Perl) — `plugins-scripts/`
**Purpose**: Check Breezecom wireless equipment signal strength via SNMP
**Output Format**: `Signal Strength at: {N}%`
**Performance Data**: None
**Status Keywords**: OK, WARNING, CRITICAL (based on signal strength thresholds)
**Notes**: SNMP OID `.1.3.6.1.4.1.710.3.2.3.1.3.0`; no perf data emitted

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname or IP address of the device |
| `-w` | `--warning=INTEGER` | **Yes** | Warning threshold (% signal strength) |
| `-c` | `--critical=INTEGER` | **Yes** | Critical threshold (% signal strength) |
| `-C` | `--community=STRING` | No | SNMP community string (default: public) |

---

## 3. check_by_ssh
**Purpose**: Execute remote commands via SSH
**Output Format**: Varies based on remote command output. In passive mode, writes to Nagios command file.
**Performance Data**: None (passthrough plugin)
**Status Keywords**: Depends on remote command

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname or IP address |
| `-C` | `--command=STRING` | **Yes** | Command to run on remote host |
| `-p` | `--port=INTEGER` | No | SSH port (default: 22) |
| `-l` | `--logname=STRING` | No | SSH login name |
| `-u` | `--user=STRING` | No | SSH user (alias for -l) |
| `-i` | `--identity=STRING` | No | SSH identity file |
| `-s` | `--services=STRING` | No | Service descriptions (comma-separated, for passive mode) |
| `-n` | `--name=STRING` | No | Short name of host in Nagios config (passive mode) |
| `-O` | `--output=FILE` | No | Output file for passive mode checks |
| `-f` | `--fork` | No | Fork to background |
| `-t` | `--timeout=INTEGER` | No | Seconds before plugin times out |
| `-S` | `--skip-stdout[=N]` | No | Skip N lines of stdout (default: all) |
| `-E` | `--skip-stderr[=N]` | No | Skip N lines of stderr (default: all) |
| `-o` | `--ssh-option=STRING` | No | Extra SSH options (repeatable) |
| `-q` | `--quiet` | No | Suppress SSH warnings |
| `-F` | `--configfile[=FILE]` | No | SSH config file |
| `-1` | `--proto1` | No | Force SSH protocol 1 |
| `-2` | `--proto2` | No | Force SSH protocol 2 |
| `-4` | `--use-ipv4` | No | Force IPv4 |
| `-6` | `--use-ipv6` | No | Force IPv6 |

---

## 4. check_cluster
**Purpose**: Aggregate host/service cluster status
**Output Format**: `CLUSTER {OK|WARNING|CRITICAL}: {Service/Host} cluster: {N} ok, {N} warning, {N} unknown, {N} critical` (services)
**Output Format**: `CLUSTER {OK|WARNING|CRITICAL}: {Host} cluster: {N} up, {N} down, {N} unreachable` (hosts)
**Performance Data**: None
**Status Keywords**: CLUSTER OK, CLUSTER WARNING, CLUSTER CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-d` | `--data=STRING` | **Yes** | Comma-separated list of service/host status values |
| `-w` | `--warning=RANGE` | **Yes** | Warning threshold |
| `-c` | `--critical=RANGE` | **Yes** | Critical threshold |
| `-s` | `--service` | No | Check a service cluster (default) |
| `-h` | `--host` | No | Check a host cluster |
| `-l` | `--label=STRING` | No | Optional label for output |

---

## 5. check_dbi
**Purpose**: Database-independent checks via DBI
**Output Format**: `{OK|WARNING|CRITICAL} - connection time: {N}s` (no "DBI" prefix)
**Performance Data**: `conntime={N}s;{warn};{crit};0; server_version={N};{warn};{crit};0;` plus optional `query=...` / `querytime=...`
**Status Keywords**: OK, WARNING, CRITICAL
**Notes**: `plugins/check_dbi.c:295`

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-d` | `--driver=STRING` | **Yes** | DBI driver to use (e.g., mysql, pgsql, sqlite) |
| `-H` | `--hostname=STRING` | No | Database hostname |
| `-q` | `--query=STRING` | No | SQL query to execute |
| `-D` | `--database=STRING` | No | Database name |
| `-w` | `--warning=RANGE` | No | Warning range |
| `-c` | `--critical=RANGE` | No | Critical range |
| `-e` | `--expect=STRING` | No | Expected string in query result |
| `-r` | `--regex=REGEX` | No | Regex to match against query result |
| `-R` | `--regexi=REGEX` | No | Case-insensitive regex |
| `-m` | `--metric=STRING` | No | Metric to check (conntime, server_version, etc.) |
| `-o` | `--option=STRING` | No | DBI driver option (key=value, repeatable) |
| `-t` | `--timeout=INTEGER` | No | Seconds before plugin times out |

---

## 6. check_dhcp (plugins-root)
**Purpose**: Test DHCP server availability
**Output Format**: `{OK|WARNING|CRITICAL|UNKNOWN}: Received {N} DHCPOFFER(s)` (no "DHCP" prefix, no "from N server(s)")
**Performance Data**: None emitted
**Status Keywords**: OK, WARNING, CRITICAL, UNKNOWN
**Notes**: Lives in `plugins-root/check_dhcp.c`, not `plugins/`; requires root/CAP_NET_RAW

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-s` | `--serverip=IPADDRESS` | No | IP address of the DHCP server to test |
| `-r` | `--requestedip=IPADDRESS` | No | IP address to request from the DHCP server |
| `-t` | `--timeout=INTEGER` | No | Seconds to wait for a DHCPOFFER (default: 2) |
| `-i` | `--interface=IFNAME` | No | Network interface to use (e.g., eth0) |
| `-m` | `--mac=HWADDRESS` | No | MAC address to use in the DHCPDISCOVER |
| `-u` | `--unicast` | No | Send DHCPDISCOVER as unicast to `-s` address |

---

## 7. check_dig
**Purpose**: DNS lookup using dig command
**Output Format**: `DNS {OK|WARNING|CRITICAL} - {N}.{N} seconds response time ({msg})`
**Performance Data**: `time={N}s;{warn};{crit};0;0`
**Status Keywords**: DNS OK, DNS WARNING, DNS CRITICAL
**Notes**: `plugins/check_dig.c:197`

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname or IP of DNS server to query |
| `-l` | `--query_address=STRING` | No | DNS record to look up (default: hostname) |
| `-w` | `--warning=DOUBLE` | No | Warning response time threshold (seconds) |
| `-c` | `--critical=DOUBLE` | No | Critical response time threshold (seconds) |
| `-T` | `--record_type=STRING` | No | DNS record type (A, MX, etc.; default: A) |
| `-a` | `--expected_address=STRING` | No | Expected IP address in response (repeatable) |
| `-e` | `--exact` | No | Require exact match on expected address |
| `-A` | `--dig-arguments=STRING` | No | Extra arguments to pass to dig |
| `-p` | `--port=INTEGER` | No | DNS port (default: 53) |
| `-t` | `--timeout=INTEGER` | No | Seconds before plugin times out |
| `-r` | `--retries=INTEGER` | No | Number of retries |
| `-4` | `--use-ipv4` | No | Force IPv4 |
| `-6` | `--use-ipv6` | No | Force IPv6 |

---

## 8. check_disk
**Purpose**: Check disk space and inode usage
**Output Format**: `DISK {OK|WARNING|CRITICAL} - free space: /{mount_point} {N} {unit} ({N}% inode={N}%)`
**Performance Data**: `/{mount_point}={used_bytes};{warn};{crit};0;{total}`
**Performance Data**: `/{mount_point}_inode_percent={used_pct}%;{warn};{crit};0;100`
**Performance Data**: `/{mount_point}_inode_used={used_inodes};;;0;{total}`
**Performance Data**: `/{mount_point}_inode_free={free_inodes};;;0;{total}`
**Status Keywords**: DISK OK, DISK WARNING, DISK CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-w` | `--warning=INTEGER%` | **Yes** | Warning threshold (% used or free space) |
| `-c` | `--critical=INTEGER%` | **Yes** | Critical threshold (% used or free space) |
| `-W` | `--iwarning=INTEGER%` | No | Warning threshold for inode usage |
| `-K` | `--icritical=INTEGER%` | No | Critical threshold for inode usage |
| `-p` | `--path=PATH` | No | Mount point or partition to check (repeatable) |
| `-x` | `--exclude_device=PATH` | No | Exclude a device (repeatable) |
| `-X` | `--exclude-type=TYPE` | No | Exclude filesystem type (e.g., tmpfs; repeatable) |
| `-N` | `--include-type=TYPE` | No | Include only this filesystem type (repeatable) |
| `-r` | `--ereg-path=REGEX` | No | Include only paths matching regex |
| `-R` | `--eregi-path=REGEX` | No | Include only paths matching regex (case-insensitive) |
| `-i` | `--ignore-ereg-path=REGEX` | No | Ignore paths matching regex |
| `-I` | `--ignore-eregi-path=REGEX` | No | Ignore paths matching regex (case-insensitive) |
| `-g` | `--group=STRING` | No | Group paths under a single name |
| `-u` | `--units=STRING` | No | Units for output (KiB, MiB, GiB, TiB, kB, MB, GB, TB) |
| `-k` | `--kilobytes` | No | Show output in kilobytes |
| `-m` | `--megabytes` | No | Show output in megabytes |
| `-H` | `--human` | No | Human-readable output |
| `-l` | `--local` | No | Only check local filesystems |
| `-L` | `--stat-remote-fs` | No | Stat remote filesystems for accessibility |
| `-M` | `--mountpoint` | No | Display mountpoint instead of filesystem |
| `-e` | `--errors-only` | No | Only display errors |
| `-E` | `--exact-match` | No | Require exact path match |
| `-f` | `--freespace-ignore-reserved` | No | Ignore reserved space when computing free space |
| `-A` | `--all` | No | Check all filesystems |
| `-n` | `--newlines` | No | Each disk on a new line |
| `-t` | `--timeout=INTEGER` | No | Seconds before plugin times out |
| N/A | `--inode-perfdata` | No | Include inode metrics in perfdata |
| N/A | `--skip-fake-fs` | No | Skip virtual/pseudo filesystems |
| N/A | `--combined-thresholds` | No | Apply single threshold to combined usage |

---

## 9. check_disk_smb (Perl) — `plugins-scripts/`
**Purpose**: Check disk space on SMB/CIFS shares via smbclient
**Output Format**: `Disk ok - {N}{unit} ({N%} free) on {mount_path}`
**Output Format (warning)**: `WARNING: Only {N}{unit} ({N%} free) on {mount_path}`
**Output Format (critical)**: `CRITICAL: Only {N}{unit} ({N%} free) on {mount_path}`
**Performance Data**: `'share_name'={used_bytes}B;{warn_bytes};{crit_bytes};0;{total_bytes}`
**Status Keywords**: Disk ok, WARNING, CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname of the SMB server |
| `-s` | `--share=STRING` | **Yes** | Share name to check |
| `-u` | `--username=STRING` | No | SMB username (default: guest) |
| `-p` | `--password=STRING` | No | SMB password |
| `-w` | `--warning=INTEGER%` | No | Warning free-space threshold % (default: 85) |
| `-c` | `--critical=INTEGER%` | No | Critical free-space threshold % (default: 95) |
| `-W` | `--workgroup=STRING` | No | SMB workgroup/domain |
| `-a` | `--address=STRING` | No | IP address of SMB server (if different from hostname) |
| `-P` | `--port=INTEGER` | No | SMB port |
| `-m` | `--maxprotocol=STRING` | No | Maximum SMB protocol version |
| `-k` | `--kerberos` | No | Use Kerberos authentication |
| `-C` | `--configfile=STRING` | No | smbclient configuration file |

---

## 10. check_dns
**Purpose**: Check DNS server response
**Output Format**: `DNS {OK|WARNING|CRITICAL}: {N}.{N} second response time. {domain} returns {address}`
**Performance Data**: `time={N}s;{warn};{crit};0;0`
**Status Keywords**: DNS OK, DNS WARNING, DNS CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname to look up |
| `-s` | `--server=STRING` | No | DNS server to query (default: system resolver) |
| `-a` | `--expected-address=STRING` | No | Expected IP address (repeatable) |
| `-A` | `--expect-authority` | No | Expect an authoritative response |
| `-n` | `--accept-cname` | No | Accept CNAME records in response |
| `-q` | `--querytype=STRING` | No | DNS query type (A, AAAA, MX, etc.; default: A) |
| `-r` | `--reverse-server=STRING` | No | Reverse lookup DNS server |
| `-w` | `--warning=DOUBLE` | No | Warning response time (seconds) |
| `-c` | `--critical=DOUBLE` | No | Critical response time (seconds) |
| `-t` | `--timeout=INTEGER` | No | Seconds before plugin times out |

---

## 11. check_dummy
**Purpose**: Return a specified state with message
**Output Format**: `{OK|WARNING|CRITICAL|UNKNOWN}: {message}`
**Performance Data**: None
**Status Keywords**: OK, WARNING, CRITICAL, UNKNOWN

**Arguments**:
| Positional | Description |
|------------|-------------|
| `<integer>` | **Required.** Exit state: 0=OK, 1=WARNING, 2=CRITICAL, 3=UNKNOWN |
| `[text]` | Optional. Text to include in output |

---

## 12. check_flexlm (Perl) — `plugins-scripts/`
**Purpose**: Check FlexLM license server status via lmstat
**Output Format (all up)**: `License Servers running:{server1},{server2},...`
**Output Format (some down)**: `License Servers running:{server1},...\nLicense servers NOT running:{server2},...`
**Performance Data**: `flexlm::up:{N};down:{N}` (non-standard; uses `:` separator)
**Status Keywords**: OK, WARNING, CRITICAL (via exit code only)
**Notes**: OK if all servers up, WARNING if some down, CRITICAL if all down.

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-F` | `--filename=STRING` | **Yes** | Path to the FlexLM `license.dat` file |
| `-t` | `--timeout=INTEGER` | No | Timeout in seconds |

---

## 13. check_fping
**Purpose**: Fast ping using fping
**Output Format**: `FPING {OK|WARNING|CRITICAL} - {host} (loss={N}%, rta={N} ms)`
**Performance Data**: `loss={N}%;{warn};{crit};0;100 rta={N}s;{warn};{crit};0;0`
**Status Keywords**: FPING OK, FPING WARNING, FPING CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname or IP to ping |
| `-w` | `--warning=RANGE` | **Yes** | Warning threshold (loss%,rta) e.g. `20%,100` |
| `-c` | `--critical=RANGE` | **Yes** | Critical threshold (loss%,rta) e.g. `40%,200` |
| `-n` | `--number=INTEGER` | No | Number of packets to send (default: 1) |
| `-b` | `--bytes=INTEGER` | No | Packet size in bytes |
| `-T` | `--target-timeout=INTEGER` | No | Per-target timeout in ms |
| `-i` | `--interval=INTEGER` | No | Interval between pings in ms |
| `-S` | `--sourceip=STRING` | No | Source IP address |
| `-I` | `--sourceif=STRING` | No | Source interface |
| `-4` | `--use-ipv4` | No | Force IPv4 |
| `-6` | `--use-ipv6` | No | Force IPv6 |

---

## 14. check_game
**Purpose**: Check game server status via qstat
**Output Format**: `OK: {players}/{max} {type} ({map}), Ping: {N} ms`
**Performance Data**: `players={N};;;0;{max} ping={N}ms`
**Status Keywords**: OK, CRITICAL (no WARNING state)

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname or IP of the game server |
| `-G` | `--game-type=STRING` | **Yes** | Game type (passed to qstat; e.g., `qs`, `q2s`) |
| `-P` | `--port=INTEGER` | No | Game server port |
| `-g` | `--game-field=INTEGER` | No | Field index for game type in qstat output |
| `-m` | `--map-field=INTEGER` | No | Field index for map name in qstat output |
| `-p` | `--ping-field=INTEGER` | No | Field index for ping value in qstat output |
| `-t` | `--timeout=INTEGER` | No | Seconds before plugin times out |

---

## 15. check_hpjd
**Purpose**: Check HP JetDirect printer status via SNMP
**Output Format**: `Printer ok - ({status_message})` for OK; raw error text for failures
**Performance Data**: None
**Status Keywords**: (no "HPJD" prefix; Printer ok / error text)

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname or IP of the printer |
| `-C` | `--community=STRING` | No | SNMP community string (default: public) |
| `-p` | `--port=INTEGER` | No | SNMP port (default: 161) |
| `-N` | `--flawcorrection` | No | Enable flaw correction mode |

---

## 16. check_http
**Purpose**: Check HTTP/HTTPS web server
**Output Format**: `HTTP {OK|WARNING|CRITICAL} - {N} bytes in {N}.{N} second response time {url}`
**Performance Data**: `time={N}s;{warn};{crit};0;0 size={N}B;{warn};{crit};0;0`
**Performance Data**: `time_connect={N}s time_first_byte={N}s time_transfer={N}s`
**Status Keywords**: HTTP OK, HTTP WARNING, HTTP CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Virtual hostname (HTTP Host header) |
| `-I` | `--IP-address=STRING` | No | Server IP address (overrides DNS) |
| `-u` | `--url=PATH` | No | URL path to request (default: /) |
| `-p` | `--port=INTEGER` | No | Port (default: 80 or 443 with SSL) |
| `-w` | `--warning=DOUBLE` | No | Warning response time threshold (seconds) |
| `-c` | `--critical=DOUBLE` | No | Critical response time threshold (seconds) |
| `-S` | `--ssl[=1\|2\|3]` | No | Use HTTPS; optionally specify SSL version |
| `-N` | `--sni` | No | Enable TLS SNI |
| N/A | `--verify-host` | No | Verify SSL certificate hostname |
| `-C` | `--certificate=INTEGER` | No | Warn if SSL cert expires in fewer than N days |
| `-J` | `--client-cert=FILE` | No | Client certificate file |
| `-K` | `--private-key=FILE` | No | Client private key file |
| `-e` | `--expect=STRING` | No | Expected HTTP status code(s) (default: HTTP/1 2\|3) |
| `-s` | `--string=STRING` | No | String to expect in body |
| `-r` | `--regex=REGEX` | No | Regex to match in body |
| `-R` | `--eregi=REGEX` | No | Case-insensitive regex to match in body |
| N/A | `--invert-regex` | No | Invert regex match result |
| `-l` | `--linespan` | No | Allow regex to span newlines |
| `-P` | `--post=STRING` | No | HTTP POST data (URL-encoded) |
| `-j` | `--method=STRING` | No | HTTP method (default: GET) |
| `-a` | `--authorization=STRING` | No | HTTP Basic Auth credentials (user:pass) |
| `-b` | `--proxy-authorization=STRING` | No | Proxy auth credentials (user:pass) |
| `-f` | `--onredirect=ok\|warning\|critical\|follow\|sticky\|stickyport` | No | Redirect handling behavior (default: follow) |
| `-A` | `--useragent=STRING` | No | User-Agent string |
| `-k` | `--header=STRING` | No | Extra HTTP request header (repeatable) |
| `-d` | `--header-string=STRING` | No | String to expect in response headers |
| `-T` | `--content-type=STRING` | No | Content-Type for POST requests |
| `-m` | `--pagesize=INTEGER:INTEGER` | No | Minimum:maximum expected page size (bytes) |
| `-M` | `--max-age=INTEGER` | No | Warn if document older than N seconds |
| `-n` | `--nohtml` | No | Strip HTML tags from output |
| `-L` | `--link` | No | Show HTML link in output |
| `-N` | `--no-body` | No | Do not fetch the body |
| `-E` | `--extended-perfdata` | No | Include connect/first-byte/transfer timing in perfdata |
| `-o` | `--output-body-as-perfdata` | No | Output body as perfdata |
| `-U` | `--show-url` | No | Show URL in output |
| `-4` | `--use-ipv4` | No | Force IPv4 |
| `-6` | `--use-ipv6` | No | Force IPv6 |
| `-t` | `--timeout=INTEGER` | No | Seconds before plugin times out |

---

## 17. check_ide_smart
**Purpose**: Check IDE/S.M.A.R.T. disk health
**Output Format**: `OK - Operational (N/N tests passed)` / `WARNING - N Harddrive Advisor(s) Detected.` / `CRITICAL - N Harddrive PreFailure(s) Detected!`
**Performance Data**: None
**Status Keywords**: OK, WARNING, CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-d` | `--device=DEVICE` | **Yes** | Block device to check (e.g., /dev/hda) |
| `-i` | `--immediate` | No | Run self-test immediately |
| `-q` | `--quiet-check` | No | Suppress SMART attribute output |
| `-n` | `--nagios` | No | Nagios-compatible output mode |
| `-1` | `--auto-on` | No | Enable automatic SMART testing |
| `-0` | `--auto-off` | No | Disable automatic SMART testing |

---

## 18. check_icmp (plugins-root)
**Purpose**: ICMP ping with high precision
**Output Format**: `{OK|WARNING|CRITICAL} - {host}: rta {N}ms, lost {N}%`
**Performance Data**: `rta={N}ms;{warn};{crit};0; pl={N}%;{warn};{crit};0;100`
**Status Keywords**: OK, WARNING, CRITICAL
**Notes**: Requires root/CAP_NET_RAW

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname(s) or IP address(es) to ping (repeatable) |
| `-w` | `--warning=RANGE` | **Yes** | Warning threshold (`rta,loss%` e.g. `100.0,20%`) |
| `-c` | `--critical=RANGE` | **Yes** | Critical threshold (`rta,loss%` e.g. `200.0,40%`) |
| `-n` / `-p` | `--packets=INTEGER` | No | Number of packets to send (default: 5) |
| `-t` | `--timeout=INTEGER` | No | Timeout in seconds |
| `-i` | (interval) | No | Packet interval in ms |
| `-I` | (target interval) | No | Target interval in ms |
| `-b` | (bytes) | No | Packet size in bytes |
| `-s` | (source IP) | No | Source IP address to bind to |
| `-l` | (TTL) | No | Time-to-live |
| `-m` | (min alive) | No | Minimum hosts that must be alive |
| `-R` | (RTA mode) | No | RTA warning,critical thresholds only |
| `-P` | (loss mode) | No | Packet loss warning,critical thresholds only |
| `-4` | `--use-ipv4` | No | Force IPv4 |
| `-6` | `--use-ipv6` | No | Force IPv6 |

---

## 19. check_ifoperstatus (Perl) — `plugins-scripts/`
**Purpose**: Check individual SNMP interface operational status
**Output Format (up)**: `OK: Interface {name} (index {N}) is up.`
**Output Format (down)**: `CRITICAL: Interface {name} (index {N}) is down.`
**Performance Data**: None
**Status Keywords**: OK, WARNING, CRITICAL, UNKNOWN

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname or IP |
| `-k` | `--key=INTEGER` | No* | SNMP interface index key (*required if no `-d` or `-T`) |
| `-d` | `--descr=STRING` | No* | Interface description string (*required if no `-k` or `-T`) |
| `-T` | `--type=INTEGER` | No* | Interface type (*required if no `-k` or `-d`) |
| `-n` | `--name=STRING` | No | Expected interface name (for verification) |
| `-C` | `--community=STRING` | No | SNMP community string (default: public) |
| `-v` | `--snmp_version=INTEGER` | No | SNMP version (1, 2c, 3; default: 2c) |
| `-p` | `--port=INTEGER` | No | SNMP port (default: 161) |
| `-L` | `--seclevel=STRING` | No | SNMPv3 security level |
| `-U` | `--secname=STRING` | No | SNMPv3 security name |
| `-a` | `--authproto=STRING` | No | SNMPv3 auth protocol |
| `-A` | `--authpass=STRING` | No | SNMPv3 auth password |
| `-X` | `--privpass=STRING` | No | SNMPv3 priv password |
| `-P` | `--privproto=STRING` | No | SNMPv3 priv protocol |
| `-c` | `--context=STRING` | No | SNMPv3 context |
| `-I` | `--ifmib` | No | Use IF-MIB (ifXTable) |
| `-w` | `--warn=STRING` | No | Warn on dormant state |
| `-D` | `--admin-down=STRING` | No | Action on admin-down state |
| `-l` | `--lastchange=STRING` | No | Check last change time |
| `-M` | `--maxmsgsize=INTEGER` | No | SNMP max message size |
| `-t` | `--timeout=INTEGER` | No | Timeout in seconds |

---

## 20. check_ifstatus (Perl) — `plugins-scripts/`
**Purpose**: Check bulk SNMP interface status (up/down counts)
**Output Format (OK)**: `OK: host '{host}', interfaces up: {N}, down: {N}, dormant: {N}, excluded: {N}, unused: {N}`
**Output Format (CRITICAL)**: `CRITICAL: host '{host}', interfaces up: {N}, down: {N}, dormant: {N}, excluded: {N}, unused: {N}<BR>\n{down_interface_details}`
**Performance Data**: `up={N} down={N} dormant={N} excluded={N} unused={N}`
**Status Keywords**: OK, CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname or IP |
| `-C` | `--community=STRING` | No | SNMP community string (default: public) |
| `-v` | `--snmp_version=STRING` | No | SNMP version (1, 2c, 3; default: 2c) |
| `-p` | `--port=INTEGER` | No | SNMP port (default: 161) |
| `-I` | `--ifmib` | No | Use IF-MIB (ifXTable) |
| `-x` | `--exclude[=STRING]` | No | Exclude interfaces by index or name |
| `-u` | `--unused_ports=STRING` | No | Mark these ports as "unused" |
| `-n` | `--unused_ports_by_name=STRING` | No | Mark ports matching name as "unused" |
| `-d` | `--exclude_ports_by_description=STRING` | No | Exclude ports by description |
| `-L` | `--seclevel=STRING` | No | SNMPv3 security level |
| `-U` | `--secname=STRING` | No | SNMPv3 security name |
| `-a` | `--authproto=STRING` | No | SNMPv3 auth protocol |
| `-A` | `--authpass=STRING` | No | SNMPv3 auth password |
| `-X` | `--privpass=STRING` | No | SNMPv3 priv password |
| `-P` | `--privproto=STRING` | No | SNMPv3 priv protocol |
| `-c` | `--context=STRING` | No | SNMPv3 context |
| `-M` | `--maxmsgsize=INTEGER` | No | SNMP max message size |
| `-t` | `--timeout=INTEGER` | No | Timeout in seconds |

---

## 21. check_ircd (Perl) — `plugins-scripts/`
**Purpose**: Check IRC daemon user count
**Output Format (OK)**: `IRCD ok - Current Local Users: {N}`
**Output Format (WARNING)**: `Warning Number Of Clients Connected : {N} (Limit = {warn_limit})`
**Output Format (CRITICAL)**: `Critical Number Of Clients Connected : {N} (Limit = {crit_limit})`
**Performance Data**: None
**Status Keywords**: IRCD ok, Warning, Critical

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname of the IRC server |
| `-w` | `--warning=INTEGER` | No | Warning user count threshold (default: 50) |
| `-c` | `--critical=INTEGER` | No | Critical user count threshold (default: 100) |
| `-p` | `--port=INTEGER` | No | IRC port (default: 6667) |
| `-t` | `--timeout=INTEGER` | No | Timeout in seconds |

---

## 22. check_ldap / check_ldaps
**Purpose**: Check LDAP server connection and search
**Output Format**: `LDAP {OK|WARNING|CRITICAL} - found {N} entries in {N}.{N} seconds`
**Performance Data**: `time={N}s;{warn};{crit};0;0 entries={N};{warn};{crit};0;0`
**Status Keywords**: LDAP OK, LDAP WARNING, LDAP CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname or IP of LDAP server |
| `-b` | `--base=STRING` | **Yes** | LDAP search base DN |
| `-U` | `--uri=STRING` | No | LDAP URI (alternative to -H) |
| `-p` | `--port=INTEGER` | No | LDAP port (default: 389, or 636 with SSL) |
| `-a` | `--attr=STRING` | No | LDAP attribute to retrieve |
| `-D` | `--bind=STRING` | No | Bind DN for authentication |
| `-P` | `--pass=STRING` | No | Bind password |
| `-w` | `--warn=DOUBLE` | No | Warning response time (seconds) |
| `-c` | `--crit=DOUBLE` | No | Critical response time (seconds) |
| `-W` | `--warn-entries=INTEGER` | No | Warning threshold for entry count |
| `-C` | `--crit-entries=INTEGER` | No | Critical threshold for entry count |
| `-T` | `--starttls` | No | Use StartTLS |
| `-S` | `--ssl` | No | Use LDAPS (SSL) |
| `-A` | `--age=INTEGER` | No | Warn if certificate expires in fewer than N days |
| `-2` | `--ver2` | No | Use LDAP protocol version 2 |
| `-3` | `--ver3` | No | Use LDAP protocol version 3 (default) |
| `-4` | `--use-ipv4` | No | Force IPv4 |
| `-6` | `--use-ipv6` | No | Force IPv6 |
| `-t` | `--timeout=INTEGER` | No | Seconds before plugin times out |

---

## 23. check_load
**Purpose**: Check system load averages
**Output Format**: `{OK|WARNING|CRITICAL} - load average: {N.NN}, {N.NN}, {N.NN}`
**Performance Data**: `load1={N};{warn};{crit};0; load5={N};{warn};{crit};0; load15={N};{warn};{crit};0;`
**Status Keywords**: OK, WARNING, CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-w` | `--warning=WLOAD1,WLOAD5,WLOAD15` | **Yes** | Warning thresholds for 1, 5, 15 min averages |
| `-c` | `--critical=CLOAD1,CLOAD5,CLOAD15` | **Yes** | Critical thresholds for 1, 5, 15 min averages |
| `-r` | `--percpu` | No | Divide load by number of CPUs |
| `-n` | `--procs-to-show=INTEGER` | No | Number of processes to display in output |

---

## 24. check_log (Bash) — `plugins-scripts/`
**Purpose**: Scan log files for pattern matches (stateful — tracks previous runs)
**Output Format (no matches)**: `Log check ok - 0 pattern matches found|match={N};;;0`
**Output Format (matches found)**: `({N}) {matching_line_content}|match={N};;;0`
**Performance Data**: `match={N};;;0`
**Status Keywords**: OK, CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-F` | `--filename=FILE` | **Yes** | Path to the log file to check |
| `-O` | `--oldlog=FILE` | **Yes** | Path to the state/old log file (created if missing) |
| `-q` | `--query=STRING` | **Yes** | Pattern (regex) to search for |
| `-w` | `--max_warning=INTEGER` | No | Return WARNING if match count >= N (otherwise CRITICAL) |
| `-t` | (exit status) | No | Override exit status |
| `-x` | `--exitstatus=INTEGER` | No | Override exit status code |

---

## 25. check_mailq (Perl) — `plugins-scripts/`
**Purpose**: Check mail queue length for multiple MTA backends
**Supported MTAs**: sendmail, qmail, postfix, exim, nullmailer, opensmtpd
**Output Format (sendmail, OK)**: `OK: sendmail mailq is empty`
**Output Format (sendmail, WARNING)**: `WARNING: sendmail mailq is {N} (threshold w = {warn})`
**Output Format (sendmail, CRITICAL)**: `CRITICAL: sendmail mailq is {N} (threshold c = {crit})`
**Performance Data**: `unsent={N};{warn};{crit};0`
**Status Keywords**: OK, WARNING, CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-w` | `--warning=INTEGER` | **Yes** | Warning queue length threshold |
| `-c` | `--critical=INTEGER` | **Yes** | Critical queue length threshold |
| `-M` | `--mailserver[=STRING]` | No | MTA type (sendmail, qmail, postfix, exim, etc.; default: sendmail) |
| `-t` | `--timeout=INTEGER` | No | Timeout in seconds |
| `-s` | `--sudo` | No | Run mailq command via sudo |
| `-d` | `--configdir[=STRING]` | No | postfix config directory |
| `-W` | (domain warning) | No | Warning threshold for per-domain queue |
| `-C` | (domain critical) | No | Critical threshold for per-domain queue |

---

## 26. check_mrtg
**Purpose**: Check MRTG log file values
**Output Format**: `{OK|WARNING|CRITICAL} - {Avg|Max}. {label} = {N} {units}`
**Performance Data**: `{label}={N};{warn};{crit};0;0`
**Status Keywords**: OK, WARNING, CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-F` | `--logfile=FILE` | **Yes** | Path to the MRTG log file |
| `-w` | `--warning=INTEGER` | **Yes** | Warning threshold |
| `-c` | `--critical=INTEGER` | **Yes** | Critical threshold |
| `-e` | `--expires=INTEGER` | **Yes** | Minutes before data is considered stale |
| `-a` | `--aggregation=STRING` | **Yes** | Aggregation type: `AVG` or `MAX` |
| `-v` | `--variable=INTEGER` | **Yes** | Which MRTG variable to check (1 or 2) |
| `-l` | `--label=STRING` | No | Label for output |
| `-u` | `--units=STRING` | No | Units string for output |

---

## 27. check_mrtgtraf
**Purpose**: Check MRTG traffic log files
**Output Format**: `Traffic {OK|WARNING|CRITICAL} - {Avg|Max}. In = {N.N} {unit}/s, {Avg|Max}. Out = {N.N} {unit}/s`
**Performance Data**: `in={N}{unit};{warn};{crit};0;0 out={N}{unit};{warn};{crit};0;0`
**Status Keywords**: Traffic OK, Traffic WARNING, Traffic CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-F` | `--filename=FILE` | **Yes** | Path to the MRTG log file |
| `-w` | `--warning=INTEGER,INTEGER` | **Yes** | Warning thresholds for in,out traffic |
| `-c` | `--critical=INTEGER,INTEGER` | **Yes** | Critical thresholds for in,out traffic |
| `-e` | `--expires=INTEGER` | **Yes** | Minutes before data is considered stale |
| `-a` | `--aggregation=STRING` | **Yes** | Aggregation type: `AVG` or `MAX` |
| `-i` | `--interface-maximum=INTEGER` | No | Interface maximum bandwidth (for % calculation) |

---

## 28. check_mysql
**Purpose**: Check MySQL server connection and status
**Output Format**: Raw `mysql_stat()` string (Uptime, Threads, Questions, etc.)
**Output Format (slave check)**: `SLOW_SLAVE {WARNING|CRITICAL}: Slave IO: {Yes/No} Slave SQL: {Yes/No} Seconds Behind Master: {N}`
**Performance Data**: `Connections={N}c Queries={N}c Uptime={N}s Threads_connected={N} ...`
**Status Keywords**: SLOW_SLAVE WARNING/CRITICAL (slave path only)

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | No | MySQL hostname (default: localhost) |
| `-P` | `--port=INTEGER` | No | MySQL port (default: 3306) |
| `-s` | `--socket=STRING` | No | MySQL socket file path |
| `-d` | `--database=STRING` | No | Database to connect to |
| `-u` | `--username=STRING` | No | MySQL username |
| `-p` | `--password=STRING` | No | MySQL password |
| `-f` | `--file=STRING` | No | MySQL client options file |
| `-g` | `--group=STRING` | No | MySQL client options group |
| `-S` | `--check-slave` | No | Check replication slave status |
| `-w` | `--warning=DOUBLE` | No | Warning threshold (seconds behind master for slave) |
| `-c` | `--critical=DOUBLE` | No | Critical threshold (seconds behind master for slave) |
| `-n` | `--ignore-auth` | No | Ignore authentication errors |
| `-l` | `--ssl` | No | Use SSL/TLS connection |
| `-C` | `--ca-cert[=FILE]` | No | CA certificate file |
| `-a` | `--cert=FILE` | No | Client certificate file |
| `-k` | `--key=FILE` | No | Client private key file |
| `-D` | `--ca-dir=DIR` | No | Directory containing CA certificates |
| `-L` | `--ciphers=STRING` | No | SSL cipher list |

---

## 29. check_mysql_query
**Purpose**: Run arbitrary SQL and check result
**Output Format**: `QUERY {OK|WARNING|CRITICAL}: '{sql}' returned {N}`
**Performance Data**: `result={N};{warn};{crit};0;0`
**Status Keywords**: QUERY OK, QUERY WARNING, QUERY CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-q` | `--query=STRING` | **Yes** | SQL query to execute |
| `-w` | `--warning=RANGE` | **Yes** | Warning threshold for query result |
| `-c` | `--critical=RANGE` | **Yes** | Critical threshold for query result |
| `-H` | `--hostname=STRING` | No | MySQL hostname |
| `-P` | `--port=INTEGER` | No | MySQL port |
| `-s` | `--socket=STRING` | No | MySQL socket file |
| `-d` | `--database=STRING` | No | Database to connect to |
| `-u` | `--username=STRING` | No | MySQL username |
| `-p` | `--password=STRING` | No | MySQL password |
| `-a` | `--character-set=STRING` | No | Character set for the connection |
| `-f` | `--file=STRING` | No | MySQL client options file |
| `-g` | `--group=STRING` | No | MySQL client options group |

---

## 30. check_ncpa (Python) — `plugins-scripts/`
**Purpose**: Check metrics via NCPA (Nagios Cross-Platform Agent) API
**Output Format**: Varies — passes through NCPA agent output
**Output Format (error)**: `UNKNOWN: An error occured connecting to API. (HTTP error: '{code}')`
**Performance Data**: Depends on remote metric
**Status Keywords**: Varies (passthrough from NCPA agent)
**Example Outputs**: 
cpu/percent: `OK: Percent was 0.97 % | 'percent'=0.97%;70;90;`
disk/logical/|/used_percent: `OK: Used_percent was 15.60 % | 'used_percent'=15.60%;60;96;`
memory/virtual/percent: `OK: Percent was 13.30 % | 'percent'=13.30%;60;90;`

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname or IP of the NCPA agent |
| `-t` | `--token=STRING` | **Yes** | NCPA API authentication token |
| `-M` | `--metric=STRING` | **Yes** | Metric path to check (e.g., `cpu/percent`) |
| `-P` | `--port=INTEGER` | No | NCPA port (default: 5693) |
| `-w` | `--warning=STRING` | No | Warning threshold |
| `-c` | `--critical=STRING` | No | Critical threshold |
| `-u` / `-n` | `--units=STRING` | No | Units for the metric value |
| `-a` | `--arguments=STRING` | No | Arguments to pass to a custom plugin |
| `-T` | `--timeout=INTEGER` | No | Timeout in seconds (default: 55) |
| `-d` | `--delta` | No | Calculate rate of change (delta) |
| `-l` | `--list` | No | List available metrics |
| `-q` | `--queryargs=STRING` | No | Extra query arguments |
| `-s` | `--secure` | No | Use HTTPS (default: True) |
| `-p` | `--performance` | No | Force performance data output |
| `-D` | `--debug` | No | Enable debug output |

---

## 31. check_nagios
**Purpose**: Check Nagios process and status log freshness
**Output Format**: `NAGIOS {OK|WARNING}: {N} process, status log updated {N} seconds ago`
**Performance Data**: None
**Status Keywords**: NAGIOS OK, NAGIOS WARNING

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-F` | `--filename=FILE` | **Yes** | Path to the Nagios status log file |
| `-e` | `--expires=INTEGER` | **Yes** | Maximum allowed age (minutes) of the status log |
| `-C` | `--command=STRING` | **Yes** | Nagios process name/command to look for |
| `-t` | `--timeout[=INTEGER]` | No | Seconds before plugin times out |

---

## 32. check_nt
**Purpose**: Check Windows NT/2000/XP/2003 server via NSClient
**Output Format (CPU load)**: `CPU Load: {N}% ({N} min average), ...`
**Output Format (memory)**: `Memory usage: Total: {N} MB, Used: {N} MB ({N}%), Free: {N} MB ({N}%)`
**Output Format (disk)**: `{drive}:\ - total: {N} Gb - used: {N} Gb ({N}%) - free {N} Gb ({N}%)`
**Performance Data**: Varies by check type
**Status Keywords**: Depends on check type

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname of the Windows server |
| `-v` | `--variable=STRING` | **Yes** | Variable to check: CLIENTVERSION, CPULOAD, UPTIME, USEDDISKSPACE, MEMUSE, SERVICESTATE, PROCSTATE, COUNTER, FILEAGE, INSTANCES |
| `-p` | `--port=INTEGER` | No | NSClient port (default: 1248) |
| `-s` | `--secret=STRING` | No | NSClient password |
| `-w` | `--warning=STRING` | No | Warning threshold |
| `-c` | `--critical=STRING` | No | Critical threshold |
| `-l` | `--params=STRING` | No | Additional parameters for the variable (e.g., drive letter, service name) |
| `-d` | `--display=STRING` | No | Display mode for service state (SHOWALL) |
| `-u` | `--unknown-timeout` | No | Return UNKNOWN on timeout instead of CRITICAL |
| `-t` | `--timeout=INTEGER` | No | Seconds before plugin times out |

---

## 33. check_ntp (C — DEPRECATED)
**Purpose**: Deprecated — use check_ntp_time or check_ntp_peer instead
**Output Format**: `NTP {OK|WARNING|CRITICAL}: Offset {N} secs`
**Performance Data**: `offset={N}s;{warn};{crit}`
**Status Keywords**: NTP OK, NTP WARNING, NTP CRITICAL, NTP UNKNOWN

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | NTP server hostname or IP |
| `-w` | `--warning=DOUBLE` | No | Warning offset threshold (seconds) |
| `-c` | `--critical=DOUBLE` | No | Critical offset threshold (seconds) |
| `-j` | `--jwarn=DOUBLE` | No | Warning jitter threshold |
| `-k` | `--jcrit=DOUBLE` | No | Critical jitter threshold |
| `-d` | `--delay[=INTEGER]` | No | Initial delay (useful for anti-DOS) |
| `-z` | `--allow-zero-stratum` | No | Do not treat stratum 0 as an error |
| `-t` | `--timeout=INTEGER` | No | Timeout in seconds |
| `-4` | `--use-ipv4` | No | Force IPv4 |
| `-6` | `--use-ipv6` | No | Force IPv6 |

---

## 34. check_ntp (Perl) — `plugins-scripts/`
**Purpose**: Check NTP time offset and jitter via ntpdate + ntpq
**Output Format (OK)**: `NTP OK: Offset {offset} secs, jitter {jitter} msec, peer is stratum {N}`
**Output Format (WARNING)**: `NTP WARNING: Offset {offset} sec > +/- {warn} sec, jitter {jitter} msec`
**Performance Data**: `offset={offset}s;{warn};{crit};; jitter={jitter}s;{jwarn};{jcrit};; peer_stratum={N}`
**Status Keywords**: NTP OK, NTP WARNING, NTP CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | NTP server hostname or IP |
| `-w` | `--warning=FLOAT` | No | Warning offset threshold (seconds) |
| `-c` | `--critical=FLOAT` | No | Critical offset threshold (seconds) |
| `-j` | `--jwarn=FLOAT` | No | Warning jitter threshold (ms) |
| `-k` | `--jcrit=FLOAT` | No | Critical jitter threshold (ms) |
| `-O` | `--zero-offset` | No | Return error if offset is zero |
| `-t` | `--timeout=INTEGER` | No | Timeout in seconds |
| `-4` | `--use-ipv4` | No | Force IPv4 |
| `-6` | `--use-ipv6` | No | Force IPv6 |

---

## 35. check_ntp_peer
**Purpose**: Check NTP server peer health
**Output Format**: `NTP {OK|WARNING|CRITICAL}: Offset={N} secs, jitter={N}, stratum={N}, truechimers={N}`
**Performance Data**: `offset={N}s;{warn};{crit}; jitter={N};{warn};{crit};0 stratum={N};{warn};{crit};0;16 truechimers={N};{warn};{crit};0`
**Status Keywords**: NTP OK, NTP WARNING, NTP CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | NTP server hostname or IP |
| `-w` | `--warning=DOUBLE` | No | Warning offset threshold (seconds) |
| `-c` | `--critical=DOUBLE` | No | Critical offset threshold (seconds) |
| `-W` | `--swarn=INTEGER` | No | Warning stratum threshold |
| `-C` | `--scrit=INTEGER` | No | Critical stratum threshold |
| `-j` | `--jwarn=DOUBLE` | No | Warning jitter threshold |
| `-k` | `--jcrit=DOUBLE` | No | Critical jitter threshold |
| `-m` | `--twarn=INTEGER` | No | Warning truechimer count threshold |
| `-n` | `--tcrit=INTEGER` | No | Critical truechimer count threshold |
| `-p` | `--port=INTEGER` | No | NTP port (default: 123) |
| `-q` | `--quiet` | No | Suppress OK output |
| `-t` | `--timeout=INTEGER` | No | Timeout in seconds |
| `-4` | `--use-ipv4` | No | Force IPv4 |
| `-6` | `--use-ipv6` | No | Force IPv6 |

---

## 36. check_ntp_time
**Purpose**: Check NTP time offset
**Output Format**: `NTP {OK|WARNING|CRITICAL}: Offset {N} secs, stratum best:{N} worst:{N}`
**Performance Data**: `offset={N}s;{warn};{crit} stratum_best={N} stratum_worst={N} num_warn_stratum={N} num_crit_stratum={N}`
**Status Keywords**: NTP OK, NTP WARNING, NTP CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | NTP server hostname or IP |
| `-w` | `--warning=DOUBLE` | No | Warning offset threshold (seconds) |
| `-c` | `--critical=DOUBLE` | No | Critical offset threshold (seconds) |
| `-W` | `--stratum-warn=INTEGER` | No | Warning stratum threshold |
| `-C` | `--stratum-crit=INTEGER` | No | Critical stratum threshold |
| `-o` | `--time-offset[=DOUBLE]` | No | Known offset to compensate for |
| `-d` | `--delay[=INTEGER]` | No | Initial delay for anti-DOS |
| `-p` | `--port=INTEGER` | No | NTP port (default: 123) |
| `-q` | `--quiet` | No | Suppress OK output |
| `-t` | `--timeout=INTEGER` | No | Timeout in seconds |
| `-4` | `--use-ipv4` | No | Force IPv4 |
| `-6` | `--use-ipv6` | No | Force IPv6 |

---

## 37. check_nwstat
**Purpose**: Check Novell NetWare server statistics
**Output Format**: Varies based on check variable
**Performance Data**: Varies based on check variable
**Status Keywords**: Depends on check type

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname of the NetWare server |
| `-v` | `--variable=STRING` | **Yes** | Variable to check (LOAD1, LOAD5, LOAD15, CONNS, VPF, VKF, LTCH, CBUFF, LRUM, DSDB, DSVER, UPTIME, WIZARDS, LOGINS, VTSYNC, ABEND) |
| `-w` | `--warning=RANGE` | No | Warning threshold |
| `-c` | `--critical=RANGE` | No | Critical threshold |
| `-p` | `--port=INTEGER` | No | Port to connect to |
| `-o` | `--osversion` | No | Display NetWare OS version |
| `-t` | `--timeout=INTEGER` | No | Timeout in seconds |

---

## 38. check_overcr
**Purpose**: Check Over-CR collector daemon
**Output Format**: Varies based on variable (load, disk, processes, uptime)
**Performance Data**: Varies based on variable
**Status Keywords**: Load OK, Process OK, Uptime OK, etc.

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname of the Over-CR server |
| `-v` | `--variable=STRING` | **Yes** | Variable to check (LOAD, DISK, PROCS, UPTIME) |
| `-w` | `--warning=RANGE` | No | Warning threshold |
| `-c` | `--critical=RANGE` | No | Critical threshold |
| `-p` | `--port=INTEGER` | No | Port to connect to |
| `-t` | `--timeout=INTEGER` | No | Timeout in seconds |

---

## 39. check_oracle (Bash) — `plugins-scripts/`
**Purpose**: Check Oracle database status via multiple methods
**Output Format**: Varies by check type
**Performance Data**: Varies by check type
**Status Keywords**: OK, WARNING, CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| N/A | `--tns SID/IP` | No* | Check TNS connectivity (*one mode required) |
| N/A | `--db SID` | No* | Check local database status |
| N/A | `--login SID` | No* | Check login capability |
| N/A | `--connect SID` | No* | Check connection |
| N/A | `--cache SID USER PASS CRIT WARN` | No* | Check buffer/library cache ratios |
| N/A | `--tablespace SID USER PASS TS CRIT WARN` | No* | Check tablespace usage |
| N/A | `--oranames HOST` | No* | Check Oracle Names server |

---

## 40. check_pgsql
**Purpose**: Check PostgreSQL database connection
**Output Format**: `{OK|WARNING|CRITICAL} - database {dbname} ({N} sec.) | time={N}s;{warn};{crit};0`
**Performance Data**: `time={N}s;{warn};{crit};0`
**Status Keywords**: OK, WARNING, CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | No | PostgreSQL hostname (default: localhost) |
| `-P` | `--port=INTEGER` | No | PostgreSQL port (default: 5432) |
| `-d` | `--database=STRING` | No | Database name (default: template1) |
| `-l` | `--logname=STRING` | No | Login name |
| `-p` | `--password=STRING` | No | Password |
| `-a` | `--authorization=STRING` | No | Authorization pair (user:password) |
| `-w` | `--warning=DOUBLE` | No | Warning connection time (seconds) |
| `-c` | `--critical=DOUBLE` | No | Critical connection time (seconds) |
| `-W` | `--query_warning=STRING` | No | Warning threshold for query result |
| `-C` | `--query_critical=STRING` | No | Critical threshold for query result |
| `-q` | `--query=STRING` | No | SQL query to execute |
| `-r` | `--print-query` | No | Print the executed query in output |
| `-o` | `--option=STRING` | No | Connection option (key=value, repeatable) |
| `-t` | `--timeout=INTEGER` | No | Seconds before plugin times out |

---

## 41. check_ping
**Purpose**: Ping host and measure response time
**Output Format**: `PING {OK|WARNING|CRITICAL} - Packet loss = {N}%, RTA = {N.NN} ms`
**Performance Data**: `rta={N}ms;{warn};{crit};0; pl={N}%;{warn};{crit};0;100`
**Status Keywords**: PING OK, PING WARNING, PING CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname or IP address to ping |
| `-w` | `--warning=THRESHOLD` | **Yes** | Warning threshold (`rta,loss%` e.g. `100.0,20%`) |
| `-c` | `--critical=THRESHOLD` | **Yes** | Critical threshold (`rta,loss%` e.g. `500.0,60%`) |
| `-p` | `--packets=INTEGER` | No | Number of ICMP packets to send (default: 5) |
| `-s` | `--show-resolution` | No | Show hostname resolution result |
| `-n` | `--nohtml` | No | Disable HTML output |
| `-L` | `--link` | No | Include HTML hyperlink in output |
| `-4` | `--use-ipv4` | No | Force IPv4 |
| `-6` | `--use-ipv6` | No | Force IPv6 |
| `-t` | `--timeout=INTEGER` | No | Seconds before plugin times out |

---

## 42. check_procs
**Purpose**: Check process count and resources
**Output Format**: `PROCS {OK|WARNING|CRITICAL}: {N} process{with filters}`
**Performance Data**: `procs={N};;;0;` (plus type-specific metrics)
**Status Keywords**: PROCS OK, PROCS WARNING, PROCS CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-w` | `--warning=RANGE` | **Yes** | Warning process count range |
| `-c` | `--critical=RANGE` | **Yes** | Critical process count range |
| `-m` | `--metric=STRING` | No | Metric to check: PROCS (default), VSZ, RSS, CPU, ELAPSED |
| `-C` | `--command=STRING` | No | Filter by command name |
| `-a` | `--argument-array=STRING` | No | Filter by argument string |
| N/A | `--ereg-argument-array=STRING` | No | Filter by regex on argument string |
| `-u` | `--user=STRING` | No | Filter by username or UID |
| `-p` | `--ppid=INTEGER` | No | Filter by parent PID |
| `-j` | `--jid=INTEGER` | No | Filter by jail ID (FreeBSD) |
| `-s` | `--status=STRING` | No | Filter by process state (D, R, S, T, Z) |
| `-z` | `--vsz=INTEGER` | No | Filter by VSZ (virtual memory size) |
| `-r` | `--rss=INTEGER` | No | Filter by RSS (resident set size) |
| `-P` | `--pcpu=FLOAT` | No | Filter by CPU usage % |
| `-e` | `--elapsed=INTEGER` | No | Filter by elapsed time (seconds) |
| `-g` | `--cgroup-hierarchy=STRING` | No | Filter by cgroup |
| `-X` | `--exclude-process=STRING` | No | Exclude processes matching this name |
| `-k` | `--no-kthreads=STRING` | No | Exclude Linux kernel threads |
| `-T` | `--traditional-filter` | No | Use traditional ps filter behavior |
| N/A | `--input-file=FILE` | No | Read process list from file (for testing) |
| `-t` | `--timeout=INTEGER` | No | Seconds before plugin times out |

---

## 43. check_radius
**Purpose**: Test RADIUS server authentication
**Output Format**: `{Auth OK|Auth Failed|Auth Error|Timeout|Bad Response}`
**Performance Data**: None
**Status Keywords**: (state via exit code only)

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | RADIUS server hostname or IP |
| `-u` | `--username=STRING` | **Yes** | Username for authentication test |
| `-p` | `--password=STRING` | **Yes** | Password for authentication test |
| `-F` | `--filename=FILE` | **Yes** | Path to RADIUS configuration/dictionary file |
| `-P` | `--port=INTEGER` | No | RADIUS port (default: 1645) |
| `-n` | `--nas-id=STRING` | No | NAS identifier |
| `-N` | `--nas-ip-address=STRING` | No | NAS IP address |
| `-c` | `--calling-station-id=STRING` | No | Calling station identifier |
| `-e` | `--expect=STRING` | No | Expected reply attribute string |
| `-r` | `--retries=INTEGER` | No | Number of retries (default: 1) |
| `-t` | `--timeout=INTEGER` | No | Timeout in seconds |

---

## 44. check_real
**Purpose**: Check REAL/RTSP streaming server
**Output Format (OK)**: `REAL {state} - {N} second response time`
**Performance Data**: None
**Status Keywords**: REAL (OK path only)

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname of the RealServer |
| `-u` | `--url=STRING` | **Yes** | URL of the content to check |
| `-I` | `--IPaddress=STRING` | No | IP address (overrides DNS for hostname) |
| `-p` | `--port=INTEGER` | No | RTSP port (default: 554) |
| `-e` | `--expect=STRING` | No | Expected string in RTSP response |
| `-w` | `--warning=DOUBLE` | No | Warning response time (seconds) |
| `-c` | `--critical=DOUBLE` | No | Critical response time (seconds) |
| `-t` | `--timeout=INTEGER` | No | Timeout in seconds |

---

## 45. check_rpc (Perl) — `plugins-scripts/`
**Purpose**: Check RPC program availability via rpcinfo
**Output Format (OK)**: `OK: RPC program {name} version {N} {tcp/udp} running`
**Output Format (CRITICAL)**: `CRITICAL: RPC program {name} version {N} {tcp/udp} is not running`
**Performance Data**: None
**Status Keywords**: OK, CRITICAL, UNKNOWN

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname or IP |
| `-C` | `--command=STRING` | **Yes** | RPC program name or number to check |
| `-c` | `--progver=STRING` | No | RPC program version(s) to check |
| `-p` | `--port=INTEGER` | No | Port to check |
| `-u` | `--udp` | No | Check UDP |
| `-t` | `--tcp` | No | Check TCP |

---

## 46. check_sensors (Bash) — `plugins-scripts/`
**Purpose**: Check hardware sensor status via lm_sensors
**Output Format (OK)**: `SENSORS OK`
**Output Format (CRITICAL)**: `SENSOR CRITICAL - Sensor alarm detected!`
**Output Format (UNKNOWN)**: `SENSORS UNKNOWN - command not found (did you install lmsensors?)`
**Performance Data**: None
**Status Keywords**: SENSORS OK, SENSOR CRITICAL, SENSOR UNKNOWN

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-i` | `--ignore-fault` | No | Treat FAULT sensor readings as OK |

---

## 47. check_smtp
**Purpose**: Check SMTP server connection
**Output Format**: `SMTP {OK|WARNING|CRITICAL} - {N}.{N} sec. response time | time={N}s;{warn};{crit};0;`
**Performance Data**: `time={N}s;{warn};{crit};0;`
**Status Keywords**: SMTP OK, SMTP WARNING, SMTP CRITICAL, SMTP UNKNOWN

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname of the SMTP server |
| `-p` | `--port=INTEGER` | No | SMTP port (default: 25) |
| `-w` | `--warning=DOUBLE` | No | Warning response time (seconds) |
| `-c` | `--critical=DOUBLE` | No | Critical response time (seconds) |
| `-e` | `--expect=STRING` | No | Expected string in SMTP banner (default: 220) |
| `-C` | `--command=STRING` | No | SMTP command to send (repeatable) |
| `-R` | `--response=STRING` | No | Expected response to command (repeatable) |
| `-f` | `--from=STRING` | No | FROM address for MAIL command |
| `-F` | `--fqdn=STRING` | No | FQDN for HELO/EHLO (default: localhost) |
| `-A` | `--authtype=STRING` | No | SMTP auth type (LOGIN, PLAIN, etc.) |
| `-U` | `--authuser=STRING` | No | SMTP auth username |
| `-P` | `--authpass=STRING` | No | SMTP auth password |
| `-s` | `--ssl` | No | Use implicit SSL/TLS |
| `-S` | `--starttls` | No | Use STARTTLS |
| N/A | `--sni` | No | Enable SNI for TLS |
| `-D` | `--certificate=INTEGER` | No | Warn if SSL cert expires in fewer than N days |
| `-L` | `--lmtp` | No | Use LMTP instead of SMTP |
| `-q` | `--ignore-quit-failure` | No | Ignore QUIT command failures |
| `-r` | `--proxy` | No | Use PROXY protocol |
| `-4` | `--use-ipv4` | No | Force IPv4 |
| `-6` | `--use-ipv6` | No | Force IPv6 |
| `-t` | `--timeout=INTEGER` | No | Timeout in seconds |

---

## 48. check_snmp
**Purpose**: Check remote machines via SNMP
**Output Format**: `SNMP {OK|WARNING|CRITICAL} - {label}={value} {label}={value} ...`
**Performance Data**: `{label}={value};{warn};{crit}` (per OID)
**Status Keywords**: SNMP OK, SNMP WARNING, SNMP CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname or IP |
| `-o` | `--oid=OID` | **Yes** | SNMP OID to query (repeatable) |
| `-C` | `--community=STRING` | No | SNMP community string (default: public) |
| `-p` | `--port=INTEGER` | No | SNMP port (default: 161) |
| `-w` | `--warning=RANGE` | No | Warning threshold range |
| `-c` | `--critical=RANGE` | No | Critical threshold range |
| `-s` | `--string=STRING` | No | Expected string in OID value |
| `-r` | `--regex=REGEX` | No | Regex to match against OID value |
| `-R` | `--eregi=REGEX` | No | Case-insensitive regex |
| `-l` | `--label=STRING` | No | Label for output (one per OID) |
| `-u` | `--units=STRING` | No | Units string for output |
| `-d` | `--delimiter=STRING` | No | Delimiter between OID values (default: !) |
| `-D` | `--output-delimiter=STRING` | No | Delimiter for multi-value output |
| `-P` | `--protocol=VERSION` | No | SNMP protocol version (1, 2c, 3; default: 1) |
| `-m` | `--miblist=STRING` | No | Colon-separated list of MIB modules to load |
| `-n` | `--next` | No | Use snmpgetnext instead of snmpget |
| `-N` | `--context=STRING` | No | SNMPv3 context name |
| `-L` | `--seclevel=STRING` | No | SNMPv3 security level (noAuthNoPriv, authNoPriv, authPriv) |
| `-U` | `--secname=STRING` | No | SNMPv3 username |
| `-a` | `--authproto=STRING` | No | SNMPv3 auth protocol (MD5, SHA) |
| `-A` | `--authpasswd=STRING` | No | SNMPv3 auth password |
| `-x` | `--privproto=STRING` | No | SNMPv3 priv protocol (DES, AES) |
| `-X` | `--privpasswd=STRING` | No | SNMPv3 priv password |
| `-e` | `--retries=INTEGER` | No | Number of retries |
| `-O` | `--perf-oids` | No | Include OID names in perfdata |
| N/A | `--strict` | No | Use strict checking |
| N/A | `--rate` | No | Calculate rate of change |
| N/A | `--rate-multiplier=FLOAT` | No | Multiply rate by this value |
| N/A | `--offset=FLOAT` | No | Add offset to returned value |
| N/A | `--multiplier=FLOAT` | No | Multiply returned value by this |
| N/A | `--invert-search` | No | Invert string/regex match |
| `-4` | `--ipv4` | No | Force IPv4 |
| `-6` | `--ipv6` | No | Force IPv6 |
| `-t` | `--timeout=INTEGER` | No | Timeout in seconds |

---

## 49. check_ssl_validity (Perl) — `plugins-scripts/`
**Purpose**: Check SSL certificate validity, expiration, and revocation
**Output Format (expired)**: `CRITICAL: Certificate expired {N.N} days ago`
**Output Format (expiring warning)**: `WARNING: Certificate expiring in {N.N} days...`
**Output Format (hostname mismatch)**: `CRITICAL: Host {vhost} not found in certificate`
**Performance Data**: None
**Status Keywords**: OK, WARNING, CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--cert-hostname=STRING` | **Yes** | Hostname to verify in the certificate's CN/SAN |
| `-I` | `--ip=STRING` | No | IP address or hostname to connect to (if different from -H) |
| `-p` | `--port=INTEGER` | No | Port to connect to (default: 443) |
| `-w` | `--warning=INTEGER` | No | Warn if certificate expires in fewer than N days |
| `-c` | `--critical=INTEGER` | No | Critical if certificate expires in fewer than N days |
| `-C` | `--crl-cache-frequency=INTEGER` | No | CRL cache update frequency in seconds |
| `-o` | `--ocsp` | No | Check OCSP revocation status |
| N/A | `--ocsp-host=STRING` | No | Override OCSP responder host |
| `-t` | `--timeout` | No | Enable connection timeout |
| `-d` | `--debug` | No | Enable debug output |

---

## 50. check_ssh
**Purpose**: Check SSH server connection
**Output Format**: `SSH OK - {server_banner} (protocol {proto}) | time={N}s;{warn};{crit};0;0`
**Performance Data**: `time={N}s;{warn};{crit};0;0`
**Status Keywords**: SSH OK, SSH CRITICAL, SSH UNKNOWN (never WARNING)

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname or IP address |
| `-p` | `--port=INTEGER` | No | SSH port (default: 22) |
| `-r` | `--remote-version=STRING` | No | Expected remote server version string |
| `-P` | `--remote-protcol=STRING` | No | Expected remote protocol version |
| `-t` | `--timeout=INTEGER` | No | Seconds before plugin times out |
| `-4` | `--use-ipv4` | No | Force IPv4 |
| `-6` | `--use-ipv6` | No | Force IPv6 |

---

## 51. check_swap
**Purpose**: Check swap space usage
**Output Format**: `SWAP {OK|WARNING|CRITICAL} - {N}% free ({N} MB out of {N} MB)`
**Performance Data**: `swap={N}MB;{warn};{crit};0;{total}`
**Status Keywords**: SWAP OK, SWAP WARNING, SWAP CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-w` | `--warning=INTEGER%` | **Yes** | Warning threshold (% free or absolute size) |
| `-c` | `--critical=INTEGER%` | **Yes** | Critical threshold (% free or absolute size) |
| `-a` | `--allswaps` | No | Check all swap partitions individually |
| `-n` | `--no-swap=ok\|warning\|critical\|unknown` | No | Return this state if no swap is configured |

---

## 52. check_tcp
**Purpose**: Check TCP port connectivity
**Output Format**: `TCP {OK|WARNING|CRITICAL} - {N}.{N} second response time on {host} port {port} [{status}]`
**Performance Data**: `time={N}s;{warn};{crit};0;{timeout}`
**Status Keywords**: TCP OK, TCP WARNING, TCP CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname or IP address |
| `-p` | `--port=INTEGER` | **Yes** | TCP port to connect to |
| `-w` | `--warning=DOUBLE` | No | Warning response time (seconds) |
| `-c` | `--critical=DOUBLE` | No | Critical response time (seconds) |
| `-s` | `--send=STRING` | No | String to send to the server |
| `-e` | `--expect=STRING` | No | Expected string in response (repeatable) |
| `-A` | `--all` | No | All `--expect` strings must be found |
| `-q` | `--quit=STRING` | No | String to send to close the connection |
| `-r` | `--refuse=ok\|warn\|crit` | No | How to handle connection refused (default: crit) |
| `-M` | `--mismatch=ok\|warn\|crit` | No | How to handle response mismatch (default: warn) |
| `-m` | `--maxbytes=INTEGER` | No | Close connection once N bytes are received |
| `-d` | `--delay=INTEGER` | No | Seconds to wait before sending data |
| `-E` | `--escape` | No | Enable `\n`, `\r`, `\t` in send/quit strings |
| `-j` | `--jail` | No | Hide output from the server |
| `-C` | `--critical-codes=STRING` | No | Comma-separated critical status codes |
| `-W` | `--warning-codes=STRING` | No | Comma-separated warning status codes |
| `-S` | `--ssl` | No | Use SSL/TLS |
| `-D` | `--certificate=INTEGER` | No | Warn if SSL cert expires in fewer than N days |
| `-N` | `--sni=STRING` | No | SNI server name |
| `-4` | `--use-ipv4` | No | Force IPv4 |
| `-6` | `--use-ipv6` | No | Force IPv6 |
| `-t` | `--timeout=INTEGER` | No | Seconds before plugin times out |

---

## 53. check_time
**Purpose**: Check time difference with remote host
**Output Format**: `TIME {OK|WARNING|CRITICAL} - {N} second time difference | time={N}s;{warn};{crit};0; offset={N}s;{warn};{crit};0;`
**Performance Data**: `time={N}s;{warn};{crit};0; offset={N}s;{warn};{crit};0;`
**Status Keywords**: TIME OK, TIME WARNING, TIME CRITICAL, TIME UNKNOWN

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname or IP of time server |
| `-w` | `--warning-variance=INTEGER` | No | Warning time offset threshold (seconds) |
| `-c` | `--critical-variance=INTEGER` | No | Critical time offset threshold (seconds) |
| `-W` | `--warning-connect=INTEGER` | No | Warning connection time threshold |
| `-C` | `--critical-connect=INTEGER` | No | Critical connection time threshold |
| `-p` | `--port=INTEGER` | No | Port (default: 37) |
| `-u` | `--udp` | No | Use UDP instead of TCP |
| `-t` | `--timeout=INTEGER` | No | Timeout in seconds |

---

## 54. check_ups
**Purpose**: Check UPS status via NUT (Network UPS Tools)
**Output Format**: `UPS {OK|WARNING|CRITICAL} - Status={status} Utility={N}V Batt={N}% Load={N}% Temp={N}{unit} Left={N}min`
**Performance Data**: `voltage={N}V;{warn};{crit};0; battery={N}%;{warn};{crit};0;100 load={N}%;{warn};{crit};0;100 temp={N};{warn};{crit};0; left={N};{warn};{crit};0;`
**Status Keywords**: UPS OK, UPS WARNING, UPS CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname of the NUT server |
| `-u` | `--ups=STRING` | **Yes** | Name of the UPS to query |
| `-w` | `--warning=INTEGER` | No | Warning battery level % |
| `-c` | `--critical=INTEGER` | No | Critical battery level % |
| `-v` | `--variable=STRING` | No | UPS variable to check (battery.charge, etc.) |
| `-p` | `--port=INTEGER` | No | NUT server port (default: 3493) |
| `-T` | `--temperature` | No | Check UPS temperature |
| `-e` | `--extended-units` | No | Use extended units in output |
| `-t` | `--timeout=INTEGER` | No | Timeout in seconds |

---

## 55. check_uptime
**Purpose**: Check system uptime
**Output Format**: `Uptime {OK|WARNING|CRITICAL}: {N} day(s) {N} hour(s) {N} minute(s) | uptime={N};{warn};{crit};0;0`
**Performance Data**: `uptime={N};{warn};{crit};0;0`
**Status Keywords**: Uptime OK, Uptime WARNING, Uptime CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-w` | `--warning=RANGE` | No | Warning uptime range |
| `-c` | `--critical=RANGE` | No | Critical uptime range |
| `-u` | `--timeunit=STRING` | No | Time unit for thresholds: seconds (default), minutes, hours, days |
| `-t` | `--timeout=INTEGER` | No | Timeout in seconds |

---

## 56. check_users
**Purpose**: Check number of logged-in users
**Output Format**: `USERS {OK|WARNING|CRITICAL} - {N} users currently logged in | users={N};{warn};{crit};0;`
**Performance Data**: `users={N};{warn};{crit};0;`
**Status Keywords**: USERS OK, USERS WARNING, USERS CRITICAL

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-w` | `--warning=INTEGER` | **Yes** | Warning user count threshold |
| `-c` | `--critical=INTEGER` | **Yes** | Critical user count threshold |

---

## 57. check_wave (Perl) — `plugins-scripts/`
**Purpose**: Check wireless signal strength via SNMP (WaveLAN/Intersil)
**Output Format**: `Signal Strength at: {N}%, SNR at {N}%`
**Performance Data**: None
**Status Keywords**: OK, WARNING, CRITICAL
**Notes**: SNMP OID `.1.3.6.1.4.1.74.2.21.1.2.1.8.1`

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-H` | `--hostname=STRING` | **Yes** | Hostname or IP of the WaveLAN device |
| `-w` | `--warning=INTEGER` | **Yes** | Warning signal strength threshold (%) |
| `-c` | `--critical=INTEGER` | **Yes** | Critical signal strength threshold (%) |

---

## 58. check_file_age (Perl) — `plugins-scripts/`
**Purpose**: Check age and/or size of a file
**Output Format**: `FILE_AGE {OK|WARNING|CRITICAL|UNKNOWN}: {filename} is {N} seconds old and {N} bytes`
**Performance Data**: `age={N}s;{warn};{crit} size={N}B;{warnsize};{critsize}`
**Status Keywords**: FILE_AGE OK, FILE_AGE WARNING, FILE_AGE CRITICAL, FILE_AGE UNKNOWN

**Arguments**:
| Flag | Long Option | Required | Description |
|------|-------------|----------|-------------|
| `-f` | `--file=STRING` | **Yes** | Path to the file to check |
| `-w` | `--warning-age=FLOAT` | No | Warning if file is older than N seconds |
| `-c` | `--critical-age=FLOAT` | No | Critical if file is older than N seconds |
| `-W` | `--warning-size=FLOAT` | No | Warning if file size is less than N bytes |
| `-C` | `--critical-size=FLOAT` | No | Critical if file size is less than N bytes |
| `-i` | `--ignore-missing` | No | Return OK if file does not exist |

---

# Performance Data Format Summary

Most plugins follow the standard Nagios performance data convention:
```
label=value[unit];[warn];[crit];[min];[max]
```
with `warn`/`crit`/`min`/`max` frequently left empty rather than populated — many
plugins omit the `min` and/or `max` field entirely. Treat trailing fields as optional.

**check_flexlm is a documented exception**: it uses `:` as the label/value separator
instead of `=` (`flexlm::up:{N};down:{N}`). A parser built only around `label=value`
will silently drop this plugin's performance data.

Multiple data points are separated by spaces:
```
label1=value1;warn1;crit1;min1;max1 label2=value2;warn2;crit2;min2;max2
```

## Common Performance Metrics by Category

### Network/Connectivity
- `time` - Response time in seconds
- `rta` - Round-trip time in milliseconds
- `pl` / `loss` - Packet loss percentage
- `jitter` - Network jitter in milliseconds
