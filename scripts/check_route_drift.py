"""Fail when Flask's /api routes and the route catalog in the spec disagree.

Compares the (method, path) pairs registered in the Flask app with the
backtick-quoted `METHOD /api/...` entries in
"spec files/Backend_Modules_and_Routes.md". Path parameters are compared by
position, not name (`<id>` equals `<int:plugin_id>`). A catalog row that starts
with `~~` is documented as disabled and is expected to be absent from the app.

Run from the repository root with the backend dependencies installed:
    FLASK_DEBUG=1 python scripts/check_route_drift.py
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "spec files" / "Backend_Modules_and_Routes.md"
ENTRY = re.compile(r"`(GET|POST|PUT|PATCH|DELETE) (/api[^`\s]*)`")


def normalize(path):
    """Replace every <converter:name> parameter with a bare <>."""
    return re.sub(r"<[^>]+>", "<>", path)


def routes_in_code():
    """Return {(method, path)} for every /api rule registered in the app."""
    os.environ.setdefault("FLASK_DEBUG", "1")
    sys.path.insert(0, str(ROOT / "server"))
    os.chdir(ROOT / "server")
    from app import app

    found = set()
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api"):
            continue
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            found.add((method, normalize(rule.rule)))
    return found


def routes_in_catalog():
    """Return (active, disabled) sets of (method, path) from the spec tables."""
    active = set()
    disabled = set()
    for line in CATALOG.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        first_cell = line.split("|")[1].strip()
        target = disabled if first_cell.startswith("~~") else active
        for method, path in ENTRY.findall(first_cell):
            target.add((method, normalize(path)))
    return active, disabled


def main():
    code = routes_in_code()
    active, disabled = routes_in_catalog()

    undocumented = sorted(code - active - disabled)
    missing_in_code = sorted(active - code)
    enabled_but_disabled_in_docs = sorted(code & disabled)

    problems = 0
    if undocumented:
        problems += 1
        print("In code but not in Backend_Modules_and_Routes.md:")
        for method, path in undocumented:
            print(f"  {method} {path}")
    if missing_in_code:
        problems += 1
        print("In Backend_Modules_and_Routes.md but not registered in code:")
        for method, path in missing_in_code:
            print(f"  {method} {path}")
    if enabled_but_disabled_in_docs:
        problems += 1
        print("Documented as disabled (~~) but registered in code:")
        for method, path in enabled_but_disabled_in_docs:
            print(f"  {method} {path}")

    if problems:
        print("\nUpdate the catalog (or the code) so they match.")
        return 1
    print(f"{len(code)} API routes match the catalog ({len(disabled)} documented as disabled)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
