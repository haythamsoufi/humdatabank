from app.utils.jsonb_text import text_from_jsonb_item, text_list_from_jsonb


def test_text_from_jsonb_item_string():
    assert text_from_jsonb_item("  hello  ") == "hello"


def test_text_from_jsonb_item_dict():
    assert text_from_jsonb_item({"text": "Q1"}) == "Q1"
    assert text_from_jsonb_item({"question": "Q2"}) == "Q2"


def test_text_list_from_jsonb_mixed():
    items = ["plain", {"text": "dict"}, {"text": "plain"}, ""]
    assert text_list_from_jsonb(items) == ["plain", "dict"]
