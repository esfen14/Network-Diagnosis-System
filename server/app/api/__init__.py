from flask import Blueprint
from app.api import( 
    user,
    system,
    plugin
)

api_bp = Blueprint('api', __name__, url_prefix='/api')


# import modules
modules = [
    user.user_bp,
    system.system_bp,
    plugin.plugin_bp
    ]

for module in modules:
    api_bp.register_blueprint(module)