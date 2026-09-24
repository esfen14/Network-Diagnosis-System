"""
plugin_validator.py — Validates a single plugin's executable, file
permissions, and that it can actually be run (Phase 7).

Distinct from the other two validators in this package:
  - nagios_validator.py validates the EXISTING nagios.cfg file
    (Phase 5's enable/disable gate).
  - command_validator.py validates a proposed override STRING before
    it's saved (Phase 6).
  - This module validates the PLUGIN EXECUTABLE ITSELF — the file on
    disk, its permissions, and whether it runs.

Scope confirmed against UI Flow Section 17 ("Apply Monitoring
Configuration"), which lists "Dependency check", "Plugin validation",
and "Nagios configuration check" as three SEPARATE steps. This module
covers only "Plugin validation" — dependency checks already exist via
PluginDependency / GET /plugin/<id>/dependencies, and Nagios config
checks are nagios_validator.py's job, reused again whenever Phase 10's
Apply step needs it. Bundling all three into one per-plugin validate
call would blur a distinction the UI Flow doc itself draws.
"""
import os
import stat
import subprocess

EXECUTION_TEST_TIMEOUT_SECONDS = 5


def check_executable(executable_path):
    """
    Confirms the plugin's file exists, is a regular file, and is
    executable. Does NOT check ownership/permission bits beyond the
    basic execute bit — see check_permissions() for the security-
    focused check.

    Returns:
        {"passed": bool, "message": str}
    """
    if not executable_path:
        return {"passed": False, "message": "No executable path recorded for this plugin."}

    if not os.path.exists(executable_path):
        return {"passed": False, "message": f"File does not exist: {executable_path}"}

    if not os.path.isfile(executable_path):
        return {"passed": False, "message": f"Path is not a regular file: {executable_path}"}

    if not os.access(executable_path, os.X_OK):
        return {"passed": False, "message": f"File is not executable: {executable_path}"}

    return {"passed": True, "message": "Executable exists and has the execute bit set."}


def check_permissions(executable_path):
    """
    Security-focused check, distinct from check_executable(): flags a
    world-writable plugin binary, since anyone on the system could
    tamper with it (a real risk — Nagios typically runs plugins with
    elevated trust). Confirmed scope: this is the specific thing
    "Validate permissions" adds beyond "Validate plugin executable".

    Returns:
        {"passed": bool, "message": str, "mode": str, "world_writable": bool}
    """
    if not executable_path or not os.path.exists(executable_path):
        return {
            "passed": False,
            "message": "Cannot check permissions — file does not exist.",
            "mode": None,
            "world_writable": None,
        }

    file_stat = os.stat(executable_path)
    mode = file_stat.st_mode
    mode_octal = format(stat.S_IMODE(mode), "04o")
    world_writable = bool(mode & stat.S_IWOTH)

    if world_writable:
        return {
            "passed": False,
            "message": f"File is world-writable ({mode_octal}) — any user could modify this plugin.",
            "mode": mode_octal,
            "world_writable": True,
        }

    return {
        "passed": True,
        "message": f"Permissions OK ({mode_octal}), not world-writable.",
        "mode": mode_octal,
        "world_writable": False,
    }


def check_execution(executable_path):
    """
    Actually runs the plugin with --version, the same safe,
    argument-free invocation Phase 2's scanner uses — never runs a
    plugin with arbitrary/real check arguments ("where safe" per the
    task name).

    "passed" means the process could be launched and ran to
    completion at all (no missing-binary/permission/timeout error) —
    NOT that it exited 0. Nagios plugins routinely exit non-zero for
    WARNING/CRITICAL states even when working correctly, and not
    every one of the 57 bundled plugins necessarily exits 0 on
    --version either, so treating a non-zero exit as a hard failure
    here would produce false negatives on working plugins.

    Returns:
        {"passed": bool, "message": str, "exit_code": int | None, "output": str}
    """
    if not executable_path or not os.path.exists(executable_path):
        return {
            "passed": False,
            "message": "Cannot test execution — file does not exist.",
            "exit_code": None,
            "output": "",
        }

    try:
        result = subprocess.run(
            [executable_path, "--version"],
            capture_output=True,
            text=True,
            timeout=EXECUTION_TEST_TIMEOUT_SECONDS,
        )
        output = (result.stdout or "") + (result.stderr or "")
        return {
            "passed": True,
            "message": f"Executed successfully (exit code {result.returncode}).",
            "exit_code": result.returncode,
            "output": output.strip()[:500],
        }

    except PermissionError:
        return {"passed": False, "message": "Permission denied when attempting to execute.", "exit_code": None, "output": ""}
    except subprocess.TimeoutExpired:
        return {"passed": False, "message": "Execution timed out.", "exit_code": None, "output": ""}
    except Exception as e:
        return {"passed": False, "message": f"Unexpected error during execution: {e}", "exit_code": None, "output": ""}


def validate_plugin_executable(executable_path):
    """
    Runs all three checks and combines them.

    Returns:
        {
            "is_valid": bool,
            "checks": {
                "executable": {...},
                "permissions": {...},
                "execution": {...},
            }
        }
    """
    executable_result = check_executable(executable_path)
    permissions_result = check_permissions(executable_path)
    execution_result = check_execution(executable_path)

    is_valid = executable_result["passed"] and permissions_result["passed"] and execution_result["passed"]

    return {
        "is_valid": is_valid,
        "checks": {
            "executable": executable_result,
            "permissions": permissions_result,
            "execution": execution_result,
        },
    }
