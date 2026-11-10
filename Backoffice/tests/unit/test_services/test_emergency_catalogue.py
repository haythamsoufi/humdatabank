"""Emergency-operation inventory: IFRC types, not a title keyword."""

import pytest

from app.services.ai.documents.emergency_catalogue import (
    remember_ifrc_document_type,
    resolve_inventory_query,
    row_matches_scope,
)

pytestmark = [pytest.mark.unit]


def test_emergency_query_is_a_collection_not_a_substring():
    resolved = resolve_inventory_query("emergency")
    assert resolved.scope == "emergency"
    assert resolved.text is None


def test_unified_plan_query_stays_a_title_substring():
    resolved = resolve_inventory_query("UPL-")
    assert resolved.scope is None
    assert resolved.text == "upl-"


def test_category_argument_selects_dref_files_the_title_does_not_name():
    resolved = resolve_inventory_query(None, "dref")
    assert resolved.scope == "dref"
    assert row_matches_scope("Burkina Faso - Floods", "MDRBF019do.pdf", "other", resolved.scope)
    assert not row_matches_scope("Burkina Faso - Floods", "MDRBF019ea.pdf", "other", resolved.scope)


def test_floods_appeal_matches_emergency_without_the_word_emergency():
    assert row_matches_scope("Afghanistan Floods", "MDRAF001ea.pdf", None, "emergency")
    assert row_matches_scope(
        "Syria 2026 Unified Plan (UPL-2026-MAASY002)",
        "Syria_INP_2026.pdf",
        "plan",
        "emergency",
    ) is False


def test_stored_ifrc_type_sets_the_category_and_is_kept():
    class Doc:
        extra_metadata = {"alt_source_urls": ["https://go-api.ifrc.org/old"]}
        document_category = None

    doc = Doc()
    remember_ifrc_document_type(doc, "DREF Operation")
    assert doc.document_category == "dref"
    assert doc.extra_metadata["ifrc_document_type"] == "DREF Operation"
    assert doc.extra_metadata["alt_source_urls"] == ["https://go-api.ifrc.org/old"]


def test_unified_planning_type_is_stored_without_becoming_an_emergency():
    class Doc:
        extra_metadata = None
        document_category = "country_plan"

    doc = Doc()
    remember_ifrc_document_type(doc, "Plan")
    assert doc.document_category == "country_plan"
    assert doc.extra_metadata["ifrc_document_type"] == "Plan"
