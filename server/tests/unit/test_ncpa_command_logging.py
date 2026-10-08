"""NCPA command logging and bootstrap probes, with SSH entirely mocked."""
import logging
from unittest.mock import MagicMock

import pytest

import app.ncpa_deployment.ncpa_deployment as worker


def ssh_result(code, stderr=b""):
    """Build the three SSH streams for a single command without a connection."""
    stdin, stdout, errors = MagicMock(), MagicMock(), MagicMock()
    stdout.read.return_value = b""
    errors.read.return_value = stderr
    stdout.channel.recv_exit_status.return_value = code
    return stdin, stdout, errors


@pytest.mark.parametrize("sudo", [False, True])
@pytest.mark.parametrize("code,expected,level", [
    (1, (1,), logging.INFO), (2, (1, 2), logging.INFO),
    (1, (), logging.ERROR), (3, (1, 2), logging.ERROR),
])
def test_nonzero_exit_preserves_failure(app, caplog, sudo, code, expected, level):
    client = MagicMock()
    client.exec_command.return_value = ssh_result(code)
    helper = worker.run_sudo_command if sudo else worker.run_command
    args = (client, "test-command", "") if sudo else (client, "test-command")
    with app.app_context(), caplog.at_level(logging.INFO):
        result = helper(*args, expected_exit_codes=expected)
    assert result["success"] is False
    assert [record.levelno for record in caplog.records] == [level]


@pytest.mark.parametrize("sudo", [False, True])
def test_success_with_stderr_still_warns(app, caplog, sudo):
    client = MagicMock()
    client.exec_command.return_value = ssh_result(0, b"notice")
    helper = worker.run_sudo_command if sudo else worker.run_command
    args = (client, "test-command", "") if sudo else (client, "test-command")
    with app.app_context(), caplog.at_level(logging.INFO):
        assert helper(*args)["success"] is True
    assert [record.levelno for record in caplog.records] == [logging.WARNING]


@pytest.mark.parametrize("code,count", [(0, 1), (1, 2)])
def test_account_probe_creates_only_missing_account(app, caplog, code, count):
    client = MagicMock()
    client.exec_command.side_effect = [ssh_result(code), ssh_result(0)]
    with app.app_context(), caplog.at_level(logging.INFO):
        assert worker.ensure_deployment_user(client, "") is True
    commands = [call.args[0] for call in client.exec_command.call_args_list]
    assert len(commands) == count
    if code:
        assert "useradd" in commands[1]
        assert any(record.levelno == logging.INFO for record in caplog.records)
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)


@pytest.mark.parametrize("code,count", [(0, 5), (1, 6), (2, 6)])
def test_key_probe_adds_only_missing_key(app, caplog, monkeypatch, tmp_path, code, count):
    public_key = tmp_path / "deployment.pub"
    public_key.write_text("ssh-ed25519 public-test-key")
    monkeypatch.setattr(worker, "PUBLIC_KEY_PATH", str(public_key))
    client = MagicMock()
    client.exec_command.side_effect = [ssh_result(0), ssh_result(code)] + [ssh_result(0) for _ in range(4)]
    with app.app_context(), caplog.at_level(logging.INFO):
        assert worker.install_deployment_key(client, "") is True
    commands = [call.args[0] for call in client.exec_command.call_args_list]
    assert len(commands) == count
    assert any("printf" in command for command in commands) is bool(code)
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)
