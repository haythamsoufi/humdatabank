"""Entry-form translation preview is a read-only lookup."""

from __future__ import annotations

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]

URL = "/forms/api/field-text-translation-preview"
ARABIC = "تم تأجيل التوزيع بسبب الفيضانات في المنطقة"
ENGLISH = "The distribution was delayed because of flooding in the area."


def _login(client, user_id, language="en"):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
        sess["language"] = language


def _post(client, payload):
    return client.post(
        URL,
        data=json.dumps(payload),
        headers={"Content-Type": "application/json", "X-CSRFToken": "test"},
    )


def test_anonymous_request_is_rejected(client):
    response = _post(client, {"text": ARABIC})
    assert response.status_code in (302, 401)


def test_user_without_a_form_cannot_preview(client, test_user):
    _login(client, test_user.id)
    with patch("app.services.translation.auto_translator.get_auto_translator") as translator:
        response = _post(client, {"text": ARABIC})
    assert response.status_code == 403
    translator.assert_not_called()


def test_unknown_assignment_is_hidden(client, test_user):
    _login(client, test_user.id)
    response = _post(client, {"text": ARABIC, "assignment_entity_status_id": 999999})
    assert response.status_code == 404


def test_preview_translates_without_asking_the_client_to_replace_the_value(client, admin_user):
    _login(client, admin_user.id)
    translator = MagicMock()
    translator.translate_text.return_value = "The distribution was delayed"
    with patch("app.routes.forms.field_translation.get_locale", return_value="en"), \
         patch("app.services.translation.auto_translator.get_auto_translator", return_value=translator):
        response = _post(client, {"text": ARABIC})

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["preview_only"] is True
    assert data["show_preview"] is True
    assert data["detected_language"] == "ar"
    assert data["target_language"] == "en"
    assert data["translation"] == "The distribution was delayed"
    assert "value" not in data
    assert "replace" not in data
    translator.translate_text.assert_called_once_with(ARABIC, "en", "ar")


def test_base64_text_is_accepted(client, admin_user):
    _login(client, admin_user.id)
    encoded = base64.b64encode(ARABIC.encode("utf-8")).decode("ascii")
    translator = MagicMock()
    translator.translate_text.return_value = "Delayed"
    with patch("app.routes.forms.field_translation.get_locale", return_value="fr"), \
         patch("app.services.translation.auto_translator.get_auto_translator", return_value=translator):
        response = _post(client, {"text_b64": encoded})

    assert response.status_code == 200
    assert response.get_json()["translation"] == "Delayed"
    translator.translate_text.assert_called_once_with(ARABIC, "fr", "ar")


def test_same_language_does_not_call_the_translator(client, admin_user):
    _login(client, admin_user.id)
    translator = MagicMock()
    with patch("app.routes.forms.field_translation.get_locale", return_value="en"), \
         patch("app.services.translation.auto_translator.get_auto_translator", return_value=translator):
        response = _post(client, {"text": ENGLISH})

    assert response.status_code == 200
    data = response.get_json()
    assert data["show_preview"] is False
    assert data["preview_only"] is True
    assert data["translation"] is None
    translator.translate_text.assert_not_called()


def test_focal_point_with_assignment_access_can_preview(client, test_user):
    _login(client, test_user.id)
    translator = MagicMock()
    translator.translate_text.return_value = "Aperçu"
    with patch("app.routes.forms.field_translation.get_locale", return_value="fr"), \
         patch(
             "app.utils.forms.form_authorization.authorize_aes_json",
             return_value=(MagicMock(), None),
         ), \
         patch("app.services.translation.auto_translator.get_auto_translator", return_value=translator):
        response = _post(client, {"text": ENGLISH, "assignment_entity_status_id": 15})

    assert response.status_code == 200
    data = response.get_json()
    assert data["show_preview"] is True
    assert data["translation"] == "Aperçu"
    translator.translate_text.assert_called_once()
    assert translator.translate_text.call_args.args[1] == "fr"


def test_empty_text_is_rejected(client, admin_user):
    _login(client, admin_user.id)
    response = _post(client, {"text": "   "})
    assert response.status_code == 400
