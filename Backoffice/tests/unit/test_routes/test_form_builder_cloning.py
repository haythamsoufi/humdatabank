"""Unit tests for app.routes.admin.form_builder.helpers.cloning."""
import json
import pytest
from unittest.mock import patch, MagicMock

pytestmark = [pytest.mark.unit]

from app.routes.admin.form_builder.helpers.cloning import (
    _parse_rule_payload,
    _remap_item_ref,
    _remap_ids_in_obj,
    _remap_rule_payload_to_string,
    _clone_template_structure,
    _clone_template_structure_between_templates,
)
from tests.factories import (
    create_test_template,
    create_test_section,
    create_test_item,
    create_test_draft_version,
)


# ---------------------------------------------------------------------------
# _parse_rule_payload — pure logic, no DB needed
# ---------------------------------------------------------------------------

class TestParseRulePayload:
    def test_returns_none_for_none_input(self):
        assert _parse_rule_payload(None) is None

    def test_returns_deep_copy_for_dict(self):
        original = {"conditions": [{"item_id": "1"}]}
        result = _parse_rule_payload(original)
        assert result == original
        assert result is not original  # deep copy

    def test_returns_deep_copy_for_list(self):
        original = [{"item_id": "1"}]
        result = _parse_rule_payload(original)
        assert result == original
        assert result is not original

    def test_returns_none_for_non_string_non_dict(self):
        assert _parse_rule_payload(42) is None
        assert _parse_rule_payload(3.14) is None

    def test_returns_none_for_empty_string(self):
        assert _parse_rule_payload("") is None
        assert _parse_rule_payload("   ") is None

    def test_returns_none_for_empty_object_string(self):
        assert _parse_rule_payload("{}") is None
        assert _parse_rule_payload("null") is None

    def test_parses_valid_json_string(self):
        payload = json.dumps({"conditions": [{"item_id": "66"}]})
        result = _parse_rule_payload(payload)
        assert result == {"conditions": [{"item_id": "66"}]}

    def test_parses_double_encoded_json(self):
        inner = json.dumps({"conditions": [{"item_id": "66"}]})
        double_encoded = json.dumps(inner)
        result = _parse_rule_payload(double_encoded)
        assert result == {"conditions": [{"item_id": "66"}]}

    def test_returns_none_for_invalid_json(self):
        result = _parse_rule_payload("not-valid-json{{{")
        assert result is None

    def test_returns_none_for_double_encoded_invalid_inner(self):
        payload = json.dumps("not-valid-json")
        result = _parse_rule_payload(payload)
        assert result is None

    def test_parses_json_list_string(self):
        payload = json.dumps([{"item_id": "1"}])
        result = _parse_rule_payload(payload)
        assert result == [{"item_id": "1"}]


# ---------------------------------------------------------------------------
# _remap_item_ref — pure logic, no DB needed
# ---------------------------------------------------------------------------

class TestRemapItemRef:
    def test_returns_none_for_none(self):
        assert _remap_item_ref(None, {}) is None

    def test_remaps_integer_id(self):
        result = _remap_item_ref(10, {10: 99})
        assert result == "99"

    def test_integer_id_not_in_map_returns_original_as_string(self):
        result = _remap_item_ref(10, {})
        assert result == "10"

    def test_returns_non_string_non_int_as_is(self):
        result = _remap_item_ref([1, 2], {})
        assert result == [1, 2]

    def test_empty_string_returns_empty(self):
        result = _remap_item_ref("", {10: 99})
        assert result == ""

    def test_numeric_string_remaps(self):
        result = _remap_item_ref("66", {66: 200})
        assert result == "200"

    def test_numeric_string_not_in_map(self):
        result = _remap_item_ref("66", {})
        assert result == "66"

    def test_plugin_ref_remaps_numeric_part(self):
        result = _remap_item_ref("plugin_123", {123: 500})
        assert result == "plugin_500"

    def test_plugin_ref_with_suffix_remaps(self):
        result = _remap_item_ref("plugin_123_measure_name", {123: 500})
        assert result == "plugin_500_measure_name"

    def test_plugin_ref_not_in_map_returns_original(self):
        result = _remap_item_ref("plugin_999", {})
        assert result == "plugin_999"

    def test_legacy_question_prefix(self):
        result = _remap_item_ref("question_66", {66: 200})
        assert result == "200"

    def test_legacy_indicator_prefix(self):
        result = _remap_item_ref("indicator_66", {66: 300})
        assert result == "300"

    def test_legacy_document_field_prefix(self):
        result = _remap_item_ref("document_field_66", {66: 400})
        assert result == "400"

    def test_legacy_matrix_prefix(self):
        result = _remap_item_ref("matrix_66", {66: 500})
        assert result == "500"

    def test_legacy_form_item_prefix(self):
        result = _remap_item_ref("form_item_66", {66: 600})
        assert result == "600"

    def test_legacy_prefix_not_in_map(self):
        result = _remap_item_ref("question_66", {})
        assert result == "66"

    def test_plain_string_not_numeric_not_plugin_returns_as_is(self):
        result = _remap_item_ref("some_other_value", {})
        assert result == "some_other_value"

    def test_string_with_leading_whitespace(self):
        result = _remap_item_ref("  66  ", {66: 200})
        assert result == "200"


# ---------------------------------------------------------------------------
# _remap_ids_in_obj — pure logic, no DB needed
# ---------------------------------------------------------------------------

class TestRemapIdsInObj:
    def test_list_remaps_recursively(self):
        obj = [{"item_id": "10"}]
        result = _remap_ids_in_obj(obj, {10: 99})
        assert result[0]["item_id"] == "99"

    def test_dict_remaps_item_id(self):
        obj = {"item_id": "5", "other": "keep"}
        result = _remap_ids_in_obj(obj, {5: 50})
        assert result["item_id"] == "50"
        assert result["other"] == "keep"

    def test_dict_remaps_field_id(self):
        obj = {"field_id": "7"}
        result = _remap_ids_in_obj(obj, {7: 77})
        assert result["field_id"] == "77"

    def test_dict_remaps_field(self):
        obj = {"field": "3"}
        result = _remap_ids_in_obj(obj, {3: 33})
        assert result["field"] == "33"

    def test_dict_remaps_value_field_id(self):
        obj = {"value_field_id": "8"}
        result = _remap_ids_in_obj(obj, {8: 88})
        assert result["value_field_id"] == "88"

    def test_scalar_returns_as_is(self):
        assert _remap_ids_in_obj("hello", {}) == "hello"
        assert _remap_ids_in_obj(42, {}) == 42
        assert _remap_ids_in_obj(None, {}) is None

    def test_nested_structure(self):
        obj = {"conditions": [{"item_id": "1"}, {"item_id": "2"}]}
        result = _remap_ids_in_obj(obj, {1: 10, 2: 20})
        assert result["conditions"][0]["item_id"] == "10"
        assert result["conditions"][1]["item_id"] == "20"

    def test_non_id_keys_recurse_but_not_remap(self):
        obj = {"nested": {"item_id": "5"}}
        result = _remap_ids_in_obj(obj, {5: 50})
        assert result["nested"]["item_id"] == "50"


# ---------------------------------------------------------------------------
# _remap_rule_payload_to_string — pure logic, no DB needed
# ---------------------------------------------------------------------------

class TestRemapRulePayloadToString:
    def test_returns_original_when_unparsable(self):
        result = _remap_rule_payload_to_string("invalid{{json", {})
        assert result == "invalid{{json"

    def test_returns_original_when_none(self):
        result = _remap_rule_payload_to_string(None, {})
        assert result is None

    def test_remaps_ids_and_returns_json_string(self):
        payload = json.dumps({"conditions": [{"item_id": "10"}]})
        result = _remap_rule_payload_to_string(payload, {10: 99})
        parsed = json.loads(result)
        assert parsed["conditions"][0]["item_id"] == "99"

    def test_returns_json_string_even_when_no_remapping(self):
        payload = json.dumps({"conditions": [{"item_id": "10"}]})
        result = _remap_rule_payload_to_string(payload, {})
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed["conditions"][0]["item_id"] == "10"


# ---------------------------------------------------------------------------
# _clone_template_structure (integration with DB)
# ---------------------------------------------------------------------------

class TestCloneTemplateStructure:
    def test_clones_empty_template(self, app, db_session):
        from app.models import FormTemplateVersion
        template = create_test_template(db_session)
        pub_version = db_session.query(FormTemplateVersion).filter_by(
            id=template.published_version_id
        ).first()

        draft = create_test_draft_version(db_session, template)

        # Should complete without error (no pages/sections/items)
        _clone_template_structure(template.id, pub_version.id, draft.id)
        db_session.flush()

    def test_clones_pages(self, app, db_session):
        from app.models import FormPage, FormTemplateVersion
        template = create_test_template(db_session)
        pub_version = db_session.query(FormTemplateVersion).filter_by(
            id=template.published_version_id
        ).first()

        page = FormPage(
            template_id=template.id,
            version_id=pub_version.id,
            name="Page 1",
            order=1
        )
        db_session.add(page)
        db_session.flush()

        draft = create_test_draft_version(db_session, template)
        _clone_template_structure(template.id, pub_version.id, draft.id)
        db_session.flush()

        cloned_pages = FormPage.query.filter_by(
            template_id=template.id,
            version_id=draft.id
        ).all()
        assert len(cloned_pages) == 1
        assert cloned_pages[0].name == "Page 1"

    def test_clones_sections_with_parent_relationships(self, app, db_session):
        from app.models import FormSection, FormTemplateVersion
        template = create_test_template(db_session)
        pub_version = db_session.query(FormTemplateVersion).filter_by(
            id=template.published_version_id
        ).first()

        parent_sec = FormSection(
            template_id=template.id,
            version_id=pub_version.id,
            name="Parent Section",
            order=1
        )
        db_session.add(parent_sec)
        db_session.flush()

        child_sec = FormSection(
            template_id=template.id,
            version_id=pub_version.id,
            name="Child Section",
            order=1,
            parent_section_id=parent_sec.id
        )
        db_session.add(child_sec)
        db_session.flush()

        draft = create_test_draft_version(db_session, template)
        _clone_template_structure(template.id, pub_version.id, draft.id)
        db_session.flush()

        cloned_sections = FormSection.query.filter_by(
            template_id=template.id,
            version_id=draft.id
        ).order_by(FormSection.order).all()
        assert len(cloned_sections) == 2
        child_clone = next((s for s in cloned_sections if s.name == "Child Section"), None)
        assert child_clone is not None
        assert child_clone.parent_section_id is not None

    def test_clones_items_with_relevance_conditions(self, app, db_session):
        from app.models import FormSection, FormItem, FormTemplateVersion
        template = create_test_template(db_session)
        pub_version = db_session.query(FormTemplateVersion).filter_by(
            id=template.published_version_id
        ).first()

        sec = FormSection(
            template_id=template.id,
            version_id=pub_version.id,
            name="Section A",
            order=1
        )
        db_session.add(sec)
        db_session.flush()

        item1 = FormItem(
            template_id=template.id,
            version_id=pub_version.id,
            section_id=sec.id,
            item_type='indicator',
            label='Item 1',
            order=1,
            type='number'
        )
        db_session.add(item1)
        db_session.flush()

        condition = json.dumps({"conditions": [{"item_id": str(item1.id)}]})
        item2 = FormItem(
            template_id=template.id,
            version_id=pub_version.id,
            section_id=sec.id,
            item_type='indicator',
            label='Item 2',
            order=2,
            type='number',
            relevance_condition=condition
        )
        db_session.add(item2)
        db_session.flush()

        draft = create_test_draft_version(db_session, template)
        _clone_template_structure(template.id, pub_version.id, draft.id)
        db_session.flush()

        cloned_items = FormItem.query.filter_by(
            template_id=template.id,
            version_id=draft.id
        ).order_by(FormItem.order).all()
        assert len(cloned_items) == 2

        item2_clone = next((it for it in cloned_items if it.label == 'Item 2'), None)
        assert item2_clone is not None
        assert item2_clone.relevance_condition is not None
        cond_data = json.loads(item2_clone.relevance_condition)
        new_item1 = next((it for it in cloned_items if it.label == 'Item 1'), None)
        assert str(new_item1.id) == cond_data["conditions"][0]["item_id"]

    def test_clones_items_with_validation_conditions(self, app, db_session):
        from app.models import FormSection, FormItem, FormTemplateVersion
        template = create_test_template(db_session)
        pub_version = db_session.query(FormTemplateVersion).filter_by(
            id=template.published_version_id
        ).first()

        sec = FormSection(
            template_id=template.id,
            version_id=pub_version.id,
            name="Section B",
            order=1
        )
        db_session.add(sec)
        db_session.flush()

        item1 = FormItem(
            template_id=template.id,
            version_id=pub_version.id,
            section_id=sec.id,
            item_type='indicator',
            label='Val Item 1',
            order=1,
            type='number'
        )
        db_session.add(item1)
        db_session.flush()

        condition = json.dumps({"conditions": [{"item_id": str(item1.id)}]})
        item2 = FormItem(
            template_id=template.id,
            version_id=pub_version.id,
            section_id=sec.id,
            item_type='indicator',
            label='Val Item 2',
            order=2,
            type='number',
            validation_condition=condition
        )
        db_session.add(item2)
        db_session.flush()

        draft = create_test_draft_version(db_session, template)
        _clone_template_structure(template.id, pub_version.id, draft.id)
        db_session.flush()

        cloned_items = FormItem.query.filter_by(
            template_id=template.id,
            version_id=draft.id
        ).order_by(FormItem.order).all()

        item2_clone = next((it for it in cloned_items if it.label == 'Val Item 2'), None)
        assert item2_clone is not None
        assert item2_clone.validation_condition is not None

    def test_clones_section_relevance_condition(self, app, db_session):
        from app.models import FormSection, FormItem, FormTemplateVersion
        template = create_test_template(db_session)
        pub_version = db_session.query(FormTemplateVersion).filter_by(
            id=template.published_version_id
        ).first()

        sec = FormSection(
            template_id=template.id,
            version_id=pub_version.id,
            name="Section C",
            order=1
        )
        db_session.add(sec)
        db_session.flush()

        item = FormItem(
            template_id=template.id,
            version_id=pub_version.id,
            section_id=sec.id,
            item_type='indicator',
            label='Item for Sec Cond',
            order=1,
            type='number'
        )
        db_session.add(item)
        db_session.flush()

        condition = json.dumps({"conditions": [{"item_id": str(item.id)}]})
        sec.relevance_condition = condition
        db_session.flush()

        draft = create_test_draft_version(db_session, template)
        _clone_template_structure(template.id, pub_version.id, draft.id)
        db_session.flush()

        cloned_sections = FormSection.query.filter_by(
            template_id=template.id,
            version_id=draft.id
        ).all()
        cloned_sec = next((s for s in cloned_sections if s.name == "Section C"), None)
        assert cloned_sec is not None
        assert cloned_sec.relevance_condition is not None

    def test_clones_items_with_config(self, app, db_session):
        from app.models import FormSection, FormItem, FormTemplateVersion
        template = create_test_template(db_session)
        pub_version = db_session.query(FormTemplateVersion).filter_by(
            id=template.published_version_id
        ).first()

        sec = FormSection(
            template_id=template.id,
            version_id=pub_version.id,
            name="Section D",
            order=1
        )
        db_session.add(sec)
        db_session.flush()

        item = FormItem(
            template_id=template.id,
            version_id=pub_version.id,
            section_id=sec.id,
            item_type='indicator',
            label='Config Item',
            order=1,
            type='number',
            config={"is_required": True, "layout_column_width": 6}
        )
        db_session.add(item)
        db_session.flush()

        draft = create_test_draft_version(db_session, template)
        _clone_template_structure(template.id, pub_version.id, draft.id)
        db_session.flush()

        cloned_items = FormItem.query.filter_by(
            template_id=template.id,
            version_id=draft.id
        ).all()
        assert len(cloned_items) == 1
        assert cloned_items[0].config == {"is_required": True, "layout_column_width": 6}
        assert cloned_items[0].config is not item.config


# ---------------------------------------------------------------------------
# _clone_template_structure_between_templates
# ---------------------------------------------------------------------------

class TestCloneTemplateStructureBetweenTemplates:
    def test_clones_to_different_template(self, app, db_session):
        from app.models import FormSection, FormItem, FormTemplateVersion
        src_template = create_test_template(db_session)
        tgt_template = create_test_template(db_session)

        src_version = db_session.query(FormTemplateVersion).filter_by(
            id=src_template.published_version_id
        ).first()
        tgt_version = create_test_draft_version(db_session, tgt_template)

        sec = FormSection(
            template_id=src_template.id,
            version_id=src_version.id,
            name="Source Section",
            order=1
        )
        db_session.add(sec)
        db_session.flush()

        item = FormItem(
            template_id=src_template.id,
            version_id=src_version.id,
            section_id=sec.id,
            item_type='indicator',
            label='Source Item',
            order=1,
            type='number'
        )
        db_session.add(item)
        db_session.flush()

        _clone_template_structure_between_templates(
            source_template_id=src_template.id,
            source_version_id=src_version.id,
            target_template_id=tgt_template.id,
            target_version_id=tgt_version.id
        )
        db_session.flush()

        cloned_sections = FormSection.query.filter_by(
            template_id=tgt_template.id,
            version_id=tgt_version.id
        ).all()
        assert len(cloned_sections) == 1
        assert cloned_sections[0].name == "Source Section"
        assert cloned_sections[0].template_id == tgt_template.id

        cloned_items = FormItem.query.filter_by(
            template_id=tgt_template.id,
            version_id=tgt_version.id
        ).all()
        assert len(cloned_items) == 1
        assert cloned_items[0].label == "Source Item"

    def test_clones_with_conditions_remapped(self, app, db_session):
        from app.models import FormSection, FormItem, FormTemplateVersion
        src_template = create_test_template(db_session)
        tgt_template = create_test_template(db_session)

        src_version = db_session.query(FormTemplateVersion).filter_by(
            id=src_template.published_version_id
        ).first()
        tgt_version = create_test_draft_version(db_session, tgt_template)

        sec = FormSection(
            template_id=src_template.id,
            version_id=src_version.id,
            name="Src Sec",
            order=1
        )
        db_session.add(sec)
        db_session.flush()

        item1 = FormItem(
            template_id=src_template.id,
            version_id=src_version.id,
            section_id=sec.id,
            item_type='indicator',
            label='Src Item 1',
            order=1,
            type='number'
        )
        db_session.add(item1)
        db_session.flush()

        condition = json.dumps({"conditions": [{"item_id": str(item1.id)}]})
        item2 = FormItem(
            template_id=src_template.id,
            version_id=src_version.id,
            section_id=sec.id,
            item_type='indicator',
            label='Src Item 2',
            order=2,
            type='number',
            relevance_condition=condition
        )
        db_session.add(item2)
        db_session.flush()

        _clone_template_structure_between_templates(
            source_template_id=src_template.id,
            source_version_id=src_version.id,
            target_template_id=tgt_template.id,
            target_version_id=tgt_version.id
        )
        db_session.flush()

        cloned_items = FormItem.query.filter_by(
            template_id=tgt_template.id,
            version_id=tgt_version.id
        ).order_by(FormItem.order).all()
        assert len(cloned_items) == 2

        item2_clone = next((it for it in cloned_items if it.label == 'Src Item 2'), None)
        assert item2_clone.relevance_condition is not None
        cond_data = json.loads(item2_clone.relevance_condition)
        item1_clone = next((it for it in cloned_items if it.label == 'Src Item 1'), None)
        assert str(item1_clone.id) == cond_data["conditions"][0]["item_id"]

    def test_clones_parent_section_relationships(self, app, db_session):
        from app.models import FormSection, FormTemplateVersion
        src_template = create_test_template(db_session)
        tgt_template = create_test_template(db_session)

        src_version = db_session.query(FormTemplateVersion).filter_by(
            id=src_template.published_version_id
        ).first()
        tgt_version = create_test_draft_version(db_session, tgt_template)

        parent = FormSection(
            template_id=src_template.id,
            version_id=src_version.id,
            name="Parent",
            order=1
        )
        db_session.add(parent)
        db_session.flush()

        child = FormSection(
            template_id=src_template.id,
            version_id=src_version.id,
            name="Child",
            order=1,
            parent_section_id=parent.id
        )
        db_session.add(child)
        db_session.flush()

        _clone_template_structure_between_templates(
            source_template_id=src_template.id,
            source_version_id=src_version.id,
            target_template_id=tgt_template.id,
            target_version_id=tgt_version.id
        )
        db_session.flush()

        cloned = FormSection.query.filter_by(
            template_id=tgt_template.id,
            version_id=tgt_version.id
        ).all()
        assert len(cloned) == 2
        child_clone = next((s for s in cloned if s.name == "Child"), None)
        assert child_clone.parent_section_id is not None
