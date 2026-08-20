from flask_login import login_required, current_user
from app import app, db
import sqlalchemy as sa
from flask import request
import threading
from app.api.system import system_bp
from app.api.helper.database_access.permissions import require_permission
from app.logging.deployment_history import get_deployment_ncpa_status
from app.system_models import NetworkDiscovery, SSHCredentials
from app.ncpa_deployment.ncpa_deployment import *

deploy_ncpa_thread = None

@system_bp.get('/deployment/ncpa/<int:device_id>/fingerprint')
@login_required
@require_permission('system.deploy.ncpa')
def get_device_fingerprint(device_id):
    device = db.session.get(NetworkDiscovery, device_id)
    if device is None:
        return {"error": "Device not found"}, 404
    try:

        fingerprint = get_host_key_fingerprint(device.IP_Address)
    except Exception as e:
        current_app.logger.error("Could not reach device.")
        return {"message": "Could not reach device."}, 502

    return {
        "device_id": device_id,
        "ip_address": device.IP_Address,
        "fingerprint": fingerprint
    }, 200

@system_bp.post('/deployment/ncpa/<int:device_id>/confirm-trust')
@login_required
@require_permission('system.deploy.ncpa')
def confirm_device_trust(device_id):
    data = request.get_json()
    device = db.session.get(NetworkDiscovery, device_id)
    if device is None:
        return {"error": "Device not found"}, 404
    
    # Recreate the fingerprint rather than believing the client
    fingerprint = get_host_key_fingerprint(device.IP_Address)

    creds = db.session.scalar(
        sa.select(SSHCredentials).where(SSHCredentials.NetworkDiscoveryID == device_id)
    )

    if creds is None:
        return {"success" : False, "message": "That device id doesn't exist."}, 404

    creds.Key_Fingerprint = fingerprint
    db.session.commit()

    return {"success": True, "message": "Device fingerprint added."}, 200

@system_bp.post('/deployment/ncpa/')
@login_required
@require_permission('system.deploy.ncpa')
def deploy_ncpa():
    '''
        device_credentials: list of dicts like
        [
            {
            "device_id": 1,
            "username": "admin",
            "password": "password123"
            }, ...
        ]
    '''
    global deploy_ncpa_thread
    
    if deploy_ncpa_thread is not None and deploy_ncpa_thread.is_alive():
        return {"message": "NCPA is already being deployed."}, 400
    
    data = request.get_json()
    device_credentials = data.get("devices", [])  # list of {device_id, username, password}

    if not device_credentials:
        return {
            "error": "No devices were provided."
        }, 400
    
    validated_entries = []
    rejected_entries = []

    for entry in device_credentials:
        device_id = entry["device_id"]
        creds = db.session.scalar(
            sa.select(SSHCredentials).where(SSHCredentials.NetworkDiscoveryID == device_id)
        )

        device = db.session.get(NetworkDiscovery, device_id)

        if device is None:
            rejected_entries.append({"device_id": device_id, "reason": "Device Does not exist"})
            continue

        ip_address = device.IP_Address

        if creds is None or creds.Key_Fingerprint is None:
            rejected_entries.append({"device_id": device_id, "reason": "Not trust-confirmed"})
            continue

        current_fingerprint = get_host_key_fingerprint(ip_address)
        if current_fingerprint != creds.Key_Fingerprint:
            rejected_entries.append({"device_id": device_id, "reason": "Host key mismatch"})
            continue

        validated_entry = { 
            "device_id": device_id, 
            "ip_address": ip_address, 
            "username": entry["username"], 
            "password": entry["password"] 
        }

        validated_entries.append(validated_entry)

    deploy_ncpa_thread = threading.Thread(
        daemon=True,
        target=install_process,
        args=(app, current_user.UserID, validated_entries)
    )
    deploy_ncpa_thread.start()

    return {
        "message": f"Deployment started for {len(validated_entries)} device(s)",
        "rejected": rejected_entries
    }, 202


@system_bp.get('/deployment/ncpa/status')
@login_required
@require_permission('system.deploy.ncpa')
def deploy_ncpa_status():
    if deploy_ncpa_thread is None or not deploy_ncpa_thread.is_alive():
        return {"message": "There is no NCPA deployment occuring right now."}, 200

    deployment_info = get_deployment_ncpa_status()

    return {
            "Status": deployment_info.Status.value,
            "Progress": deployment_info.Progress,
            "Message": deployment_info.Message,
            "Error": deployment_info.Error,
    }, 200
