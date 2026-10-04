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
- [Historical test failures](historical/TEST_FAILURES.md): previous findings;
  historical counts are not the current collection inventory.

The [test guide](../README.md) separates isolated tests, live integration tests,
and opt-in end-to-end tooling. Existing harness improvements do not satisfy the
complete proposed deterministic approach.
