# Test plans and approach

- [Test Approach Adjustment Plan](TEST_APPROACH_ADJUSTMENT_PLAN.md): proposed
  deterministic browser-to-Nagios core acceptance; implementation is deferred
  pending product fixes. This is an approach proposal, not an implemented runner.
- [Network Discovery Extended Test Plan](NETWORK_DISCOVERY_EXTENDED_TEST_PLAN.md):
  existing live-lab scenarios and operational constraints, retained separately.
- [NCPA, SSH-Port and Service-Identification Lab Test Plan](NCPA_PORTS_AND_SERVICE_IDENTIFICATION_LAB_TEST_PLAN.md):
  manual live-lab cases for the per-device SSH port, the configurable NCPA port,
  fingerprint-based service identification and the NCPA deployment page. It adds
  only cases the extended plan does not have and says which existing cases to
  repeat.
- [Plugin-Driven Monitoring Lab Test Plan](PLUGIN_DRIVEN_MONITORING_LAB_TEST_PLAN.md):
  manual live-lab cases for Plugin Manager as the monitoring switch: upgrade of a real database,
  enable/disable/stop/resume against a real Nagios, rejected configs, NCPA with `check_ncpa` off,
  `localhost.cfg` left alone, and the pages in a browser.
- [Plugin-Driven Monitoring Acceptance Test Plan](PLUGIN_DRIVEN_MONITORING_ACCEPTANCE_TEST_PLAN.md):
  lab acceptance cases with expected results that judge the monitoring logic, the ports UI,
  permissions and the system's objectives, with traceability and the e2e harness work still
  needed. It supersedes the Extended plan's PM-01..PM-05.
- [Plugin-Driven Monitoring E2E Harness Adjustment Plan](PLUGIN_DRIVEN_MONITORING_HARNESS_ADJUSTMENT_PLAN.md):
  proposed changes to `e2e/network_discovery/` so the acceptance cases run without hand steps: drop the
  removed apply flow, add the new route calls, localhost/preview guards, scenario runner, permission
  matrix and traceability reporting. Nothing in it is implemented yet.
- [Historical test failures](historical/TEST_FAILURES.md): previous findings;
  historical counts are not the current collection inventory.

The [test guide](../README.md) separates isolated tests, live integration tests,
and opt-in end-to-end tooling. Existing harness improvements do not satisfy the
complete proposed deterministic approach.
