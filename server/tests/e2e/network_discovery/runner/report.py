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


def write_report(run_dir: Path, config: dict[str, Any], commit: str) -> Path:
    """Generate the final Markdown report and a machine-readable CSV summary."""
    rows = read_results(run_dir)
    counts = Counter(row.get("result", "Unknown") for row in rows)
    report = run_dir / "Network_Discovery_Extended_Test_Report.md"
    lines = [
        "# Network Discovery Extended Test Report",
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
    lines.extend([
        "",
        "## Notes",
        "",
        "- Full command and API evidence is stored under `evidence/`.",
        "- Secrets and raw databases are intentionally excluded.",
        "- A successful API response alone is not considered a live-service pass.",
    ])
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    csv_path = run_dir / "evidence" / "plugin-results.csv"
    fieldnames = ["test_id", "plugin", "target", "service", "result", "summary", "started_at", "completed_at"]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return report
