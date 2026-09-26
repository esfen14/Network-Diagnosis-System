"""
custom_plugin.py — Handles the file-handling side of Phase 8 (Custom
Plugins): securely staging an uploaded file, computing its checksum,
and installing it into the Nagios plugin directory.

Kept separate from service.py's DB/business logic, matching this
package's existing split (scanner.py = filesystem, service.py =
DB/orchestration) — this module owns the actual bytes on disk.

SECURITY NOTES:
  - The uploaded filename is never trusted directly. werkzeug's
    secure_filename() strips path separators and other dangerous
    characters, preventing path traversal (e.g. "../../etc/cron.d/x").
  - Files are staged in a real OS temp directory (tempfile.mkdtemp)
    before being moved into NAGIOS_PLUGIN_DIR — nothing touches the
    real plugin directory until every check has passed.
  - The staging directory is always cleaned up, success or failure.
"""
import hashlib
import os
import shutil
import tempfile

from werkzeug.utils import secure_filename

from app.api.plugin.scanner import get_plugin_dir

MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB — generous for a plugin script/binary


class UploadTooLargeError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class InvalidFilenameError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class NameCollisionError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def stage_upload(file_storage):
    """
    Saves an uploaded file (a Flask/Werkzeug FileStorage object, from
    request.files) into a fresh temp directory, after sanitizing its
    filename.

    Args:
        file_storage: the werkzeug FileStorage from request.files.

    Returns:
        (staged_path: str, safe_filename: str, staging_dir: str,
         checksum: str, size_bytes: int)

    Raises:
        InvalidFilenameError: filename missing or becomes empty after
            sanitization (e.g. it was entirely path-traversal characters).
        UploadTooLargeError: exceeds MAX_UPLOAD_SIZE_BYTES.
    """
    original_filename = file_storage.filename or ""
    safe_filename = secure_filename(original_filename)

    if not safe_filename:
        raise InvalidFilenameError(
            f"'{original_filename}' is not a valid filename."
        )

    staging_dir = tempfile.mkdtemp(prefix="pinpoint_plugin_upload_")
    staged_path = os.path.join(staging_dir, safe_filename)

    file_storage.save(staged_path)

    size_bytes = os.path.getsize(staged_path)
    if size_bytes > MAX_UPLOAD_SIZE_BYTES:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise UploadTooLargeError(
            f"File is {size_bytes} bytes, exceeding the {MAX_UPLOAD_SIZE_BYTES}-byte limit."
        )

    checksum = _sha256_of_file(staged_path)

    # Executable bit so Phase 7's check_executable()/check_execution()
    # can meaningfully test it while it's still just staged.
    os.chmod(staged_path, 0o755)

    return staged_path, safe_filename, staging_dir, checksum, size_bytes


def check_name_collision(safe_filename):
    """
    Confirmed scope: reject if a file already exists at that path in
    the real Nagios plugin directory — whether from the baseline ISO
    scan or a previous custom upload. Prevents accidentally
    overwriting an existing plugin.

    Raises:
        NameCollisionError
    """
    target_path = os.path.join(get_plugin_dir(), safe_filename)
    if os.path.exists(target_path):
        raise NameCollisionError(
            f"A file named '{safe_filename}' already exists in the Nagios plugin directory."
        )


def install_staged_file(staged_path, safe_filename):
    """
    Moves a staged, validated file into NAGIOS_PLUGIN_DIR. Only called
    after every validation check has passed — see service.py's
    register_custom_plugin().

    Returns:
        the final installed path (str)
    """
    target_path = os.path.join(get_plugin_dir(), safe_filename)
    shutil.move(staged_path, target_path)
    os.chmod(target_path, 0o755)
    return target_path


def cleanup_staging(staging_dir):
    """Always called, success or failure — removes the temp staging dir."""
    shutil.rmtree(staging_dir, ignore_errors=True)


def _sha256_of_file(path):
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
