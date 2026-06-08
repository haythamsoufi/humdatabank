"""Unit tests for template section and item duplication services."""

import uuid

import pytest

from app.models import FormItem, FormSection, IndicatorBank
from app.services.item_duplication_service import ItemDuplicationService
from app.services.section_duplication_service import SectionDuplicationService

from tests.factories import (
    create_test_item,
    create_test_section,
    create_test_template,
)


@pytest.mark.unit
class TestSectionDuplicationService:
    def test_duplicate_section_creates_new_row(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="Section Dup Template")
            section = create_test_section(
                db_session,
                template,
                name="Source Section",
                order=2,
            )
            before_count = db_session.query(FormSection).count()

            new_section, _section_map = SectionDuplicationService.duplicate_section(section.id)
            db_session.commit()

            assert db_session.query(FormSection).count() == before_count + 1
            assert new_section.id != section.id
            assert new_section.template_id == template.id
            assert new_section.version_id == section.version_id
            assert "Source Section" in new_section.name

    def test_duplicate_section_copies_child_items(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="Section Items Dup Template")
            section = create_test_section(db_session, template, name="Parent Section")
            create_test_item(
                db_session,
                section,
                template,
                item_type="question",
                label="Child Question 1",
                type="text",
                order=1,
            )
            create_test_item(
                db_session,
                section,
                template,
                item_type="question",
                label="Child Question 2",
                type="text",
                order=2,
            )

            new_section, _section_map = SectionDuplicationService.duplicate_section(section.id)
            db_session.commit()

            copied_items = (
                db_session.query(FormItem)
                .filter_by(section_id=new_section.id, archived=False)
                .order_by(FormItem.order)
                .all()
            )
            assert len(copied_items) == 2
            assert copied_items[0].label == "Child Question 1"
            assert copied_items[1].label == "Child Question 2"
            assert "(Copy)" in new_section.name


@pytest.mark.unit
class TestItemDuplicationService:
    def test_duplicate_indicator_item(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="Indicator Dup Template")
            section = create_test_section(db_session, template)
            indicator_bank = IndicatorBank(
                name=f"Indicator {uuid.uuid4().hex[:8]}",
                definition="Test indicator",
                type="Number",
                unit="People",
            )
            db_session.add(indicator_bank)
            db_session.flush()

            source_item = create_test_item(
                db_session,
                section,
                template,
                item_type="indicator",
                label="Source Indicator",
                type="number",
                indicator_bank_id=indicator_bank.id,
            )
            before_count = db_session.query(FormItem).count()

            new_item = ItemDuplicationService.duplicate_item(source_item.id)
            db_session.commit()

            assert db_session.query(FormItem).count() == before_count + 1
            assert new_item.id != source_item.id
            assert new_item.indicator_bank_id == indicator_bank.id
            assert new_item.item_type == "indicator"
            assert "(Copy)" in new_item.label

    def test_duplicate_question_item(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="Question Dup Template")
            section = create_test_section(db_session, template)
            source_item = create_test_item(
                db_session,
                section,
                template,
                item_type="question",
                label="Source Question",
                type="text",
            )

            new_item = ItemDuplicationService.duplicate_item(source_item.id)
            db_session.commit()

            assert new_item.id != source_item.id
            assert new_item.item_type == "question"
            assert new_item.type == "text"
            assert "(Copy)" in new_item.label
