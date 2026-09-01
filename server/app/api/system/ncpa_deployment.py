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
3. Confirm trust (save fingerprint)  →  4. Supply credentials & start  →
5. Background deployment  →  6. Monitor status

Security
--------
- Every SSH connection verifies the device's host-key fingerprint.
- The deployment user on the remote device has restricted sudo (one command only).
- All routes require the ``system.deploy.ncpa`` permission.

Module-level state
------------------
deploy_ncpa_thread          – Background daemon thread (``None`` when idle)
deploy_ncpa_thread_stop_event – Threading.Event for graceful stop

Routes
------
GET    /system/deployment/ncpa/devices            – List NCPA-eligible devices
GET    /system/deployment/ncpa/<id>/fingerprint    – Fetch live SSH host-key fingerprint
POST   /system/deployment/ncpa/<id>/confirm-trust  – Save/confirm device fingerprint
POST   /system/deployment/ncpa/start               – Start background deployment
POST   /system/deployment/ncpa/stop                – Request running deployment to stop
GET    /system/deployment/ncpa/status              – Latest deployment job status
GET    /system/deployment/ncpa/devices/trusted     – Trust-confirmed devices ready for deploy
"""

from flask_login import login_required, current_user
from flask import request, current_app
from app import app, db
import sqlalchemy as sa
import threading
from app.api.system import system_bp
from app.api.helper import success, error
from app.api.helper.database_access.permissions import require_permission
from app.logging.deployment_history import get_deployment_ncpa_status
from app.system_models import NetworkDiscovery, SSHCredentials, NCPADeployment, AgentStatus
from app.ncpa_deployment.ncpa_deployment import *

deploy_ncpa_thread = None
deploy_ncpa_thread_stop_event = threading.Event()


@system_bp.get('/deployment/ncpa/devices')
@login_required
@require_permission("system.deploy.ncpa")
def get_ncpa_eligible_devices():
    """
    List all devices marked as NCPA-eligible.

    Returns devices where ``NCPA_Eligible == True``, sorted by hostname.

    Response (200):
        { "success": true, "data": { "devices": [ {"device_id": int, "hostname": str}, ... ] } }
    """
    try:
        devices = db.session.scalars(
            sa.select(NetworkDiscovery)
            .where(NetworkDiscovery.NCPA_Eligible.is_(True))
            .where(NetworkDiscovery.Include_Device_In_Scanning.is_(True))
            .order_by(NetworkDiscovery.Hostname.asc())
        ).all()

        return success({
            "devices": [
                {
                    "device_id": device.NetDiscoveryID,
                    "hostname": device.Hostname,
                }
                for device in devices
            ]
        })

    except Exception:
        current_app.logger.exception("An unexpected error occurred.")
        return error("An unexpected error occurred.", 500)


@system_bp.get('/deployment/ncpa/<int:device_id>/fingerprint')
@login_required
@require_permission('system.deploy.ncpa')
def get_device_fingerprint(device_id):
    """
    Fetch the live SSH host-key fingerprint for a device.

    Connects to the device's IP address and retrieves its current
    SSH host-key (SHA-256, base64-encoded). Used during the trust-
    confirmation flow so the admin can verify before approving.

    Args:
        device_id: Primary key of the NetworkDiscovery record.

    Response (200):
        { "success": true, "data": { "device_id": int, "ip_address": str, "fingerprint": str } }

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

        try:
            fingerprint = get_host_key_fingerprint(device.IP_Address)
        except Exception:
            current_app.logger.error("Could not reach device at %s.", device.IP_Address)
            return error("Could not reach device.", 502)

        return success({
            "device_id": device_id,
            "ip_address": device.IP_Address,
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
    Save the device's current SSH host-key fingerprint.

    Re-fetches the live fingerprint server-side (does not trust the
    client) and stores it in the SSH_CREDENTIALS table. This is the
    "trust confirmation" step — once saved, the device can be deployed to.

    Args:
        device_id: Primary key of the NetworkDiscovery record.

    Response (200):
        { "success": true, "message": "Device fingerprint saved." }

    Errors:
        404 – Device not found, or no SSH credentials entry exists.
        500 – Unexpected error.
    """
    try:
        device = db.session.get(NetworkDiscovery, device_id)

        if device is None:
            return error("Device not found.", 404)

        if not device.Include_Device_In_Scanning:
            return error("Device not included in scanning.", 404)

        # Recreate the fingerprint server-side rather than trusting the client
        fingerprint = get_host_key_fingerprint(device.IP_Address)

        creds = db.session.scalar(
            sa.select(SSHCredentials).where(
                SSHCredentials.NetworkDiscoveryID == device_id
            )
        )

        if creds is None:
            return error("That device has no credentials entry.", 404)

        creds.Key_Fingerprint = fingerprint
        db.session.commit()

        return success(message="Device fingerprint saved.")

    except Exception:
        current_app.logger.exception("An unexpected error occurred.")
        return error("An unexpected error occurred.", 500)


@system_bp.post('/deployment/ncpa/start')
@login_required
@require_permission('system.deploy.ncpa')
def deploy_ncpa():
    """
    Start a background NCPA deployment job for one or more devices.

    Validates each device (existence, trust confirmation, host-key match),
    then launches a daemon thread that runs the actual deployment
    (bootstrap user → install SSH key → install NCPA → verify).

    Request body (JSON):
        {
            "devices": [
                { "device_id": 1, "username": "admin", "password": "secret" },
                ...
            ]
        }

    Rejection reasons per device:
        - "Device does not exist." – no NetworkDiscovery record
        - "Not trust-confirmed."   – no SSH credentials or fingerprint saved
        - "Host key mismatch."     – live fingerprint differs from stored

    Response (202):
        {
            "success": true,
            "data": { "started": int, "rejected": [{ "device_id": int, "reason": str }, ...] },
            "message": "Deployment started for N device(s)."
        }

    Errors:
        400 – Deployment already running, or no devices provided.
        500 – Unexpected error.
    """
    global deploy_ncpa_thread

    if deploy_ncpa_thread is not None and deploy_ncpa_thread.is_alive():
        return error("NCPA is already being deployed.", 400)

    data = request.get_json()
    device_credentials = data.get("devices", []) if data else []

    if not device_credentials:
        return error("No devices were provided.", 400)

    validated_entries = []
    rejected_entries = []

    for entry in device_credentials:
        device_id = entry["device_id"]

        device = db.session.get(NetworkDiscovery, device_id)
        if device is None:
            rejected_entries.append({
                "device_id": device_id,
                "reason": "Device does not exist."
            })
            continue

        if not device.Include_Device_In_Scanning:
            rejected_entries.append({
                "device_id": device_id,
                "reason": "Device is not included in scanning."
            })
            continue

        creds = db.session.scalar(
            sa.select(SSHCredentials).where(
                SSHCredentials.NetworkDiscoveryID == device_id
            )
        )

        if creds is None or creds.Key_Fingerprint is None:
            rejected_entries.append({
                "device_id": device_id,
                "reason": "Not trust-confirmed."
            })
            continue

        current_fingerprint = get_host_key_fingerprint(device.IP_Address)
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
              current_user.UserID,
              validated_entries,
              deploy_ncpa_thread_stop_event
              )
    )
    deploy_ncpa_thread.start()

    return success(
        {
            "started": len(validated_entries),
            "rejected": rejected_entries,
        },
        message=f"Deployment started for {len(validated_entries)} device(s).",
        status=202,
    )


@system_bp.post('/deployment/ncpa/stop')
@login_required
@require_permission('system.deploy.ncpa')
def stop_ncpa_deployment():
    """
    Request the running deployment thread to stop.

    Sets the ``deploy_ncpa_thread_stop_event`` flag. The background
    thread checks this flag between devices and will halt on the next
    evaluation.

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
    Return the latest NCPA deployment job's status.

    Queries the most recent record from ``NCPA_DEPLOYMENT_STATUS``
    (ordered by ``Start_At`` descending).

    Possible ``status`` values:
        ``Running``, ``Success``, ``Partial Failure``, ``Failed``, ``Interrupted``

    Response (200):
        {
            "success": true,
            "data": {
                "id": int,
                "status": str,
                "progress": int,
                "message": str,
                "start_at": "ISO-8601",
                "completed_at": "ISO-8601" | null,
                "error": str | null
            }
        }

    When no deployment has occurred yet:
        { "success": true, "message": "No NCPA deployment has occurred yet." }
    """
    try:
        deployment_info = get_deployment_ncpa_status()

        if deployment_info is None:
            return success(message="No NCPA deployment has occurred yet.")

        return success({
            "id": deployment_info.NCPADeployStatusID,
            "status": deployment_info.Status.value,
            "progress": deployment_info.Progress,
            "message": deployment_info.Message,
            "start_at": deployment_info.Start_At.isoformat(),
            "completed_at": (
                deployment_info.Completed_At.isoformat()
                if deployment_info.Completed_At else None
            ),
            "error": deployment_info.Error,
        })

    except Exception:
        current_app.logger.exception("An unexpected error occurred.")
        return error("An unexpected error occurred.", 500)


@system_bp.get('/deployment/ncpa/devices/trusted')
@login_required
@require_permission('system.deploy.ncpa')
def get_trusted_devices():
    """
    List trust-confirmed devices ready for deployment.

    Returns devices that have:
    - A saved SSH host-key fingerprint (``Key_Fingerprint IS NOT NULL``)
    - An ``NCPADeployment`` record with ``Agent_Status == PENDING_NCPA``

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
                NCPADeployment.Agent_Status == AgentStatus.PENDING_NCPA,
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
