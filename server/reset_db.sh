#!/bin/bash
# Rebuild both development databases from the committed migrations and
# fill them with development seed data (test users included).
# Never run this on a production server — it deletes system.db and history.db.
set -e
cd "$(dirname "$0")"

if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
elif [ -f ../.venv/bin/activate ]; then
    source ../.venv/bin/activate
fi

echo "Using python: $(which python)"
rm -f system.db history.db
flask db upgrade
flask seed
echo "DONE"
