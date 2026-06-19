from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from config import Config

import os

# Instantiate the application
app = Flask(__name__)

# Call the configurations used
app.config.from_object(Config)

# instantiate the database of the app
db = SQLAlchemy(app)

# instantiate migrate
migrate = Migrate(app, db)

# instantiate the Login Manager
login = LoginManager(app)
login.login_view = None

from app.api.commands.seed import seed_command

app.cli.add_command(seed_command)

from app import system_models, history_models

#where the bluprints are called and registered
from app.api.user import user_bp

app.register_blueprint(user_bp)