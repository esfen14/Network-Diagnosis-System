"""Markdown and CSV report generation for a completed live-lab run."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

from .common import read_results, utc_now


def _cell(value: Any) -> str:
    """Escape a value for a compact Markdown table cell."""
    return str(value or "").replace("|", "\\|").replace("\n", " ")


SATISFIED = {"Pass", "Previously verified"}


def objective_status(case_ids: list[str], results: dict[str, str]) -> str:
    """
    Judge one objective from its cases: Met when every applicable case passed,
    Not met when none did, Not fully met when one failed, otherwise Partly
    verified (some cases blocked, skipped or not run).
    """
    outcomes = [results.get(case_id, "Not run") for case_id in case_ids]
    applicable = [value for value in outcomes if value != "Not Applicable"]
    if not applicable or not any(value in SATISFIED for value in applicable):
        return "Not met"
    if all(value in SATISFIED for value in applicable):
        return "Met"
    if "Fail" in applicable:
        return "Not fully met"
    return "Partly verified"


def _traceability_lines(traceability: dict[str, Any], results: dict[str, str]) -> list[str]:
    """Render the objective table and the blocking cases from a traceability manifest."""
    lines = [
        "",
        "## Objective traceability",
        "",
        "An objective with no passing case is not met. Failed, blocked and unrun cases are shown so a gap is visible.",
        "",
        "| Objective | Title | Cases | Status |",
        "|---|---|---|---|",
    ]
    for objective, entry in traceability.get("objectives", {}).items():
        ids = entry.get("cases", [])
        cells = ", ".join(f"{case_id} ({results.get(case_id, 'Not run')})" for case_id in ids)
        lines.append(
            f"| {_cell(objective)} | {_cell(entry.get('title'))} | {_cell(cells)} | "
            f"{objective_status(ids, results)} |"
        )
    blocking = traceability.get("blocking", [])
    if blocking:
        lines.extend(["", "## Blocking cases", ""])
        lines.extend(f"- {case_id}: {results.get(case_id, 'Not run')}" for case_id in blocking)
    return lines


def write_report(
    run_dir: Path, config: dict[str, Any], commit: str, traceability: dict[str, Any] | None = None,
) -> Path:
    """
    Generate the final Markdown report and a machine-readable CSV summary.

    config["report_title"] and config["report_name"] rename the report (the
    defaults keep the Network Discovery names); traceability adds the objective
    table; evidence/findings.md, when present, is linked under Notes.
    """
    rows = read_results(run_dir)
    counts = Counter(row.get("result", "Unknown") for row in rows)
    title = config.get("report_title") or "Network Discovery Extended Test Report"
    name = config.get("report_name") or "Network_Discovery_Extended_Test_Report.md"
    if "/" in name or "\\" in name or not name.endswith(".md"):
        raise ValueError("report_name must be a plain .md file name.")
    report = run_dir / name
    lines = [
        f"# {title}",
        "",
        f"- Generated: {utc_now()}",
        f"- Tested commit: `{commit}`",
        f"- Lab network: `{config['lab_network']}`",
        f"- Cases recorded: {len(rows)}",
        "",
        "## Result summary",
        "",
    ]
    if counts:
        for label in sorted(counts):
            lines.append(f"- {label}: {counts[label]}")
    else:
        lines.append("- No test results were recorded.")
    lines.extend([
        "",
        "## Case results",
        "",
        "| Test ID | Plugin/service | Target | Result | Summary | Evidence |",
        "|---|---|---|---|---|---|",
    ])
    for row in rows:
        plugin_service = "/".join(filter(None, [row.get("plugin"), row.get("service")]))
        evidence = ", ".join(row.get("evidence") or [])
        lines.append(
            f"| {_cell(row.get('test_id'))} | {_cell(plugin_service)} | "
            f"{_cell(row.get('target'))} | {_cell(row.get('result'))} | "
            f"{_cell(row.get('summary'))} | {_cell(evidence)} |"
        )
    if traceability:
        lines.extend(_traceability_lines(traceability, {row["test_id"]: row.get("result", "Unknown") for row in rows}))
    lines.extend([
        "",
        "## Notes",
        "",
        "- Full command and API evidence is stored under `evidence/`.",
        "- Secrets and raw databases are intentionally excluded.",
        "- A successful API response alone is not considered a live-service pass.",
    ])
    if (run_dir / "evidence" / "findings.md").is_file():
        lines.append("- Findings and plan-wording issues: `evidence/findings.md` (not counted in the results above).")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    csv_path = run_dir / "evidence" / "plugin-results.csv"
    fieldnames = ["test_id", "plugin", "target", "service", "result", "summary", "started_at", "completed_at"]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return report
