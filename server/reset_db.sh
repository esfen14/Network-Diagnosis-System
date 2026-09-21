#!/bin/bash
set -e
cd /Users/karell/Documents/GitHub/Network-Diagnosis-System/server
source venv/bin/activate
export FLASK_APP=server.py
echo "Using python: $(which python)"
flask db init
flask db migrate -m "initial"
flask db upgrade
flask seed --reset
echo "DONE"
