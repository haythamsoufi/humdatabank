"""Shared translation helpers for organization WTForms and routes."""
import json
from contextlib import suppress
from typing import Any, Dict

from flask import current_app, has_app_context
from wtforms import StringField
from wtforms.validators import Optional, Length

from app.models import db
from app.models.organization import (
    SecretariatClusterOffice,
    SecretariatDepartment,
    SecretariatDivision,
    SecretariatRegionalOffice,
)
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.transactions import request_transaction_rollback
from config.config import Config

def get_translation_languages():
    """Return translation languages based on current supported languages."""
    # Prefer runtime config so orgs can change languages without code changes.
    # Must be safe to call during module import (no app context yet).
    if has_app_context():
        langs = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
    else:
        langs = []
    langs = langs or getattr(Config, "TRANSLATABLE_LANGUAGES", []) or []
    all_names = getattr(Config, "ALL_LANGUAGES_DISPLAY_NAMES", {}) or {}
    return [(code, all_names.get(code, code.upper())) for code in langs]


def get_translation_codes():
    return [code for code, _ in get_translation_languages()]


def add_translation_fields(form_cls, base_name, label_prefix, max_length):
    """Dynamically attach language-specific StringFields to a WTForms class."""
    added_any = False
    for code, language in get_translation_languages():
        field_name = f'{base_name}_{code}'
        if not hasattr(form_cls, field_name):
            setattr(
                form_cls,
                field_name,
                StringField(
                    f'{label_prefix} ({language})',
                    validators=[Optional(), Length(max=max_length)]
                ),
            )
            added_any = True

    # WTForms clears `form_cls._unbound_fields` to None when new fields are added
    # at runtime (via FormMeta.__setattr__). If we add fields during `__init__`,
    # we must rebuild it before calling `super().__init__()`; otherwise WTForms
    # will crash trying to iterate None.
    if added_any or getattr(form_cls, "_unbound_fields", None) is None:
        fields = []
        for name in dir(form_cls):
            if not name.startswith("_"):
                unbound_field = getattr(form_cls, name)
                if hasattr(unbound_field, "_formfield"):
                    fields.append((name, unbound_field))
        # Stable sort: creation order, then name.
        fields.sort(key=lambda x: (x[1].creation_counter, x[0]))
        form_cls._unbound_fields = fields

def collect_translations(form, field_prefix):
    """Extract non-empty translation values from a form for a given field prefix."""
    translations = {}
    for code in get_translation_codes():
        field = getattr(form, f'{field_prefix}_{code}', None)
        if field and field.data and field.data.strip():
            translations[code] = field.data.strip()
    return translations or None


def clear_translation_fields(form, field_prefix):
    """Clear translation fields to prevent WTForms from using property fallbacks
    that return English names when translations don't exist.
    """
    for code in get_translation_codes():
        field = getattr(form, f'{field_prefix}_{code}', None)
        if field:
            field.data = ''


def populate_translation_fields(form, entity, attr_name, field_prefix):
    """Populate form translation fields from an entity JSONB attribute.

    Only populates fields if a translation value exists. Missing translations
    are left empty (not filled with English values).

    Note: Call _clear_translation_fields() first if the entity has properties
    that fall back to English names.
    """
    raw_translations = getattr(entity, attr_name, None)
    translations = None

    if raw_translations:
        translations = raw_translations
        if isinstance(raw_translations, str):
            try:
                translations = json.loads(raw_translations)
            except (TypeError, ValueError):
                translations = None
        if not isinstance(translations, dict):
            translations = None

    for code in get_translation_codes():
        field = getattr(form, f'{field_prefix}_{code}', None)
        if field:
            value = ''
            # Only set value if translation exists in name_translations JSONB field
            # Do NOT fall back to legacy properties as they return English when translation is missing
            if translations and code in translations:
                translation_value = translations.get(code)
                # Only use the value if it's a non-empty string
                if translation_value and isinstance(translation_value, str) and translation_value.strip():
                    value = translation_value.strip()
            # Always set to empty string if no valid translation found (never use English as fallback)
            field.data = value


def count_missing_name_translations(entities) -> Dict[str, int]:
    """Count missing translations for the provided entities."""
    counts: Dict[str, int] = {}
    if has_app_context():
        lang_codes = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
    else:
        lang_codes = getattr(Config, "TRANSLATABLE_LANGUAGES", []) or []
    for entity in entities:
        base_name = getattr(entity, 'name', '')
        if not base_name or not str(base_name).strip():
            continue

        raw = getattr(entity, 'name_translations', None)
        translations: Dict[str, Any] = {}
        if isinstance(raw, dict):
            translations = raw
        elif isinstance(raw, str):
            with suppress((TypeError, ValueError, json.JSONDecodeError)):
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    translations = parsed

        for lang_code in lang_codes:
            translated_value = translations.get(lang_code) if translations else None
            if not translated_value or not str(translated_value).strip():
                counts[lang_code] = counts.get(lang_code, 0) + 1

    return counts


def normalize_translations_dict(raw) -> Dict[str, Any]:
    """Return a dict of translations from a JSONB column value."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        with suppress((TypeError, ValueError, json.JSONDecodeError)):
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
    return {}


def regional_office_translation_fields(entity) -> list:
    """Return translatable field pairs for a regional office."""
    fields = [('name', 'name_translations')]
    short_name = getattr(entity, 'short_name', None)
    if short_name and str(short_name).strip():
        fields.append(('short_name', 'short_name_translations'))
    return fields


def resolve_field_translation(entity, source_attr, source_value, lang_code, auto_translator, translation_service):
    """Translate a field, copying name translations for identical short names when possible."""
    if source_attr == 'short_name':
        name = getattr(entity, 'name', None)
        if name and str(source_value).strip().casefold() == str(name).strip().casefold():
            name_translations = normalize_translations_dict(getattr(entity, 'name_translations', None))
            copied = name_translations.get(lang_code) if name_translations else None
            if copied and str(copied).strip():
                return str(copied).strip()

    return auto_translator.translate_text(
        str(source_value).strip(),
        lang_code,
        'en',
        translation_service,
    )


def entity_translation_field_pairs(entity, fields, fields_for_entity=None):
    if fields_for_entity is not None:
        return fields_for_entity(entity)
    return fields or []


def commit_translation_entity(entity) -> None:
    """Commit a single translated entity (streaming endpoints opt out of auto-commit)."""
    db.session.add(entity)
    db.session.commit()


def count_missing_translations_for_fields(entities, fields, fields_for_entity=None) -> Dict[str, int]:
    """Count missing translations for one or more source/translation field pairs."""
    counts: Dict[str, int] = {}
    if has_app_context():
        lang_codes = current_app.config.get("TRANSLATABLE_LANGUAGES") or []
    else:
        lang_codes = getattr(Config, "TRANSLATABLE_LANGUAGES", []) or []

    for entity in entities:
        for source_attr, translations_attr in entity_translation_field_pairs(entity, fields, fields_for_entity):
            source_value = getattr(entity, source_attr, None)
            if not source_value or not str(source_value).strip():
                continue

            translations = normalize_translations_dict(getattr(entity, translations_attr, None))
            for lang_code in lang_codes:
                translated_value = translations.get(lang_code) if translations else None
                if not translated_value or not str(translated_value).strip():
                    counts[lang_code] = counts.get(lang_code, 0) + 1

    return counts


def secretariat_translation_fields(entity_type: str):
    """Return (entities, translation_fields, result_entity_type) for secretariat auto-translate."""
    if entity_type == 'secretariat_divisions':
        return SecretariatDivision.query.all(), [('name', 'name_translations')], 'secretariat_division'
    if entity_type == 'secretariat_departments':
        return SecretariatDepartment.query.all(), [('name', 'name_translations')], 'secretariat_department'
    if entity_type == 'secretariat_regions':
        return (
            SecretariatRegionalOffice.query.all(),
            None,
            'secretariat_regional_office',
        )
    if entity_type == 'secretariat_clusters':
        return SecretariatClusterOffice.query.all(), [('name', 'name_translations')], 'secretariat_cluster_office'
    return None, None, None


def secretariat_translation_jobs():
    """Return ordered translation jobs for all secretariat entity types."""
    return [
        (SecretariatDivision.query.all(), [('name', 'name_translations')], 'secretariat_division', None),
        (SecretariatDepartment.query.all(), [('name', 'name_translations')], 'secretariat_department', None),
        (
            SecretariatRegionalOffice.query.all(),
            None,
            'secretariat_regional_office',
            regional_office_translation_fields,
        ),
        (SecretariatClusterOffice.query.all(), [('name', 'name_translations')], 'secretariat_cluster_office', None),
    ]


def stream_entity_translation_events(
    entities,
    entity_type_label,
    fields,
    normalized_languages,
    auto_translator,
    translation_service,
    *,
    fields_for_entity=None,
    emit_complete=True,
):
    """Yield SSE events while translating entity name fields."""
    from sqlalchemy.orm.attributes import flag_modified

    total_count = 0
    for entity in entities:
        for source_attr, translations_attr in entity_translation_field_pairs(entity, fields, fields_for_entity):
            source_value = getattr(entity, source_attr, None)
            if not source_value or not str(source_value).strip():
                continue
            translations = normalize_translations_dict(getattr(entity, translations_attr, None))
            for lang_code in Config.TRANSLATABLE_LANGUAGES:
                if lang_code not in normalized_languages:
                    continue
                if lang_code in translations and str(translations.get(lang_code, '')).strip():
                    continue
                total_count += 1

    yield f"data: {json.dumps({'type': 'start', 'total': total_count})}\n\n"

    processed_count = 0
    success_count = 0
    error_count = 0

    pending_jobs = []
    for entity in entities:
        for source_attr, translations_attr in entity_translation_field_pairs(entity, fields, fields_for_entity):
            source_value = getattr(entity, source_attr, None)
            if not source_value or not str(source_value).strip():
                continue

            translations = normalize_translations_dict(getattr(entity, translations_attr, None))
            for lang_code in Config.TRANSLATABLE_LANGUAGES:
                if lang_code not in normalized_languages:
                    continue
                if lang_code in translations and str(translations.get(lang_code, '')).strip():
                    continue
                pending_jobs.append((entity, source_attr, translations_attr, source_value, lang_code))

    by_lang = {}
    for job in pending_jobs:
        by_lang.setdefault(job[4], []).append(job)

    translated_by_key = {}
    for lang_code, jobs in by_lang.items():
        texts = [j[3] for j in jobs]
        try:
            outs = auto_translator.translate_batch(
                texts, lang_code, 'en', translation_service
            )
        except Exception:
            outs = [
                resolve_field_translation(
                    j[0], j[1], j[3], lang_code, auto_translator, translation_service
                )
                for j in jobs
            ]
        for job, translated in zip(jobs, outs):
            translated_by_key[(id(job[0]), job[1], lang_code)] = translated

    for entity, source_attr, translations_attr, source_value, lang_code in pending_jobs:
        translated = translated_by_key.get((id(entity), source_attr, lang_code))

        if translated:
            if not getattr(entity, translations_attr, None):
                setattr(entity, translations_attr, {})
            current_translations = normalize_translations_dict(getattr(entity, translations_attr, None))
            current_translations[lang_code] = translated
            setattr(entity, translations_attr, current_translations)
            flag_modified(entity, translations_attr)
            try:
                from app.services.translation.catalog_service import (
                    PROVENANCE_MACHINE,
                    record_entity_provenance,
                )

                record_entity_provenance(
                    entity_type=entity_type_label,
                    entity_id=int(entity.id),
                    field_name=translations_attr,
                    locale=lang_code,
                    provenance=PROVENANCE_MACHINE,
                    engine=translation_service,
                )
            except Exception:
                current_app.logger.debug("entity provenance write skipped", exc_info=True)

            result = {
                'success': True,
                'entity_type': entity_type_label,
                'entity_id': entity.id,
                'language': lang_code,
                'field': source_attr,
            }
            success_count += 1
        else:
            result = {
                'success': False,
                'entity_type': entity_type_label,
                'entity_id': entity.id,
                'language': lang_code,
                'field': source_attr,
                'error': 'Translation service returned no result',
            }
            error_count += 1

        processed_count += 1

        try:
            commit_translation_entity(entity)
        except Exception as e:
            request_transaction_rollback()
            current_app.logger.error(
                "Error committing translation for %s %s field %s, language %s: %s",
                entity_type_label,
                entity.id,
                source_attr,
                lang_code,
                e,
            )
            result['success'] = False
            result['error'] = GENERIC_ERROR_MESSAGE
            error_count += 1
            if success_count > 0 and translated:
                success_count -= 1

        yield f"data: {json.dumps({'type': 'progress', 'result': result, 'processed': processed_count, 'total': total_count, 'success': success_count, 'error': error_count})}\n\n"

    if emit_complete:
        yield f"data: {json.dumps({'type': 'complete', 'processed': processed_count, 'total': total_count, 'success': success_count, 'error': error_count})}\n\n"

