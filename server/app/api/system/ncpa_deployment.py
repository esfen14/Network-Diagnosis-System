from flask_login import login_required, current_user
from flask import request, current_app
from app import app, db
import sqlalchemy as sa
import threading
from app.api.system import system_bp
from app.api.helper import success, error
from app.api.helper.database_access.permissions import require_permission
from app.logging.deployment_history import get_deployment_ncpa_status
from app.system_models import NetworkDiscovery, SSHCredentials
from app.ncpa_deployment.ncpa_deployment import *

deploy_ncpa_thread = None
deploy_ncpa_thread_stop_event = threading.Event()


@system_bp.get('/deployment/ncpa/devices')
@login_required
@require_permission("system.deploy.ncpa")
def get_ncpa_eligible_devices():
    try:
        devices = db.session.scalars(
            sa.select(NetworkDiscovery)
            .where(NetworkDiscovery.NCPA_Eligible.is_(True))
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
    try:
        device = db.session.get(NetworkDiscovery, device_id)

        if device is None:
            return error("Device not found.", 404)

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
    try:
        device = db.session.get(NetworkDiscovery, device_id)

        if device is None:
            return error("Device not found.", 404)

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
    '''
    Expected JSON body:
    {
        "devices": [
            { "device_id": 1, "username": "admin", "password": "password123" },
            ...
        ]
    }
    '''
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
    global deploy_ncpa_thread

    if deploy_ncpa_thread is None or not deploy_ncpa_thread.is_alive():
        return error("There is no NCPA deployment running.", 400)

    deploy_ncpa_thread_stop_event.set()
    return success(message="NCPA deployment stop requested.")


@system_bp.get('/deployment/ncpa/status')
@login_required
@require_permission('system.deploy.ncpa')
def deploy_ncpa_status():
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
                NCPADeployment.Agent_Status == AgentStatus.PENDING_NCPA
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
