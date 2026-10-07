"""Validate agent progress files in .agent/progress/.

    python3 -I scripts/check_agent_progress.py          # structure check
    python3 -I scripts/check_agent_progress.py --none   # fail if any progress file exists

A progress file (issue-<n>.md) lets an agent that stops mid-job resume without
starting over. The structure check keeps them usable: required sections, a valid
Status line, a checklist, and a concrete "Next action". The --none mode is for
pull requests that are ready for review: the file is scaffolding and must be
deleted before merge. See "spec files/Agent_Workflow_and_CI.md".
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / ".agent" / "progress"
SECTIONS = [
    "## Finish condition",
    "## Plan",
    "## Round log",
    "## State for the next session",
    "## Decisions and notes",
]
STATUSES = {"in-progress", "blocked", "ready-for-review"}
CHECKBOX = re.compile(r"^\s*(?:\d+\.|[-*])\s*\[[ xX]\]\s*\S", re.M)
PLACEHOLDERS = ("(item from the issue)", "Step: what, and which files")


def section_text(text, heading):
    """The body of one level-2 section, up to the next level-2 heading."""
    start = text.index(heading) + len(heading)
    match = re.search(r"^## ", text[start:], re.M)
    return text[start:start + match.start()] if match else text[start:]


def problems_in(path):
    """Return a list of problems with one progress file."""
    text = path.read_text(encoding="utf-8")
    problems = []
    if not re.match(r"# Issue #\d+: \S", text):
        problems.append("first line must be '# Issue #<n>: <title>'")
    status = re.search(r"^Status:\s*(\S+)", text, re.M)
    if not status or status.group(1) not in STATUSES:
        problems.append("needs a 'Status:' line: " + " | ".join(sorted(STATUSES)))
    missing = [heading for heading in SECTIONS if heading not in text]
    if missing:
        return problems + [f"missing section {heading!r}" for heading in missing]
    for heading in ("## Finish condition", "## Plan"):
        body = section_text(text, heading)
        if not CHECKBOX.search(body):
            problems.append(f"{heading!r} needs at least one checkbox item")
        if any(placeholder in body for placeholder in PLACEHOLDERS):
            problems.append(f"{heading!r} still has template placeholder text")
    if status and status.group(1) != "ready-for-review":
        nxt = re.search(r"^- Next action[^:]*:\s*(.*)$", section_text(text, "## State for the next session"), re.M)
        if not nxt or not nxt.group(1).strip():
            problems.append("'Next action' under 'State for the next session' is empty")
    return problems


def main(argv):
    files = sorted(FOLDER.glob("issue-*.md")) if FOLDER.is_dir() else []
    if "--none" in argv:
        if files:
            print("Agent progress files must be deleted before a pull request is ready for review:")
            for path in files:
                print(f"  {path.relative_to(ROOT)}")
            print("Run: git rm .agent/progress/issue-<n>.md")
            return 1
        print("no agent progress files")
        return 0

    failed = False
    for path in files:
        problems = problems_in(path)
        for problem in problems:
            failed = True
            print(f"{path.relative_to(ROOT)}: {problem}")
    if failed:
        return 1
    print(f"{len(files)} agent progress file(s) OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
