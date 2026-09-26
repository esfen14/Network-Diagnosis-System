"""Small helpers for reading system-wide toggles that gate logging behavior.

Kept separate from app/api/system/settings.py to avoid other modules
(login, account management) importing route-handler code just to check a
flag.
"""

from app import db
from app.system_models import SystemSettings


def _get_settings():
    return db.session.get(SystemSettings, 1)


def is_audit_logging_enabled() -> bool:
    """Whether admin-action audit trail entries (account changes, config
    changes) should be recorded. Defaults to True if settings don't exist
    yet — logging is the safer default."""
    settings = _get_settings()
    return settings is None or settings.Audit_Logging


def is_failed_login_monitoring_enabled() -> bool:
    settings = _get_settings()
    return settings is None or settings.Failed_Login_Monitoring


def is_strong_password_policy_enabled() -> bool:
    settings = _get_settings()
    return settings is None or settings.Strong_Password_Policy


DEFAULT_SESSION_TIMEOUT_MINUTES = 30


def get_session_timeout_minutes() -> int:
    """Idle minutes before a logged-in session expires. Falls back to
    DEFAULT_SESSION_TIMEOUT_MINUTES if settings don't exist yet or hold
    a non-positive value, so a bad row can never disable the timeout."""
    settings = _get_settings()
    if settings is None or not settings.Session_Timeout or settings.Session_Timeout <= 0:
        return DEFAULT_SESSION_TIMEOUT_MINUTES
    return settings.Session_Timeout
