"""
OpenAI tool specifications for the form-builder assistant tools.

These tools are only exposed when the chat request originates from the
form-builder AI panel (``page_context.formBuilder``) AND the user holds the
matching ``admin.templates.*`` RBAC permissions. See
``AIToolsRegistry.get_tool_definitions_openai``.
"""

from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Shared sub-schemas (inlined into each tool definition)
# ---------------------------------------------------------------------------

_RULE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "description": (
        "Condition rule (skip logic / validation). Conditions reference other items by "
        "numeric item id (existing items — read the structure first) or by 'ref' of an item "
        "created in the same call. Allowed condition_type values depend on the TARGET item: "
        "number/percentage/date/datetime/indicator: equal_to, not_equal_to, greater_than, "
        "greater_than_or_equal_to, less_than, less_than_or_equal_to, is_empty, is_not_empty; "
        "text/textarea/single_choice: equal_to, not_equal_to, is_empty, is_not_empty; "
        "yesno: is_yes, is_no, is_empty, is_not_empty; "
        "multiple_choice: contains, not_contains, is_empty, is_not_empty; "
        "document_field/matrix: is_empty, is_not_empty."
    ),
    "properties": {
        "logic": {"type": "string", "enum": ["AND", "OR"], "default": "AND"},
        "conditions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item": {
                        "type": ["string", "integer"],
                        "description": "Target item: numeric item id, or the 'ref' of an item created in this call.",
                    },
                    "condition_type": {"type": "string"},
                    "value": {
                        "type": "string",
                        "description": "Comparison value (omit for is_yes/is_no/is_empty/is_not_empty).",
                    },
                    "value_item": {
                        "type": ["string", "integer"],
                        "description": "Optional: compare against another item's value (id or ref) instead of a static value.",
                    },
                },
                "required": ["item", "condition_type"],
            },
        },
    },
    "required": ["conditions"],
}

_ITEM_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "description": "A form field. item_type decides which other properties apply.",
    "properties": {
        "ref": {
            "type": "string",
            "description": "Optional unique reference (e.g. 'q_sector') so rules/operations in this call can target this item.",
        },
        "item_type": {
            "type": "string",
            "enum": ["question", "indicator", "document_field", "matrix"],
        },
        "label": {"type": "string", "description": "Field label shown to the user."},
        "order": {"type": "number", "description": "Display order (defaults to position)."},
        "is_required": {"type": "boolean", "default": False},
        "question_type": {
            "type": "string",
            "enum": [
                "text", "textarea", "number", "percentage", "yesno",
                "single_choice", "multiple_choice", "date", "datetime", "blank",
            ],
            "description": "Required for item_type=question.",
        },
        "definition": {
            "type": "string",
            "description": (
                "Help text shown beneath the field label — e.g. instructions, examples, guidance, "
                "SharePoint links, or ROI formulas visible in the source form. Always populate this "
                "instead of embedding instructions inside the label. Never leave useful guidance text "
                "out of the form just because it was below the label in the source."
            ),
        },
        "options": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Manual choices for single_choice/multiple_choice questions.",
        },
        "lookup_list_id": {
            "type": ["string", "integer"],
            "description": (
                "Calculated choices source instead of manual options: a numeric lookup list id, or a "
                "system list: 'country_map' (countries), 'national_society', 'indicator_bank'. "
                "Prefer system lists when the user asks for e.g. a country dropdown."
            ),
        },
        "list_display_column": {"type": "string", "description": "Column of the lookup list to display (default 'name')."},
        "list_filters": {
            "type": "array",
            "items": {"type": "object"},
            "description": "Optional lookup list filters, e.g. [{\"field\": \"region\", \"op\": \"eq\", \"value\": \"Africa\"}].",
        },
        "indicator_bank_id": {
            "type": "integer",
            "description": (
                "Required for item_type=indicator: the Indicator Bank id. Resolve it first with "
                "search_indicator_bank — never invent ids."
            ),
        },
        "allowed_disaggregation_options": {
            "type": "array",
            "items": {"type": "string", "enum": ["total", "sex", "age", "sex_age", "disability"]},
            "description": "Indicator disaggregations (default ['total']).",
        },
        "allow_data_not_available": {"type": "boolean"},
        "allow_not_applicable": {"type": "boolean"},
        "show_hint": {
            "type": "boolean",
            "description": (
                "When true, shows a highlighted guidance note below the field label in the entry form."
            ),
        },
        "hint_text": {
            "type": "string",
            "description": "Custom entry form hint text (optional when show_hint is true).",
        },
        "hint_text_translations": {
            "type": "object",
            "description": "Localized hint text, e.g. {en: '...', fr: '...'}.",
        },
        "hint_style": {
            "type": "string",
            "enum": ["normal", "info", "warning", "tip", "important"],
            "description": (
                "Visual style for the entry form hint callout (default warning)."
            ),
        },
        "description": {"type": "string", "description": "Help text for document_field items."},
        "max_documents": {"type": "integer", "description": "Max uploads for document_field items."},
        "matrix_config": {
            "type": "object",
            "description": (
                "Required for item_type=matrix. {row_mode: 'manual'|'list_library', "
                "columns: [{name (stable code/slug), type: 'number_whole'|'number_decimal'|'tick', "
                "decimals (int, only for number_decimal, default 2), "
                "name_translations: {en: 'Column label', ...}, optional group}], "
                "rows: [{text, name_translations?}] (manual mode), "
                "lookup_list_id + list_display_column (list_library mode), "
                "show_row_totals, show_column_totals}."
            ),
        },
        "relevance": {**_RULE_SCHEMA, "description": "Skip logic: show this field only when the rule passes."},
        "validation": {**_RULE_SCHEMA, "description": "Validation rule that must pass on submitted data."},
        "validation_message": {
            "type": "string",
            "description": "User-facing message when validation fails (required when 'validation' is set).",
        },
    },
    "required": ["item_type", "label"],
}

_SECTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "ref": {"type": "string", "description": "Optional unique reference for this section."},
        "name": {"type": "string"},
        "order": {"type": "number"},
        "section_type": {
            "type": "string",
            "enum": ["standard", "repeat", "dynamic_indicators", "discussion"],
            "default": "standard",
            "description": (
                "'repeat' = repeating group (set max_entries); 'dynamic_indicators' = data-entry users pick "
                "indicators themselves (set indicator_filters / max_dynamic_indicators); "
                "'discussion' = comment thread section (at most one per template version; requires enable_discussion; add from template details, not the section modal)."
            ),
        },
        "page_ref": {"type": "string", "description": "Page ref this section belongs to (paginated templates)."},
        "parent_ref": {"type": "string", "description": "Parent section ref to create this as a sub-section."},
        "max_entries": {"type": "integer", "description": "Repeat sections: max instances (omit for unlimited)."},
        "max_dynamic_indicators": {"type": "integer"},
        "indicator_filters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string", "description": "e.g. 'sector', 'subsector', 'type', 'emergency'"},
                    "values": {"type": "array", "items": {"type": "string"}},
                    "primary_only": {"type": "boolean"},
                },
                "required": ["field", "values"],
            },
            "description": "Dynamic sections: which Indicator Bank rows users may add.",
        },
        "allowed_disaggregation_options": {
            "type": "array",
            "items": {"type": "string", "enum": ["total", "sex", "age", "sex_age", "disability"]},
        },
        "add_indicator_note": {"type": "string"},
        "relevance": {**_RULE_SCHEMA, "description": "Skip logic: show this section only when the rule passes."},
        "items": {"type": "array", "items": _ITEM_SCHEMA},
    },
    "required": ["name"],
}

_OPERATION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "description": (
        "One edit operation. 'op' decides which other properties apply:\n"
        "- update_template_settings: name, description, is_paginated\n"
        "- add_page: page {ref, name, order}\n"
        "- add_section: section (full section object incl. items)\n"
        "- update_section: section_id (or section_ref), then any of name, order, section_type, "
        "max_entries, max_dynamic_indicators, indicator_filters, allowed_disaggregation_options\n"
        "- remove_section: section_id (archives instead of deleting when data exists)\n"
        "- add_item: section_id (or section_ref) + item (full item object)\n"
        "- update_item: item_id (or item_ref), then any of label, definition, description, order, "
        "is_required, question_type, options, lookup_list_id, indicator_bank_id, "
        "allowed_disaggregation_options, max_documents, matrix_config, validation_message\n"
        "- remove_item: item_id (archives instead of deleting when data exists)\n"
        "- set_relevance: item_id OR section_id + rule (null rule clears the skip logic)\n"
        "- set_validation: item_id + rule + message (null rule clears the validation)"
    ),
    "properties": {
        "op": {
            "type": "string",
            "enum": [
                "update_template_settings", "add_page", "add_section", "update_section",
                "remove_section", "add_item", "update_item", "remove_item",
                "set_relevance", "set_validation",
            ],
        },
        "page": {"type": "object"},
        "section": _SECTION_SCHEMA,
        "item": _ITEM_SCHEMA,
        "section_id": {"type": "integer"},
        "section_ref": {"type": "string"},
        "item_id": {"type": "integer"},
        "item_ref": {"type": "string"},
        "name": {"type": "string"},
        "description": {"type": "string"},
        "is_paginated": {"type": "boolean"},
        "order": {"type": "number"},
        "section_type": {
            "type": "string",
            "enum": ["standard", "repeat", "dynamic_indicators", "discussion"],
        },
        "label": {"type": "string"},
        "definition": {"type": "string"},
        "is_required": {"type": "boolean"},
        "question_type": {"type": "string"},
        "options": {"type": "array", "items": {"type": "string"}},
        "lookup_list_id": {"type": ["string", "integer"]},
        "list_display_column": {"type": "string"},
        "list_filters": {"type": "array", "items": {"type": "object"}},
        "indicator_bank_id": {"type": "integer"},
        "allowed_disaggregation_options": {"type": "array", "items": {"type": "string"}},
        "max_entries": {"type": "integer"},
        "max_dynamic_indicators": {"type": "integer"},
        "indicator_filters": {"type": "array", "items": {"type": "object"}},
        "max_documents": {"type": "integer"},
        "matrix_config": {"type": "object"},
        "rule": {**_RULE_SCHEMA, "description": "The rule for set_relevance/set_validation (null to clear)."},
        "message": {"type": "string", "description": "Validation message for set_validation."},
        "validation_message": {"type": "string"},
        "relevance": _RULE_SCHEMA,
        "validation": _RULE_SCHEMA,
    },
    "required": ["op"],
}


FORM_TEMPLATE_TOOL_SPECS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_form_template_full_structure",
            "description": (
                "Read the FULL structure of a form template (pages, sections, items with ids, "
                "types, options, rules). ALWAYS call this before editing an existing template so "
                "you use real section/item ids from the draft version. Defaults to the draft "
                "version when one exists."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "template_id": {"type": "integer", "description": "Form template id."},
                    "version_id": {
                        "type": "integer",
                        "description": "Optional specific version id (default: draft, else published).",
                    },
                },
                "required": ["template_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_form_template",
            "description": (
                "Create a NEW form template from a structured schema. The template is created as a "
                "DRAFT — it is never published automatically; the user reviews and deploys it in the "
                "form builder. For indicator items, resolve indicator_bank_id with search_indicator_bank "
                "first. Returns created ids, a ref->id map, warnings, and the edit_url."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Template name (max 100 chars)."},
                    "description": {"type": "string"},
                    "is_paginated": {"type": "boolean", "default": False},
                    "pages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "ref": {"type": "string"},
                                "name": {"type": "string"},
                                "order": {"type": "integer"},
                            },
                            "required": ["name"],
                        },
                        "description": "Only for paginated templates.",
                    },
                    "sections": {"type": "array", "items": _SECTION_SCHEMA},
                },
                "required": ["name", "sections"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_form_template",
            "description": (
                "Apply a list of edit operations to a form template. All changes go to the DRAFT "
                "version (auto-created from the published version when needed) — nothing is "
                "published automatically. ALWAYS call get_form_template_full_structure first to get "
                "real ids. Returns changes, refs, and warnings (if any). Do not repeat the result "
                "\"note\" field or draft/deploy reminders in the user-facing answer."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "template_id": {"type": "integer"},
                    "operations": {"type": "array", "items": _OPERATION_SCHEMA},
                },
                "required": ["template_id", "operations"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "translate_form_template",
            "description": (
                "Machine-translate all template content (labels, definitions, options, section/page/"
                "template names) of the DRAFT version into the requested languages using the "
                "platform translation service. By default only fills missing translations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "template_id": {"type": "integer"},
                    "languages": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Target language codes (e.g. ['fr', 'es', 'ar']). English is the source.",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["untranslated", "overwrite"],
                        "default": "untranslated",
                        "description": "'untranslated' fills gaps only; 'overwrite' replaces existing translations.",
                    },
                },
                "required": ["template_id", "languages"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "discard_template_draft",
            "description": (
                "DESTRUCTIVE: delete the template's draft version and all its draft-only changes, "
                "reverting to the published version. Call ONLY when the user explicitly asks to "
                "undo/discard the draft. Never call this on your own initiative."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "template_id": {"type": "integer"},
                },
                "required": ["template_id"],
            },
        },
    },
]

FORM_TEMPLATE_TOOL_NAMES = frozenset(
    {
        "get_form_template_full_structure",
        "create_form_template",
        "edit_form_template",
        "translate_form_template",
        "discard_template_draft",
    }
)

# Write tools require edit/create permission; the read tool only needs view.
FORM_TEMPLATE_WRITE_TOOLS = frozenset(
    {
        "create_form_template",
        "edit_form_template",
        "translate_form_template",
        "discard_template_draft",
    }
)
