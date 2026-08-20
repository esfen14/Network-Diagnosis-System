from app.system_models import NetworkDiscoveryStatus, DiscoveryStatus
from flask import current_app
import sqlalchemy as sa 
from app import db
from datetime import datetime, timezone
from app.logging.user_activity import create_user_log

def create_network_discovery_status(user_id):
    try:
        user_log = create_user_log(user_id, "Discovering Network Hosts") 

        network_discovery_status = NetworkDiscoveryStatus(
            Status = DiscoveryStatus.RUNNING,
            Progress = 0, 
            Message = "Network Discovery process starting.",
            LogID = user_log.LogID
        )

        db.session.add(network_discovery_status)
        db.session.commit()

        return network_discovery_status
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(f"Cannot create network dicovery status {e}")
        raise

def update_network_discovery_status(network_discovery_status_id, status, progress, message, completed_at=None, error=None):
    try:

        network_discovery_status = db.session.scalar(
            sa.Select(NetworkDiscoveryStatus).where(
                NetworkDiscoveryStatus.DiscoveryStatusID == network_discovery_status_id
            )
        )

        if network_discovery_status is None:
            raise ValueError(
                f"Discovery status {network_discovery_status_id} does not exist"
            )

        network_discovery_status.Status = status
        network_discovery_status.Progress = progress
        network_discovery_status.Message = message
        network_discovery_status.Completed_At = completed_at
        network_discovery_status.Error = error

        db.session.commit()

        return NetworkDiscoveryStatus
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(f"Cannot create network dicovery status {e}")

def get_network_discovery_status():
    try:
        return db.session.scalar(
            sa.Select(NetworkDiscoveryStatus)
            .where(NetworkDiscoveryStatus.Status == DiscoveryStatus.RUNNING)
            .order_by(NetworkDiscoveryStatus.Start_At.desc()
                      ).limit(1)
        )
    except Exception as e:
        current_app.logger.exception(f"An Error Occured")
        raise ValueError("An Error Occured")

def calculate_progress(current, total, start, end):
    if total <= 0:
        return end

    return int(start + (current / total) * (end - start))