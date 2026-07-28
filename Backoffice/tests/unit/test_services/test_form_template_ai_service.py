"""Unit tests for FormTemplateAIService (AI form-builder assistant).

Covers: canonical schema -> models (create_template), edit operations
(apply_edits), skip-logic/validation rule normalization, draft-only and
RBAC safety invariants, translations, and draft discard.
"""

import json
import uuid
from unittest.mock import patch

import pytest

from app.models import (
    FormItem,
    FormPage,
    FormSection,
    FormTemplate,
    FormTemplateVersion,
    IndicatorBank,
)
from app.services.forms.template_ai_service import (
    FormTemplateAIError,
    FormTemplateAIService,
)

from tests.factories import (
    create_test_item,
    create_test_section,
    create_test_template,
    create_test_user,
)


AUTHZ = "app.services.organization.authorization_service.AuthorizationService"


@pytest.fixture
def service():
    return FormTemplateAIService()


@pytest.fixture
def user(db_session):
    return create_test_user(db_session)


@pytest.fixture
def grant_all_rbac():
    """Allow every RBAC permission + template access for the duration of a test."""
    with patch(f"{AUTHZ}.has_rbac_permission", return_value=True), \
         patch(f"{AUTHZ}.check_template_access", return_value=True):
        yield


def _make_indicator_bank(db_session):
    bank = IndicatorBank(
        name=f"AI Test Indicator {uuid.uuid4().hex[:8]}",
        definition="Test indicator",
        type="number",
        unit="People",
    )
    db_session.add(bank)
    db_session.flush()
    return bank


def _draft_template(db_session, **kwargs):
    """Template whose only version is a draft (so item/section ids are stable)."""
    return create_test_template(db_session, status="draft", **kwargs)


# ---------------------------------------------------------------------------
# create_template
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateTemplate:
    def test_creates_template_with_draft_version_and_structure(
        self, db_session, app, service, user, grant_all_rbac
    ):
        bank = _make_indicator_bank(db_session)
        schema = {
            "name": "AI Health Form",
            "description": "Created by the assistant",
            "sections": [
                {
                    "ref": "s_main",
                    "name": "Main Section",
                    "items": [
                        {"ref": "q_text", "item_type": "question", "question_type": "text",
                         "label": "Programme name", "is_required": True},
                        {"item_type": "question", "question_type": "single_choice",
                         "label": "Sector", "options": ["Health", "WASH"]},
                        {"ref": "i_reached", "item_type": "indicator",
                         "label": "People reached", "indicator_bank_id": bank.id},
                        {"item_type": "document_field", "label": "Budget document",
                         "max_documents": 2},
                    ],
                },
            ],
        }

        result = service.create_template(schema, user)

        assert result["version_status"] == "draft"
        assert result["sections_created"] == 1
        assert result["items_created"] == 4
        assert result["warnings"] == []
        assert "edit_url" in result and str(result["template_id"]) in result["edit_url"]

        template = db_session.get(FormTemplate, result["template_id"])
        assert template is not None
        # Safety invariant: AI never publishes.
        assert template.published_version_id is None

        draft = db_session.get(FormTemplateVersion, result["version_id"])
        assert draft.status == "draft"
        assert draft.name == "AI Health Form"

        sections = FormSection.query.filter_by(version_id=draft.id, archived=False).all()
        assert len(sections) == 1
        items = (
            FormItem.query.filter_by(version_id=draft.id, archived=False)
            .order_by(FormItem.order)
            .all()
        )
        assert len(items) == 4
        assert items[0].type == "text"
        assert items[0].config["is_required"] is True
        assert items[1].options_json == ["Health", "WASH"]
        assert items[2].indicator_bank_id == bank.id
        assert items[2].unit == "People"
        assert items[3].is_document_field
        assert items[3].config["max_documents"] == 2

        # Ref map echoes created ids.
        assert result["refs"]["s_main"]["type"] == "section"
        assert result["refs"]["q_text"]["id"] == items[0].id
        assert result["refs"]["i_reached"]["id"] == items[2].id

        # Change log appended to the draft comment.
        assert "[AI " in (draft.comment or "")

    def test_requires_create_permission(self, db_session, app, service, user):
        with patch(f"{AUTHZ}.has_rbac_permission", return_value=False):
            with pytest.raises(FormTemplateAIError, match="admin.templates.create"):
                service.create_template({"name": "Nope", "sections": []}, user)

    def test_requires_authenticated_user(self, db_session, app, service):
        with pytest.raises(FormTemplateAIError, match="Authentication required"):
            service.create_template({"name": "Nope", "sections": []}, None)

    def test_name_is_required(self, db_session, app, service, user, grant_all_rbac):
        with pytest.raises(FormTemplateAIError, match="'name' is required"):
            service.create_template({"sections": []}, user)

    def test_invalid_question_type_rolls_back(
        self, db_session, app, service, user, grant_all_rbac
    ):
        before = db_session.query(FormTemplate).count()
        schema = {
            "name": "Broken",
            "sections": [
                {"name": "S", "items": [
                    {"item_type": "question", "question_type": "not_a_type", "label": "Q"}
                ]}
            ],
        }
        with pytest.raises(FormTemplateAIError, match="invalid question_type"):
            service.create_template(schema, user)
        assert db_session.query(FormTemplate).count() == before

    def test_choice_question_without_options_warns(
        self, db_session, app, service, user, grant_all_rbac
    ):
        schema = {
            "name": "Choices",
            "sections": [
                {"name": "S", "items": [
                    {"item_type": "question", "question_type": "single_choice", "label": "Pick"}
                ]}
            ],
        }
        result = service.create_template(schema, user)
        assert any("without options" in w for w in result["warnings"])

    def test_unresolved_indicator_creates_item_with_warning(
        self, db_session, app, service, user, grant_all_rbac
    ):
        schema = {
            "name": "Indicators",
            "sections": [
                {"name": "S", "items": [
                    {"item_type": "indicator", "label": "Mystery", "indicator_bank_id": 99999999}
                ]}
            ],
        }
        result = service.create_template(schema, user)
        assert any("search_indicator_bank" in w for w in result["warnings"])
        item = FormItem.query.filter_by(version_id=result["version_id"]).first()
        assert item.indicator_bank_id is None
        assert item.item_type == "indicator"

    def test_pages_enable_pagination(self, db_session, app, service, user, grant_all_rbac):
        schema = {
            "name": "Paged",
            "pages": [{"ref": "p1", "name": "Page One"}],
            "sections": [{"name": "S", "page_ref": "p1", "items": []}],
        }
        result = service.create_template(schema, user)
        draft = db_session.get(FormTemplateVersion, result["version_id"])
        assert draft.is_paginated is True
        page = FormPage.query.filter_by(version_id=draft.id).first()
        section = FormSection.query.filter_by(version_id=draft.id).first()
        assert section.page_id == page.id

    def test_duplicate_refs_rejected(self, db_session, app, service, user, grant_all_rbac):
        schema = {
            "name": "Dups",
            "sections": [
                {"ref": "x", "name": "A", "items": []},
                {"ref": "x", "name": "B", "items": []},
            ],
        }
        with pytest.raises(FormTemplateAIError, match="Duplicate ref"):
            service.create_template(schema, user)

    def test_repeat_section_config(self, db_session, app, service, user, grant_all_rbac):
        schema = {
            "name": "Repeats",
            "sections": [
                {"name": "Activities", "section_type": "repeat", "max_entries": 5, "items": []}
            ],
        }
        result = service.create_template(schema, user)
        section = FormSection.query.filter_by(version_id=result["version_id"]).first()
        assert section.section_type == "repeat"
        assert section.max_entries == 5

    def test_matrix_item_manual_rows(self, db_session, app, service, user, grant_all_rbac):
        schema = {
            "name": "Matrices",
            "sections": [
                {"name": "S", "items": [
                    {
                        "item_type": "matrix",
                        "label": "Staff by region",
                        "matrix_config": {
                            "row_mode": "manual",
                            "rows": ["North", "South"],
                            "columns": [{"name": "Staff", "type": "number"}],
                        },
                    }
                ]}
            ],
        }
        result = service.create_template(schema, user)
        item = FormItem.query.filter_by(version_id=result["version_id"]).first()
        mc = item.config["matrix_config"]
        assert mc["row_mode"] == "manual"
        assert mc["rows"] == [{"text": "North"}, {"text": "South"}]
        # Legacy "number" is normalized to the explicit "number_whole" type.
        assert mc["columns"] == [{"name": "Staff", "type": "number_whole"}]

    def test_matrix_column_name_translations_preserved(
        self, db_session, app, service, user, grant_all_rbac
    ):
        schema = {
            "name": "Matrix labels",
            "sections": [
                {"name": "S", "items": [
                    {
                        "item_type": "matrix",
                        "label": "PNS staff contributions",
                        "matrix_config": {
                            "row_mode": "list_library",
                            "lookup_list_id": "national_society",
                            "list_display_column": "name",
                            "rows": [],
                            "columns": [
                                {
                                    "name": "intl_delegates_hns",
                                    "type": "number",
                                    "name_translations": {
                                        "en": "# of international delegates integrated with the HNS",
                                    },
                                },
                                {
                                    "name": "intl_delegates_ifrc",
                                    "type": "number",
                                    "label": "Delegates with IFRC",
                                },
                            ],
                            "show_row_totals": False,
                            "show_column_totals": False,
                        },
                    }
                ]}
            ],
        }
        result = service.create_template(schema, user)
        item = FormItem.query.filter_by(version_id=result["version_id"]).first()
        cols = item.config["matrix_config"]["columns"]
        assert cols[0]["name_translations"]["en"].startswith("# of international")
        assert cols[1]["name_translations"]["en"] == "Delegates with IFRC"

    def test_matrix_requires_columns(self, db_session, app, service, user, grant_all_rbac):
        schema = {
            "name": "Bad Matrix",
            "sections": [
                {"name": "S", "items": [
                    {"item_type": "matrix", "label": "M",
                     "matrix_config": {"row_mode": "manual", "rows": ["A"]}}
                ]}
            ],
        }
        with pytest.raises(FormTemplateAIError, match="at least one column"):
            service.create_template(schema, user)


# ---------------------------------------------------------------------------
# apply_edits
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestApplyEdits:
    def test_add_section_to_draft_only_template(
        self, db_session, app, service, user, grant_all_rbac
    ):
        template = _draft_template(db_session)
        result = service.apply_edits(
            template.id,
            [{"op": "add_section", "section": {
                "name": "WASH", "items": [
                    {"item_type": "question", "question_type": "number", "label": "Wells built"}
                ]}}],
            user,
        )
        assert result["version_status"] == "draft"
        assert any("WASH" in c for c in result["changes"])
        section = FormSection.query.filter_by(
            version_id=result["version_id"], name="WASH"
        ).first()
        assert section is not None
        assert FormItem.query.filter_by(section_id=section.id).count() == 1

    def test_editing_published_template_creates_draft_and_keeps_published_intact(
        self, db_session, app, service, user, grant_all_rbac
    ):
        template = create_test_template(db_session)  # published v1
        published_id = template.published_version_id
        section = create_test_section(db_session, template, name="Existing")
        create_test_item(
            db_session, section, template, item_type="question", label="Q1", type="text"
        )

        result = service.apply_edits(
            template.id,
            [{"op": "add_section", "section": {"name": "New AI Section", "items": []}}],
            user,
        )

        # A draft was created; the published version was not modified.
        assert result["version_id"] != published_id
        draft = db_session.get(FormTemplateVersion, result["version_id"])
        assert draft.status == "draft"
        db_session.refresh(template)
        assert template.published_version_id == published_id
        published_sections = {
            s.name for s in FormSection.query.filter_by(version_id=published_id).all()
        }
        assert "New AI Section" not in published_sections
        draft_sections = {
            s.name for s in FormSection.query.filter_by(version_id=draft.id).all()
        }
        assert "New AI Section" in draft_sections

    def test_add_item_with_published_section_id_maps_to_draft(
        self, db_session, app, service, user, grant_all_rbac
    ):
        """AI often reads published section ids, then edit creates a draft with new ids."""
        template = create_test_template(db_session)
        published_id = template.published_version_id
        section = create_test_section(db_session, template, name="Funding")
        create_test_item(
            db_session, section, template, item_type="question", label="Existing Q", type="text"
        )
        read = service.get_full_structure(template.id, user)
        assert read["version_id"] == published_id
        published_section_id = read["sections"][0]["id"]

        result = service.apply_edits(
            template.id,
            [{
                "op": "add_item",
                "section_id": published_section_id,
                "item": {
                    "item_type": "matrix",
                    "label": "PNS staff contributions",
                    "matrix_config": {
                        "row_mode": "list_library",
                        "lookup_list_id": "national_society",
                        "list_display_column": "name",
                        "rows": [],
                        "columns": [
                            {
                                "name": "intl_delegates_hns",
                                "type": "number",
                                "name_translations": {
                                    "en": "# of international delegates integrated with the HNS",
                                },
                            },
                        ],
                        "show_row_totals": False,
                        "show_column_totals": False,
                    },
                },
            }],
            user,
        )

        assert result["version_id"] != published_id
        draft_section = FormSection.query.filter_by(
            version_id=result["version_id"], name="Funding"
        ).first()
        assert draft_section is not None
        matrix = FormItem.query.filter_by(
            section_id=draft_section.id, label="PNS staff contributions"
        ).first()
        assert matrix is not None
        cols = matrix.config["matrix_config"]["columns"]
        assert cols[0]["name_translations"]["en"].startswith("# of international")

    def test_update_item_with_published_section_id_maps_to_draft(
        self, db_session, app, service, user, grant_all_rbac
    ):
        template = create_test_template(db_session)
        published_id = template.published_version_id
        section = create_test_section(db_session, template, name="Funding")
        item = create_test_item(
            db_session, section, template, item_type="question", label="Old label", type="text"
        )
        read = service.get_full_structure(template.id, user)
        published_item_id = read["sections"][0]["items"][0]["id"]

        result = service.apply_edits(
            template.id,
            [{"op": "update_item", "item_id": published_item_id, "label": "New label"}],
            user,
        )

        draft_item = FormItem.query.filter_by(
            version_id=result["version_id"], label="New label"
        ).first()
        assert draft_item is not None
        assert draft_item.id != item.id

    def test_update_item_required_flag_and_label(
        self, db_session, app, service, user, grant_all_rbac
    ):
        template = _draft_template(db_session)
        version = template.versions.first()
        section = create_test_section(db_session, template, version=version)
        item = create_test_item(
            db_session, section, template, item_type="question", label="Old", type="text"
        )

        result = service.apply_edits(
            template.id,
            [{"op": "update_item", "item_id": item.id, "label": "New label", "is_required": True}],
            user,
        )

        db_session.refresh(item)
        assert item.label == "New label"
        assert item.config["is_required"] is True
        assert any("New label" in c for c in result["changes"])

    def test_remove_item_without_data_deletes_row(
        self, db_session, app, service, user, grant_all_rbac
    ):
        template = _draft_template(db_session)
        version = template.versions.first()
        section = create_test_section(db_session, template, version=version)
        item = create_test_item(
            db_session, section, template, item_type="question", label="Doomed", type="text"
        )
        item_id = item.id

        service.apply_edits(
            template.id, [{"op": "remove_item", "item_id": item_id}], user
        )
        assert db_session.get(FormItem, item_id) is None

    def test_unknown_operation_rejected(self, db_session, app, service, user, grant_all_rbac):
        template = _draft_template(db_session)
        with pytest.raises(FormTemplateAIError, match="unknown op"):
            service.apply_edits(template.id, [{"op": "publish_template"}], user)

    def test_operations_must_be_non_empty(self, db_session, app, service, user, grant_all_rbac):
        template = _draft_template(db_session)
        with pytest.raises(FormTemplateAIError, match="non-empty list"):
            service.apply_edits(template.id, [], user)

    def test_requires_edit_permission(self, db_session, app, service, user):
        template = _draft_template(db_session)
        with patch(f"{AUTHZ}.has_rbac_permission", return_value=False):
            with pytest.raises(FormTemplateAIError, match="admin.templates.edit"):
                service.apply_edits(
                    template.id, [{"op": "add_section", "section": {"name": "X"}}], user
                )

    def test_requires_template_access(self, db_session, app, service, user):
        template = _draft_template(db_session)
        with patch(f"{AUTHZ}.has_rbac_permission", return_value=True), \
             patch(f"{AUTHZ}.check_template_access", return_value=False):
            with pytest.raises(FormTemplateAIError, match="access"):
                service.apply_edits(
                    template.id, [{"op": "add_section", "section": {"name": "X"}}], user
                )

    def test_template_not_found(self, db_session, app, service, user, grant_all_rbac):
        with pytest.raises(FormTemplateAIError, match="not found"):
            service.apply_edits(99999999, [{"op": "add_section", "section": {"name": "X"}}], user)

    def test_refs_resolve_across_operations(
        self, db_session, app, service, user, grant_all_rbac
    ):
        """A section/item created in one op can be referenced by later ops in the same call."""
        template = _draft_template(db_session)
        result = service.apply_edits(
            template.id,
            [
                {"op": "add_section", "section": {"ref": "s1", "name": "Sec", "items": [
                    {"ref": "q_yes", "item_type": "question", "question_type": "yesno",
                     "label": "Has activities?"},
                ]}},
                {"op": "add_item", "section_ref": "s1", "item": {
                    "ref": "q_detail", "item_type": "question", "question_type": "text",
                    "label": "Describe activities",
                }},
                {"op": "set_relevance", "item_ref": "q_detail", "rule": {
                    "logic": "AND",
                    "conditions": [{"item": "q_yes", "condition_type": "is_yes"}],
                }},
            ],
            user,
        )

        detail_id = result["refs"]["q_detail"]["id"]
        yes_id = result["refs"]["q_yes"]["id"]
        detail = db_session.get(FormItem, detail_id)
        rule = json.loads(detail.relevance_condition)
        assert rule["logic"] == "AND"
        assert rule["conditions"] == [
            {"item_id": str(yes_id), "condition_type": "is_yes", "value": ""}
        ]


# ---------------------------------------------------------------------------
# Skip logic / validation rules (phase 2)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRules:
    @pytest.fixture
    def template_with_items(self, db_session, app):
        template = _draft_template(db_session)
        version = template.versions.first()
        section = create_test_section(db_session, template, version=version)
        number_a = create_test_item(
            db_session, section, template, item_type="question",
            label="People reached", type="number", order=1,
        )
        number_b = create_test_item(
            db_session, section, template, item_type="question",
            label="People targeted", type="number", order=2,
        )
        yesno = create_test_item(
            db_session, section, template, item_type="question",
            label="Active?", type="yesno", order=3,
        )
        return template, section, number_a, number_b, yesno

    def test_invalid_condition_type_for_target_rejected(
        self, db_session, app, service, user, grant_all_rbac, template_with_items
    ):
        template, _section, _a, _b, yesno = template_with_items
        with pytest.raises(FormTemplateAIError, match="not valid"):
            service.apply_edits(
                template.id,
                [{"op": "set_relevance", "item_id": yesno.id, "rule": {
                    "conditions": [{"item": yesno.id, "condition_type": "contains", "value": "x"}],
                }}],
                user,
            )

    def test_validation_rule_requires_message(
        self, db_session, app, service, user, grant_all_rbac, template_with_items
    ):
        template, _section, number_a, number_b, _y = template_with_items
        with pytest.raises(FormTemplateAIError, match="validation_message"):
            service.apply_edits(
                template.id,
                [{"op": "set_validation", "item_id": number_a.id, "rule": {
                    "conditions": [{
                        "item": number_a.id,
                        "condition_type": "less_than_or_equal_to",
                        "value_item": number_b.id,
                    }],
                }}],
                user,
            )

    def test_field_to_field_validation_with_message(
        self, db_session, app, service, user, grant_all_rbac, template_with_items
    ):
        template, _section, number_a, number_b, _y = template_with_items
        service.apply_edits(
            template.id,
            [{"op": "set_validation", "item_id": number_a.id,
              "message": "People reached must not exceed people targeted.",
              "rule": {
                  "conditions": [{
                      "item": number_a.id,
                      "condition_type": "less_than_or_equal_to",
                      "value_item": number_b.id,
                  }],
              }}],
            user,
        )
        db_session.refresh(number_a)
        rule = json.loads(number_a.validation_condition)
        assert rule["conditions"][0]["value_field_id"] == number_b.id
        assert "value" not in rule["conditions"][0]
        assert number_a.validation_message == "People reached must not exceed people targeted."

    def test_clearing_relevance(self, db_session, app, service, user, grant_all_rbac, template_with_items):
        template, _section, number_a, _b, yesno = template_with_items
        number_a.relevance_condition = json.dumps(
            {"logic": "AND", "conditions": [
                {"item_id": str(yesno.id), "condition_type": "is_yes", "value": ""}
            ]}
        )
        db_session.commit()

        result = service.apply_edits(
            template.id,
            [{"op": "set_relevance", "item_id": number_a.id, "rule": None}],
            user,
        )
        db_session.refresh(number_a)
        assert number_a.relevance_condition is None
        assert any("Cleared skip logic" in c for c in result["changes"])

    def test_rule_value_required_for_valued_conditions(
        self, db_session, app, service, user, grant_all_rbac, template_with_items
    ):
        template, _section, number_a, _b, _y = template_with_items
        with pytest.raises(FormTemplateAIError, match="requires a 'value'"):
            service.apply_edits(
                template.id,
                [{"op": "set_relevance", "item_id": number_a.id, "rule": {
                    "conditions": [{"item": number_a.id, "condition_type": "greater_than"}],
                }}],
                user,
            )


# ---------------------------------------------------------------------------
# get_full_structure
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetFullStructure:
    def test_returns_sections_and_items(self, db_session, app, service, user, grant_all_rbac):
        template = _draft_template(db_session)
        version = template.versions.first()
        section = create_test_section(db_session, template, version=version, name="Sec A")
        create_test_item(
            db_session, section, template, item_type="question",
            label="Q1", type="text", order=1,
        )

        result = service.get_full_structure(template.id, user)

        assert result["template_id"] == template.id
        assert result["version_status"] == "draft"
        assert len(result["sections"]) == 1
        assert result["sections"][0]["name"] == "Sec A"
        assert result["sections"][0]["items"][0]["label"] == "Q1"
        assert result["sections"][0]["items"][0]["question_type"] == "text"

    def test_prefers_draft_over_published(self, db_session, app, service, user, grant_all_rbac):
        template = create_test_template(db_session)  # published
        draft = FormTemplateVersion(
            template_id=template.id, version_number=2, status="draft", name="Draft v2"
        )
        db_session.add(draft)
        db_session.commit()

        result = service.get_full_structure(template.id, user)
        assert result["version_id"] == draft.id
        assert result["version_status"] == "draft"

    def test_requires_view_permission(self, db_session, app, service, user):
        template = _draft_template(db_session)
        with patch(f"{AUTHZ}.has_rbac_permission", return_value=False):
            with pytest.raises(FormTemplateAIError, match="admin.templates.view"):
                service.get_full_structure(template.id, user)


# ---------------------------------------------------------------------------
# translate_template (phase 3)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTranslateTemplate:
    def test_rejects_unsupported_language(self, db_session, app, service, user, grant_all_rbac):
        app.config["SUPPORTED_LANGUAGES"] = ["en", "fr"]
        template = _draft_template(db_session)
        with pytest.raises(FormTemplateAIError, match="not enabled"):
            service.translate_template(template.id, ["de"], user)

    def test_requires_non_english_target(self, db_session, app, service, user, grant_all_rbac):
        app.config["SUPPORTED_LANGUAGES"] = ["en", "fr"]
        template = _draft_template(db_session)
        with pytest.raises(FormTemplateAIError, match="non-English"):
            service.translate_template(template.id, ["en"], user)

    def test_translates_labels_and_section_names(
        self, db_session, app, service, user, grant_all_rbac
    ):
        app.config["SUPPORTED_LANGUAGES"] = ["en", "fr"]
        template = _draft_template(db_session)
        version = template.versions.first()
        section = create_test_section(db_session, template, version=version, name="Health")
        item = create_test_item(
            db_session, section, template, item_type="question",
            label="Programme name", type="text",
        )

        class FakeTranslator:
            def translate_text(self, text, target, source="en"):
                return f"[fr] {text}"

        with patch(
            "app.services.translation.auto_translator.get_auto_translator",
            return_value=FakeTranslator(),
        ):
            result = service.translate_template(template.id, ["fr"], user)

        assert result["translated"] > 0
        assert result["failed"] == 0
        db_session.refresh(item)
        db_session.refresh(section)
        assert item.label_translations["fr"] == "[fr] Programme name"
        assert section.name_translations["fr"] == "[fr] Health"

    def test_untranslated_scope_skips_existing(
        self, db_session, app, service, user, grant_all_rbac
    ):
        app.config["SUPPORTED_LANGUAGES"] = ["en", "fr"]
        template = _draft_template(db_session)
        version = template.versions.first()
        section = create_test_section(db_session, template, version=version, name="Health")
        section.name_translations = {"fr": "Santé (manual)"}
        db_session.commit()

        class FakeTranslator:
            def translate_text(self, text, target, source="en"):
                return f"[fr] {text}"

        with patch(
            "app.services.translation.auto_translator.get_auto_translator",
            return_value=FakeTranslator(),
        ):
            result = service.translate_template(template.id, ["fr"], user, scope="untranslated")

        db_session.refresh(section)
        assert section.name_translations["fr"] == "Santé (manual)"
        assert result["skipped_existing"] >= 1


# ---------------------------------------------------------------------------
# discard_draft (phase 7)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDiscardDraft:
    def test_discards_draft_keeps_published(self, db_session, app, service, user, grant_all_rbac):
        template = create_test_template(db_session)  # published v1
        published_id = template.published_version_id
        draft = FormTemplateVersion(
            template_id=template.id, version_number=2, status="draft", name="Draft v2"
        )
        db_session.add(draft)
        db_session.flush()
        section = FormSection(
            template_id=template.id, version_id=draft.id, name="Draft Sec", order=1
        )
        db_session.add(section)
        db_session.commit()
        draft_id = draft.id

        result = service.discard_draft(template.id, user)

        assert result["discarded_version_id"] == draft_id
        assert db_session.get(FormTemplateVersion, draft_id) is None
        assert FormSection.query.filter_by(version_id=draft_id).count() == 0
        db_session.refresh(template)
        assert template.published_version_id == published_id

    def test_refuses_to_discard_only_version(self, db_session, app, service, user, grant_all_rbac):
        template = _draft_template(db_session)
        with pytest.raises(FormTemplateAIError, match="only version"):
            service.discard_draft(template.id, user)

    def test_no_draft_to_discard(self, db_session, app, service, user, grant_all_rbac):
        template = create_test_template(db_session)  # published only
        with pytest.raises(FormTemplateAIError, match="no draft"):
            service.discard_draft(template.id, user)
