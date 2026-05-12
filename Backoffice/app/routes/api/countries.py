# Backoffice/app/routes/api/countries.py
"""
Country and Period API endpoints.
Part of the /api/v1 blueprint.
"""

from flask import request, current_app, make_response
import hashlib
import json
import re
import time
import threading
from pathlib import Path

# Import the API blueprint from parent
from app.routes.api import api_bp

# Import models
from app.models import Country, AssignedForm, PublicSubmission
from app.models.organization import NationalSociety
from app.models.assignments import AssignmentEntityStatus
from app.utils.auth import require_api_key, require_api_key_or_session
from app.utils.rate_limiting import rate_limit, api_rate_limit
from app.services.user_analytics_service import get_client_ip
from app import db
from sqlalchemy.orm import joinedload

# Import utility functions
from app.utils.api_helpers import json_response, api_error

# ---------------------------------------------------------------------------
# Module-level caches (survive across requests, reset on worker restart)
# ---------------------------------------------------------------------------

# Region translations — read once from disk, refresh if the file changes.
_region_translations_cache: dict = {}
_region_aliases_cache: dict = {}
_region_file_mtime: float = 0.0
_region_cache_lock = threading.Lock()

# Serialized countrymap response — keyed by locale, expires after TTL seconds.
_COUNTRYMAP_TTL = 300  # 5 minutes
_countrymap_cache: dict[str, tuple[float, str, str]] = {}  # locale -> (expires_at, etag, json_body)
_countrymap_cache_lock = threading.Lock()


def _load_region_translations() -> tuple[dict, dict]:
    """Return (translations, aliases), re-reading the config file only when it changes."""
    global _region_translations_cache, _region_aliases_cache, _region_file_mtime

    cfg_path = Path(current_app.root_path).parent / 'config' / 'region_translations.json'
    try:
        mtime = cfg_path.stat().st_mtime if cfg_path.exists() else 0.0
    except OSError:
        mtime = 0.0

    with _region_cache_lock:
        if mtime != _region_file_mtime:
            translations: dict = {}
            aliases: dict = {}
            try:
                if cfg_path.exists():
                    with open(cfg_path, 'r', encoding='utf-8') as f:
                        cfg_json = json.load(f)
                    if isinstance(cfg_json, dict) and 'aliases' in cfg_json and isinstance(cfg_json['aliases'], dict):
                        aliases = cfg_json['aliases']
                        translations = {k: v for k, v in cfg_json.items() if k != 'aliases'}
                    else:
                        translations = cfg_json
            except Exception as e:
                current_app.logger.warning(f"Could not load region_translations.json: {e}")
            _region_translations_cache = translations
            _region_aliases_cache = aliases
            _region_file_mtime = mtime

        return _region_translations_cache, _region_aliases_cache


def _countrymap_rate_limit_fallback():
    """on_limit callback for the countrymap rate limiter.

    Called only when a client has exceeded its request quota.  Returns the
    most-recently cached response for that locale instead of a hard 429,
    so callers still receive valid data.  Returns None if no cache entry
    exists yet (triggers the normal 429 path).
    """
    from config import Config
    locale = (request.args.get('locale') or '').lower().strip()
    if locale not in set(Config.LANGUAGES + ['']):
        locale = 'en'
    cache_key = locale or 'en'

    with _countrymap_cache_lock:
        cached = _countrymap_cache.get(cache_key)

    if not cached:
        return None  # no data yet — let rate_limit() return 429

    _expires_at, etag, json_body = cached

    if_none_match = request.headers.get('If-None-Match', '').strip().strip('"')
    if if_none_match and if_none_match == etag:
        resp = make_response('', 304)
        resp.headers['ETag'] = f'"{etag}"'
        resp.headers['Cache-Control'] = f'public, max-age={_COUNTRYMAP_TTL}'
        return resp

    resp = make_response(json_body, 200)
    resp.headers['Content-Type'] = 'application/json'
    resp.headers['ETag'] = f'"{etag}"'
    resp.headers['Cache-Control'] = f'public, max-age={_COUNTRYMAP_TTL}'
    resp.headers['Vary'] = 'Accept-Language'
    current_app.logger.info("countrymap: serving stale cache as rate-limit fallback (locale=%s)", cache_key)
    return resp


@api_bp.route('/countrymap', methods=['GET'])
@require_api_key_or_session  # SECURITY: Allow session auth for internal admin use
@rate_limit(
    requests_per_minute=60,
    key_func=lambda: f"countrymap_{get_client_ip()}",
    on_limit=_countrymap_rate_limit_fallback,
)
def get_countries():
    """
    API endpoint to retrieve a list of all countries.
    Authentication: API key in Authorization header (Bearer token) or session.
    Optional query params:
      - locale: two-letter locale code ('en','fr','es','ar','zh','ru','hi') to localize returned labels
    Returns:
        JSON array of countries with localized fields and multilingual maps when available.

    Performance notes:
      - Every successful response is stored in ``_countrymap_cache`` (keyed by locale).
      - When a client exceeds the 60 req/min limit, ``_countrymap_rate_limit_fallback``
        returns the most-recently cached response instead of 429.
      - HTTP ETag + Cache-Control allow clients and reverse proxies to cache the response.
      - national_societies is eagerly loaded to avoid the N+1 query that a plain
        Country.query.all() loop would generate.
    """
    from config import Config

    requested_locale = (request.args.get('locale') or '').lower().strip()
    if requested_locale not in set(Config.LANGUAGES + ['']):
        requested_locale = 'en'

    page = request.args.get('page', type=int)
    per_page = request.args.get('per_page', type=int)
    use_cache = not (page and per_page)

    # ── Build response from DB ───────────────────────────────────────────────
    region_translations, region_aliases = _load_region_translations()

    def _normalize_region_key(value: str) -> str:
        v = (value or '').strip().lower()
        v = v.replace('&', 'and').replace('-', ' ')
        return ' '.join(v.split())

    normalized_key_to_config_key = {_normalize_region_key(k): k for k in region_translations}

    # Eager-load national_societies to eliminate N+1 queries.
    from app.services import CountryService
    if use_cache:
        countries = CountryService.get_all_with_national_societies(ordered=True).all()
    else:
        countries_query = CountryService.get_all_with_national_societies(ordered=True)
        paginated = countries_query.paginate(page=page, per_page=per_page, error_out=False)
        countries = paginated.items

    supported_langs = current_app.config.get("SUPPORTED_LANGUAGES", Config.LANGUAGES) or ["en"]
    translatable_langs = current_app.config.get("TRANSLATABLE_LANGUAGES") or [c for c in supported_langs if c != "en"]
    supported_langs = [
        (c or "").split("_", 1)[0].split("-", 1)[0].strip().lower()
        for c in supported_langs
    ]
    supported_langs = [c for c in supported_langs if c] or ["en"]
    translatable_langs = [
        (c or "").split("_", 1)[0].split("-", 1)[0].strip().lower()
        for c in translatable_langs
    ]
    translatable_langs = [c for c in translatable_langs if c and c != "en"]

    serialized_countries = []
    for country in countries:
        name_translations = country.name_translations if isinstance(getattr(country, "name_translations", None), dict) else {}
        country_multilingual_names = {lc: name_translations.get(lc) for lc in translatable_langs}

        try:
            ns = country.primary_national_society
        except Exception as e:
            current_app.logger.debug("primary_national_society for country %s failed: %s", country.id, e)
            ns = None
        ns_translations = {}
        if ns and isinstance(getattr(ns, "name_translations", None), dict):
            ns_translations = ns.name_translations
        ns_multilingual_names = {lc: ns_translations.get(lc) for lc in translatable_langs}

        locale_code = requested_locale or 'en'
        localized_country_name = country.get_name_translation(locale_code) or country.name
        if ns and getattr(ns, 'name_translations', None):
            localized_ns_name = ns.name_translations.get(locale_code) or ns.name
        else:
            localized_ns_name = ns.name if ns else None

        region_base = country.region if country.region else 'Other'
        configured = region_translations.get(region_base) or region_translations.get(region_base.title())
        if not configured:
            alias_target = region_aliases.get(region_base) or region_aliases.get(region_base.title())
            if alias_target and alias_target in region_translations:
                configured = region_translations.get(alias_target)
        if not configured:
            norm = _normalize_region_key(region_base)
            mapped_key = normalized_key_to_config_key.get(norm)
            if mapped_key:
                configured = region_translations.get(mapped_key)
        if configured and isinstance(configured, dict):
            region_multilingual = configured
            region_localized = configured.get(requested_locale or 'en') or configured.get('en') or region_base
        else:
            region_localized = region_base
            region_multilingual = {lc: region_base for lc in supported_langs}

        serialized_countries.append({
            'id': country.id,
            'name': country.name,
            'localized_name': localized_country_name,
            'multilingual_names': country_multilingual_names,
            'iso3': country.iso3,
            'iso2': country.iso2,
            'national_society_name': (ns.name if ns else None),
            'localized_national_society_name': localized_ns_name,
            'multilingual_national_society_names': ns_multilingual_names,
            'region': region_base,
            'region_localized': region_localized,
            'region_multilingual_names': {
                lc: region_multilingual.get(lc)
                for lc in supported_langs
            },
        })

    if not use_cache:
        return json_response({
            'countries': serialized_countries,
            'total_items': paginated.total,
            'total_pages': paginated.pages,
            'current_page': paginated.page,
            'per_page': paginated.per_page,
        })

    # ── Populate cache and return with HTTP cache headers ────────────────────
    now = time.time()
    json_body = json.dumps(serialized_countries, ensure_ascii=False, separators=(',', ':'))
    etag = hashlib.sha1(json_body.encode('utf-8')).hexdigest()[:16]  # noqa: S324 – not security-sensitive
    cache_key = requested_locale or 'en'

    with _countrymap_cache_lock:
        _countrymap_cache[cache_key] = (now + _COUNTRYMAP_TTL, etag, json_body)

    resp = make_response(json_body, 200)
    resp.headers['Content-Type'] = 'application/json'
    resp.headers['ETag'] = f'"{etag}"'
    resp.headers['Cache-Control'] = f'public, max-age={_COUNTRYMAP_TTL}'
    resp.headers['Vary'] = 'Accept-Language'
    return resp


@api_bp.route('/periods', methods=['GET'])
@require_api_key
@api_rate_limit()
def get_periods():
    """Lightweight endpoint returning distinct period names present in data.
    Accepts optional template_id and country filters to scope results, but by default returns all.
    """
    try:
        template_id = request.args.get('template_id', type=int)
        country_id = request.args.get('country_id', type=int)
        country_iso2 = request.args.get('country_iso2', type=str)
        country_iso3 = request.args.get('country_iso3', type=str)

        # Resolve iso filters to country_id if provided
        if (country_iso2 or country_iso3) and not country_id:
            from app.utils.country_utils import resolve_country_from_iso
            resolved_id, error = resolve_country_from_iso(iso2=country_iso2, iso3=country_iso3)
            if error:
                # Determine status code based on error type
                status_code = 400 if 'Invalid' in error else 404
                return api_error(error, status_code)
            if resolved_id:
                country_id = resolved_id

        periods_set = set()

        # Get periods from assigned forms - use database-level distinct to avoid loading all records
        assigned_query = db.session.query(AssignedForm.period_name).distinct()
        if template_id:
            assigned_query = assigned_query.filter(AssignedForm.template_id == template_id)
        if country_id:
            assigned_query = assigned_query.join(AssignmentEntityStatus).filter(
                AssignmentEntityStatus.entity_id == country_id,
                AssignmentEntityStatus.entity_type == 'country'
            )

        # Get distinct period names directly from database
        for (period_name,) in assigned_query.filter(AssignedForm.period_name.isnot(None)).all():
            if period_name:
                periods_set.add(period_name)

        # Get periods from public submissions - use database-level distinct
        public_query = db.session.query(AssignedForm.period_name).distinct().join(
            PublicSubmission, AssignedForm.id == PublicSubmission.assigned_form_id
        )
        if template_id:
            public_query = public_query.filter(AssignedForm.template_id == template_id)
        if country_id:
            public_query = public_query.filter(PublicSubmission.country_id == country_id)

        # Get distinct period names directly from database
        for (period_name,) in public_query.filter(AssignedForm.period_name.isnot(None)).all():
            if period_name:
                periods_set.add(period_name)

        # Sort periods by extracted year desc, then lexically
        def _extract_year(p):
            try:
                m = re.search(r"\b(20\d{2})\b", p or '')
                return int(m.group(1)) if m else 0
            except Exception as e:
                current_app.logger.debug("_extract_year failed for %r: %s", p, e)
                return 0
        sorted_periods = sorted(periods_set, key=lambda p: (_extract_year(p), str(p)), reverse=True)
        return json_response(sorted_periods)
    except Exception as e:
        current_app.logger.error(f"Error fetching periods: {e}", exc_info=True)
        # Graceful empty result
        return json_response([])


@api_bp.route('/nationalsocietymap', methods=['GET'])
@require_api_key
@api_rate_limit()
def get_national_societies():
    """
    API endpoint to retrieve a list of all national societies.
    Authentication: API key in Authorization header (Bearer token).
    Optional query params:
      - locale: two-letter locale code ('en','fr','es','ar','zh','ru','hi') to localize returned labels
      - country_id: filter by country ID
      - is_active: filter by active status (true/false)
      - page: page number for pagination
      - per_page: items per page for pagination
    Returns:
        JSON array of national societies with localized fields, multilingual maps, and country information.
    """
    # Determine requested locale (centralized in Config)
    from config import Config
    requested_locale = (request.args.get('locale') or '').lower().strip()
    if requested_locale not in set(Config.LANGUAGES + ['']):
        requested_locale = 'en'

    # Load data-driven region translations from config file if present
    region_translations = {}
    region_aliases = {}
    try:
        cfg_path = Path(current_app.root_path).parent / 'config' / 'region_translations.json'
        if cfg_path.exists():
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg_json = json.load(f)
                # Support either flat map or object with aliases
                if isinstance(cfg_json, dict) and 'aliases' in cfg_json and isinstance(cfg_json['aliases'], dict):
                    region_aliases = cfg_json['aliases']
                    region_translations = {k: v for k, v in cfg_json.items() if k != 'aliases'}
                else:
                    region_translations = cfg_json
    except Exception as _e:
        current_app.logger.warning(f"Could not load region_translations.json: {_e}")

    def _normalize_region_key(value: str) -> str:
        v = (value or '').strip().lower()
        v = v.replace('&', 'and')
        v = v.replace('-', ' ')
        v = ' '.join(v.split())
        return v

    # Build normalized key lookup for config keys
    normalized_key_to_config_key = { _normalize_region_key(k): k for k in region_translations.keys() }

    # Build query with eager loading of country relationship
    query = NationalSociety.query.options(joinedload(NationalSociety.country))

    # Apply filters
    country_id = request.args.get('country_id', type=int)
    if country_id:
        query = query.filter(NationalSociety.country_id == country_id)

    is_active_param = request.args.get('is_active', type=str)
    if is_active_param is not None:
        is_active = is_active_param.lower() in ('true', '1', 'yes')
        query = query.filter(NationalSociety.is_active == is_active)

    # Order by country name, then display_order, then NS name
    query = query.join(Country).order_by(Country.name, NationalSociety.display_order, NationalSociety.name)

    # Optional pagination
    page = request.args.get('page', type=int)
    per_page = request.args.get('per_page', type=int)
    if page and per_page:
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        national_societies = paginated.items
    else:
        national_societies = query.all()

    # Serialize national society data
    serialized_ns = []
    for ns in national_societies:
        country = ns.country

        supported_langs = current_app.config.get("SUPPORTED_LANGUAGES", Config.LANGUAGES) or ["en"]
        translatable_langs = current_app.config.get("TRANSLATABLE_LANGUAGES") or [c for c in supported_langs if c != "en"]
        # Normalize codes to base ISO (e.g., fr_FR -> fr)
        supported_langs = [
            (c or "").split("_", 1)[0].split("-", 1)[0].strip().lower()
            for c in supported_langs
        ]
        supported_langs = [c for c in supported_langs if c] or ["en"]
        translatable_langs = [
            (c or "").split("_", 1)[0].split("-", 1)[0].strip().lower()
            for c in translatable_langs
        ]
        translatable_langs = [c for c in translatable_langs if c and c != "en"]

        # Build multilingual name maps for National Society
        ns_name_translations = ns.name_translations if isinstance(getattr(ns, "name_translations", None), dict) else {}
        ns_multilingual_names = {lc: ns_name_translations.get(lc) for lc in translatable_langs}

        # Build multilingual name maps for Country
        country_name_translations = country.name_translations if isinstance(getattr(country, "name_translations", None), dict) else {}
        country_multilingual_names = {lc: country_name_translations.get(lc) for lc in translatable_langs}

        # Resolve localized names (ISO codes only)
        locale_code = requested_locale or 'en'
        localized_ns_name = ns.get_name_translation(locale_code) or ns.name
        localized_country_name = country.get_name_translation(locale_code) or country.name

        # Region values: prefer data-driven translations when available
        region_base = country.region if country.region else 'Other'
        # If a matching key exists in the config, use its map; else pass through
        # Try exact, alias, then normalized match
        configured = region_translations.get(region_base) or region_translations.get(region_base.title())
        if not configured:
            # Alias direct mapping (e.g., "Europe & CA" -> "Europe and Central Asia")
            alias_target = region_aliases.get(region_base) or region_aliases.get(region_base.title())
            if alias_target and alias_target in region_translations:
                configured = region_translations.get(alias_target)
        if not configured:
            # Normalized match against config keys
            norm = _normalize_region_key(region_base)
            mapped_key = normalized_key_to_config_key.get(norm)
            if mapped_key:
                configured = region_translations.get(mapped_key)
        if configured and isinstance(configured, dict):
            region_multilingual = configured
            region_localized = configured.get(requested_locale or 'en') or configured.get('en') or region_base
        else:
            region_localized = region_base
            region_multilingual = {lc: region_base for lc in supported_langs}

        serialized_ns.append({
            'id': ns.id,
            'name': ns.name,
            'localized_name': localized_ns_name,
            'multilingual_names': ns_multilingual_names,
            'code': ns.code,
            'description': ns.description,
            'is_active': ns.is_active,
            'display_order': ns.display_order,
            'part_of': ns.part_of if ns.part_of else [],
            'country_id': country.id,
            'country_name': country.name,
            'country_localized_name': localized_country_name,
            'country_multilingual_names': country_multilingual_names,
            'country_iso3': country.iso3,
            'country_iso2': country.iso2,
            'region': region_base,
            'region_localized': region_localized,
            # Keep this dynamic so new languages appear automatically
            'region_multilingual_names': {
                lc: region_multilingual.get(lc)
                for lc in supported_langs
            },
        })

    if page and per_page:
        return json_response({
            'national_societies': serialized_ns,
            'total_items': paginated.total,
            'total_pages': paginated.pages,
            'current_page': paginated.page,
            'per_page': paginated.per_page
        })
    return json_response(serialized_ns)
