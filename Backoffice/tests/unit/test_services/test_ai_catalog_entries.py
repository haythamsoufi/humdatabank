"""Catalog aliases for one file published under several years or document types."""

from datetime import date
from types import SimpleNamespace

import pytest

from app.services.ai.documents.submitted_metadata import (
    absorb_catalog_from_ai_document,
    format_year_span,
    record_submitted_catalog_entry,
    years_covered_by_period,
)
from app.services.ai.documents.vector_store import document_covers_date_range_clause


pytestmark = pytest.mark.unit


def _submitted(**kwargs):
    country = kwargs.get("country")
    return SimpleNamespace(
        id=kwargs["id"],
        period=kwargs.get("period"),
        document_type=kwargs.get("document_type"),
        document_label=None,
        filename=kwargs.get("filename") or "plan.pdf",
        source_url=kwargs.get("source_url"),
        document_country=SimpleNamespace(name=country) if country else None,
        fdrs_import_key="k" if kwargs.get("fdrs", True) else None,
        language=kwargs.get("language"),
    )


def _ai(**kwargs):
    return SimpleNamespace(
        id=kwargs.get("id", 1),
        title=kwargs.get("title") or "Strategic Plan - Monaco (2025)",
        filename=kwargs.get("filename") or "Strategic Plan_Monaco_2025_fr.pdf",
        source_url=kwargs.get("source_url"),
        country_name=kwargs.get("country_name") or "Monaco",
        country_id=kwargs.get("country_id", 1),
        submitted_document_id=kwargs.get("submitted_document_id", 1913),
        guidance_document_id=kwargs.get("guidance_document_id"),
        document_category=kwargs.get("document_category") or "strategic_plan",
        document_date=kwargs.get("document_date") or date(2025, 12, 31),
        document_language="fr",
        extra_metadata=dict(kwargs.get("extra_metadata") or {
            "document_type_label": "Strategic Plan",
            "reporting_period": "2025",
            "source_system": "FDRS",
        }),
        processing_status="completed",
        total_chunks=39,
        is_public=True,
    )


class TestYearSpan:
    def test_range_period_expands(self):
        assert years_covered_by_period("2025-2030") == [2025, 2026, 2027, 2028, 2029, 2030]

    def test_single_year(self):
        assert years_covered_by_period("2024") == [2024]

    def test_contiguous_span(self):
        assert format_year_span([2025, 2023, 2024]) == "2023-2025"

    def test_gap_stays_listed(self):
        assert format_year_span([2020, 2024]) == "2020, 2024"


class TestRecordSubmittedCatalogEntry:
    def test_multi_year_title_and_coverage(self):
        keeper = _ai()
        added_2024 = record_submitted_catalog_entry(
            keeper,
            _submitted(id=1910, period="2024", document_type="Strategic Plan", country="Monaco"),
        )
        added_2023 = record_submitted_catalog_entry(
            keeper,
            _submitted(id=1906, period="2023", document_type="Strategic Plan", country="Monaco"),
        )

        assert added_2024 is True
        assert added_2023 is True
        assert keeper.submitted_document_id == 1913
        assert keeper.title == "Strategic Plan - Monaco (2023-2025)"
        assert keeper.extra_metadata["coverage_years"] == [2023, 2024, 2025]
        assert keeper.document_date == date(2025, 12, 31)
        assert [e["submitted_document_id"] for e in keeper.extra_metadata["catalog_entries"]] == [
            1913, 1910, 1906
        ]

    def test_repeat_of_same_submitted_id_is_not_added_twice(self):
        keeper = _ai()
        record_submitted_catalog_entry(
            keeper,
            _submitted(id=1910, period="2024", document_type="Strategic Plan", country="Monaco"),
        )
        again = record_submitted_catalog_entry(
            keeper,
            _submitted(id=1910, period="2024", document_type="Strategic Plan", country="Monaco"),
        )
        assert again is False
        assert len(keeper.extra_metadata["catalog_entries"]) == 2

    def test_same_period_second_filename_keeps_one_year(self):
        keeper = _ai(
            title="Strategic Plan - Cook Islands (2024-2030)",
            country_name="Cook Islands",
            extra_metadata={
                "document_type_label": "Strategic Plan",
                "reporting_period": "2024-2030",
            },
        )
        record_submitted_catalog_entry(
            keeper,
            _submitted(
                id=676,
                period="2024-2030",
                document_type="Strategic Plan",
                country="Cook Islands",
                filename="Strategic Plan_CookIslands_2024-2030.pdf",
            ),
        )
        assert keeper.title == "Strategic Plan - Cook Islands (2024-2030)"
        assert keeper.extra_metadata["coverage_years"] == list(range(2024, 2031))
        assert len(keeper.extra_metadata["catalog_entries"]) == 2

    def test_two_document_types_share_one_title(self):
        keeper = _ai(
            title="Annual Report - Portugal (2023-2023)",
            country_name="Portugal",
            document_category="report",
            extra_metadata={
                "document_type_label": "Annual Report",
                "reporting_period": "2023-2023",
            },
        )
        record_submitted_catalog_entry(
            keeper,
            _submitted(
                id=2512,
                period="2023-2023",
                document_type="Strategic Plan",
                country="Portugal",
            ),
        )
        assert keeper.title == "Annual Report / Strategic Plan - Portugal (2023)"
        assert keeper.document_category == "report"
        assert keeper.extra_metadata["document_categories"] == ["report", "strategic_plan"]

    def test_range_plus_single_years_becomes_one_span(self):
        keeper = _ai(
            title="Strategic Plan - Sweden (2025-2030)",
            country_name="Sweden",
            extra_metadata={
                "document_type_label": "Strategic Plan",
                "reporting_period": "2025-2030",
            },
        )
        record_submitted_catalog_entry(
            keeper,
            _submitted(id=2869, period="2024", document_type="Strategic Plan", country="Sweden"),
        )
        record_submitted_catalog_entry(
            keeper,
            _submitted(id=2866, period="2023", document_type="Strategic Plan", country="Sweden"),
        )
        assert keeper.title == "Strategic Plan - Sweden (2023-2030)"

    def test_year_in_the_title_is_kept_when_period_metadata_is_missing(self):
        keeper = _ai(extra_metadata={})
        record_submitted_catalog_entry(
            keeper,
            _submitted(id=1910, period="2024", document_type="Strategic Plan", country="Monaco"),
        )
        assert keeper.title == "Strategic Plan - Monaco (2024-2025)"

    def test_absorb_duplicate_rows_before_delete(self):
        keeper = _ai(submitted_document_id=1913)
        loser = _ai(
            id=2,
            submitted_document_id=1910,
            title="Strategic Plan - Monaco (2024)",
            extra_metadata={
                "document_type_label": "Strategic Plan",
                "reporting_period": "2024",
            },
        )
        absorb_catalog_from_ai_document(keeper, loser)
        assert keeper.title == "Strategic Plan - Monaco (2024-2025)"
        assert {e["submitted_document_id"] for e in keeper.extra_metadata["catalog_entries"]} == {1913, 1910}


def test_date_filter_also_matches_coverage_years():
    clause = document_covers_date_range_clause({"min": "2023-01-01", "max": "2023-12-31"})
    compiled = str(clause)
    assert "coverage_years" in compiled
    assert "document_date" in compiled
