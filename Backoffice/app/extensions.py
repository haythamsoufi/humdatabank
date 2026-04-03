from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_babel import Babel
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
from contextlib import suppress

# Initialize extensions
db = SQLAlchemy()
login = LoginManager()
login.login_view = "auth.login"
login.login_message = None
login.login_message_category = "info"
migrate = Migrate()
babel = Babel()
csrf = CSRFProtect()
mail = Mail()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
)

# Configure Babel — translations live at Backoffice/translations/ (one level
# above app/), so the relative path from app.root_path is "../translations".
def configure_babel(app):
    app.config.setdefault('BABEL_TRANSLATION_DIRECTORIES', '../translations')
    app.config.setdefault('BABEL_DEFAULT_LOCALE', 'en')
    app.config.setdefault('BABEL_DEFAULT_TIMEZONE', 'UTC')

    if app.config.get('DEBUG', False):
        app.config['BABEL_CACHE_ENABLED'] = False

        @app.before_request
        def force_reload_translations():
            if app.config.get('DEBUG', False):
                from flask_babel import refresh
                with suppress(Exception):
                    refresh()
