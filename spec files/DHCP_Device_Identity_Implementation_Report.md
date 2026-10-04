# Implementation Report: DHCP Device Identity and Port Handling

**Branch:** `revisions` (from `installer-connection` @ `0910a333`)
**Implements:** `DHCP_Device_Identity_Plan.md`
**Scope touched:** `server/` only (back-end, migration, tests). No front-end changes.
**Status:** Phases 0, 1, 2, 3 and the back-end half of Phase 4 are implemented and tested. The Device Inventory UI (rest of Phase 4) and NRDP (Phase 5) are not. See [section 5](#5-what-was-not-done).

---

## 1. What happened, in short

A device used to be identified by its IP address in several places. When a DHCP lease changed, the next scan could create a duplicate device, keep checking the old IP, or attach one device's history to another. One missed scan also deleted a port and its Nagios services.

This branch separates a device's **identity** from its **IP** and gives **ports** a lifecycle:

- A scan now only reports what it saw. A new reconciler decides which known device each result is, using evidence that survives a lease change (NCPA certificate, SSH host key, machine-id, hardware MAC). It never merges two devices on weak evidence; ambiguous cases become review items.
- Each device gets a Nagios `host_name` chosen once at creation and never derived from its IP, so `history.db`, acknowledgements and graphs survive an IP change.
- Ports move through `SUGGESTED / MONITORED / MISSING / ARCHIVED / IGNORED`. A single missed scan changes nothing, monitored ports are never deleted automatically, and new ports are suggestions unless their service is on an auto-monitor list.
- NCPA devices are recognised by TLS certificate across subnets, and a scheduled job finds an NCPA device that moved between full scans.
- The three bugs listed in the plan's Phase 0 are fixed.

## 2. Plan coverage

| Plan item | Status | Notes |
|---|---|---|
| Phase 0: fix current bugs | Done | All three; see 3.2 |
| Phase 1: identity, reconciler, stable host names, lifecycle, config-write lock | Done | Matching rules implemented as in section 4 of the plan |
| Phase 2: NCPA identity at deployment, persistent cert, token reuse, TLS fingerprint in scans, relocation job | Done in code, **not run against a real device** | See section 5 |
| Phase 3: port lifecycle, upserts, hysteresis, auto-monitor list, frozen plugin, ephemeral filter, NCPA port protection, skip-apply-when-unchanged | Done | Plan rule 8 (dashboard alert collapsing) not done; see section 5 |
| Phase 4: routes | Done | Plus two small routes the plan implies; see 4.3 |
| Phase 4: Device Inventory UI | **Not done** | `AGENTS.md` section 9 requires `Display_Requirements.md` to be updated first |
| Phase 5: NRDP | **Not done** | Plan marks it optional, to be decided after Phase 2 is in use |

## 3. Changes: where, what, and why

### 3.1 Database (`server/app/system_models.py`, `server/migrations/versions/d41f7a2b9e10_...py`)

All new tables are application data, so they live in `system.db` (not `history.db`), as `AGENTS.md` requires.

| Change | Why |
|---|---|
| `NetworkDiscovery` gains `Nagios_Host_Name` (unique), `Display_Name`, `Addressing`, `Identity_Confidence`, `Device_State`, `First_Seen_At`, `Last_Seen_At`, `Missed_Scans`, `Merged_Into_ID` | Separates identity from IP; `IP_Address` now always means "current address" |
| New `DeviceIdentifier` (unique on `(Kind, Value)` **only for strong identifiers**, via a partial index) | One key can never belong to two devices, but two devices may share a weak one such as the same DNS name |
| New `DeviceAddressHistory` | "IP changed from X to Y at T"; one open row per device |
| New `DeviceReviewItem` | **Addition to the plan.** The `GET /system/discover/review` route needs somewhere to keep conflicts, IP reuse, etc. until a user deals with them |
| `Open_TCP_Services` / `Open_UDP_Services` gain `Port_State`, `Source`, `Plugin_Name`, `Observed_Service_Name`, `First_Seen_At`, `Last_Seen_At`, `Closed_At`, `Missed_Scans`, and a unique `(NetDiscoveryID, Port_Number)` | Port lifecycle; saves become upserts. `Observed_Service_Name` is an **addition** so a changed nmap guess can be shown as a suggestion without renaming the monitored service |
| Enums: `AddressingMode`, `IdentityConfidence`, `DeviceState`, `IdentifierKind`, `AddressSource`, `ReviewKind`, `PortState`, `PortSource` | `AGENTS.md`: every fixed-value field is an Enum |

**Migration `d41f7a2b9e10`** (down from `c3610bb0fc54`; `history.db` untouched):

- Existing `Nagios_Host_Name` = existing `Hostname`, including `<ip>.<domain>` names, so existing history and acknowledgements stay attached. Duplicate names get `-2`, `-3` (problem E) instead of failing the unique constraint.
- Existing ports become `MONITORED`; duplicate `(device, port)` rows are collapsed first (oldest kept) so the unique constraint can be created. Port 5693 on a device with a deployed token becomes `Source = NCPA`.
- Existing hardware MACs and SSH fingerprints become `DeviceIdentifier` rows (randomized MACs are skipped; a value two rows share stays on the first device only).
- Each device gets one open address row. Confidence is `VERIFIED` with a fingerprint, `LIKELY` with a hardware MAC, otherwise `UNVERIFIED`.
- Downgrade is implemented and tested.

### 3.2 Phase 0: bugs fixed in the old save code

| Bug (plan section 2) | Fix | Where |
|---|---|---|
| A MAC match never updated `IP_Address` | `apply_match` updates IP and network and records the change | `device_identity.py` |
| Update branch reset `NCPA_Eligible` on every rescan | Eligibility is only set when NCPA records are first created; a rescan never touches it, so "incompatible" is not undone either | `device_identity.ensure_ncpa_records` |
| `SSH_Port = int(port_number)` used before assignment (`UnboundLocalError` on the first new Linux host) | Uses the standard SSH port (`SSH_PORT`, default 22) | `device_identity.ensure_ncpa_records` |

Related hardening found while doing this: a failed OS detection (`Unknown`) no longer overwrites a known OS, and a routed (MAC-less) rescan no longer wipes a stored MAC.

### 3.3 New modules (`server/app/network_discovery/`)

| File | Role | Why it is separate |
|---|---|---|
| `device_identity.py` | The reconciler: `resolve_observation` (read-only decision), `reconcile_scan` (two passes), stable host names, address history, identifiers, review items, lifecycle sweep | A scan observes, a reconciler decides (plan principle). Pass one is read-only so the result cannot depend on scan order |
| `port_lifecycle.py` | Upsert, hysteresis, auto-monitor, frozen plugin, ephemeral filter, NCPA protection, user state changes | Keeps port rules out of the scan-saving code |
| `identity_probes.py` | TLS certificate fingerprint and SSH host-key fingerprint | Read-only probes. The TLS probe completes a handshake and sends no data, so **no NCPA token is ever sent to an unknown host** (plan principle 3) |
| `ncpa_relocation.py` | The relocation job | Plan section 7 |

**How matching works** (plan section 4, implemented in `resolve_observation`):

1. Strong identifiers (NCPA certificate, machine-id, SSH host key) point to **one** device: same device, `VERIFIED`, unless another strong identifier contradicts it (then a conflict).
2. They point to **two** devices: conflict, no merge, review item.
3. Only a hardware MAC matches: same device, `LIKELY`, unless a strong identifier contradicts it (then "identity changed", e.g. OS reinstall).
4. Same IP as a known device but an identifier or MAC contradicts it: IP reuse. New device; the old one becomes `ADDRESS_UNKNOWN`.
5. Same IP, nothing contradicting: same device, confidence unchanged.
6. Nothing matches: new device.

Randomized (locally administered) MACs are treated as no MAC. In the "ambiguous" outcomes a new device is still created, so the host keeps being monitored; the review item lists the candidates so a user can merge.

### 3.4 Changes to existing files

| File | Change | Why |
|---|---|---|
| `network_discovery/create_host_cfg.py` | `_save_discovered_hosts` rewritten to use the reconciler and port lifecycle; `_create_hostname` replaced by `_collect_identifiers` (no more `<ip>.<domain>` names); `_load_monitored_hosts` loads by device and port state and uses the stable name; `config_write_lock` (re-entrant) around load, generate, validate and apply in both `discover_network_create_hosts` and `add_ncpa_port`; `config_unchanged` skips validate/apply/reload when only the timestamp differs; new `regenerate_and_apply_config()` for relocation and user edits; `add_ncpa_port` uses `mark_ncpa_port` | Plan sections 8, 9, 10. The lock stops discovery, NCPA deployment, relocation and user edits overwriting each other's `hosts.cfg` |
| `network_discovery/host_config_templates.py` | Hosts/services can render `active_checks_enabled 0` and a `notes` line | `ADDRESS_UNKNOWN` devices stay in the config but are not checked, so checks never hit the wrong machine |
| `ncpa_deployment/ncpa_deployment.py` | Helper script prints an `IDENTITY_BEGIN/END` block (machine-id, hardware MACs, hostname) and uses a persistent self-signed certificate; `_parse_identity`, `store_deployment_identity`; token reuse on redeploy; best-effort identity storage after deployment (a failure there does not fail the deployment) | Plan section 7. The token is never printed by the helper |
| `api/system/ncpa_deployment.py` | Trust confirmation also stores the SSH host key as an identifier | The key the admin trusted is also identity evidence |
| `api/system/device_identity.py` (new) | Routes, see 4.3 | Plan section 11 |
| `api/system/__init__.py` | Registers the new routes | |
| `api/plugin/service.py`, `api/system/report.py` | Use `nagios_host_name(device)` instead of `Hostname` | These must match the name Nagios and `history.db` use; otherwise plugin services and the hosts-by-OS report would point at a name that no longer exists |
| `scheduler.py` | Adds the `ncpa_relocation` job (interval `NCPA_RELOCATE_MINUTES`) | Plan section 7 |
| `api/commands/seed.py` | New permission `system.hosts.edit` | Plan section 11 |
| `config.py` | New settings from plan section 12 | Kept in `config.py` (not `SystemSettings`), the plan allowed either |
| `conftest.py`, `tests/unit/test_create_host_cfg.py` | Test permissions; one assertion updated because loaded services now carry `plugin_name` | |

### 3.5 Routes (`server/app/api/system/device_identity.py`)

| Route | Permission | Purpose |
|---|---|---|
| `GET /system/hosts/<id>/addresses` | `system.hosts` | Address history |
| `GET /system/hosts/<id>/identifiers` | `system.hosts` | Evidence, confidence, recommendation for Unverified devices. Machine-id is returned masked |
| `PUT /system/hosts/<id>` | `system.hosts.edit` | Display name, addressing mode. Never touches Nagios |
| `POST /system/hosts/<id>/merge` | `system.hosts.edit` | Merge a duplicate into a target |
| `POST /system/hosts/<id>/retire` | `system.hosts.edit` | Retire |
| `PUT /system/hosts/<id>/ports/<proto>/<port>` | `system.hosts.edit` | Change port state; can also add a port by hand (**addition**, needed so ephemeral-range ports can be monitored) |
| `GET /system/discover/review` | `system.discover` | Unresolved review items |
| `POST /system/discover/review/<id>/resolve` | `system.hosts.edit` | **Addition**: without it a review item could never leave the list |

Every change writes an activity-log entry. Merge, retire and port changes regenerate the Nagios config and report `config_applied` / `config_message`; if regeneration fails the database change is kept and the failure is reported, not hidden.

### 3.6 Settings (`config.py`)

`DEVICE_MISSING_AFTER_SCANS=5`, `DEVICE_RETIRE_AFTER_DAYS=30`, `PORT_MISSING_AFTER_SCANS=5`, `PORT_ARCHIVE_AFTER_DAYS=30`, `AUTO_MONITOR_SERVICES=["ssh","http","https","snmp","ncpa"]`, `EPHEMERAL_PORT_RANGES=[(32768,60999),(49152,65535)]`, `NCPA_RELOCATE_MINUTES=5`. Defaults are the plan's.

## 4. Decisions where the plan was silent or ambiguous

These are worth a second look in review.

1. **Weak identifiers.** The plan makes `(Kind, Value)` unique "for strong kinds". Implemented as a partial unique index so DNS names (weak) can repeat.
2. **A MAC is not a "strong identifier" for matching**, only for uniqueness. It gives `LIKELY`, as the plan's confidence table says.
3. **Several results resolving to one device in one scan.** If the second address's MAC is already known (multi-NIC), the extra address is recorded in the history and nothing else happens. If the MAC is new, it is recorded and a `DUPLICATE_IDENTITY` review item is raised, because "second NIC" and "cloned VM" cannot be told apart from a shared host key alone. Only the first address is monitored.
4. **A device whose IP was taken by a matched device** (e.g. an unverified device whose lease was handed to someone else) becomes `ADDRESS_UNKNOWN`. The plan only described this for the explicit contradiction case.
5. **Retirement time.** There is no "state entered at" column, so `Last_Seen_At` is used for `DEVICE_RETIRE_AFTER_DAYS`.
6. **Machine-id is masked in the API.** `/etc/machine-id` is meant to stay semi-confidential. The full value is still stored for matching.
7. **`Include_Device_In_Scanning`** is still never set to `False` by anything (plan section 2 noted this). Retire uses `Device_State` instead; the old filter is kept.

## 5. What was not done

- **Device Inventory UI** (badges, address panel, grouped scan results, merge/retire actions, port tabs). The back-end routes it needs exist. `AGENTS.md` section 9 says `Display_Requirements.md` must be updated first, so I did not start it.
- **Phase 5, NRDP.**
- **Verification items from plan section 15 are still open.** In particular: the helper writes `certificate = <crt>,<key>` into `ncpa.cfg`, which I could not check against the NCPA version you install. If the key name differs the `sed` matches nothing and NCPA silently keeps its `adhoc` certificate, which would make certificate matching useless. The helper script is syntax-checked (`bash -n`) but was **not run on a real host**. Nor were the nmap sweep, the real NCPA endpoint, or a real `nagios -v` run.
- **Relocation trigger is simplified.** It looks for NCPA devices whose host is DOWN/UNREACHABLE. The plan also mentions devices whose NCPA services return auth/connection errors; that is not implemented.
- **Plan rule 8** (dashboard alerts feed collapses service alerts under a DOWN host) is not done; it is a dashboard change.
- **Automatic decisions are logged to the application log and shown as review items**, but are not written to the user-facing activity log (it requires a user, and these happen in background jobs). User-initiated changes are logged.
- `NCPA` node name as a Nagios host-name source: the hook exists (`create_stable_host_name(..., ncpa_node_name)`) but nothing supplies it yet, because it needs the `/api/system` check from plan section 15.
- Local `system.db` / `history.db` are gitignored and stamped at a revision (`fdadc5473356`) that is not in the repo, so I did **not** run the migration against them. Run it where appropriate with `flask db upgrade --multidb` (back up first).

## 6. Testing

Run from `server/` with the virtualenv active.

```bash
pytest tests/unit/test_device_identity.py tests/unit/test_port_lifecycle.py tests/unit/test_device_config.py \
       tests/unit/test_ncpa_identity.py tests/unit/test_device_identity_routes.py \
       tests/unit/test_device_name_consumers.py tests/unit/test_device_migration.py
pytest        # everything
```

### 6.1 New tests: 235

| File | Tests | What it covers |
|---|---|---|
| `test_device_identity.py` | 53 | Phase 0 regressions; one test per row of the plan's section 4 decision table (strong match, two-device conflict, contradicting identifier, MAC-only, IP reuse by MAC and by host key, same-IP-unverified, new device); randomized MAC; OS reinstall flagged not accepted; repeated review cases don't pile up; address history; static device that moves; identifier uniqueness and weak-identifier sharing; multi-NIC independent of scan order; swapped addresses; lifecycle (missed, missing, reactivated, other networks untouched, IP taken over, retired, merged); stable host names (never IP-based, duplicate DNS names, unchanged across IP change) |
| `test_port_lifecycle.py` | 32 | Auto-monitor vs suggest; ephemeral ports not recorded; no duplicates and DB constraint; one miss changes nothing, three misses go `MISSING`, sighting resets, host-not-seen changes no counters; archive timeout; archived/ignored behaviour; UDP; no row ever deleted by a scan; NCPA port protection; frozen plugin; user actions; only `MONITORED`/`MISSING` reach the config |
| `test_device_config.py` | 23 | Loader uses stable name and current address; each device state in or out of config; `ADDRESS_UNKNOWN` host and its services have `active_checks_enabled 0`; devices sharing an IP; timestamp-insensitive fingerprint; skip validate/apply/reload when unchanged; invalid config not applied; the lock is held during load/apply and a second writer waits; the full discovery flow with unchanged and changed config |
| `test_ncpa_identity.py` | 43 | Identity-block parsing; helper script content (persistent cert, no token printed, valid bash); storing identity and cloned-VM conflict; `install_ncpa` stores evidence, mints a token, **reuses** an existing token, survives an identity failure; **TLS probe against a real local TLS server** (correct SHA-256, sends no data); closed and non-TLS ports; SSH probe format matches trust confirmation; probe gating by open port; relocation (candidates, cert match, wrong cert ignored, discovery running, own address, squatter marked unknown, **no token sent**, per-network failure, sweep parsing without service/OS detection); scheduler registration and error containment |
| `test_device_identity_routes.py` | 69 | Login and permission checks for every route (including read-only users); addresses; identifiers and masking; edit validation; retire; merge (identifiers, history, ports, plugin configs, NCPA records, review items, invalid and repeated merges); port state (freeze, ignore/restore, NCPA protection, add by hand, invalid input); review list and resolve; activity-log entries |
| `test_device_name_consumers.py` | 6 | Plugin configurations and the hosts-by-OS report use the stable name; trust confirmation records the host key and flags a key another device owns |
| `test_device_migration.py` | 9 | The migration on throwaway SQLite files seeded with pre-migration rows (subprocess): names kept and de-duplicated, confidence, identifiers, address rows, ports kept monitored and duplicates collapsed, constraints enforced, `history.db` untouched, downgrade then upgrade |

Shared builders are in `tests/support/identity_helpers.py`; the migration is driven by `tests/support/migration_runner.py`. As with the existing suite, nmap, SSH and Nagios are mocked.

Bugs found by the tests while writing them, and fixed: new Linux devices were not getting their SSH/NCPA placeholder records, and plain "new device" decisions were wrongly sent through review-item creation.

### 6.2 Full suite

`1261 passed, 33 skipped, 1 failed`. Before this branch's work the same suite was `1026 passed, 33 skipped, 1 failed` (measured part-way through development, so the 235 new tests account for the difference).

The one failure, `tests/unit/test_automation.py::TestSecurityCheck::test_flags_broken_plugins_and_logs_summary`, **is not caused by this branch**: it also fails on a clean checkout of `HEAD`. It writes and executes a shell script as a "good" plugin, which cannot run on this Windows machine.

### 6.3 Not covered by automated tests

Real nmap, real SSH/NCPA hosts, a real `nagios -v` and reload, the helper script actually running, and the front-end (no UI was built).

## 7. Upgrading an existing installation

1. Back up `system.db`.
2. `cd server && flask db upgrade --multidb` (the `history.db` step is a no-op).
3. Existing devices keep their current Nagios names, so Nagios, history and acknowledgements are unaffected. Devices gain identity as scans and NCPA deployments supply evidence; until then they show as Unverified or Likely.
4. The next scan regenerates `hosts.cfg`. If it is identical to the running one, Nagios is not reloaded.
5. Re-deploying NCPA to a device now reuses its token and installs a persistent certificate, which is what enables certificate-based recognition and relocation. Already-deployed agents keep their `adhoc` certificate until redeployed.
