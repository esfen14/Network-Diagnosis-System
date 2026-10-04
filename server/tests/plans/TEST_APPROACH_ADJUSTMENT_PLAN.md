# Deterministic Browser-to-Nagios Core Tests

**Status:** Proposed — implementation deferred pending fixes

**Recorded:** 2026-10-04 (Asia/Manila)

**Document type:** Proposed adjustment to the testing approach

## Summary

Replace AI-coordinated live testing with an unattended runner that exercises
Pinpoint through its browser UI, verifies actual Nagios execution, injects
controlled failures, restores the disposable lab, and generates a complete
acceptance report. The agreed boundary is **browser → application → Nagios**.

Agreed decisions:

- Cover the core suite first; extended profiles remain gated on core acceptance.
- Build missing UI workflows before claiming browser coverage.
- Run against a dedicated disposable Pinpoint/Nagios instance and disposable targets.
- Require no AI decisions or repairs after launch. AI may investigate the completed report afterward.

Existing product defects must produce failures. Fixing them is separate from
changing tests to expose them. The current harness improvements (plugin enabling,
application verification, fresh checks and runtime provenance) do **not** yet
satisfy this proposed approach. Saving this plan and reorganizing the test tree
does not implement the runner or the missing UI workflows.

Keep the [extended live-test plan](NETWORK_DISCOVERY_EXTENDED_TEST_PLAN.md)
separate. Existing live tools are under `../e2e/network_discovery/`.

## 1. Complete the Application Workflows

Extend Device Inventory with a discovery view alongside its existing monitoring
view. Show stable device identity, discovered ports, suggested/monitored states,
scan counters, and service monitoring results.

Add permission-controlled UI actions for:

- Promoting discovered ports, ignoring ports, and excluding devices using existing backend operations.
- Configuring per-device discovery plugin variables, including MySQL user/database and SNMP settings.
- Fetching and displaying SSH fingerprints, explicitly confirming trust, starting/cancelling NCPA deployment, and displaying progress and terminal errors.
- Viewing individual services and their live states so browser assertions can verify failure and recovery.

Reuse existing APIs wherever available. Add these missing interfaces:

- Paginated `GET /api/system/hosts` for discovery inventory.
- `GET /api/system/hosts/<id>/ports` for discovered ports and lifecycle metadata.
- `GET/PUT /api/system/hosts/<id>/plugin-variables` for registry-supported variables.

Use `system.hosts` for discovery reads and `system.hosts.edit` for changes;
retain `system.deploy.ncpa` for deployment. Validate variables through the plugin
registry, redact secret values from reads, and regenerate/validate/apply
monitoring through the existing configuration pipeline.

Do not add endpoints that directly set plugin status, simulate Nagios success,
or insert discovered hosts for testing. Update the owning backend, frontend,
data, and implementation-status specifications with these workflows.

## 2. Build One Deterministic Runner

Extend the existing live harness with:

```text
run-suite --profile core --config <lab> --cases <manifest> --run-id <id>
recover --run-id <id>
```

Use Python Playwright with a pinned Chromium browser, page objects, accessible
selectors, and isolated browser sessions. See the
[official Python Playwright documentation](https://playwright.dev/python/docs/intro).

The runner executes a fixed sequence:

1. Validate configuration, required permissions, executable availability, network isolation, pinned SSH identities, browser dependencies, and recovery access.
2. Verify the approved baseline and restore the dedicated test instances.
3. Run the existing isolated regression gate.
4. Log in through the browser.
5. Enable required plugins through Plugin Manager.
6. Configure discovery settings, start discovery, and verify progress through the UI.
7. Inspect discovered devices, configure variables, and promote required suggested ports through the UI.
8. Confirm pinned fingerprints and deploy NCPA through the UI.
9. Verify monitoring objects, Plugin Manager application, and service states.
10. Execute controlled failure/recovery and lifecycle cases.
11. Restore the lab, verify restoration, and finalize the report.

User-facing acceptance actions must use UI controls. Direct API requests are
permitted only for explicitly labelled authorization/invalid-request tests and
read-only verification. Shell/SSH operations control disposable fixtures and
fault injection; they must not perform the application workflow being tested.

Manifest entries define case ID, dependencies, target, exact expected services
and commands, action, expected outcome, timeout, and recovery operation. Validate
the entire manifest before making changes. Run sequentially with one lab lock
and fixed ordering.

## 3. Enforce Reliable Evidence and Recovery

A passing service case requires agreement between:

- Target listener state.
- Discovery records and monitoring configuration.
- Loaded Nagios command and executable.
- A positive, fresh Nagios execution timestamp and expected state.
- Pinpoint's stored result.
- The rendered browser state.

Require the complete expected metric set; prefix matching alone cannot pass
SNMP or NCPA acceptance. Generic TCP fallback cannot satisfy a MySQL or NCPA case.
UNKNOWN fails ordinary service-outage acceptance but remains valid in the
explicitly defined `check_dummy` UNKNOWN case.

Use bounded polling instead of fixed readiness sleeps. Do not automatically
retry failed acceptance actions. Record failures, restore the case baseline,
and continue independent cases; mark dependent cases Blocked.

Capture recovery operations before each mutation. Restore the complete
disposable application/Nagios and guest baselines after cases that cannot be
reversed safely through existing APIs. Snapshot restoration is lab cleanup,
never evidence of successful product rollback.

Persist the execution journal and sanitized evidence outside restored instances.
On interruption, leave the case incomplete and run recovery. Resuming restores
the baseline and reruns necessary dependencies; it never reuses stale passing
results.

Prohibit during acceptance:

- Direct database writes or fabricated host/service records.
- Temporary permission seeding to overcome installation failures.
- Guest chmod/restart repairs to overcome failed NCPA deployment.
- Direct Nagios reloads to rescue an application reload failure.
- Mocked application responses, browser request fulfillment, or substituted plugins.

## 4. Core Scenarios and Reporting

Automate the existing core case IDs with explicit assertions:

- Discovery settings validation, concurrency, cancellation, unchanged scans, new listeners, and ownership of ports.
- Suggested-port promotion, exclusion/filtering, closed-port thresholds, missing hosts, and reappearance.
- Every core service family's healthy, failed, and recovered state.
- Plugin enable/apply/running, multiple targets, idempotent reapplication, and rejection of non-enabled plugins.
- NCPA pinned trust, actual fingerprint mismatch, deployment, listener stability, terminal metadata, and CPU/memory/every expected disk metric.
- Protocol-faithful unsupported UDP discovery and skipped-service handling.
- Configuration validation and application rollback under controlled reload failure.
- `check_dummy` OK/WARNING/CRITICAL/UNKNOWN transitions.
- Browser permission restrictions, direct API authorization checks, and sanitized evidence.

Use an independent scheduled recovery safeguard for SSH outages. Fault injection
must be explicitly declared and isolated to the disposable instance. Report
helper-level fault tests separately from browser acceptance and real daemon
rollback.

Test normal missing-scan thresholds with real successive scans. Test time-based
retirement/archive in a separately labelled disposable profile with zero-day
retention configured before startup. Verify production defaults through isolated
tests; do not claim the accelerated profile proves 30 days elapsed.

Require a result for every required case. Missing, Failed, Blocked, interrupted,
or cleanup-failed cases prevent overall acceptance. Extended profiles cannot
start until core passes. Selecting an individual case produces a partial report,
never full-suite acceptance.

Reports include tested commit, manifest/baseline hashes, effective timings and
lifecycle settings, case results, sanitized evidence references, and cleanup
verification. Keep credentials, cookies, raw databases, private keys, and
secret-bearing traces out of exported artifacts.

## 5. Delivery and Acceptance

Implement in this order: missing UI/API workflows, baseline/recovery support,
orchestration, browser scenarios, then reporting enforcement.

Validate with:

- Backend tests for new interfaces, permissions, validation, and apply failures.
- Frontend tests/build for the new controls and states.
- Harness self-tests for dependency ordering, missing cases, stale checks, plugin fallback rejection, interruption, and cleanup failure.
- Two consecutive unattended runs from the same verified baseline.

Acceptance requires both runs to execute the same case set and produce
consistent classifications without prompts, AI repairs, or hidden omissions.
Existing defects may yield consistent failures; they must remain visible until
separately fixed and retested.

One-time administrator preparation remains necessary for credentials, pinned
fingerprints, lab ownership, and baseline creation. After that preparation and
an explicit launch, the runner owns execution, recovery, and reporting.
