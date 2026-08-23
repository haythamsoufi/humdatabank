"""Shared translation helpers for organization WTForms and routes."""
import json
from contextlib import suppress
from typing import Any, Dict, Iterable, List

from flask import current_app, has_app_context
from wtforms import StringField
from wtforms.validators import Optional, Length

from app.models import db
from app.models.core import Country
from app.models.organization import (
    NationalSociety,
    SecretariatClusterOffice,
    SecretariatDepartment,
    SecretariatDivision,
    SecretariatRegionalOffice,
)
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.transactions import request_transaction_rollback
from config.config import Config


def iso_language_code(value: str | None) -> str:
    """Normalize a language key to a short ISO code (`ru_RU` / `russian` → `ru`)."""
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    return Country.normalize_language_code(raw)


def unique_iso_language_codes(values: Iterable | None, *, exclude_en: bool = True) -> List[str]:
    """Return de-duplicated ISO language codes, preserving order."""
    codes: List[str] = []
    seen = set()
    for value in values or []:
        code = iso_language_code(value)
        if not code or code in seen:
            continue
        if exclude_en and code == "en":
            continue
        seen.add(code)
        codes.append(code)
    return codes


def get_translation_codes() -> List[str]:
    """Return translatable ISO codes, matching the organization admin UI when possible.

    Production reads DB-backed supported languages (same source as the page columns).
    Tests keep using ``app.config`` so fixtures remain deterministic.
    """
    raw: List[Any] = []
    if has_app_context() and not current_app.config.get("TESTING"):
        with suppress(Exception):
            from app.services.platform.app_settings_service import get_supported_languages

            raw = list(get_supported_languages(default=[]) or [])
    if not raw and has_app_context():
        raw = list(current_app.config.get("TRANSLATABLE_LANGUAGES") or [])
        if not raw:
            raw = list(current_app.config.get("SUPPORTED_LANGUAGES") or [])
    if not raw:
        raw = list(getattr(Config, "TRANSLATABLE_LANGUAGES", []) or [])
        if not raw:
            raw = list(getattr(Config, "LANGUAGES", []) or [])
    return unique_iso_language_codes(raw, exclude_en=True)


def get_translation_languages():
    """Return translation languages based on current supported languages."""
    all_names = getattr(Config, "ALL_LANGUAGES_DISPLAY_NAMES", {}) or {}
    display_names = getattr(Config, "LANGUAGE_DISPLAY_NAMES", {}) or {}
    return [
        (code, display_names.get(code) or all_names.get(code, code.upper()))
        for code in get_translation_codes()
    ]


def lookup_translation(translations, lang_code: str | None) -> str:
    """Return a non-empty translation for *lang_code*, accepting locale and legacy keys."""
    data = normalize_translations_dict(translations)
    wanted = iso_language_code(lang_code)
    if not data or not wanted:
        return ""

    keys_to_try = []
    raw = str(lang_code or "").strip()
    if raw:
        keys_to_try.extend((raw, raw.lower()))
    keys_to_try.append(wanted)

    seen = set()
    for key in keys_to_try:
        if not key or key in seen:
            continue
        seen.add(key)
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for key, value in data.items():
        if iso_language_code(key) != wanted:
            continue
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def translation_is_present(translations, lang_code: str | None) -> bool:
    """True when a usable translation exists for *lang_code* (including aliased keys)."""
    return bool(lookup_translation(translations, lang_code))


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
    translations = normalize_translations_dict(getattr(entity, attr_name, None))

    for code in get_translation_codes():
        field = getattr(form, f'{field_prefix}_{code}', None)
        if field:
            # Only set value if a real translation exists (locale / legacy keys included).
            # Do NOT fall back to English names when the translation is missing.
            field.data = lookup_translation(translations, code)


def count_missing_name_translations(entities) -> Dict[str, int]:
    """Count missing translations for the provided entities."""
    lang_codes = get_translation_codes()
    counts: Dict[str, int] = {code: 0 for code in lang_codes}
    for entity in entities:
        base_name = getattr(entity, 'name', '')
        if not base_name or not str(base_name).strip():
            continue

        translations = normalize_translations_dict(getattr(entity, 'name_translations', None))
        for lang_code in lang_codes:
            if not translation_is_present(translations, lang_code):
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
    lang_codes = get_translation_codes()
    counts: Dict[str, int] = {code: 0 for code in lang_codes}

    for entity in entities:
        for source_attr, translations_attr in entity_translation_field_pairs(entity, fields, fields_for_entity):
            source_value = getattr(entity, source_attr, None)
            if not source_value or not str(source_value).strip():
                continue

            translations = normalize_translations_dict(getattr(entity, translations_attr, None))
            for lang_code in lang_codes:
                if not translation_is_present(translations, lang_code):
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
            for lang_code in unique_iso_language_codes(normalized_languages, exclude_en=True):
                if translation_is_present(translations, lang_code):
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
            for lang_code in unique_iso_language_codes(normalized_languages, exclude_en=True):
                if translation_is_present(translations, lang_code):
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
            if not isinstance(outs, (list, tuple)) or len(outs) != len(jobs):
                raise ValueError("translation batch returned unexpected result")
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


def organization_entity_specs() -> Dict[str, Dict[str, Any]]:
    """Allowlisted organization entity types for bulk auto-translate persist."""
    return {
        "countries": {
            "model": Country,
            "label": "country",
            "fields": {"name": "name_translations"},
        },
        "national_societies": {
            "model": NationalSociety,
            "label": "national_society",
            "fields": {"name": "name_translations"},
        },
        "secretariat_divisions": {
            "model": SecretariatDivision,
            "label": "secretariat_division",
            "fields": {"name": "name_translations"},
        },
        "secretariat_departments": {
            "model": SecretariatDepartment,
            "label": "secretariat_department",
            "fields": {"name": "name_translations"},
        },
        "secretariat_regions": {
            "model": SecretariatRegionalOffice,
            "label": "secretariat_regional_office",
            "fields": {
                "name": "name_translations",
                "short_name": "short_name_translations",
            },
        },
        "secretariat_clusters": {
            "model": SecretariatClusterOffice,
            "label": "secretariat_cluster_office",
            "fields": {"name": "name_translations"},
        },
    }


def apply_organization_entity_translations(
    work_items: List[Dict[str, Any]],
    *,
    overwrite: bool = False,
    service_name: str | None = None,
    auto_translator=None,
) -> Dict[str, Any]:
    """Translate and persist organization name JSONB fields in language batches.

    ``work_items`` entries: ``id``, ``entity_type``, ``entity_id``, ``field``,
    ``text``, ``target_languages``. Same batching contract as Manage Translations
    (``translate_batch`` grouped by language, then one commit).
    """
    from sqlalchemy.orm.attributes import flag_modified

    specs = organization_entity_specs()
    if auto_translator is None:
        from app.services.translation.auto_translator import get_auto_translator

        auto_translator = get_auto_translator()

    parsed: List[Dict[str, Any]] = []
    ids_by_type: Dict[str, set] = {}
    for raw in work_items or []:
        if not isinstance(raw, dict):
            continue
        entity_type = str(raw.get("entity_type") or "").strip()
        spec = specs.get(entity_type)
        if not spec:
            continue
        try:
            entity_id = int(raw.get("entity_id"))
        except (TypeError, ValueError):
            continue
        field = str(raw.get("field") or "name").strip() or "name"
        if field not in spec["fields"]:
            continue
        text = raw.get("text")
        if not text or not str(text).strip():
            continue
        langs = unique_iso_language_codes(raw.get("target_languages") or [], exclude_en=True)
        if not langs:
            continue
        item_id = raw.get("id")
        if item_id is None:
            item_id = f"{entity_type}:{entity_id}:{field}"
        parsed.append({
            "id": str(item_id),
            "entity_type": entity_type,
            "entity_id": entity_id,
            "field": field,
            "translations_attr": spec["fields"][field],
            "label": spec["label"],
            "text": str(text).strip(),
            "target_languages": langs,
        })
        ids_by_type.setdefault(entity_type, set()).add(entity_id)

    entities_by_key: Dict[tuple, Any] = {}
    for entity_type, ids in ids_by_type.items():
        model = specs[entity_type]["model"]
        for row in model.query.filter(model.id.in_(list(ids))).all():
            entities_by_key[(entity_type, row.id)] = row

    jobs = []
    skipped_existing = 0
    for item in parsed:
        entity = entities_by_key.get((item["entity_type"], item["entity_id"]))
        if entity is None:
            continue
        translations = normalize_translations_dict(getattr(entity, item["translations_attr"], None))
        for lang in item["target_languages"]:
            if not overwrite and translation_is_present(translations, lang):
                skipped_existing += 1
                continue
            jobs.append((item, lang, entity))

    by_lang: Dict[str, list] = {}
    for job in jobs:
        by_lang.setdefault(job[1], []).append(job)

    translated_by_key: Dict[tuple, Any] = {}
    for lang_code, lang_jobs in by_lang.items():
        texts = [j[0]["text"] for j in lang_jobs]
        try:
            if len(texts) == 1:
                outs = [auto_translator.translate_text(texts[0], lang_code, "en", service_name)]
            else:
                outs = auto_translator.translate_batch(texts, lang_code, "en", service_name)
            if not isinstance(outs, (list, tuple)) or len(outs) != len(lang_jobs):
                raise ValueError("translation batch returned unexpected result")
        except Exception:
            outs = [
                resolve_field_translation(
                    j[2],
                    j[0]["field"],
                    j[0]["text"],
                    lang_code,
                    auto_translator,
                    service_name,
                )
                for j in lang_jobs
            ]
        for job, translated in zip(lang_jobs, outs):
            translated_by_key[(id(job[2]), job[0]["field"], job[1])] = translated

    jobs.sort(key=lambda job: 0 if job[0]["field"] == "name" else 1)

    results: List[Dict[str, Any]] = []
    success_count = 0
    skipped_untranslatable = 0
    dirty: List[Any] = []

    for item, lang_code, entity in jobs:
        translated = translated_by_key.get((id(entity), item["field"], lang_code))
        if item["field"] == "short_name":
            name = getattr(entity, "name", None)
            if name and item["text"].strip().casefold() == str(name).strip().casefold():
                copied = lookup_translation(getattr(entity, "name_translations", None), lang_code)
                if copied:
                    translated = copied

        if not translated or not str(translated).strip():
            skipped_untranslatable += 1
            continue

        translated = str(translated).strip()
        current = dict(normalize_translations_dict(getattr(entity, item["translations_attr"], None)))
        current[lang_code] = translated
        setattr(entity, item["translations_attr"], current)
        flag_modified(entity, item["translations_attr"])
        dirty.append(entity)

        try:
            from app.services.translation.catalog_service import (
                PROVENANCE_MACHINE,
                record_entity_provenance,
            )

            record_entity_provenance(
                entity_type=item["label"],
                entity_id=int(entity.id),
                field_name=item["translations_attr"],
                locale=lang_code,
                provenance=PROVENANCE_MACHINE,
                engine=service_name,
            )
        except Exception:
            current_app.logger.debug("entity provenance write skipped", exc_info=True)

        success_count += 1
        results.append({
            "id": item["id"],
            "entity_id": entity.id,
            "entity_type": item["entity_type"],
            "field": item["field"],
            "language": lang_code,
            "translation": translated,
        })

    if dirty:
        seen_ids = set()
        for entity in dirty:
            marker = id(entity)
            if marker in seen_ids:
                continue
            seen_ids.add(marker)
            db.session.add(entity)
        db.session.commit()

    return {
        "success_count": success_count,
        "results": results,
        "skipped_untranslatable": skipped_untranslatable,
        "skipped_existing": skipped_existing,
    }

