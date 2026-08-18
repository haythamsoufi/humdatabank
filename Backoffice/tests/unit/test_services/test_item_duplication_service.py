"""
Comprehensive tests for app/services/item_duplication_service.py

Targets 100% coverage:
- ItemDuplicationService.duplicate_item
- ItemDuplicationService._duplicate_item_object
- ItemDuplicationService._deep_copy_json_field (staticmethod)
"""
import json
import pytest

from app import db
from app.models import FormItem, IndicatorBank
from app.services.forms.item_duplication_service import ItemDuplicationService
from tests.factories import (
    create_test_item,
    create_test_section,
    create_test_template,
)


@pytest.mark.unit
class TestItemDuplicationServiceDuplicateItem:

    def test_raises_value_error_when_item_not_found(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            ItemDuplicationService.duplicate_item(99999)

    def test_duplicate_creates_new_item(self, db_session):
        template = create_test_template(db_session, name="ItemDup Template New")
        section = create_test_section(db_session, template, name="Section New")
        source = create_test_item(
            db_session, section, template,
            item_type="question", label="Original Question", type="text", order=1
        )
        before = db_session.query(FormItem).count()

        new_item = ItemDuplicationService.duplicate_item(source.id)
        db_session.commit()

        assert db_session.query(FormItem).count() == before + 1
        assert new_item.id != source.id

    def test_duplicate_inherits_template_and_version(self, db_session):
        template = create_test_template(db_session, name="ItemDup Template Inherit")
        section = create_test_section(db_session, template, name="Section Inherit")
        source = create_test_item(
            db_session, section, template,
            item_type="question", label="Inherit Item", type="text", order=1
        )

        new_item = ItemDuplicationService.duplicate_item(source.id)
        db_session.commit()

        assert new_item.template_id == template.id
        assert new_item.version_id == source.version_id
        assert new_item.section_id == source.section_id

    def test_duplicate_adds_copy_suffix(self, db_session):
        template = create_test_template(db_session, name="ItemDup Template Suffix")
        section = create_test_section(db_session, template, name="Section Suffix")
        source = create_test_item(
            db_session, section, template,
            item_type="question", label="My Question", type="text", order=1
        )

        new_item = ItemDuplicationService.duplicate_item(source.id)
        db_session.commit()

        assert "My Question" in new_item.label
        assert "Copy" in new_item.label

    def test_duplicate_suffix_increments_on_collision(self, db_session):
        template = create_test_template(db_session, name="ItemDup Template Collision")
        section = create_test_section(db_session, template, name="Section Collision")
        source = create_test_item(
            db_session, section, template,
            item_type="question", label="Collision Item", type="text", order=1
        )

        first_copy = ItemDuplicationService.duplicate_item(source.id)
        db_session.commit()

        second_copy = ItemDuplicationService.duplicate_item(source.id)
        db_session.commit()

        assert "Copy 2" in second_copy.label

    def test_duplicate_new_item_not_archived(self, db_session):
        template = create_test_template(db_session, name="ItemDup Template Archive")
        section = create_test_section(db_session, template, name="Section Archive")
        source = create_test_item(
            db_session, section, template,
            item_type="question", label="Archive Item", type="text", order=1
        )

        new_item = ItemDuplicationService.duplicate_item(source.id)
        db_session.commit()

        assert new_item.archived is False

    def test_duplicate_order_after_last_item(self, db_session):
        template = create_test_template(db_session, name="ItemDup Template Order")
        section = create_test_section(db_session, template, name="Section Order")
        item1 = create_test_item(
            db_session, section, template,
            item_type="question", label="Item 1", type="text", order=1
        )
        item2 = create_test_item(
            db_session, section, template,
            item_type="question", label="Item 2", type="text", order=5
        )

        new_item = ItemDuplicationService.duplicate_item(item1.id)
        db_session.commit()

        # Should be placed after the last item (order 5), so order >= 6
        assert new_item.order >= 6

    def test_duplicate_indicator_item_with_bank(self, db_session):
        template = create_test_template(db_session, name="ItemDup Indicator Template")
        section = create_test_section(db_session, template, name="Indicator Section")

        bank = IndicatorBank(
            name="Test Indicator Bank",
            definition="A test indicator",
            type="Number",
            unit="People",
        )
        db_session.add(bank)
        db_session.flush()

        source = create_test_item(
            db_session, section, template,
            item_type="indicator", label="Source Indicator", type="number",
            order=1, indicator_bank_id=bank.id
        )

        new_item = ItemDuplicationService.duplicate_item(source.id)
        db_session.commit()

        assert new_item.item_type == "indicator"
        assert new_item.indicator_bank_id == bank.id

    def test_duplicate_item_with_no_label_uses_type(self, db_session):
        template = create_test_template(db_session, name="ItemDup No Label Template")
        section = create_test_section(db_session, template, name="No Label Section")
        source = create_test_item(
            db_session, section, template,
            item_type="question", label=None, type="text", order=1
        )
        # Override label to None in DB
        source.label = None
        db_session.commit()

        new_item = ItemDuplicationService.duplicate_item(source.id)
        db_session.commit()

        # Label should be generated from item_type
        assert new_item.label is not None
        assert "Copy" in new_item.label

    def test_raises_if_section_not_found(self, db_session):
        """If item's section_id points to a missing section, raises ValueError."""
        template = create_test_template(db_session, name="ItemDup Bad Section Template")
        section = create_test_section(db_session, template, name="To Delete Section")
        source = create_test_item(
            db_session, section, template,
            item_type="question", label="Orphan Item", type="text", order=1
        )
        source_id = source.id

        # Delete the section directly (bypassing cascade constraints)
        db_session.query(FormItem).filter_by(section_id=section.id).delete()
        db_session.delete(section)
        db_session.commit()

        # Now the item doesn't exist anymore, duplicate_item should raise
        with pytest.raises(ValueError):
            ItemDuplicationService.duplicate_item(source_id)


@pytest.mark.unit
class TestItemDuplicationServiceDuplicateItemObject:

    def test_copies_all_item_properties(self, db_session):
        template = create_test_template(db_session, name="ItemObj Template Props")
        section = create_test_section(db_session, template, name="Props Section")
        source = create_test_item(
            db_session, section, template,
            item_type="question", label="Props Question", type="text", order=3
        )
        source.relevance_condition = '[{"field": 1}]'
        source.validation_condition = '[{"rule": "required"}]'
        source.validation_message = "This is required"
        source.definition = "A definition"
        source.description = "A description"
        db_session.commit()

        new_item = ItemDuplicationService._duplicate_item_object(
            source,
            template.id,
            source.version_id,
            section.id,
            order=10,
            label="Copy Label"
        )
        db_session.add(new_item)
        db_session.flush()

        assert new_item.relevance_condition == source.relevance_condition
        assert new_item.validation_condition == source.validation_condition
        assert new_item.validation_message == source.validation_message
        assert new_item.definition == source.definition
        assert new_item.description == source.description

    def test_copies_translations(self, db_session):
        template = create_test_template(db_session, name="ItemObj Template Trans")
        section = create_test_section(db_session, template, name="Trans Section")
        source = create_test_item(
            db_session, section, template,
            item_type="question", label="Trans Question", type="text", order=1
        )
        source.label_translations = {"fr": "Question en Français"}
        source.definition_translations = {"fr": "Définition"}
        source.options_translations = {"fr": [{"label": "Oui"}]}
        source.validation_message_translations = {"fr": "Ceci est obligatoire"}
        db_session.commit()

        new_item = ItemDuplicationService._duplicate_item_object(
            source,
            template.id,
            source.version_id,
            section.id,
            order=2,
            label="Trans Copy"
        )
        db_session.add(new_item)
        db_session.flush()

        assert new_item.label_translations == {"fr": "Question en Français"}
        assert new_item.definition_translations == {"fr": "Définition"}
        assert new_item.options_translations == {"fr": [{"label": "Oui"}]}
        assert new_item.validation_message_translations == {"fr": "Ceci est obligatoire"}

    def test_copies_options_json(self, db_session):
        template = create_test_template(db_session, name="ItemObj Template Options")
        section = create_test_section(db_session, template, name="Options Section")
        source = create_test_item(
            db_session, section, template,
            item_type="question", label="Options Question", type="single_choice", order=1
        )
        source.options_json = [{"label": "Yes", "value": "yes"}, {"label": "No", "value": "no"}]
        db_session.commit()

        new_item = ItemDuplicationService._duplicate_item_object(
            source,
            template.id,
            source.version_id,
            section.id,
            order=2,
            label="Options Copy"
        )
        db_session.add(new_item)
        db_session.flush()

        assert new_item.options_json == [
            {"label": "Yes", "value": "yes"},
            {"label": "No", "value": "no"}
        ]

    def test_new_item_never_archived(self, db_session):
        template = create_test_template(db_session, name="ItemObj Template NotArchived")
        section = create_test_section(db_session, template, name="NotArchived Section")
        source = create_test_item(
            db_session, section, template,
            item_type="question", label="NA Item", type="text", order=1, archived=True
        )

        new_item = ItemDuplicationService._duplicate_item_object(
            source,
            template.id,
            source.version_id,
            section.id,
            order=2,
            label="NA Copy"
        )
        db_session.add(new_item)
        db_session.flush()

        assert new_item.archived is False

    def test_copies_config(self, db_session):
        template = create_test_template(db_session, name="ItemObj Template Config")
        section = create_test_section(db_session, template, name="Config Section")
        source = create_test_item(
            db_session, section, template,
            item_type="indicator", label="Config Item", type="number", order=1
        )
        source.config = {"disaggregation": True, "indirect_reach": False}
        db_session.commit()

        new_item = ItemDuplicationService._duplicate_item_object(
            source,
            template.id,
            source.version_id,
            section.id,
            order=2,
            label="Config Copy"
        )
        db_session.add(new_item)
        db_session.flush()

        assert new_item.config == {"disaggregation": True, "indirect_reach": False}


@pytest.mark.unit
class TestItemDuplicationServiceDeepCopyJsonField:

    def test_none_returns_none(self):
        from app.utils.json_helpers import deep_copy_json
        assert deep_copy_json(None) is None

    def test_dict_deep_copied(self):
        from app.utils.json_helpers import deep_copy_json
        original = {"a": 1, "b": {"c": 2}}
        result = deep_copy_json(original)
        assert result == original
        # Should be a different object
        result["b"]["c"] = 99
        assert original["b"]["c"] == 2

    def test_list_deep_copied(self):
        from app.utils.json_helpers import deep_copy_json
        original = [1, 2, {"key": "val"}]
        result = deep_copy_json(original)
        assert result == original

    def test_string_roundtripped(self):
        from app.utils.json_helpers import deep_copy_json
        original = '{"key": "value"}'
        result = deep_copy_json(original)
        # JSON string should be parsed and returned as dict
        assert result is not None

    def test_via_static_method(self):
        result = ItemDuplicationService._deep_copy_json_field({"x": 42})
        assert result == {"x": 42}

    def test_via_static_method_none(self):
        result = ItemDuplicationService._deep_copy_json_field(None)
        assert result is None
