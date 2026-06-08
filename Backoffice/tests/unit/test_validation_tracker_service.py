"""Unit tests for validation dashboard tracker service."""

from unittest.mock import MagicMock, patch

from app.services.validation_tracker_service import (
    TRACKER_DOCUMENT_SPECS,
    TRACKER_SECTION_SPECS,
    _overall_completion_rate,
    _reporting_section_ratios,
    _section_fill_status,
    _status_value,
    build_tracker_data,
)


def test_section_fill_status_thresholds():
    assert _section_fill_status(0) == "not_started"
    assert _section_fill_status(0.5) == "in_progress"
    assert _section_fill_status(1.0) == "complete"


def test_status_value_without_assignment():
    assert _status_value(None) == "no_assignment"


def test_status_value_from_enum():
    aes = MagicMock()
    aes.status.value = "submitted"
    assert _status_value(aes) == "submitted"


@patch("app.services.validation_tracker_service.compute_income_sources_ratio", return_value=0.0)
def test_reporting_section_ratios_empty_kpi_data(_mock_income_ratio):
    ratios = _reporting_section_ratios({}, aes_id=1, template_id=21, version_id=None)
    assert set(ratios.keys()) == {"governance", "finance", "reach"}
    assert ratios["governance"] == 0.0
    assert ratios["reach"] == 0.0


def test_overall_completion_rate_averages_sections():
    assert _overall_completion_rate({"governance": 1.0, "finance": 0.5, "reach": 0.0}) == 50.0
    assert _overall_completion_rate({}) == 0.0


@patch("app.services.validation_tracker_service.compute_income_sources_ratio", return_value=0.0)
@patch("app.services.validation_tracker_service.active_country_map_query")
@patch("app.services.validation_tracker_service.AssignedForm")
@patch("app.services.validation_tracker_service.AssignmentEntityStatus")
@patch("app.services.validation_tracker_service._bulk_kpi_data_by_aes")
@patch("app.services.validation_tracker_service._document_field_map")
@patch("app.services.validation_tracker_service.SubmittedDocument")
def test_build_tracker_data_shapes(
    mock_submitted_doc,
    mock_doc_map,
    mock_bulk_kpi,
    mock_aes_model,
    mock_assigned_form,
    mock_active_countries,
    _mock_income_ratio,
):
    assignment = MagicMock()
    assignment.id = 10
    assignment.template = MagicMock(published_version_id=5)
    assignment.requires_delegation_review = False
    mock_assigned_form.query.filter.return_value.first.return_value = assignment

    country = MagicMock()
    country.id = 1
    country.name = "Testland"
    country.iso3 = "TST"
    country.region = "Europe"
    country.status = "Active"
    mock_active_countries.return_value.all.return_value = [country]

    aes = MagicMock()
    aes.id = 99
    aes.entity_id = 1
    aes.assigned_form_id = 10
    aes.status.value = "in_progress"
    aes.submitted_at = None
    mock_aes_model.query.filter.return_value.all.return_value = [aes]

    mock_doc_map.return_value = {spec["key"]: [] for spec in TRACKER_DOCUMENT_SPECS}
    mock_bulk_kpi.return_value = {99: {}}
    mock_submitted_doc.query.filter.return_value.all.return_value = []

    payload = build_tracker_data(21, "2024")

    assert payload["template_id"] == 21
    assert payload["period_name"] == "2024"
    assert len(payload["rows"]) == 1
    row = payload["rows"][0]
    assert row["country_name"] == "Testland"
    assert row["status"] == "in_progress"
    assert set(row["sections"].keys()) == {s["key"] for s in TRACKER_SECTION_SPECS}
    assert row["completion_rate"] == 0.0
    assert payload["stats"]["assigned_count"] == 1
    assert payload["delegation_review_enabled"] is False
    assert "sent_for_review" not in payload["stats"]["by_status"] or payload["stats"]["by_status"].get("sent_for_review", 0) == 0
    assert len(payload["map"]["countries"]) == 1
    assert payload["map"]["countries"][0]["iso3"] == "TST"
