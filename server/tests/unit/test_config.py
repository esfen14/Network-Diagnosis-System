"""
tests/unit/test_config.py — Tests for environment-driven settings in
server/config.py.

Config values are computed when the class body runs, so each test loads a
fresh, private copy of config.py after setting the environment. The shared
`config` module used by the app is never touched.
"""
import importlib.util
import os
from pathlib import Path

import pytest

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.py"

ENV_VARS = [
    "SECRET_KEY",
    "NAGIOS_HOST",
    "NAGIOS_PORT",
    "NAGIOS_USERNAME",
    "NAGIOS_PASSWORD",
    "PINPOINT_NETWORKS",
    "PINPOINT_DOMAIN",
]


def load_config(monkeypatch, **env):
    """
    Clear the settings under test, apply env, and return a freshly executed
    Config class from config.py.
    """
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    spec = importlib.util.spec_from_file_location("config_under_test", CONFIG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Config


class TestNagiosUrls:

    def test_defaults_to_localhost_port_80(self, monkeypatch):
        cfg = load_config(monkeypatch)
        assert cfg.NAGIOS_STATUS_URL == "http://127.0.0.1:80/nagios/cgi-bin/statusjson.cgi"

    def test_separate_host_and_port(self, monkeypatch):
        cfg = load_config(monkeypatch, NAGIOS_HOST="127.0.0.1", NAGIOS_PORT="8081")
        assert cfg.NAGIOS_STATUS_URL == "http://127.0.0.1:8081/nagios/cgi-bin/statusjson.cgi"
        assert cfg.NAGIOS_ARCHIVE_URL == "http://127.0.0.1:8081/nagios/cgi-bin/archivejson.cgi"
        assert cfg.NAGIOS_OBJECT_URL == "http://127.0.0.1:8081/nagios/cgi-bin/objectjson.cgi"

    @pytest.mark.parametrize("port", [None, "8081", "80"])
    def test_legacy_host_with_port_is_not_doubled(self, monkeypatch, port):
        env = {"NAGIOS_HOST": "127.0.0.1:8081"}
        if port is not None:
            env["NAGIOS_PORT"] = port
        cfg = load_config(monkeypatch, **env)
        assert cfg.NAGIOS_STATUS_URL == "http://127.0.0.1:8081/nagios/cgi-bin/statusjson.cgi"


class TestSecrets:

    def test_no_source_fallbacks(self, monkeypatch):
        cfg = load_config(monkeypatch)
        assert cfg.SECRET_KEY is None
        assert cfg.NAGIOS_USERNAME is None
        assert cfg.NAGIOS_PASSWORD is None

    def test_read_from_environment(self, monkeypatch):
        cfg = load_config(
            monkeypatch,
            SECRET_KEY="abc",
            NAGIOS_USERNAME="pinpoint-api",
            NAGIOS_PASSWORD="pw",
        )
        assert cfg.SECRET_KEY == "abc"
        assert cfg.NAGIOS_USERNAME == "pinpoint-api"
        assert cfg.NAGIOS_PASSWORD == "pw"


class TestNetworkSettings:

    def test_networks_default(self, monkeypatch):
        cfg = load_config(monkeypatch)
        assert cfg.NETWORKS == ["192.168.130.0/24"]

    def test_networks_from_comma_list(self, monkeypatch):
        cfg = load_config(monkeypatch, PINPOINT_NETWORKS=" 192.168.50.0/24, 10.0.0.0/24 ,")
        assert cfg.NETWORKS == ["192.168.50.0/24", "10.0.0.0/24"]

    def test_domain(self, monkeypatch):
        assert load_config(monkeypatch).DOMAIN == "test.local"
        assert load_config(monkeypatch, PINPOINT_DOMAIN="pinpoint.lan").DOMAIN == "pinpoint.lan"
