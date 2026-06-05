"""Unit tests for FDRS compliance document label matching."""

import pytest

from app.services.data_quality.helpers import (
    active_country_map_query,
    build_compliance_document_lookups,
    compliance_doc_status_counts_toward_requirement,
    fdrs_compliance_doc_label_matches,
)
from app.models.enums import DocumentStatus


@pytest.mark.parametrize(
    "label,doc_type,expected",
    [
        ("Audited Financial Statement", "Audited Financial Statement", True),
        ("Our Audited Financial Statements", "Audited Financial Statement", True),
        ("Unaudited Financial Statement", "Audited Financial Statement", False),
        ("Our Unaudited Financial Statement", "Audited Financial Statement", False),
        ("Annual Report", "Annual Report", True),
        ("Our Annual Report", "Annual Report", True),
        ("Unaudited Financial Statement", "Annual Report", False),
        ("", "Annual Report", False),
        (None, "Annual Report", False),
    ],
)
def test_fdrs_compliance_doc_label_matches(label, doc_type, expected):
    assert fdrs_compliance_doc_label_matches(label, doc_type) is expected


def test_build_compliance_document_lookups_tracks_pending_status():
    submitted_docs = [
        type("Doc", (), {
            "form_item_id": 10,
            "assignment_entity_status_id": 5,
            "status": DocumentStatus.PENDING,
        })(),
        type("Doc", (), {
            "form_item_id": 11,
            "assignment_entity_status_id": 6,
            "status": DocumentStatus.APPROVED,
        })(),
    ]
    item_id_to_doc_type = {10: "Annual Report", 11: "Audited Financial Statement"}

    present, pending, status = build_compliance_document_lookups(submitted_docs, item_id_to_doc_type)

    assert present[(5, "Annual Report")] is True
    assert pending[(5, "Annual Report")] is True
    assert status[(5, "Annual Report")] == "pending"
    assert present[(6, "Audited Financial Statement")] is True
    assert pending.get((6, "Audited Financial Statement")) is None
    assert status[(6, "Audited Financial Statement")] == "approved"


@pytest.mark.parametrize(
    "status,expected",
    [
        ("approved", True),
        ("pending", True),
        ("rejected", False),
        ("missing", False),
        (None, False),
    ],
)
def test_compliance_doc_status_counts_toward_requirement(status, expected):
    assert compliance_doc_status_counts_toward_requirement(status) is expected


def test_active_country_map_query_filters_inactive(app, db_session):
    from app.models import Country

    active = Country(name="Active Land", iso3="ACL", region="Test", status="Active")
    inactive = Country(name="Inactive Land", iso3="ICL", region="Test", status="Inactive")
    db_session.add_all([active, inactive])
    db_session.commit()

    rows = active_country_map_query().all()
    names = {c.name for c in rows}
    assert "Active Land" in names
    assert "Inactive Land" not in names
