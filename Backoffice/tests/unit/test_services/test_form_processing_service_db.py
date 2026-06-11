"""
DB-backed tests for app/services/form_processing_service.py

These tests require a live database (db_session fixture) and are kept in a
separate file to avoid PostgreSQL deadlocks that occur when they are run
immediately after the large set of mock-only tests in test_form_processing_service.py
(the session-level app fixture's open connections interfere with db_session's
schema setup in that scenario).
"""
import pytest
from unittest.mock import patch

from app.services.form_processing_service import get_form_items_for_section
from tests.factories import (
    create_test_item,
    create_test_section,
    create_test_template,
)


@pytest.mark.unit
class TestGetFormItemsForSection:

    def test_empty_section_returns_empty_list(self, db_session):
        with patch("app.utils.form_localization.get_translation_key", return_value="en"), \
             patch("app.get_locale", return_value="en"):
            template = create_test_template(db_session)
            section = create_test_section(db_session, template, section_type="standard")
            result = get_form_items_for_section(section, None)
        assert result == []

    def test_standard_section_with_items(self, db_session):
        with patch("app.utils.form_localization.get_translation_key", return_value="en"), \
             patch("app.get_locale", return_value="en"):
            template = create_test_template(db_session)
            section = create_test_section(db_session, template, section_type="standard")
            create_test_item(
                db_session, section, template,
                item_type="question", label="Q1", type="text", order=1
            )
            create_test_item(
                db_session, section, template,
                item_type="question", label="Q2", type="text", order=2
            )
            result = get_form_items_for_section(section, None)
        assert len(result) == 2

    def test_archived_items_excluded(self, db_session):
        with patch("app.utils.form_localization.get_translation_key", return_value="en"), \
             patch("app.get_locale", return_value="en"):
            template = create_test_template(db_session)
            section = create_test_section(db_session, template, section_type="standard")
            create_test_item(
                db_session, section, template,
                item_type="question", label="Active Q", type="text", order=1
            )
            create_test_item(
                db_session, section, template,
                item_type="question", label="Archived Q", type="text", order=2,
                archived=True
            )
            result = get_form_items_for_section(section, None)
        assert len(result) == 1
        assert result[0].label == "Active Q"
