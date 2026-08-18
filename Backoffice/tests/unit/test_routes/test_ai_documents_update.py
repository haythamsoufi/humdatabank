"""PATCH /api/ai/documents/<id> geography and category updates."""

import uuid

import pytest

from app.models import AIDocument
from tests.factories import create_test_country

pytestmark = [pytest.mark.unit]


def _create_doc(db_session, admin_user, **kwargs):
    defaults = {
        "title": "Strategy 2030",
        "filename": "S2030.pdf",
        "file_type": "pdf",
        "file_size_bytes": 100,
        "storage_path": "S2030.pdf",
        "content_hash": f"hash-{uuid.uuid4().hex}",
        "processing_status": "completed",
        "user_id": admin_user.id,
    }
    defaults.update(kwargs)
    doc = AIDocument(**defaults)
    db_session.add(doc)
    db_session.commit()
    return doc


class TestUpdateDocumentGeography:
    def test_set_global_clears_country(self, logged_in_client, db_session, admin_user):
        country = create_test_country(db_session, name="Switzerland", iso2="CH", iso3="CHE")
        doc = _create_doc(
            db_session,
            admin_user,
            country_id=country.id,
            country_name="Switzerland",
            geographic_scope=None,
        )
        doc.countries.append(country)
        db_session.commit()

        resp = logged_in_client.patch(
            f"/api/ai/documents/{doc.id}",
            json={"geographic_scope": "global"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["document"]["geographic_scope"] == "global"
        assert body["document"]["country_id"] is None
        assert body["document"]["countries"] == []

        refreshed = AIDocument.query.get(doc.id)
        assert refreshed.geographic_scope == "global"
        assert refreshed.country_id is None
        assert list(refreshed.countries) == []

    def test_set_country_specific(self, logged_in_client, db_session, admin_user):
        country = create_test_country(db_session, name="Kenya", iso2="KE", iso3="KEN")
        doc = _create_doc(db_session, admin_user, geographic_scope="global")

        resp = logged_in_client.patch(
            f"/api/ai/documents/{doc.id}",
            json={"geographic_scope": None, "country_id": country.id},
            content_type="application/json",
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["document"]["geographic_scope"] is None
        assert body["document"]["country_id"] == country.id
        assert body["document"]["country_name"] == "Kenya"
        assert len(body["document"]["countries"]) == 1
        assert body["document"]["countries"][0]["iso3"] == "KEN"

    def test_clear_geography(self, logged_in_client, db_session, admin_user):
        country = create_test_country(db_session, name="France", iso2="FR", iso3="FRA")
        doc = _create_doc(
            db_session,
            admin_user,
            country_id=country.id,
            country_name="France",
        )
        doc.countries.append(country)
        db_session.commit()

        resp = logged_in_client.patch(
            f"/api/ai/documents/{doc.id}",
            json={"geographic_scope": None, "country_id": None},
            content_type="application/json",
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["document"]["geographic_scope"] is None
        assert body["document"]["country_id"] is None
        assert body["document"]["countries"] == []

    def test_invalid_scope(self, logged_in_client, db_session, admin_user):
        doc = _create_doc(db_session, admin_user)
        resp = logged_in_client.patch(
            f"/api/ai/documents/{doc.id}",
            json={"geographic_scope": "continent"},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_unknown_country_id(self, logged_in_client, db_session, admin_user):
        doc = _create_doc(db_session, admin_user)
        resp = logged_in_client.patch(
            f"/api/ai/documents/{doc.id}",
            json={"geographic_scope": None, "country_id": 999999},
            content_type="application/json",
        )
        assert resp.status_code == 400
