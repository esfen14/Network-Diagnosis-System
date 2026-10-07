import os
import secrets

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from config import Config
from flask_cors import CORS


# Instantiate the application
app = Flask(__name__)

CORS(app, supports_credentials=True)

# Call the configurations used
app.config.from_object(Config)

# Refuse to run without a real secret in production. In debug mode fall back
# to a random per-process key so `flask run` works without a server/.env
# (sessions then reset whenever the dev server restarts).
if not app.config.get("SECRET_KEY"):
    if not app.debug:
        raise RuntimeError(
            "SECRET_KEY is not set. Set it in the environment "
            "(e.g. /etc/pinpoint/pinpoint.env or server/.env)."
        )
    app.config["SECRET_KEY"] = secrets.token_hex(32)
    # secrets_store refuses to store a password under a key the next start would not have.
    app.config["SECRET_KEY_IS_TEMPORARY"] = True
    app.logger.warning("SECRET_KEY is not set; using a temporary key for this debug session.")

# Runtime folders are not tracked in git, so make sure they exist.
for folder in (app.config["HOST_CONFIG_DIR"], app.config["BACKUP_DIR"]):
    folder.mkdir(parents=True, exist_ok=True)

# instantiate the database of the app
db = SQLAlchemy(app)

# instantiate migrate
# render_as_batch lets Alembic alter SQLite tables (copy-and-move) instead
# of emitting ALTER statements SQLite does not support.
migrate = Migrate(app, db, render_as_batch=True)

# instantiate the Login Manager
login = LoginManager(app)
login.login_view = None

from app.api.commands.seed import (
    seed_command,
    init_production_command,
    sync_permissions_command,
    warn_if_permissions_missing,
)

app.cli.add_command(seed_command)
app.cli.add_command(init_production_command)
app.cli.add_command(sync_permissions_command)

from app import system_models, history_models, plugin_models

#where the bluprints are called and registered
from app.api import api_bp

app.register_blueprint(api_bp)

from app.scheduler import init_scheduler

# Only the serving process should poll Nagios and run automation jobs.
# Importing the app for a `flask` command or a script must not start them,
# so the scheduler is opt-in (the installer sets this for Gunicorn only).
if os.environ.get("PINPOINT_SCHEDULER", "0") == "1":
    with app.app_context():
        warn_if_permissions_missing(app.logger)
    init_scheduler()
