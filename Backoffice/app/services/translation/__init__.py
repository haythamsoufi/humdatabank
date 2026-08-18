"""Translation services package.

Provides automatic and IFRC translation capabilities for the platform.
Migrated from app.utils.auto_translator. The IFRC Translation API client lives
directly in auto_translator.py (there is no separate standalone IFRC service
module — a legacy duplicate under this name was removed as dead code).
"""

from .auto_translator import (
    AutoTranslator,
    TranslationService,
    GoogleTranslateService,
    LibreTranslateService,
    IFRCTranslationService,
    auto_translator,
    get_auto_translator,
    translate_text,
    translate_form_item_auto,
    translate_section_name_auto,
    translate_question_option_auto,
    translate_page_name_auto,
    translate_template_name_auto,
)

__all__ = [
    "AutoTranslator",
    "TranslationService",
    "GoogleTranslateService",
    "LibreTranslateService",
    "IFRCTranslationService",
    "auto_translator",
    "get_auto_translator",
    "translate_text",
    "translate_form_item_auto",
    "translate_section_name_auto",
    "translate_question_option_auto",
    "translate_page_name_auto",
    "translate_template_name_auto",
]
