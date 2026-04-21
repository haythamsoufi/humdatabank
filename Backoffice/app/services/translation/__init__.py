"""Translation services package.

Provides automatic and IFRC-specific translation capabilities for the platform.
Migrated from app.utils.auto_translator and app.utils.ifrc_translation_service.
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
from .ifrc_service import (
    IFRCTranslationService as IFRCTranslationServiceStandalone,
    create_ifrc_translation_service,
    translate_with_ifrc,
    translate_batch_with_ifrc,
    test_ifrc_api_connection,
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
    "IFRCTranslationServiceStandalone",
    "create_ifrc_translation_service",
    "translate_with_ifrc",
    "translate_batch_with_ifrc",
    "test_ifrc_api_connection",
]
