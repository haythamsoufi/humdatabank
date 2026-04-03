import pytest


@pytest.mark.unit
def test_normalize_chatbot_language_defaults_to_en():
    from app.routes.chatbot import normalize_chatbot_language

    assert normalize_chatbot_language(None) == "en"
    assert normalize_chatbot_language("") == "en"
    assert normalize_chatbot_language("   ") == "en"
    assert normalize_chatbot_language(123) == "en"


@pytest.mark.unit
def test_normalize_chatbot_language_normalizes_region_and_case():
    from app.routes.chatbot import normalize_chatbot_language

    assert normalize_chatbot_language("fr_FR") == "fr"
    assert normalize_chatbot_language("FR") == "fr"
    assert normalize_chatbot_language("ar") == "ar"


@pytest.mark.unit
def test_normalize_chatbot_language_unknown_falls_back_to_en():
    from app.routes.chatbot import normalize_chatbot_language

    assert normalize_chatbot_language("xx") == "en"

