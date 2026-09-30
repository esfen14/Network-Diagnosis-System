import os
from pathlib import Path

basedir = os.path.abspath(os.path.dirname(__file__))


def env_list(name, default):
    """
    Read a comma-separated environment variable into a list of stripped,
    non-empty strings. Returns default when the variable is unset or empty.
    """
    value = os.environ.get(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


class Config:
    # No fallback: a secret committed to source lets anyone forge sessions.
    # app/__init__.py refuses to start without it outside debug mode.
    SECRET_KEY = os.environ.get('SECRET_KEY')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'system.db')
    SQLALCHEMY_BINDS = {
        "history": "sqlite:///" +  os.path.join(basedir, 'history.db')
    }

    """
    |------------------------------------------------------------------
    | Network discovery / host-config generation settings
    |
    | Centralized here (accessed via current_app.config[...]) instead of
    | as module-level constants scattered across network_discovery.py and
    | create_host_cfg.py, so they can eventually be surfaced and edited
    | through a Settings UI without touching source files.
    |------------------------------------------------------------------
    """

    # What networks/ports network_discovery.py scans with nmap.
    # NOTE: localhost should never be added here — scanning it can crash
    # or hang the discovery process.
    # Override with PINPOINT_NETWORKS, e.g. "192.168.50.0/24,10.0.0.0/24".
    NETWORKS = env_list('PINPOINT_NETWORKS', ["192.168.130.0/24"])
    TCP_PORTS = ["1-6000"]
    UDP_PORTS = [53, 67, 68, 69, 123, 161, 162, 514]

    # What service names to assign to well-known ports from nmap results.
    TCP_SERVICE_OVERRIDES = {
        "5693": "ncpa",
        "5666": "nrpe",
        "22": "ssh",
        "80": "http",
        "443": "https",
    }
    UDP_SERVICE_OVERRIDES = {
        "5666": "nrpe",
        "22": "ssh",
        "80": "http",
        "443": "https",
        "161": "snmp",
    }

    # Default hostname suffix given to discovered hosts: <ip>.<DOMAIN>
    # e.g. 192.168.130.10.test.local
    DOMAIN = os.environ.get('PINPOINT_DOMAIN') or "test.local"
    NCPA_PORT = "5693"

    # SNMP polling defaults, used when a discovered host exposes SNMP
    # instead of (or alongside) NCPA. Each SNMP_OIDS entry becomes its own
    # Nagios service ("snmp-<metric>-<port>"); optional keys warning,
    # critical, label and units are passed to check_snmp for that service.
    # A host can override any of these (including the whole OID list) via
    # NetworkDiscovery.Plugin_Variables["snmp"] — see
    # network_discovery/plugin_registry.py.
    SNMP_COMMUNITY_STRING = os.environ.get('SNMP_COMMUNITY_STRING') or "public"
    SNMP_PORT = "161"
    SNMP_OIDS = [
        {"metric": "uptime", "oid": "1.3.6.1.2.1.1.3.0"},
        {"metric": "system_description", "oid": "1.3.6.1.2.1.1.1.0"},
        {"metric": "lan_status", "oid": "1.3.6.1.2.1.2.2.1.8.3"},
        {"metric": "lan_in_octets", "oid": "1.3.6.1.2.1.2.2.1.10.3"},
        {"metric": "lan_out_octets", "oid": "1.3.6.1.2.1.2.2.1.16.3"},
        {"metric": "memory_total", "oid": "1.3.6.1.4.1.2021.4.5.0"},
    ]

    # NCPA metrics checked on every host with a deployed NCPA agent. Each
    # entry becomes its own Nagios service ("ncpa-<metric>-<port>"). A path
    # containing {partition} expands to one service per partition recorded
    # at install time (NCPADevicePartition), falling back to fallback_path
    # when none were recorded. Overridable per host via
    # NetworkDiscovery.Plugin_Variables["ncpa"].
    NCPA_METRICS = [
        {"metric": "cpu", "path": "cpu/percent", "warning": "50", "critical": "80", "queryargs": "aggregate=avg"},
        {"metric": "memory", "path": "memory/virtual/percent", "warning": "50", "critical": "80", "units": "Gi"},
        {
            "metric": "disk",
            "path": "disk/logical/{partition}/percent",
            "fallback_path": "disk/logical/percent",
            "warning": "70",
            "critical": "95",
        },
    ]

    # Folders where generated/backed-up host configs are stored.
    HOST_CONFIG_DIR = Path(basedir) / "host-config-files"
    BACKUP_DIR = Path(basedir) / "running-host-config-backup"

    """
    |------------------------------------------------------------------
    | Advanced settings — Nagios integration
    |------------------------------------------------------------------
    """

    # Live Nagios config/binary paths, needed for -v validation and
    # applying generated host configs.
    NAGIOS_HOST_CFG = Path(os.environ.get('NAGIOS_HOST_CFG') or "/usr/local/nagios/etc/objects/hosts.cfg")
    NAGIOS_BIN = Path(os.environ.get('NAGIOS_BIN') or "/usr/local/nagios/bin/nagios")
    NAGIOS_MAIN_CFG = Path(os.environ.get('NAGIOS_MAIN_CFG') or "/usr/local/nagios/etc/nagios.cfg")

    # Nagios web/API host and port, used to build the status, archive and
    # object JSON CGI endpoints. Override via env if Nagios runs elsewhere
    # (e.g. Docker, or the installer's 127.0.0.1:8081).
    NAGIOS_HOST = os.environ.get('NAGIOS_HOST') or "127.0.0.1"
    NAGIOS_PORT = os.environ.get('NAGIOS_PORT') or "80"

    # Older installs pack the port into NAGIOS_HOST ("127.0.0.1:8081").
    # Keep accepting that form so they don't end up with "host:8081:8081".
    if ":" in NAGIOS_HOST:
        NAGIOS_BASE_URL = f"http://{NAGIOS_HOST}"
    else:
        NAGIOS_BASE_URL = f"http://{NAGIOS_HOST}:{NAGIOS_PORT}"

    NAGIOS_STATUS_URL = f"{NAGIOS_BASE_URL}/nagios/cgi-bin/statusjson.cgi"
    NAGIOS_ARCHIVE_URL = f"{NAGIOS_BASE_URL}/nagios/cgi-bin/archivejson.cgi"
    NAGIOS_OBJECT_URL = f"{NAGIOS_BASE_URL}/nagios/cgi-bin/objectjson.cgi"

    # No defaults: set these per server (the installer creates a dedicated
    # Nagios API account). For local development put them in server/.env.
    NAGIOS_USERNAME = os.environ.get('NAGIOS_USERNAME')
    NAGIOS_PASSWORD = os.environ.get('NAGIOS_PASSWORD')

    """
    |------------------------------------------------------------------
    | Plugin Manager settings
    |------------------------------------------------------------------
    """

    # Directory Nagios loads plugin executables from. Scanned for the
    # plugin inventory; custom uploads and updates are installed here.
    # Override via env to point at a local folder on a dev machine.
    NAGIOS_PLUGIN_DIR = os.environ.get('NAGIOS_PLUGIN_DIR') or "/usr/local/nagios/libexec/"

    # Nagios config file holding Plugin Manager's generated command and
    # service objects. Kept separate from NAGIOS_HOST_CFG because
    # Network Discovery fully regenerates hosts.cfg on every scan.
    PLUGIN_SERVICE_CFG = Path(os.environ.get('PLUGIN_SERVICE_CFG') or "/usr/local/nagios/etc/objects/plugin-services.cfg")

    # Folders where candidate/backed-up plugin service configs are stored.
    PLUGIN_SERVICE_STAGING_DIR = Path(basedir) / "plugin-service-config-files"
    PLUGIN_SERVICE_BACKUP_DIR = Path(basedir) / "running-plugin-service-config-backup"

    """
    |------------------------------------------------------------------
    | Scheduled automation (app/automation.py)
    |------------------------------------------------------------------
    """

    # How often the scheduler checks whether a scheduled scan, update
    # check, security check or backup is due.
    AUTOMATION_CHECK_MINUTES = 5

    # Where automatic database backups are written, and how many of the
    # most recent backups to keep. Older ones are deleted.
    DATABASE_BACKUP_DIR = Path(os.environ.get('DATABASE_BACKUP_DIR') or Path(basedir) / "database-backups")
    DATABASE_BACKUP_KEEP = 7
