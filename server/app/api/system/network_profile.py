from flask import request, current_app
from flask_login import login_required, current_user

from app import db
from app.api.system import system_bp
from app.api.helper import success, error, validate_json_data
from app.api.helper.database_access.permissions import require_permission
from app.system_models import NetworkProfile
from app.logging.user_activity import create_user_log
from app.api.helper.settings_flags import is_audit_logging_enabled

DEFAULT_NAME = "CICT Network"
DEFAULT_REFERENCE = ""
DETAIL_LABELS = ("IP Range", "Gateway Device", "Subnet Mask", "DNS Server", "ISP", "Location")
DEFAULT_DETAILS = {label: "" for label in DETAIL_LABELS}
MAX_NAME = 100
MAX_REFERENCE = 50
MAX_DETAIL = 100


def _serialize(row):
    details = dict(DEFAULT_DETAILS)
    if row is not None and row.Details:
        details.update({k: v for k, v in row.Details.items() if k in DETAIL_LABELS})
    return {
        "name": row.Name if row is not None else DEFAULT_NAME,
        "reference": (row.Reference or "") if row is not None else DEFAULT_REFERENCE,
        "details": [{"label": label, "value": details[label]} for label in DETAIL_LABELS],
    }


@system_bp.get('/network-profile')
@login_required
@require_permission('system.network_health')
def get_network_profile():
    try:
        return success(_serialize(db.session.get(NetworkProfile, 1)))
    except Exception:
        current_app.logger.exception("An unexpected error occurred while fetching the network profile.")
        return error("An unexpected error occurred.", 500)


@system_bp.put('/network-profile')
@login_required
@require_permission('settings.discovery')
def update_network_profile():
    data = request.get_json(silent=True)
    err = validate_json_data(data)
    if err is not None:
        return err

    name = data.get("name")
    reference = data.get("reference", "")
    details = data.get("details")
    if not isinstance(name, str) or not name.strip():
        return error("Network name is required.", 400)
    if len(name.strip()) > MAX_NAME:
        return error(f"Network name must be {MAX_NAME} characters or fewer.", 400)
    if not isinstance(reference, str) or len(reference.strip()) > MAX_REFERENCE:
        return error(f"Reference must be {MAX_REFERENCE} characters or fewer.", 400)
    if not isinstance(details, list):
        return error("Details must be a list.", 400)

    cleaned = {}
    for item in details:
        if not isinstance(item, dict) or item.get("label") not in DETAIL_LABELS:
            return error("Unknown detail field.", 400)
        value = item.get("value", "")
        if not isinstance(value, str) or len(value.strip()) > MAX_DETAIL:
            return error(f"{item['label']} must be {MAX_DETAIL} characters or fewer.", 400)
        cleaned[item["label"]] = value.strip()

    try:
        row = db.session.get(NetworkProfile, 1)
        if row is None:
            row = NetworkProfile(Id=1, Name=name.strip())
            db.session.add(row)
        row.Name = name.strip()
        row.Reference = reference.strip()
        row.Details = cleaned
        row.Updated_By = current_user.UserID
        if is_audit_logging_enabled():
            create_user_log(current_user.UserID, f"Updated network profile '{row.Name}'")
        db.session.commit()
        return success(_serialize(row), message="Network profile saved.")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("An unexpected error occurred while saving the network profile.")
        return error("An unexpected error occurred.", 500)
