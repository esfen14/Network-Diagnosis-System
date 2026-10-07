"""
secrets_store.py — encrypts the passwords stored with custom checks.

A custom check that needs a password (spec files/Custom_Checks_Plan.md section 9) keeps it in
PLUGIN_CONFIGURATION.Configuration_Data["secrets"] as a Fernet token, never as plain text, and the
API never returns it. It is decrypted only to build the Nagios command when hosts.cfg is generated.

The key is derived (HKDF-SHA256) from PINPOINT_SECRETS_KEY when that environment variable is set,
otherwise from the app's SECRET_KEY. If the key changes, stored passwords can no longer be read:
decrypt() raises SecretsError, the check is left out of hosts.cfg with a warning, and the
administrator enters the password again. Without a stable key (the debug session's random one)
nothing is stored, so a password is never saved that the next start could not read.

What this does not do: Nagios needs the password in the check's command line, so it is written to
hosts.cfg and is visible to anyone who can read that file, the Nagios web UI's command view, or the
process list while the check runs. Keep hosts.cfg readable only by the Nagios user and group.
"""
import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from flask import current_app

PREFIX = "v1:"
KEY_INFO = b"pinpoint-secrets-v1"


class SecretsError(Exception):
    """A secret could not be stored or read. The message never contains a value."""
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def key_material():
    """
    The text the key is derived from: PINPOINT_SECRETS_KEY, else SECRET_KEY. Raises SecretsError
    when there is none, or only the random one a debug session makes up (SECRET_KEY_IS_TEMPORARY).
    """
    explicit = os.environ.get("PINPOINT_SECRETS_KEY")
    if explicit:
        return explicit
    secret_key = current_app.config.get("SECRET_KEY")
    if not secret_key or current_app.config.get("SECRET_KEY_IS_TEMPORARY"):
        raise SecretsError(
            "Passwords cannot be stored because the server has no fixed SECRET_KEY. "
            "Set SECRET_KEY (or PINPOINT_SECRETS_KEY) and restart."
        )
    return secret_key


def fernet():
    """The Fernet for the current key material."""
    derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=KEY_INFO).derive(
        key_material().encode("utf-8")
    )
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt(value):
    """The stored form of a secret: "v1:" followed by the Fernet token. Raises SecretsError without a stable key."""
    return PREFIX + fernet().encrypt(str(value).encode("utf-8")).decode("ascii")


def decrypt(stored):
    """
    The secret behind a stored value. Raises SecretsError if the value is not in this format, was
    made with another key, or is damaged.
    """
    unreadable = SecretsError("A stored password cannot be read (the key changed or the data is damaged).")
    text = str(stored or "")
    if not text.startswith(PREFIX):
        raise unreadable
    try:
        return fernet().decrypt(text[len(PREFIX):].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        raise unreadable


def is_readable(stored):
    """True if decrypt(stored) works."""
    try:
        decrypt(stored)
        return True
    except SecretsError:
        return False
