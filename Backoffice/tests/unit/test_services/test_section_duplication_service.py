"""
Comprehensive tests for app/services/section_duplication_service.py

Targets 100% coverage:
- SectionDuplicationService.duplicate_section
- SectionDuplicationService._get_section_hierarchy
- SectionDuplicationService._duplicate_section_object
- SectionDuplicationService._duplicate_section_items
"""
import json
import pytest

from app import db
from app.models import FormItem, FormSection
from app.services.forms.section_duplication_service import SectionDuplicationService
from tests.factories import (
    create_test_item,
    create_test_section,
    create_test_template,
)


@pytest.mark.unit
class TestSectionDuplicationServiceDuplicateSection:

    def test_raises_value_error_when_section_not_found(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            SectionDuplicationService.duplicate_section(99999)

    def test_duplicate_creates_new_section(self, db_session):
        template = create_test_template(db_session, name="Dup Test Template 1")
        section = create_test_section(db_session, template, name="Source A", order=1)
        before = db_session.query(FormSection).count()

        new_sec, _ = SectionDuplicationService.duplicate_section(section.id)
        db_session.commit()

        assert db_session.query(FormSection).count() == before + 1
        assert new_sec.id != section.id

    def test_duplicate_adds_copy_suffix_to_name(self, db_session):
        template = create_test_template(db_session, name="Dup Test Template Copy Suffix")
        section = create_test_section(db_session, template, name="My Section", order=1)

        new_sec, _ = SectionDuplicationService.duplicate_section(section.id)
        db_session.commit()

        assert "My Section" in new_sec.name
        assert "Copy" in new_sec.name

    def test_duplicate_copy_suffix_increments_on_collision(self, db_session):
        template = create_test_template(db_session, name="Dup Test Template Collision")
        section = create_test_section(db_session, template, name="Collision Section", order=1)

        # Create the first copy manually
        first_copy, _ = SectionDuplicationService.duplicate_section(section.id)
        db_session.commit()

        # Duplicate again - should create Copy 2
        second_copy, _ = SectionDuplicationService.duplicate_section(section.id)
        db_session.commit()

        assert "Copy 2" in second_copy.name

    def test_duplicate_inherits_template_and_version(self, db_session):
        template = create_test_template(db_session, name="Dup Test Template Inherit")
        section = create_test_section(db_session, template, name="Inherit Section", order=2)

        new_sec, _ = SectionDuplicationService.duplicate_section(section.id)
        db_session.commit()

        assert new_sec.template_id == template.id
        assert new_sec.version_id == section.version_id

    def test_duplicate_copies_items(self, db_session):
        template = create_test_template(db_session, name="Dup Test Template Items")
        section = create_test_section(db_session, template, name="Section With Items", order=1)
        create_test_item(db_session, section, template, item_type="question", label="Item 1", type="text", order=1)
        create_test_item(db_session, section, template, item_type="question", label="Item 2", type="text", order=2)

        new_sec, _ = SectionDuplicationService.duplicate_section(section.id)
        db_session.commit()

        copied = (
            db_session.query(FormItem)
            .filter_by(section_id=new_sec.id, archived=False)
            .order_by(FormItem.order)
            .all()
        )
        assert len(copied) == 2
        assert copied[0].label == "Item 1"
        assert copied[1].label == "Item 2"

    def test_duplicate_preserves_section_type(self, db_session):
        template = create_test_template(db_session, name="Dup Test Template SectionType")
        section = create_test_section(
            db_session, template, name="Dynamic Section", order=1, section_type="dynamic_indicators"
        )
        new_sec, _ = SectionDuplicationService.duplicate_section(section.id)
        db_session.commit()

        assert new_sec.section_type == "dynamic_indicators"

    def test_duplicate_section_not_archived(self, db_session):
        template = create_test_template(db_session, name="Dup Test Template Archived")
        section = create_test_section(db_session, template, name="Non-Archived Source", order=1)

        new_sec, _ = SectionDuplicationService.duplicate_section(section.id)
        db_session.commit()

        assert new_sec.archived is False

    def test_duplicate_order_placed_after_last_top_level(self, db_session):
        template = create_test_template(db_session, name="Dup Test Template Order")
        sec1 = create_test_section(db_session, template, name="Section 1", order=1)
        sec2 = create_test_section(db_session, template, name="Section 2", order=2)

        new_sec, _ = SectionDuplicationService.duplicate_section(sec1.id)
        db_session.commit()

        # New section should have order > existing max (2)
        assert new_sec.order >= 3

    def test_duplicate_preserves_config(self, db_session):
        template = create_test_template(db_session, name="Dup Test Template Config")
        section = create_test_section(db_session, template, name="Config Section", order=1)
        # Set config directly
        section.config = {"key": "value", "nested": {"a": 1}}
        db_session.commit()

        new_sec, _ = SectionDuplicationService.duplicate_section(section.id)
        db_session.commit()

        assert new_sec.config == {"key": "value", "nested": {"a": 1}}

    def test_duplicate_preserves_allow_data_not_available(self, db_session):
        template = create_test_template(db_session, name="Dup Test Template DataNA")
        section = create_test_section(db_session, template, name="DataNA Section", order=1)
        section.allow_data_not_available = True
        db_session.commit()

        new_sec, _ = SectionDuplicationService.duplicate_section(section.id)
        db_session.commit()

        assert new_sec.allow_data_not_available is True

    def test_duplicate_preserves_allow_not_applicable(self, db_session):
        template = create_test_template(db_session, name="Dup Test Template NotAppl")
        section = create_test_section(db_session, template, name="NotAppl Section", order=1)
        section.allow_not_applicable = True
        db_session.commit()

        new_sec, _ = SectionDuplicationService.duplicate_section(section.id)
        db_session.commit()

        assert new_sec.allow_not_applicable is True

    def test_returns_section_id_map(self, db_session):
        template = create_test_template(db_session, name="Dup Test Template IDMap")
        section = create_test_section(db_session, template, name="IDMap Section", order=1)

        _, section_id_map = SectionDuplicationService.duplicate_section(section.id)
        db_session.commit()

        assert section.id in section_id_map
        assert section_id_map[section.id] != section.id


@pytest.mark.unit
class TestSectionDuplicationServiceSubsections:

    def test_duplicate_subsection_preserves_parent(self, db_session):
        template = create_test_template(db_session, name="Subsec Template Parent")
        parent = create_test_section(db_session, template, name="Parent Section", order=1)
        child = create_test_section(
            db_session, template, name="Child Section", order=1,
            parent_section_id=parent.id
        )

        new_child, _ = SectionDuplicationService.duplicate_section(child.id)
        db_session.commit()

        assert new_child.parent_section_id == parent.id

    def test_duplicate_section_with_nested_subsections(self, db_session):
        template = create_test_template(db_session, name="Nested Subsec Template")
        parent = create_test_section(db_session, template, name="Parent Nested", order=1)
        child = create_test_section(
            db_session, template, name="Child Nested", order=1,
            parent_section_id=parent.id
        )
        grandchild = create_test_section(
            db_session, template, name="Grandchild", order=1,
            parent_section_id=child.id
        )

        before_count = db_session.query(FormSection).count()
        new_parent, section_id_map = SectionDuplicationService.duplicate_section(parent.id)
        db_session.commit()

        # Should have duplicated parent + child + grandchild = 3 more sections
        assert db_session.query(FormSection).count() == before_count + 3
        # All original IDs should be in the map
        assert parent.id in section_id_map
        assert child.id in section_id_map
        assert grandchild.id in section_id_map

    def test_duplicate_nested_subsection_items(self, db_session):
        template = create_test_template(db_session, name="Nested Items Template")
        parent = create_test_section(db_session, template, name="Parent Items", order=1)
        child = create_test_section(
            db_session, template, name="Child Items", order=1,
            parent_section_id=parent.id
        )
        create_test_item(
            db_session, child, template,
            item_type="question", label="Child Item", type="text", order=1
        )

        new_parent, section_id_map = SectionDuplicationService.duplicate_section(parent.id)
        db_session.commit()

        new_child_id = section_id_map.get(child.id)
        assert new_child_id is not None

        child_items = (
            db_session.query(FormItem)
            .filter_by(section_id=new_child_id, archived=False)
            .all()
        )
        assert len(child_items) == 1
        assert child_items[0].label == "Child Item"


@pytest.mark.unit
class TestSectionDuplicationServiceGetHierarchy:

    def test_hierarchy_returns_single_section_for_leaf(self, db_session):
        template = create_test_template(db_session, name="Hierarchy Template Leaf")
        section = create_test_section(db_session, template, name="Leaf Section", order=1)

        result = SectionDuplicationService._get_section_hierarchy(section.id)

        assert len(result) == 1
        assert result[0].id == section.id

    def test_hierarchy_includes_children(self, db_session):
        template = create_test_template(db_session, name="Hierarchy Template Children")
        parent = create_test_section(db_session, template, name="H Parent", order=1)
        child1 = create_test_section(
            db_session, template, name="H Child 1", order=1,
            parent_section_id=parent.id
        )
        child2 = create_test_section(
            db_session, template, name="H Child 2", order=2,
            parent_section_id=parent.id
        )

        result = SectionDuplicationService._get_section_hierarchy(parent.id)
        ids = [s.id for s in result]

        assert parent.id in ids
        assert child1.id in ids
        assert child2.id in ids

    def test_hierarchy_returns_empty_for_missing_section(self, db_session):
        result = SectionDuplicationService._get_section_hierarchy(99999)
        assert result == []


@pytest.mark.unit
class TestSectionDuplicationServiceDuplicateSectionObject:

    def test_creates_section_with_correct_attributes(self, db_session):
        template = create_test_template(db_session, name="DupObj Template")
        section = create_test_section(
            db_session, template, name="Obj Source Section", order=2
        )
        section.allow_data_not_available = True
        section.section_type = "standard"
        db_session.commit()

        version_id = section.version_id

        new_sec = SectionDuplicationService._duplicate_section_object(
            section,
            template.id,
            version_id,
            is_root=True,
            order_offset=0.0,
            original_parent_id=None
        )
        db_session.add(new_sec)
        db_session.flush()

        assert new_sec.template_id == template.id
        assert new_sec.version_id == version_id
        assert "Obj Source Section" in new_sec.name
        assert new_sec.archived is False

    def test_order_offset_applied(self, db_session):
        template = create_test_template(db_session, name="DupObj Template Offset")
        section = create_test_section(db_session, template, name="Offset Section", order=5)
        version_id = section.version_id

        new_sec = SectionDuplicationService._duplicate_section_object(
            section,
            template.id,
            version_id,
            is_root=False,
            order_offset=3.0,
        )
        db_session.add(new_sec)
        db_session.flush()

        # order = 5 + 3 = 8
        assert new_sec.order == 8

    def test_root_subsection_uses_plus_one_order(self, db_session):
        template = create_test_template(db_session, name="DupObj Template Subsec")
        parent = create_test_section(db_session, template, name="SubParent", order=1)
        child = create_test_section(
            db_session, template, name="SubChild", order=3,
            parent_section_id=parent.id
        )
        version_id = child.version_id

        new_sec = SectionDuplicationService._duplicate_section_object(
            child,
            template.id,
            version_id,
            is_root=True,
            order_offset=0.0,
            original_parent_id=parent.id
        )
        db_session.add(new_sec)
        db_session.flush()

        # order = 3 + 1 = 4
        assert new_sec.order == 4

    def test_name_translations_copied(self, db_session):
        template = create_test_template(db_session, name="DupObj Translations Template")
        section = create_test_section(db_session, template, name="Trans Section", order=1)
        section.name_translations = {"fr": "Section Traduite"}
        db_session.commit()

        new_sec = SectionDuplicationService._duplicate_section_object(
            section,
            template.id,
            section.version_id,
            is_root=True,
            order_offset=0.0,
        )
        db_session.add(new_sec)
        db_session.flush()

        assert new_sec.name_translations == {"fr": "Section Traduite"}

    def test_config_none_stays_none(self, db_session):
        template = create_test_template(db_session, name="DupObj No Config Template")
        section = create_test_section(db_session, template, name="No Config Section", order=1)
        section.config = None
        db_session.commit()

        new_sec = SectionDuplicationService._duplicate_section_object(
            section,
            template.id,
            section.version_id,
            is_root=True,
            order_offset=0.0,
        )
        db_session.add(new_sec)
        db_session.flush()

        assert new_sec.config is None


@pytest.mark.unit
class TestSectionDuplicationServiceDuplicateSectionItems:

    def test_copies_all_non_archived_items(self, db_session):
        template = create_test_template(db_session, name="DupItems Template")
        source_section = create_test_section(db_session, template, name="Source Items Section", order=1)
        target_section = create_test_section(db_session, template, name="Target Items Section", order=2)

        create_test_item(
            db_session, source_section, template,
            item_type="indicator", label="Item A", type="number", order=1
        )
        create_test_item(
            db_session, source_section, template,
            item_type="question", label="Item B", type="text", order=2
        )

        SectionDuplicationService._duplicate_section_items(
            source_section.id,
            target_section.id,
            template.id,
            source_section.version_id
        )
        db_session.flush()

        target_items = (
            db_session.query(FormItem)
            .filter_by(section_id=target_section.id)
            .order_by(FormItem.order)
            .all()
        )
        assert len(target_items) == 2
        assert target_items[0].label == "Item A"
        assert target_items[1].label == "Item B"

    def test_copies_also_archived_items(self, db_session):
        template = create_test_template(db_session, name="DupItems Template Archived")
        source_section = create_test_section(db_session, template, name="Archived Source", order=1)
        target_section = create_test_section(db_session, template, name="Archived Target", order=2)

        create_test_item(
            db_session, source_section, template,
            item_type="question", label="Active", type="text", order=1
        )
        create_test_item(
            db_session, source_section, template,
            item_type="question", label="Archived", type="text", order=2, archived=True
        )

        SectionDuplicationService._duplicate_section_items(
            source_section.id,
            target_section.id,
            template.id,
            source_section.version_id
        )
        db_session.flush()

        target_items = (
            db_session.query(FormItem)
            .filter_by(section_id=target_section.id)
            .all()
        )
        # Both items should be copied but new ones are NOT archived
        assert len(target_items) == 2
        for item in target_items:
            assert item.archived is False

    def test_copies_item_translations(self, db_session):
        template = create_test_template(db_session, name="DupItems Translations Template")
        source_section = create_test_section(db_session, template, name="Trans Source", order=1)
        target_section = create_test_section(db_session, template, name="Trans Target", order=2)

        item = create_test_item(
            db_session, source_section, template,
            item_type="question", label="Trans Item", type="text", order=1
        )
        item.label_translations = {"fr": "Question en Français"}
        item.definition_translations = {"fr": "Définition"}
        item.options_translations = {"fr": [{"label": "Oui", "value": "yes"}]}
        db_session.commit()

        SectionDuplicationService._duplicate_section_items(
            source_section.id,
            target_section.id,
            template.id,
            source_section.version_id
        )
        db_session.flush()

        target_items = (
            db_session.query(FormItem)
            .filter_by(section_id=target_section.id)
            .all()
        )
        assert len(target_items) == 1
        assert target_items[0].label_translations == {"fr": "Question en Français"}
        assert target_items[0].definition_translations == {"fr": "Définition"}

    def test_copies_options_json(self, db_session):
        template = create_test_template(db_session, name="DupItems OptionsJSON Template")
        source_section = create_test_section(db_session, template, name="OptionsJSON Source", order=1)
        target_section = create_test_section(db_session, template, name="OptionsJSON Target", order=2)

        item = create_test_item(
            db_session, source_section, template,
            item_type="question", label="Options Item", type="single_choice", order=1
        )
        item.options_json = [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}]
        db_session.commit()

        SectionDuplicationService._duplicate_section_items(
            source_section.id,
            target_section.id,
            template.id,
            source_section.version_id
        )
        db_session.flush()

        target_items = (
            db_session.query(FormItem)
            .filter_by(section_id=target_section.id)
            .all()
        )
        assert len(target_items) == 1
        assert target_items[0].options_json == [
            {"label": "A", "value": "a"},
            {"label": "B", "value": "b"}
        ]

    def test_empty_source_section_no_items_copied(self, db_session):
        template = create_test_template(db_session, name="DupItems Empty Template")
        source_section = create_test_section(db_session, template, name="Empty Source", order=1)
        target_section = create_test_section(db_session, template, name="Empty Target", order=2)

        SectionDuplicationService._duplicate_section_items(
            source_section.id,
            target_section.id,
            template.id,
            source_section.version_id
        )
        db_session.flush()

        target_items = (
            db_session.query(FormItem)
            .filter_by(section_id=target_section.id)
            .all()
        )
        assert len(target_items) == 0

    def test_copies_config_json(self, db_session):
        template = create_test_template(db_session, name="DupItems Config Template")
        source_section = create_test_section(db_session, template, name="Config Source", order=1)
        target_section = create_test_section(db_session, template, name="Config Target", order=2)

        item = create_test_item(
            db_session, source_section, template,
            item_type="indicator", label="Config Item", type="number", order=1
        )
        item.config = {"allow_disaggregation": True}
        db_session.commit()

        SectionDuplicationService._duplicate_section_items(
            source_section.id,
            target_section.id,
            template.id,
            source_section.version_id
        )
        db_session.flush()

        target_items = (
            db_session.query(FormItem)
            .filter_by(section_id=target_section.id)
            .all()
        )
        assert len(target_items) == 1
        assert target_items[0].config == {"allow_disaggregation": True}
