"""
plugin_update.py — Handles Phase 9 (Updates): receiving an update
archive (uploaded or downloaded), safely extracting it, and backing
up/restoring the plugin file being replaced.

Kept separate from custom_plugin.py (Phase 8) because this is a
genuinely different workflow: Phase 8 receives one plugin executable
directly; this receives a compressed ARCHIVE (matching how
nagios-plugins itself ships, e.g. nagios-plugins-2.4.12.tar.gz, per
install-nagios-plugins.sh) that may contain multiple files, only one
of which is the plugin actually being updated.

SECURITY NOTES (two real, separate concerns handled here):
  1. Archive extraction ("zip-slip"/"tar-slip"): a malicious archive
     member can use ".." in its name to write outside the intended
     extraction directory. Every member's resolved path is checked
     BEFORE any extraction happens. Symlink/hardlink members are
     rejected outright — a classic follow-up exploit is a symlink
     member pointing outside the extraction dir, then a later member
     written "through" it.
  2. URL download (SSRF): confirmed scope includes admin-provided
     URLs, which means this server can be made to issue an outbound
     HTTP request to wherever that URL points. validate_download_url()
     resolves the hostname and rejects private/loopback/link-local/
     reserved IP ranges before ever making the request.
"""
import ipaddress
import os
import shutil
import socket
import tarfile
import tempfile
import zipfile
from urllib.parse import urlparse

import requests

from app.api.plugin.scanner import NAGIOS_PLUGIN_DIR

MAX_ARCHIVE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB — archives can bundle multiple plugins
DOWNLOAD_TIMEOUT_SECONDS = 15
BACKUP_DIR_NAME = ".pinpoint_backups"

SUPPORTED_EXTENSIONS = (".tar.gz", ".tgz", ".zip")


class InvalidUrlError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class DownloadError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class ArchiveTooLargeError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class UnsupportedArchiveError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class UnsafeArchiveError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class PluginNotInArchiveError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class NoBackupAvailableError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def validate_download_url(url):
    """
    SSRF guard: only http/https, and the hostname must not resolve to
    a private/loopback/link-local/reserved address. Confirmed scope:
    URL-based download is explicitly supported, so this is the
    mitigation that makes that safe to allow at all.

    Raises:
        InvalidUrlError
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise InvalidUrlError(f"URL scheme must be http or https, got '{parsed.scheme}'.")

    hostname = parsed.hostname
    if not hostname:
        raise InvalidUrlError("URL has no hostname.")

    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise InvalidUrlError(f"Could not resolve hostname '{hostname}': {e}")

    for family, _, _, _, sockaddr in addr_info:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise InvalidUrlError(
                f"URL resolves to a private/internal address ({ip}) — not allowed."
            )


def receive_archive(file_storage=None, url=None):
    """
    Stages an update archive, either from an uploaded file or a
    downloaded URL (exactly one must be given). Confirmed scope: both
    input methods are supported.

    Returns:
        (archive_path: str, staging_dir: str)

    Raises:
        InvalidUrlError, DownloadError, ArchiveTooLargeError,
        UnsupportedArchiveError
    """
    if bool(file_storage) == bool(url):
        raise ValueError("Provide exactly one of file_storage or url.")

    staging_dir = tempfile.mkdtemp(prefix="pinpoint_plugin_update_")

    try:
        if file_storage:
            filename = file_storage.filename or ""
            if not filename.lower().endswith(SUPPORTED_EXTENSIONS):
                raise UnsupportedArchiveError(
                    f"'{filename}' is not a supported archive type ({', '.join(SUPPORTED_EXTENSIONS)})."
                )
            archive_path = os.path.join(staging_dir, os.path.basename(filename))
            file_storage.save(archive_path)

        else:
            validate_download_url(url)
            filename = os.path.basename(urlparse(url).path) or "download.archive"
            if not filename.lower().endswith(SUPPORTED_EXTENSIONS):
                raise UnsupportedArchiveError(
                    f"URL does not point to a supported archive type ({', '.join(SUPPORTED_EXTENSIONS)})."
                )
            archive_path = os.path.join(staging_dir, filename)

            try:
                with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT_SECONDS) as resp:
                    resp.raise_for_status()
                    total = 0
                    with open(archive_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            total += len(chunk)
                            if total > MAX_ARCHIVE_SIZE_BYTES:
                                raise ArchiveTooLargeError(
                                    f"Download exceeded the {MAX_ARCHIVE_SIZE_BYTES}-byte limit."
                                )
                            f.write(chunk)
            except requests.RequestException as e:
                raise DownloadError(f"Failed to download archive: {e}")

        size_bytes = os.path.getsize(archive_path)
        if size_bytes > MAX_ARCHIVE_SIZE_BYTES:
            raise ArchiveTooLargeError(
                f"Archive is {size_bytes} bytes, exceeding the {MAX_ARCHIVE_SIZE_BYTES}-byte limit."
            )

        return archive_path, staging_dir

    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def _is_within_directory(base_dir, target_path):
    base = os.path.realpath(base_dir)
    target = os.path.realpath(target_path)
    return target == base or target.startswith(base + os.sep)


def extract_archive(archive_path, dest_dir):
    """
    Safely extracts a .tar.gz/.tgz/.zip archive. Every member's
    resolved destination path is validated to stay within dest_dir
    BEFORE any extraction happens (prevents "zip-slip"/"tar-slip" path
    traversal). Symlink/hardlink members are rejected outright.

    Raises:
        UnsupportedArchiveError, UnsafeArchiveError
    """
    lower = archive_path.lower()

    if lower.endswith(".tar.gz") or lower.endswith(".tgz"):
        with tarfile.open(archive_path, "r:gz") as tar:
            for member in tar.getmembers():
                if member.issym() or member.islnk():
                    raise UnsafeArchiveError(
                        f"Archive contains a symlink/hardlink member ('{member.name}') — rejected."
                    )
                target = os.path.join(dest_dir, member.name)
                if not _is_within_directory(dest_dir, target):
                    raise UnsafeArchiveError(
                        f"Archive member '{member.name}' would extract outside the target directory."
                    )
            tar.extractall(dest_dir, filter='data')  # safe: every member validated above, plus Python's own PEP 706 filter

    elif lower.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as zf:
            for name in zf.namelist():
                target = os.path.join(dest_dir, name)
                if not _is_within_directory(dest_dir, target):
                    raise UnsafeArchiveError(
                        f"Archive member '{name}' would extract outside the target directory."
                    )
            zf.extractall(dest_dir)

    else:
        raise UnsupportedArchiveError(f"Unsupported archive type: {archive_path}")


def find_plugin_in_extracted(extracted_dir, plugin_name):
    """
    Locates the specific file matching plugin_name within the
    extracted archive contents (searched recursively, since archives
    commonly nest files under a version-named folder, e.g.
    nagios-plugins-2.4.13/check_snmp).

    Confirmed scope (Implementation Plan Section 18, Phase 9 IMPORTANT
    note): "Individual extracted plugins are the managed units...
    Updating one plugin must not automatically replace every plugin."
    This deliberately returns only the ONE matching file — everything
    else extracted from the archive is ignored, not installed.

    Raises:
        PluginNotInArchiveError
    """
    for root, _dirs, files in os.walk(extracted_dir):
        if plugin_name in files:
            return os.path.join(root, plugin_name)

    raise PluginNotInArchiveError(
        f"No file named '{plugin_name}' was found anywhere in the archive."
    )


def backup_plugin(plugin_name, current_executable_path):
    """
    Copies the currently-installed file to a single backup slot for
    this plugin (overwriting any previous backup) BEFORE it gets
    replaced. Confirmed scope: UI Flow Section 22 shows "Rollback:
    Available" even after a SUCCESSFUL update, so this backup persists
    until the NEXT update, not just until the current one finishes.

    Returns:
        the backup file path (str)
    """
    backup_dir = os.path.join(NAGIOS_PLUGIN_DIR, BACKUP_DIR_NAME)
    os.makedirs(backup_dir, exist_ok=True)
    backup_path = os.path.join(backup_dir, plugin_name)
    shutil.copy2(current_executable_path, backup_path)
    return backup_path


def get_backup_path(plugin_name):
    return os.path.join(NAGIOS_PLUGIN_DIR, BACKUP_DIR_NAME, plugin_name)


def has_backup(plugin_name):
    return os.path.exists(get_backup_path(plugin_name))


def replace_plugin(new_file_path, target_path):
    """Installs the new file over the currently-installed one. Only
    called after backup_plugin() has already succeeded."""
    shutil.copy2(new_file_path, target_path)
    os.chmod(target_path, 0o755)


def restore_from_backup(plugin_name, target_path):
    """
    The manual rollback action: copies the backed-up file back over
    the (possibly broken) currently-installed file.

    Raises:
        NoBackupAvailableError
    """
    backup_path = get_backup_path(plugin_name)
    if not os.path.exists(backup_path):
        raise NoBackupAvailableError(f"No backup is available for '{plugin_name}'.")

    shutil.copy2(backup_path, target_path)
    os.chmod(target_path, 0o755)


def cleanup_staging(staging_dir):
    shutil.rmtree(staging_dir, ignore_errors=True)
