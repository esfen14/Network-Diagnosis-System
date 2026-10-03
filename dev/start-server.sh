#!/bin/sh
#
# - FLASK_DEBUG=0 so the Nagios poller starts: in debug mode without the
#   reloader, server/app/scheduler.py skips starting it.
# - NAGIOS_HOST defaults to the Nagios box on Tailscale; override it to
#   point elsewhere, e.g. NAGIOS_HOST=192.168.130.10 dev/start-server.sh
cd "$(dirname "$0")/../server" || exit 1
NAGIOS_HOST="${NAGIOS_HOST:-100.91.50.105}" FLASK_DEBUG=0 \
  exec venv/bin/flask run --host 127.0.0.1 --port "${PORT:-5001}"

# paki-change guys yung port number sa 5001 to 5000 para ma run yung flask server sa default port.
