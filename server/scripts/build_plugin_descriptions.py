"""
build_plugin_descriptions.py - Regenerates app/api/plugin/plugin_catalog_data.py.

Plugin Manager shows a description, a category and a documentation link for
each plugin. The server never fetches these from the internet at runtime
(offline installs, SSRF surface, latency); this script builds them once, at
development time, and the result is committed.

Sources
-------
  - "spec files/Plugins_List.md": the **Purpose** line of every catalogued
    nagios-plugins 2.4.12 plugin (built from the real plugin source).
  - The official nagios-plugins manual pages
    (https://www.nagios-plugins.org/doc/man/check_<name>.html), whose opening
    sentence ("This plugin tests ...") supplies the plugins the catalog does
    not list: check_ftp and check_udp (see EXTRA_DESCRIPTIONS).
  - CATEGORIES below, a hand-curated grouping for the Plugin Manager.

Run from the server/ directory:

    python scripts/build_plugin_descriptions.py          # rewrite the file
    python scripts/build_plugin_descriptions.py --check  # exit 1 if out of date

Re-run it when Plugins_List.md or the bundled plugin set changes.
"""
import argparse
import re
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent
CATALOG_MD = SERVER_DIR.parent / "spec files" / "Plugins_List.md"
OUTPUT = SERVER_DIR / "app" / "api" / "plugin" / "plugin_catalog_data.py"

DOC_URL = "https://www.nagios-plugins.org/doc/man/{page}.html"

# check_ldaps and check_ldap share one manual page.
DOC_PAGE_ALIASES = {"check_ldaps": "check_ldap"}

# check_ncpa belongs to the NCPA project, not nagios-plugins, so the
# nagios-plugins manual has no page for it (checked against the manual index).
DOC_URL_OVERRIDES = {"check_ncpa": "https://www.nagios.org/ncpa/"}

# Plugins that exist in nagios-plugins 2.4.12 but are not in Plugins_List.md.
# Wording follows the opening sentence of each official manual page.
EXTRA_DESCRIPTIONS = {
    "check_ftp": "Test FTP connections with the specified host (or unix socket).",
    "check_udp": "Test UDP connections with the specified host (or unix socket).",
}

# Plugins_List.md lists check_ntp twice (a deprecated C build and a Perl
# replacement installed under the same filename). One entry covers both.
DESCRIPTION_OVERRIDES = {
    "check_ntp": (
        "Check NTP time offset and jitter via ntpdate + ntpq. The older C build "
        "is deprecated; prefer check_ntp_time or check_ntp_peer."
    ),
}

CATEGORIES = {
    "Connectivity": [
        "check_icmp", "check_ping", "check_fping", "check_tcp", "check_udp", "check_dhcp",
    ],
    "DNS & Time": [
        "check_dns", "check_dig", "check_ntp", "check_ntp_peer", "check_ntp_time", "check_time",
    ],
    "Network Services": [
        "check_ssh", "check_ftp", "check_ldap", "check_ldaps", "check_ircd", "check_radius",
        "check_real", "check_rpc", "check_game", "check_by_ssh",
    ],
    "Web": ["check_http", "check_ssl_validity"],
    "Mail": ["check_smtp", "check_mailq"],
    "Database": [
        "check_dbi", "check_mysql", "check_mysql_query", "check_pgsql", "check_oracle",
    ],
    "SNMP & Devices": [
        "check_snmp", "check_ifoperstatus", "check_ifstatus", "check_breeze", "check_hpjd",
        "check_wave", "check_mrtg", "check_mrtgtraf",
    ],
    "Agents": ["check_ncpa", "check_nt", "check_nwstat", "check_overcr"],
    "System": [
        "check_apt", "check_load", "check_procs", "check_swap", "check_users", "check_uptime",
        "check_log", "check_file_age", "check_nagios",
    ],
    "Storage": ["check_disk", "check_disk_smb"],
    "Hardware": ["check_ide_smart", "check_sensors", "check_ups"],
    "Utility": ["check_dummy", "check_cluster", "check_flexlm"],
}

HEADING = re.compile(r"^## \d+\. (check_\w+(?: / check_\w+)*)")
PURPOSE = re.compile(r"^\*\*Purpose\*\*: (.+?)\s*$")


def parse_catalog(text):
    """Return {plugin_name: purpose} from Plugins_List.md (first entry wins)."""
    purposes = {}
    names = []
    for line in text.splitlines():
        heading = HEADING.match(line)
        if heading:
            names = [part.strip() for part in heading.group(1).split("/")]
            continue
        purpose = PURPOSE.match(line)
        if purpose and names:
            for name in names:
                purposes.setdefault(name, purpose.group(1))
            names = []
    return purposes


def sentence(text):
    """Make a description a complete sentence."""
    text = " ".join(text.split())
    return text if text.endswith((".", "!", "?")) else text + "."


def build_entries(purposes):
    """Return {name: {description, category, documentation_url}}."""
    category_of = {}
    for category, members in CATEGORIES.items():
        for name in members:
            category_of[name] = category

    descriptions = dict(purposes)
    descriptions.update(EXTRA_DESCRIPTIONS)
    descriptions.update(DESCRIPTION_OVERRIDES)

    missing = sorted(set(descriptions) - set(category_of))
    if missing:
        raise SystemExit(f"No category for: {', '.join(missing)}. Add them to CATEGORIES.")
    unknown = sorted(set(category_of) - set(descriptions))
    if unknown:
        raise SystemExit(f"Category without a description source: {', '.join(unknown)}.")

    entries = {}
    for name in sorted(descriptions):
        page = DOC_PAGE_ALIASES.get(name, name)
        entries[name] = {
            "description": sentence(descriptions[name]),
            "category": category_of[name],
            "documentation_url": DOC_URL_OVERRIDES.get(name) or DOC_URL.format(page=page),
        }
    return entries


def render(entries):
    """Return the generated module's source."""
    lines = [
        '"""',
        "plugin_catalog_data.py - Descriptions, categories and documentation links for",
        "the bundled nagios-plugins 2.4.12 set.",
        "",
        "GENERATED by server/scripts/build_plugin_descriptions.py. Do not edit by hand;",
        "change the script's inputs and re-run it. Lookup helpers live in",
        "plugin_descriptions.py.",
        '"""',
        "",
        "PLUGIN_CATALOG = {",
    ]
    for name, entry in entries.items():
        lines.append(f"    {name!r}: {{")
        for key in ("description", "category", "documentation_url"):
            lines.append(f"        {key!r}: {entry[key]!r},")
        lines.append("    },")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if the file is out of date")
    args = parser.parse_args()

    purposes = parse_catalog(CATALOG_MD.read_text(encoding="utf-8"))
    rendered = render(build_entries(purposes))

    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != rendered:
            print(f"{OUTPUT} is out of date; run scripts/build_plugin_descriptions.py")
            return 1
        print("plugin_catalog_data.py is up to date")
        return 0

    OUTPUT.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"Wrote {len(purposes) + len(EXTRA_DESCRIPTIONS)} plugin entries to {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
