"""Fail when the browser routes in code and the frontend spec disagree.

Three sources are compared (pure standard library, no Node needed):
  - client/src/App.tsx          the <Route> elements (path and page component)
  - client/src/lib/pageAccess.ts  PAGE_PERMISSIONS (route -> client permission)
  - "spec files/Frontend_Modules_and_Routes.md"  the "Browser route catalog" table

Checks: every routed path is documented and vice versa; the page component and
the required permission in the table match the code; PAGE_PERMISSIONS has an
entry for every gated page and no entry for a path that is not routed.

    python3 -I scripts/check_frontend_route_drift.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "client" / "src" / "App.tsx"
ACCESS = ROOT / "client" / "src" / "lib" / "pageAccess.ts"
SPEC = ROOT / "spec files" / "Frontend_Modules_and_Routes.md"

# Routed but not permission-gated by PAGE_PERMISSIONS: public or redirect-only.
UNGATED = {"/login", "/"}


def routes_in_app():
    """Return {path: page component or None} for every <Route> in App.tsx."""
    text = APP.read_text(encoding="utf-8")
    routes = {}
    starts = [match.start() for match in re.finditer(r"<Route\b", text)]
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(text)
        block = text[start:end]
        header = block.split("element", 1)[0]
        path_match = re.search(r"""\bpath=(?:(["'])([^"']*)\1|\{\s*(["'`])([^"'`]*)\3\s*\})""", header)
        if path_match:
            path = path_match.group(2) if path_match.group(1) else path_match.group(4)
        elif re.search(r"\bpath=", header):
            raise SystemExit("App.tsx: a <Route> has a path this check cannot read; use a plain string literal")
        elif re.search(r"\bindex\b", block.split("element", 1)[0]):
            path = ""
        else:
            continue
        if path == "*":
            continue
        full = path if path.startswith("/") else "/" + path
        page = re.search(r"element=\{\s*<([A-Z]\w*)", block)
        component = page.group(1) if page else None
        # The layout route owns "/" and wraps AdminLayout; the index route is the redirect.
        if full == "/" and component == "AdminLayout":
            continue
        routes[full] = component
    return routes


def permissions_in_code():
    """Return {path: permission or None} from PAGE_PERMISSIONS."""
    text = ACCESS.read_text(encoding="utf-8")
    body = re.search(r"PAGE_PERMISSIONS[^=]*=\s*\{(.*?)\n\}", text, re.S)
    if not body:
        raise SystemExit("PAGE_PERMISSIONS not found in pageAccess.ts")
    found = {}
    for key, value in re.findall(r"'(/[^']*)'\s*:\s*(null|'[^']*')", body.group(1)):
        found[key] = None if value == "null" else value.strip("'")
    return found


def routes_in_spec():
    """Return {path: (page, permission)} from the Browser route catalog table."""
    rows = {}
    in_section = False
    for line in SPEC.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            in_section = line.strip() == "## Browser route catalog"
            continue
        if not in_section or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        path = re.fullmatch(r"`(/[^`]*)`", cells[0])
        if not path:
            continue  # header, separator and the "unmatched path" row
        page = re.fullmatch(r"`(\w+)`", cells[1])
        permission = re.fullmatch(r"`([a-z_.]+)`", cells[2])
        if not permission and not re.match(r"(Public|—|Any logged-in user)", cells[2]):
            raise SystemExit(f"Spec route table: cannot read the permission cell for {path.group(1)}: {cells[2]!r}")
        rows[path.group(1)] = (page.group(1) if page else None, permission.group(1) if permission else None)
    return rows


def main():
    app = routes_in_app()
    gated = permissions_in_code()
    spec = routes_in_spec()
    problems = []

    for path in sorted(set(app) - set(spec)):
        problems.append(f"{path} is routed in App.tsx but missing from the spec route table")
    for path in sorted(set(spec) - set(app)):
        problems.append(f"{path} is in the spec route table but not routed in App.tsx")

    for path in sorted(set(app) & set(spec)):
        spec_page, spec_permission = spec[path]
        code_page = app[path]
        redirect = path == "/" and code_page == "Navigate"
        if spec_page != code_page and not redirect:
            problems.append(f"{path}: spec page {spec_page} but App.tsx renders {code_page}")
        if path in UNGATED:
            continue
        code_permission = gated.get(path)
        if spec_permission != code_permission:
            problems.append(f"{path}: spec permission {spec_permission} but pageAccess.ts has {code_permission}")

    for path in sorted(set(app) - set(gated) - UNGATED):
        problems.append(f"{path} is routed but has no entry in PAGE_PERMISSIONS (pageAccess.ts)")
    for path in sorted(set(gated) - set(app)):
        problems.append(f"{path} is in PAGE_PERMISSIONS but is not routed in App.tsx")

    if problems:
        print("Frontend route drift:")
        for problem in problems:
            print("  " + problem)
        return 1
    print(f"{len(app)} browser routes match App.tsx, pageAccess.ts and the spec table")
    return 0


if __name__ == "__main__":
    sys.exit(main())
