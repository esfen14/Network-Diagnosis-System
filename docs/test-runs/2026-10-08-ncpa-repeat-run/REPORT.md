# Test run: ncpa-repeat-run

| | |
|---|---|
| Date | 2026-10-08 |
| Commit tested | Installer `e471a1b8` (`fix/check-ncpa-python3-shebang` in `lorraine-pangilinan/PinPoint-Installer`; merged to the installer's `main` afterwards as `2859361d`); the application commit was not verified |
| Plan | Recheck the fix for issue [#45](https://github.com/esfen14/Network-Diagnosis-System/issues/45) after [`2026-10-08-ncpa-run`](../2026-10-08-ncpa-run/REPORT.md) |
| Tester | Claude Code, supervised by the project owner |
| Environment | VirtualBox VM lab, `scripts/vmlab provision --force` with a temporary configuration selecting installer `e471a1b8`. The base snapshot already contained an application installation, so this was **not** a clean appliance build |
| Raw evidence | None committed |

## Result

**Overall: Partial.** The installer fix was inspected and one real NCPA check returned OK
instead of return code 127. The fresh-install acceptance condition of #45 was **not**
established, so #45 stays open. An earlier version of this report said "Pass
(Analysis-based)"; that overstated the evidence and is withdrawn.

Totals: Pass 4, Fail 0, Blocked 3, Skipped 1 (see the table).

## Cases

| Case | Result | Notes (what was observed) | Issue |
|---|---|---|---|
| Installer fix by inspection | Pass | `setup/install-nagios-plugins.sh` rewrites the plugin's `python` interpreter line to `python3`; its verify step runs `check_ncpa.py --help` directly through `runuser -u nagios`; `setup/pinpoint-healthcheck.sh` does the same and records a failure on a nonzero exit | #45 |
| Installer run prints the new checks | Pass | `Interpreter line changed to python3`, `check_ncpa.py verified`, `Plugin interpreters verified` | #45 |
| Installed plugin's first line | Pass | `#!/usr/bin/env python3` | #45 |
| One NCPA service is no longer 127 | Pass | After enabling `check_ncpa.py` (six services applied), one NCPA CPU service was `Ok` with `OK: Percent was 0.00 %`. The other five were still waiting for their first check, so no result is recorded for them | #45 |
| Fresh deployment of an exact application commit | Blocked | Both attempts (the issue branch and `main`) failed in the installer's upgrade path with an unknown remote-tracking revision (`origin/<branch>`) | #45 |
| `scripts/vmlab ncpa` on a new deployment | Blocked | Rejected because NCPA was already deployed on both targets; `scripts/vmlab sync` was then used, so the runtime is not a verified deployment of an exact commit | #45 |
| All six NCPA services OK or at a real threshold state | Blocked | Not observed | #45 |
| Negative test: verify step and healthcheck fail when `nagios` cannot start the plugin | Skipped | Failure handling was inspected only, never run | #45 |

## Deviations from the plan

- The run could not start from a clean `scripts/vmlab fresh main`, which the finish
  condition of #45 requires.

## Follow-up

- The blocked and skipped cases above were run in [`2026-10-08-ncpa-fresh-run`](../2026-10-08-ncpa-fresh-run/REPORT.md).

- Defects found: none new. Open work stays on [#45](https://github.com/esfen14/Network-Diagnosis-System/issues/45).
- Cases to repeat in the next run: a clean `scripts/vmlab fresh main` with the installer fix
  merged; deploy NCPA; enable the plugin; confirm all six services report OK or a threshold
  state; run the negative test (make `python3` unavailable to `nagios`, expect the verify step
  and the healthcheck to fail); then commit a complete report and tick the finish conditions.

## Sanitization checklist

- [x] No passwords, tokens, keys, SNMP communities or private key paths
- [x] No addresses outside the documented lab range
- [x] Evidence is referenced by name and location, not pasted
