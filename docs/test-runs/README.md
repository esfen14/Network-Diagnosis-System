# Test Runs

The record of what was tested, on which commit, and what happened. One folder
per run; the plan that drives a run stays in
[`server/tests/plans/`](../../server/tests/plans/README.md).

## Where results go

| Kind | Where | Committed? | Kept |
|---|---|---|---|
| Automated suites in CI (pytest, vitest) | GitHub Actions run, `test-results` artifact (JUnit XML) | No | 30 days |
| Local runs while developing | `test-results/` in the repo root | No (git-ignored) | Until deleted |
| Live-lab and acceptance runs: summary | `docs/test-runs/<date>-<slug>/REPORT.md` | **Yes** | Permanent |
| Live-lab raw evidence (logs, Nagios configs, captures, screenshots) | The harness `output_root` on the lab host (for example `/home/paeng/pinpoint-test-results`) | **Never** | Lab owner |

Raw evidence can hold credentials, SNMP communities, host keys and lab
addresses, so it never enters the repository. The report records what the
evidence showed and where to find it.

## Starting a run

```bash
scripts/new_test_run.sh <slug> [path/to/test-plan.md]
```

This creates `docs/test-runs/<date>-<slug>/REPORT.md` from
[`TEMPLATE.md`](TEMPLATE.md) with the date and commit filled in. Fill the case
table while you test, not afterward.

## Rules

- Name the exact commit tested. A result without a commit is not reproducible.
- One row per plan case: `Pass`, `Fail`, `Blocked` or `Skipped`, and why.
- Every `Fail` and `Blocked` links a GitHub issue. Defects live in issues, not in
  the report.
- Sanitize before committing: no passwords, tokens, keys, community strings,
  private addresses beyond the documented lab range, or full command output that
  contains them.
- `Pass` means the behavior was observed running. Reading code or a diff is not a
  test: record it as `Skipped` or `Blocked` with the reason, and say "inspected" in the
  notes. A run with no observed behavior is not `Pass` overall, and does not change an
  earlier run's index row.
- A report is never edited to change a result. Re-test in a new run and link it. The one
  exception is a result that overstated its evidence: correct it in place, say so in the
  report, and fix the index row in the same change.

## Index

| Run | Kind | Commit | Result | Report |
|---|---|---|---|---|
| [2026-10-08 issue-47-ncpa-live](2026-10-08-issue-47-ncpa-live/REPORT.md) | VM lab, live SSH/NCPA deployment for issue #47 | `7735fc1e` | Pass for #47 deployment/log behavior | [REPORT.md](2026-10-08-issue-47-ncpa-live/REPORT.md) |
| [2026-10-08 vm-lab-remaining](2026-10-08-vm-lab-remaining/REPORT.md) | VM lab, fresh install of the #43 fix, alerts, sync, up/down/revert | app `d8dc63e0`, `main` `483c8bdc` | Pass | [REPORT.md](2026-10-08-vm-lab-remaining/REPORT.md) |
| [2026-10-08 ncpa-fresh-run](2026-10-08-ncpa-fresh-run/REPORT.md) | VM lab, clean appliance with the #45 installer fix, NCPA deploy, all six services, negative tests | app `ed9f2c2`, installer `e471a1b8` (unmerged) | Pass for #45 behavior; defect found (duplicate device record, issue not yet filed) | [REPORT.md](2026-10-08-ncpa-fresh-run/REPORT.md) |
| [2026-10-08 ncpa-repeat-run](2026-10-08-ncpa-repeat-run/REPORT.md) | VM lab, partial recheck of the #45 installer fix (not a fresh deployment) | installer `e471a1b8` | Partial: fix inspected and one NCPA check OK; acceptance not complete (#45 open) | [REPORT.md](2026-10-08-ncpa-repeat-run/REPORT.md) |
| [2026-10-08 ncpa-run](2026-10-08-ncpa-run/REPORT.md) | VM lab, NCPA deployment and monitoring | app `1540545` | Partial: deployment passes, NCPA checks CRITICAL (#45) | [REPORT.md](2026-10-08-ncpa-run/REPORT.md) |
| [2026-10-08 vm-lab-first-run](2026-10-08-vm-lab-first-run/REPORT.md) | VM lab, installer-built appliance | app `1540545` | Pass (tooling); defect #43 found | [REPORT.md](2026-10-08-vm-lab-first-run/REPORT.md) |

Add a row when you commit a report. Earlier runs mentioned in
[`../plans/`](../plans/) (for example the 2026-10-03 and 2026-10-06 live runs)
were reported outside the repository and are not reproduced here.
