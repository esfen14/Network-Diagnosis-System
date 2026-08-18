from flask import current_app
import sqlalchemy as sa
from app import db
from datetime import datetime
from app.logging.user_activity import create_user_log


def create_deployment_log(user_id, hostname, notes, deployemnt_status, deployed_at, updated_at):
    try:
        return 0
    except Exception as e:
        current_app.logger.exception(f"Cannot create export log for user {user_id} error: {e}")

