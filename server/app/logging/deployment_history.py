from app.system_models import DeploymentHistory
from flask import current_app
import sqlalchemy as sa
from app import db
from datetime import datetime
from app.logging.user_activity import create_user_log


def create_deployment_log(user_id, hostname, notes, deployemnt_status, deployed_at, updated_at):
    try:
        action = f"NCPA Deployment for {hostname}"
        user_log = create_user_log(user_id, action)

        deployment_history = DeploymentHistory(
            Notes = notes,
            Deployment_Status = deployemnt_status,
            Deployed_At = deployed_at,
            Updated_At = updated_at,
            LogID = user_log.LogID
        )
        db.session.add(deployment_history)

        db.session.commit

        return user_log, deployment_history
    except Exception as e:
        current_app.logger.exception(f"Cannot create export log for user {user_id} error: {e}")

