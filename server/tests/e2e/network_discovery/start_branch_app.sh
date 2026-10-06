#!/bin/bash
# Start the checked-out branch's Flask app on 127.0.0.1:8001 for the plugin-driven monitoring harness.
# Uses server/system.db (run `flask db upgrade` first; preflight checks the revision). Optional environment:
#   NAGIOS_USERNAME / NAGIOS_PASSWORD   Nagios API account (live status chips)
#   NAGIOS_BIN                          rejection wrapper from `run_tests.py prepare-rejection`
#   PINPOINT_PORT_ARCHIVE_AFTER_DAYS    e.g. 0.001 for the PORT-LIFECYCLE archive step
set -e
SERVER="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$SERVER"
: "${SECRET_KEY:=lab-test-secret}"
export SECRET_KEY PINPOINT_NETWORKS="${PINPOINT_NETWORKS:-10.0.2.0/28}" PINPOINT_SCHEDULER="${PINPOINT_SCHEDULER:-1}"
exec .venv/bin/python -m flask --app app:app run --port 8001 --no-reload
