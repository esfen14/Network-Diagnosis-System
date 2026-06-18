from app.system_models import UserStatus
from typing import Union
from email_validator import validate_email

"""
This is a separation of conern regarding conversion of data
"""
def convert_user_status(status):
    status = status.strip().lower()
    for main_status in UserStatus:
        if status == main_status.value.lower():
            return main_status


def normalize_email(email):
    return validate_email(email, check_deliverability=False).normalized