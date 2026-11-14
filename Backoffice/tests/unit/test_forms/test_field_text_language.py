"""Language detection for the entry-form translation preview badge."""

from app.services.forms.field_text_language import (
    detect_field_text_language,
    translation_preview_decision,
)


ARABIC = "تم تأجيل التوزيع بسبب الفيضانات في المنطقة"
ENGLISH = "The distribution was delayed because of flooding in the area."
FRENCH = "La distribution a été retardée à cause des inondations dans la région."
SPANISH = "La distribución fue retrasada por las inundaciones en la región."
RUSSIAN = "Распределение было отложено из-за наводнения в этом районе."
CHINESE = "由于该地区发生洪水，分发工作被推迟了。"


def test_empty_and_names_are_not_badged():
    assert detect_field_text_language("") == (None, 0.0)
    assert detect_field_text_language("OK")[0] is None
    assert detect_field_text_language("Amman clinic")[0] is None
    assert translation_preview_decision("Jean Dupont", "en")["offer"] is False


def test_arabic_offers_a_preview_only_when_the_display_language_differs():
    detected, confidence = detect_field_text_language(ARABIC)
    assert detected == "ar"
    assert confidence >= 0.9
    assert translation_preview_decision(ARABIC, "en")["offer"] is True
    assert translation_preview_decision(ARABIC, "ar")["offer"] is False
    assert translation_preview_decision(ARABIC, "ar-SA")["offer"] is False


def test_latin_sentences_follow_the_display_language():
    assert detect_field_text_language(ENGLISH)[0] == "en"
    assert detect_field_text_language(FRENCH)[0] == "fr"
    assert detect_field_text_language(SPANISH)[0] == "es"

    assert translation_preview_decision(ENGLISH, "fr")["offer"] is True
    assert translation_preview_decision(ENGLISH, "en")["offer"] is False
    assert translation_preview_decision(FRENCH, "en")["offer"] is True
    assert translation_preview_decision(FRENCH, "fr")["offer"] is False
    assert translation_preview_decision(SPANISH, "en")["offer"] is True


def test_non_latin_scripts():
    assert detect_field_text_language(RUSSIAN)[0] == "ru"
    assert detect_field_text_language(CHINESE)[0] == "zh"
    assert detect_field_text_language("वितरण बाढ़ के कारण स्थगित कर दिया गया")[0] == "hi"
    assert translation_preview_decision(RUSSIAN, "en")["offer"] is True
    assert translation_preview_decision("वितरण बाढ़ के कारण स्थगित कर दिया गया", "hi")["offer"] is False
