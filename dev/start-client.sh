#!/bin/sh
# starst the Vite front end for local development
# started by dev/start-server.sh (port 5001).
cd "$(dirname "$0")/../client" || exit 1
API_PROXY_TARGET="${API_PROXY_TARGET:-http://127.0.0.1:5001}" \
  exec npm run dev -- --port 5173 --strictPort
