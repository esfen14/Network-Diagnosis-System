
from server.app.system_models import UserStatus


def convert_user_status(status):
    status = status.strip().lower()
    for main_status in UserStatus:
        if status == main_status.value.lower():
            return UserStatus