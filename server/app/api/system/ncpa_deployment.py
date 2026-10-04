"""
NCPA Deployment API Routes
==========================

Purpose
-------
This module provides the Flask REST API for remotely deploying the NCPA
(Nagios Core Agent) monitoring agent to discovered network devices.

Workflow
--------
1. List eligible devices  →  2. Verify SSH host-key fingerprint  →
3. Confirm trust (save the fingerprint the user approved)  →
4. Check each device's login  →  5. Supply credentials & start  →
6. Background deployment  →  7. Monitor status  →  8. Review the run

Security
--------
- Every SSH connection verifies the device's host-key fingerprint.
- Trust is saved only for the exact fingerprint the user was shown.
- Passwords are used for one SSH session and never stored, logged or
  returned. The deployment user on the remote device has restricted sudo
  (one command only).
- All routes require the ``system.deploy.ncpa`` permission.

Module-level state
------------------
deploy_ncpa_thread            – Background daemon thread (``None`` when idle)
deploy_ncpa_thread_stop_event – Threading.Event for graceful stop
credential_check_times        – Last login check per device (rate limit)

Routes
------
GET    /system/deployment/ncpa/devices             – NCPA-eligible devices with trust and agent state
GET    /system/deployment/ncpa/<id>/fingerprint    – Fetch live SSH host-key fingerprint
POST   /system/deployment/ncpa/<id>/confirm-trust  – Save the fingerprint the user approved
POST   /system/deployment/ncpa/check-credentials   – Test logins and sudo without deploying
POST   /system/deployment/ncpa/start               – Start background deployment
POST   /system/deployment/ncpa/stop                – Request running deployment to stop
GET    /system/deployment/ncpa/status              – Latest run with per-device results
GET    /system/deployment/ncpa/runs                – Paginated run history
GET    /system/deployment/ncpa/runs/<id>           – One run with per-device results
POST   /system/deployment/ncpa/runs/<id>/review    – Mark a finished run as reviewed
GET    /system/deployment/ncpa/devices/trusted     – Trust-confirmed devices ready for deploy
POST   /system/deployment/ncpa/<id>/refresh-disks  – Re-read a deployed agent's disks
"""

from datetime import datetime, timezone, date
from concurrent.futures import ThreadPoolExecutor
import hmac
import time

from flask_login import login_required, current_user
from flask import request, current_app
from app import app, db
import sqlalchemy as sa
import threading
from app.api.system import system_bp
from app.api.helper import success, error
from app.api.helper.validation import validate_json_data
from app.api.helper.database_access.permissions import require_permission
from app.logging.deployment_history import (
    get_deployment_ncpa_status, create_ncpa_deployment_status, add_deployment_result,
    get_deployment_results, count_deployment_results,
)
from app.logging.user_activity import create_user_log
from app.system_models import (
    NetworkDiscovery, SSHCredentials, NCPADeployment, AgentStatus, IdentifierKind,
    NCPADeploymentStatus, NCPADeploymentResult, DeploymentStatus, DeploymentOutcome,
    ActivityLog, User,
)
from app.network_discovery.device_identity import Evidence, record_device_evidence
from app.network_discovery.port_lifecycle import device_ssh_port
from app.ncpa_deployment.ncpa_deployment import *

deploy_ncpa_thread = None
deploy_ncpa_thread_stop_event = threading.Event()

# Agent states a device can be deployed from: never tried, or a failed try.
DEPLOYABLE_AGENT_STATUSES = (AgentStatus.PENDING_NCPA, AgentStatus.FAILED)

# Finished runs an administrator should look at until marked reviewed.
REVIEWABLE_RUN_STATUSES = (DeploymentStatus.SUCCESS, DeploymentStatus.PARTIAL_FAILURE)

# Login checks: at most one per device in this window, and a bounded batch.
CREDENTIAL_CHECK_INTERVAL_SECONDS = 3
MAX_DEVICES_PER_REQUEST = 50
MAX_USERNAME_LENGTH = 64
MAX_PASSWORD_LENGTH = 256
credential_check_times = {}
credential_check_lock = threading.Lock()


# ==========================================================
# HELPERS
# ==========================================================

def parse_credential_entries(data):
    """
    Validate a ``{"devices": [{"device_id", "username", "password"}]}`` body.
    Returns (entries, None) with each entry normalized, or (None, message)
    describing the first problem. Duplicate device IDs are an error so one
    device is never deployed twice in a run. Never echoes credentials.
    """
    devices = data.get("devices")
    if not isinstance(devices, list) or not devices:
        return None, "No devices were provided."
    if len(devices) > MAX_DEVICES_PER_REQUEST:
        return None, f"At most {MAX_DEVICES_PER_REQUEST} devices can be sent at once."

    entries = []
    seen = set()
    for entry in devices:
        if not isinstance(entry, dict):
            return None, "Each device must be an object."

        device_id = entry.get("device_id")
        username = entry.get("username")
        password = entry.get("password")

        if not isinstance(device_id, int) or isinstance(device_id, bool):
            return None, "Each device needs a numeric device_id."
        if device_id in seen:
            return None, f"Device {device_id} was sent more than once."
        if not isinstance(username, str) or not username.strip():
            return None, f"Device {device_id} needs a username."
        if len(username) > MAX_USERNAME_LENGTH or any(ch.isspace() or not ch.isprintable() for ch in username):
            return None, f"Device {device_id} has an invalid username."
        if not isinstance(password, str) or not password:
            return None, f"Device {device_id} needs a password."
        if len(password) > MAX_PASSWORD_LENGTH or "\n" in password or "\r" in password:
            return None, f"Device {device_id} has an invalid password."

        seen.add(device_id)
        entries.append({"device_id": device_id, "username": username, "password": password})

    return entries, None


def device_deployment_rows(device_id):
    """The device's SSHCredentials and NCPADeployment rows (either may be None)."""
    creds = db.session.scalar(
        sa.select(SSHCredentials).where(SSHCredentials.NetworkDiscoveryID == device_id)
    )
    deployment = db.session.scalar(
        sa.select(NCPADeployment).where(NCPADeployment.NetworkDiscoveryID == device_id)
    )
    return creds, deployment


def deploy_rejection(device, creds, deployment):
    """
    Why a device cannot be deployed to, checked without touching the
    network, or None when it can. Order matters: the first reason wins.
    """
    if device is None:
        return "Device does not exist."
    if not device.Include_Device_In_Scanning:
        return "Device is not included in scanning."
    if deployment is None:
        return "Device is not NCPA-eligible."
    if deployment.Agent_Status is AgentStatus.DEPLOYED:
        return "NCPA is already deployed."
    if deployment.Agent_Status not in DEPLOYABLE_AGENT_STATUSES:
        status = deployment.Agent_Status.value if deployment.Agent_Status else "Unknown"
        return f"Device cannot be deployed to ({status})."
    if creds is None or creds.Key_Fingerprint is None:
        return "Not trust-confirmed."
    return None


def user_name(user):
    """A user's display name, or None for a missing user."""
    if user is None:
        return None
    return f"{user.First_Name} {user.Last_Name}".strip()


def iso(value):
    """ISO-8601 text for a datetime, or None."""
    return value.isoformat() if value else None


def serialize_result(result):
    """One device's outcome in a run, as the API returns it."""
    return {
        "device_id": result.NetworkDiscoveryID,
        "hostname": result.Hostname,
        "ip_address": result.IP_Address,
        "outcome": result.Outcome.value,
        "error": result.Error,
        "started_at": iso(result.Started_At),
        "completed_at": iso(result.Completed_At),
    }


def serialize_run(run, started_by, counts):
    """
    A run's summary as the API returns it. ``needs_review`` is true for a
    finished Success or Partial Failure run nobody has reviewed yet.
    """
    return {
        "id": run.NCPADeployStatusID,
        "status": run.Status.value,
        "progress": run.Progress,
        "message": run.Message,
        "error": run.Error,
        "start_at": iso(run.Start_At),
        "completed_at": iso(run.Completed_At),
        "started_by": user_name(started_by),
        "counts": counts,
        "reviewed_at": iso(run.Reviewed_At),
        "reviewed_by": user_name(run.Reviewer),
        "needs_review": run.Status in REVIEWABLE_RUN_STATUSES and run.Reviewed_At is None,
    }


def run_detail(run):
    """A run's summary plus every device result. Reads only."""
    started_by = db.session.scalar(
        sa.select(User).join(ActivityLog, ActivityLog.UserID == User.UserID)
        .where(ActivityLog.LogID == run.LogID)
    )
    counts = count_deployment_results([run.NCPADeployStatusID])[run.NCPADeployStatusID]
    body = serialize_run(run, started_by, counts)
    body["devices"] = [serialize_result(result) for result in get_deployment_results(run.NCPADeployStatusID)]
    return body


def parse_date_arg(name):
    """
    A YYYY-MM-DD query argument as a date. Returns (date | None, error
    response | None); an absent argument is (None, None).
    """
    value = request.args.get(name, default="", type=str)
    if not value:
        return None, None
    try:
        return date.fromisoformat(value), None
    except ValueError:
        return None, error(f"{name} must be a date in YYYY-MM-DD format.", 400)


def check_one_device(job):
    """
    Thread-pool worker for check-credentials: test one device's login in
    its own app context. ``job`` holds the device ID, IP, trusted
    fingerprint and credentials; returns (device_id, result code).
    """
    with app.app_context():
        result = check_device_credentials(job["ip_address"], job["fingerprint"], job["username"], job["password"])
    job["password"] = None
    return job["device_id"], result


# ==========================================================
# DEVICES AND TRUST
# ==========================================================

@system_bp.get('/deployment/ncpa/devices')
@login_required
@require_permission("system.deploy.ncpa")
def get_ncpa_eligible_devices():
    """
    List every device NCPA can be deployed to, or was deployed to, with
    what the deployment page needs to show and select it.

    A device is listed when it is included in scanning and is either
    NCPA-eligible now or has an NCPA deployment record (so devices marked
    incompatible stay visible). Sorted by hostname.

    Response (200):
        { "success": true, "data": { "devices": [ {
            "device_id": int, "hostname": str, "ip_address": str,
            "trusted": bool, "fingerprint": str | null,
            "agent_status": "Pending NCPA" | "Deployed NCPA" | "Deployment Failed" | "Excluded" | "Incompatible" | null,
            "last_error": str | null,
            "last_outcome": "Success" | "Failed" | "Down" | ... | null,
            "last_run_id": int | null,
            "deployable": bool
        }, ... ] } }
    """
    try:
        latest_result_ids = (
            sa.select(sa.func.max(NCPADeploymentResult.NCPADeployResultID))
            .group_by(NCPADeploymentResult.NetworkDiscoveryID)
        )
        latest_results = {
            result.NetworkDiscoveryID: result
            for result in db.session.scalars(
                sa.select(NCPADeploymentResult).where(NCPADeploymentResult.NCPADeployResultID.in_(latest_result_ids))
            )
        }

        rows = db.session.execute(
            sa.select(NetworkDiscovery, SSHCredentials, NCPADeployment)
            .outerjoin(SSHCredentials, SSHCredentials.NetworkDiscoveryID == NetworkDiscovery.NetDiscoveryID)
            .outerjoin(NCPADeployment, NCPADeployment.NetworkDiscoveryID == NetworkDiscovery.NetDiscoveryID)
            .where(NetworkDiscovery.Include_Device_In_Scanning.is_(True))
            .where(sa.or_(NetworkDiscovery.NCPA_Eligible.is_(True), NCPADeployment.NCPADeployID.is_not(None)))
            .order_by(NetworkDiscovery.Hostname.asc(), NetworkDiscovery.NetDiscoveryID.asc())
        ).all()

        devices = []
        for device, creds, deployment in rows:
            agent_status = deployment.Agent_Status if deployment else None
            latest = latest_results.get(device.NetDiscoveryID)
            fingerprint = creds.Key_Fingerprint if creds else None
            devices.append({
                "device_id": device.NetDiscoveryID,
                "hostname": device.Hostname,
                "ip_address": device.IP_Address,
                "trusted": fingerprint is not None,
                "fingerprint": fingerprint,
                "agent_status": agent_status.value if agent_status else None,
                "last_error": deployment.Error if deployment else None,
                "last_outcome": latest.Outcome.value if latest else None,
                "last_run_id": deployment.NCPADeploymentStatusID if deployment else None,
                "deployable": agent_status in DEPLOYABLE_AGENT_STATUSES,
            })

        return success({"devices": devices})

    except Exception:
        current_app.logger.exception("An unexpected error occurred.")
        return error("An unexpected error occurred.", 500)


@system_bp.get('/deployment/ncpa/<int:device_id>/fingerprint')
@login_required
@require_permission('system.deploy.ncpa')
def get_device_fingerprint(device_id):
    """
    Fetch the live SSH host-key fingerprint for a device.

    Connects to the device's IP address on the port discovery found SSH
    on (the standard SSH port if none is recorded) and retrieves its
    current SSH host-key (SHA-256, base64-encoded). Used during the trust-
    confirmation flow so the admin can verify before approving.

    Args:
        device_id: Primary key of the NetworkDiscovery record.

    Response (200):
        { "success": true, "data": { "device_id": int, "ip_address": str, "ssh_port": int, "fingerprint": str } }

    Errors:
        404 – Device not found.
        502 – Could not reach the device.
        500 – Unexpected error.
    """
    try:
        device = db.session.get(NetworkDiscovery, device_id)

        if device is None:
            return error("Device not found.", 404)

        if not device.Include_Device_In_Scanning:
            return error("Device not included in scanning.", 404)

        ssh_port = device_ssh_port(device_id)
        try:
            fingerprint = get_host_key_fingerprint(device.IP_Address, ssh_port)
        except Exception:
            fingerprint = None

        if fingerprint is None:
            current_app.logger.error("Could not reach device at %s.", device.IP_Address)
            return error("Could not reach device.", 502)

        return success({
            "device_id": device_id,
            "ip_address": device.IP_Address,
            "ssh_port": ssh_port,
            "fingerprint": fingerprint,
        })

    except Exception:
        current_app.logger.exception("An unexpected error occurred.")
        return error("An unexpected error occurred.", 500)


@system_bp.post('/deployment/ncpa/<int:device_id>/confirm-trust')
@login_required
@require_permission('system.deploy.ncpa')
def confirm_device_trust(device_id):
    """
    Save the SSH host-key fingerprint the user approved.

    Re-fetches the live fingerprint server-side (does not trust the
    client) and stores it in the SSH_CREDENTIALS table together with the
    SSH port it was read from; every later deployment connection uses that
    port. This is the "trust confirmation" step — once saved, the device
    can be deployed to.

    Args:
        device_id: Primary key of the NetworkDiscovery record.

    Request body (JSON):
        { "fingerprint": "<the value shown to the user>" }

    Response (200):
        { "success": true, "message": "Device fingerprint saved." }

    Errors:
        400 – No fingerprint in the body.
        404 – Device not found, or no SSH credentials entry exists.
        409 – The live key differs from the approved one; ``data.fingerprint``
              holds the new key to show the user.
        502 – Could not reach the device.
        500 – Unexpected error.
    """
    try:
        # A missing or non-JSON body is a 400 from validate_json_data, not a 415/500.
        data = request.get_json(silent=True)
        validation_error = validate_json_data(data)
        if validation_error:
            return validation_error

        approved = data.get("fingerprint")
        if not isinstance(approved, str) or not approved.strip():
            return error("The approved fingerprint is required.", 400)

        device = db.session.get(NetworkDiscovery, device_id)

        if device is None:
            return error("Device not found.", 404)

        if not device.Include_Device_In_Scanning:
            return error("Device not included in scanning.", 404)

        # Recreate the fingerprint server-side rather than trusting the client
        ssh_port = device_ssh_port(device_id)
        fingerprint = get_host_key_fingerprint(device.IP_Address, ssh_port)

        creds = db.session.scalar(
            sa.select(SSHCredentials).where(
                SSHCredentials.NetworkDiscoveryID == device_id
            )
        )

        if creds is None:
            return error("That device has no credentials entry.", 404)

        # A fingerprint only vouches for the port it was read from.
        creds.Key_Fingerprint = fingerprint
        creds.SSH_Port = ssh_port

        # The trusted host key also identifies the device across IP changes.
        record_device_evidence(device, [Evidence(IdentifierKind.SSH_HOST_KEY, fingerprint)])
        db.session.commit()

        return success(message="Device fingerprint saved.")

    except Exception:
        db.session.rollback()
        current_app.logger.exception("An unexpected error occurred.")
        return error("An unexpected error occurred.", 500)


@system_bp.post('/deployment/ncpa/check-credentials')
@login_required
@require_permission('system.deploy.ncpa')
def check_ncpa_credentials():
    """
    Test each device's login before deploying, without changing anything.

    For each trusted device: verifies its host key, logs in with the given
    username and password, and checks the account can use sudo. Nothing
    is installed or stored, and credentials are never logged or returned.
    Each device can be checked at most once every few seconds.

    Request body (JSON):
        { "devices": [ { "device_id": 1, "username": "admin", "password": "secret" }, ... ] }

    Result codes per device:
        ``ok``               – login and sudo work
        ``auth_failed``      – the username or password was rejected
        ``no_sudo``          – logged in, but the account cannot use sudo
        ``unreachable``      – the device did not answer on SSH
        ``host_key_changed`` – the live host key differs from the trusted one
        ``not_trusted``      – the host key has not been confirmed
        ``not_found``        – no such device, or it is not included in scanning
        ``rate_limited``     – checked too recently; try again shortly

    Response (200):
        { "success": true, "data": { "results": [ { "device_id": int, "result": str }, ... ] } }

    Errors:
        400 – Missing or invalid body, credentials, or device IDs.
        500 – Unexpected error.
    """
    try:
        # A missing or non-JSON body is a 400 from validate_json_data, not a 415/500.
        data = request.get_json(silent=True)
        validation_error = validate_json_data(data)
        if validation_error:
            return validation_error

        entries, message = parse_credential_entries(data)
        if entries is None:
            return error(message, 400)

        results = {}
        jobs = []
        now = time.monotonic()

        with credential_check_lock:
            for entry in entries:
                device_id = entry["device_id"]
                device = db.session.get(NetworkDiscovery, device_id)
                if device is None or not device.Include_Device_In_Scanning:
                    results[device_id] = "not_found"
                    continue

                creds, _deployment = device_deployment_rows(device_id)
                if creds is None or creds.Key_Fingerprint is None:
                    results[device_id] = "not_trusted"
                    continue

                last_check = credential_check_times.get(device_id)
                if last_check is not None and now - last_check < CREDENTIAL_CHECK_INTERVAL_SECONDS:
                    results[device_id] = "rate_limited"
                    continue

                credential_check_times[device_id] = now
                jobs.append({
                    "device_id": device_id,
                    "ip_address": device.IP_Address,
                    "fingerprint": creds.Key_Fingerprint,
                    "username": entry["username"],
                    "password": entry["password"],
                })
                entry["password"] = None

        if jobs:
            with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as pool:
                for device_id, result in pool.map(check_one_device, jobs):
                    results[device_id] = result

        return success({
            "results": [
                {"device_id": entry["device_id"], "result": results[entry["device_id"]]}
                for entry in entries
            ]
        })

    except Exception:
        current_app.logger.exception("An unexpected error occurred while checking credentials.")
        return error("An unexpected error occurred.", 500)


# ==========================================================
# DEPLOYMENT RUNS
# ==========================================================

@system_bp.post('/deployment/ncpa/start')
@login_required
@require_permission('system.deploy.ncpa')
def deploy_ncpa():
    """
    Start a background NCPA deployment run for one or more devices.

    Validates each device (exists, NCPA-eligible, not already deployed,
    trust-confirmed, reachable, host key unchanged), creates the run with a
    result row per device (Rejected or Pending), then launches a daemon
    thread that deploys the accepted devices in order.

    Request body (JSON):
        {
            "devices": [
                { "device_id": 1, "username": "admin", "password": "secret" },
                ...
            ]
        }

    Rejection reasons per device include:
        - "Device does not exist."
        - "Device is not NCPA-eligible."
        - "NCPA is already deployed."
        - "Not trust-confirmed."   – no fingerprint saved
        - "Device unreachable."    – no answer on SSH
        - "Host key mismatch."     – live fingerprint differs from stored

    Response (202):
        {
            "success": true,
            "data": { "run_id": int, "started": int, "rejected": [{ "device_id": int, "reason": str }, ...] },
            "message": "Deployment started for N device(s)."
        }

    Errors:
        400 – Deployment already running, invalid body or credentials, or
              every device was rejected (``data.rejected`` lists why).
        500 – Unexpected error.
    """
    global deploy_ncpa_thread

    if deploy_ncpa_thread is not None and deploy_ncpa_thread.is_alive():
        return error("NCPA is already being deployed.", 400)

    data = request.get_json(silent=True)
    validation_error = validate_json_data(data)
    if validation_error:
        return validation_error

    entries, message = parse_credential_entries(data)
    if entries is None:
        return error(message, 400)

    try:
        validated_entries = []
        rejected_entries = []
        rejected_devices = []

        for entry in entries:
            device_id = entry["device_id"]
            device = db.session.get(NetworkDiscovery, device_id)
            creds, deployment = device_deployment_rows(device_id) if device else (None, None)

            reason = deploy_rejection(device, creds, deployment)
            if reason is None:
                current_fingerprint = get_host_key_fingerprint(device.IP_Address)
                if current_fingerprint is None:
                    reason = "Device unreachable."
                elif not hmac.compare_digest(current_fingerprint, creds.Key_Fingerprint):
                    reason = "Host key mismatch."

            if reason is not None:
                rejected_entries.append({"device_id": device_id, "reason": reason})
                if device is not None:
                    rejected_devices.append((device, reason))
                continue

            validated_entries.append({
                "device": device,
                "device_id": device_id,
                "ip_address": device.IP_Address,
                "username": entry["username"],
                "password": entry["password"],
            })

        if not validated_entries:
            return error("No devices could be deployed.", 400, {"rejected": rejected_entries})

        run = create_ncpa_deployment_status(current_user.UserID)
        if run is None:
            return error("Could not start the deployment.", 500)

        current_fingerprint = get_host_key_fingerprint(device.IP_Address, creds.SSH_Port)
        if current_fingerprint != creds.Key_Fingerprint:
            rejected_entries.append({
                "device_id": device_id,
                "reason": "Host key mismatch."
            })
            continue

        validated_entries.append({
            "device_id": device_id,
            "ip_address": device.IP_Address,
            "username": entry["username"],
            "password": entry["password"],
        })

        deploy_ncpa_thread_stop_event.clear()
        deploy_ncpa_thread = threading.Thread(
            daemon=True,
            target=install_process,
            args=(app,
                  run.NCPADeployStatusID,
                  validated_entries,
                  deploy_ncpa_thread_stop_event
                  )
        )
        deploy_ncpa_thread.start()

        return success(
            {
                "run_id": run.NCPADeployStatusID,
                "started": len(validated_entries),
                "rejected": rejected_entries,
            },
            message=f"Deployment started for {len(validated_entries)} device(s).",
            status=202,
        )

    except Exception:
        db.session.rollback()
        current_app.logger.exception("An unexpected error occurred while starting the deployment.")
        return error("An unexpected error occurred.", 500)


@system_bp.post('/deployment/ncpa/stop')
@login_required
@require_permission('system.deploy.ncpa')
def stop_ncpa_deployment():
    """
    Request the running deployment thread to stop.

    Sets the ``deploy_ncpa_thread_stop_event`` flag. The background
    thread checks this flag between devices; devices it has not started
    become Skipped and the run is marked Interrupted.

    Response (200):
        { "success": true, "message": "NCPA deployment stop requested." }

    Errors:
        400 – No deployment is currently running.
    """
    global deploy_ncpa_thread

    if deploy_ncpa_thread is None or not deploy_ncpa_thread.is_alive():
        return error("There is no NCPA deployment running.", 400)

    deploy_ncpa_thread_stop_event.set()
    return success(message="NCPA deployment stop requested.")


@system_bp.get('/deployment/ncpa/status')
@login_required
@require_permission('system.deploy.ncpa')
def deploy_ncpa_status():
    """
    Return the latest NCPA deployment run with its per-device results.

    Possible ``status`` values:
        ``Running``, ``Success``, ``Partial Failure``, ``Failed``, ``Interrupted``

    Possible device ``outcome`` values:
        ``Pending``, ``Running``, ``Success``, ``Failed``, ``Down``,
        ``Incompatible``, ``Rejected``, ``Skipped``

    Response (200):
        {
            "success": true,
            "data": {
                "id": int, "status": str, "progress": int, "message": str,
                "error": str | null,
                "start_at": "ISO-8601", "completed_at": "ISO-8601" | null,
                "started_by": str | null,
                "counts": { "pending": int, "running": int, "success": int, "failed": int,
                            "down": int, "incompatible": int, "rejected": int, "skipped": int },
                "reviewed_at": "ISO-8601" | null, "reviewed_by": str | null,
                "needs_review": bool,
                "devices": [ { "device_id": int, "hostname": str, "ip_address": str,
                               "outcome": str, "error": str | null,
                               "started_at": "ISO-8601" | null, "completed_at": "ISO-8601" | null }, ... ]
            }
        }

    When no deployment has occurred yet:
        { "success": true, "message": "No NCPA deployment has occurred yet." }
    """
    try:
        deployment_info = get_deployment_ncpa_status()

        if deployment_info is None:
            return success(message="No NCPA deployment has occurred yet.")

        return success(run_detail(deployment_info))

    except Exception:
        current_app.logger.exception("An unexpected error occurred.")
        return error("An unexpected error occurred.", 500)


@system_bp.get('/deployment/ncpa/runs')
@login_required
@require_permission('system.deploy.ncpa')
def list_ncpa_deployment_runs():
    """
    Paginated history of NCPA deployment runs, newest first.

    Query parameters:
        page (int, default 1), per_page (int, default 10, max 100)
        status (str, optional) – one run status, e.g. ``Partial Failure``
        needs_review (bool, optional) – ``true`` for finished runs not yet reviewed
        start_date, end_date (YYYY-MM-DD, optional) – inclusive range on the start time

    Response (200):
        {
            "success": true,
            "data": {
                "items": [ <run summary as in /status, without "devices"> ],
                "page": int, "per_page": int, "pages": int, "total": int,
                "has_next": bool, "has_prev": bool,
                "needs_review": int   – runs awaiting review across all pages
            }
        }

    Errors:
        400 – Invalid page, per_page, status or date.
        500 – Unexpected error.
    """
    try:
        page = request.args.get("page", default=1, type=int)
        per_page = request.args.get("per_page", default=10, type=int)
        status_text = request.args.get("status", default="", type=str)
        needs_review = request.args.get("needs_review", default="", type=str).lower()

        if page < 1:
            return error("Page must be greater than 0", 400)
        if per_page < 1 or per_page > 100:
            return error("per_page must be between 1 and 100", 400)

        start_date, date_error = parse_date_arg("start_date")
        if date_error:
            return date_error
        end_date, date_error = parse_date_arg("end_date")
        if date_error:
            return date_error

        reviewable = sa.and_(
            NCPADeploymentStatus.Status.in_(REVIEWABLE_RUN_STATUSES),
            NCPADeploymentStatus.Reviewed_At.is_(None),
        )

        query = (
            sa.select(NCPADeploymentStatus, User)
            .join(ActivityLog, ActivityLog.LogID == NCPADeploymentStatus.LogID)
            .outerjoin(User, User.UserID == ActivityLog.UserID)
        )

        if status_text:
            try:
                query = query.where(NCPADeploymentStatus.Status == DeploymentStatus(status_text))
            except ValueError:
                return error("Invalid status.", 400)
        if needs_review == "true":
            query = query.where(reviewable)
        if start_date:
            query = query.where(sa.func.date(NCPADeploymentStatus.Start_At) >= start_date.isoformat())
        if end_date:
            query = query.where(sa.func.date(NCPADeploymentStatus.Start_At) <= end_date.isoformat())

        total = db.session.scalar(sa.select(sa.func.count()).select_from(query.subquery())) or 0
        rows = db.session.execute(
            query.order_by(NCPADeploymentStatus.Start_At.desc(), NCPADeploymentStatus.NCPADeployStatusID.desc())
            .limit(per_page).offset((page - 1) * per_page)
        ).all()

        counts = count_deployment_results([run.NCPADeployStatusID for run, _user in rows])
        items = []
        for run, started_by in rows:
            items.append(serialize_run(run, started_by, counts[run.NCPADeployStatusID]))

        pages = max(1, -(-total // per_page))
        awaiting_review = db.session.scalar(
            sa.select(sa.func.count()).select_from(NCPADeploymentStatus).where(reviewable)
        ) or 0

        return success({
            "items": items,
            "page": page,
            "per_page": per_page,
            "pages": pages,
            "total": total,
            "has_next": page < pages,
            "has_prev": page > 1,
            "needs_review": awaiting_review,
        })

    except Exception:
        current_app.logger.exception("An unexpected error occurred while listing deployment runs.")
        return error("An unexpected error occurred.", 500)


@system_bp.get('/deployment/ncpa/runs/<int:run_id>')
@login_required
@require_permission('system.deploy.ncpa')
def get_ncpa_deployment_run(run_id):
    """
    One deployment run with every device's outcome.

    Response (200):
        { "success": true, "data": <run as in /status, including "devices"> }

    Errors:
        404 – No such run.
        500 – Unexpected error.
    """
    try:
        run = db.session.get(NCPADeploymentStatus, run_id)
        if run is None:
            return error("Deployment run not found.", 404)

        return success(run_detail(run))

    except Exception:
        current_app.logger.exception("An unexpected error occurred.")
        return error("An unexpected error occurred.", 500)


@system_bp.post('/deployment/ncpa/runs/<int:run_id>/review')
@login_required
@require_permission('system.deploy.ncpa')
def review_ncpa_deployment_run(run_id):
    """
    Mark a finished deployment run as reviewed by the current user, and
    record it in the activity log. Marking an already reviewed run again
    changes nothing.

    Response (200):
        { "success": true, "data": <run as in /status>, "message": "Deployment run marked as reviewed." }

    Errors:
        404 – No such run.
        409 – The run is still running.
        500 – Unexpected error.
    """
    try:
        run = db.session.get(NCPADeploymentStatus, run_id)
        if run is None:
            return error("Deployment run not found.", 404)

        if run.Status is DeploymentStatus.RUNNING:
            return error("A running deployment cannot be reviewed yet.", 409)

        if run.Reviewed_At is None:
            run.Reviewed_At = datetime.now(timezone.utc)
            run.Reviewed_By = current_user.UserID
            create_user_log(current_user.UserID, f"Reviewed NCPA deployment NP-{run_id:04d}")
            db.session.commit()

        return success(run_detail(run), message="Deployment run marked as reviewed.")

    except Exception:
        db.session.rollback()
        current_app.logger.exception("An unexpected error occurred while reviewing a deployment run.")
        return error("An unexpected error occurred.", 500)


@system_bp.get('/deployment/ncpa/devices/trusted')
@login_required
@require_permission('system.deploy.ncpa')
def get_trusted_devices():
    """
    List trust-confirmed devices ready for deployment.

    Returns devices that have:
    - A saved SSH host-key fingerprint (``Key_Fingerprint IS NOT NULL``)
    - An ``NCPADeployment`` record that is Pending NCPA or Deployment Failed
      (so a failed device can be retried)

    These are devices the admin can select, supply credentials for,
    and then deploy.

    Response (200):
        { "success": true, "data": { "devices": [ {"device_id": int, "hostname": str, "ip_address": str}, ... ] } }
    """
    try:
        devices = db.session.scalars(
            sa.select(NetworkDiscovery)
            .join(
                SSHCredentials,
                NetworkDiscovery.NetDiscoveryID == SSHCredentials.NetworkDiscoveryID
            )
            .join(
                NCPADeployment,
                NetworkDiscovery.NetDiscoveryID == NCPADeployment.NetworkDiscoveryID
            )
            .where(
                SSHCredentials.Key_Fingerprint.is_not(None),
                NCPADeployment.Agent_Status.in_(DEPLOYABLE_AGENT_STATUSES),
                NetworkDiscovery.Include_Device_In_Scanning.is_(True)
            )
        ).all()

        # The front-end must supply username and password per device before deploying
        return success({
            "devices": [
                {
                    "device_id": device.NetDiscoveryID,
                    "hostname": device.Hostname,
                    "ip_address": device.IP_Address,
                }
                for device in devices
            ]
        })

    except Exception:
        current_app.logger.exception("An unexpected error occurred.")
        return error("An unexpected error occurred.", 500)


@system_bp.post('/deployment/ncpa/<int:device_id>/refresh-disks')
@login_required
@require_permission('system.deploy.ncpa')
def refresh_ncpa_disks(device_id):
    """
    Re-read the logical disks a deployed NCPA agent serves (after a disk was
    added or removed), store them, and regenerate the Nagios config so the
    disk services match.

    Response (200):
        { "success": true, "data": { "device_id": int, "disks": [str],
                                      "config_applied": bool, "message": str } }

    Errors:
        404 – Device not found or NCPA not deployed on it.
        502 – The agent returned no disks (unreachable or none mounted).
        500 – Unexpected error.
    """
    try:
        device = db.session.get(NetworkDiscovery, device_id)
        deployment = db.session.scalar(
            sa.select(NCPADeployment).where(
                NCPADeployment.NetworkDiscoveryID == device_id,
                NCPADeployment.Agent_Status == AgentStatus.DEPLOYED,
                NCPADeployment.Token.is_not(None),
            )
        )
        if device is None or deployment is None:
            return error("NCPA is not deployed on this device.", 404)

        disks = refresh_ncpa_partitions(deployment, device.IP_Address)
        if not disks:
            return error("The NCPA agent reported no monitorable disks.", 502)

        from app.network_discovery.create_host_cfg import regenerate_and_apply_config
        applied, message = regenerate_and_apply_config()
        return success({
            "device_id": device_id,
            "disks": disks,
            "config_applied": applied,
            "message": message,
        })

    except Exception:
        db.session.rollback()
        current_app.logger.exception("An unexpected error occurred.")
        return error("An unexpected error occurred.", 500)
