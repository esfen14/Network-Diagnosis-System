import os
from pathlib import Path

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or "1VMBzjR2m/0kF7eqw5d5zy_Gk<j-M5<Ga4C^d"
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
    NETWORKS = ["192.168.130.0/24"]
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
    DOMAIN = "test.local"
    NCPA_PORT = "5693"

    # SNMP polling settings, used when a discovered host exposes SNMP
    # instead of (or alongside) NCPA/NRPE.
    SNMP_COMMUNITY_STRING = os.environ.get('SNMP_COMMUNITY_STRING') or "public"
    SNMP_PORT = "161"
    SNMP_OID = {
        "1.3.6.1.2.1.1.3.0": "uptime",
        "1.3.6.1.2.1.1.1.0": "system_description",
        "1.3.6.1.2.1.2.2.1.8.3": "lan_status",
        "1.3.6.1.2.1.2.2.1.10.3": "lan_in_octets",
        "1.3.6.1.2.1.2.2.1.16.3": "lan_out_octets",
        "1.3.6.1.4.1.2021.4.5.0": "memory_total",
    }

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

    # Nagios web/API host, used to build the status + archive JSON CGI
    # endpoints. Override via env if Nagios runs elsewhere (e.g. Docker).
    NAGIOS_HOST = os.environ.get('NAGIOS_HOST') or "192.168.130.10"
    NAGIOS_STATUS_URL = f"http://{NAGIOS_HOST}/nagios/cgi-bin/statusjson.cgi"
    NAGIOS_ARCHIVE_URL = f"http://{NAGIOS_HOST}/nagios/cgi-bin/archivejson.cgi"
    NAGIOS_USERNAME = os.environ.get('NAGIOS_USERNAME') or "nagiosadmin"
    NAGIOS_PASSWORD = os.environ.get('NAGIOS_PASSWORD') or "password"

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
