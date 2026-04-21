import json
import os
import re
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

try:
    from flask import current_app, has_app_context
    from app.models import SystemSettings
    from app.extensions import db
except Exception as e:  # pragma: no cover - allows usage outside app context
    logging.getLogger(__name__).debug("Flask/app not available, using fallbacks: %s", e)
    current_app = None  # type: ignore
    SystemSettings = None  # type: ignore
    db = None  # type: ignore

    def has_app_context():  # type: ignore
        return False


logger = logging.getLogger(__name__)


def _get_settings_path() -> str:
    """Return the absolute path to the JSON settings file (legacy, for migration only).

    Always use Backoffice/config/app_settings.json unless APP_SETTINGS_PATH is set.
    This function is kept for backward compatibility during migration.
    """
    # Allow override via environment variable
    env_path = os.environ.get("APP_SETTINGS_PATH")
    if env_path and env_path.strip():
        return env_path.strip()

    # Resolve to Backoffice/config relative to this file
    utils_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.abspath(os.path.join(utils_dir, "..", ".."))
    config_dir = os.path.join(backend_dir, "config")

    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, "app_settings.json")


def _read_settings_json_file() -> Dict:
    """Load settings from legacy JSON file (no DB / no app context)."""
    settings_path = _get_settings_path()
    try:
        if not os.path.exists(settings_path):
            return {}
        with open(settings_path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception as e:
        logger.debug("JSON settings read failed: %s", e)
        return {}


def _write_settings_json_file(settings: Dict) -> bool:
    """Persist settings to legacy JSON file (no DB / no app context)."""
    settings_path = _get_settings_path()
    try:
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.debug("JSON settings write failed: %s", e)
        return False


def read_settings() -> Dict:
    """Read settings from database. Returns empty dict if no settings exist.

    This function now reads from the database instead of JSON file.
    For backward compatibility during migration, it falls back to JSON file if DB is not available
    or if there is no Flask application context (e.g. CLI, imports, background threads).
    """
    if SystemSettings is None or db is None:
        return _read_settings_json_file()

    if not has_app_context():
        return _read_settings_json_file()

    try:
        return SystemSettings.get_all_as_dict()
    except Exception as e:
        logger.debug("DB settings read failed, trying JSON fallback: %s", e)
        return _read_settings_json_file()


def write_settings(settings: Dict, user_id: Optional[int] = None) -> bool:
    """Write settings to database. Returns True on success.

    This function now writes to the database instead of JSON file.
    Each key-value pair in the settings dict is stored as a separate row.
    """
    if SystemSettings is None or db is None:
        return _write_settings_json_file(settings)

    if not has_app_context():
        return _write_settings_json_file(settings)

    try:
        # Write each setting to database as a separate row
        for key, value in settings.items():
            SystemSettings.set_value(key, value, description=None, user_id=user_id)
        return True
    except Exception as e:
        # Log error but don't fail silently - allow caller to handle
        if current_app:
            current_app.logger.error(f"Failed to write setting to database: {e}")
        return False


ALLOWED_ENTITY_TYPE_GROUPS = ['countries', 'ns_structure', 'secretariat']

try:
    from flask import has_request_context
except Exception as e:  # pragma: no cover
    logging.getLogger(__name__).debug("flask.has_request_context not available: %s", e)
    def has_request_context():
        return False

try:
    from flask_babel import get_locale
except Exception as e:  # pragma: no cover
    logging.getLogger(__name__).debug("flask_babel.get_locale not available: %s", e)
    def get_locale():
        return None


def _resolve_locale(locale: Optional[str] = None) -> str:
    """Resolve locale preference with sensible fallbacks."""
    if locale:
        return str(locale)
    try:
        if has_request_context():
            loc = get_locale()
            if loc:
                return str(loc)
    except Exception as e:
        # Don't break request handling due to localization lookups, but also don't swallow silently.
        logger.debug("Locale resolution failed; falling back to 'en': %s", e, exc_info=True)
    return 'en'


def _extract_localized_value(value, default: str, locale: str) -> str:
    """Return localized string from dict or fallback to default."""
    if isinstance(value, dict):
        normalized = {str(k).lower(): str(v).strip() for k, v in value.items() if isinstance(v, str) and v.strip()}
        if not normalized:
            return default
        lookup_key = locale.lower()
        if lookup_key in normalized:
            return normalized[lookup_key]
        if '-' in lookup_key:
            base = lookup_key.split('-')[0]
            if base in normalized:
                return normalized[base]
        if 'en' in normalized:
            return normalized['en']
        return next(iter(normalized.values()))
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def get_supported_languages(default: Optional[List[str]] = None) -> List[str]:
    """Return supported languages from settings; fallback to provided default."""
    data = read_settings()
    langs = data.get("languages")
    if isinstance(langs, list) and langs:
        return [str(l).lower() for l in langs]
    return list(default or [])


def set_supported_languages(languages: List[str], user_id: Optional[int] = None) -> bool:
    """Persist supported languages to settings database.

    - Ensures 'en' is included
    - Preserves input order (deduplicated, lowercased)
    """
    if not isinstance(languages, list):
        raise ValueError("languages must be a list")
    # Normalize and de-duplicate while preserving order
    seen: set = set()
    ordered: List[str] = []
    for lang in languages:
        code = str(lang).lower()
        if code not in seen:
            seen.add(code)
            ordered.append(code)

    # Ensure 'en' is included if not already present
    if 'en' not in seen:
        ordered.insert(0, 'en')

    data = read_settings()
    data["languages"] = ordered
    return write_settings(data, user_id=user_id)


def get_show_language_flags(default: bool = True) -> bool:
    """Return whether language flags should be shown in the UI.

    Stored in settings as key: 'show_language_flags' (bool/int/str).
    Defaults to True.
    """
    data = read_settings()
    value = data.get("show_language_flags", default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "true", "yes", "y", "on"}:
            return True
        if v in {"0", "false", "no", "n", "off", ""}:
            return False
    return bool(default)


def set_show_language_flags(enabled: bool, user_id: Optional[int] = None) -> bool:
    """Persist whether language flags should be shown in the UI."""
    data = read_settings()
    data["show_language_flags"] = bool(enabled)
    return write_settings(data, user_id=user_id)


def get_document_types(default: Optional[List[str]] = None) -> List[str]:
    """Return document types from settings; fallback to provided default.

    Ensures returned values are strings stripped of whitespace and preserves order.
    """
    data = read_settings()
    types = data.get("document_types")
    if isinstance(types, list) and types:
        cleaned: List[str] = []
        seen: set = set()
        for t in types:
            s = str(t).strip()
            if s and s not in seen:
                seen.add(s)
                cleaned.append(s)
        if cleaned:
            return cleaned
    return list(default or [])


def get_frontend_url(default: str = None) -> str:
    """Return frontend URL from settings; fallback to provided default."""
    # Check environment variable first
    env_url = os.environ.get("FRONTEND_URL")
    if env_url and env_url.strip():
        return env_url.strip()

    # Fall back to settings database
    data = read_settings()
    url = data.get("frontend_url")
    if isinstance(url, str) and url.strip():
        return url.strip()

    return default


def set_document_types(document_types: List[str], user_id: Optional[int] = None) -> bool:
    """Persist document types to settings database.

    - Trims whitespace, removes empty entries
    - De-duplicates while preserving order
    """
    if not isinstance(document_types, list):
        raise ValueError("document_types must be a list")

    seen: set = set()
    ordered: List[str] = []
    for item in document_types:
        value = str(item).strip()
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)

    data = read_settings()
    data["document_types"] = ordered
    return write_settings(data, user_id=user_id)


def get_age_groups(default: Optional[List[str]] = None) -> List[str]:
    """Return age groups from settings; fallback to provided default.

    Ensures returned values are strings stripped of whitespace and preserves order.
    """
    data = read_settings()
    groups = data.get("age_groups")
    if isinstance(groups, list) and groups:
        cleaned: List[str] = []
        for g in groups:
            s = str(g).strip()
            if s:
                cleaned.append(s)
        if cleaned:
            return cleaned
    return list(default or [])


def set_age_groups(age_groups: List[str], user_id: Optional[int] = None) -> bool:
    """Persist age groups to settings database.

    - Trims whitespace, removes empty entries
    - Preserves order as provided by the UI (which supports reordering)
    """
    if not isinstance(age_groups, list):
        raise ValueError("age_groups must be a list")

    ordered: List[str] = []
    for item in age_groups:
        value = str(item).strip()
        if value:
            ordered.append(value)

    data = read_settings()
    data["age_groups"] = ordered
    return write_settings(data, user_id=user_id)


def get_sex_categories(default: Optional[List[str]] = None) -> List[str]:
    """Return sex categories from settings; fallback to provided default.

    Ensures returned values are strings stripped of whitespace and preserves order.
    """
    data = read_settings()
    cats = data.get("sex_categories")
    if isinstance(cats, list) and cats:
        cleaned: List[str] = []
        for c in cats:
            s = str(c).strip()
            if s:
                cleaned.append(s)
        if cleaned:
            return cleaned
    return list(default or [])


def set_sex_categories(sex_categories: List[str], user_id: Optional[int] = None) -> bool:
    """Persist sex categories to settings database.

    - Trims whitespace, removes empty entries
    - Preserves order as provided by the UI
    """
    if not isinstance(sex_categories, list):
        raise ValueError("sex_categories must be a list")

    ordered: List[str] = []
    for item in sex_categories:
        value = str(item).strip()
        if value:
            ordered.append(value)

    data = read_settings()
    data["sex_categories"] = ordered
    return write_settings(data, user_id=user_id)


# ---------------------------------------------------------------------------
# Translations for list-type settings (document types, age groups, sex cats)
# Storage format:  { "en_value": { "fr": "…", "es": "…" }, … }
# ---------------------------------------------------------------------------

def _translations_key(setting_key: str) -> str:
    """Return the settings-database key that holds translations for a list setting."""
    return f"{setting_key}_translations"


def get_list_translations(setting_key: str) -> dict:
    """Return translations dict for a list-type setting.

    Returns ``{ "English text": { "fr": "…", "es": "…" }, … }``.
    Always returns a plain dict (never None).
    """
    data = read_settings()
    raw = data.get(_translations_key(setting_key))
    if isinstance(raw, dict):
        return raw
    return {}


def set_list_translations(
    setting_key: str,
    translations: dict,
    user_id: Optional[int] = None,
) -> bool:
    """Persist translations for a list-type setting.

    *translations* should be ``{ "English text": { "fr": "…", … }, … }``.
    Empty inner dicts or empty string values are cleaned out.
    """
    if not isinstance(translations, dict):
        translations = {}
    cleaned: dict = {}
    for en_text, lang_map in translations.items():
        en_text = str(en_text).strip()
        if not en_text or not isinstance(lang_map, dict):
            continue
        inner = {
            k: v.strip()
            for k, v in lang_map.items()
            if isinstance(k, str) and isinstance(v, str) and v.strip()
        }
        if inner:
            cleaned[en_text] = inner
    data = read_settings()
    data[_translations_key(setting_key)] = cleaned
    return write_settings(data, user_id=user_id)


def _normalize_entity_group_list(entity_groups: Sequence[str], fallback: Optional[Sequence[str]] = None) -> List[str]:
    """
    Normalize entity group identifiers:
    - lowercases and strips values
    - keeps only allowed keys
    - de-duplicates while preserving order
    """
    if not isinstance(entity_groups, (list, tuple)):
        entity_groups = list(fallback or [])

    normalized: List[str] = []
    seen: set = set()
    for group in entity_groups:
        key = str(group).strip().lower()
        if key and key in ALLOWED_ENTITY_TYPE_GROUPS and key not in seen:
            seen.add(key)
            normalized.append(key)
    return normalized


def get_enabled_entity_types(default: Optional[Sequence[str]] = None) -> List[str]:
    """Return enabled entity type groups (countries, NS structure, secretariat)."""
    data = read_settings()
    groups = data.get("enabled_entity_types")
    normalized = _normalize_entity_group_list(groups or [], fallback=default or ALLOWED_ENTITY_TYPE_GROUPS)
    if normalized:
        return normalized
    return list(default or ALLOWED_ENTITY_TYPE_GROUPS)


def set_enabled_entity_types(entity_groups: Sequence[str], user_id: Optional[int] = None) -> bool:
    """Persist enabled entity type groups."""
    normalized = _normalize_entity_group_list(entity_groups, fallback=ALLOWED_ENTITY_TYPE_GROUPS)
    # Ensure at least one entity type is enabled (fallback to countries if empty)
    if not normalized:
        normalized = ['countries']
    data = read_settings()
    data["enabled_entity_types"] = normalized
    return write_settings(data, user_id=user_id)


# Organization Branding Functions
# ---------------------------------------------------------------------------
# AI Configuration Management
# ---------------------------------------------------------------------------

AI_SETTINGS_KEY = "ai_settings"
AI_BETA_ACCESS_KEY = "ai_beta_access"

AI_SENSITIVE_KEYS = frozenset({
    'OPENAI_API_KEY', 'GEMINI_API_KEY', 'AZURE_OPENAI_KEY',
    'COPILOT_API_KEY', 'COHERE_API_KEY',
    'AI_CHAT_ARCHIVE_ENCRYPTION_KEY', 'AI_CHAT_ARCHIVE_AZURE_CONNECTION_STRING',
    'AZURE_STORAGE_CONNECTION_STRING',
})


def get_ai_settings() -> Dict:
    """Read AI settings overrides from database.

    Returns only DB-stored values, not env/config defaults.
    """
    data = read_settings()
    result = data.get(AI_SETTINGS_KEY)
    if isinstance(result, dict):
        return result
    return {}


def set_ai_settings(settings: Dict, user_id: Optional[int] = None) -> bool:
    """Save AI settings to database.

    Empty/None values are stripped so the key reverts to env/code default.
    Sensitive keys (API keys, secrets) are never stored; they are env-only.
    """
    if not isinstance(settings, dict):
        raise ValueError("settings must be a dictionary")

    cleaned: Dict = {}
    for k, v in settings.items():
        if k in AI_SENSITIVE_KEYS:
            continue
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        cleaned[k] = v

    data = read_settings()
    data[AI_SETTINGS_KEY] = cleaned
    return write_settings(data, user_id=user_id)


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off", ""}:
            return False
    return bool(default)


def _normalize_user_id_list(raw: Any) -> List[int]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        candidates = list(raw)
    elif isinstance(raw, str):
        candidates = [part.strip() for part in raw.split(",")]
    else:
        candidates = [raw]

    out: List[int] = []
    seen: set = set()
    for item in candidates:
        try:
            uid = int(str(item).strip())
        except (ValueError, TypeError):
            continue
        if uid <= 0 or uid in seen:
            continue
        seen.add(uid)
        out.append(uid)
    return out


def get_ai_beta_access_settings(default_enabled: bool = False) -> Dict[str, Any]:
    """Return AI beta access settings.

    Shape: {"enabled": bool, "allowed_user_ids": [int, ...]}
    """
    data = read_settings()
    raw = data.get(AI_BETA_ACCESS_KEY)
    stored = raw if isinstance(raw, dict) else {}

    enabled = _coerce_bool(stored.get("enabled"), default_enabled)
    allowed_user_ids = _normalize_user_id_list(stored.get("allowed_user_ids"))

    # Optional env overrides for emergency operations.
    env_enabled = (os.environ.get("AI_BETA_ENABLED") or "").strip().lower()
    if env_enabled in {"1", "true", "yes", "y", "on"}:
        enabled = True
    elif env_enabled in {"0", "false", "no", "n", "off"}:
        enabled = False

    env_allowed = (os.environ.get("AI_BETA_ALLOWED_USER_IDS") or "").strip()
    if env_allowed:
        allowed_user_ids = _normalize_user_id_list(env_allowed)

    return {
        "enabled": bool(enabled),
        "allowed_user_ids": allowed_user_ids,
    }


def set_ai_beta_access_settings(
    enabled: bool,
    allowed_user_ids: Any,
    user_id: Optional[int] = None,
) -> bool:
    """Persist AI beta access settings."""
    normalized_ids = _normalize_user_id_list(allowed_user_ids)
    payload = {
        "enabled": bool(enabled),
        "allowed_user_ids": normalized_ids,
    }
    data = read_settings()
    data[AI_BETA_ACCESS_KEY] = payload
    return write_settings(data, user_id=user_id)


def is_ai_beta_restricted(default_enabled: bool = False) -> bool:
    """Return True when AI features are restricted to selected users."""
    return bool(get_ai_beta_access_settings(default_enabled=default_enabled).get("enabled", False))


def get_ai_beta_allowed_user_ids() -> List[int]:
    """Return selected user IDs allowed to access AI beta features."""
    settings = get_ai_beta_access_settings()
    return _normalize_user_id_list(settings.get("allowed_user_ids"))


def user_has_ai_beta_access(user) -> bool:
    """Return whether this user can access AI features.

    Access rules:
    - Beta OFF (toggle disabled): all authenticated users have access — no restriction applied.
    - Beta ON (toggle enabled): only system managers and users explicitly added to the
      allow-list can access AI. Admins must be added to the list to gain access.
    - Unauthenticated users: never have access regardless of toggle state.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False

    # When beta mode is OFF, access is unrestricted — everyone can use AI.
    if not is_ai_beta_restricted():
        return True

    # Beta mode is ON: only system managers and explicitly allowed users have access.
    try:
        from app.services.authorization_service import AuthorizationService

        if AuthorizationService.is_system_manager(user):
            return True
    except Exception as e:
        logger.debug("user_has_ai_beta_access system-manager check failed: %s", e)

    try:
        uid = int(getattr(user, "id", 0) or 0)
    except (ValueError, TypeError):
        uid = 0
    if uid <= 0:
        return False
    return uid in set(get_ai_beta_allowed_user_ids())


def user_is_explicit_beta_tester(user) -> bool:
    """Return True for users who are explicitly in the AI beta allow-list.

    System managers always have access but are NOT considered beta testers for
    UI-display purposes (they don't need the badge). Everyone else — including
    admins — must be in the allow-list when beta mode is ON to see the badge.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False

    # Badge is only shown when beta mode is active.
    if not is_ai_beta_restricted():
        return False

    # System managers bypass the list and don't need the badge.
    try:
        from app.services.authorization_service import AuthorizationService

        if AuthorizationService.is_system_manager(user):
            return False
    except Exception:
        pass

    try:
        uid = int(getattr(user, "id", 0) or 0)
    except (ValueError, TypeError):
        uid = 0
    if uid <= 0:
        return False
    return uid in set(get_ai_beta_allowed_user_ids())


def apply_ai_settings_to_config(app) -> None:
    """Apply DB-stored AI settings to the running Flask app config.

    Call after app initialization when the database is available.
    Non-sensitive keys: DB overrides env. Sensitive keys are never applied from DB
    (env-only); they keep their env/Config values.
    """
    try:
        from config import Config as _Cfg
        ai = get_ai_settings()
        if not ai:
            return
        for key, value in ai.items():
            if key in AI_SENSITIVE_KEYS:
                continue
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            app.config[key] = value
            try:
                setattr(_Cfg, key, value)
            except Exception as e:
                logger.debug("Could not set Config.%s: %s", key, e)
    except Exception as exc:
        logger.warning("Failed to apply AI settings from database: %s", exc)


def get_organization_branding(default: Optional[Dict] = None) -> Dict:
    """Return organization branding settings from database.

    Returns a dictionary with keys:
    - organization_name: Full organization name (string or dict with language keys like {'en': 'Humanitarian Databank', 'fr': 'Banque de Données ONG'})
    - organization_short_name: Short name for UI (string or dict with language keys)
    - organization_domain: Primary domain (e.g., "humdatabank.org") - not localized
    - organization_email_domain: Email domain for user detection (e.g., "humdatabank.org") - not localized
    - organization_logo_path: Path to logo file (e.g., "logo.svg") - not localized
    - organization_favicon_path: Path to favicon file (e.g., "favicon.svg") - not localized
    - organization_copyright_year: Copyright year (e.g., 2024) - not localized
    - indicator_details_url_template: Optional URL template for "View Full Details" links. Use "{id}" placeholder.
    - propose_new_indicator_url: Optional URL for "Propose a new indicator" links.

    Falls back to environment variables or provided default.
    """
    import os
    data = read_settings()
    branding = data.get("organization_branding")

    if isinstance(branding, dict) and branding:
        return branding

    # Fallback to environment variables
    env_branding = {
        "organization_name": os.environ.get("ORGANIZATION_NAME", "").strip(),
        "organization_short_name": os.environ.get("ORGANIZATION_SHORT_NAME", "").strip(),
        "organization_domain": os.environ.get("ORGANIZATION_DOMAIN", "").strip(),
        "organization_email_domain": os.environ.get("ORGANIZATION_EMAIL_DOMAIN", "").strip(),
        "organization_logo_path": os.environ.get("ORGANIZATION_LOGO_PATH", "").strip(),
        "organization_favicon_path": os.environ.get("ORGANIZATION_FAVICON_PATH", "").strip(),
        "organization_copyright_year": os.environ.get("ORGANIZATION_COPYRIGHT_YEAR", "").strip(),
    }

    # Remove empty values
    env_branding = {k: v for k, v in env_branding.items() if v}

    if env_branding:
        return env_branding

    # Final fallback to provided default or system default
    if default:
        return default

    # System default
    return {
        "organization_name": "Humanitarian Databank",
        "organization_short_name": "Humanitarian Databank",
        "organization_domain": "humdatabank.org",
        "organization_email_domain": "humdatabank.org",
        "organization_logo_path": "logo.svg",
        "organization_favicon_path": "favicon.svg",
        "organization_copyright_year": str(datetime.now().year),
    }


def set_organization_branding(branding: Dict, user_id: Optional[int] = None) -> bool:
    """Persist organization branding settings to database.

    Expected keys in branding dict:
    - organization_name (required) - can be string or dict with language keys
    - organization_short_name (optional) - can be string or dict with language keys
    - organization_domain (required) - string only
    - organization_email_domain (optional, defaults to organization_domain) - string only
    - organization_logo_path (optional) - string only
    - organization_favicon_path (optional) - string only
    - organization_copyright_year (optional, defaults to current year) - string only
    - indicator_details_url_template (optional) - string; URL template with "{id}" placeholder
    - propose_new_indicator_url (optional) - string; URL to propose a new indicator

    For localized fields (organization_name, organization_short_name), the dict format is:
    {'en': 'English Name', 'fr': 'French Name', ...}
    """
    if not isinstance(branding, dict):
        raise ValueError("branding must be a dictionary")

    # Validate required fields
    org_name = branding.get("organization_name")
    org_domain = branding.get("organization_domain")

    if not org_name or not org_domain:
        raise ValueError("organization_name and organization_domain are required")

    # Normalize organization_name - can be string or dict
    if isinstance(org_name, dict):
        # Validate dict has at least 'en' key
        if 'en' not in org_name or not org_name['en']:
            raise ValueError("organization_name must have 'en' (English) value when using localized format")
        normalized_name = {k: str(v).strip() for k, v in org_name.items() if v and str(v).strip()}
    else:
        # Convert string to dict format with 'en' as default
        normalized_name = {'en': str(org_name).strip()}

    # Normalize organization_short_name - can be string or dict
    org_short_name = branding.get("organization_short_name")
    if org_short_name:
        if isinstance(org_short_name, dict):
            normalized_short_name = {k: str(v).strip() for k, v in org_short_name.items() if v and str(v).strip()}
        else:
            # If string provided, use it for 'en' and try to derive from organization_name for other languages
            normalized_short_name = {'en': str(org_short_name).strip()}
            if isinstance(normalized_name, dict):
                # Use organization_name for other languages if available
                for lang, name in normalized_name.items():
                    if lang != 'en' and lang not in normalized_short_name:
                        normalized_short_name[lang] = name
    else:
        # Default to organization_name for all languages
        normalized_short_name = normalized_name.copy() if isinstance(normalized_name, dict) else {'en': normalized_name.get('en', '')}

    # Set defaults for optional fields
    normalized = {
        "organization_name": normalized_name,
        "organization_short_name": normalized_short_name,
        "organization_domain": str(org_domain).strip(),
        "organization_email_domain": str(branding.get("organization_email_domain", org_domain)).strip(),
        "organization_logo_path": str(branding.get("organization_logo_path", "")).strip(),
        "organization_favicon_path": str(branding.get("organization_favicon_path", "")).strip(),
        "organization_copyright_year": str(branding.get("organization_copyright_year", str(datetime.now().year))).strip(),
        "indicator_details_url_template": str(branding.get("indicator_details_url_template", "")).strip(),
        "propose_new_indicator_url": str(branding.get("propose_new_indicator_url", "")).strip(),
    }

    # Remove empty optional fields
    if not normalized["organization_logo_path"]:
        normalized.pop("organization_logo_path", None)
    if not normalized.get("organization_favicon_path"):
        normalized.pop("organization_favicon_path", None)
    if not normalized.get("indicator_details_url_template"):
        normalized.pop("indicator_details_url_template", None)
    if not normalized.get("propose_new_indicator_url"):
        normalized.pop("propose_new_indicator_url", None)

    data = read_settings()
    data["organization_branding"] = normalized
    return write_settings(data, user_id=user_id)


def get_organization_name(default: str = "Humanitarian Databank", locale: Optional[str] = None) -> str:
    """Get organization name from settings with localization support."""
    branding = get_organization_branding()
    resolved_locale = _resolve_locale(locale)
    value = branding.get("organization_name")
    return _extract_localized_value(value, default, resolved_locale)


def get_organization_short_name(default: str = "Humanitarian Databank", locale: Optional[str] = None) -> str:
    """Get organization short name from settings with localization support."""
    branding = get_organization_branding()
    resolved_locale = _resolve_locale(locale)
    value = branding.get("organization_short_name")
    return _extract_localized_value(value, default, resolved_locale)


def get_organization_domain(default: str = "humdatabank.org") -> str:
    """Get organization domain from settings."""
    branding = get_organization_branding()
    return branding.get("organization_domain", default)


def get_organization_email_domain(default: str = "humdatabank.org") -> str:
    """Get organization email domain from settings."""
    branding = get_organization_branding()
    return branding.get("organization_email_domain", branding.get("organization_domain", default))


def is_organization_email(email: str) -> bool:
    """Check if email belongs to organization domain."""
    if not email or not isinstance(email, str):
        return False
    email_domain = get_organization_email_domain()
    if not email_domain:
        return False
    email_lower = email.lower().strip()
    domain_lower = email_domain.lower().strip()
    return email_lower.endswith(f"@{domain_lower}")


def get_organization_logo_path(default: str = "logo.svg") -> str:
    """Get organization logo path from settings.

    Missing or blank values use ``default`` (Movement emblem ``logo.svg``, same artwork as
    ``Website/public/ns_logo_placeholder.svg``).
    """
    branding = get_organization_branding()
    raw = branding.get("organization_logo_path")
    if raw is None:
        return default
    path = str(raw).strip()
    return path or default


def get_organization_favicon_path(default: str = "favicon.svg") -> str:
    """Get organization favicon path from settings.

    Missing or blank values use ``default`` (bundled ``favicon.svg``, same emblem as ``logo.svg``).
    """
    branding = get_organization_branding()
    raw = branding.get("organization_favicon_path")
    if raw is None:
        return default
    path = str(raw).strip()
    return path or default


def get_organization_copyright_year(default: Optional[str] = None) -> str:
    """Get organization copyright year from settings."""
    branding = get_organization_branding()
    year = branding.get("organization_copyright_year")
    if year:
        return str(year)
    return default or str(datetime.now().year)


# Chatbot settings
CHATBOT_NAME_KEY = "chatbot_name"


def get_chatbot_org_only() -> bool:
    """Return True when the chatbot should be restricted to org-domain users only.

    Reads from AI settings (CHATBOT_ORG_ONLY key) or falls back to the
    CHATBOT_ORG_ONLY env var. Defaults to False (chatbot is available to all
    authenticated users who have it enabled on their account).
    """
    env_val = os.environ.get("CHATBOT_ORG_ONLY", "").strip().lower()
    if env_val in ("true", "1", "yes"):
        return True
    if env_val in ("false", "0", "no"):
        return False

    ai = get_ai_settings()
    v = ai.get("CHATBOT_ORG_ONLY")
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes")
    return False


def get_chatbot_name(default: str = "") -> str:
    """Get the chatbot display name from settings.

    - Defaults to empty string (generic UI labels are used).
    - Can be overridden by env var CHATBOT_NAME (non-empty).
    """
    env_name = os.environ.get("CHATBOT_NAME")
    if isinstance(env_name, str) and env_name.strip():
        return env_name.strip()

    data = read_settings()
    value = data.get(CHATBOT_NAME_KEY)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def set_chatbot_name(name: str, user_id: Optional[int] = None) -> bool:
    """Persist the chatbot display name to settings database.

    Passing an empty/blank name will store an empty string and the getter will
    fall back to the default.
    """
    if name is None:
        name = ""
    if not isinstance(name, str):
        raise ValueError("chatbot_name must be a string")

    normalized = name.strip()
    # Keep this conservative; it's shown in UI/aria labels.
    if len(normalized) > 80:
        raise ValueError("chatbot_name is too long (max 80 characters)")

    data = read_settings()
    data[CHATBOT_NAME_KEY] = normalized
    return write_settings(data, user_id=user_id)


# ---------------------------------------------------------------------------
# Mobile app minimum version (/api/mobile/v1 X-App-Version enforcement)
# ---------------------------------------------------------------------------

MOBILE_MIN_APP_VERSION_KEY = "mobile_min_app_version"
_MOBILE_MIN_SEMVER_PATTERN = re.compile(r"^\d+(\.\d+)*$")


def get_mobile_min_app_version() -> Optional[str]:
    """Minimum mobile app semver enforced for ``/api/mobile/v1`` (426 below min).

    Precedence: database (admin System Configuration) → ``MOBILE_MIN_APP_VERSION``
    env → :data:`current_app.config['MOBILE_MIN_APP_VERSION']` (tests / legacy).

    Returns ``None`` when unset (no enforcement).
    """
    if SystemSettings is not None and has_app_context():
        try:
            raw = SystemSettings.get_value(MOBILE_MIN_APP_VERSION_KEY)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
        except Exception as e:
            logger.debug("get_mobile_min_app_version DB read failed: %s", e)

    env_v = (os.environ.get("MOBILE_MIN_APP_VERSION") or "").strip()
    if env_v:
        return env_v

    try:
        if has_app_context() and current_app is not None:
            cfg = current_app.config.get("MOBILE_MIN_APP_VERSION")
            if isinstance(cfg, str) and cfg.strip():
                return cfg.strip()
    except Exception:
        pass
    return None


def set_mobile_min_app_version(version: str, *, user_id: Optional[int] = None) -> bool:
    """Persist minimum mobile semver. Empty string removes enforcement (deletes row)."""
    if version is None:
        version = ""
    if not isinstance(version, str):
        raise ValueError("mobile_min_app_version must be a string")

    normalized = version.strip()
    if normalized:
        if len(normalized) > 32:
            raise ValueError("Version is too long (max 32 characters)")
        if not _MOBILE_MIN_SEMVER_PATTERN.match(normalized):
            raise ValueError("Use numeric semver segments only (e.g. 1.2.0)")

    if SystemSettings is None or db is None or not has_app_context():
        data = read_settings()
        if normalized:
            data[MOBILE_MIN_APP_VERSION_KEY] = normalized
        else:
            data.pop(MOBILE_MIN_APP_VERSION_KEY, None)
        return write_settings(data, user_id=user_id)

    try:
        from app.utils.datetime_helpers import utcnow

        existing = SystemSettings.query.filter_by(
            setting_key=MOBILE_MIN_APP_VERSION_KEY
        ).first()
        if not normalized:
            if existing:
                db.session.delete(existing)
                db.session.commit()
            return True
        if existing:
            existing.setting_value = normalized
            existing.description = (
                "Minimum mobile app version for /api/mobile/v1 (X-App-Version)."
            )
            if user_id:
                existing.updated_by_user_id = user_id
            existing.updated_at = utcnow()
        else:
            db.session.add(
                SystemSettings(
                    setting_key=MOBILE_MIN_APP_VERSION_KEY,
                    setting_value=normalized,
                    description=(
                        "Minimum mobile app version for /api/mobile/v1 (X-App-Version)."
                    ),
                    updated_by_user_id=user_id,
                )
            )
        db.session.commit()
        return True
    except Exception as e:
        logger.error("set_mobile_min_app_version failed: %s", e, exc_info=True)
        db.session.rollback()
        return False


# ---------------------------------------------------------------------------
# Notification priorities (per notification type)
# ---------------------------------------------------------------------------

NOTIFICATION_PRIORITIES_KEY = "notification_priorities"
VALID_PRIORITIES = frozenset(("normal", "high", "urgent", "low"))


def get_notification_priorities() -> Dict[str, str]:
    """Return {notification_type: priority} from settings. Empty/missing uses 'normal'."""
    data = read_settings()
    raw = data.get(NOTIFICATION_PRIORITIES_KEY)
    if not isinstance(raw, dict):
        return {}
    result = {}
    for k, v in raw.items():
        if isinstance(k, str) and isinstance(v, str) and v.strip().lower() in VALID_PRIORITIES:
            result[k.strip()] = v.strip().lower()
    return result


def set_notification_priorities(priorities: Dict[str, str], user_id: Optional[int] = None) -> bool:
    """Save notification type -> priority mapping. Keys are NotificationType.value strings."""
    cleaned = {}
    for k, v in (priorities or {}).items():
        if not isinstance(k, str) or not k.strip():
            continue
        p = (v or "normal").strip().lower()
        cleaned[k.strip()] = p if p in VALID_PRIORITIES else "normal"
    data = read_settings()
    data[NOTIFICATION_PRIORITIES_KEY] = cleaned
    return write_settings(data, user_id=user_id)


def get_notification_priority(notification_type: str, default: str = "normal") -> str:
    """Return configured priority for a notification type, or default if not set."""
    if not notification_type:
        return default
    nt_val = getattr(notification_type, "value", str(notification_type))
    priorities = get_notification_priorities()
    return priorities.get(nt_val, default)


# ---------------------------------------------------------------------------
# Auto-approve access requests  (env-var driven, not a DB setting)
# ---------------------------------------------------------------------------

def get_auto_approve_access_requests() -> bool:
    """Return whether country access requests should be auto-approved.

    Controlled exclusively by the ``AUTO_APPROVE_ACCESS_REQUESTS`` environment
    variable.  Any truthy string (``1``, ``true``, ``yes``, ``on``) enables
    auto-approve; everything else (including unset) keeps the default manual
    review workflow.
    """
    value = os.environ.get("AUTO_APPROVE_ACCESS_REQUESTS", "")
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


# Email Template Management Functions
# Each template is used for both: (1) email HTML body, (2) Notifications Center pre-fill.
# Stored under "email_templates" as: key -> { lang: content, label?, notification_title?, notification_message?, priority? }
EMAIL_TEMPLATE_KEYS = [
    'email_template_suggestion_confirmation',
    'email_template_admin_notification',
    'email_template_security_alert',
    'email_template_welcome',
    'email_template_notification',
]

# Metadata keys stored in the same email_templates[key] for Notifications Center pre-fill.
_TEMPLATE_METADATA_KEYS = frozenset(("label", "notification_title", "notification_message", "priority"))


def _is_lang_key(k: str) -> bool:
    """True if k is a language code (e.g. en, fr), not metadata."""
    if not k or not isinstance(k, str):
        return False
    k = k.strip().lower()
    if k in _TEMPLATE_METADATA_KEYS:
        return False
    return len(k) >= 2 and len(k) <= 5 and k.replace("-", "").replace("_", "").isalpha()


def get_notification_templates() -> Dict[str, Dict[str, str]]:
    """Return notification pre-fill data from the same templates used for emails.

    Reads label, notification_title, notification_message, priority from each
    email_templates[key]. Used by the Notifications Center dropdown.

    Returns:
        ``{key: {"label": ..., "title": ..., "message": ..., "priority": ...}}``
    """
    data = read_settings()
    templates = data.get("email_templates", {})
    if not isinstance(templates, dict):
        return {}
    result: Dict[str, Dict[str, str]] = {}
    for key in EMAIL_TEMPLATE_KEYS:
        val = templates.get(key)
        if not isinstance(val, dict):
            result[key] = {"label": "", "title": "", "message": "", "priority": "normal"}
            continue
        result[key] = {
            "label": (val.get("label") or "").strip() or key.replace("_", " ").title(),
            "title": (val.get("notification_title") or "").strip(),
            "message": (val.get("notification_message") or "").strip(),
            "priority": (val.get("priority") or "normal").strip() or "normal",
        }
    return result


def get_template_metadata() -> Dict[str, Dict[str, str]]:
    """Return metadata (label, notification_title, notification_message, priority) per template key."""
    return get_notification_templates()


def get_email_template(template_key: str, default: Optional[str] = None, language: str = "en") -> str:
    """Get email template from database settings.

    Supports both legacy string format and new multilingual dict format.
    When multilingual, falls back to English, then to *default*.

    Args:
        template_key: Template key (e.g., 'email_template_welcome')
        default: Default template if not found in database
        language: ISO language code to retrieve (default 'en')

    Returns:
        Template string (Jinja2 format)
    """
    if template_key not in EMAIL_TEMPLATE_KEYS:
        raise ValueError(f"Invalid email template key: {template_key}")

    data = read_settings()
    templates = data.get("email_templates", {})
    template = templates.get(template_key)

    # New multilingual dict format: {"en": "...", "fr": "..."}
    if isinstance(template, dict):
        content = template.get(language) or template.get("en") or ""
        if content and isinstance(content, str) and content.strip():
            return content
        return default or ""

    # Legacy string format (treated as English)
    if template and isinstance(template, str):
        return template

    return default or ""


def set_email_template(template_key: str, template_content, user_id: Optional[int] = None) -> bool:
    """Save email template to database settings.

    Accepts either a plain string (stored under English) or a dict of
    ``{lang: content}`` pairs.

    Args:
        template_key: Template key (e.g., 'email_template_welcome')
        template_content: Template content string or {lang: content} dict
        user_id: User ID who made the change

    Returns:
        True on success
    """
    if template_key not in EMAIL_TEMPLATE_KEYS:
        raise ValueError(f"Invalid email template key: {template_key}")

    data = read_settings()
    if "email_templates" not in data:
        data["email_templates"] = {}

    if isinstance(template_content, dict):
        cleaned = {
            lang: content.strip()
            for lang, content in template_content.items()
            if isinstance(content, str) and content.strip()
        }
        data["email_templates"][template_key] = cleaned
    elif isinstance(template_content, str):
        trimmed = template_content.strip()
        data["email_templates"][template_key] = {"en": trimmed} if trimmed else {}
    else:
        raise ValueError("template_content must be a string or dict")

    return write_settings(data, user_id=user_id)


def get_all_email_templates() -> Dict[str, Dict[str, str]]:
    """Get all email templates from database (HTML content per language only).

    Returns:
        Dictionary mapping template keys to ``{lang: content}`` dicts.
        Metadata keys (label, notification_*) are excluded.
    """
    data = read_settings()
    templates = data.get("email_templates", {})

    result: Dict[str, Dict[str, str]] = {}
    for key in EMAIL_TEMPLATE_KEYS:
        val = templates.get(key, "")
        if isinstance(val, dict):
            result[key] = {
                lang: content
                for lang, content in val.items()
                if _is_lang_key(lang) and isinstance(content, str) and content.strip()
            }
        elif isinstance(val, str) and val.strip():
            result[key] = {"en": val}
        else:
            result[key] = {}

    return result


def set_all_email_templates(
    templates: Dict,
    metadata: Optional[Dict[str, Dict[str, str]]] = None,
    user_id: Optional[int] = None,
) -> bool:
    """Save all email templates to database.

    Each template is stored with both HTML content (per lang) and optional
    metadata (label, notification_title, notification_message, priority)
    for use in the Notifications Center.

    Args:
        templates: Dictionary mapping template keys to {lang: content} or string
        metadata: Optional {key: {label, notification_title, notification_message, priority}}
        user_id: User ID who made the change

    Returns:
        True on success
    """
    if not isinstance(templates, dict):
        raise ValueError("templates must be a dictionary")

    for key in templates.keys():
        if key not in EMAIL_TEMPLATE_KEYS:
            raise ValueError(f"Invalid email template key: {key}")

    data = read_settings()
    data["email_templates"] = {}

    for key in EMAIL_TEMPLATE_KEYS:
        val = templates.get(key, {})
        if isinstance(val, str):
            trimmed = val.strip()
            content_part = {"en": trimmed} if trimmed else {}
        elif isinstance(val, dict):
            content_part = {
                lang: content.strip()
                for lang, content in val.items()
                if _is_lang_key(lang) and isinstance(content, str) and content.strip()
            }
        else:
            content_part = {}

        meta = (metadata or {}).get(key) or {}
        meta_part = {}
        for m in _TEMPLATE_METADATA_KEYS:
            v = meta.get(m)
            if isinstance(v, str) and v.strip():
                meta_part[m] = v.strip()

        data["email_templates"][key] = {**content_part, **meta_part}

    return write_settings(data, user_id=user_id)
