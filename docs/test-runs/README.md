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
- A report is never edited to change a result. Re-test in a new run and link it.

## Index

| Run | Kind | Commit | Result | Report |
|---|---|---|---|---|
| [2026-10-08 vm-lab-remaining](2026-10-08-vm-lab-remaining/REPORT.md) | VM lab, fresh install of the #43 fix, alerts, sync, up/down/revert | app `d8dc63e0`, `main` `483c8bdc` | Pass | [REPORT.md](2026-10-08-vm-lab-remaining/REPORT.md) |
| [2026-10-08 ncpa-run](2026-10-08-ncpa-run/REPORT.md) | VM lab, NCPA deployment and monitoring | app `1540545` | Partial: deployment passes, NCPA checks CRITICAL (#45) | [REPORT.md](2026-10-08-ncpa-run/REPORT.md) |
| [2026-10-08 vm-lab-first-run](2026-10-08-vm-lab-first-run/REPORT.md) | VM lab, installer-built appliance | app `1540545` | Pass (tooling); defect #43 found | [REPORT.md](2026-10-08-vm-lab-first-run/REPORT.md) |

Add a row when you commit a report. Earlier runs mentioned in
[`../plans/`](../plans/) (for example the 2026-10-03 and 2026-10-06 live runs)
were reported outside the repository and are not reproduced here.
