"""
command_validator.py — Validates a Nagios command-override string for
shell-injection risk (Phase 6).

Unlike nagios_validator.py (Phase 5), this does NOT shell out to the
real `nagios` binary. Reason: per the UI Flow doc (Section 17, "Apply
Monitoring Configuration" is a distinct, LATER screen from Section 16's
"Command Override"), saving a command override here is DB-only — it
doesn't touch live nagios.cfg at all. That happens later, in Phase 10's
Apply step. Running `nagios -v` here would only validate the
pre-existing config file, telling us nothing about the string being
saved right now.

What this DOES validate: the override string itself, since it gets
saved now but will eventually be executed by Nagios once Phase 10
applies it — so this is the safety net against saving something
dangerous in the meantime.

Confirmed validation level: moderate. Blocks classic shell-injection
metacharacters, but explicitly ALLOWS the pipe character (|), since
Nagios command definitions sometimes legitimately pipe output.
"""
import re

MAX_COMMAND_LENGTH = 500

# Confirmed blocklist: command chaining/substitution/newlines.
# Deliberately does NOT include | (pipe) — allowed.
_DANGEROUS_PATTERNS = [
    (";", "semicolon (command separator)"),
    ("`", "backtick (command substitution)"),
    ("$(", "$(...) command substitution"),
    ("&&", "&& (command chaining)"),
    ("||", "|| (command chaining)"),
    ("\n", "newline"),
    ("\r", "carriage return"),
]


def validate_command_definition(command):
    """
    Args:
        command: the proposed override command string.

    Returns:
        (is_valid: bool, reason: str | None)
    """
    if command is None or not command.strip():
        return False, "Command cannot be empty."

    if len(command) > MAX_COMMAND_LENGTH:
        return False, f"Command exceeds maximum length of {MAX_COMMAND_LENGTH} characters."

    for pattern, description in _DANGEROUS_PATTERNS:
        if pattern in command:
            return False, f"Command contains a disallowed character/sequence: {description}."

    return True, None
