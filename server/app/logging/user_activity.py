from app.system_models import ActivityLog
from flask import current_app
import sqlalchemy as sa
from app import db
from datetime import datetime


def create_user_log(user_id, action):
    try:
        user_log = ActivityLog(
            Action_Type = action,
            UserID = user_id
        )

        db.session.add(user_log)
        db.session.flush()

        return user_log
    except Exception as e:
        current_app.logger.exception(f"Cannot create log for user {user_id} error: {e}")

