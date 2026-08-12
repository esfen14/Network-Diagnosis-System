from app.system_models import ExportLog
from flask import current_app
import sqlalchemy as sa
from app import db
from datetime import datetime, timezone
from app.logging.user_activity import create_user_log


def create_export_log(user_id, report_type, report_format, start_date, end_date):
    try:
        action = f"Export {report_type}"
        user_log = create_user_log(user_id, action)

        export_log = ExportLog(
            Report_Type = report_type,
            Export_Format = report_format,
            Start_Date= start_date,
            End_Date= end_date,
            LogID = user_log.LogID
        )

        db.session.add(export_log)

        db.session.commit

        return user_log, export_log
    except Exception as e:
        current_app.logger.exception(f"Cannot create export log for user {user_id} error: {e}")

