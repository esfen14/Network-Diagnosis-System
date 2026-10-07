"""Fail when the React client calls an /api endpoint the Flask app does not serve.

Scans client/src (tests excluded, comments stripped) for string and template
literals that start with /api/, or with a `${CONST}` that the same file sets to
an /api/ prefix. Query strings are dropped and a `${...}` placeholder becomes a
wildcard path segment (so `/api/system/report/${view}` matches any single-segment
report route). When the call is apiGet/apiPost/apiPut/apiDelete, or a fetch with
a literal `method:`, the HTTP method is checked too; otherwise the path only.
A `const NAME = '/api/...'` declaration that is only the prefix of served routes
is not a call. A URL held in a variable is checked by path only (no method).
Compared with the routes Flask registers, so run it with the backend
dependencies installed:

    FLASK_DEBUG=1 python scripts/check_client_api_drift.py
"""
import re
import sys
from pathlib import Path

from check_route_drift import normalize, routes_in_code

ROOT = Path(__file__).resolve().parent.parent
CLIENT_SRC = ROOT / "client" / "src"

LITERAL = re.compile(r"""(['"`])(/api/(?:(?!\1)[^\n])*)\1""")
CONST_LITERAL = re.compile(r"""(['"`])\$\{(\w+)\}((?:(?!\1)[^\n])*)\1""")
PREFIX_CONST = re.compile(r"""\bconst\s+(\w+)\s*=\s*['"`](/api/[^'"`\n]*)['"`]""")
API_NAME = re.compile(r"\bapi(Get|Post|Put|Delete)\s*$")
FETCH_NAME = re.compile(r"\bfetch\s*$")
METHOD = re.compile(r"method\s*:\s*['\"](GET|POST|PUT|PATCH|DELETE)['\"]")


def strip_comments(text):
    """Blank out // and /* */ comments, keeping line numbers intact."""
    def blank(match):
        return re.sub(r"[^\n]", " ", match.group(0))

    text = re.sub(r"/\*.*?\*/", blank, text, flags=re.S)
    return re.sub(r"(?<![:'\"`])//[^\n]*", blank, text)


def clean_path(raw):
    """Normalise a literal: drop the query string, turn ${...} into <>."""
    path = raw.split("?", 1)[0]
    path = re.sub(r"\$\{[^}]*\}", "<>", path)
    return normalize(path).rstrip("/") or "/"


def callee_before(text, start):
    """
    The text of the callee when the literal at start is a call's first argument,
    e.g. "apiGet<Foo<Bar>>" for `apiGet<Foo<Bar>>(` + literal; None otherwise.
    """
    i = start - 1
    while i >= 0 and text[i].isspace():
        i -= 1
    if i < 0 or text[i] != "(":
        return None
    i -= 1
    while i >= 0 and text[i].isspace():
        i -= 1
    end = i + 1
    if i >= 0 and text[i] == ">":
        depth = 0
        while i >= 0:
            if text[i] == ">" and not (i > 0 and text[i - 1] == "="):
                depth += 1
            elif text[i] == "<":
                depth -= 1
                if depth == 0:
                    break
            i -= 1
        i -= 1
        while i >= 0 and text[i].isspace():
            i -= 1
        end = i + 1
    return text[max(0, end - 60):end]


def method_for(text, start, end):
    """
    Guess the HTTP method of the call whose first argument is the literal at
    start:end. None when the URL is not passed straight to apiGet/apiPost/
    apiPut/apiDelete/fetch (for example it sits in a variable): such a call is
    checked by path only.
    """
    callee = callee_before(text, start)
    if callee is None:
        return None
    api = API_NAME.search(callee)
    if api:
        return api.group(1).upper()
    if FETCH_NAME.search(callee):
        window = text[end:end + 400]
        stop = re.search(r"\bfetch\s*\(|\bapi(?:Get|Post|Put|Delete)\b", window)
        window = window[:stop.start()] if stop else window
        found = METHOD.search(window)
        return found.group(1) if found else "GET"
    return None


def calls_in_client():
    """Return (file, line, method or None, path, is_prefix_declaration) for every /api literal."""
    calls = []
    for path in sorted(CLIENT_SRC.rglob("*.ts*")):
        relative = path.relative_to(CLIENT_SRC)
        if "test" in relative.parts or ".test." in path.name:
            continue
        text = strip_comments(path.read_text(encoding="utf-8"))
        declared = set()
        for const in PREFIX_CONST.finditer(text):
            declared.add(const.start(2) - 1)
        for match in LITERAL.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            is_declaration = match.start() in declared
            calls.append((str(relative), line, method_for(text, match.start(), match.end()), clean_path(match.group(2)), is_declaration))
        prefixes = dict((name, value) for name, value in PREFIX_CONST.findall(text))
        for match in CONST_LITERAL.finditer(text):
            prefix = prefixes.get(match.group(2))
            if prefix is None:
                continue
            line = text.count("\n", 0, match.start()) + 1
            joined = clean_path(prefix + match.group(3))
            calls.append((str(relative), line, method_for(text, match.start(), match.end()), joined, False))
    return calls


def matching_methods(path, served):
    """
    Methods of every served route whose segments match path. A <> in the client
    path (a ${...} placeholder) matches any served segment; a literal client
    segment must equal the served one, so a typo cannot hide behind a sibling
    <param> route.
    """
    wanted = path.split("/")
    found = set()
    for method, route in served:
        actual = route.split("/")
        if len(actual) != len(wanted):
            continue
        same = True
        for left, right in zip(wanted, actual):
            if left != right and left != "<>":
                same = False
                break
        if same:
            found.add(method)
    return found


def is_route_prefix(path, served):
    """True when path is only the leading part of at least one served route."""
    return any(route.startswith(path + "/") for _, route in served)


def main():
    served = routes_in_code()
    problems = []
    calls = calls_in_client()
    for file, line, method, path, is_declaration in calls:
        methods = matching_methods(path, served)
        if not methods:
            if is_declaration and is_route_prefix(path, served):
                continue  # `const BASE = '/api/...'`, used as ${BASE}/... elsewhere
            problems.append(f"{file}:{line}  {method or '?'} {path}  is not a route Flask serves")
        elif method and method not in methods:
            problems.append(f"{file}:{line}  {method} {path}  but Flask serves only {', '.join(sorted(methods))}")

    if problems:
        print("Client calls that do not match the backend:")
        for problem in problems:
            print("  " + problem)
        return 1
    print(f"{len(calls)} client API call sites all match routes Flask serves")
    return 0


if __name__ == "__main__":
    sys.exit(main())
