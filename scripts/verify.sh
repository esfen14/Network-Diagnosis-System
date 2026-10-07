#!/usr/bin/env bash
# Single verification entry point for agents, developers and CI.
#
# Usage: scripts/verify.sh [docs|backend|frontend|all]   (default: all)
#
# Exits non-zero on the first failing stage. CI runs each stage as its own job
# (.github/workflows/ci.yml) with the same commands, so a green local run means
# a green pipeline. See "spec files/Agent_Workflow_and_CI.md".
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
stage="${1:-all}"

docs() {
  echo "==> docs: relative markdown links (AGENTS.md, README.md, spec files/, docs/, server/tests/)"
  python3 -I "$root/scripts/check_doc_links.py" "$root"
  echo "==> docs: environment variables match the README table"
  python3 -I "$root/scripts/check_env_drift.py"
  echo "==> docs: browser routes match App.tsx, pageAccess.ts and the spec"
  python3 -I "$root/scripts/check_frontend_route_drift.py"
}

backend() {
  echo "==> backend: isolated pytest suite"
  cd "$root/server"
  local py=python
  if [ -x .venv/bin/python ]; then py=.venv/bin/python; fi
  echo "==> backend: route catalog matches the Flask routes"
  FLASK_DEBUG=1 "$py" "$root/scripts/check_route_drift.py"
  echo "==> backend: every client /api call matches a Flask route"
  FLASK_DEBUG=1 "$py" "$root/scripts/check_client_api_drift.py"
  FLASK_DEBUG=1 "$py" -m pytest tests/unit -q
}

frontend() {
  echo "==> frontend: test + build"
  cd "$root/client"
  npm run test
  npm run build
  echo "==> frontend: lint (errors block; warnings are tracked in Implementation_Status.md)"
  npm run lint
}

case "$stage" in
  docs) docs ;;
  backend) backend ;;
  frontend) frontend ;;
  all) docs; backend; frontend ;;
  *) echo "unknown stage: $stage" >&2; exit 2 ;;
esac
echo "verify: $stage OK"
