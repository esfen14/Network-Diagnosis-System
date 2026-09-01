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
        "5693": "ncpa",
        "5666": "nrpe",
        "22": "ssh",
        "80": "http",
        "443": "https",
    }

    # Default hostname suffix given to discovered hosts: <ip>.<DOMAIN>
    # e.g. 192.168.130.10.test.local
    DOMAIN = "test.local"
    NCPA_PORT = "5693"

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