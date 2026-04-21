# Backoffice/app/routes/api/countries.py
"""
Country and Period API endpoints.
Part of the /api/v1 blueprint.
"""

from flask import request, current_app
import json
import re
from pathlib import Path

# Import the API blueprint from parent
from app.routes.api import api_bp

# Import models
from app.models import Country, AssignedForm, PublicSubmission
from app.models.organization import NationalSociety
from app.models.assignments import AssignmentEntityStatus
from app.utils.auth import require_api_key, require_api_key_or_session
from app.utils.rate_limiting import api_rate_limit
from app import db
from sqlalchemy.orm import joinedload

# Import utility functions
from app.utils.api_helpers import json_response, api_error


@api_bp.route('/countrymap', methods=['GET'])
@require_api_key_or_session  # SECURITY: Allow session auth for internal admin use
@api_rate_limit()
def get_countries():
    """
    API endpoint to retrieve a list of all countries.
    Authentication: API key in Authorization header (Bearer token) or session.
    Optional query params:
      - locale: two-letter locale code ('en','fr','es','ar','zh','ru','hi') to localize returned labels
    Returns:
        JSON array of countries with localized fields and multilingual maps when available.
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

    # No hardcoded region translations; return regions exactly as stored

    # Optional pagination
    from app.services import CountryService
    page = request.args.get('page', type=int)
    per_page = request.args.get('per_page', type=int)
    if page and per_page:
        countries_query = CountryService.get_all(ordered=True)
        paginated = countries_query.paginate(page=page, per_page=per_page, error_out=False)
        countries = paginated.items
    else:
        countries = CountryService.get_all(ordered=True).all()

    # Serialize country data; pass-through region values from DB
    serialized_countries = []
    for country in countries:
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

        # Build multilingual name maps from JSONB directly (no hardcoded language codes)
        name_translations = country.name_translations if isinstance(getattr(country, "name_translations", None), dict) else {}
        country_multilingual_names = {lc: name_translations.get(lc) for lc in translatable_langs}

        # National Society multilingual map now sourced from NationalSociety model
        try:
            ns = country.primary_national_society
        except Exception as e:
            current_app.logger.debug("primary_national_society for country %s failed: %s", country.id, e)
            ns = None
        ns_translations = {}
        if ns and isinstance(getattr(ns, "name_translations", None), dict):
            ns_translations = ns.name_translations
        ns_multilingual_names = {lc: ns_translations.get(lc) for lc in translatable_langs}

        # Resolve localized country and NS names (ISO codes only)
        locale_code = requested_locale or 'en'
        localized_country_name = country.get_name_translation(locale_code) or country.name
        if ns and getattr(ns, 'name_translations', None):
            localized_ns_name = ns.name_translations.get(locale_code) or ns.name
        else:
            localized_ns_name = ns.name if ns else None

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
            # Keep this dynamic so new languages appear automatically
            'region_multilingual_names': {
                lc: region_multilingual.get(lc)
                for lc in supported_langs
            },
        })

    if page and per_page:
        return json_response({
            'countries': serialized_countries,
            'total_items': paginated.total,
            'total_pages': paginated.pages,
            'current_page': paginated.page,
            'per_page': paginated.per_page
        })
    return json_response(serialized_countries)


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
