# Test run: ncpa-fresh-run

| | |
|---|---|
| Date | 2026-10-08 |
| Commit tested | Application `main` at `ed9f2c2` (installed by the installer's deploy step); installer `e471a1b8` (`fix/check-ncpa-python3-shebang` in `lorraine-pangilinan/PinPoint-Installer`; merged to the installer's `main` afterwards as `2859361d`, PR #2), used through `VMLAB_INSTALLER_DIR` for the base steps, the deploy step and the healthcheck; lab tooling `a424008f` |
| Plan | Remaining finish conditions of [#45](https://github.com/esfen14/Pinpoint/issues/45); follows [`2026-10-08-ncpa-run`](../2026-10-08-ncpa-run/REPORT.md) (failure found) and [`2026-10-08-ncpa-repeat-run`](../2026-10-08-ncpa-repeat-run/REPORT.md) (partial recheck) |
| Tester | Claude Code, supervised by the project owner |
| Environment | A newly created VirtualBox appliance, `pinpoint-appliance-45` (Ubuntu 22.04.5, Nagios Core 4.5.11), built with `scripts/vmlab create` and `provision`, plus the five `demo/` targets at `10.77.0.2` to `.6`. The previous appliance's snapshot already held an application install (`/opt/pinpoint`, Gunicorn running), which is why earlier fresh runs failed in the installer's upgrade path; it was left untouched and powered off. The host was short on memory (about 3 GB free with six VMs running), which slowed discovery |
| Raw evidence | Author's machine: the Claude Code session scratchpad (`provision45.log`, `fresh45.log`, `negative45.log`, `installer-neg45.log`) and `/tmp/installer-neg.log` on the appliance; not committed |

## Result

**Overall: Pass for the behavior #45 describes, with one new defect found.** On a clean
appliance built with the installer fix, the application installs fresh, NCPA deploys to two
targets, and all six NCPA services report OK with real values instead of return code 127.
The installer's verify step and the healthcheck both fail when the `nagios` user cannot start
the plugin (127, 126 and the original bug state). The fix has since been merged to the
installer's `main` (PR #2, merge `2859361d`, which contains `e471a1b8`); this run tested the
commit before the merge, not `main` itself.

Totals: Pass 9, Fail 1, Blocked 0, Skipped 0 (see the table).

## Cases

| Case | Result | Notes (what was observed; evidence file name) | Issue |
|---|---|---|---|
| Base build on a clean VM with installer `e471a1b8` (`provision`) | Pass | Printed `Interpreter line changed to python3`, `check_ncpa.py verified`, `Plugin interpreters verified` (`provision45.log`) | #45 |
| Appliance has no `python` command and the plugin starts with `python3` | Pass | `command -v python` finds nothing; first line `#!/usr/bin/env python3`. No `python-is-python3` workaround was applied, unlike in the first NCPA run | #45 |
| `scripts/vmlab fresh main` on the clean snapshot | Pass | Application `ed9f2c2` installed; healthcheck 60 passed, 0 failed, including `check_ncpa.py runs as nagios` (`fresh45.log`) | #45 |
| Discovery finds the five targets | Pass | All five monitored and Up. Deviation: the smoke script's "discovery finishes" check timed out after 300 s on two runs; the hosts were present anyway | |
| NCPA deployment to `10.77.0.2` and `10.77.0.6` | Pass | 16 of 16 checks; `Success` in 30 s; both `Deployed NCPA` | |
| Enable `check_ncpa.py` | Pass | Preview "6 service(s) on 2 device(s)"; 6 services applied, Nagios config reloaded | #45 |
| All six NCPA services report OK or a real threshold state, never 127 | Pass | Read from Nagios `status.dat`, each `current_state=0` with real output: CPU 0.00 % (both hosts), root disk 30.30 % and 28.10 %, memory about 49 % (both). The second host needed a second deployment, see the next row | #45 |
| One device record per host | **Fail** | `10.77.0.6` (`legacy01`) appeared as two records: an `Address Unknown` one that NCPA was first deployed to (its services are generated with `active_checks_enabled 0` and were never checked) and a live one. Another discovery did not merge them. NCPA was deployed again to the live record; the dead record remains. Not isolated: it may need overlapping discoveries (the smoke script's second run started a new discovery while the first may still have been running) | [#59](https://github.com/esfen14/Pinpoint/issues/59) |
| Negative test: healthcheck fails when `nagios` cannot start the plugin | Pass | With the shebang set back to `python`, the old `python3 plugin --help` check still exits 0 while a direct run as `nagios` exits 127, and the healthcheck reports `[FAIL] check_ncpa.py: interpreter missing (exit 127, line 1: #!/usr/bin/env python)` (59 passed, 1 failed). With `python3.10` not executable by others: `[FAIL] ... permission problem (exit 126)`. With `/usr/bin/python3` renamed: `[FAIL] ... exit 127, line 1: #!/usr/bin/env python3`. All restored afterwards (`negative45.log`) | #45 |
| Negative test: the installer's verify step fails when `nagios` cannot start the plugin | Pass | With `/usr/bin/python3` renamed, `install-nagios-plugins.sh` exited 1 after `✗ check_ncpa.py failed to run as nagios (exit code 127)` and `Interpreter line: #!/usr/bin/env python3` (`installer-neg45.log`). `python3` restored afterwards | #45 |

## Deviations from the plan

- The base was not built from the installer ISO; `scripts/vmlab` runs the installer's own steps on a stock Ubuntu install, as in the earlier runs.
- The fix was tested from a local checkout of commit `e471a1b8`, before it was merged. A build from the installer's `main` (`2859361d`) was not repeated.
- The negative tests broke the interpreter on the live appliance rather than building a separate broken image.

## Follow-up

- Defect: the duplicate `Address Unknown` device record, filed as [#59](https://github.com/esfen14/Pinpoint/issues/59).
- Optional before closing #45: one more `scripts/vmlab provision --force` and `fresh main` using the installer's `main`, to confirm the merged result.
- Shell tests for the installer's verify step and healthcheck (a shared `setup/plugin-interpreters.sh` and `tests/test-plugin-interpreters.sh`) were written but not pushed, because this account has read-only access to the installer repository.
- Still skipped from the first NCPA run: the CPU load alert on an NCPA threshold (`demo_lab.py load`), the browser wizard, the failure paths (wrong password, no sudo, changed host key) and redeploy to an already-deployed device.

## Sanitization checklist

- [x] No passwords, tokens, keys, SNMP communities or private key paths
- [x] No addresses outside the documented lab range
- [x] Evidence is referenced by name and location, not pasted
