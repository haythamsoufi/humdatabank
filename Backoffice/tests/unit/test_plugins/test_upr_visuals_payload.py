"""DB-backed build_payload orchestration for an empty UPR assignment."""

from __future__ import annotations

import pytest

from plugins.upr_visuals.catalog import PLAN_TEMPLATE_ID
from plugins.upr_visuals.data import build_payload
from tests.factories import create_test_assignment_entity_status, create_test_country, create_test_template


@pytest.mark.integration
def test_build_payload_empty_upr_assignment(db_session, monkeypatch):
    country = create_test_country(db_session, name="Côte d'Ivoire Visuals")
    template = create_test_template(db_session, name="Unified Plan 2026")
    monkeypatch.setattr("plugins.upr_visuals.catalog.PLAN_TEMPLATE_ID", template.id)
    monkeypatch.setattr("plugins.upr_visuals.catalog.UPR_VISUAL_TEMPLATE_IDS", frozenset({template.id}))
    monkeypatch.setattr("plugins.upr_visuals.errors.UPR_VISUAL_TEMPLATE_IDS", frozenset({template.id}))

    aes = create_test_assignment_entity_status(
        db_session,
        country=country,
        template=template,
        period_name="Annual 2026",
    )

    payload = build_payload(aes.id)
    assert payload["meta"]["aes_id"] == aes.id
    assert payload["meta"]["kind"] == "plan"
    assert payload["meta"]["country_name"] == country.name
    assert payload["meta"]["iso3"] == country.iso3
    assert "kpis" in payload
    assert payload["people_reached"]
    assert all(not row.get("has_value") for row in payload["people_reached"])
    assert payload["support"] == []
    dash_ids = {item["id"] for item in payload["dashboards"]}
    assert "combined" in dash_ids
    assert "in_support" in dash_ids
    _ = PLAN_TEMPLATE_ID
