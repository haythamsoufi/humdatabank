# ========== Form Localization Utilities ==========
"""
Unified localization utilities for form elements.
Uses Flask-Babel for proper internationalization.
"""

import logging
from contextlib import suppress

from flask import session

logger = logging.getLogger(__name__)
from flask_babel import gettext as _
from app import get_locale
from typing import Dict, Any, Optional


# Central configuration
from config import Config

# NOTE:
# We do not use legacy per-language DB columns (name_french, etc.) anymore.
# All translations are JSON dicts keyed by ISO language code in *_translations fields.


def get_translation_key(locale: Optional[str] = None) -> str:
    """
    Canonical session/request language code. Use this instead of ad-hoc
    session.get('language') or get_locale() when resolving the current language.

    Returns the ISO language code for the current or specified locale (e.g., 'en', 'fr', 'ar').

    IMPORTANT:
    - We standardize JSON translation dictionaries across the app to use ISO codes only.
    - This function intentionally does NOT return language-name keys; it uses ISO codes only.
    """
    current_locale = locale or (str(get_locale()) if get_locale() else None) or session.get('language') or 'en'
    # Normalize 'en_US' -> 'en'
    if isinstance(current_locale, str) and '_' in current_locale:
        current_locale = current_locale.split('_', 1)[0]
    return (str(current_locale).strip().lower() or 'en')


def get_localized_indicator_type(indicator_type: str) -> str:
    """
    Get the localized indicator type name using Flask-Babel translations.
    Falls back to the original type if no translation is available.

    Args:
        indicator_type: The indicator type string (e.g., 'number', 'percentage')

    Returns:
        str: Localized indicator type name or original type
    """
    if not indicator_type:
        return ''

    with suppress(Exception):
        from flask import has_app_context

        if has_app_context():
            from app.extensions import db
            from app.models import IndicatorBankType

            row = IndicatorBankType.query.filter(
                db.func.lower(IndicatorBankType.code) == str(indicator_type).strip().lower()
            ).first()
            if row and row.is_active:
                loc = get_translation_key()
                lab = row.get_name_translation(loc)
                if lab:
                    return lab

    # Map indicator types to translation keys
    type_translation_map = {
        'number': _('Number'),
        'Number': _('Number'),
        'percentage': _('Percentage'),
        'Percentage': _('Percentage'),
        'text': _('Text'),
        'Text': _('Text'),
        'yesno': _('Yes/No'),
        'YesNo': _('Yes/No'),
        'date': _('Date'),
        'Date': _('Date'),
        'boolean': _('Boolean'),
        'integer': _('Integer')
    }

    # Try exact match first, then lowercase match for backward compatibility
    if indicator_type in type_translation_map:
        return type_translation_map[indicator_type]

    type_key = indicator_type.lower()
    if type_key in type_translation_map:
        return type_translation_map[type_key]
    s = str(indicator_type).strip()
    if not s:
        return ""
    if s.islower() or s.isupper():
        return " ".join(w.capitalize() for w in s.replace("_", " ").split())
    return indicator_type


def get_localized_indicator_unit(indicator_unit: str) -> str:
    """
    Get the localized indicator unit name using Flask-Babel translations.
    Falls back to the original unit if no translation is available.

    Args:
        indicator_unit: The indicator unit string (e.g., 'people', 'volunteers')

    Returns:
        str: Localized indicator unit name or original unit
    """
    if not indicator_unit:
        return ''

    with suppress(Exception):
        from flask import has_app_context

        if has_app_context():
            from app.extensions import db
            from app.models import IndicatorBankUnit

            key = " ".join(str(indicator_unit).strip().lower().split())
            row = IndicatorBankUnit.query.filter(
                db.func.lower(IndicatorBankUnit.code) == key
            ).first()
            if not row:
                row = IndicatorBankUnit.query.filter(
                    db.func.lower(IndicatorBankUnit.name) == key
                ).first()
            if row and row.is_active:
                loc = get_translation_key()
                lab = row.get_name_translation(loc)
                if lab:
                    return lab

    # Map indicator units to translation keys
    unit_translation_map = {
        'people': _('People'),
        'volunteers': _('Volunteers'),
        'staff': _('Staff'),
        'units': _('Units'),
        'percent': _('Percent'),
        'usd': _('USD'),
        'eur': _('EUR'),
        'items': _('Items'),
        'sessions': _('Sessions'),
        'trainings': _('Trainings'),
        'beneficiaries': _('Beneficiaries'),
        'households': _('Households'),
        'communities': _('Communities'),
        'organizations': _('Organizations'),
        'facilities': _('Facilities'),
        'centers': _('Centers'),
        'clinics': _('Clinics'),
        'hospitals': _('Hospitals'),
        'schools': _('Schools'),
        'students': _('Students'),
        'teachers': _('Teachers'),
        'professionals': _('Professionals'),
        'specialists': _('Specialists'),
        'experts': _('Experts'),
        'instructors': _('Instructors'),
        'participants': _('Participants'),
        'recipients': _('Recipients'),
        'victims': _('Victims'),
        'survivors': _('Survivors'),
        'refugees': _('Refugees'),
        'migrants': _('Migrants'),
        'displaced': _('Displaced'),
        'ns': _('National Society'),
    }

    unit_key = indicator_unit.lower()
    unmapped = unit_translation_map.get(unit_key, None)
    if unmapped is not None:
        return unmapped
    s = str(indicator_unit).strip()
    if not s:
        return ""
    if s.islower() or s.isupper():
        return " ".join(w.capitalize() for w in s.replace("-", " ").split())
    return indicator_unit


def get_indicator_bank_type_display(indicator_bank) -> str:
    """Type label for admin grids: catalog name (locale-aware) when FK is set, else localized code string."""
    if indicator_bank is None:
        return ""
    mt = getattr(indicator_bank, "measurement_type", None)
    if mt is not None:
        loc = get_translation_key()
        return (mt.get_name_translation(loc) or mt.name or "").strip()
    return get_localized_indicator_type(getattr(indicator_bank, "type", None) or "")


def get_indicator_bank_unit_display(indicator_bank) -> str:
    """Unit label for admin grids: catalog name (locale-aware) when FK is set, else localized code string."""
    if indicator_bank is None:
        return ""
    mu = getattr(indicator_bank, "measurement_unit", None)
    if mu is not None:
        loc = get_translation_key()
        return (mu.get_name_translation(loc) or mu.name or "").strip()
    return get_localized_indicator_unit(getattr(indicator_bank, "unit", None) or "")


def _get_localized_from_json(translations: Any, default_value: str) -> str:
    """Return translation for current language from a JSON dict, else English, else default."""
    locale_code = get_translation_key()
    if isinstance(translations, dict) and translations:
        val = translations.get(locale_code)
        if val and str(val).strip():
            return str(val).strip()
        val = translations.get("en")
        if val and str(val).strip():
            return str(val).strip()
    return default_value


def get_localized_indicator_name(indicator_bank) -> str:
    """
    Get the localized indicator name based on the current session language.
    Now uses JSONB translations for better performance.
    Falls back to the default name if localized version is not available.

    Args:
        indicator_bank: IndicatorBank instance

    Returns:
        str: Localized indicator name or default name
    """
    if not indicator_bank:
        return _('Unknown Indicator')

    # JSONB translations (no legacy per-language columns)
    translations = getattr(indicator_bank, "name_translations", None)
    localized = _get_localized_from_json(translations, "")
    if localized:
        return localized
    return getattr(indicator_bank, "name", None) or _("Unknown Indicator")


def get_localized_indicator_definition(indicator_bank) -> str:
    """
    Get the localized indicator definition based on the current session language.
    Now uses JSONB translations for better performance.
    Falls back to the default definition if localized version is not available.

    Args:
        indicator_bank: IndicatorBank instance

    Returns:
        str: Localized indicator definition or default definition
    """
    if not indicator_bank:
        return ''

    translations = getattr(indicator_bank, "definition_translations", None)
    localized = _get_localized_from_json(translations, "")
    if localized:
        return localized
    return getattr(indicator_bank, "definition", "") or ""


def get_localized_name_from_translations(
    entity, name_attr: str = 'name', translations_attr: str = 'name_translations'
) -> str:
    """
    Get localized name for an entity from session language.
    Use for any entity with {name_attr} and {translations_attr} (e.g. name_translations).
    Falls back to the entity's default name if no translation is available.
    """
    if not entity:
        return ''
    lang = get_translation_key()
    translations = getattr(entity, translations_attr, None)
    if isinstance(translations, dict):
        val = translations.get(lang)
        if isinstance(val, str) and val.strip():
            return val.strip()
        val = translations.get('en')
        if isinstance(val, str) and val.strip():
            return val.strip()
    return getattr(entity, name_attr, '') or ''


def get_localized_sector_name(sector) -> str:
    """
    Get the localized sector name based on the current session language.
    Falls back to the default name if localized version is not available.
    """
    if not sector:
        return _('Other')

    locale_code = get_translation_key()
    translations = getattr(sector, 'name_translations', None)
    if isinstance(translations, dict) and translations:
        val = translations.get(locale_code)
        if val and str(val).strip():
            return str(val).strip()
        val = translations.get('en')
        if val and str(val).strip():
            return str(val).strip()

    return getattr(sector, "name", None) or _("Other")


def get_localized_subsector_name(subsector) -> str:
    """
    Get the localized subsector name based on the current session language.
    Falls back to the default name if localized version is not available.
    """
    if not subsector:
        return _('Other')

    locale_code = get_translation_key()
    translations = getattr(subsector, 'name_translations', None)
    if isinstance(translations, dict) and translations:
        val = translations.get(locale_code)
        if val and str(val).strip():
            return str(val).strip()
        val = translations.get('en')
        if val and str(val).strip():
            return str(val).strip()

    return getattr(subsector, "name", None) or _("Other")


def get_localized_page_name(page) -> str:
    """
    Get the localized page name based on the current session language.
    Falls back to the default name if localized version is not available.
    """
    if not page:
        return _("Data Entry")

    locale_code = get_translation_key()
    translations = page.name_translations
    if isinstance(translations, str):
        try:
            import json
            translations = json.loads(translations)
        except Exception as e:
            logger.debug("Could not parse page name_translations JSON: %s", e)
            translations = None

    if isinstance(translations, dict) and translations:
        val = translations.get(locale_code)
        if val and str(val).strip():
            return str(val).strip()
        val = translations.get('en')
        if val and str(val).strip():
            return str(val).strip()

    return page.name or _("Data Entry")


def get_localized_section_name(section) -> str:
    """
    Get the localized section name with translation support.
    """
    if not section:
        return _("Unknown Section")

    locale_code = get_translation_key()
    translations = section.name_translations
    if isinstance(translations, str):
        try:
            import json
            translations = json.loads(translations)
        except Exception as e:
            logger.debug("Could not parse section name_translations JSON: %s", e)
            translations = None

    if isinstance(translations, dict) and translations:
        val = translations.get(locale_code)
        if val and str(val).strip():
            return str(val).strip()
        val = translations.get('en')
        if val and str(val).strip():
            return str(val).strip()

    return section.name or _("Unknown Section")


def get_localized_template_name(template, locale: Optional[str] = None, version=None) -> str:
    """
    Get the localized template name based on the current session language.
    Falls back to the default name if localized version is not available.

    Args:
        template: FormTemplate object
        locale: Optional locale code (e.g., 'ar', 'fr', 'es'). If not provided, uses session language.
        version: Optional FormTemplateVersion object. If provided, uses version-specific name/translations.
                  If not provided, uses the template's published version.

    Note:
        Template name_translations are stored with ISO locale codes (e.g., 'ar', 'fr', 'es'),
        ISO codes only (not language-name keys).
        Names are now stored only in versions, not in templates.
    """
    if not template:
        return _("Unknown Template")

    # Use provided version, or fall back to published version, or first version
    if not version:
        version = template.published_version if template.published_version else template.versions.order_by('created_at').first()

    if not version:
        return _("Unknown Template")

    # Use version name and translations
    name_to_use = version.name if version.name else "Unnamed Template"
    translations_to_use = version.name_translations

    if translations_to_use:
        # Get locale from parameter or canonical session/request language
        current_locale = locale or get_translation_key()

        # Version name_translations use ISO codes directly (e.g., 'ar', 'fr', 'es')
        # Check if we have a translation for this locale
        # Handle both dict and JSON string formats
        translations_dict = translations_to_use
        if isinstance(translations_dict, str):
            import json
            try:
                translations_dict = json.loads(translations_dict)
            except (json.JSONDecodeError, TypeError):
                translations_dict = {}

        if isinstance(translations_dict, dict):
            # Try exact locale match first
            translated_name = translations_dict.get(current_locale)
            if translated_name and translated_name.strip():
                return translated_name

            # Fallback: try lowercase version of locale
            translated_name = translations_dict.get(current_locale.lower())
            if translated_name and translated_name.strip():
                return translated_name

    return name_to_use


def get_localized_country_name(country):
    """
    Get the localized country name based on the current session language.
    Falls back to the default name if localized version is not available.
    """
    if not country:
        return _('Unknown Country')
    locale_code = get_translation_key()
    try:
        translated = country.get_name_translation(locale_code)
        return translated or getattr(country, "name", _("Unknown Country"))
    except Exception as e:
        logger.debug("get_localized_country_name failed: %s", e)
        return getattr(country, "name", _("Unknown Country"))


def get_localized_national_society_name(country):
    """
    Get the localized National Society name based on the current session language.
    Falls back to the default name if localized version is not available.
    """
    if not country:
        return _('Unknown')
    try:
        # Prefer active NS ordered by display_order, then id
        nss = list(getattr(country, 'national_societies', []) or [])
        if not nss:
            # Fallback to country name if no NS exists
            return getattr(country, 'name', _('Unknown'))
        active = [ns for ns in nss if getattr(ns, 'is_active', True)]
        candidates = active if active else nss
        candidates.sort(key=lambda ns: ((getattr(ns, 'display_order', 0) or 0), getattr(ns, 'id', 0) or 0))
        ns = candidates[0]

        # Get current locale code (e.g., 'fr', 'es', 'ar')
        current_locale = get_translation_key()

        # NS name_translations use locale codes directly (e.g., 'fr', 'es', 'ar')
        if getattr(ns, 'name_translations', None):
            # Try exact locale match first
            translated = ns.get_name_translation(current_locale)
            if translated and translated.strip() and translated != ns.name:
                return translated
            # Fallback: try lowercase version
            translated = ns.get_name_translation(current_locale.lower())
            if translated and translated.strip() and translated != ns.name:
                return translated

        return ns.name
    except Exception as e:
        logger.debug("get_localized_national_society_name failed: %s", e)
        return getattr(country, 'name', _('Unknown'))
