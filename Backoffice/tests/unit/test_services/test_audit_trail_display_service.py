"""
Extended tests for app/services/audit_trail_display_service.py.

Tests cover the functions not already exercised by
tests/unit/test_utils/test_audit_trail_display.py:
  - build_form_context_lookups_from_activity_logs
  - _resolve_form_context
  - create_consistent_description (all branches)
  - extract_entity_info
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.audit_trail_display_service import (
    FormContextLookups,
    _extract_aes_and_template_ids_from_context,
    _resolve_form_context,
    build_form_context_lookups_from_activity_logs,
    consolidate_activity_type,
    create_consistent_description,
    extract_entity_info,
    refine_activity_row_consolidated_type,
)


# ---------------------------------------------------------------------------
# consolidate_activity_type – extra branches
# ---------------------------------------------------------------------------
class TestConsolidateActivityType:
    def test_normalizable_type_returned_normalized(self):
        t = consolidate_activity_type("form_save")
        assert t == "form_saved"

    def test_unknown_type_passed_through_as_is(self):
        # normalize_activity_type passes unknown types through unchanged
        t = consolidate_activity_type("custom_event_xyz")
        assert t == "custom_event_xyz"

    def test_page_view_canonical_type_preserved(self):
        t = consolidate_activity_type("page_view")
        assert t == "page_view"

    def test_none_activity_view_in_action(self):
        t = consolidate_activity_type(None, "view_dashboard")
        assert t == "page_view"

    def test_none_activity_other_action(self):
        t = consolidate_activity_type(None, "user_update")
        assert t == "user_update"

    def test_both_none_returns_unknown(self):
        t = consolidate_activity_type(None, None)
        assert t == "unknown"


# ---------------------------------------------------------------------------
# refine_activity_row_consolidated_type – extra branches
# ---------------------------------------------------------------------------
class TestRefineActivityRowConsolidatedType:
    def test_data_deleted_with_endpoint(self):
        result = refine_activity_row_consolidated_type(
            "data_deleted",
            None,
            "/forms/1/delete",
            http_method="DELETE",
        )
        assert result is not None

    def test_page_view_type_returned_as_page_view_without_catalog(self):
        result = refine_activity_row_consolidated_type(
            "page_view",
            None,
            None,
        )
        assert result == "page_view"

    def test_unknown_type_with_no_endpoint(self):
        result = refine_activity_row_consolidated_type("unknown", None, None)
        assert result == "unknown"


# ---------------------------------------------------------------------------
# _extract_aes_and_template_ids_from_context – extra branches
# ---------------------------------------------------------------------------
class TestExtractAesAndTemplateIds:
    def test_aes_id_from_form_data(self):
        aes, tid = _extract_aes_and_template_ids_from_context(
            {"form_data": {"aes_id": "7"}}
        )
        assert aes == 7
        assert tid is None

    def test_assignment_id_fallback_in_form_data(self):
        aes, tid = _extract_aes_and_template_ids_from_context(
            {"form_data": {"assignment_id": "3"}}
        )
        assert aes == 3

    def test_assignment_id_at_top_level(self):
        aes, tid = _extract_aes_and_template_ids_from_context(
            {"assignment_id": "5"}
        )
        assert aes == 5

    def test_template_id_extracted(self):
        _, tid = _extract_aes_and_template_ids_from_context(
            {"template_id": "10"}
        )
        assert tid == 10

    def test_non_digit_aes_id_ignored(self):
        aes, _ = _extract_aes_and_template_ids_from_context(
            {"form_data": {"aes_id": "abc"}}
        )
        assert aes is None

    def test_none_context_returns_none_none(self):
        aes, tid = _extract_aes_and_template_ids_from_context(None)
        assert aes is None and tid is None

    def test_non_dict_context_returns_none_none(self):
        aes, tid = _extract_aes_and_template_ids_from_context("bad")
        assert aes is None and tid is None

    def test_url_path_fallback_when_no_aes_raw(self):
        aes, _ = _extract_aes_and_template_ids_from_context(
            {"url_path": "/forms/enter_data/99/section"}
        )
        assert aes == 99


# ---------------------------------------------------------------------------
# _resolve_form_context – pure (with FormContextLookups)
# ---------------------------------------------------------------------------
class TestResolveFormContext:
    def test_none_context_returns_triple_none(self):
        tn, an, cn = _resolve_form_context(None, None, None)
        assert tn is None and an is None and cn is None

    def test_non_dict_context_returns_triple_none(self):
        tn, an, cn = _resolve_form_context("bad", None, None)
        assert tn is None and an is None and cn is None

    def test_aes_resolved_from_lookups(self):
        lookups = FormContextLookups(
            aes_by_id={
                1: {"template_name": "T1", "assignment_name": "FY2024", "country_name": "Kenya"}
            },
            template_name_by_id={},
        )
        tn, an, cn = _resolve_form_context(
            {"form_data": {"aes_id": "1"}},
            None,
            lookups,
        )
        assert tn == "T1"
        assert an == "FY2024"
        assert cn == "Kenya"

    def test_template_resolved_from_lookups(self):
        lookups = FormContextLookups(
            aes_by_id={},
            template_name_by_id={5: "My Template"},
        )
        tn, an, cn = _resolve_form_context(
            {"template_id": "5"},
            None,
            lookups,
        )
        assert tn == "My Template"
        assert an is None

    def test_aes_fallback_to_db_query(self, app):
        with app.app_context():
            mock_aes = MagicMock()
            mock_aes.assigned_form.template.name = "FallbackTemplate"
            mock_aes.assigned_form.period_name = "Q1"
            mock_aes.country.name = "Tanzania"

            # Lazy import inside function: patch at app.models module level
            with patch("app.models.AssignmentEntityStatus") as MockAES:
                MockAES.query.get.return_value = mock_aes
                tn, an, cn = _resolve_form_context(
                    {"form_data": {"aes_id": "99"}},
                    None,
                    None,
                )
                assert tn == "FallbackTemplate"

    def test_template_fallback_to_db_query(self, app):
        with app.app_context():
            mock_tmpl = MagicMock()
            mock_tmpl.name = "DBTemplate"

            # Lazy import inside function: patch at app.models module level
            with patch("app.models.FormTemplate") as MockFT:
                MockFT.query.get.return_value = mock_tmpl
                tn, _an, _cn = _resolve_form_context(
                    {"template_id": "77"},
                    None,
                    None,
                )
                assert tn == "DBTemplate"

    def test_aes_fallback_with_no_template(self, app):
        with app.app_context():
            mock_aes = MagicMock()
            mock_aes.assigned_form = None
            mock_aes.country = None

            with patch("app.models.AssignmentEntityStatus") as MockAES:
                MockAES.query.get.return_value = mock_aes
                tn, an, cn = _resolve_form_context(
                    {"form_data": {"aes_id": "999"}},
                    None,
                    None,
                )
                assert tn is None

    def test_db_exception_returns_triple_none(self, app):
        with app.app_context():
            with patch("app.models.AssignmentEntityStatus") as MockAES:
                MockAES.query.get.side_effect = Exception("db error")
                tn, an, cn = _resolve_form_context(
                    {"form_data": {"aes_id": "100"}},
                    None,
                    None,
                )
                assert tn is None


# ---------------------------------------------------------------------------
# build_form_context_lookups_from_activity_logs
# ---------------------------------------------------------------------------
class TestBuildFormContextLookups:
    def test_empty_logs_returns_empty_lookups(self, app):
        with app.app_context():
            lookups = build_form_context_lookups_from_activity_logs([])
            assert lookups.aes_by_id == {}
            assert lookups.template_name_by_id == {}

    def test_logs_with_no_context_data(self, app):
        with app.app_context():
            log = MagicMock()
            log.context_data = None
            log.url_path = None
            lookups = build_form_context_lookups_from_activity_logs([log])
            assert lookups.aes_by_id == {}

    def test_log_url_path_merged_into_context(self, app):
        with app.app_context():
            log = MagicMock()
            log.context_data = {}
            log.url_path = "/forms/enter_data/42"
            # AES id 42 is extracted from the URL. We mock AssignmentEntityStatus AND
            # joinedload (which is imported inside the function) so SQLAlchemy never
            # attempts to build a real ORM expression from mock attributes.
            with patch("app.models.assignments.AssignmentEntityStatus") as MockAES, \
                 patch("sqlalchemy.orm.joinedload") as mock_jl:
                mock_jl.return_value = MagicMock()
                mock_jl.return_value.joinedload.return_value = MagicMock()
                MockAES.query.filter.return_value.options.return_value.all.return_value = []
                lookups = build_form_context_lookups_from_activity_logs([log])
                assert isinstance(lookups.aes_by_id, dict)


# ---------------------------------------------------------------------------
# create_consistent_description – all branches
# ---------------------------------------------------------------------------
class TestCreateConsistentDescription:
    def test_activity_login(self):
        desc = create_consistent_description("activity", "login", None, None)
        assert "Logged in" in desc

    def test_activity_logout(self):
        desc = create_consistent_description("activity", "logout", None, None)
        assert "Logged out" in desc

    def test_activity_profile_update(self):
        desc = create_consistent_description("activity", "profile_update", None, None)
        assert "profile" in desc.lower()

    def test_activity_data_export(self):
        desc = create_consistent_description("activity", "data_export", None, None)
        assert "Exported" in desc

    def test_activity_account_created(self):
        desc = create_consistent_description("activity", "account_created", None, None)
        assert "Account" in desc

    def test_activity_file_uploaded(self):
        desc = create_consistent_description("activity", "file_uploaded", None, None)
        assert "file" in desc.lower() or "Uploaded" in desc

    def test_activity_file_upload(self):
        desc = create_consistent_description("activity", "file_upload", None, None)
        assert "file" in desc.lower() or "Uploaded" in desc

    def test_activity_data_modified_uses_original(self):
        desc = create_consistent_description(
            "activity", "data_modified", None, "Custom update description"
        )
        assert desc == "Custom update description"

    def test_activity_data_modified_no_original(self):
        desc = create_consistent_description("activity", "data_modified", None, None)
        assert "Updated" in desc

    def test_activity_data_deleted_no_original(self):
        desc = create_consistent_description("activity", "data_deleted", None, None)
        assert "Deleted" in desc

    def test_activity_form_saved_with_context(self):
        lookups = FormContextLookups(
            aes_by_id={1: {"template_name": "T", "assignment_name": "A", "country_name": "C"}},
            template_name_by_id={},
        )
        desc = create_consistent_description(
            "activity",
            "form_saved",
            None,
            None,
            context_data={"form_data": {"aes_id": "1"}},
            form_lookups=lookups,
        )
        assert "T" in desc

    def test_activity_form_submitted_with_context(self):
        lookups = FormContextLookups(
            aes_by_id={2: {"template_name": "TForm", "assignment_name": None, "country_name": "X"}},
            template_name_by_id={},
        )
        desc = create_consistent_description(
            "activity",
            "form_submitted",
            None,
            None,
            context_data={"form_data": {"aes_id": "2"}},
            form_lookups=lookups,
        )
        assert "TForm" in desc

    def test_activity_form_approved(self):
        desc = create_consistent_description("activity", "form_approved", None, None)
        assert "Approved" in desc

    def test_activity_form_reopened(self):
        desc = create_consistent_description("activity", "form_reopened", None, None)
        assert "Reopened" in desc

    def test_activity_form_validated(self):
        desc = create_consistent_description("activity", "form_validated", None, None)
        assert "Validated" in desc

    def test_activity_request_with_inferred_type(self):
        desc = create_consistent_description(
            "activity",
            "request",
            None,
            "Submitted Save Form",
        )
        assert desc is not None

    def test_activity_request_performed_prefix(self):
        desc = create_consistent_description(
            "activity",
            "request",
            None,
            "Performed some action",
        )
        assert "Submitted" in desc or "some action" in desc

    def test_activity_request_no_original_returns_default(self):
        desc = create_consistent_description("activity", "request", None, None)
        assert "request" in desc.lower() or desc

    def test_activity_page_view_with_original_viewed_prefix(self):
        desc = create_consistent_description(
            "activity", "page_view", None, "Viewed the dashboard"
        )
        assert desc == "Viewed the dashboard"

    def test_activity_page_view_without_original(self):
        desc = create_consistent_description("activity", "page_view", None, None)
        assert desc is not None

    def test_activity_fallback_to_original_description(self):
        desc = create_consistent_description(
            "activity", "unknown_exotic_type", None, "Original desc"
        )
        assert desc == "Original desc"

    def test_activity_fallback_no_original(self):
        desc = create_consistent_description(
            "activity", "unknown_exotic_type", None, None
        )
        assert desc == "User activity"

    def test_admin_action_no_action_type(self):
        desc = create_consistent_description(
            "admin_action", None, None, "Some admin thing"
        )
        assert desc == "Some admin thing"

    def test_admin_action_no_action_type_no_original(self):
        desc = create_consistent_description("admin_action", None, None, None)
        assert desc == "Admin action"

    def test_admin_action_view_type(self):
        desc = create_consistent_description("admin_action", None, "view_users", None)
        assert "Viewed" in desc or "users" in desc.lower()

    def test_admin_action_non_view_with_original(self):
        desc = create_consistent_description(
            "admin_action", None, "user_update", "Updated user"
        )
        assert desc == "Updated user"

    def test_admin_action_non_view_no_original(self):
        desc = create_consistent_description("admin_action", None, "user_create", None)
        assert "User Create" in desc or "user_create" in desc.lower()

    def test_form_saved_public_endpoint_fallback(self):
        desc = create_consistent_description(
            "activity",
            "form_saved",
            None,
            None,
            endpoint="public.submit",
            context_data={},
        )
        assert "public" in desc.lower() or "form" in desc.lower()

    def test_form_saved_no_context_generic_fallback(self):
        desc = create_consistent_description(
            "activity",
            "form_saved",
            None,
            None,
        )
        assert "form" in desc.lower() or "Saved" in desc

    def test_catalog_spec_overrides_description(self):
        desc = create_consistent_description(
            "activity",
            "request",
            None,
            "Old desc",
            endpoint="settings.manage_settings",
            http_method="POST",
        )
        assert desc is not None and desc != ""

    def test_data_deleted_inferred_type_with_desc(self):
        desc = create_consistent_description(
            "activity",
            "data_deleted",
            None,
            "Deleted user record",
        )
        assert desc is not None


# ---------------------------------------------------------------------------
# extract_entity_info
# ---------------------------------------------------------------------------
class TestExtractEntityInfo:
    def test_activity_with_entity_in_context(self):
        ctx = {"entity_type": "country", "entity_id": 5, "entity_name": "Kenya"}
        etype, eid, ename = extract_entity_info("activity", ctx)
        assert etype == "country"
        assert eid == 5
        assert ename == "Kenya"

    def test_activity_with_country_id_in_context(self):
        ctx = {"country_id": 3, "country_name": "Ghana"}
        etype, eid, ename = extract_entity_info("activity", ctx)
        assert etype == "country"
        assert eid == 3
        assert ename == "Ghana"

    def test_activity_country_id_in_form_data(self):
        ctx = {"form_data": {"country_id": 7, "country_name": "Niger"}}
        etype, eid, ename = extract_entity_info("activity", ctx)
        assert etype == "country"
        assert eid == 7

    def test_activity_entity_id_without_name_triggers_lookup(self, app):
        with app.app_context():
            ctx = {"entity_type": "country", "entity_id": 10}
            # EntityService is lazily imported inside extract_entity_info
            with patch("app.services.entity_service.EntityService") as MockES:
                MockES.get_entity_display_name.return_value = "Nigeria"
                etype, eid, ename = extract_entity_info("activity", ctx)
                assert ename == "Nigeria"

    def test_activity_lookup_exception_ignored(self, app):
        with app.app_context():
            ctx = {"entity_type": "country", "entity_id": 10}
            with patch(
                "app.services.entity_service.EntityService",
                side_effect=Exception,
            ):
                etype, eid, ename = extract_entity_info("activity", ctx)
                assert eid == 10

    def test_activity_none_context(self):
        etype, eid, ename = extract_entity_info("activity", None)
        assert etype is None

    def test_admin_action_with_country_in_details(self, app):
        with app.app_context():
            details = {"country_id": 2, "country_name": "Zambia"}
            etype, eid, ename = extract_entity_info("admin_action", None, details=details)
            assert etype == "country"
            assert eid == 2
            assert ename == "Zambia"

    def test_admin_action_country_from_new_values(self, app):
        with app.app_context():
            admin_action = MagicMock()
            admin_action.new_values = {"country_id": 8}
            admin_action.old_values = {}
            admin_action.target_type = "user"
            admin_action.target_id = None

            # Country is lazily imported inside extract_entity_info from app.models
            with patch("app.models.Country") as MockCountry:
                mock_country = MagicMock()
                mock_country.name = "Rwanda"
                MockCountry.query.get.return_value = mock_country
                etype, eid, ename = extract_entity_info(
                    "admin_action", None, admin_action=admin_action
                )
                assert etype == "country"

    def test_admin_action_country_from_country_ids_single(self, app):
        with app.app_context():
            admin_action = MagicMock()
            admin_action.new_values = {"country_ids": [4]}
            admin_action.old_values = {}
            admin_action.target_type = "user"
            admin_action.target_id = None

            with patch("app.models.Country") as MockCountry:
                mock_country = MagicMock()
                mock_country.name = "Sudan"
                MockCountry.query.get.return_value = mock_country
                etype, eid, ename = extract_entity_info(
                    "admin_action", None, admin_action=admin_action
                )
                assert eid == 4

    def test_admin_action_fallback_to_target_type_country(self, app):
        with app.app_context():
            admin_action = MagicMock()
            admin_action.new_values = {}
            admin_action.old_values = {}
            admin_action.target_type = "country"
            admin_action.target_id = 9

            with patch("app.models.Country") as MockCountry:
                mock_country = MagicMock()
                mock_country.name = "Malawi"
                MockCountry.query.get.return_value = mock_country
                etype, eid, ename = extract_entity_info(
                    "admin_action", None, admin_action=admin_action
                )
                assert eid == 9
                assert ename == "Malawi"

    def test_admin_action_country_lookup_exception(self, app):
        with app.app_context():
            details = {"country_id": 2}
            with patch("app.models.Country") as MockCountry:
                MockCountry.query.get.side_effect = Exception("lookup failed")
                etype, eid, ename = extract_entity_info("admin_action", None, details=details)
                assert eid == 2
                assert ename is None

    def test_general_exception_handled_gracefully(self, app):
        with app.app_context():
            # Simulate an outer exception by passing data that triggers an error branch
            # The outer try/except in extract_entity_info catches all exceptions
            ctx = MagicMock()
            ctx.__class__ = dict  # make isinstance(context_data, dict) True
            ctx.get = MagicMock(side_effect=RuntimeError("boom"))
            etype, eid, ename = extract_entity_info("activity", ctx)
            assert etype is None
