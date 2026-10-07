"""
tests/unit/test_ncpa_deployment_runs.py — NCPA deployment runs, per-device
outcomes, trust confirmation, login checks and run review.

Covers "docs/plans/NCPA_Deployment_UI_Plan.md" sections 3 to 6. SSH is
always mocked; no test opens a network connection.

Endpoints tested (all under /api/system/deployment/ncpa/):
  GET  /devices                  (extended fields)
  GET  /<id>/fingerprint         (unreachable)
  POST /<id>/confirm-trust       (approved fingerprint only)
  POST /check-credentials
  POST /start                    (validation, rejections, run rows)
  GET  /status                   (per-device results)
  GET  /runs, /runs/<id>
  POST /runs/<id>/review
  GET  /devices/trusted          (failed devices can be retried)

Worker functions tested: install_process, give_program_permissions,
check_device_credentials.
"""
import logging
import socket
import threading
from unittest.mock import patch, MagicMock

import paramiko
import pytest
import sqlalchemy as sa

import app.api.system.ncpa_deployment as routes
import app.ncpa_deployment.ncpa_deployment as worker
from app import db
from app.logging.deployment_history import create_ncpa_deployment_status, add_deployment_result
from app.system_models import (
    ActivityLog,
    AgentStatus,
    DeploymentOutcome,
    DeploymentStatus,
    DiscoveryStatus,
    NCPADeployment,
    NCPADeploymentResult,
    NCPADeploymentStatus,
    NetworkDiscovery,
    NetworkDiscoveryStatus,
    SSHCredentials,
)

BASE = "/api/system/deployment/ncpa"
FINGERPRINT = "q8Zk4m1XvT2Lr9bN0cYwJ5sHf7aEeP3uD6gKiOtR1lM"
PASSWORD = "S3cret-deploy-pass"


# ─── Seeding helpers ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_module_state():
    """Each test starts with no running thread and no recent login checks."""
    routes.credential_check_times.clear()
    with patch.object(routes, "deploy_ncpa_thread", None):
        yield
    routes.credential_check_times.clear()


def make_device(db_session, admin_user, hostname="web-01", ip="10.0.20.11", trusted=True,
                agent_status=AgentStatus.PENDING_NCPA, eligible=True, include=True, ssh_port=22):
    """A discovered device with SSH_CREDENTIALS and an NCPA_DEPLOYMENT row."""
    log = ActivityLog(Action_Type="test", UserID=admin_user.UserID)
    db_session.session.add(log)
    db_session.session.flush()
    status = NetworkDiscoveryStatus(Status=DiscoveryStatus.SUCCESS, Progress=100, Message="Done", LogID=log.LogID)
    db_session.session.add(status)
    db_session.session.flush()

    device = NetworkDiscovery(
        Hostname=hostname, IP_Address=ip, Network="10.0.20.0/24",
        NCPA_Eligible=eligible, Include_Device_In_Scanning=include,
        DiscoveryStatusID=status.DiscoveryStatusID,
    )
    db_session.session.add(device)
    db_session.session.flush()
    db_session.session.add(SSHCredentials(
        SSH_Port=ssh_port, Key_Installed=False, Key_Fingerprint=FINGERPRINT if trusted else None,
        NetworkDiscoveryID=device.NetDiscoveryID,
    ))
    if agent_status is not None:
        db_session.session.add(NCPADeployment(Agent_Status=agent_status, NetworkDiscoveryID=device.NetDiscoveryID))
    db_session.session.commit()
    return device


def make_run(admin_user, devices_outcomes, status=DeploymentStatus.SUCCESS):
    """A finished run with one result row per (device, outcome, error)."""
    run = create_ncpa_deployment_status(admin_user.UserID)
    run.Status = status
    run.Progress = 100
    for device, outcome, error in devices_outcomes:
        add_deployment_result(run.NCPADeployStatusID, device, outcome, error)
    db.session.commit()
    return run


def results_of(run_id):
    rows = db.session.scalars(
        sa.select(NCPADeploymentResult)
        .where(NCPADeploymentResult.NCPADeploymentStatusID == run_id)
        .order_by(NCPADeploymentResult.NCPADeployResultID)
    ).all()
    return [(row.NetworkDiscoveryID, row.Outcome, row.Error) for row in rows]


def creds(*device_ids, username="admin", password=PASSWORD):
    return {"devices": [{"device_id": d, "username": username, "password": password} for d in device_ids]}


# ─── Trust confirmation (plan §3.1, §3.2) ─────────────────────────────────────

class TestConfirmTrust:
    def url(self, device):
        return f"{BASE}/{device.NetDiscoveryID}/confirm-trust"

    def test_saves_the_fingerprint_the_user_approved(self, logged_in_client, db_session, admin_user):
        device = make_device(db_session, admin_user, trusted=False)
        with patch.object(routes, "get_host_key_fingerprint", return_value=FINGERPRINT):
            resp = logged_in_client.post(self.url(device), json={"fingerprint": FINGERPRINT})

        assert resp.status_code == 200
        saved = db.session.scalar(sa.select(SSHCredentials.Key_Fingerprint).where(
            SSHCredentials.NetworkDiscoveryID == device.NetDiscoveryID))
        assert saved == FINGERPRINT

    def test_a_key_that_changed_since_viewing_is_not_trusted(self, logged_in_client, db_session, admin_user):
        device = make_device(db_session, admin_user, trusted=False)
        with patch.object(routes, "get_host_key_fingerprint", return_value="NEWKEY"):
            resp = logged_in_client.post(self.url(device), json={"fingerprint": FINGERPRINT})

        assert resp.status_code == 409
        assert resp.get_json()["data"]["fingerprint"] == "NEWKEY"
        saved = db.session.scalar(sa.select(SSHCredentials.Key_Fingerprint).where(
            SSHCredentials.NetworkDiscoveryID == device.NetDiscoveryID))
        assert saved is None

    def test_unreachable_device_is_502(self, logged_in_client, db_session, admin_user):
        device = make_device(db_session, admin_user, trusted=False)
        with patch.object(routes, "get_host_key_fingerprint", return_value=None):
            resp = logged_in_client.post(self.url(device), json={"fingerprint": FINGERPRINT})
        assert resp.status_code == 502

    def test_the_approved_fingerprint_is_required(self, logged_in_client, db_session, admin_user):
        device = make_device(db_session, admin_user, trusted=False)
        resp = logged_in_client.post(self.url(device), json={"fingerprint": "  "})
        assert resp.status_code == 400


class TestFingerprint:
    def test_unreachable_device_is_502_not_an_empty_key(self, logged_in_client, db_session, admin_user):
        device = make_device(db_session, admin_user, trusted=False)
        # get_host_key_fingerprint returns None, rather than raising, when the host is down.
        with patch.object(routes, "get_host_key_fingerprint", return_value=None):
            resp = logged_in_client.get(f"{BASE}/{device.NetDiscoveryID}/fingerprint")
        assert resp.status_code == 502


# ─── POST /start (plan §3.3–3.7, §5) ──────────────────────────────────────────

class TestStart:
    def start(self, client, body, live_fingerprint=FINGERPRINT):
        thread = MagicMock()
        with patch.object(routes, "get_host_key_fingerprint", return_value=live_fingerprint), \
             patch.object(routes.threading, "Thread", return_value=thread) as thread_cls:
            resp = client.post(f"{BASE}/start", json=body)
        return resp, thread_cls

    def test_missing_password_is_400_and_starts_nothing(self, logged_in_client, db_session, admin_user):
        device = make_device(db_session, admin_user)
        resp, thread_cls = self.start(logged_in_client, creds(device.NetDiscoveryID, password=""))
        assert resp.status_code == 400
        assert "password" in resp.get_json()["message"]
        thread_cls.assert_not_called()

    def test_missing_username_is_400(self, logged_in_client, db_session, admin_user):
        device = make_device(db_session, admin_user)
        resp, _ = self.start(logged_in_client, {"devices": [{"device_id": device.NetDiscoveryID, "password": "p"}]})
        assert resp.status_code == 400

    def test_a_device_sent_twice_is_400(self, logged_in_client, db_session, admin_user):
        device = make_device(db_session, admin_user)
        resp, _ = self.start(logged_in_client, creds(device.NetDiscoveryID, device.NetDiscoveryID))
        assert resp.status_code == 400

    def test_unreachable_device_is_rejected_as_down(self, logged_in_client, db_session, admin_user):
        device = make_device(db_session, admin_user)
        resp, thread_cls = self.start(logged_in_client, creds(device.NetDiscoveryID), live_fingerprint=None)

        assert resp.status_code == 400
        assert resp.get_json()["data"]["rejected"] == [
            {"device_id": device.NetDiscoveryID, "reason": "Device unreachable."}]
        thread_cls.assert_not_called()
        assert db.session.scalar(sa.select(sa.func.count()).select_from(NCPADeploymentStatus)) == 0

    def test_changed_host_key_is_rejected(self, logged_in_client, db_session, admin_user):
        device = make_device(db_session, admin_user)
        resp, _ = self.start(logged_in_client, creds(device.NetDiscoveryID), live_fingerprint="OTHER")
        assert resp.get_json()["data"]["rejected"][0]["reason"] == "Host key mismatch."

    def test_deployed_and_incompatible_devices_are_rejected(self, logged_in_client, db_session, admin_user):
        deployed = make_device(db_session, admin_user, hostname="a", agent_status=AgentStatus.DEPLOYED)
        incompatible = make_device(db_session, admin_user, hostname="b", agent_status=AgentStatus.INCOMPATIBLE)
        resp, _ = self.start(logged_in_client, creds(deployed.NetDiscoveryID, incompatible.NetDiscoveryID))

        reasons = {r["device_id"]: r["reason"] for r in resp.get_json()["data"]["rejected"]}
        assert reasons[deployed.NetDiscoveryID] == "NCPA is already deployed."
        assert reasons[incompatible.NetDiscoveryID] == "Device cannot be deployed to (Incompatible)."

    def test_failed_device_can_be_retried_and_run_rows_are_created(self, logged_in_client, db_session, admin_user):
        failed = make_device(db_session, admin_user, hostname="app-03", agent_status=AgentStatus.FAILED)
        untrusted = make_device(db_session, admin_user, hostname="db-02", trusted=False)

        resp, thread_cls = self.start(logged_in_client, creds(failed.NetDiscoveryID, untrusted.NetDiscoveryID))

        assert resp.status_code == 202
        data = resp.get_json()["data"]
        assert data["started"] == 1
        assert data["rejected"] == [{"device_id": untrusted.NetDiscoveryID, "reason": "Not trust-confirmed."}]
        assert results_of(data["run_id"]) == [
            (untrusted.NetDiscoveryID, DeploymentOutcome.REJECTED, "Not trust-confirmed."),
            (failed.NetDiscoveryID, DeploymentOutcome.PENDING, None),
        ]
        # The worker gets the run ID and only the accepted device.
        args = thread_cls.call_args.kwargs["args"]
        assert args[1] == data["run_id"]
        assert [entry["device_id"] for entry in args[2]] == [failed.NetDiscoveryID]

    def test_the_password_is_never_stored_or_returned(self, logged_in_client, db_session, admin_user):
        device = make_device(db_session, admin_user)
        resp, _ = self.start(logged_in_client, creds(device.NetDiscoveryID))

        assert PASSWORD not in resp.get_data(as_text=True)
        run = db.session.get(NCPADeploymentStatus, resp.get_json()["data"]["run_id"])
        stored = " ".join(str(v) for v in (run.Message, run.Error, *[e for _, _, e in results_of(run.NCPADeployStatusID)]))
        assert PASSWORD not in stored


# ─── install_process: per-device outcomes (plan §5) ───────────────────────────

class TestInstallProcess:
    """The background worker with both device steps and add_ncpa_port mocked."""

    def run_worker(self, app, admin_user, devices, outcomes, stop=False, add_port=None, explode=False):
        run = create_ncpa_deployment_status(admin_user.UserID)
        for device in devices:
            add_deployment_result(run.NCPADeployStatusID, device, DeploymentOutcome.PENDING)
        db.session.commit()

        entries = [{"device_id": d.NetDiscoveryID, "ip_address": d.IP_Address, "username": "admin",
                    "password": PASSWORD} for d in devices]
        stop_event = threading.Event()
        if stop:
            stop_event.set()

        def deploy(device_id, *_args):
            if explode:
                raise RuntimeError("boom")
            return outcomes[device_id]

        with patch.object(worker, "deploy_device", side_effect=deploy), \
             patch.object(worker, "add_ncpa_port", side_effect=add_port) as add_ncpa_port:
            worker.install_process(app, run.NCPADeployStatusID, entries, stop_event)

        run = db.session.get(NCPADeploymentStatus, run.NCPADeployStatusID, populate_existing=True)
        return run, add_ncpa_port, entries

    def test_mixed_outcomes_are_a_partial_failure(self, app, db_session, admin_user):
        ok = make_device(db_session, admin_user, hostname="ok")
        down = make_device(db_session, admin_user, hostname="down")
        auth = make_device(db_session, admin_user, hostname="auth")
        outcomes = {
            ok.NetDiscoveryID: (DeploymentOutcome.SUCCESS, None),
            down.NetDiscoveryID: (DeploymentOutcome.UNREACHABLE, "Device unreachable."),
            auth.NetDiscoveryID: (DeploymentOutcome.FAILED, "SSH authentication failed."),
        }

        run, add_ncpa_port, entries = self.run_worker(app, admin_user, [ok, down, auth], outcomes)

        assert run.Status is DeploymentStatus.PARTIAL_FAILURE
        assert run.Error is None  # no "[3, 7]" list string any more
        assert results_of(run.NCPADeployStatusID) == [
            (ok.NetDiscoveryID, DeploymentOutcome.SUCCESS, None),
            (down.NetDiscoveryID, DeploymentOutcome.UNREACHABLE, "Device unreachable."),
            (auth.NetDiscoveryID, DeploymentOutcome.FAILED, "SSH authentication failed."),
        ]
        assert add_ncpa_port.call_args.args[1] == [ok.NetDiscoveryID]
        assert all(entry["password"] is None for entry in entries)

    def test_all_devices_failing_is_failed_not_partial(self, app, db_session, admin_user):
        a = make_device(db_session, admin_user, hostname="a")
        b = make_device(db_session, admin_user, hostname="b")
        outcomes = {a.NetDiscoveryID: (DeploymentOutcome.FAILED, "x"), b.NetDiscoveryID: (DeploymentOutcome.UNREACHABLE, "y")}

        run, add_ncpa_port, _ = self.run_worker(app, admin_user, [a, b], outcomes)

        assert run.Status is DeploymentStatus.FAILED
        add_ncpa_port.assert_not_called()

    def test_all_devices_succeeding_is_success(self, app, db_session, admin_user):
        a = make_device(db_session, admin_user)
        run, _, _ = self.run_worker(app, admin_user, [a], {a.NetDiscoveryID: (DeploymentOutcome.SUCCESS, None)})
        assert run.Status is DeploymentStatus.SUCCESS
        assert run.Completed_At is not None

    def test_stop_skips_devices_not_started(self, app, db_session, admin_user):
        a = make_device(db_session, admin_user, hostname="a")
        b = make_device(db_session, admin_user, hostname="b")

        run, add_ncpa_port, _ = self.run_worker(app, admin_user, [a, b], {}, stop=True)

        assert run.Status is DeploymentStatus.INTERRUPTED
        assert {outcome for _, outcome, _ in results_of(run.NCPADeployStatusID)} == {DeploymentOutcome.SKIPPED}
        add_ncpa_port.assert_not_called()

    def test_passwords_are_dropped_even_when_the_run_is_stopped(self, app, db_session, admin_user):
        a = make_device(db_session, admin_user)
        _run, _, entries = self.run_worker(app, admin_user, [a], {}, stop=True)
        assert entries[0]["password"] is None

    def test_a_config_that_could_not_be_applied_is_not_reported_as_success(self, app, db_session, admin_user):
        a = make_device(db_session, admin_user)

        def config_failed(_app, _devices, run_id, _stop):
            worker.update_ncpa_deployment_status(run_id, DeploymentStatus.FAILED, 100, "Config not applied.")

        run, _, _ = self.run_worker(app, admin_user, [a], {a.NetDiscoveryID: (DeploymentOutcome.SUCCESS, None)},
                                    add_port=config_failed)

        assert run.Status is DeploymentStatus.FAILED
        assert run.Message == "Config not applied."

    def test_an_unexpected_error_fails_the_run_and_its_open_devices(self, app, db_session, admin_user):
        a = make_device(db_session, admin_user)

        run, _, _ = self.run_worker(app, admin_user, [a], {}, explode=True)

        assert run.Status is DeploymentStatus.FAILED
        assert run.Error == "An unexpected error occurred."
        assert results_of(run.NCPADeployStatusID)[0][1] is DeploymentOutcome.FAILED

    def test_credentials_never_reach_the_log(self, app, db_session, admin_user, caplog):
        a = make_device(db_session, admin_user)
        with caplog.at_level(logging.DEBUG):
            self.run_worker(app, admin_user, [a], {a.NetDiscoveryID: (DeploymentOutcome.FAILED, "SSH authentication failed.")})
        assert PASSWORD not in caplog.text


# ─── give_program_permissions: outcome classification (plan §5) ───────────────

class TestBootstrapOutcomes:
    def bootstrap(self, host_key="ok", connect=None, trusted=(FINGERPRINT, 2222)):
        info = MagicMock()
        with patch.object(worker, "query_trusted_host", return_value=trusted), \
             patch.object(worker, "check_host_key", return_value=host_key) as check, \
             patch.object(worker, "connect_with_fingerprint_check", side_effect=connect) as connect_mock, \
             patch.object(worker, "update_ncpa_deployment_info", info):
            result = worker.give_program_permissions(1, 7, "10.0.20.11", "admin", PASSWORD)
        self.check, self.connect = check, connect_mock
        return result, info

    def test_host_key_and_login_use_the_pinned_ssh_port(self, app, db_session):
        self.bootstrap(connect=paramiko.AuthenticationException("no"))
        self.check.assert_called_once_with("10.0.20.11", 2222, FINGERPRINT)
        assert self.connect.call_args.args[:4] == ("10.0.20.11", 2222, "admin", FINGERPRINT)

    def test_untrusted_device_fails_instead_of_crashing(self, app, db_session):
        result, info = self.bootstrap(trusted=(None, None))
        assert result == (DeploymentOutcome.FAILED, "Device has not been trust-confirmed.")
        self.check.assert_not_called()

    def test_no_answer_on_ssh_is_down(self, app, db_session):
        result, info = self.bootstrap(host_key="unreachable")
        assert result == (DeploymentOutcome.UNREACHABLE, "Device unreachable.")
        assert info.call_args.kwargs["agent_status"] is AgentStatus.FAILED

    def test_a_changed_host_key_fails(self, app, db_session):
        result, _ = self.bootstrap(host_key="mismatch")
        assert result[0] is DeploymentOutcome.FAILED
        assert "Host key changed" in result[1]

    def test_rejected_login_is_failed_not_down(self, app, db_session):
        result, _ = self.bootstrap(connect=paramiko.AuthenticationException("no"))
        assert result == (DeploymentOutcome.FAILED, "SSH authentication failed.")

    def test_timeout_while_connecting_is_down(self, app, db_session):
        result, _ = self.bootstrap(connect=socket.timeout("timed out"))
        assert result == (DeploymentOutcome.UNREACHABLE, "Device unreachable.")


# ─── check_device_credentials and POST /check-credentials (plan §6) ───────────

class TestCheckDeviceCredentials:
    def check(self, host_key="ok", connect=None, sudo_ok=True):
        client = MagicMock()
        sudo = MagicMock(return_value={"success": sudo_ok, "message": "", "output": "", "error": ""})
        with patch.object(worker, "check_host_key", return_value=host_key) as check, \
             patch.object(worker, "connect_with_fingerprint_check", side_effect=connect, return_value=client) as connect_mock, \
             patch.object(worker, "run_sudo_command", sudo):
            result = worker.check_device_credentials("10.0.20.11", 2222, FINGERPRINT, "admin", PASSWORD)
        self.check_host, self.connect = check, connect_mock
        return result, sudo, client

    def test_uses_the_pinned_ssh_port(self, app):
        with app.app_context():
            self.check()
        self.check_host.assert_called_once_with("10.0.20.11", 2222, FINGERPRINT)
        assert self.connect.call_args.args[:4] == ("10.0.20.11", 2222, "admin", FINGERPRINT)

    def test_login_and_sudo_work(self, app):
        with app.app_context():
            result, sudo, client = self.check()
        assert result == "ok"
        assert sudo.call_args.kwargs["log_command"] == "sudo -k -v"
        client.close.assert_called_once()

    def test_wrong_password(self, app):
        with app.app_context():
            assert self.check(connect=paramiko.AuthenticationException("no"))[0] == "auth_failed"

    def test_no_sudo(self, app):
        with app.app_context():
            assert self.check(sudo_ok=False)[0] == "no_sudo"

    def test_unreachable_and_changed_key(self, app):
        with app.app_context():
            assert self.check(host_key="unreachable")[0] == "unreachable"
            assert self.check(host_key="mismatch")[0] == "host_key_changed"
            assert self.check(connect=OSError("refused"))[0] == "unreachable"


class TestCheckCredentialsRoute:
    URL = f"{BASE}/check-credentials"

    def test_reports_each_device(self, logged_in_client, db_session, admin_user):
        good = make_device(db_session, admin_user, hostname="good", ssh_port=2222)
        untrusted = make_device(db_session, admin_user, hostname="untrusted", trusted=False)

        with patch.object(routes, "check_device_credentials", return_value="auth_failed") as check:
            resp = logged_in_client.post(self.URL, json=creds(good.NetDiscoveryID, untrusted.NetDiscoveryID, 99999))

        assert resp.status_code == 200
        assert resp.get_json()["data"]["results"] == [
            {"device_id": good.NetDiscoveryID, "result": "auth_failed"},
            {"device_id": untrusted.NetDiscoveryID, "result": "not_trusted"},
            {"device_id": 99999, "result": "not_found"},
        ]
        check.assert_called_once_with(good.IP_Address, 2222, FINGERPRINT, "admin", PASSWORD)
        assert PASSWORD not in resp.get_data(as_text=True)

    def test_a_device_checked_moments_ago_is_rate_limited(self, logged_in_client, db_session, admin_user):
        device = make_device(db_session, admin_user)
        with patch.object(routes, "check_device_credentials", return_value="ok") as check:
            logged_in_client.post(self.URL, json=creds(device.NetDiscoveryID))
            resp = logged_in_client.post(self.URL, json=creds(device.NetDiscoveryID))

        assert resp.get_json()["data"]["results"][0]["result"] == "rate_limited"
        assert check.call_count == 1

    def test_invalid_body_is_400(self, logged_in_client, db_session, admin_user):
        resp = logged_in_client.post(self.URL, json={"devices": [{"device_id": "1", "username": "a", "password": "b"}]})
        assert resp.status_code == 400

    def test_requires_permission(self, limited_client, db_session, admin_user):
        resp = limited_client.post(self.URL, json=creds(1))
        assert resp.status_code == 403


# ─── Device list, status, runs, review (plan §6) ──────────────────────────────

class TestDevicesList:
    def test_reports_trust_agent_state_and_last_outcome(self, logged_in_client, db_session, admin_user):
        down = make_device(db_session, admin_user, hostname="nas-06", agent_status=AgentStatus.FAILED)
        pending = make_device(db_session, admin_user, hostname="db-02", trusted=False)
        incompatible = make_device(db_session, admin_user, hostname="legacy-07", eligible=False,
                                   agent_status=AgentStatus.INCOMPATIBLE)
        make_run(admin_user, [(down, DeploymentOutcome.UNREACHABLE, "Device unreachable.")],
                 status=DeploymentStatus.FAILED)

        resp = logged_in_client.get(f"{BASE}/devices")

        devices = {d["hostname"]: d for d in resp.get_json()["data"]["devices"]}
        assert devices["nas-06"]["last_outcome"] == "Down"
        assert devices["nas-06"]["deployable"] is True
        assert devices["nas-06"]["trusted"] is True
        assert devices["db-02"]["trusted"] is False and devices["db-02"]["fingerprint"] is None
        assert devices["db-02"]["agent_status"] == "Pending NCPA"
        # Marked incompatible (no longer eligible) but still shown, not selectable.
        assert devices["legacy-07"]["deployable"] is False
        assert devices["legacy-07"]["agent_status"] == "Incompatible"
        assert pending.NetDiscoveryID == devices["db-02"]["device_id"]
        assert incompatible.NetDiscoveryID == devices["legacy-07"]["device_id"]

    def test_trusted_list_includes_failed_devices_for_retry(self, logged_in_client, db_session, admin_user):
        failed = make_device(db_session, admin_user, agent_status=AgentStatus.FAILED)
        resp = logged_in_client.get(f"{BASE}/devices/trusted")
        assert [d["device_id"] for d in resp.get_json()["data"]["devices"]] == [failed.NetDiscoveryID]


class TestRuns:
    def test_status_includes_devices_and_counts(self, logged_in_client, db_session, admin_user):
        a = make_device(db_session, admin_user, hostname="a")
        b = make_device(db_session, admin_user, hostname="b")
        make_run(admin_user, [(a, DeploymentOutcome.SUCCESS, None), (b, DeploymentOutcome.UNREACHABLE, "Device unreachable.")],
                 status=DeploymentStatus.PARTIAL_FAILURE)

        data = logged_in_client.get(f"{BASE}/status").get_json()["data"]

        assert data["status"] == "Partial Failure"
        assert data["started_by"] == "Admin User"
        assert data["counts"]["success"] == 1 and data["counts"]["down"] == 1
        assert [(d["hostname"], d["outcome"]) for d in data["devices"]] == [("a", "Success"), ("b", "Down")]
        assert data["needs_review"] is True

    def test_runs_are_paginated_newest_first_with_review_count(self, logged_in_client, db_session, admin_user):
        a = make_device(db_session, admin_user)
        first = make_run(admin_user, [(a, DeploymentOutcome.SUCCESS, None)])
        second = make_run(admin_user, [(a, DeploymentOutcome.FAILED, "x")], status=DeploymentStatus.FAILED)
        third = make_run(admin_user, [(a, DeploymentOutcome.SUCCESS, None)])

        data = logged_in_client.get(f"{BASE}/runs?per_page=2").get_json()["data"]

        assert [item["id"] for item in data["items"]] == [third.NCPADeployStatusID, second.NCPADeployStatusID]
        assert data["total"] == 3 and data["pages"] == 2 and data["has_next"] is True
        assert data["needs_review"] == 2  # both Success runs; the Failed one needs no review
        assert data["items"][1]["counts"]["failed"] == 1
        assert first.NCPADeployStatusID not in [item["id"] for item in data["items"]]

    def test_runs_filter_by_status_and_review(self, logged_in_client, db_session, admin_user):
        a = make_device(db_session, admin_user)
        make_run(admin_user, [(a, DeploymentOutcome.SUCCESS, None)])
        failed = make_run(admin_user, [(a, DeploymentOutcome.FAILED, "x")], status=DeploymentStatus.FAILED)

        by_status = logged_in_client.get(f"{BASE}/runs?status=Failed").get_json()["data"]["items"]
        assert [item["id"] for item in by_status] == [failed.NCPADeployStatusID]
        to_review = logged_in_client.get(f"{BASE}/runs?needs_review=true").get_json()["data"]["items"]
        assert [item["status"] for item in to_review] == ["Success"]

    def test_invalid_filters_are_400(self, logged_in_client, db_session, admin_user):
        assert logged_in_client.get(f"{BASE}/runs?status=Nope").status_code == 400
        assert logged_in_client.get(f"{BASE}/runs?start_date=04-10-2026").status_code == 400
        assert logged_in_client.get(f"{BASE}/runs?per_page=500").status_code == 400

    def test_run_detail_and_404(self, logged_in_client, db_session, admin_user):
        a = make_device(db_session, admin_user)
        run = make_run(admin_user, [(a, DeploymentOutcome.SUCCESS, None)])

        data = logged_in_client.get(f"{BASE}/runs/{run.NCPADeployStatusID}").get_json()["data"]
        assert data["devices"][0]["device_id"] == a.NetDiscoveryID
        assert logged_in_client.get(f"{BASE}/runs/99999").status_code == 404

    def test_runs_require_permission(self, limited_client, db_session, admin_user):
        assert limited_client.get(f"{BASE}/runs").status_code == 403
        assert limited_client.post(f"{BASE}/runs/1/review").status_code == 403


class TestReview:
    def test_marks_the_run_reviewed_once_and_logs_it(self, logged_in_client, db_session, admin_user):
        a = make_device(db_session, admin_user)
        run = make_run(admin_user, [(a, DeploymentOutcome.SUCCESS, None)])

        resp = logged_in_client.post(f"{BASE}/runs/{run.NCPADeployStatusID}/review")
        first_time = resp.get_json()["data"]["reviewed_at"]
        again = logged_in_client.post(f"{BASE}/runs/{run.NCPADeployStatusID}/review").get_json()["data"]

        assert resp.status_code == 200
        assert resp.get_json()["data"]["reviewed_by"] == "Admin User"
        assert resp.get_json()["data"]["needs_review"] is False
        assert again["reviewed_at"] == first_time
        logs = db.session.scalars(sa.select(ActivityLog.Action_Type).where(
            ActivityLog.Action_Type.like("Reviewed NCPA deployment%"))).all()
        assert logs == [f"Reviewed NCPA deployment NP-{run.NCPADeployStatusID:04d}"]

    def test_a_running_run_cannot_be_reviewed(self, logged_in_client, db_session, admin_user):
        run = create_ncpa_deployment_status(admin_user.UserID)
        resp = logged_in_client.post(f"{BASE}/runs/{run.NCPADeployStatusID}/review")
        assert resp.status_code == 409

    def test_unknown_run_is_404(self, logged_in_client, db_session, admin_user):
        assert logged_in_client.post(f"{BASE}/runs/99999/review").status_code == 404


class TestRequestBodies:
    def test_a_missing_body_is_a_json_400_not_a_500(self, logged_in_client, db_session, admin_user):
        device = make_device(db_session, admin_user, trusted=False)
        for url in (f"{BASE}/{device.NetDiscoveryID}/confirm-trust", f"{BASE}/check-credentials", f"{BASE}/start"):
            resp = logged_in_client.post(url)
            assert resp.status_code == 400, url
            assert resp.get_json()["success"] is False
