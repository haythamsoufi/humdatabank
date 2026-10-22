"""The resource edit form base64-encodes text inputs before POST."""
import base64

import pytest

pytestmark = [pytest.mark.unit]


def test_video_links_are_decoded_before_validation(app):
    from types import SimpleNamespace

    from app.routes.admin.content_management import _decode_b64_form_text_fields

    link = "https://youtu.be/p7JOBPItKzY"
    encoded = base64.b64encode(link.encode()).decode()

    class Field:
        def __init__(self, data):
            self.data = data

    form = SimpleNamespace(
        default_title=Field(None),
        default_description=Field(None),
        external_url_en=Field(encoded),
    )
    with app.app_context():
        _decode_b64_form_text_fields(form)
    assert form.external_url_en.data == link
