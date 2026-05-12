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
from pathlib import Path

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


def resolve_translations_directory(app) -> str:
    """Absolute path to gettext catalogs (Backoffice/translations).

    - Local dev: repo folder next to the ``app`` package (``../translations``).
    - Docker/Azure: entrypoint symlinks ``/app/translations`` to persistent storage;
      same layout relative to ``app.root_path``.

    Override with env ``BACKOFFICE_TRANSLATIONS_DIR`` (absolute path) when needed.
    """
    env_override = (os.environ.get("BACKOFFICE_TRANSLATIONS_DIR") or "").strip()
    if env_override:
        candidate = os.path.abspath(os.path.normpath(env_override))
        if os.path.isdir(candidate):
            return candidate
        app.logger.warning(
            "BACKOFFICE_TRANSLATIONS_DIR is not a directory (%s); using default next to app package",
            candidate,
        )
    return os.path.abspath(os.path.normpath(os.path.join(app.root_path, "..", "translations")))


def ensure_translation_mo_files(app, translations_dir: str) -> None:
    """Compile messages.po -> messages.mo when .mo is missing or older (gettext loads .mo only)."""
    try:
        import polib  # type: ignore
    except ImportError:
        return

    root = Path(translations_dir)
    if not root.is_dir():
        return

    for locale_dir in sorted(root.iterdir()):
        if not locale_dir.is_dir() or locale_dir.name.startswith("."):
            continue
        lc = locale_dir / "LC_MESSAGES"
        po = lc / "messages.po"
        mo = lc / "messages.mo"
        if not po.is_file():
            continue
        try:
            need = not mo.is_file() or po.stat().st_mtime > mo.stat().st_mtime
            if not need:
                continue
            polib.pofile(str(po)).save_as_mofile(str(mo))
            app.logger.info("Compiled gettext catalog: %s", mo)
        except Exception as e:
            app.logger.warning("Could not compile %s: %s", po, e)


# Must run *before* babel.init_app() so Flask-Babel resolves the real catalog path.
# If this runs after init_app, Babel keeps the default ``translations`` dir under
# app.root_path (wrong — catalogs live in Backoffice/translations/).
def configure_babel(app):
    translations_dir = resolve_translations_directory(app)
    app.config["BACKOFFICE_TRANSLATIONS_DIR"] = translations_dir
    app.config["BABEL_TRANSLATION_DIRECTORIES"] = translations_dir
    app.config.setdefault("BABEL_DEFAULT_LOCALE", "en")
    app.config.setdefault("BABEL_DEFAULT_TIMEZONE", "UTC")

    ensure_translation_mo_files(app, translations_dir)

    if app.config.get("DEBUG", False):
        app.config["BABEL_CACHE_ENABLED"] = False

        @app.before_request
        def force_reload_translations():
            if app.config.get("DEBUG", False):
                from flask_babel import refresh
                with suppress(Exception):
                    refresh()
