import logging
import os
import sys
from datetime import timedelta
from dotenv import load_dotenv

# Bootstrap logging for config module (runs before app init)
logging.basicConfig(stream=sys.stderr, level=logging.WARNING, format="%(message)s")
_config_logger = logging.getLogger(__name__)

# Load environment variables from .env file(s)
# IMPORTANT: Never override existing environment variables (like DATABASE_URL from Fly.io)
# 1) default .env lookup (project root if running from root) - don't override existing
load_dotenv()
# 2) explicitly load Backoffice/.env to ensure local dev picks it up regardless of cwd
# Use override=False (default) to ensure .env files don't override system/env vars (e.g., Fly.io DATABASE_URL)
backoffice_env_path = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')), '.env')
load_dotenv(backoffice_env_path, override=False)

# Get the base directory of the application
basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

_ALLOWED_FLASK_CONFIGS = {"development", "production", "staging", "testing", "default", ""}


def _parse_bool(value, default: bool = False) -> bool:
    """Parse a config value as boolean. Only 'true' and 'false' are accepted (case-insensitive).
    Any other value (including empty) returns default."""
    normalized = str(value or "").strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return default


def _parse_log_mode(value, default: str = "normal") -> str:
    """
    Parse logging mode for human-friendly env configuration.

    Allowed:
    - quiet:   WARNING and above
    - normal:  INFO and above
    - debug:   DEBUG and above
    """
    normalized = str(value or "").strip().lower()
    if normalized in {"quiet", "normal", "debug"}:
        return normalized
    return default


def _parse_log_level(value, default: str = "INFO") -> str:
    """
    Parse explicit log level name (DEBUG/INFO/WARNING/ERROR/CRITICAL).
    Unknown/empty returns default.
    """
    normalized = str(value or "").strip().upper()
    if normalized in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        return normalized
    return default


def _resolve_app_version() -> str:
    """Version for admin UI and GitHub release comparison.

    Set ``APP_VERSION`` (e.g. deploy workflow passes latest GitHub release tag at image build).
    ``RELEASE_VERSION`` is only the container image stream tag (e.g. v1.7) and is not used here.
    Leading ``v``/``V`` is stripped to match GitHub ``tag_name`` handling in update checks.
    """
    raw = (os.environ.get("APP_VERSION") or "").strip()
    if raw:
        return raw.lstrip("vV")
    return "1.0.4"


def _is_development_mode() -> bool:
    """
    Determine if we're in development mode based on FLASK_CONFIG.

    Returns True if FLASK_CONFIG is 'development' or 'default' (or unset).
    Returns False otherwise (production, staging, testing, etc.)
    """
    flask_config = os.environ.get("FLASK_CONFIG", "").lower()
    return flask_config in {"development", "default", ""}


def _should_strict_validate(flask_config: str) -> bool:
    """
    Strict validation prevents a boot with missing/dangerous config.

    Default:
    - production/staging: strict
    - development/testing/default: non-strict
    Override with STRICT_ENV_VALIDATION=true or false.
    """
    override = os.environ.get("STRICT_ENV_VALIDATION")
    if override is not None and str(override).strip() != "":
        return _parse_bool(override, default=False)
    return flask_config in {"production", "staging"}


def _require_env(name: str, *, flask_config: str, hint: str = "") -> str:
    val = os.environ.get(name)
    if val is None or str(val).strip() == "":
        msg = f"{name} environment variable is required for {flask_config or 'default'}."
        if hint:
            msg += f" {hint}"
        raise RuntimeError(msg)
    return str(val)

def _load_supported_languages_from_settings(default_languages):
    """Return default supported languages.

    Note: Runtime settings are now stored in the database (system_settings table).
    These defaults are only used during app initialization before database is available.
    """
    # Ensure 'en' is included and is first
    normalized = list(default_languages)
    if 'en' not in normalized:
        normalized.insert(0, 'en')
    elif normalized[0] != 'en':
        normalized.remove('en')
        normalized.insert(0, 'en')
    return normalized

def _load_document_types_from_settings(default_document_types):
    """Return default document types.

    Note: Runtime settings are now stored in the database (system_settings table).
    These defaults are only used during app initialization before database is available.
    """
    return list(default_document_types)

def _load_age_groups_from_settings(default_age_groups):
    """Return default age groups.

    Note: Runtime settings are now stored in the database (system_settings table).
    These defaults are only used during app initialization before database is available.
    """
    return list(default_age_groups)

def _load_sex_categories_from_settings(default_sex_categories):
    """Return default sex categories.

    Note: Runtime settings are now stored in the database (system_settings table).
    These defaults are only used during app initialization before database is available.
    """
    return list(default_sex_categories)

ALLOWED_ENTITY_GROUPS = ['countries', 'ns_structure', 'secretariat']

def _load_enabled_entity_types_from_settings(default_entity_groups):
    """Return default enabled entity groups.

    Note: Runtime settings are now stored in the database (system_settings table).
    These defaults are only used during app initialization before database is available.
    """
    # Validate and normalize the defaults
    normalized = []
    seen = set()
    for g in default_entity_groups:
        key = str(g).strip().lower()
        if key in ALLOWED_ENTITY_GROUPS and key not in seen:
            seen.add(key)
            normalized.append(key)
    return normalized if normalized else list(default_entity_groups)

def _normalize_database_uri(uri):
    """Normalize database URI to ensure Postgres works across providers.

    - Convert postgres:// to postgresql:// (Heroku style)
    - Ensure psycopg2 driver is specified for SQLAlchemy
    """
    if not uri:
        return None
    # Normalize scheme
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    # Ensure driver is explicit
    if uri.startswith("postgresql://") and "+psycopg2" not in uri:
        uri = uri.replace("postgresql://", "postgresql+psycopg2://", 1)
    return uri

class Config:
    # Application version (shown in System Configuration page header); see _resolve_app_version()
    APP_VERSION = _resolve_app_version()
    # GitHub repository for update checks (owner/repo)
    GITHUB_REPO = os.environ.get("GITHUB_REPO", "haythamsoufi/humdatabank")
    # Optional GitHub personal access token for private repos (fine-grained token with Contents:read)
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

    # SECRET_KEY is critical for session security, CSRF protection, and token generation
    # In production, it MUST be set via environment variable
    _secret_key = os.environ.get("SECRET_KEY")
    _flask_config = os.environ.get("FLASK_CONFIG", "").lower()

    if _flask_config not in _ALLOWED_FLASK_CONFIGS:
        # Fail fast for unknown config names; otherwise callers often fall back to DevelopmentConfig (DEBUG=True).
        raise RuntimeError(
            f"Invalid FLASK_CONFIG='{_flask_config}'. Allowed: {sorted(c for c in _ALLOWED_FLASK_CONFIGS if c)}"
        )

    _KNOWN_WEAK_KEYS = {"dev_change_me", "change-me", "secret", "password", "development", "testing"}

    if not _secret_key:
        if _flask_config in ('production', 'staging'):
            _config_logger.error("=" * 80)
            _config_logger.error("ERROR: SECRET_KEY environment variable is required in %s!", _flask_config)
            _config_logger.error("=" * 80)
            _config_logger.error('Generate a secure key with: python -c "import secrets; print(secrets.token_urlsafe(32))"')
            raise RuntimeError(
                f"SECRET_KEY environment variable is required in {_flask_config}. "
                "Please set SECRET_KEY in your environment or deployment secrets. "
                "Generate a secure key with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
                " Without it, each Gunicorn worker process generates its own random key, "
                "breaking sessions/CSRF/mobile JWTs whenever requests land on a different worker."
            )
        else:
            import secrets
            _secret_key = secrets.token_urlsafe(32)
            _config_logger.warning("=" * 80)
            _config_logger.warning("SECURITY WARNING: SECRET_KEY not set in environment!")
            _config_logger.warning("=" * 80)
            _config_logger.warning("Generated secure random SECRET_KEY for this session.")
            _config_logger.warning("This key will change on each restart unless you set SECRET_KEY in your .env file.")
            _config_logger.warning("")
            _config_logger.warning("To use a fixed key, run:")
            _config_logger.warning('  python -c "import secrets; print(secrets.token_urlsafe(32))"')
            _config_logger.warning("")
            _config_logger.warning("Then add it to your .env file:")
            _config_logger.warning("  SECRET_KEY=your_generated_key_here")
            _config_logger.warning("=" * 80)
    elif _flask_config in ('production', 'staging'):
        if len(_secret_key) < 32:
            raise RuntimeError(
                f"SECRET_KEY is too short ({len(_secret_key)} chars). "
                "Production/staging requires at least 32 characters. "
                'Generate a secure key with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )
        if _secret_key.lower() in _KNOWN_WEAK_KEYS:
            raise RuntimeError(
                "SECRET_KEY is a known weak/default value. "
                'Generate a secure key with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )

    SECRET_KEY = _secret_key

    # Dedicated signing key for mobile JWT tokens. Falls back to SECRET_KEY when
    # not set.  Using a separate secret limits blast radius: rotating one key
    # does not invalidate the other.
    MOBILE_JWT_SECRET = os.environ.get("MOBILE_JWT_SECRET") or _secret_key

    # Optional shared plaintext for Flutter `MOBILE_APP_API_KEY` (X-Mobile-Auth / Bearer on /api/v1).
    # When set, requests match this key even if no `api_keys` row exists (e.g. Fly without seeding DB keys).
    # DB-managed keys are still checked first; a matching but revoked/expired DB key is not bypassed.
    _mobile_app_api_key_raw = (os.environ.get("MOBILE_APP_API_KEY") or "").strip()
    MOBILE_APP_API_KEY = _mobile_app_api_key_raw or None
    try:
        _rl = int((os.environ.get("MOBILE_APP_API_KEY_RATE_LIMIT_PER_MINUTE") or "300").strip())
        MOBILE_APP_API_KEY_RATE_LIMIT_PER_MINUTE = _rl if _rl > 0 else 300
    except (TypeError, ValueError):
        MOBILE_APP_API_KEY_RATE_LIMIT_PER_MINUTE = 300

    # reCAPTCHA Enterprise (IFRC Indicator Bank public suggestion compat route)
    RECAPTCHA_PROJECT_ID = (os.environ.get("RECAPTCHA_PROJECT_ID") or "").strip() or None
    RECAPTCHA_API_KEY = (os.environ.get("RECAPTCHA_API_KEY") or "").strip() or None
    RECAPTCHA_SITE_KEY = (os.environ.get("RECAPTCHA_SITE_KEY") or "").strip() or None
    RECAPTCHA_EXPECTED_ACTION = (os.environ.get("RECAPTCHA_EXPECTED_ACTION") or "SendSuggestion").strip()
    try:
        RECAPTCHA_MIN_SCORE = float((os.environ.get("RECAPTCHA_MIN_SCORE") or "0.5").strip())
    except (TypeError, ValueError):
        RECAPTCHA_MIN_SCORE = 0.5

    # Comma-separated IPs that bypass all in-process rate limiting.
    # Useful for CI pipelines and dedicated load-test runner IPs so they never
    # see 429 responses regardless of request volume.
    # Example: RATE_LIMIT_EXEMPT_IPS=10.0.0.5,10.0.0.6
    _exempt_ips_raw = (os.environ.get("RATE_LIMIT_EXEMPT_IPS") or "").strip()
    RATE_LIMIT_EXEMPT_IPS: list[str] = [ip.strip() for ip in _exempt_ips_raw.split(",") if ip.strip()]

    # PostgreSQL is required. No SQLite fallback.
    # Read DATABASE_URL from environment - this is critical for Fly.io deployments
    _database_url = os.environ.get("DATABASE_URL")
    if not _database_url:
        _config_logger.error("ERROR: DATABASE_URL environment variable is not set!")
        _config_logger.error("Available environment variables:")
        for key in sorted(os.environ.keys()):
            if 'DATABASE' in key.upper() or 'DB' in key.upper():
                _config_logger.error("  %s=%s", key, os.environ.get(key))
        raise RuntimeError(
            "DATABASE_URL environment variable is required but not set. "
            "Please set DATABASE_URL in your environment or Fly.io secrets."
        )
    # Log the database URL (with password masked) for debugging
    _masked_url = _database_url
    if '@' in _masked_url:
        # Mask password in URL: postgresql://user:password@host -> postgresql://user:***@host
        parts = _masked_url.split('@')
        if '://' in parts[0]:
            scheme_user_pass = parts[0].split('://')
            if len(scheme_user_pass) == 2 and ':' in scheme_user_pass[1]:
                user_pass = scheme_user_pass[1].split(':')
                if len(user_pass) == 2:
                    _masked_url = f"{scheme_user_pass[0]}://{user_pass[0]}:***@{parts[1]}"
    # Use INFO level for startup messages (Azure App Service may capture these)
    _config_logger.info("Using DATABASE_URL: %s", _masked_url)
    SQLALCHEMY_DATABASE_URI = _normalize_database_uri(_database_url)
    if not SQLALCHEMY_DATABASE_URI:
        raise RuntimeError(f"Invalid DATABASE_URL format: {_database_url}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Enhanced Security Configuration
    # Force HTTPS in production/staging
    PREFERRED_URL_SCHEME = 'https' if (os.environ.get('FLASK_CONFIG') or '').lower() in {'production', 'staging'} else 'http'


    # Security Headers Configuration (env: true/false only)
    SECURITY_HEADERS_ENABLED = _parse_bool(os.environ.get('SECURITY_HEADERS_ENABLED'), default=True)

    # WebSocket Configuration (env: true/false only)
    # AI chat/docs streaming only. Notifications are HTTP polling — never WS.
    # Default false: long-lived sockets pin gthread workers. Prod Azure is false.
    WEBSOCKET_ENABLED = _parse_bool(os.environ.get('WEBSOCKET_ENABLED'), default=False)
    # Max inbound WebSocket frame size (bytes). Enforced via flask-sock SOCK_SERVER_OPTIONS
    # and an application-level parse guard.
    WS_MAX_MESSAGE_BYTES = int(os.environ.get('WS_MAX_MESSAGE_BYTES', str(256 * 1024)))
    SOCK_SERVER_OPTIONS = {
        'max_message_size': WS_MAX_MESSAGE_BYTES,
    }

    # Content Security Policy Configuration
    CSP_REPORT_URI = os.environ.get('CSP_REPORT_URI')  # Optional CSP reporting endpoint
    # NOTE:
    # Static asset cache-busting is handled internally by the app at runtime.
    # We intentionally do not expose an env/config knob for it.

    # More robust connection handling (esp. for Postgres)
    # IMPORTANT — multi-worker arithmetic: total max DB connections =
    #   GUNICORN_WORKERS × (SQLALCHEMY_POOL_SIZE + SQLALCHEMY_MAX_OVERFLOW)
    # Keep this well below PostgreSQL's max_connections.
    # Azure PostgreSQL Flexible Server max_connections varies by tier
    # (e.g. 50 for B1ms, 100 for B2s, 200 for GP-2vCore).
    # Default here: 3 workers × (5 + 20) = 75 connections — safe for most tiers.
    # max_overflow default raised 10 -> 20 (2026-07-22, platform-502-db-pool-alert-storm
    # incident): matches azure-deploy.ps1's original provisioning intent
    # (POOL_SIZE=10/MAX_OVERFLOW=20) and gives more per-worker burst headroom before a
    # single worker's pool saturates. Overflow connections are opened on demand and
    # closed when idle, so raising the ceiling costs nothing at rest.
    # Override via env vars to tune per environment.
    # pool_timeout < GUNICORN_TIMEOUT (25 s) so waiting for a slot fails fast.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        # recycle connections periodically to avoid stale connections on some providers
        "pool_recycle": int(os.environ.get("SQLALCHEMY_POOL_RECYCLE", "300")),
        "pool_size": int(os.environ.get("SQLALCHEMY_POOL_SIZE", "5")),
        "max_overflow": int(os.environ.get("SQLALCHEMY_MAX_OVERFLOW", "20")),
        # Stop waiting for a pool slot well before Gunicorn's 25 s kill timeout.
        "pool_timeout": int(os.environ.get("SQLALCHEMY_POOL_TIMEOUT", "15")),
        "echo": False,
    }
    # List of supported language codes (order matters: first is fallback)
    # Note: Runtime settings are stored in the database (system_settings table).
    # These are defaults used during app initialization.
    DEFAULT_LANGUAGES = ["en", "fr", "es", "ar", "ru", "zh"]
    LANGUAGES = _load_supported_languages_from_settings(DEFAULT_LANGUAGES)

    # Display names for UI usage (keyed by ISO code)
    LANGUAGE_DISPLAY_NAMES = {
        'en': 'English',
        'fr': 'French',
        'es': 'Spanish',
        'ar': 'Arabic',
        'ru': 'Russian',
        'zh': 'Chinese',
        'hi': 'Hindi',
    }

    # Mapping from locale code to translation service language key names
    # e.g., used by auto-translation APIs that expect names like 'french', 'spanish'
    LOCALE_TO_TRANSLATION_KEY = {
        'en': 'english',
        'fr': 'french',
        'es': 'spanish',
        'ar': 'arabic',
        'ru': 'russian',
        'zh': 'chinese',
        'hi': 'hindi',
    }

    # Mapping from locale code to model multilingual attribute suffix, where applicable
    # English is represented by None to indicate default/base fields
    LANGUAGE_MODEL_KEY = {
        'en': None,
        'fr': 'french',
        'es': 'spanish',
        'ar': 'arabic',
        'ru': 'russian',
        'zh': 'chinese',
        'hi': 'hindi',
    }

    # Convenience list of non-English languages for translation targets
    TRANSLATABLE_LANGUAGES = [code for code in LANGUAGES if code != 'en']

    # Optional: mapping of language codes to flag-icon CSS codes for UI
    LANGUAGE_FLAG_ICONS = {
        'en': 'gb',
        'fr': 'fr',
        'es': 'es',
        'ar': 'sa',
        'ru': 'ru',
        'zh': 'cn',
        'hi': 'in',
    }

    # Comprehensive list of all languages (ISO 639-1 codes with display names)
    # Used for document language selection and other places where all languages should be available
    ALL_LANGUAGES_DISPLAY_NAMES = {
        'aa': 'Afar',
        'ab': 'Abkhazian',
        'ae': 'Avestan',
        'af': 'Afrikaans',
        'ak': 'Akan',
        'am': 'Amharic',
        'an': 'Aragonese',
        'ar': 'Arabic',
        'as': 'Assamese',
        'av': 'Avaric',
        'ay': 'Aymara',
        'az': 'Azerbaijani',
        'ba': 'Bashkir',
        'be': 'Belarusian',
        'bg': 'Bulgarian',
        'bh': 'Bihari',
        'bi': 'Bislama',
        'bm': 'Bambara',
        'bn': 'Bengali',
        'bo': 'Tibetan',
        'br': 'Breton',
        'bs': 'Bosnian',
        'ca': 'Catalan',
        'ce': 'Chechen',
        'ch': 'Chamorro',
        'co': 'Corsican',
        'cr': 'Cree',
        'cs': 'Czech',
        'cu': 'Church Slavic',
        'cv': 'Chuvash',
        'cy': 'Welsh',
        'da': 'Danish',
        'de': 'German',
        'dv': 'Divehi',
        'dz': 'Dzongkha',
        'ee': 'Ewe',
        'el': 'Greek',
        'en': 'English',
        'eo': 'Esperanto',
        'es': 'Spanish',
        'et': 'Estonian',
        'eu': 'Basque',
        'fa': 'Persian',
        'ff': 'Fulah',
        'fi': 'Finnish',
        'fj': 'Fijian',
        'fo': 'Faroese',
        'fr': 'French',
        'fy': 'Western Frisian',
        'ga': 'Irish',
        'gd': 'Scottish Gaelic',
        'gl': 'Galician',
        'gn': 'Guarani',
        'gu': 'Gujarati',
        'gv': 'Manx',
        'ha': 'Hausa',
        'he': 'Hebrew',
        'hi': 'Hindi',
        'ho': 'Hiri Motu',
        'hr': 'Croatian',
        'ht': 'Haitian',
        'hu': 'Hungarian',
        'hy': 'Armenian',
        'hz': 'Herero',
        'ia': 'Interlingua',
        'id': 'Indonesian',
        'ie': 'Interlingue',
        'ig': 'Igbo',
        'ii': 'Sichuan Yi',
        'ik': 'Inupiaq',
        'io': 'Ido',
        'is': 'Icelandic',
        'it': 'Italian',
        'iu': 'Inuktitut',
        'ja': 'Japanese',
        'jv': 'Javanese',
        'ka': 'Georgian',
        'kg': 'Kongo',
        'ki': 'Kikuyu',
        'kj': 'Kuanyama',
        'kk': 'Kazakh',
        'kl': 'Kalaallisut',
        'km': 'Central Khmer',
        'kn': 'Kannada',
        'ko': 'Korean',
        'kr': 'Kanuri',
        'ks': 'Kashmiri',
        'ku': 'Kurdish',
        'kv': 'Komi',
        'kw': 'Cornish',
        'ky': 'Kirghiz',
        'la': 'Latin',
        'lb': 'Luxembourgish',
        'lg': 'Ganda',
        'li': 'Limburgan',
        'ln': 'Lingala',
        'lo': 'Lao',
        'lt': 'Lithuanian',
        'lu': 'Luba-Katanga',
        'lv': 'Latvian',
        'mg': 'Malagasy',
        'mh': 'Marshallese',
        'mi': 'Maori',
        'mk': 'Macedonian',
        'ml': 'Malayalam',
        'mn': 'Mongolian',
        'mr': 'Marathi',
        'ms': 'Malay',
        'mt': 'Maltese',
        'my': 'Burmese',
        'na': 'Nauru',
        'nb': 'Norwegian Bokmål',
        'nd': 'North Ndebele',
        'ne': 'Nepali',
        'ng': 'Ndonga',
        'nl': 'Dutch',
        'nn': 'Norwegian Nynorsk',
        'no': 'Norwegian',
        'nr': 'South Ndebele',
        'nv': 'Navajo',
        'ny': 'Chichewa',
        'oc': 'Occitan',
        'oj': 'Ojibwa',
        'om': 'Oromo',
        'or': 'Oriya',
        'os': 'Ossetian',
        'pa': 'Punjabi',
        'pi': 'Pali',
        'pl': 'Polish',
        'ps': 'Pushto',
        'pt': 'Portuguese',
        'qu': 'Quechua',
        'rm': 'Romansh',
        'rn': 'Rundi',
        'ro': 'Romanian',
        'ru': 'Russian',
        'rw': 'Kinyarwanda',
        'sa': 'Sanskrit',
        'sc': 'Sardinian',
        'sd': 'Sindhi',
        'se': 'Northern Sami',
        'sg': 'Sango',
        'si': 'Sinhala',
        'sk': 'Slovak',
        'sl': 'Slovenian',
        'sm': 'Samoan',
        'sn': 'Shona',
        'so': 'Somali',
        'sq': 'Albanian',
        'sr': 'Serbian',
        'ss': 'Swati',
        'st': 'Southern Sotho',
        'su': 'Sundanese',
        'sv': 'Swedish',
        'sw': 'Swahili',
        'ta': 'Tamil',
        'te': 'Telugu',
        'tg': 'Tajik',
        'th': 'Thai',
        'ti': 'Tigrinya',
        'tk': 'Turkmen',
        'tl': 'Tagalog',
        'tn': 'Tswana',
        'to': 'Tonga',
        'tr': 'Turkish',
        'ts': 'Tsonga',
        'tt': 'Tatar',
        'tw': 'Twi',
        'ty': 'Tahitian',
        'ug': 'Uighur',
        'uk': 'Ukrainian',
        'ur': 'Urdu',
        'uz': 'Uzbek',
        've': 'Venda',
        'vi': 'Vietnamese',
        'vo': 'Volapük',
        'wa': 'Walloon',
        'wo': 'Wolof',
        'xh': 'Xhosa',
        'yi': 'Yiddish',
        'yo': 'Yoruba',
        'za': 'Zhuang',
        'zh': 'Chinese',
        'zu': 'Zulu',
    }

    # External GO/document API credentials (used by AI document import endpoints; IFRC_* env names retained)
    # SECURITY: credentials must come from environment or secret store (never hardcoded).
    IFRC_API_USER = os.environ.get("IFRC_API_USER") or os.environ.get("IFRC_API_USERNAME")
    IFRC_API_PASSWORD = os.environ.get("IFRC_API_PASSWORD")
    # Comma-separated host allowlist for external document fetch (SSRF protection).
    # Defaults are intentionally restrictive; expand via env if needed.
    IFRC_DOCUMENT_ALLOWED_HOSTS = [
        h.strip().lower()
        for h in (os.environ.get("IFRC_DOCUMENT_ALLOWED_HOSTS") or "api.ifrc.org,go.ifrc.org,go-api.ifrc.org,ifrc.org,prddsgolocstor01.blob.core.windows.net").split(",")
        if h.strip()
    ]

    # IFRC FDRS Data API (https://data-api.ifrc.org) — codebook, fdrsdata, entities/ns; admin FDRS sync + import_fdrs_form_data.py
    _fdrs_data_api_key_raw = (os.environ.get("FDRS_DATA_API_KEY") or "").strip()
    FDRS_DATA_API_KEY = _fdrs_data_api_key_raw or None
    _fdrs_data_api_base_raw = (os.environ.get("FDRS_DATA_API_BASE") or "").strip().rstrip("/")
    FDRS_DATA_API_BASE = _fdrs_data_api_base_raw or None
    _fdrs_databank_api_key_raw = (os.environ.get("FDRS_DATABANK_API_KEY") or "").strip()
    FDRS_DATABANK_API_KEY = _fdrs_databank_api_key_raw or None

    # Mapbox (Validation Dashboard tracker world map; not shared with Interactive Map plugin UI settings)
    _mapbox_access_token_raw = (os.environ.get("MAPBOX_ACCESS_TOKEN") or "").strip()
    MAPBOX_ACCESS_TOKEN = _mapbox_access_token_raw or None
    MAPBOX_STYLE_ID = (
        (os.environ.get("MAPBOX_STYLE_ID") or "go-ifrc/ckrfe16ru4c8718phmckdfjh0").strip()
        or "go-ifrc/ckrfe16ru4c8718phmckdfjh0"
    )

    # Session / cookie behavior
    # NOTE: Session durations are defined below (PERMANENT_SESSION_LIFETIME + SESSION_INACTIVITY_TIMEOUT).
    SESSION_REFRESH_EACH_REQUEST = True  # Refresh session on each request
    SESSION_COOKIE_SECURE = True  # Use secure cookies in production (overridden in DevelopmentConfig)
    SESSION_COOKIE_HTTPONLY = True  # Prevent XSS attacks
    SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF protection

    # CSRF Configuration
    WTF_CSRF_ENABLED = True
    WTF_CSRF_CHECK_DEFAULT = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour
    WTF_CSRF_SSL_STRICT = True

    # Standard Disaggregation Categories
    DEFAULT_SEX_CATEGORIES = _load_sex_categories_from_settings(["Male", "Female", "Non-binary", "Unknown"])
    DEFAULT_AGE_GROUPS = _load_age_groups_from_settings(["<5", "5-17", "18-49", "50+", "Unknown"])

    # Allowed disaggregation options keys and their display names
    DISAGGREGATION_MODES = {
        "total": "Total Only",
        "sex": "By Sex",
        "age": "By Age",
        "sex_age": "By Sex and Age"
    }

    # Units that support disaggregation (case-sensitive)
    DISAGGREGATION_ALLOWED_UNITS = ["People", "Volunteers", "Staff"]

    # Document Types for upload dropdown (loaded from settings; empty list if missing)
    DOCUMENT_TYPES = _load_document_types_from_settings([])

    # Entity type groups enabled across admin experiences
    DEFAULT_ENABLED_ENTITY_TYPES = ['countries', 'ns_structure', 'secretariat']
    ENABLED_ENTITY_TYPES = _load_enabled_entity_types_from_settings(DEFAULT_ENABLED_ENTITY_TYPES)

    # NEW: Configuration for uploaded documents
    # Prefer environment variable (e.g., Fly sets /data/uploads) and fallback to instance folder
    upload_folder_env = os.environ.get('UPLOAD_FOLDER', '').strip()
    UPLOAD_FOLDER = upload_folder_env if upload_folder_env else os.path.join(basedir, 'instance', 'uploads')
    # Per-country UPR Country Reporting Excel template (T33 export/import)
    UPR_COUNTRY_REPORTING_TEMPLATE_PATH = os.environ.get(
        'UPR_COUNTRY_REPORTING_TEMPLATE_PATH',
        os.environ.get(
            'MYR_REPORTING_TEMPLATE_PATH',
            os.path.join(basedir, 'app', 'static', 'templates', 'unified_country_report.xlsx'),
        ),
    )
    # Deprecated alias — use UPR_COUNTRY_REPORTING_TEMPLATE_PATH
    MYR_REPORTING_TEMPLATE_PATH = UPR_COUNTRY_REPORTING_TEMPLATE_PATH
    # Ensure the upload folder exists (this will be handled in __init__.py)

    # Request size limits
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max request size
    # Explicit upload size limit used by document upload validation
    # Accepts value in MB (e.g., 25 for 25MB) and converts to bytes
    _max_upload_mb = os.environ.get('MAX_UPLOAD_SIZE_BYTES', '25')
    try:
        MAX_UPLOAD_SIZE_BYTES = int(float(_max_upload_mb)) * 1024 * 1024
    except (ValueError, TypeError):
        # Fallback to 25MB if invalid value provided
        MAX_UPLOAD_SIZE_BYTES = 25 * 1024 * 1024

    # DEBUG is automatically determined by environment (development = True, otherwise False)
    # This removes the need to explicitly set DEBUG in environment variables
    DEBUG = _is_development_mode()

    # Verbose browser console (console.log / debug / info / warn / …) on Backoffice pages.
    # Default follows DEBUG. Override with CLIENT_CONSOLE_LOGGING=true|false (explicit env always wins).
    _client_console_env = os.environ.get("CLIENT_CONSOLE_LOGGING")
    if _client_console_env is not None and str(_client_console_env).strip() != "":
        CLIENT_CONSOLE_LOGGING = _parse_bool(_client_console_env, default=False)
    else:
        CLIENT_CONSOLE_LOGGING = DEBUG

    # Session configuration
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=10)
    SESSION_INACTIVITY_TIMEOUT = timedelta(
        minutes=int(os.environ.get('SESSION_INACTIVITY_TIMEOUT_MINUTES', 120))
    )
    # Azure/OAuth: reuse an active session from the same device when duplicate callbacks arrive within this window
    OAUTH_LOGIN_DEDUP_SECONDS = int(os.environ.get('OAUTH_LOGIN_DEDUP_SECONDS', 90))

    # AI Chatbot Configuration
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    AZURE_OPENAI_KEY = os.environ.get('AZURE_OPENAI_KEY')
    AZURE_OPENAI_ENDPOINT = os.environ.get('AZURE_OPENAI_ENDPOINT')
    AZURE_OPENAI_DEPLOYMENT = os.environ.get('AZURE_OPENAI_DEPLOYMENT')
    AZURE_OPENAI_API_VERSION = os.environ.get('AZURE_OPENAI_API_VERSION')
    COPILOT_API_KEY = os.environ.get('COPILOT_API_KEY')
    COPILOT_API_ENDPOINT = os.environ.get('COPILOT_API_ENDPOINT')
    COPILOT_MODEL = os.environ.get('COPILOT_MODEL')
    CHATBOT_ENABLED = _parse_bool(os.environ.get('CHATBOT_ENABLED'), default=True)
    TRANSLATION_REVIEW_ENABLED = _parse_bool(os.environ.get('TRANSLATION_REVIEW_ENABLED'), default=True)
    CHATBOT_MAX_HISTORY = int(os.environ.get('CHATBOT_MAX_HISTORY', '10'))

    # ==================== AI/RAG System Configuration ====================
    # OpenAI Configuration (for embeddings and agent)
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    # Default LLM model (OPENAI_MODEL). Supported models depend on your OpenAI account.
    # Some models (e.g. GPT-5 family) reject sampling params; see app.utils.ai_utils.openai_model_supports_sampling_params.
    OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-5-mini')
    # Optional: override model pricing (JSON). Keys: "chat" (model -> {input, output} per 1M tokens), "embedding" (model -> per 1M tokens). See app.utils.ai_pricing.
    AI_MODEL_PRICING = os.environ.get('AI_MODEL_PRICING')  # JSON string or set in code

    # Embedding Configuration
    # AI_EMBEDDING_DIMENSIONS must match the pgvector column size (e.g. 1536 for text-embedding-3-small).
    # Changing provider/model/dimensions requires a DB migration to alter the vector column and may
    # require re-embedding existing documents.
    AI_EMBEDDING_PROVIDER = os.environ.get('AI_EMBEDDING_PROVIDER', 'openai')  # 'openai' or 'local'
    AI_EMBEDDING_MODEL = os.environ.get('AI_EMBEDDING_MODEL', 'text-embedding-3-small')
    AI_EMBEDDING_DIMENSIONS = int(os.environ.get('AI_EMBEDDING_DIMENSIONS', '1536'))

    # Document Processing
    AI_MAX_DOCUMENT_SIZE_MB = int(os.environ.get('AI_MAX_DOCUMENT_SIZE_MB', '50'))
    # Text-only PDF processing: drop embedded images before extraction to cut memory/size.
    AI_PDF_STRIP_IMAGES_ENABLED = _parse_bool(os.environ.get('AI_PDF_STRIP_IMAGES_ENABLED'), default=True)
    AI_PDF_STRIP_IMAGES_MIN_MB = int(os.environ.get('AI_PDF_STRIP_IMAGES_MIN_MB', '10'))
    AI_CHUNK_SIZE = int(os.environ.get('AI_CHUNK_SIZE', '512'))  # tokens
    AI_CHUNK_OVERLAP = int(os.environ.get('AI_CHUNK_OVERLAP', '50'))  # tokens
    # Table extraction (PDFs): when enabled, we attempt to extract tables into structured table chunks.
    AI_TABLE_EXTRACTION_ENABLED = _parse_bool(os.environ.get('AI_TABLE_EXTRACTION_ENABLED'), default=True)
    # When table extraction is enabled, remove table-area text from the PDF's extracted page text
    # to avoid duplicating messy table text in semantic chunks.
    AI_EXCLUDE_TABLE_TEXT_FROM_PDF_TEXT = _parse_bool(os.environ.get('AI_EXCLUDE_TABLE_TEXT_FROM_PDF_TEXT'), default=True)
    # Optional: attempt to extract approximate cell background colors (slower; raster sampling).
    AI_TABLE_EXTRACT_COLORS_ENABLED = _parse_bool(os.environ.get('AI_TABLE_EXTRACT_COLORS_ENABLED'), default=False)
    # When True (default), documents that reach Approved status are queued for AI embedding/indexing automatically.
    AI_AUTO_PROCESS_APPROVED_DOCUMENTS = _parse_bool(
        os.environ.get('AI_AUTO_PROCESS_APPROVED_DOCUMENTS'), default=True
    )
    # Country/scope: keyword pass first; LLM only when keyword confidence is below this threshold.
    AI_DOC_COUNTRY_LLM_ENABLED = _parse_bool(os.environ.get('AI_DOC_COUNTRY_LLM_ENABLED'), default=True)
    try:
        AI_DOC_COUNTRY_LLM_MIN_CONFIDENCE = float(os.environ.get('AI_DOC_COUNTRY_LLM_MIN_CONFIDENCE', '0.7'))
    except ValueError:
        AI_DOC_COUNTRY_LLM_MIN_CONFIDENCE = 0.7
    # Blank => AI_QUERY_REWRITE_MODEL / gpt-4o-mini (cheap classifier, not the main chat model).
    AI_DOC_COUNTRY_LLM_MODEL = (os.environ.get('AI_DOC_COUNTRY_LLM_MODEL') or '').strip() or None

    # Vector Search
    AI_TOP_K_RESULTS = int(os.environ.get('AI_TOP_K_RESULTS', '5'))
    AI_RERANK_ENABLED = _parse_bool(os.environ.get('AI_RERANK_ENABLED'), default=False)
    # Rerank provider: 'cohere' (requires COHERE_API_KEY) or 'local' (cross-encoder). Not used if AI_RERANK_ENABLED=false.
    AI_RERANK_PROVIDER = (os.environ.get('AI_RERANK_PROVIDER', 'cohere') or 'cohere').strip().lower()
    # Number of candidates to return after reranking (reranker receives more, returns this many).
    AI_RERANK_TOP_K = int(os.environ.get('AI_RERANK_TOP_K', '20'))
    # Max chunks per document in hybrid results (0 = no cap). Default 2 avoids one long document filling the whole result set (e.g. top 8).
    AI_DOCUMENT_DIVERSITY_MAX_CHUNKS_PER_DOC = int(os.environ.get('AI_DOCUMENT_DIVERSITY_MAX_CHUNKS_PER_DOC', '2'))
    # Minimum chunk token_count before keyword_match_boost or source_boost apply in hybrid scoring.
    # Short headers/contact blocks can hit keyword_score≈1.0 on a single term via ts_rank_cd normalization.
    AI_MIN_TOKENS_FOR_KEYWORD_BOOST = int(os.environ.get('AI_MIN_TOKENS_FOR_KEYWORD_BOOST', '22'))
    # Local cross-encoder model for reranking when AI_RERANK_PROVIDER=local (e.g. cross-encoder/ms-marco-MiniLM-L-6-v2).
    AI_RERANK_LOCAL_MODEL = os.environ.get('AI_RERANK_LOCAL_MODEL', 'cross-encoder/ms-marco-MiniLM-L-6-v2')
    # Cohere reranking (only used when AI_RERANK_PROVIDER=cohere)
    COHERE_API_KEY = os.environ.get('COHERE_API_KEY')
    AI_RERANK_COHERE_MODEL = os.environ.get('AI_RERANK_COHERE_MODEL', 'rerank-v3.5')

    # Multi-modal
    AI_MULTIMODAL_ENABLED = _parse_bool(os.environ.get('AI_MULTIMODAL_ENABLED'), default=True)
    AI_OCR_ENABLED = _parse_bool(os.environ.get('AI_OCR_ENABLED'), default=True)

    # Agent Configuration
    AI_AGENT_ENABLED = _parse_bool(os.environ.get('AI_AGENT_ENABLED'), default=True)
    AI_AGENT_MAX_ITERATIONS = 25
    # Dev-friendly defaults; ProductionConfig overrides for Azure (~230s gateway limit).
    AI_AGENT_TIMEOUT_SECONDS = int(os.environ.get('AI_AGENT_TIMEOUT_SECONDS', '300'))
    # SSE stream: max seconds without completion before yielding stream_idle_timeout
    AI_SSE_IDLE_TIMEOUT_SECONDS = int(os.environ.get('AI_SSE_IDLE_TIMEOUT_SECONDS', '420'))
    AI_AGENT_MAX_TOOLS_PER_QUERY = 50
    # Max number of search_documents/search_documents_hybrid calls per agent run.
    # Lower (e.g. 3) on staging if traces show many broad search_documents calls and narrative fails.
    AI_AGENT_SEARCH_DOCS_MAX_CALLS = int(os.environ.get('AI_AGENT_SEARCH_DOCS_MAX_CALLS', '5'))
    # Max completion tokens per agent LLM turn (ReAct and native). 32768 allows full 192-row all-countries tables with extra columns.
    AI_AGENT_MAX_COMPLETION_TOKENS = int(os.environ.get('AI_AGENT_MAX_COMPLETION_TOKENS', '32768'))
    # Per-query LLM/tool cost ceiling (USD). Default 2.00; set to 0 to disable (not recommended prod).
    _cost_cap = os.environ.get("AI_AGENT_COST_LIMIT_USD", "").strip()
    AI_AGENT_COST_LIMIT_USD = float(_cost_cap) if _cost_cap else 2.0
    try:
        AI_AGENT_TOOL_CB_FAILURE_THRESHOLD = int(os.environ.get("AI_AGENT_TOOL_CB_FAILURE_THRESHOLD", "3"))
    except ValueError:
        AI_AGENT_TOOL_CB_FAILURE_THRESHOLD = 3
    if AI_AGENT_TOOL_CB_FAILURE_THRESHOLD < 1:
        AI_AGENT_TOOL_CB_FAILURE_THRESHOLD = 1
    try:
        AI_AGENT_TOOL_CB_RESET_SECONDS = float(os.environ.get("AI_AGENT_TOOL_CB_RESET_SECONDS", "30"))
    except ValueError:
        AI_AGENT_TOOL_CB_RESET_SECONDS = 30.0
    try:
        AI_AGENT_SYSTEM_PROMPT_CACHE_TTL_SECONDS = float(os.environ.get("AI_AGENT_SYSTEM_PROMPT_CACHE_TTL_SECONDS", "60"))
    except ValueError:
        AI_AGENT_SYSTEM_PROMPT_CACHE_TTL_SECONDS = 60.0
    # Query rewrite: LLM rewrites the user message before passing to the agent (and direct LLM). Improves tool use.
    AI_QUERY_REWRITE_ENABLED = _parse_bool(os.environ.get('AI_QUERY_REWRITE_ENABLED'), default=True)
    # Reject generic/off-topic chat (coding, recipes, unrelated trivia) before the agent; see ai_query_rewriter.is_message_in_platform_scope.
    AI_PLATFORM_SCOPE_ENFORCE_ENABLED = _parse_bool(os.environ.get('AI_PLATFORM_SCOPE_ENFORCE_ENABLED'), default=True)
    # Model for query rewrite. When unset, use a fast model to keep latency low (not the main chat model).
    _qrm = (os.environ.get("AI_QUERY_REWRITE_MODEL") or "").strip()
    AI_QUERY_REWRITE_MODEL = _qrm if _qrm else "gpt-4o-mini"
    # Model for interactive table reference-data enrichment (column pick + batched per-country JSON).
    # Default unset => ai_payload_inference uses gpt-4o-mini (fast). Set to OPENAI_MODEL only if needed.
    AI_TABLE_ENRICHMENT_MODEL = os.environ.get('AI_TABLE_ENRICHMENT_MODEL') or None
    # Response revision: run every final response through an LLM for clarity and consistency (default: False to reduce cost).
    AI_RESPONSE_REVISION_ENABLED = _parse_bool(os.environ.get('AI_RESPONSE_REVISION_ENABLED'), default=False)
    AI_RESPONSE_REVISION_MAX_TOKENS = int(os.environ.get('AI_RESPONSE_REVISION_MAX_TOKENS', '1500'))

    # Function Calling
    AI_FUNCTION_CALLING_PROVIDER = os.environ.get('AI_FUNCTION_CALLING_PROVIDER', 'openai')
    AI_USE_NATIVE_FUNCTION_CALLING = _parse_bool(os.environ.get('AI_USE_NATIVE_FUNCTION_CALLING'), default=True)

    # Optional OpenTelemetry tracing for AI (agent, chat, embeddings). No-op if opentelemetry not installed.
    AI_OPENTELEMETRY_ENABLED = _parse_bool(os.environ.get('AI_OPENTELEMETRY_ENABLED'), default=False)
    OTEL_SERVICE_NAME = os.environ.get('OTEL_SERVICE_NAME', 'hum-databank-backoffice-ai')

    # Tool Configuration
    AI_TOOL_CACHE_ENABLED = _parse_bool(os.environ.get('AI_TOOL_CACHE_ENABLED'), default=True)
    AI_TOOL_CACHE_TTL_SECONDS = int(os.environ.get('AI_TOOL_CACHE_TTL_SECONDS', '300'))
    AI_TOOL_RATE_LIMIT_PER_MIN = 120

    # AI chat quotas (cost control)
    # Keep these static and permissive to reduce operational config complexity.
    AI_CHAT_DAILY_LIMIT_PER_USER = 1_000_000
    AI_CHAT_DAILY_LIMIT_PER_SYSTEM = 5_000_000
    # Document search: max top_k when return_all_countries=True (list-style queries across many countries).
    # Kept at 200 to avoid huge tool observations that can cause "could not generate the final narrative".
    AI_DOCUMENT_SEARCH_MAX_TOP_K_LIST = int(os.environ.get('AI_DOCUMENT_SEARCH_MAX_TOP_K_LIST', '200'))
    # Document search: minimum combined_score floor (vector*0.7 + keyword*0.3 + boosts).
    # Applied only for return_all_countries queries. 0 disables the fixed floor.
    AI_DOCUMENT_SEARCH_MIN_SCORE = float(os.environ.get('AI_DOCUMENT_SEARCH_MIN_SCORE', '0.3'))
    # Adaptive score ratio: effective threshold = max(MIN_SCORE, top_score * RATIO).
    # E.g. if top chunk scores 0.88 and ratio is 0.45, threshold = max(0.3, 0.396) = 0.396.
    AI_DOCUMENT_SEARCH_MIN_SCORE_RATIO = float(os.environ.get('AI_DOCUMENT_SEARCH_MIN_SCORE_RATIO', '0.45'))
    # Document search: sanitize boolean-heavy queries for semantic retrieval.
    # Keeps the original query for keyword search, but uses a simplified query for embeddings/rerank.
    AI_DOCUMENT_SEARCH_SANITIZE_QUERY = _parse_bool(os.environ.get('AI_DOCUMENT_SEARCH_SANITIZE_QUERY'), default=True)
    # Indicator bulk tool: max countries to query in get_indicator_values_for_all_countries (avoids timeouts).
    AI_INDICATOR_MAX_COUNTRIES = int(os.environ.get('AI_INDICATOR_MAX_COUNTRIES', '250'))
    # Indicator resolution: how to map user phrase (e.g. "volunteers") to Indicator Bank.
    # - "vector": semantic search on indicator embeddings (best; requires embeddings populated).
    # - "vector_then_llm": vector top-k then LLM picks one (most powerful; needs AI_INDICATOR_LLM_DISAMBIGUATE).
    # - "keyword": legacy ILIKE + name variants (no embeddings required).
    AI_INDICATOR_RESOLUTION_METHOD = (os.environ.get('AI_INDICATOR_RESOLUTION_METHOD', 'vector') or 'vector').strip().lower()
    if AI_INDICATOR_RESOLUTION_METHOD not in ('vector', 'vector_then_llm', 'keyword'):
        AI_INDICATOR_RESOLUTION_METHOD = 'keyword'
    # When true and method is vector_then_llm, LLM disambiguates among top-k vector results.
    AI_INDICATOR_LLM_DISAMBIGUATE = _parse_bool(os.environ.get('AI_INDICATOR_LLM_DISAMBIGUATE'), default=True)
    # Number of indicator candidates from vector search (then optional LLM pick-one).
    AI_INDICATOR_TOP_K = int(os.environ.get('AI_INDICATOR_TOP_K', '10'))

    # AI Chat Persistence: Retention + Archiving
    # -------------------------------------------------------------------------
    # Conversations are stored for authenticated users. These settings control
    # how long we keep messages in Postgres and whether we archive older threads.
    #
    # Typical setup:
    # - Archive to filesystem after 90 days (delete messages from DB after archive)
    # - Purge conversations entirely after 365 days
    #
    # Providers:
    # - filesystem: write archives under UPLOAD_FOLDER/AI_CHAT_ARCHIVE_DIR
    # - azure_blob: write archives to Azure Blob Storage container
    AI_CHAT_RETENTION_ENABLED = _parse_bool(os.environ.get('AI_CHAT_RETENTION_ENABLED'), default=True)
    AI_CHAT_ARCHIVE_PROVIDER = (os.environ.get('AI_CHAT_ARCHIVE_PROVIDER', 'filesystem') or 'filesystem').strip().lower()
    AI_CHAT_ARCHIVE_AFTER_DAYS = int(os.environ.get('AI_CHAT_ARCHIVE_AFTER_DAYS', '90'))
    AI_CHAT_PURGE_AFTER_DAYS = int(os.environ.get('AI_CHAT_PURGE_AFTER_DAYS', '365'))
    AI_CHAT_ARCHIVE_DIR = (os.environ.get('AI_CHAT_ARCHIVE_DIR', 'ai_chat_archives') or 'ai_chat_archives').strip()
    AI_CHAT_MAINTENANCE_BATCH_SIZE = int(os.environ.get('AI_CHAT_MAINTENANCE_BATCH_SIZE', '200'))

    # HTTP timeouts for outbound AI calls (embedding, LLM). Prevents hung requests.
    AI_HTTP_TIMEOUT_SECONDS = int(os.environ.get('AI_HTTP_TIMEOUT_SECONDS', '120'))
    # Dedicated timeout (seconds) for the small AIQueryPlanner routing LLM call (default: min(HTTP, 45)).
    AI_AGENT_PLANNER_TIMEOUT_SECONDS = int(os.environ.get("AI_AGENT_PLANNER_TIMEOUT_SECONDS", "45") or "45")
    # Max pagination batches when document_list fast-path fetches search_documents batches.
    AI_AGENT_DOCUMENT_LIST_MAX_PAGES = int(os.environ.get("AI_AGENT_DOCUMENT_LIST_MAX_PAGES", "10") or "10")
    # Prior user messages injected into native vs ReAct agent prompts (defaults preserve prior behavior).
    AI_AGENT_HISTORY_MESSAGES = int(os.environ.get("AI_AGENT_HISTORY_MESSAGES", "6") or "6")
    AI_AGENT_HISTORY_MESSAGES_REACT = int(os.environ.get("AI_AGENT_HISTORY_MESSAGES_REACT", "4") or "4")
    # LLM evidence planner: pre-flight source-family routing (not keyword-based).
    AI_AGENT_EVIDENCE_PLAN_ENABLED = _parse_bool(os.environ.get("AI_AGENT_EVIDENCE_PLAN_ENABLED"), default=True)
    try:
        AI_AGENT_EVIDENCE_PLAN_MIN_CONFIDENCE = float(os.environ.get("AI_AGENT_EVIDENCE_PLAN_MIN_CONFIDENCE", "0.7"))
    except (TypeError, ValueError):
        AI_AGENT_EVIDENCE_PLAN_MIN_CONFIDENCE = 0.7
    AI_AGENT_EVIDENCE_PLAN_TIMEOUT_SECONDS = int(os.environ.get("AI_AGENT_EVIDENCE_PLAN_TIMEOUT_SECONDS", "30") or "30")
    AI_AGENT_EVIDENCE_PLAN_MAX_DEFERRALS = int(os.environ.get("AI_AGENT_EVIDENCE_PLAN_MAX_DEFERRALS", "2") or "2")
    AI_AGENT_EVIDENCE_FINISH_ASSESS_ENABLED = _parse_bool(
        os.environ.get("AI_AGENT_EVIDENCE_FINISH_ASSESS_ENABLED"), default=True
    )

    # Agent tool observations: max chars passed to the LLM per tool result (avoids context overflow).
    # Lower AI_TOOL_OBSERVATION_MAX_CHARS_DOCUMENT_SEARCH (e.g. 80000) if "could not generate narrative" after large searches.
    AI_TOOL_OBSERVATION_MAX_CHARS = int(os.environ.get('AI_TOOL_OBSERVATION_MAX_CHARS', '20000'))
    AI_TOOL_OBSERVATION_MAX_CHARS_DOCUMENT_SEARCH = int(os.environ.get('AI_TOOL_OBSERVATION_MAX_CHARS_DOCUMENT_SEARCH', '120000'))
    AI_TOOL_OBSERVATION_DOCUMENT_SEARCH_MAX_CONTENT_PER_CHUNK = int(os.environ.get('AI_TOOL_OBSERVATION_DOCUMENT_SEARCH_MAX_CONTENT_PER_CHUNK', '500'))

    # Max characters allowed in a single chat message (validation in ai_chat_request).
    AI_MAX_MESSAGE_CHARS = int(os.environ.get('AI_MAX_MESSAGE_CHARS', '4000'))

    # Optional Redis URL for cross-worker rate limiting (e.g. AI WebSocket). If unset, in-memory per worker.
    REDIS_URL = os.environ.get('REDIS_URL')  # e.g. redis://localhost:6379/0

    # Export limits (API endpoints)
    AI_CHAT_EXPORT_MAX_MESSAGES = int(os.environ.get('AI_CHAT_EXPORT_MAX_MESSAGES', '5000'))
    AI_CHAT_EXPORT_MAX_BYTES = int(os.environ.get('AI_CHAT_EXPORT_MAX_BYTES', str(10 * 1024 * 1024)))  # 10MB

    # Optional encryption for archives (at-rest).
    # If set, should be a 32-byte urlsafe base64 key (Fernet key).
    # Note: we do not enable encryption by default because it requires a stable key.
    AI_CHAT_ARCHIVE_ENCRYPTION_KEY = os.environ.get('AI_CHAT_ARCHIVE_ENCRYPTION_KEY', '')  # optional

    # Azure Blob settings for AI chat archiving (only used when provider=azure_blob)
    AI_CHAT_ARCHIVE_AZURE_CONNECTION_STRING = os.environ.get('AI_CHAT_ARCHIVE_AZURE_CONNECTION_STRING', '')
    AI_CHAT_ARCHIVE_AZURE_CONTAINER = os.environ.get('AI_CHAT_ARCHIVE_AZURE_CONTAINER', 'ai-chat-archives')

    # Azure Blob Storage for file uploads (documents, resources, submissions, logos, etc.)
    # When AZURE_STORAGE_CONNECTION_STRING is set, uploads are stored in Azure Blob Storage
    # instead of the local filesystem. Falls back to local UPLOAD_FOLDER when not set.
    AZURE_STORAGE_CONNECTION_STRING = os.environ.get('AZURE_STORAGE_CONNECTION_STRING', '')
    AZURE_STORAGE_CONTAINER = os.environ.get('AZURE_STORAGE_CONTAINER', 'uploads')
    # When set, static_url() serves JS/CSS/images from this CDN/blob origin instead of Gunicorn.
    # Sector logos are mirrored into this container under system/sectors/ when
    # UPLOAD_STORAGE_PROVIDER=azure_blob.
    STATIC_CDN_URL = (os.environ.get('STATIC_CDN_URL') or '').strip().rstrip('/')
    STATIC_BLOB_CONTAINER = (os.environ.get('STATIC_BLOB_CONTAINER') or '').strip()
    _upload_provider_raw = (os.environ.get('UPLOAD_STORAGE_PROVIDER', '') or '').strip().lower()
    UPLOAD_STORAGE_PROVIDER = (
        _upload_provider_raw if _upload_provider_raw in ('filesystem', 'azure_blob')
        else ('azure_blob' if os.environ.get('AZURE_STORAGE_CONNECTION_STRING', '').strip() else 'filesystem')
    )
    # Optional: Azure Files credentials (e.g. SMB mount or separate ops). Branding file pickers on the
    # settings page use Azure Blob when ``UPLOAD_STORAGE_PROVIDER=azure_blob``; this is unrelated to that flow.
    AZURE_FILE_SHARE_CONNECTION_STRING = os.environ.get('AZURE_FILE_SHARE_CONNECTION_STRING', '').strip()

    # AI DLP (Data Loss Prevention) Guard
    # -------------------------------------------------------------------------
    # Best-effort protection against accidental sharing of obvious sensitive data
    # (emails, phone numbers, tokens, secrets, private keys, etc.) with external LLMs.
    #
    # Modes:
    # - warn: allow but do not require confirmation
    # - confirm: require allow_sensitive=true unless no_external_llm=true (private/local-only mode)
    # - block: always block when detected (configurable to also block local-only)
    # NOTE: Hard-coded defaults by design (no environment variables).
    # If you need to change behavior, edit these constants in code.
    AI_DLP_ENABLED = True
    AI_DLP_MODE = "confirm"  # "warn" | "confirm" | "block"
    AI_DLP_MAX_SCAN_CHARS = 12000

    # Azure AD B2C Federation Login (OIDC)
    AZURE_B2C_TENANT = os.environ.get('AZURE_B2C_TENANT')
    AZURE_B2C_POLICY = os.environ.get('AZURE_B2C_POLICY')
    AZURE_B2C_CLIENT_ID = os.environ.get('AZURE_B2C_CLIENT_ID')
    AZURE_B2C_CLIENT_SECRET = os.environ.get('AZURE_B2C_CLIENT_SECRET')
    AZURE_B2C_REDIRECT_URI = os.environ.get('AZURE_B2C_REDIRECT_URI')
    # URI to send users to after B2C logs them out (post_logout_redirect_uri).
    # Must be registered in the B2C app registration (Authentication → Redirect URIs).
    # Defaults to /login if not set, but that URI still needs to be registered in B2C.
    AZURE_B2C_POST_LOGOUT_REDIRECT_URI = os.environ.get('AZURE_B2C_POST_LOGOUT_REDIRECT_URI')
    AZURE_B2C_SCOPE = os.environ.get('AZURE_B2C_SCOPE', 'openid email profile')

    # Temporary site lock: show a coming-soon page for all routes except health/static.
    # Set COMING_SOON_BYPASS_SECRET so the team can visit /?coming_soon_bypass=<secret>.
    COMING_SOON_LOCK = _parse_bool(os.environ.get('COMING_SOON_LOCK'), default=False)
    COMING_SOON_BYPASS_SECRET = (os.environ.get('COMING_SOON_BYPASS_SECRET') or '').strip()

    # Maintenance site lock (takes precedence over COMING_SOON_LOCK when both are set).
    MAINTENANCE_LOCK = _parse_bool(os.environ.get('MAINTENANCE_LOCK'), default=False)
    MAINTENANCE_BYPASS_SECRET = (os.environ.get('MAINTENANCE_BYPASS_SECRET') or '').strip()

    # Verbose app/form debug: DEBUG log level, debug_utils helpers, guarded admin debug logs.
    # Env: true/false only (see _parse_bool). Default false; avoid true in production unless troubleshooting.
    # Warn in deploy preflight when estimated FK remapping rows exceed this count.
    DEPLOY_MIGRATION_PREFLIGHT_ROW_THRESHOLD = int(
        os.environ.get("DEPLOY_MIGRATION_PREFLIGHT_ROW_THRESHOLD", "500000")
    )

    VERBOSE_FORM_DEBUG = _parse_bool(os.environ.get("VERBOSE_FORM_DEBUG"), default=False)

    # Log full filtered form POST bodies at DEBUG (very noisy for large templates).
    # Default false; use only when debugging field submission issues.
    VERBOSE_FORM_DATA_LOGGING = _parse_bool(
        os.environ.get("VERBOSE_FORM_DATA_LOGGING"), default=False
    )

    # Terminal/stdout logging controls.
    #
    # LOG_MODE is the recommended control:
    # - quiet  -> WARNING+
    # - normal -> INFO+
    # - debug  -> DEBUG+
    #
    # LOG_LEVEL is an optional override (DEBUG/INFO/WARNING/ERROR/CRITICAL).
    #
    # Back-compat:
    # - VERBOSE_FORM_DEBUG=true behaves like LOG_MODE=debug (but LOG_LEVEL still wins if set).
    LOG_MODE = _parse_log_mode(os.environ.get("LOG_MODE"), default="normal")
    LOG_LEVEL = _parse_log_level(os.environ.get("LOG_LEVEL"), default="INFO")

    # If you want API tracking logs in the terminal (not the DB tracking itself),
    # choose the level they emit at. Default DEBUG so normal mode stays quiet.
    API_TRACKER_LOG_LEVEL = _parse_log_level(os.environ.get("API_TRACKER_LOG_LEVEL"), default="DEBUG")

    # When True with LOG_MODE=debug, allow OpenAI/httpx wire-level DEBUG (logs full JSON bodies).
    # Default False so agent/chat runs stay readable in the terminal.
    AI_VERBOSE_OPENAI_HTTP = _parse_bool(os.environ.get("AI_VERBOSE_OPENAI_HTTP"), default=False)

    # Background scheduler jobs are maintenance tasks; tolerate short event-loop/process stalls
    # without logging noisy APScheduler misfire warnings.
    SCHEDULER_MISFIRE_GRACE_SECONDS = int(os.environ.get('SCHEDULER_MISFIRE_GRACE_SECONDS', '30'))

    # How often (minutes) the digest-email job fires.  The digest trigger window is typically
    # 60 minutes, so 5-minute polling is sufficient and reduces load 12× vs 1-minute polling.
    SCHEDULER_DIGEST_EMAIL_INTERVAL_MINUTES = int(
        os.environ.get('SCHEDULER_DIGEST_EMAIL_INTERVAL_MINUTES', '5')
    )

    # FDS access request digest schedule: System Configuration → Emails (DB-backed).

    # Verbose AI SSE logs (delta sampling, persist/engine summary lines). Default false.
    AI_STREAM_DEBUG = _parse_bool(os.environ.get("AI_STREAM_DEBUG"), default=False)

    # Memory Monitoring Configuration
    MEMORY_MONITORING_ENABLED = _parse_bool(os.environ.get('MEMORY_MONITORING_ENABLED'), default=False)

    # System Monitoring Configuration (CPU, Disk, Database, etc.)
    SYSTEM_MONITORING_ENABLED = _parse_bool(os.environ.get('SYSTEM_MONITORING_ENABLED'), default=False)

    # Slow / stuck request logging (stdout; on by default — surfaces in Azure Log Stream)
    SLOW_REQUEST_LOG_ENABLED = _parse_bool(os.environ.get('SLOW_REQUEST_LOG_ENABLED'), default=True)
    SLOW_REQUEST_THRESHOLD_SECONDS = float(os.environ.get('SLOW_REQUEST_THRESHOLD_SECONDS', '10'))
    # In-flight warnings fire BEFORE GUNICORN_TIMEOUT (default 25 s) so [STUCK_REQUEST] appears
    # in the log before the worker is killed and can no longer log anything.
    # Warning at 15 s → log appears ~10 s before Gunicorn kills at 25 s.
    # Critical at 23 s → fires 2 s before the kill, giving one last log entry.
    SLOW_REQUEST_STUCK_WARNING_SECONDS = float(os.environ.get('SLOW_REQUEST_STUCK_WARNING_SECONDS', '15'))
    SLOW_REQUEST_STUCK_CRITICAL_SECONDS = float(os.environ.get('SLOW_REQUEST_STUCK_CRITICAL_SECONDS', '23'))

    # Logging Performance Optimization Configuration
    # tracemalloc has 5-20% CPU overhead - disable by default in staging/production
    # Set TRACEMALLOC_ENABLED=true only when actively debugging memory issues
    TRACEMALLOC_ENABLED = _parse_bool(os.environ.get('TRACEMALLOC_ENABLED'), default=False)

    # Log file rotation settings (prevents unbounded log growth and improves performance)
    # Memory log settings
    MEMORY_LOG_MAX_BYTES = int(os.environ.get('MEMORY_LOG_MAX_BYTES', str(10 * 1024 * 1024)))  # 10MB default
    MEMORY_LOG_BACKUP_COUNT = int(os.environ.get('MEMORY_LOG_BACKUP_COUNT', '5'))  # Keep 5 backups

    # System log settings
    SYSTEM_LOG_MAX_BYTES = int(os.environ.get('SYSTEM_LOG_MAX_BYTES', str(10 * 1024 * 1024)))  # 10MB default
    SYSTEM_LOG_BACKUP_COUNT = int(os.environ.get('SYSTEM_LOG_BACKUP_COUNT', '5'))  # Keep 5 backups

    # Application log settings (larger since it's the main log)
    APPLICATION_LOG_MAX_BYTES = int(os.environ.get('APPLICATION_LOG_MAX_BYTES', str(50 * 1024 * 1024)))  # 50MB default
    APPLICATION_LOG_BACKUP_COUNT = int(os.environ.get('APPLICATION_LOG_BACKUP_COUNT', '5'))  # Keep 5 backups

    # Email Configuration (Email API only)
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@example.com')
    # Dedicated no-reply sender for system notifications/password resets
    MAIL_NOREPLY_SENDER = os.environ.get('MAIL_NOREPLY_SENDER', os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@example.com'))

    # Public Indicator Bank detail page base URL (no trailing slash). Used for admin grid links to external bank.
    INDICATOR_BANK_PUBLIC_BASE = (os.environ.get('INDICATOR_BANK_PUBLIC_BASE') or '').strip()

    # Email API - select API key and URL based on environment
    if _flask_config == 'production':
        EMAIL_API_KEY = os.environ.get('EMAIL_API_KEY_PROD') or os.environ.get('EMAIL_API_KEY', '')
        EMAIL_API_URL = os.environ.get('EMAIL_API_URL_PROD', '')
    elif _flask_config == 'staging':
        EMAIL_API_KEY = os.environ.get('EMAIL_API_KEY_STG') or os.environ.get('EMAIL_API_KEY', '')
        EMAIL_API_URL = os.environ.get('EMAIL_API_URL_STG', '')
    else:
        # Default to staging for development
        EMAIL_API_KEY = os.environ.get('EMAIL_API_KEY_STG') or os.environ.get('EMAIL_API_KEY', '')
        EMAIL_API_URL = os.environ.get('EMAIL_API_URL_STG', '')

    # Admin email addresses for notifications
    admin_emails_str = os.environ.get('ADMIN_EMAILS', '')
    ADMIN_EMAILS = [email.strip() for email in admin_emails_str.split(',') if email.strip()] if admin_emails_str else []

    # Team email for BCC (defaults to sender email)
    TEAM_EMAIL = os.environ.get('TEAM_EMAIL', '')

    # Comma-separated allowlist (lowercased in code). When non-empty, ``send_email`` only
    # delivers to these addresses. Used in local dev and staging; **ignored when FLASK_CONFIG=production.**
    allowed_recipients_str = os.environ.get('ALLOWED_EMAIL_RECIPIENTS_DEV', '')
    ALLOWED_EMAIL_RECIPIENTS_DEV = [email.strip().lower() for email in allowed_recipients_str.split(',') if email.strip()] if allowed_recipients_str else []

    # Base URL for admin links in emails
    BASE_URL = os.environ.get('BASE_URL', 'http://localhost:5000')

    # External Humanitarian Databank MCP server (streamable-http). When set, GET/POST /mcp
    # on this app is reverse-proxied to that host (path preserved). Example:
    # https://ifrc-databank-mcp-staging.azurewebsites.net
    MCP_UPSTREAM_URL = (os.environ.get('MCP_UPSTREAM_URL') or '').strip().rstrip('/')

    # Shareable short link target for the IFRC Network Databank Custom GPT (GET /gpt, /assistant).
    CUSTOM_GPT_URL = (
        os.environ.get('CUSTOM_GPT_URL')
        or 'https://chatgpt.com/g/g-6a7217c375ac81919b0913bdd4ef15b6-ifrc-network-databank'
    ).strip()

    # Notification TTL configuration (days to keep notifications before expiration)
    # Default is 90 days if not specified for a notification type
    NOTIFICATION_TTL_DAYS = {
        'deadline_reminder': 30,
        'assignment_created': 90,
        'assignment_submitted': 90,
        'assignment_approved': 90,
        'assignment_reopened': 90,
        'public_submission_received': 60,
        'form_updated': 60,
        'document_uploaded': 60,
        'user_added_to_country': 90,
        'self_report_created': 90,
    }

    # Notification deduplication window (minutes)
    # Prevents duplicate notifications within this time window
    NOTIFICATION_DEDUP_WINDOW_MINUTES = int(os.environ.get('NOTIFICATION_DEDUP_WINDOW_MINUTES', '5'))
    NOTIFICATION_DEDUP_WINDOW_MINUTES_ADMIN = int(os.environ.get('NOTIFICATION_DEDUP_WINDOW_MINUTES_ADMIN', '1'))

    # Notification grouping window (minutes)
    # Groups notifications of the same type within this time window
    NOTIFICATION_GROUPING_WINDOW_MINUTES = int(os.environ.get('NOTIFICATION_GROUPING_WINDOW_MINUTES', '60'))

    # Notification expiration and cleanup configuration
    NOTIFICATION_EXPIRATION_DAYS = int(os.environ.get('NOTIFICATION_EXPIRATION_DAYS', '90'))
    NOTIFICATION_CLEANUP_RETENTION_DAYS = int(os.environ.get('NOTIFICATION_CLEANUP_RETENTION_DAYS', '90'))
    # Email delivery log retention (digest + instant sends); defaults to cleanup retention.
    NOTIFICATION_EMAIL_LOG_RETENTION_DAYS = int(
        os.environ.get(
            'NOTIFICATION_EMAIL_LOG_RETENTION_DAYS',
            os.environ.get('NOTIFICATION_CLEANUP_RETENTION_DAYS', '90'),
        )
    )

    # Notification rate limiting
    MAX_NOTIFICATIONS_PER_USER_PER_HOUR = int(os.environ.get('MAX_NOTIFICATIONS_PER_USER_PER_HOUR', '100'))
    MAX_NOTIFICATIONS_GLOBAL_PER_HOUR = int(os.environ.get('MAX_NOTIFICATIONS_GLOBAL_PER_HOUR', '10000'))

    # Feature flags for notifications (env: true/false only).
    # Notification delivery is HTTP-only (no WS). AI chat/docs WS use WEBSOCKET_ENABLED.
    FEATURES = {
        'notifications_push_enabled': _parse_bool(os.environ.get('FEATURES_NOTIFICATIONS_PUSH_ENABLED'), default=False),
        'notifications_email_digests_enabled': _parse_bool(os.environ.get('FEATURES_NOTIFICATIONS_EMAIL_DIGESTS_ENABLED'), default=True),
        'notifications_analytics_enabled': _parse_bool(os.environ.get('FEATURES_NOTIFICATIONS_ANALYTICS_ENABLED'), default=True),
        'notifications_webhooks_enabled': _parse_bool(os.environ.get('FEATURES_NOTIFICATIONS_WEBHOOKS_ENABLED'), default=False),
    }

class DevelopmentConfig(Config):
    # DEBUG is inherited from Config base class (automatically True for development)
    LOG_TO_STDOUT = True
    # Terminal logging: INFO+ by default in dev (quiet enough to work with, noisy enough to be useful).
    # Set LOG_MODE=debug in .env for full DEBUG output ([EntryTiming], [EmOps Direct], etc.).
    LOG_MODE = _parse_log_mode(os.environ.get("LOG_MODE"), default="normal")
    LOG_LEVEL = _parse_log_level(os.environ.get("LOG_LEVEL"), default="INFO")
    # Prefer DEV_DATABASE_URL, fallback to DATABASE_URL. No SQLite fallback.
    SQLALCHEMY_DATABASE_URI = _normalize_database_uri(os.environ.get('DEV_DATABASE_URL') or os.environ.get('DATABASE_URL'))

    # Allow HTTP cookies in development (for localhost testing). Env: true/false only.
    SESSION_COOKIE_SECURE = _parse_bool(os.environ.get('SESSION_COOKIE_SECURE'), default=False)

    # Background scheduler is off by default in dev — it fires notification/email jobs
    # that block worker threads and pollute the terminal. Set SCHEDULER_ENABLED=true in
    # .env to test scheduling behaviour locally.
    SCHEDULER_ENABLED = _parse_bool(os.environ.get('SCHEDULER_ENABLED'), default=False)

    # Disable AI caches locally so prompt/tool changes apply on every request.
    AI_AGENT_SYSTEM_PROMPT_CACHE_TTL_SECONDS = 0
    AI_TOOL_CACHE_ENABLED = False

class ProductionConfig(Config):
    # DEBUG is inherited from Config base class (automatically False for production)
    # DATABASE_URL must be PostgreSQL. No SQLite fallback.
    SQLALCHEMY_DATABASE_URI = _normalize_database_uri(os.environ.get('DATABASE_URL'))

    # Add missing production settings
    upload_folder_env = os.environ.get('UPLOAD_FOLDER', '').strip()
    UPLOAD_FOLDER = upload_folder_env if upload_folder_env else '/data/uploads'
    LOG_TO_STDOUT = True

    # Session configuration for production
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # CSRF Configuration for production
    WTF_CSRF_ENABLED = True
    WTF_CSRF_SSL_STRICT = True

    # Rate limiting: custom deque limiter should not be skipped in production.
    RATE_LIMIT_SKIP_DEBUG = False

    # Connection pool — keep totals below PostgreSQL max_connections.
    # total max = GUNICORN_WORKERS × (SQLALCHEMY_POOL_SIZE + SQLALCHEMY_MAX_OVERFLOW)
    # With 3 workers and defaults below: 3 × (5 + 20) = 75 connections.
    # (Prod currently overrides SQLALCHEMY_POOL_SIZE=10 via App Settings, giving
    # 3 × (10 + 20) = 90 — still well under Azure PostgreSQL Flexible Server's
    # max_connections=250. See docs/handovers/2026-07-22-platform-502-db-pool-alert-storm-incident.md.)
    #
    # max_overflow default raised 10 -> 20 (2026-07-22): matches azure-deploy.ps1's
    # original provisioning intent (POOL_SIZE=10/MAX_OVERFLOW=20) and gives more
    # per-worker burst headroom before a single worker's pool saturates. Overflow
    # connections are opened on demand and closed when idle, so raising the ceiling
    # costs nothing at rest.
    #
    # connect_timeout:   abort TCP handshake that hangs (e.g. private-endpoint warming up).
    # statement_timeout: kill runaway queries before they exhaust the pool and cause 504s.
    #                    Must be < GUNICORN_TIMEOUT (25 s) so the worker releases its DB
    #                    connection before being killed. Default 18 s.
    #                    Overridable via DB_STATEMENT_TIMEOUT_MS (0 = disabled).
    # pool_timeout:      stop waiting for a free pool slot before Gunicorn kills the worker.
    #                    Must be < GUNICORN_TIMEOUT (25 s). Default 15 s.
    _stmt_timeout_ms = int(os.environ.get("DB_STATEMENT_TIMEOUT_MS", "18000"))
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": int(os.environ.get("SQLALCHEMY_POOL_RECYCLE", "300")),
        "pool_size": int(os.environ.get("SQLALCHEMY_POOL_SIZE", "5")),
        "max_overflow": int(os.environ.get("SQLALCHEMY_MAX_OVERFLOW", "20")),
        "pool_timeout": int(os.environ.get("SQLALCHEMY_POOL_TIMEOUT", "15")),
        "connect_args": {
            "connect_timeout": int(os.environ.get("DB_CONNECT_TIMEOUT", "10")),
            **({"options": f"-c statement_timeout={_stmt_timeout_ms}"} if _stmt_timeout_ms > 0 else {}),
        },
    }

    # Azure App Service front-end HTTP timeout is ~230s. Keep in-app limits below that
    # so workers release DB connections before the gateway returns 504.
    AI_AGENT_TIMEOUT_SECONDS = int(os.environ.get('AI_AGENT_TIMEOUT_SECONDS', '100'))
    AI_SSE_IDLE_TIMEOUT_SECONDS = int(os.environ.get('AI_SSE_IDLE_TIMEOUT_SECONDS', '180'))

    # Set logging level to INFO for better visibility
    LOG_LEVEL = "INFO"

class StagingConfig(ProductionConfig):
    """
    Staging should be production-like (DEBUG off, secure cookies on).
    DEBUG is inherited from Config base class (automatically False for staging).
    """

class TestingConfig(Config):
    TESTING = True
    DEBUG = False
    # Use TEST_DATABASE_URL or fallback to DATABASE_URL. No SQLite allowed.
    SQLALCHEMY_DATABASE_URI = _normalize_database_uri(os.environ.get('TEST_DATABASE_URL') or os.environ.get('DATABASE_URL'))
    WTF_CSRF_ENABLED = False
    MEMORY_MONITORING_ENABLED = False
    SYSTEM_MONITORING_ENABLED = False
    SLOW_REQUEST_LOG_ENABLED = False
    # Avoid RotatingFileHandler on instance/logs/application.log during pytest — on Windows
    # the file is often locked by a running dev server, causing PermissionError on rollover.
    APPLICATION_LOG_FILE_ENABLED = False
    # Smaller pool + statement timeout so stuck DDL/locks fail fast instead of hanging.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": int(os.environ.get("SQLALCHEMY_POOL_RECYCLE", "300")),
        "pool_size": 2,
        "max_overflow": 2,
        "pool_timeout": 10,
        "connect_args": {
            "connect_timeout": 10,
            "options": "-c statement_timeout=120000",
        },
    }

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'staging': StagingConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
