from server.app.system_models import UserStatus
from typing import Union
from email_validator import validate_email

def convert_user_status(status):
    status = status.strip().lower()
    for main_status in UserStatus:
        if status == main_status.value.lower():
            return UserStatus


def normalize_email(email):
    return validate_email(email, check_deliverability=True).normalized