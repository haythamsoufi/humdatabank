"""Tests for SubmittedDocument → AIDocument metadata mapping."""

from datetime import date

from app.services.ai.documents.submitted_metadata import (
    build_ai_title_from_submitted_document,
    build_submitted_document_metadata_hints,
    map_document_type_label_to_category,
    merge_submitted_metadata_hints,
    parse_submitted_document_period_date,
)


class _FakeCountry:
    def __init__(self, name):
        self.name = name
        self.id = 1


class _FakeSubmittedDoc:
    def __init__(self, **kwargs):
        self.document_type = kwargs.get("document_type")
        self.form_item = kwargs.get("form_item")
        self.fdrs_import_key = kwargs.get("fdrs_import_key")
        self.language = kwargs.get("language")
        self.period = kwargs.get("period")
        self.filename = kwargs.get("filename", "report.pdf")
        self.country = kwargs.get("country")
        self.assignment_entity_status_id = kwargs.get("assignment_entity_status_id")
        self.public_submission_id = kwargs.get("public_submission_id")
        self.linked_entity_type = kwargs.get("linked_entity_type")
        self.linked_entity_id = kwargs.get("linked_entity_id")

    @property
    def document_label(self):
        if self.form_item:
            return self.form_item.label
        return self.document_type or "Document"

    @property
    def document_country(self):
        return self.country


def test_map_fdrs_document_types_to_categories():
    assert map_document_type_label_to_category("Annual Report") == "report"
    assert map_document_type_label_to_category("Strategic Plan") == "strategic_plan"
    assert map_document_type_label_to_category("Audited Financial Statement") == "report"


def test_fdrs_hints_set_source_organization_and_category():
    doc = _FakeSubmittedDoc(
        document_type="Annual Report",
        fdrs_import_key="abc123",
        language="fr",
        period="2024",
        country=_FakeCountry("Afghanistan"),
    )
    hints = build_submitted_document_metadata_hints(doc)
    assert hints["source_organization"] == "FDRS"
    assert hints["document_category"] == "report"
    assert hints["document_language"] == "fr"
    assert hints["document_date"] == date(2024, 12, 31)
    assert hints["extra_metadata"]["source_system"] == "FDRS"
    assert hints["extra_metadata"]["document_type_label"] == "Annual Report"


def test_merge_hints_override_heuristic_category_and_source():
    doc = _FakeSubmittedDoc(
        document_type="Strategic Plan",
        fdrs_import_key="key",
        period="2023",
    )
    merged = merge_submitted_metadata_hints(
        doc,
        {
            "document_category": "plan",
            "source_organization": "Adobe InDesign",
            "document_language": "en",
            "quality_score": 0.8,
        },
    )
    assert merged["document_category"] == "strategic_plan"
    assert merged["source_organization"] == "FDRS"
    assert merged["quality_score"] == 0.8


def test_build_ai_title_from_submitted_document():
    doc = _FakeSubmittedDoc(
        document_type="Annual Report",
        period="2024",
        country=_FakeCountry("Syria"),
        filename="Annual Report_SYR_2024_en.pdf",
    )
    assert build_ai_title_from_submitted_document(doc) == "Annual Report - Syria (2024)"


def test_parse_submitted_document_period_date_range():
    assert parse_submitted_document_period_date("2021-2024") == date(2024, 12, 31)
