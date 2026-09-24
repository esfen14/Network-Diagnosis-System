"""
nagios_validator.py — Runs Nagios's own configuration validation.

Used by Phase 5 (Enable/Disable) and expected to be reused by later
phases that also need to validate Nagios configuration before applying
a change (Command Management, Custom Plugins, Updates, Monitoring
Configuration all have their own "Validate Nagios configuration" task
in the Implementation Plan).

Runs the exact command configure-nagios.sh itself uses to validate:
    /usr/local/nagios/bin/nagios -v /usr/local/nagios/etc/nagios.cfg

IMPORTANT: this validates Nagios's ENTIRE configuration, not anything
plugin-specific — Plugin Manager doesn't generate or write any Nagios
config yet (that's Phase 10), so there is nothing narrower to validate
today. This is a deliberate, confirmed scope decision for Phase 5, not
an oversight.
"""
import subprocess

NAGIOS_BINARY_PATH = "/usr/local/nagios/bin/nagios"
NAGIOS_CONFIG_PATH = "/usr/local/nagios/etc/nagios.cfg"

VALIDATION_TIMEOUT_SECONDS = 30


def validate_nagios_configuration():
    """
    Runs Nagios's own config validation.

    Returns:
        (is_valid: bool, output: str)

        is_valid is True only if the nagios binary ran and exited 0.
        output is the combined stdout+stderr for diagnostics/history.

        On a dev machine without Nagios installed (e.g. Windows),
        this correctly returns (False, "...not found..."), since
        this operation genuinely cannot be safely validated there —
        that's honest behavior, not a bug.
    """
    try:
        result = subprocess.run(
            [NAGIOS_BINARY_PATH, "-v", NAGIOS_CONFIG_PATH],
            capture_output=True,
            text=True,
            timeout=VALIDATION_TIMEOUT_SECONDS,
        )
        output = (result.stdout or "") + (result.stderr or "")
        return result.returncode == 0, output

    except FileNotFoundError:
        return False, f"Nagios binary not found at {NAGIOS_BINARY_PATH}."
    except subprocess.TimeoutExpired:
        return False, "Nagios configuration validation timed out."
    except Exception as e:
        return False, f"Unexpected error running Nagios validation: {e}"
