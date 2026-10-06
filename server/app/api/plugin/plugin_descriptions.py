"""
plugin_descriptions.py — Descriptions, categories and documentation links for
Plugin Manager plugins.

The bundled nagios-plugins set is described by plugin_catalog_data.py, a file
generated at development time by scripts/build_plugin_descriptions.py. Nothing
here contacts the internet: the server must not fetch documentation when a page
loads (offline installs, SSRF surface, latency).

A plugin that is not in the catalog (custom or non-standard) falls back to the
first descriptive paragraph of its own `--help` output, read at scan time with
the same safe, bounded invocation the scanner already uses for `--version`.

Fields an administrator or a custom upload already set are never overwritten.
"""
import re
import subprocess

from app.api.plugin.plugin_catalog_data import PLUGIN_CATALOG

HELP_TIMEOUT_SECONDS = 5
MAX_DESCRIPTION_LENGTH = 500   # PLUGIN.Description column size
MAX_CATEGORY_LENGTH = 50       # PLUGIN.Category column size

# Paragraphs of `--help` output that are not a description of the plugin.
_VERSION_HEADER = re.compile(r"^\S+\s+v?\d+\.\d+")
_BOILERPLATE_PREFIXES = ("copyright", "the nagios plugins come", "this nagios plugin")
_STOP_PREFIXES = ("usage", "options", "-")
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def get_catalog_entry(name):
    """
    Return the catalog entry for a plugin name as
    {"description", "category", "documentation_url"}, or None if the plugin is
    not part of the bundled set. Does not touch the database or filesystem.
    """
    return PLUGIN_CATALOG.get(name)


def documentation_url(name):
    """Return the documentation link for a catalogued plugin, or None."""
    entry = get_catalog_entry(name)
    return entry["documentation_url"] if entry else None


def clean_text(text, limit):
    """
    Collapse whitespace, drop control characters and cut text to limit
    characters (ending in an ellipsis when cut). Returns None if nothing is
    left.
    """
    text = " ".join(_CONTROL_CHARACTERS.sub("", str(text or "")).split())
    if not text:
        return None
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def parse_help_description(output):
    """
    Pick the plugin's description out of its `--help` output: the first
    paragraph that is not the version/copyright header, the warranty notice or
    the "Usage:" section. Returns None if there is no such paragraph.
    """
    for paragraph in re.split(r"\n\s*\n", str(output or "")):
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        if not lines:
            continue

        first = lines[0].lower()
        if first.startswith(_STOP_PREFIXES):
            # Usage and option documentation follow the description.
            return None
        if (_VERSION_HEADER.match(lines[0]) or first.startswith(_BOILERPLATE_PREFIXES)
                or "absolutely no warranty" in paragraph.lower()):
            continue

        text = clean_text(" ".join(lines), MAX_DESCRIPTION_LENGTH)
        if text and len(text) >= 10:
            return text
    return None


def extract_help_description(plugin_path):
    """
    Best-effort: run `<plugin_path> --help` locally and return its description
    paragraph. Never raises; any failure (unsupported flag, timeout, no usable
    text) returns None. Only call this for files the scanner already accepted
    as real plugin programs, since it executes the file.
    """
    try:
        result = subprocess.run(
            [plugin_path, "--help"],
            capture_output=True,
            text=True,
            timeout=HELP_TIMEOUT_SECONDS,
        )
    except Exception:
        return None

    return parse_help_description((result.stdout or "") + "\n\n" + (result.stderr or ""))


def fill_missing_metadata(plugin, fallback_description=None):
    """
    Fill an empty Description and Category on a Plugin row from the catalog,
    or (Description only) from fallback_description when the plugin is not
    catalogued. Values that are already set are left alone. Returns True if
    anything changed. Does not commit.
    """
    changed = False
    entry = get_catalog_entry(plugin.Name)

    if not plugin.Description:
        description = entry["description"] if entry else fallback_description
        description = clean_text(description, MAX_DESCRIPTION_LENGTH)
        if description:
            plugin.Description = description
            changed = True

    if not plugin.Category and entry:
        plugin.Category = clean_text(entry["category"], MAX_CATEGORY_LENGTH)
        changed = changed or bool(plugin.Category)

    return changed
