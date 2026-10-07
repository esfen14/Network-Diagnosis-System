"""Fail when the backend's environment variables and the README table disagree.

The "Production settings" table in README.md is the agreed interface with the
PinPoint Installer, which writes /etc/pinpoint/pinpoint.env from it. This
script finds every environment variable the server reads (os.environ.get,
setdefault and pop, os.getenv, os.environ[...], the same through `import os as o`
or `from os import environ, getenv`, and the env_* helpers in server/config.py)
and compares the names with the table. Only literal variable names are seen; a
name held in a variable is not. Pure standard library; no app import.

    python3 -I scripts/check_env_drift.py
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
SKIP_DIRS = {".venv", "venv", "tests", "migrations", "__pycache__", "lib", "lib64", "site-packages"}

# Read by the server but supplied by the OS or by Flask/Werkzeug, not by the installer.
NOT_INSTALLER_SETTINGS = {"HOME", "WERKZEUG_RUN_MAIN"}
# Documented, though read by Flask itself rather than by our code.
READ_BY_FLASK = {"FLASK_DEBUG"}

NAME = re.compile(r"^[A-Z][A-Z0-9_]+$")


def os_names(tree):
    """
    Names that mean the os module, os.environ and os.getenv in this module,
    following `import os as o` and `from os import environ, getenv as g`.
    """
    modules = {"os"}
    environs = set()
    getenvs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    modules.add(alias.asname or "os")
        elif isinstance(node, ast.ImportFrom) and node.module == "os":
            for alias in node.names:
                if alias.name == "environ":
                    environs.add(alias.asname or "environ")
                elif alias.name == "getenv":
                    getenvs.add(alias.asname or "getenv")
    return modules, environs, getenvs


def is_environ(node, modules, environs):
    """True for the expression os.environ (or an imported `environ`)."""
    if isinstance(node, ast.Name):
        return node.id in environs
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "environ"
        and isinstance(node.value, ast.Name)
        and node.value.id in modules
    )


def first_string(call):
    """The first positional argument when it is a string constant, else None."""
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    return None


def env_names_in(tree):
    """Variable names read from the environment in one parsed module."""
    names = set()
    modules, environs, getenvs = os_names(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            is_get = (
                isinstance(func, ast.Attribute)
                and func.attr in {"get", "setdefault", "pop"}
                and is_environ(func.value, modules, environs)
            )
            is_getenv = (
                isinstance(func, ast.Attribute)
                and func.attr == "getenv"
                and isinstance(func.value, ast.Name)
                and func.value.id in modules
            ) or (isinstance(func, ast.Name) and func.id in getenvs)
            is_helper = isinstance(func, ast.Name) and func.id.startswith("env_")
            name = first_string(node) if (is_get or is_getenv or is_helper) else None
            if name and NAME.match(name):
                names.add(name)
        elif isinstance(node, ast.Subscript) and is_environ(node.value, modules, environs):
            key = node.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str) and NAME.match(key.value):
                names.add(key.value)
    return names


def names_in_code():
    """Map each variable the server reads to the files that read it."""
    found = {}
    for path in sorted((ROOT / "server").rglob("*.py")):
        relative = path.relative_to(ROOT / "server")
        if SKIP_DIRS & set(relative.parts) or path.name == "conftest.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for name in env_names_in(tree):
            found.setdefault(name, []).append(str(relative))
    return found


def names_in_readme():
    """Variable names in the first column of the production settings table."""
    names = set()
    in_table = False
    for line in README.read_text(encoding="utf-8").splitlines():
        if line.startswith("| Variable |"):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                break
            match = re.match(r"\|\s*`([A-Z][A-Z0-9_]+)`", line)
            if match:
                names.add(match.group(1))
    return names


def main():
    in_code = names_in_code()
    documented = names_in_readme()
    if not documented:
        print("README.md: production settings table not found")
        return 1

    code_names = set(in_code) - NOT_INSTALLER_SETTINGS
    undocumented = sorted(code_names - documented)
    stale = sorted(documented - code_names - READ_BY_FLASK)
    dropped = sorted(READ_BY_FLASK - documented)

    if undocumented:
        print("Read by the server but missing from the README production settings table:")
        for name in undocumented:
            print(f"  {name}  ({', '.join(in_code[name])})")
    if stale:
        print("In the README production settings table but never read by the server:")
        for name in stale:
            print(f"  {name}")
    if dropped:
        print("Read by Flask itself but no longer in the README production settings table:")
        for name in dropped:
            print(f"  {name}")
    if undocumented or stale or dropped:
        print("\nUpdate the table (the installer builds pinpoint.env from it) or the code.")
        return 1
    print(f"{len(documented)} environment variables match the README table")
    return 0


if __name__ == "__main__":
    sys.exit(main())
