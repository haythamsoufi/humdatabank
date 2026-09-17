"""Tests for AI document provenance metadata extraction."""

from datetime import date, datetime

import pytest

from app.services.ai.documents.metadata import extract_document_date, enrich_document_metadata

pytestmark = [pytest.mark.unit]


class TestExtractDocumentDateUplYear:
    def test_syria_2026_upl_ignores_pdf_creation_date(self):
        result = extract_document_date(
            title="Syria 2026 Unified Plan (UPL-2026-MAASY002)",
            filename="Syria_INP_2026.pdf",
            text_sample="IFRC Country Delegation Syria, Damascus 2025-12-11 funding 163.6M CHF",
            pdf_creation_date="D:20251211103000+01'00'",
        )
        assert result == date(2026, 1, 1)

    def test_upl_code_in_filename_beats_pdf_creation(self):
        result = extract_document_date(
            title="Country plan",
            filename="UPL-2026-MAASY002.pdf",
            text_sample="",
            pdf_creation_date="D:20251211000000",
        )
        assert result == date(2026, 1, 1)

    def test_unified_plan_phrase_in_title(self):
        result = extract_document_date(
            title="Estonia 2025 Unified Plan",
            filename="report.pdf",
            text_sample="Published 2024-11-02",
            pdf_creation_date="D:20241102120000",
        )
        assert result == date(2025, 1, 1)


class TestExtractDocumentDateFallbacks:
    def test_filename_year_beats_pdf_creation_when_title_has_no_plan_year(self):
        result = extract_document_date(
            title="Syria Country Plan",
            filename="Syria_INP_2026.pdf",
            text_sample="",
            pdf_creation_date="D:20251211103000",
        )
        assert result == date(2026, 1, 1)

    def test_iso_date_in_title_when_not_a_unified_plan(self):
        result = extract_document_date(
            title="Flash Update 2024-03-15",
            filename="update.pdf",
            text_sample="",
            pdf_creation_date="D:20240101000000",
        )
        assert result == date(2024, 3, 15)

    def test_month_year_in_title(self):
        result = extract_document_date(
            title="Sitrep March 2024",
            filename="sitrep.pdf",
            text_sample="",
            pdf_creation_date="D:20251211000000",
        )
        assert result == date(2024, 3, 1)

    def test_body_iso_date_beats_pdf_creation(self):
        result = extract_document_date(
            title="Assessment",
            filename="assessment.pdf",
            text_sample="Issued 2024-06-18 following the mission.",
            pdf_creation_date="D:20251211000000",
        )
        assert result == date(2024, 6, 18)

    def test_pdf_creation_is_last_resort(self):
        result = extract_document_date(
            title="Untitled",
            filename="scan.pdf",
            text_sample="",
            pdf_creation_date="D:20230801120000",
        )
        assert result == date(2023, 8, 1)

    def test_pdf_creation_datetime_object(self):
        result = extract_document_date(
            title="Untitled",
            filename="scan.pdf",
            text_sample="",
            pdf_creation_date=datetime(2023, 8, 1, 12, 0, 0),
        )
        assert result == date(2023, 8, 1)

    def test_returns_none_when_no_signals(self):
        assert extract_document_date("Notes", "notes.pdf", "No dates here.") is None


class TestEnrichDocumentMetadataUsesPlanYear:
    def test_enrichment_stores_upl_year_not_pdf_creation(self):
        meta = enrich_document_metadata(
            title="Syria 2026 Unified Plan (UPL-2026-MAASY002)",
            filename="Syria_INP_2026.pdf",
            text="Cover page dated 2025-12-11. Longer-term needs MAASY002.",
            pdf_metadata={"creation_date": "D:20251211103000+01'00'"},
        )
        assert meta["document_date"] == date(2026, 1, 1)
