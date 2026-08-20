from app.system_models import NCPADeploymentStatus, DeploymentStatus
from flask import current_app
import sqlalchemy as sa
from app import db
from datetime import datetime
from app.logging.user_activity import create_user_log


def create_ncpa_deployment_status(user_id):
    try:
        action = "NCPA Deployed"
        user_log = create_user_log(user_id, action)

        ncpa_deploymenet_staus = NCPADeploymentStatus(
            Status= DeploymentStatus.RUNNING,
            Progress= 0,
            Message= "NCPA Deloymnet process starting.",
            LogID = user_log.LogID
        )

        db.session.add(ncpa_deploymenet_staus)
        db.session.commit()

        return ncpa_deploymenet_staus
    except Exception as e:
        current_app.logger.exception(f"Cannot create NCPA Deployment log for user {user_id} error: {e}")

def update_ncpa_deployment_status(ncpa_deployment_status_id, status, progress, message, competed_at=None,error=None):
    try:
        ncpa_deployment_status = db.session.scalar(
            sa.Select(NCPADeploymentStatus)
            .where(
                NCPADeploymentStatus.NCPADeployStatusID == ncpa_deployment_status_id
            )
        )

        if ncpa_deployment_status is None:
            raise ValueError(
                f"NCPA Deployment status {ncpa_deployment_status_id} does not exist"
            )

        ncpa_deployment_status.Status = status
        ncpa_deployment_status.Progress = progress
        ncpa_deployment_status.Message = message
        ncpa_deployment_status.Completed_At = competed_at
        ncpa_deployment_status.Error = error

        db.session.commit()

    except Exception as e:
        current_app.logger.exception(f"Cannot update NCPA Deployement log {ncpa_deployment_status_id}")

def get_deployment_ncpa_status():
    try:
        return db.session.scalar(
            sa.select(NCPADeploymentStatus)
            .order_by(NCPADeploymentStatus.Start_At.desc()
                      ).limit(1)
        )

    except Exception as e:
        current_app.logger.exception(f"An Error Occured.")
        raise ValueError("An Error Occured")
    
def calculate_progress(current, total, start, end):
    if total <= 0:
        return end

    return int(start + (current / total) * (end - start))