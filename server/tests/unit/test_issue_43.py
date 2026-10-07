import pytest
from app.nagios.status import insert_host_status_data
from app.history_models import HostStatus, HostStateType
import sqlalchemy as sa
from app import db

# This test tries to reproduce the AttributeError when host status is 'pending'
def test_insert_pending_host_does_not_crash(db_session, caplog):
    # Prepare payload with 'pending' status
    payload = {
        "name": "pending-host",
        "status": "pending",
        "last_update": 1_790_418_781_000,
        "plugin_output": "Pending",
        "state_type": "soft",
        "current_attempt": 1,
        "max_attempts": 3,
        "last_check": 1_790_418_781_000,
        "next_check": 1_790_419_081_000,
        "acknowledgement_type": "none",
        "is_flapping": False,
        "notifications_enabled": True,
    }

    # Should not raise AttributeError and should not log "Failed to insert host status"
    with caplog.at_level("ERROR"):
        insert_host_status_data(payload)
        
    for record in caplog.records:
        assert "Failed to insert host status" not in record.message
    
    # Verification: Ensure it was not inserted, or if we decide to insert it, what status it has.
    row = db_session.session.scalar(
        sa.select(HostStatus).where(HostStatus.Hostname == "pending-host")
    )
    
    assert row is None
