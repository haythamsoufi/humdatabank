"""Tests for GET /api/v1/fdrs/published-data (plugins/fdrs/public_api_routes.py).

Real end-to-end: a genuine `APIKey` row (via create_test_api_key) and a real
`Authorization: Bearer <key>` header — no auth mocking. This endpoint must only
ever surface the *published* snapshot, never a live/unpublished edit, and only
for form items marked privacy='public'.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm.attributes import flag_modified

from app.models import FormData
from app.utils.datetime_helpers import utcnow
from tests.factories import (
    create_test_api_key,
    create_test_assignment_entity_status,
    create_test_country,
    create_test_item,
    create_test_section,
    create_test_template,
)
from tests.helpers import assert_paginated_response

pytestmark = [pytest.mark.unit]

_URL = "/api/v1/fdrs/published-data"


def _patch_fdrs_template_id(monkeypatch, template_id: int) -> None:
    import plugins.fdrs.public_api_routes as public_api_routes

    monkeypatch.setattr(public_api_routes, "FDRS_TEMPLATE_ID", template_id)


def _bearer_headers(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


@pytest.fixture
def published_scenario(db_session, monkeypatch):
    template = create_test_template(db_session, name="FDRS Public API Test Template")
    _patch_fdrs_template_id(monkeypatch, template.id)

    section = create_test_section(db_session, template)
    item_public = create_test_item(db_session, section, template, label="Public Published Item")
    item_public.set_privacy("public")
    flag_modified(item_public, "config")
    item_private = create_test_item(db_session, section, template, label="Internal Item")
    item_unpublished = create_test_item(db_session, section, template, label="Public But Unpublished Item")
    item_unpublished.set_privacy("public")
    flag_modified(item_unpublished, "config")
    db_session.commit()

    country = create_test_country(db_session, name="Publishland", iso2="PL", iso3="PBL")
    aes = create_test_assignment_entity_status(
        db_session, country=country, template=template, period_name="2024",
    )

    published_row = FormData(
        assignment_entity_status_id=aes.id,
        form_item_id=item_public.id,
        value="123",
        numeric_value=123.0,
        published_value="123",
        published_numeric_value=123.0,
        published_at=utcnow(),
    )
    # Privacy is public, but published_* was never set for this item's private counterpart —
    # even though it has a live `value`, the public feed must never expose it.
    private_but_published_row = FormData(
        assignment_entity_status_id=aes.id,
        form_item_id=item_private.id,
        value="secret",
        published_value="should-never-be-exposed",
    )
    unpublished_row = FormData(
        assignment_entity_status_id=aes.id,
        form_item_id=item_unpublished.id,
        value="live-edit-not-yet-published",
        published_value=None,
    )
    db_session.add_all([published_row, private_but_published_row, unpublished_row])
    db_session.commit()

    return {
        "template": template,
        "assigned_form_id": aes.assigned_form_id,
        "country": country,
        "item_public": item_public,
        "item_private": item_private,
        "item_unpublished": item_unpublished,
    }


class TestAuth:
    def test_missing_api_key_returns_401(self, client, db_session, published_scenario):
        response = client.get(_URL)
        assert response.status_code == 401

    def test_invalid_api_key_returns_401(self, client, db_session, published_scenario):
        response = client.get(_URL, headers=_bearer_headers("not-a-real-key"))
        assert response.status_code == 401


class TestPublishedDataContents:
    def test_only_published_public_item_is_returned(self, client, db_session, published_scenario):
        api_key_obj, full_key = create_test_api_key(db_session)
        response = client.get(_URL, headers=_bearer_headers(full_key))

        assert_paginated_response(response, min_items=1)
        data = response.get_json()["data"]
        assert len(data) == 1
        row = data[0]
        assert row["value"] == "123"
        assert row["num_value"] == 123.0
        assert row["data_status"] == "available"
        assert row["country_name"] == "Publishland"
        assert row["published_at"] is not None

    def test_private_item_never_exposed_even_if_published_value_set(self, client, db_session, published_scenario):
        api_key_obj, full_key = create_test_api_key(db_session)
        response = client.get(_URL, headers=_bearer_headers(full_key))

        data = response.get_json()["data"]
        labels = [row["item_label"] for row in data]
        assert "Internal Item" not in labels
        values = [row["value"] for row in data]
        assert "should-never-be-exposed" not in values

    def test_unpublished_live_edit_never_exposed(self, client, db_session, published_scenario):
        api_key_obj, full_key = create_test_api_key(db_session)
        response = client.get(_URL, headers=_bearer_headers(full_key))

        data = response.get_json()["data"]
        labels = [row["item_label"] for row in data]
        assert "Public But Unpublished Item" not in labels
        values = [row["value"] for row in data]
        assert "live-edit-not-yet-published" not in values

    def test_filter_by_country_iso3(self, client, db_session, published_scenario):
        api_key_obj, full_key = create_test_api_key(db_session)
        response = client.get(_URL, query_string={"country_iso3": "PBL"}, headers=_bearer_headers(full_key))
        assert len(response.get_json()["data"]) == 1

        response_miss = client.get(_URL, query_string={"country_iso3": "ZZZ"}, headers=_bearer_headers(full_key))
        assert response_miss.get_json()["data"] == []

    def test_filter_by_period_name(self, client, db_session, published_scenario):
        api_key_obj, full_key = create_test_api_key(db_session)
        response = client.get(_URL, query_string={"period_name": "2024"}, headers=_bearer_headers(full_key))
        assert len(response.get_json()["data"]) == 1

        response_miss = client.get(_URL, query_string={"period_name": "1999"}, headers=_bearer_headers(full_key))
        assert response_miss.get_json()["data"] == []

    def test_filter_by_assignment_id(self, client, db_session, published_scenario):
        api_key_obj, full_key = create_test_api_key(db_session)
        response = client.get(
            _URL,
            query_string={"assignment_id": published_scenario["assigned_form_id"]},
            headers=_bearer_headers(full_key),
        )
        assert len(response.get_json()["data"]) == 1

    def test_filter_by_form_item_id(self, client, db_session, published_scenario):
        api_key_obj, full_key = create_test_api_key(db_session)
        response = client.get(
            _URL,
            query_string={"form_item_id": published_scenario["item_public"].id},
            headers=_bearer_headers(full_key),
        )
        assert len(response.get_json()["data"]) == 1

        response_miss = client.get(
            _URL,
            query_string={"form_item_id": published_scenario["item_unpublished"].id},
            headers=_bearer_headers(full_key),
        )
        assert response_miss.get_json()["data"] == []

    def test_pagination_meta(self, client, db_session, published_scenario):
        api_key_obj, full_key = create_test_api_key(db_session)
        response = client.get(_URL, query_string={"page": 1, "per_page": 1}, headers=_bearer_headers(full_key))
        meta = response.get_json()["meta"]
        assert meta["total"] == 1
        assert meta["page"] == 1
        assert meta["per_page"] == 1
        assert meta["total_pages"] == 1

    def test_invalid_page_returns_400(self, client, db_session, published_scenario):
        api_key_obj, full_key = create_test_api_key(db_session)
        response = client.get(_URL, query_string={"page": 0}, headers=_bearer_headers(full_key))
        assert response.status_code == 400

    def test_invalid_per_page_returns_400(self, client, db_session, published_scenario):
        api_key_obj, full_key = create_test_api_key(db_session)
        response = client.get(_URL, query_string={"per_page": 0}, headers=_bearer_headers(full_key))
        assert response.status_code == 400
