"""Unit tests for admin document grid serialization."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.routes.admin.content_management import (
    _language_display_name,
    _serialize_document_grid_row,
)

pytestmark = [pytest.mark.unit]

_AUTH_SVC = "app.services.organization.authorization_service.AuthorizationService"


def _make_doc(**kwargs):
    defaults = {
        "id": 1,
        "filename": "report.pdf",
        "document_label": "Annual Report",
        "language": "en",
        "period": "2024",
        "is_public": True,
        "public_submission_id": None,
        "uploaded_by_user_id": 10,
        "linked_entity_type": "country",
        "linked_entity_id": 5,
        "country_id": 5,
        "status": "pending",
        "standalone_linked_display": "",
        "thumbnail_relative_path": None,
        "thumbnail_filename": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_user(**kwargs):
    defaults = {
        "id": 10,
        "name": "Test User",
        "email": "test@example.org",
        "title": "",
        "active": True,
        "profile_color": "",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_country(**kwargs):
    defaults = {"id": 5, "name": "Afghanistan"}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestLanguageDisplayName:
    def test_zz_maps_to_unknown(self):
        assert _language_display_name("zz") == "Unknown"

    def test_english_unchanged(self):
        assert _language_display_name("en") != "Unknown"


class TestSerializeDocumentGridRow:
    def _serialize(self, doc, status="pending", country=None, user=None):
        country = country if country is not None else _make_country()
        user = user if user is not None else _make_user()
        uploaded_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        row = (doc, status, country, user, uploaded_at, None, True)
        with patch(f"{_AUTH_SVC}.has_rbac_permission", return_value=True):
            return _serialize_document_grid_row(row)

    def test_is_public_uses_model_flag_not_public_submission(self):
        doc = _make_doc(is_public=False, public_submission_id=99)
        payload = self._serialize(doc)
        assert payload["is_public"] is False

    def test_is_public_true_for_fdrs_style_public_doc(self):
        doc = _make_doc(is_public=True, public_submission_id=None)
        payload = self._serialize(doc)
        assert payload["is_public"] is True

    def test_decline_url_present_for_managers(self):
        doc = _make_doc()
        payload = self._serialize(doc)
        assert payload["decline_url"].endswith(f"/documents/decline/{doc.id}")
