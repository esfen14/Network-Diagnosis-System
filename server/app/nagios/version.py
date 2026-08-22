import requests
from datetime import datetime, timezone
from flask import current_app

latest = ""

last_checked = datetime.now(timezone.utc)

def check_latest_version():
    try:
        response = requests.get(
            "https://api.github.com/repos/NagiosEnterprises/nagioscore/releases/latest",
            timeout=10
        )
        response.raise_for_status()
        
        latest = response.json()["tag_name"].split("-")[1]
        
        last_checked = datetime.now(timezone.utc)
    except requests.exceptions.HTTPError as e:
        current_app.logger.exception(f"Error: {e}")
    
    