"""
FormTemplateAIService
─────────────────────
Bulk create/edit service for form templates, used by the AI chatbot
form-builder assistant tools.

Design rules (safety invariants enforced here, not just in prompts):
- All writes go to a *draft* FormTemplateVersion. Published versions are
  never modified and ``published_version_id`` is never touched.
- Versions are never deleted (except the explicit ``discard_draft``).
- RBAC is checked on every public method (``admin.templates.create`` /
  ``admin.templates.edit`` / ``admin.templates.view`` + template access).

The canonical JSON schema accepted by ``create_template`` /
``apply_edits`` mirrors the relational model: template metadata +
``pages[]`` + ``sections[]`` with nested ``items[]``. Every section/item
may carry an optional ``ref`` key so that later operations (and skip
logic rules) can reference entities created in the same call; results
echo the ``ref -> created id`` mapping.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app

from app import db
from app.models import (
    FormTemplate,
    FormTemplateVersion,
    FormPage,
    FormSection,
    FormItem,
    IndicatorBank,
    LookupList,
    QuestionType,
)
from app.utils.datetime_helpers import utcnow

logger = logging.getLogger(__name__)


class FormTemplateAIError(Exception):
    """User-facing error raised for invalid schemas, RBAC failures, etc."""


# ---------------------------------------------------------------------------
# Schema vocabulary
# ---------------------------------------------------------------------------

QUESTION_TYPES = {qt.value for qt in QuestionType}

SECTION_TYPES = {"standard", "repeat", "dynamic_indicators"}

ITEM_TYPES = {"question", "indicator", "document_field", "matrix"}

DISAGGREGATION_OPTIONS = {"total", "sex", "age", "sex_age", "disability"}

SYSTEM_LOOKUP_LISTS = {"country_map", "indicator_bank", "national_society", "emergency_operations"}

# "number" is accepted as a legacy alias for "number_whole" for backward compatibility with
# older AI prompts/specs; it is normalized to the explicit type below.
MATRIX_COLUMN_TYPES = {"number", "number_whole", "number_decimal", "tick"}

# Per-target-type condition types. Restricted to what the data-entry runtime
# evaluator actually implements (contains/starts_with/ends_with are offered by
# the builder for text questions but silently fail at runtime, so they are
# excluded for text; contains/not_contains are kept for multiple_choice).
_NUMERIC_CONDITIONS = {
    "equal_to", "not_equal_to",
    "greater_than", "greater_than_or_equal_to",
    "less_than", "less_than_or_equal_to",
    "is_empty", "is_not_empty",
}
_EMPTYNESS_CONDITIONS = {"is_empty", "is_not_empty"}

CONDITION_TYPES_BY_TARGET = {
    "number": _NUMERIC_CONDITIONS,
    "percentage": _NUMERIC_CONDITIONS,
    "text": {"equal_to", "not_equal_to", "is_empty", "is_not_empty"},
    "textarea": {"equal_to", "not_equal_to", "is_empty", "is_not_empty"},
    "yesno": {"is_yes", "is_no", "is_empty", "is_not_empty"},
    "single_choice": {"equal_to", "not_equal_to", "is_empty", "is_not_empty"},
    "multiple_choice": {"contains", "not_contains", "is_empty", "is_not_empty"},
    "date": _NUMERIC_CONDITIONS,
    "datetime": _NUMERIC_CONDITIONS,
    "indicator": _NUMERIC_CONDITIONS,
    "document_field": _EMPTYNESS_CONDITIONS,
    "matrix": _EMPTYNESS_CONDITIONS,
}

_VALUELESS_CONDITIONS = {"is_yes", "is_no", "is_empty", "is_not_empty"}

EDIT_OPERATIONS = {
    "update_template_settings",
    "add_page",
    "add_section",
    "update_section",
    "remove_section",
    "add_item",
    "update_item",
    "remove_item",
    "set_relevance",
    "set_validation",
}

# Hard limits so a single tool call cannot create unbounded structures.
MAX_SECTIONS_PER_CALL = 60
MAX_ITEMS_PER_CALL = 400
MAX_OPERATIONS_PER_CALL = 80
MAX_OPTIONS_PER_QUESTION = 200


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _as_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_str(value: Any, max_len: int = 2000) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return s[:max_len]


def _supported_language_codes() -> List[str]:
    try:
        codes = current_app.config.get("SUPPORTED_LANGUAGES")
        if codes:
            return list(codes)
    except RuntimeError:
        pass
    return ["en"]


def _normalize_name_translations(value: Any, max_len: int = 500) -> Optional[Dict[str, str]]:
    """Normalize a locale -> label map (ISO language codes only)."""
    if not isinstance(value, dict):
        return None
    supported = _supported_language_codes()
    cleaned: Dict[str, str] = {}
    for raw_code, raw_text in value.items():
        if not isinstance(raw_code, str):
            continue
        code = raw_code.strip().lower().split("_", 1)[0]
        if code not in supported:
            continue
        text = _clean_str(raw_text, max_len)
        if text:
            cleaned[code] = text
    return cleaned or None


class FormTemplateAIService:
    """Create and edit form templates from a canonical JSON schema."""

    # ------------------------------------------------------------------
    # RBAC helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _require_permission(user, permission_code: str) -> None:
        from app.services.organization.authorization_service import AuthorizationService

        if user is None or not getattr(user, "id", None):
            raise FormTemplateAIError("Authentication required for form template tools.")
        try:
            allowed = AuthorizationService.has_rbac_permission(user, permission_code)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("RBAC check %s failed: %s", permission_code, exc)
            allowed = False
        if not allowed:
            raise FormTemplateAIError(
                f"You do not have the '{permission_code}' permission required for this action."
            )

    @staticmethod
    def _require_template_access(template_id: int, user) -> FormTemplate:
        from app.services.organization.authorization_service import AuthorizationService

        template = FormTemplate.query.get(int(template_id))
        if not template:
            raise FormTemplateAIError(f"Template {template_id} not found.")
        try:
            allowed = AuthorizationService.check_template_access(int(template_id), int(user.id))
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("check_template_access failed: %s", exc)
            allowed = False
        if not allowed:
            raise FormTemplateAIError("You do not have access to this template (owner/shared only).")
        return template

    # ------------------------------------------------------------------
    # Draft handling
    # ------------------------------------------------------------------

    @staticmethod
    def _get_or_create_draft(template: FormTemplate, user_id: int) -> FormTemplateVersion:
        from app.routes.admin.form_builder.helpers.template_mgmt import _get_or_create_draft_version

        draft = _get_or_create_draft_version(template, user_id)
        # Compare to the value string — str(enum) is the member repr, not "draft".
        if draft.status != "draft":  # pragma: no cover - invariant guard
            raise FormTemplateAIError("Internal error: resolved version is not a draft.")
        return draft

    @staticmethod
    def _resolve_read_version(template: FormTemplate, version_id: Optional[int]) -> FormTemplateVersion:
        if version_id:
            version = FormTemplateVersion.query.filter_by(
                id=int(version_id), template_id=template.id
            ).first()
            if not version:
                raise FormTemplateAIError(
                    f"Version {version_id} not found for template {template.id}."
                )
            return version
        draft = FormTemplateVersion.query.filter_by(template_id=template.id, status="draft").first()
        if draft:
            return draft
        if template.published_version_id:
            published = FormTemplateVersion.query.get(template.published_version_id)
            if published:
                return published
        version = template.versions.order_by("created_at").first()
        if not version:
            raise FormTemplateAIError(f"Template {template.id} has no versions.")
        return version

    # ------------------------------------------------------------------
    # Public API: read
    # ------------------------------------------------------------------

    def get_full_structure(
        self,
        template_id: int,
        user,
        version_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Version-scoped full serialization of a template (draft preferred)."""
        self._require_permission(user, "admin.templates.view")
        template = self._require_template_access(template_id, user)
        version = self._resolve_read_version(template, version_id)

        pages = (
            FormPage.query.filter_by(template_id=template.id, version_id=version.id)
            .order_by(FormPage.order)
            .all()
        )
        sections = (
            FormSection.query.filter_by(template_id=template.id, version_id=version.id, archived=False)
            .order_by(FormSection.order)
            .all()
        )

        sections_data = []
        for section in sections:
            items = (
                FormItem.query.filter_by(section_id=section.id, archived=False)
                .order_by(FormItem.order)
                .all()
            )
            sections_data.append(self._serialize_section(section, items))

        return {
            "template_id": template.id,
            "version_id": version.id,
            "version_number": version.version_number,
            "version_status": (
                version.status.value
                if hasattr(version.status, "value")
                else version.status
            ),
            "name": version.name,
            "description": version.description,
            "name_translations": version.name_translations,
            "description_translations": version.description_translations,
            "is_paginated": bool(version.is_paginated),
            "pages": [
                {
                    "id": p.id,
                    "name": p.name,
                    "order": p.order,
                    "name_translations": p.name_translations,
                }
                for p in pages
            ],
            "sections": sections_data,
            "edit_url": self._edit_url(template.id, version.id),
        }

    @staticmethod
    def _serialize_section(section: FormSection, items: List[FormItem]) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "id": section.id,
            "name": section.name,
            "name_translations": section.name_translations,
            "order": section.order,
            "section_type": section.section_type or "standard",
            "parent_section_id": section.parent_section_id,
            "page_id": section.page_id,
            "relevance_condition": section.relevance_condition,
            "items": [FormTemplateAIService._serialize_item(i) for i in items],
        }
        if (section.section_type or "") == "repeat":
            data["max_entries"] = section.max_entries
        if (section.section_type or "") == "dynamic_indicators":
            data["max_dynamic_indicators"] = section.max_dynamic_indicators
            data["indicator_filters"] = section.indicator_filters_list
            data["allowed_disaggregation_options"] = section.allowed_disaggregation_options_list
        return data

    @staticmethod
    def _serialize_item(item: FormItem) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "id": item.id,
            "item_type": item.item_type,
            "label": item.label,
            "label_translations": item.label_translations,
            "order": item.order,
            "is_required": item.is_required,
            "relevance_condition": item.relevance_condition,
        }
        if item.is_question:
            data["question_type"] = item.type
            data["definition"] = item.definition
            data["definition_translations"] = item.definition_translations
            if item.options_json:
                data["options"] = item.options_json
                data["options_translations"] = item.options_translations
            if item.lookup_list_id:
                data["lookup_list_id"] = item.lookup_list_id
                data["list_display_column"] = item.list_display_column
                data["list_filters"] = item.list_filters_json
            data["validation_condition"] = item.validation_condition
            data["validation_message"] = item.validation_message
        elif item.is_indicator:
            data["indicator_bank_id"] = item.indicator_bank_id
            data["indicator_bank_name"] = item.indicator_bank.name if item.indicator_bank else None
            data["allowed_disaggregation_options"] = item.allowed_disaggregation_options
            data["validation_condition"] = item.validation_condition
            data["validation_message"] = item.validation_message
        elif item.is_document_field:
            data["description"] = item.description
            data["max_documents"] = (item.config or {}).get("max_documents")
        elif item.is_matrix:
            data["matrix_config"] = (item.config or {}).get("matrix_config")

        cfg = item.config or {}
        if cfg.get("show_hint"):
            data["show_hint"] = True
            if cfg.get("hint_text"):
                data["hint_text"] = cfg["hint_text"]
            if cfg.get("hint_text_translations"):
                data["hint_text_translations"] = cfg["hint_text_translations"]
            if cfg.get("hint_style"):
                data["hint_style"] = cfg["hint_style"]
        return data

    @staticmethod
    def _edit_url(template_id: int, version_id: Optional[int] = None) -> str:
        url = f"/admin/templates/edit/{int(template_id)}"
        if version_id:
            url += f"?version_id={int(version_id)}"
        return url

    # ------------------------------------------------------------------
    # Public API: create
    # ------------------------------------------------------------------

    def create_template(self, schema: Dict[str, Any], user) -> Dict[str, Any]:
        """Create a new FormTemplate with a draft v1 version from a canonical schema."""
        self._require_permission(user, "admin.templates.create")

        if not isinstance(schema, dict):
            raise FormTemplateAIError("Template schema must be an object.")
        name = _clean_str(schema.get("name"), 100)
        if not name:
            raise FormTemplateAIError("Template 'name' is required.")
        sections_schema = schema.get("sections") or []
        if not isinstance(sections_schema, list):
            raise FormTemplateAIError("'sections' must be a list.")

        self._validate_structure_size(sections_schema)

        warnings: List[str] = []
        try:
            template = FormTemplate(
                created_by=user.id,
                owned_by=user.id,
                created_at=utcnow(),
            )
            db.session.add(template)
            db.session.flush()

            draft = self._get_or_create_draft(template, user.id)
            draft.name = name
            draft.description = _clean_str(schema.get("description"), 4000)
            draft.is_paginated = _as_bool(schema.get("is_paginated"))
            draft.add_to_self_report = _as_bool(schema.get("add_to_self_report"))
            draft.display_order_visible = _as_bool(schema.get("display_order_visible"))
            draft.updated_by = user.id

            ref_map: Dict[str, Tuple[str, int]] = {}
            deferred_rules: List[Dict[str, Any]] = []

            self._build_pages(schema.get("pages") or [], template, draft, ref_map, warnings)
            counts = self._build_sections(
                sections_schema, template, draft, ref_map, warnings, deferred_rules
            )
            self._apply_deferred_rules(draft, ref_map, deferred_rules, warnings)

            summary = (
                f"Created template '{name}' with {counts['sections']} section(s) "
                f"and {counts['items']} item(s)."
            )
            self._append_change_log(draft, summary)

            db.session.commit()
        except FormTemplateAIError:
            db.session.rollback()
            raise
        except Exception as exc:
            db.session.rollback()
            logger.error("create_template failed: %s", exc, exc_info=True)
            raise FormTemplateAIError(f"Failed to create template: {exc}") from exc

        return {
            "template_id": template.id,
            "version_id": draft.id,
            "version_status": "draft",
            "name": name,
            "sections_created": counts["sections"],
            "items_created": counts["items"],
            "refs": {ref: {"type": kind, "id": obj_id} for ref, (kind, obj_id) in ref_map.items()},
            "warnings": warnings,
            "edit_url": self._edit_url(template.id, draft.id),
            "note": "The template was created as a DRAFT. The user must review it in the form builder and Deploy it to publish.",
        }

    # ------------------------------------------------------------------
    # Public API: edit
    # ------------------------------------------------------------------

    def apply_edits(self, template_id: int, operations: List[Dict[str, Any]], user) -> Dict[str, Any]:
        """Apply a list of edit operations to the template's draft version."""
        self._require_permission(user, "admin.templates.edit")
        template = self._require_template_access(template_id, user)

        if not isinstance(operations, list) or not operations:
            raise FormTemplateAIError("'operations' must be a non-empty list.")
        if len(operations) > MAX_OPERATIONS_PER_CALL:
            raise FormTemplateAIError(
                f"Too many operations in one call (max {MAX_OPERATIONS_PER_CALL})."
            )

        warnings: List[str] = []
        changes: List[str] = []
        ref_map: Dict[str, Tuple[str, int]] = {}
        deferred_rules: List[Dict[str, Any]] = []

        try:
            draft = self._get_or_create_draft(template, user.id)
            draft.updated_by = user.id
            undo_structure = self.get_full_structure(template_id, user, version_id=draft.id)

            for idx, op in enumerate(operations):
                if not isinstance(op, dict):
                    raise FormTemplateAIError(f"Operation #{idx + 1} must be an object.")
                op_name = str(op.get("op") or "").strip()
                if op_name not in EDIT_OPERATIONS:
                    raise FormTemplateAIError(
                        f"Operation #{idx + 1}: unknown op '{op_name}'. "
                        f"Allowed: {sorted(EDIT_OPERATIONS)}"
                    )
                handler = getattr(self, f"_op_{op_name}")
                change = handler(
                    op, template=template, draft=draft,
                    ref_map=ref_map, warnings=warnings, deferred_rules=deferred_rules,
                )
                if change:
                    changes.append(change)

            self._apply_deferred_rules(draft, ref_map, deferred_rules, warnings)

            if changes:
                self._append_change_log(draft, "; ".join(changes))

            redo_structure = self.get_full_structure(template_id, user, version_id=draft.id)
            db.session.commit()
        except FormTemplateAIError:
            db.session.rollback()
            raise
        except Exception as exc:
            db.session.rollback()
            logger.error("apply_edits failed: %s", exc, exc_info=True)
            raise FormTemplateAIError(f"Failed to apply edits: {exc}") from exc

        return {
            "template_id": template.id,
            "version_id": draft.id,
            "version_status": "draft",
            "changes": changes,
            "refs": {ref: {"type": kind, "id": obj_id} for ref, (kind, obj_id) in ref_map.items()},
            "warnings": warnings,
            "edit_url": self._edit_url(template.id, draft.id),
            "note": "Draft updated.",
            "undo_structure": undo_structure,
            "redo_structure": redo_structure,
        }

    def restore_draft_structure(
        self, template_id: int, structure: Dict[str, Any], user
    ) -> Dict[str, Any]:
        """Replace the current draft's pages/sections/items with a captured snapshot."""
        self._require_permission(user, "admin.templates.edit")
        template = self._require_template_access(template_id, user)

        if not isinstance(structure, dict):
            raise FormTemplateAIError("Structure snapshot must be an object.")
        if not isinstance(structure.get("sections"), list):
            raise FormTemplateAIError("Structure snapshot must include a 'sections' list.")

        draft = self._get_or_create_draft(template, user.id)
        warnings: List[str] = []

        existing_items = FormItem.query.filter_by(
            template_id=template.id, version_id=draft.id
        ).all()
        for item in existing_items:
            if self._item_has_data(item):
                raise FormTemplateAIError(
                    "Cannot restore this snapshot because some fields already have "
                    "submitted data."
                )

        try:
            FormItem.query.filter_by(
                template_id=template.id, version_id=draft.id
            ).delete(synchronize_session=False)
            FormSection.query.filter_by(
                template_id=template.id, version_id=draft.id
            ).delete(synchronize_session=False)
            FormPage.query.filter_by(
                template_id=template.id, version_id=draft.id
            ).delete(synchronize_session=False)
            db.session.flush()

            draft.name = _clean_str(structure.get("name"), 100) or draft.name
            draft.description = structure.get("description")
            draft.name_translations = structure.get("name_translations")
            draft.description_translations = structure.get("description_translations")
            draft.is_paginated = _as_bool(structure.get("is_paginated"))
            draft.updated_by = user.id

            ref_map: Dict[str, Tuple[str, int]] = {}
            deferred_rules: List[Dict[str, Any]] = []

            page_ref_by_id: Dict[int, str] = {}
            pages_schema: List[Dict[str, Any]] = []
            for page in structure.get("pages") or []:
                if not isinstance(page, dict):
                    continue
                old_id = _as_int(page.get("id"))
                ref = f"__restore_page_{old_id}" if old_id is not None else None
                if old_id is not None and ref:
                    page_ref_by_id[old_id] = ref
                pages_schema.append(
                    {
                        "name": page.get("name"),
                        "order": page.get("order"),
                        "ref": ref,
                        "name_translations": page.get("name_translations"),
                    }
                )
            if pages_schema:
                self._build_pages(pages_schema, template, draft, ref_map, warnings)

            raw_sections = [
                s for s in (structure.get("sections") or []) if isinstance(s, dict)
            ]
            raw_sections.sort(key=lambda s: _as_float(s.get("order"), 0.0) or 0.0)
            section_id_to_ref: Dict[int, str] = {}
            sections_schema: List[Dict[str, Any]] = []
            for section in raw_sections:
                old_id = _as_int(section.get("id"))
                ref = f"__restore_sec_{old_id}" if old_id is not None else None
                if old_id is not None and ref:
                    section_id_to_ref[old_id] = ref
                sections_schema.append(
                    self._structure_section_to_schema(section, page_ref_by_id, ref)
                )
            for section_schema, section in zip(sections_schema, raw_sections):
                parent_id = _as_int(section.get("parent_section_id"))
                if parent_id is not None and parent_id in section_id_to_ref:
                    section_schema["parent_ref"] = section_id_to_ref[parent_id]

            self._validate_structure_size(sections_schema)
            counts = self._build_sections(
                sections_schema, template, draft, ref_map, warnings, deferred_rules
            )
            self._apply_deferred_rules(draft, ref_map, deferred_rules, warnings)
            self._append_change_log(
                draft,
                f"Restored draft structure ({counts['sections']} section(s), "
                f"{counts['items']} item(s)).",
            )
            db.session.commit()
        except FormTemplateAIError:
            db.session.rollback()
            raise
        except Exception as exc:
            db.session.rollback()
            logger.error("restore_draft_structure failed: %s", exc, exc_info=True)
            raise FormTemplateAIError(f"Failed to restore draft structure: {exc}") from exc

        return {
            "template_id": template.id,
            "version_id": draft.id,
            "version_status": "draft",
            "edit_url": self._edit_url(template.id, draft.id),
            "sections_restored": counts["sections"],
            "items_restored": counts["items"],
            "warnings": warnings,
        }

    @staticmethod
    def _structure_section_to_schema(
        section: Dict[str, Any],
        page_ref_by_id: Dict[int, str],
        section_ref: Optional[str],
    ) -> Dict[str, Any]:
        schema: Dict[str, Any] = {
            "name": section.get("name"),
            "order": section.get("order"),
            "section_type": section.get("section_type") or "standard",
            "name_translations": section.get("name_translations"),
            "relevance_condition": section.get("relevance_condition"),
            "ref": section_ref,
        }
        page_id = _as_int(section.get("page_id"))
        if page_id is not None and page_id in page_ref_by_id:
            schema["page_ref"] = page_ref_by_id[page_id]
        for key in (
            "max_entries",
            "max_dynamic_indicators",
            "indicator_filters",
            "allowed_disaggregation_options",
        ):
            if section.get(key) is not None:
                schema[key] = section.get(key)
        items = []
        for item in section.get("items") or []:
            if isinstance(item, dict):
                items.append(FormTemplateAIService._structure_item_to_schema(item))
        schema["items"] = items
        return schema

    @staticmethod
    def _structure_item_to_schema(item: Dict[str, Any]) -> Dict[str, Any]:
        schema: Dict[str, Any] = {
            "item_type": item.get("item_type") or "question",
            "label": item.get("label"),
            "order": item.get("order"),
            "is_required": item.get("is_required"),
            "label_translations": item.get("label_translations"),
            "relevance_condition": item.get("relevance_condition"),
            "validation_condition": item.get("validation_condition"),
            "validation_message": item.get("validation_message"),
        }
        item_type = schema["item_type"]
        if item_type == "question":
            for key in (
                "question_type",
                "definition",
                "definition_translations",
                "options",
                "options_translations",
                "lookup_list_id",
                "list_display_column",
                "list_filters",
            ):
                if item.get(key) is not None:
                    schema[key] = item.get(key)
        elif item_type == "indicator":
            for key in ("indicator_bank_id", "allowed_disaggregation_options",):
                if item.get(key) is not None:
                    schema[key] = item.get(key)
        elif item_type == "document_field":
            if item.get("description") is not None:
                schema["description"] = item.get("description")
            if item.get("max_documents") is not None:
                schema["max_documents"] = item.get("max_documents")
        elif item_type == "matrix" and item.get("matrix_config") is not None:
            schema["matrix_config"] = item.get("matrix_config")
        return schema

    # ------------------------------------------------------------------
    # Public API: translations (phase 3)
    # ------------------------------------------------------------------

    def translate_template(
        self,
        template_id: int,
        languages: List[str],
        user,
        scope: str = "untranslated",
    ) -> Dict[str, Any]:
        """Machine-translate labels/definitions/options/section/page/template names."""
        self._require_permission(user, "admin.templates.edit")
        template = self._require_template_access(template_id, user)

        supported = [
            str(c).lower() for c in current_app.config.get("SUPPORTED_LANGUAGES", ["en"])
        ]
        targets = []
        for lang in languages or []:
            code = str(lang or "").strip().lower().split("_", 1)[0].split("-", 1)[0]
            if not code or code == "en":
                continue
            if code not in supported:
                raise FormTemplateAIError(
                    f"Language '{lang}' is not enabled on this platform. Supported: {supported}"
                )
            if code not in targets:
                targets.append(code)
        if not targets:
            raise FormTemplateAIError("Provide at least one non-English target language.")

        overwrite = str(scope or "untranslated").strip().lower() in ("overwrite", "all", "overwrite_all")

        from app.services.translation.auto_translator import get_auto_translator
        from config.config import Config

        translator = get_auto_translator()

        def _translate(text: str, code: str) -> Optional[str]:
            target = Config.LANGUAGE_MODEL_KEY.get(code) or code
            try:
                return translator.translate_text(text, target, "en")
            except Exception as exc:  # pragma: no cover - network failure path
                logger.debug("translate_text failed (%s -> %s): %s", text[:40], code, exc)
                return None

        try:
            max_items = _as_int(
                current_app.config.get("AI_FORM_TEMPLATE_TRANSLATE_MAX_ITEMS", 200), 200
            )
            draft = self._get_or_create_draft(template, user.id)
            draft.updated_by = user.id

            translated = 0
            skipped = 0
            failed = 0

            def _fill_map(current: Optional[dict], text: Optional[str]) -> Tuple[Optional[dict], int, int, int]:
                """Return (new_map, translated, skipped, failed) for one text field."""
                if not text or not str(text).strip():
                    return current, 0, 0, 0
                new_map = dict(current or {})
                t = s = f = 0
                for code in targets:
                    if not overwrite and new_map.get(code):
                        s += 1
                        continue
                    result = _translate(str(text), code)
                    if result:
                        new_map[code] = result
                        t += 1
                    else:
                        f += 1
                return (new_map or None), t, s, f

            # Template/version name + description
            for attr_text, attr_map in (
                ("name", "name_translations"),
                ("description", "description_translations"),
            ):
                new_map, t, s, f = _fill_map(getattr(draft, attr_map), getattr(draft, attr_text))
                if t:
                    setattr(draft, attr_map, new_map)
                translated, skipped, failed = translated + t, skipped + s, failed + f

            # Pages
            pages = FormPage.query.filter_by(template_id=template.id, version_id=draft.id).all()
            for page in pages:
                new_map, t, s, f = _fill_map(page.name_translations, page.name)
                if t:
                    page.name_translations = new_map
                translated, skipped, failed = translated + t, skipped + s, failed + f

            # Sections
            sections = FormSection.query.filter_by(
                template_id=template.id, version_id=draft.id, archived=False
            ).all()
            for section in sections:
                new_map, t, s, f = _fill_map(section.name_translations, section.name)
                if t:
                    section.name_translations = new_map
                translated, skipped, failed = translated + t, skipped + s, failed + f

            # Items (labels, definitions, manual options)
            items = (
                FormItem.query.filter_by(template_id=template.id, version_id=draft.id, archived=False)
                .order_by(FormItem.order)
                .limit(max_items or 200)
                .all()
            )
            for item in items:
                new_map, t, s, f = _fill_map(item.label_translations, item.label)
                if t:
                    item.label_translations = new_map
                translated, skipped, failed = translated + t, skipped + s, failed + f

                if item.definition:
                    new_map, t, s, f = _fill_map(item.definition_translations, item.definition)
                    if t:
                        item.definition_translations = new_map
                    translated, skipped, failed = translated + t, skipped + s, failed + f

                if item.is_document_field and item.description:
                    new_map, t, s, f = _fill_map(item.description_translations, item.description)
                    if t:
                        item.description_translations = new_map
                    translated, skipped, failed = translated + t, skipped + s, failed + f

                # Manual choice options: array of {option_text, translations}
                if item.is_question and isinstance(item.options_json, list) and item.options_json:
                    existing = item.options_translations if isinstance(item.options_translations, list) else []
                    by_text = {
                        str(e.get("option_text")): dict(e.get("translations") or {})
                        for e in existing
                        if isinstance(e, dict) and e.get("option_text")
                    }
                    changed = False
                    for option in item.options_json:
                        opt_text = str(option).strip()
                        if not opt_text:
                            continue
                        tr = by_text.setdefault(opt_text, {})
                        for code in targets:
                            if not overwrite and tr.get(code):
                                skipped += 1
                                continue
                            result = _translate(opt_text, code)
                            if result:
                                tr[code] = result
                                translated += 1
                                changed = True
                            else:
                                failed += 1
                    if changed:
                        item.options_translations = [
                            {"option_text": text, "translations": tr}
                            for text, tr in by_text.items()
                        ]

            summary = (
                f"Auto-translated template content to {', '.join(targets)} "
                f"({translated} strings translated)."
            )
            if translated:
                self._append_change_log(draft, summary)
            db.session.commit()
        except FormTemplateAIError:
            db.session.rollback()
            raise
        except Exception as exc:
            db.session.rollback()
            logger.error("translate_template failed: %s", exc, exc_info=True)
            raise FormTemplateAIError(f"Failed to translate template: {exc}") from exc

        return {
            "template_id": template.id,
            "version_id": draft.id,
            "languages": targets,
            "translated": translated,
            "skipped_existing": skipped,
            "failed": failed,
            "edit_url": self._edit_url(template.id, draft.id),
            "note": (
                "Translations were written to the DRAFT version. "
                "Failed strings usually mean no translation provider is configured."
            ),
        }

    # ------------------------------------------------------------------
    # Public API: discard draft (phase 7)
    # ------------------------------------------------------------------

    def discard_draft(self, template_id: int, user) -> Dict[str, Any]:
        """Delete the draft version and all its structure (the AI 'undo')."""
        self._require_permission(user, "admin.templates.edit")
        template = self._require_template_access(template_id, user)

        draft = FormTemplateVersion.query.filter_by(template_id=template.id, status="draft").first()
        if not draft:
            raise FormTemplateAIError("This template has no draft version to discard.")

        other_versions = (
            FormTemplateVersion.query.filter(
                FormTemplateVersion.template_id == template.id,
                FormTemplateVersion.id != draft.id,
            ).count()
        )
        if other_versions == 0:
            raise FormTemplateAIError(
                "The draft is the only version of this template. Discarding it would leave "
                "an empty template — delete the whole template from the Templates page instead."
            )

        try:
            items_deleted = FormItem.query.filter_by(
                template_id=template.id, version_id=draft.id
            ).delete(synchronize_session=False)
            sections_deleted = FormSection.query.filter_by(
                template_id=template.id, version_id=draft.id
            ).delete(synchronize_session=False)
            pages_deleted = FormPage.query.filter_by(
                template_id=template.id, version_id=draft.id
            ).delete(synchronize_session=False)
            db.session.delete(draft)
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            logger.error("discard_draft failed: %s", exc, exc_info=True)
            raise FormTemplateAIError(f"Failed to discard draft: {exc}") from exc

        return {
            "template_id": template.id,
            "discarded_version_id": draft.id,
            "items_deleted": items_deleted,
            "sections_deleted": sections_deleted,
            "pages_deleted": pages_deleted,
            "edit_url": self._edit_url(template.id),
            "note": "The draft was discarded. The published version is unchanged.",
        }

    # ------------------------------------------------------------------
    # Structure builders
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_structure_size(sections_schema: List[Any]) -> None:
        if len(sections_schema) > MAX_SECTIONS_PER_CALL:
            raise FormTemplateAIError(f"Too many sections (max {MAX_SECTIONS_PER_CALL}).")
        total_items = sum(
            len(s.get("items") or []) for s in sections_schema if isinstance(s, dict)
        )
        if total_items > MAX_ITEMS_PER_CALL:
            raise FormTemplateAIError(f"Too many items (max {MAX_ITEMS_PER_CALL}).")

    def _build_pages(
        self,
        pages_schema: List[Any],
        template: FormTemplate,
        draft: FormTemplateVersion,
        ref_map: Dict[str, Tuple[str, int]],
        warnings: List[str],
    ) -> None:
        if not pages_schema:
            return
        if not draft.is_paginated:
            draft.is_paginated = True
            warnings.append("Pages were provided, so is_paginated was enabled automatically.")
        for i, page_schema in enumerate(pages_schema):
            if not isinstance(page_schema, dict):
                raise FormTemplateAIError(f"Page #{i + 1} must be an object.")
            name = _clean_str(page_schema.get("name"), 100)
            if not name:
                raise FormTemplateAIError(f"Page #{i + 1}: 'name' is required.")
            page = FormPage(
                template_id=template.id,
                version_id=draft.id,
                name=name,
                order=_as_int(page_schema.get("order"), i + 1),
            )
            if page_schema.get("name_translations") is not None:
                page.name_translations = page_schema.get("name_translations")
            db.session.add(page)
            db.session.flush()
            self._register_ref(ref_map, page_schema.get("ref"), "page", page.id)

    def _build_sections(
        self,
        sections_schema: List[Any],
        template: FormTemplate,
        draft: FormTemplateVersion,
        ref_map: Dict[str, Tuple[str, int]],
        warnings: List[str],
        deferred_rules: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        counts = {"sections": 0, "items": 0}
        for i, section_schema in enumerate(sections_schema):
            if not isinstance(section_schema, dict):
                raise FormTemplateAIError(f"Section #{i + 1} must be an object.")
            section = self._create_section(
                section_schema, template, draft, ref_map, warnings,
                default_order=float(i + 1), deferred_rules=deferred_rules,
            )
            counts["sections"] += 1
            items_schema = section_schema.get("items") or []
            if not isinstance(items_schema, list):
                raise FormTemplateAIError(f"Section '{section.name}': 'items' must be a list.")
            for j, item_schema in enumerate(items_schema):
                if not isinstance(item_schema, dict):
                    raise FormTemplateAIError(
                        f"Section '{section.name}' item #{j + 1} must be an object."
                    )
                self._create_item(
                    item_schema, template, draft, section, ref_map, warnings,
                    default_order=float(j + 1), deferred_rules=deferred_rules,
                )
                counts["items"] += 1
        return counts

    def _create_section(
        self,
        schema: Dict[str, Any],
        template: FormTemplate,
        draft: FormTemplateVersion,
        ref_map: Dict[str, Tuple[str, int]],
        warnings: List[str],
        default_order: float,
        deferred_rules: List[Dict[str, Any]],
    ) -> FormSection:
        name = _clean_str(schema.get("name"), 100)
        if not name:
            raise FormTemplateAIError("Every section requires a 'name'.")
        section_type = str(schema.get("section_type") or "standard").strip().lower()
        if section_type not in SECTION_TYPES:
            raise FormTemplateAIError(
                f"Section '{name}': invalid section_type '{section_type}'. Allowed: {sorted(SECTION_TYPES)}"
            )

        page_id = None
        page_ref = schema.get("page_ref")
        if page_ref:
            page_id = self._resolve_ref(ref_map, page_ref, "page", f"Section '{name}' page_ref")
        elif schema.get("page_id"):
            page_id = self._validate_page_id(_as_int(schema.get("page_id")), template, draft, name)

        parent_section_id = None
        parent_ref = schema.get("parent_ref")
        if parent_ref:
            parent_section_id = self._resolve_ref(
                ref_map, parent_ref, "section", f"Section '{name}' parent_ref"
            )
        elif schema.get("parent_section_id"):
            parent_section_id = self._validate_section_id(
                _as_int(schema.get("parent_section_id")), draft, f"Section '{name}' parent_section_id"
            ).id

        section = FormSection(
            template_id=template.id,
            version_id=draft.id,
            name=name,
            order=_as_float(schema.get("order"), default_order),
            section_type=section_type,
            page_id=page_id,
            parent_section_id=parent_section_id,
        )

        self._apply_section_config(section, schema, warnings)

        if schema.get("name_translations") is not None:
            section.name_translations = schema.get("name_translations")
        if schema.get("relevance_condition") is not None:
            section.relevance_condition = schema.get("relevance_condition")

        db.session.add(section)
        db.session.flush()
        self._register_ref(ref_map, schema.get("ref"), "section", section.id)

        rule = schema.get("relevance")
        if rule is not None:
            deferred_rules.append({"kind": "section_relevance", "section_id": section.id, "rule": rule})

        return section

    def _apply_section_config(
        self, section: FormSection, schema: Dict[str, Any], warnings: List[str]
    ) -> None:
        """Apply type-specific config (repeat / dynamic_indicators) to a section."""
        section_type = section.section_type or "standard"

        if "max_entries" in schema and schema.get("max_entries") is not None:
            if section_type != "repeat":
                warnings.append(
                    f"Section '{section.name}': max_entries is only used for repeat sections (ignored)."
                )
            else:
                section.set_max_entries(_as_int(schema.get("max_entries")))

        if section_type == "dynamic_indicators":
            if schema.get("max_dynamic_indicators") is not None:
                section.max_dynamic_indicators = _as_int(schema.get("max_dynamic_indicators"))
            filters = schema.get("indicator_filters")
            if filters is not None:
                if not isinstance(filters, list):
                    raise FormTemplateAIError(
                        f"Section '{section.name}': indicator_filters must be a list of "
                        "{field, values} objects."
                    )
                normalized = []
                for f in filters:
                    if not isinstance(f, dict) or not f.get("field") or not isinstance(f.get("values"), list):
                        raise FormTemplateAIError(
                            f"Section '{section.name}': each indicator filter needs 'field' and 'values' (list)."
                        )
                    entry = {"field": str(f["field"]), "values": [str(v) for v in f["values"]]}
                    if f.get("primary_only") is not None:
                        entry["primary_only"] = _as_bool(f.get("primary_only"))
                    normalized.append(entry)
                section.set_indicator_filters(normalized)
            disagg = schema.get("allowed_disaggregation_options")
            if disagg is not None:
                section.set_allowed_disaggregation_options(
                    self._validate_disagg_options(disagg, f"Section '{section.name}'")
                )
            if schema.get("allow_data_not_available") is not None:
                section.allow_data_not_available = _as_bool(schema.get("allow_data_not_available"))
            if schema.get("allow_not_applicable") is not None:
                section.allow_not_applicable = _as_bool(schema.get("allow_not_applicable"))
            note = _clean_str(schema.get("add_indicator_note"), 2000)
            if note:
                section.add_indicator_note = note

    def _create_item(
        self,
        schema: Dict[str, Any],
        template: FormTemplate,
        draft: FormTemplateVersion,
        section: FormSection,
        ref_map: Dict[str, Tuple[str, int]],
        warnings: List[str],
        default_order: float,
        deferred_rules: List[Dict[str, Any]],
    ) -> FormItem:
        item_type = str(schema.get("item_type") or "question").strip().lower()
        if item_type not in ITEM_TYPES:
            raise FormTemplateAIError(
                f"Invalid item_type '{item_type}'. Allowed: {sorted(ITEM_TYPES)}"
            )

        label = _clean_str(schema.get("label"), 4000)
        question_type = None
        if item_type == "question":
            question_type = str(schema.get("question_type") or "").strip().lower()
            if question_type not in QUESTION_TYPES:
                raise FormTemplateAIError(
                    f"Question '{label or '?'}': invalid question_type '{question_type}'. "
                    f"Allowed: {sorted(QUESTION_TYPES)}"
                )
            if not label and question_type != "blank":
                raise FormTemplateAIError("Every non-blank question requires a 'label'.")
        elif not label:
            raise FormTemplateAIError(f"Every {item_type} item requires a 'label'.")

        item = FormItem(
            item_type=item_type,
            section_id=section.id,
            template_id=template.id,
            version_id=draft.id,
            label=label or "",
            order=_as_float(schema.get("order"), default_order),
        )

        config: Dict[str, Any] = {
            "is_required": _as_bool(schema.get("is_required")),
            "layout_column_width": min(12, max(1, _as_int(schema.get("layout_column_width"), 12))),
            "layout_break_after": _as_bool(schema.get("layout_break_after")),
            "allowed_disaggregation_options": ["total"],
            "age_groups_config": None,
            "default_value": _clean_str(schema.get("default_value"), 500),
            "allow_data_not_available": _as_bool(schema.get("allow_data_not_available")),
            "allow_not_applicable": _as_bool(schema.get("allow_not_applicable")),
            "allow_disability_questions": False,
            "indirect_reach": False,
            "privacy": _clean_str(schema.get("privacy"), 50) or "ifrc_network",
        }

        if _as_bool(schema.get("show_hint")):
            config["show_hint"] = True
            hint_text = _clean_str(schema.get("hint_text"), 500)
            if hint_text:
                config["hint_text"] = hint_text
            hint_translations = _normalize_name_translations(
                schema.get("hint_text_translations"), max_len=500
            )
            if hint_translations:
                config["hint_text_translations"] = hint_translations
            hint_style = _clean_str(schema.get("hint_style"), 20)
            if hint_style in {"normal", "info", "warning", "tip", "important"} and hint_style != "warning":
                config["hint_style"] = hint_style

        if item_type == "question":
            item.type = question_type
            item.definition = _clean_str(schema.get("definition"), 4000) or ""
            self._apply_question_options(item, schema, question_type, warnings)
        elif item_type == "indicator":
            self._apply_indicator_fields(item, schema, config, warnings)
        elif item_type == "document_field":
            item.description = _clean_str(schema.get("description"), 4000) or ""
            max_docs = _as_int(schema.get("max_documents"))
            config["max_documents"] = max_docs
        elif item_type == "matrix":
            config["matrix_config"] = self._validate_matrix_config(
                schema.get("matrix_config"), label or "matrix"
            )
            if config["matrix_config"].get("row_mode") == "list_library":
                item.lookup_list_id = str(config["matrix_config"].get("lookup_list_id"))
                item.list_display_column = config["matrix_config"].get("list_display_column")
                if config["matrix_config"].get("list_filters"):
                    item.list_filters_json = config["matrix_config"]["list_filters"]

        item.config = config

        if schema.get("label_translations") is not None:
            item.label_translations = schema.get("label_translations")
        if item.is_question and schema.get("definition_translations") is not None:
            item.definition_translations = schema.get("definition_translations")
        if item.is_question and schema.get("options_translations") is not None:
            item.options_translations = schema.get("options_translations")
        if schema.get("relevance_condition") is not None:
            item.relevance_condition = schema.get("relevance_condition")
        if schema.get("validation_condition") is not None:
            item.validation_condition = schema.get("validation_condition")

        validation_message = _clean_str(schema.get("validation_message"), 2000)
        if validation_message:
            item.validation_message = validation_message

        db.session.add(item)
        db.session.flush()
        self._register_ref(ref_map, schema.get("ref"), "item", item.id)

        if schema.get("relevance") is not None:
            deferred_rules.append(
                {"kind": "item_relevance", "item_id": item.id, "rule": schema.get("relevance")}
            )
        if schema.get("validation") is not None:
            deferred_rules.append(
                {
                    "kind": "item_validation",
                    "item_id": item.id,
                    "rule": schema.get("validation"),
                    "message": validation_message,
                }
            )

        return item

    def _apply_question_options(
        self, item: FormItem, schema: Dict[str, Any], question_type: str, warnings: List[str]
    ) -> None:
        options = schema.get("options")
        lookup_list_id = schema.get("lookup_list_id")
        is_choice = question_type in ("single_choice", "multiple_choice")

        if lookup_list_id is not None and str(lookup_list_id).strip():
            # Calculated choices (phase 6)
            if not is_choice:
                raise FormTemplateAIError(
                    f"Question '{item.label}': lookup_list_id is only valid for choice questions."
                )
            raw = str(lookup_list_id).strip()
            if raw.isdigit():
                lookup = LookupList.query.get(int(raw))
                if not lookup:
                    raise FormTemplateAIError(
                        f"Question '{item.label}': lookup list {raw} does not exist."
                    )
                item.lookup_list_id = str(int(raw))
                display_column = _clean_str(schema.get("list_display_column"), 100)
                if not display_column and lookup.columns_config:
                    try:
                        display_column = lookup.columns_config[0]["name"]
                    except Exception:
                        display_column = None
                item.list_display_column = display_column or "name"
            else:
                if raw not in SYSTEM_LOOKUP_LISTS:
                    warnings.append(
                        f"Question '{item.label}': '{raw}' is not a known system list "
                        f"({sorted(SYSTEM_LOOKUP_LISTS)}); it may be a plugin list."
                    )
                item.lookup_list_id = raw
                item.list_display_column = _clean_str(schema.get("list_display_column"), 100) or (
                    "code" if raw == "reporting_currency" else "name"
                )
            filters = schema.get("list_filters")
            if filters is not None:
                if not isinstance(filters, list):
                    raise FormTemplateAIError(
                        f"Question '{item.label}': list_filters must be a list of filter objects."
                    )
                item.list_filters_json = filters
            item.options_json = None
            return

        if options is not None:
            if not is_choice:
                warnings.append(
                    f"Question '{item.label}': options were provided but question_type is "
                    f"'{question_type}' — options ignored."
                )
                return
            if not isinstance(options, list) or not all(isinstance(o, (str, int, float)) for o in options):
                raise FormTemplateAIError(
                    f"Question '{item.label}': options must be a list of strings."
                )
            if len(options) > MAX_OPTIONS_PER_QUESTION:
                raise FormTemplateAIError(
                    f"Question '{item.label}': too many options (max {MAX_OPTIONS_PER_QUESTION})."
                )
            cleaned = [str(o).strip() for o in options if str(o).strip()]
            if not cleaned:
                raise FormTemplateAIError(f"Question '{item.label}': options list is empty.")
            item.options_json = cleaned
        elif is_choice:
            warnings.append(
                f"Question '{item.label}': choice question created without options — "
                "add options before deploying."
            )

    def _apply_indicator_fields(
        self, item: FormItem, schema: Dict[str, Any], config: Dict[str, Any], warnings: List[str]
    ) -> None:
        bank_id = _as_int(schema.get("indicator_bank_id"))
        bank = IndicatorBank.query.get(bank_id) if bank_id else None
        if bank:
            item.indicator_bank_id = bank.id
            item.type = bank.type or "number"
            item.unit = bank.unit or ""
            item.indicator_type_id = bank.indicator_type_id
            item.indicator_unit_id = bank.indicator_unit_id
            if not item.label:
                item.label = bank.name
        else:
            item.type = "number"
            item.unit = ""
            warnings.append(
                f"Indicator '{item.label}': no valid indicator_bank_id was provided "
                f"(got {schema.get('indicator_bank_id')!r}). The item was created, but the "
                "template cannot be deployed until a valid Indicator Bank reference is set. "
                "Use search_indicator_bank to find the right indicator."
            )
        disagg = schema.get("allowed_disaggregation_options")
        if disagg is not None:
            config["allowed_disaggregation_options"] = self._validate_disagg_options(
                disagg, f"Indicator '{item.label}'"
            )

    @staticmethod
    def _validate_disagg_options(value: Any, owner: str) -> List[str]:
        if not isinstance(value, list) or not value:
            raise FormTemplateAIError(
                f"{owner}: allowed_disaggregation_options must be a non-empty list."
            )
        cleaned = []
        for v in value:
            opt = str(v).strip().lower()
            if opt not in DISAGGREGATION_OPTIONS:
                raise FormTemplateAIError(
                    f"{owner}: invalid disaggregation option '{v}'. Allowed: {sorted(DISAGGREGATION_OPTIONS)}"
                )
            if opt not in cleaned:
                cleaned.append(opt)
        return cleaned

    def _validate_matrix_config(self, value: Any, label: str) -> Dict[str, Any]:
        """Validate and normalize a matrix_config payload (phase 6)."""
        if not isinstance(value, dict):
            raise FormTemplateAIError(f"Matrix '{label}': matrix_config object is required.")

        row_mode = str(value.get("row_mode") or "manual").strip().lower()
        if row_mode not in ("manual", "list_library"):
            raise FormTemplateAIError(
                f"Matrix '{label}': row_mode must be 'manual' or 'list_library'."
            )

        columns_in = value.get("columns")
        if not isinstance(columns_in, list) or not columns_in:
            raise FormTemplateAIError(f"Matrix '{label}': at least one column is required.")
        columns = []
        for c in columns_in:
            if not isinstance(c, dict) or not _clean_str(c.get("name"), 200):
                raise FormTemplateAIError(
                    f"Matrix '{label}': each column needs a 'name' (and optional 'type')."
                )
            col_type = str(c.get("type") or "number_whole").strip().lower()
            if col_type not in MATRIX_COLUMN_TYPES:
                raise FormTemplateAIError(
                    f"Matrix '{label}': column type '{col_type}' invalid. Allowed: {sorted(MATRIX_COLUMN_TYPES)}"
                )
            if col_type == "number":
                col_type = "number_whole"
            col_entry: Dict[str, Any] = {
                "name": _clean_str(c.get("name"), 200),
                "type": col_type,
            }
            if col_type == "number_decimal":
                try:
                    decimals = int(c.get("decimals", 2))
                except (TypeError, ValueError):
                    decimals = 2
                col_entry["decimals"] = min(max(decimals, 0), 6)
            name_translations = _normalize_name_translations(c.get("name_translations"))
            if not name_translations:
                fallback_label = _clean_str(c.get("label"), 500)
                if fallback_label:
                    name_translations = {"en": fallback_label}
            if name_translations:
                col_entry["name_translations"] = name_translations
            group = _clean_str(c.get("group"), 200)
            if group:
                col_entry["group"] = group
            columns.append(col_entry)

        config: Dict[str, Any] = {
            "type": "matrix",
            "row_mode": row_mode,
            "columns": columns,
            "show_row_totals": _as_bool(value.get("show_row_totals")),
            "show_column_totals": _as_bool(value.get("show_column_totals")),
        }

        if row_mode == "manual":
            rows_in = value.get("rows")
            if not isinstance(rows_in, list) or not rows_in:
                raise FormTemplateAIError(
                    f"Matrix '{label}': manual matrices require a non-empty 'rows' list."
                )
            rows = []
            for r in rows_in:
                if isinstance(r, dict):
                    text = _clean_str(r.get("text") or r.get("label"), 500)
                    row_translations = _normalize_name_translations(r.get("name_translations"))
                else:
                    text = _clean_str(r, 500)
                    row_translations = None
                if not text:
                    raise FormTemplateAIError(f"Matrix '{label}': every row needs text.")
                row_entry: Dict[str, Any] = {"text": text}
                if row_translations:
                    row_entry["name_translations"] = row_translations
                rows.append(row_entry)
            config["rows"] = rows
        else:
            lookup_list_id = value.get("lookup_list_id")
            if lookup_list_id is None or not str(lookup_list_id).strip():
                raise FormTemplateAIError(
                    f"Matrix '{label}': list_library matrices require lookup_list_id."
                )
            raw = str(lookup_list_id).strip()
            if raw.isdigit() and not LookupList.query.get(int(raw)):
                raise FormTemplateAIError(f"Matrix '{label}': lookup list {raw} does not exist.")
            config["lookup_list_id"] = int(raw) if raw.isdigit() else raw
            config["list_display_column"] = _clean_str(value.get("list_display_column"), 100) or "name"
            filters = value.get("list_filters")
            if filters is not None:
                if not isinstance(filters, list):
                    raise FormTemplateAIError(
                        f"Matrix '{label}': list_filters must be a list of "
                        "{column, operator, value} objects."
                    )
                config["list_filters"] = filters

        return config

    # ------------------------------------------------------------------
    # Edit operation handlers (called dynamically as _op_<name>)
    # ------------------------------------------------------------------

    def _op_update_template_settings(self, op, *, template, draft, ref_map, warnings, deferred_rules):
        changed = []
        if op.get("name") is not None:
            name = _clean_str(op.get("name"), 100)
            if not name:
                raise FormTemplateAIError("update_template_settings: 'name' cannot be empty.")
            draft.name = name
            changed.append(f"name='{name}'")
        if op.get("description") is not None:
            draft.description = _clean_str(op.get("description"), 4000)
            changed.append("description")
        for flag in ("is_paginated", "add_to_self_report", "display_order_visible"):
            if op.get(flag) is not None:
                setattr(draft, flag, _as_bool(op.get(flag)))
                changed.append(f"{flag}={_as_bool(op.get(flag))}")
        if not changed:
            return None
        return f"Updated template settings ({', '.join(changed)})"

    def _op_add_page(self, op, *, template, draft, ref_map, warnings, deferred_rules):
        page_schema = op.get("page")
        if not isinstance(page_schema, dict):
            raise FormTemplateAIError("add_page: 'page' object is required.")
        self._build_pages([page_schema], template, draft, ref_map, warnings)
        return f"Added page '{page_schema.get('name')}'"

    def _op_add_section(self, op, *, template, draft, ref_map, warnings, deferred_rules):
        section_schema = op.get("section")
        if not isinstance(section_schema, dict):
            raise FormTemplateAIError("add_section: 'section' object is required.")
        last = (
            FormSection.query.filter_by(version_id=draft.id, archived=False)
            .order_by(FormSection.order.desc())
            .first()
        )
        default_order = (last.order + 1) if last else 1.0
        section = self._create_section(
            section_schema, template, draft, ref_map, warnings,
            default_order=default_order, deferred_rules=deferred_rules,
        )
        items_schema = section_schema.get("items") or []
        if not isinstance(items_schema, list):
            raise FormTemplateAIError("add_section: 'items' must be a list.")
        if len(items_schema) > MAX_ITEMS_PER_CALL:
            raise FormTemplateAIError(f"Too many items (max {MAX_ITEMS_PER_CALL}).")
        for j, item_schema in enumerate(items_schema):
            self._create_item(
                item_schema, template, draft, section, ref_map, warnings,
                default_order=float(j + 1), deferred_rules=deferred_rules,
            )
        return f"Added section '{section.name}' with {len(items_schema)} item(s)"

    def _op_update_section(self, op, *, template, draft, ref_map, warnings, deferred_rules):
        section = self._resolve_section(op, draft, ref_map, "update_section")
        changed = []
        if op.get("section_type") is not None:
            section_type = str(op.get("section_type")).strip().lower()
            if section_type not in SECTION_TYPES:
                raise FormTemplateAIError(
                    f"update_section: invalid section_type '{section_type}'. "
                    f"Allowed: {sorted(SECTION_TYPES)}"
                )
            section.section_type = section_type
            changed.append(f"section_type={section_type}")
        if op.get("name") is not None:
            name = _clean_str(op.get("name"), 100)
            if not name:
                raise FormTemplateAIError("update_section: 'name' cannot be empty.")
            section.name = name
            changed.append(f"name='{name}'")
        if op.get("order") is not None:
            section.order = _as_float(op.get("order"), section.order)
            changed.append(f"order={section.order}")
        self._apply_section_config(section, op, warnings)
        if any(k in op for k in (
            "max_entries", "max_dynamic_indicators", "indicator_filters",
            "allowed_disaggregation_options", "allow_data_not_available",
            "allow_not_applicable", "add_indicator_note",
        )):
            changed.append("configuration")
        if not changed:
            return None
        return f"Updated section '{section.name}' ({', '.join(changed)})"

    def _op_remove_section(self, op, *, template, draft, ref_map, warnings, deferred_rules):
        section = self._resolve_section(op, draft, ref_map, "remove_section")
        name = section.name
        items = FormItem.query.filter_by(section_id=section.id).all()
        has_data = any(self._item_has_data(i) for i in items)
        if has_data:
            section.archived = True
            for i in items:
                i.archived = True
            warnings.append(
                f"Section '{name}' has submitted data and was archived instead of deleted."
            )
            return f"Archived section '{name}' ({len(items)} item(s))"
        for i in items:
            db.session.delete(i)
        db.session.delete(section)
        db.session.flush()
        return f"Removed section '{name}' ({len(items)} item(s))"

    def _op_add_item(self, op, *, template, draft, ref_map, warnings, deferred_rules):
        section = self._resolve_section(op, draft, ref_map, "add_item")
        item_schema = op.get("item")
        if not isinstance(item_schema, dict):
            raise FormTemplateAIError("add_item: 'item' object is required.")
        last = (
            FormItem.query.filter_by(section_id=section.id, archived=False)
            .order_by(FormItem.order.desc())
            .first()
        )
        default_order = (last.order + 1) if last else 1.0
        item = self._create_item(
            item_schema, template, draft, section, ref_map, warnings,
            default_order=default_order, deferred_rules=deferred_rules,
        )
        return f"Added {item.item_type} '{item.label}' to section '{section.name}'"

    def _op_update_item(self, op, *, template, draft, ref_map, warnings, deferred_rules):
        item = self._resolve_item(op, draft, ref_map, "update_item")
        changed = []

        if op.get("label") is not None:
            label = _clean_str(op.get("label"), 4000)
            if not label and not (item.is_question and item.type == "blank"):
                raise FormTemplateAIError("update_item: 'label' cannot be empty.")
            item.label = label or ""
            changed.append("label")
        if op.get("definition") is not None and item.is_question:
            item.definition = _clean_str(op.get("definition"), 4000) or ""
            changed.append("definition")
        if op.get("description") is not None and item.is_document_field:
            item.description = _clean_str(op.get("description"), 4000) or ""
            changed.append("description")
        if op.get("order") is not None:
            item.order = _as_float(op.get("order"), item.order)
            changed.append(f"order={item.order}")

        config = dict(item.config or {})
        config_changed = False
        if op.get("is_required") is not None:
            config["is_required"] = _as_bool(op.get("is_required"))
            changed.append(f"is_required={config['is_required']}")
            config_changed = True
        for flag in ("allow_data_not_available", "allow_not_applicable", "layout_break_after"):
            if op.get(flag) is not None:
                config[flag] = _as_bool(op.get(flag))
                changed.append(flag)
                config_changed = True
        if op.get("layout_column_width") is not None:
            config["layout_column_width"] = min(12, max(1, _as_int(op.get("layout_column_width"), 12)))
            changed.append("layout_column_width")
            config_changed = True
        if op.get("max_documents") is not None and item.is_document_field:
            config["max_documents"] = _as_int(op.get("max_documents"))
            changed.append("max_documents")
            config_changed = True
        if op.get("matrix_config") is not None and item.is_matrix:
            config["matrix_config"] = self._validate_matrix_config(op.get("matrix_config"), item.label)
            changed.append("matrix_config")
            config_changed = True

        if op.get("question_type") is not None and item.is_question:
            question_type = str(op.get("question_type")).strip().lower()
            if question_type not in QUESTION_TYPES:
                raise FormTemplateAIError(
                    f"update_item: invalid question_type '{question_type}'."
                )
            item.type = question_type
            changed.append(f"question_type={question_type}")

        if (op.get("options") is not None or op.get("lookup_list_id") is not None) and item.is_question:
            self._apply_question_options(item, op, item.type, warnings)
            changed.append("options")

        if op.get("indicator_bank_id") is not None and item.is_indicator:
            self._apply_indicator_fields(item, op, config, warnings)
            changed.append("indicator_bank_id")
            config_changed = True

        if op.get("allowed_disaggregation_options") is not None and item.is_indicator:
            config["allowed_disaggregation_options"] = self._validate_disagg_options(
                op.get("allowed_disaggregation_options"), f"Item '{item.label}'"
            )
            changed.append("allowed_disaggregation_options")
            config_changed = True

        if op.get("validation_message") is not None:
            item.validation_message = _clean_str(op.get("validation_message"), 2000)
            changed.append("validation_message")

        if config_changed:
            item.config = config

        if op.get("relevance") is not None:
            deferred_rules.append(
                {"kind": "item_relevance", "item_id": item.id, "rule": op.get("relevance")}
            )
            changed.append("relevance")
        if op.get("validation") is not None:
            deferred_rules.append(
                {
                    "kind": "item_validation",
                    "item_id": item.id,
                    "rule": op.get("validation"),
                    "message": _clean_str(op.get("validation_message"), 2000) or item.validation_message,
                }
            )
            changed.append("validation")

        if not changed:
            return None
        return f"Updated {item.item_type} '{item.label}' ({', '.join(changed)})"

    def _op_remove_item(self, op, *, template, draft, ref_map, warnings, deferred_rules):
        item = self._resolve_item(op, draft, ref_map, "remove_item")
        label, item_type = item.label, item.item_type
        if self._item_has_data(item):
            item.archived = True
            warnings.append(
                f"Item '{label}' has submitted data and was archived instead of deleted."
            )
            return f"Archived {item_type} '{label}'"
        db.session.delete(item)
        db.session.flush()
        return f"Removed {item_type} '{label}'"

    def _op_set_relevance(self, op, *, template, draft, ref_map, warnings, deferred_rules):
        rule = op.get("rule")
        if op.get("section_id") is not None or op.get("section_ref") is not None:
            section = self._resolve_section(op, draft, ref_map, "set_relevance")
            deferred_rules.append(
                {"kind": "section_relevance", "section_id": section.id, "rule": rule}
            )
            return f"Set skip logic on section '{section.name}'" if rule else (
                f"Cleared skip logic on section '{section.name}'"
            )
        item = self._resolve_item(op, draft, ref_map, "set_relevance")
        deferred_rules.append({"kind": "item_relevance", "item_id": item.id, "rule": rule})
        return f"Set skip logic on '{item.label}'" if rule else f"Cleared skip logic on '{item.label}'"

    def _op_set_validation(self, op, *, template, draft, ref_map, warnings, deferred_rules):
        item = self._resolve_item(op, draft, ref_map, "set_validation")
        rule = op.get("rule")
        message = _clean_str(op.get("message") or op.get("validation_message"), 2000)
        deferred_rules.append(
            {"kind": "item_validation", "item_id": item.id, "rule": rule, "message": message}
        )
        return f"Set validation rule on '{item.label}'" if rule else (
            f"Cleared validation rule on '{item.label}'"
        )

    # ------------------------------------------------------------------
    # Entity resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _register_ref(ref_map: Dict[str, Tuple[str, int]], ref: Any, kind: str, obj_id: int) -> None:
        if ref is None:
            return
        key = str(ref).strip()
        if not key:
            return
        if key in ref_map:
            raise FormTemplateAIError(f"Duplicate ref '{key}' — refs must be unique within a call.")
        ref_map[key] = (kind, int(obj_id))

    @staticmethod
    def _resolve_ref(
        ref_map: Dict[str, Tuple[str, int]], ref: Any, expected_kind: str, owner: str
    ) -> int:
        key = str(ref or "").strip()
        entry = ref_map.get(key)
        if not entry:
            raise FormTemplateAIError(f"{owner}: unknown ref '{key}'.")
        kind, obj_id = entry
        if kind != expected_kind:
            raise FormTemplateAIError(
                f"{owner}: ref '{key}' is a {kind}, expected a {expected_kind}."
            )
        return obj_id

    @staticmethod
    def _map_entity_id_to_draft_version(model, entity_id: Optional[int], draft: FormTemplateVersion):
        """Map an id from another version of the same template onto the draft clone."""
        if not entity_id:
            return None
        in_draft = model.query.filter_by(id=int(entity_id), version_id=draft.id).first()
        if in_draft:
            return in_draft
        source = model.query.filter_by(id=int(entity_id), template_id=draft.template_id).first()
        if not source or source.version_id == draft.id:
            return None

        stable_key = getattr(source, "stable_key", None)
        if stable_key:
            mapped = model.query.filter_by(
                template_id=draft.template_id,
                version_id=draft.id,
                stable_key=stable_key,
            ).first()
            if mapped:
                return mapped

        if model is FormSection:
            query = FormSection.query.filter_by(
                template_id=draft.template_id,
                version_id=draft.id,
                name=source.name,
                order=source.order,
            )
            if hasattr(source, "archived"):
                query = query.filter_by(archived=getattr(source, "archived", False))
            return query.first()

        if model is FormPage:
            return FormPage.query.filter_by(
                template_id=draft.template_id,
                version_id=draft.id,
                name=source.name,
                order=source.order,
            ).first()

        if model is FormItem:
            draft_section = FormTemplateAIService._map_entity_id_to_draft_version(
                FormSection, source.section_id, draft
            )
            query = FormItem.query.filter_by(
                template_id=draft.template_id,
                version_id=draft.id,
                label=source.label,
                order=source.order,
            )
            if draft_section:
                query = query.filter_by(section_id=draft_section.id)
            if hasattr(source, "archived"):
                query = query.filter_by(archived=getattr(source, "archived", False))
            return query.first()

        return None

    @staticmethod
    def _validate_page_id(page_id: Optional[int], template, draft, owner: str) -> int:
        page = FormPage.query.filter_by(id=page_id or 0, version_id=draft.id).first()
        if not page:
            page = FormTemplateAIService._map_entity_id_to_draft_version(
                FormPage, page_id, draft
            )
        if not page:
            raise FormTemplateAIError(f"Section '{owner}': page {page_id} not found in this draft.")
        return page.id

    @staticmethod
    def _validate_section_id(section_id: Optional[int], draft, owner: str) -> FormSection:
        section = FormSection.query.filter_by(id=section_id or 0, version_id=draft.id).first()
        if not section:
            section = FormTemplateAIService._map_entity_id_to_draft_version(
                FormSection, section_id, draft
            )
        if not section:
            raise FormTemplateAIError(
                f"{owner}: section {section_id} not found in the draft version "
                f"(version_id={draft.id}). Read the structure first — section IDs differ between versions."
            )
        return section

    def _resolve_section(self, op: Dict[str, Any], draft, ref_map, op_name: str) -> FormSection:
        if op.get("section_ref"):
            section_id = self._resolve_ref(ref_map, op.get("section_ref"), "section", op_name)
            return self._validate_section_id(section_id, draft, op_name)
        section_id = _as_int(op.get("section_id"))
        if not section_id:
            raise FormTemplateAIError(f"{op_name}: 'section_id' (or 'section_ref') is required.")
        return self._validate_section_id(section_id, draft, op_name)

    def _resolve_item(self, op: Dict[str, Any], draft, ref_map, op_name: str) -> FormItem:
        if op.get("item_ref"):
            item_id = self._resolve_ref(ref_map, op.get("item_ref"), "item", op_name)
        else:
            item_id = _as_int(op.get("item_id"))
            if not item_id:
                raise FormTemplateAIError(f"{op_name}: 'item_id' (or 'item_ref') is required.")
        item = FormItem.query.filter_by(id=item_id, version_id=draft.id).first()
        if not item:
            item = self._map_entity_id_to_draft_version(FormItem, item_id, draft)
        if not item:
            raise FormTemplateAIError(
                f"{op_name}: item {item_id} not found in the draft version "
                f"(version_id={draft.id}). Read the structure first — item IDs differ between versions."
            )
        return item

    @staticmethod
    def _item_has_data(item: FormItem) -> bool:
        try:
            if item.data_entries.first() is not None:
                return True
            if item.repeat_data_entries.first() is not None:
                return True
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("_item_has_data check failed for item %s: %s", item.id, exc)
            return True
        return False

    # ------------------------------------------------------------------
    # Rules (phase 2): skip logic + validation conditions
    # ------------------------------------------------------------------

    def _apply_deferred_rules(
        self,
        draft: FormTemplateVersion,
        ref_map: Dict[str, Tuple[str, int]],
        deferred_rules: List[Dict[str, Any]],
        warnings: List[str],
    ) -> None:
        """Apply rules after all entities exist, so refs can point at new items."""
        for entry in deferred_rules:
            kind = entry["kind"]
            rule = entry.get("rule")
            serialized = (
                self._normalize_rule(rule, draft, ref_map) if rule is not None else None
            )

            if kind == "section_relevance":
                section = FormSection.query.get(entry["section_id"])
                section.relevance_condition = serialized
            elif kind == "item_relevance":
                item = FormItem.query.get(entry["item_id"])
                item.relevance_condition = serialized
            elif kind == "item_validation":
                item = FormItem.query.get(entry["item_id"])
                item.validation_condition = serialized
                if serialized:
                    message = entry.get("message") or item.validation_message
                    if not message:
                        raise FormTemplateAIError(
                            f"Item '{item.label}': a validation rule requires a "
                            "'validation_message' explaining the rule to the user."
                        )
                    item.validation_message = message
        db.session.flush()

    def _normalize_rule(
        self,
        rule: Any,
        draft: FormTemplateVersion,
        ref_map: Dict[str, Tuple[str, int]],
    ) -> str:
        """
        Normalize an AI-provided rule into the stored JSON string format:
        {"logic": "AND", "conditions": [{"item_id": "66", "condition_type": "...",
        "value": "..."} | {..., "value_field_id": 18}]}
        """
        if not isinstance(rule, dict):
            raise FormTemplateAIError("Rules must be objects with 'logic' and 'conditions'.")
        logic = str(rule.get("logic") or "AND").strip().upper()
        if logic not in ("AND", "OR"):
            raise FormTemplateAIError("Rule 'logic' must be 'AND' or 'OR'.")
        conditions_in = rule.get("conditions")
        if not isinstance(conditions_in, list) or not conditions_in:
            raise FormTemplateAIError("Rule 'conditions' must be a non-empty list.")

        conditions_out = []
        for i, cond in enumerate(conditions_in):
            if not isinstance(cond, dict):
                raise FormTemplateAIError(f"Rule condition #{i + 1} must be an object.")
            target_item = self._resolve_rule_target(
                cond.get("item") if cond.get("item") is not None else cond.get("item_id"),
                draft, ref_map, f"Rule condition #{i + 1}",
            )
            condition_type = str(cond.get("condition_type") or "").strip()
            allowed = self._allowed_condition_types(target_item)
            if condition_type not in allowed:
                raise FormTemplateAIError(
                    f"Rule condition #{i + 1}: condition_type '{condition_type}' is not valid "
                    f"for '{target_item.label}' ({self._target_type_name(target_item)}). "
                    f"Allowed: {sorted(allowed)}"
                )

            out: Dict[str, Any] = {
                "item_id": str(target_item.id),
                "condition_type": condition_type,
            }
            value_item = cond.get("value_item") if cond.get("value_item") is not None else cond.get("value_field_id")
            if condition_type in _VALUELESS_CONDITIONS:
                out["value"] = ""
            elif value_item is not None:
                value_target = self._resolve_rule_target(
                    value_item, draft, ref_map, f"Rule condition #{i + 1} value_item"
                )
                out["value_field_id"] = int(value_target.id)
            else:
                value = cond.get("value")
                if value is None or (isinstance(value, str) and not value.strip()):
                    raise FormTemplateAIError(
                        f"Rule condition #{i + 1}: '{condition_type}' requires a 'value' "
                        "(or a 'value_item' field reference)."
                    )
                out["value"] = str(value).strip()
            conditions_out.append(out)

        return json.dumps({"logic": logic, "conditions": conditions_out})

    def _resolve_rule_target(
        self,
        target: Any,
        draft: FormTemplateVersion,
        ref_map: Dict[str, Tuple[str, int]],
        owner: str,
    ) -> FormItem:
        if target is None:
            raise FormTemplateAIError(f"{owner}: 'item' (id or ref) is required.")
        item_id = _as_int(target)
        if item_id is None:
            item_id = self._resolve_ref(ref_map, target, "item", owner)
        item = FormItem.query.filter_by(id=item_id, version_id=draft.id).first()
        if not item:
            item = self._map_entity_id_to_draft_version(FormItem, item_id, draft)
        if not item:
            raise FormTemplateAIError(
                f"{owner}: item {target!r} not found in the draft version."
            )
        return item

    @staticmethod
    def _target_type_name(item: FormItem) -> str:
        if item.is_question:
            return item.type or "text"
        if item.is_indicator:
            return "indicator"
        if item.is_document_field:
            return "document_field"
        return "matrix"

    @classmethod
    def _allowed_condition_types(cls, item: FormItem) -> set:
        return CONDITION_TYPES_BY_TARGET.get(
            cls._target_type_name(item), _EMPTYNESS_CONDITIONS
        )

    # ------------------------------------------------------------------
    # Change log (phase 7)
    # ------------------------------------------------------------------

    @staticmethod
    def _append_change_log(draft: FormTemplateVersion, summary: str) -> None:
        """Append an AI change summary to the draft comment so reviewers see it at deploy."""
        stamp = utcnow().strftime("%Y-%m-%d %H:%M UTC")
        line = f"[AI {stamp}] {summary}"
        existing = (draft.comment or "").strip()
        combined = f"{existing}\n{line}".strip() if existing else line
        # Keep the comment bounded: drop oldest lines when too long.
        max_len = 8000
        if len(combined) > max_len:
            lines = combined.splitlines()
            while lines and len("\n".join(lines)) > max_len:
                lines.pop(0)
            combined = "\n".join(lines)
        draft.comment = combined
