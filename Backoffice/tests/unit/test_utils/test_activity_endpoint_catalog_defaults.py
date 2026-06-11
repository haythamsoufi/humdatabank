"""
Comprehensive tests for app/utils/activity_endpoint_catalog/defaults.py.

Targets every branch to bring coverage from ~51 % → 100 %.
"""

from __future__ import annotations

import pytest

from app.utils.activity_endpoint_catalog.defaults import (
    _describe_post_inner,
    _humanize_snake_tail,
    _strip_outer_wrappers,
    activity_category_for_endpoint,
    blueprint_name,
    catalog_display_description,
    default_generated_description,
    describe_get_request_without_catalog,
)


# ---------------------------------------------------------------------------
# _humanize_snake_tail
# ---------------------------------------------------------------------------


class TestHumanizeSnakeTail:
    def test_empty_string(self):
        assert _humanize_snake_tail("") == ""

    def test_only_underscores(self):
        assert _humanize_snake_tail("___") == ""

    def test_single_word(self):
        assert _humanize_snake_tail("document") == "Document"

    def test_multi_word(self):
        assert _humanize_snake_tail("entity_from_assignment") == "Entity From Assignment"

    def test_leading_trailing_underscores(self):
        assert _humanize_snake_tail("_foo_bar_") == "Foo Bar"


# ---------------------------------------------------------------------------
# _strip_outer_wrappers
# ---------------------------------------------------------------------------


class TestStripOuterWrappers:
    def test_no_prefix(self):
        assert _strip_outer_wrappers("delete_document") == "delete_document"

    def test_api_prefix(self):
        assert _strip_outer_wrappers("api_delete_document") == "delete_document"

    def test_get_prefix(self):
        assert _strip_outer_wrappers("get_users") == "users"

    def test_fetch_prefix(self):
        assert _strip_outer_wrappers("fetch_data") == "data"

    def test_nested_api_get(self):
        # api_ then get_ stripped in two passes
        assert _strip_outer_wrappers("api_get_users") == "users"

    def test_nested_api_fetch(self):
        assert _strip_outer_wrappers("api_fetch_records") == "records"

    def test_short_api_not_stripped(self):
        # "api_" requires len > 4; "api_" itself (len==4) would not strip remainder
        assert _strip_outer_wrappers("api_") == "api_"

    def test_short_fetch_not_stripped(self):
        assert _strip_outer_wrappers("fetch_") == "fetch_"

    def test_short_get_not_stripped(self):
        assert _strip_outer_wrappers("get_") == "get_"

    def test_three_layer_strip(self):
        # api_ → get_ → fetch_ → three passes strip all three prefixes
        # api_get_fetch_data → get_fetch_data → fetch_data → data
        assert _strip_outer_wrappers("api_get_fetch_data") == "data"


# ---------------------------------------------------------------------------
# describe_get_request_without_catalog
# ---------------------------------------------------------------------------


class TestDescribeGetRequestWithoutCatalog:
    def test_none_endpoint(self):
        assert describe_get_request_without_catalog(None) == "Session ·"

    def test_empty_string(self):
        assert describe_get_request_without_catalog("") == "Session ·"

    def test_api_prefix_endpoint(self):
        result = describe_get_request_without_catalog("admin_notifications.api_get_all_notifications")
        assert result.startswith("Session ·")
        assert "All Notifications" in result

    def test_api_prefix_without_get(self):
        result = describe_get_request_without_catalog("some.api_list_users")
        assert result.startswith("Session ·")
        assert "List Users" in result

    def test_regular_page_endpoint(self):
        result = describe_get_request_without_catalog("analytics.audit_trail")
        assert result.startswith("Session ·")
        assert "Audit Trail" in result

    def test_endpoint_with_other_verb_prefix(self):
        result = describe_get_request_without_catalog("some.post_something")
        assert result.startswith("Session ·")

    def test_endpoint_no_dot(self):
        result = describe_get_request_without_catalog("dashboard")
        assert result.startswith("Session ·")

    def test_api_prefix_only_gives_session_dot(self):
        # api_ with nothing meaningful after
        result = describe_get_request_without_catalog("bp.api_")
        # api_ stripped, then empty readable → "Session ·"
        assert result == "Session ·"


# ---------------------------------------------------------------------------
# blueprint_name
# ---------------------------------------------------------------------------


class TestBlueprintName:
    def test_with_dot(self):
        assert blueprint_name("ai_management.delete_doc") == "ai_management"

    def test_without_dot(self):
        assert blueprint_name("dashboard") == ""

    def test_empty_string(self):
        assert blueprint_name("") == ""

    def test_multiple_dots(self):
        assert blueprint_name("a.b.c") == "a"


# ---------------------------------------------------------------------------
# activity_category_for_endpoint
# ---------------------------------------------------------------------------


class TestActivityCategoryForEndpoint:
    def test_ai_management(self):
        assert activity_category_for_endpoint("ai_management.foo") == "admin_ai"

    def test_ai_documents(self):
        assert activity_category_for_endpoint("ai_documents.bar") == "admin_ai"

    def test_ai_v2(self):
        assert activity_category_for_endpoint("ai_v2.chat") == "admin_ai"

    def test_ai(self):
        assert activity_category_for_endpoint("ai.thing") == "admin_ai"

    def test_ai_ws(self):
        assert activity_category_for_endpoint("ai_ws.connect") == "admin_ai"

    def test_content_management(self):
        assert activity_category_for_endpoint("content_management.edit") == "admin_content"

    def test_embed_management(self):
        assert activity_category_for_endpoint("embed_management.create") == "admin_embed"

    def test_assignment_management(self):
        assert activity_category_for_endpoint("assignment_management.bulk") == "admin_assignments"

    def test_excel(self):
        assert activity_category_for_endpoint("excel.export") == "admin_assignments"

    def test_organization(self):
        assert activity_category_for_endpoint("organization.index") == "admin_organization"

    def test_system_admin(self):
        assert activity_category_for_endpoint("system_admin.settings") == "admin_system"

    def test_template_special(self):
        assert activity_category_for_endpoint("template_special.view") == "admin_system"

    def test_user_management(self):
        assert activity_category_for_endpoint("user_management.list") == "admin_users"

    def test_form_builder(self):
        assert activity_category_for_endpoint("form_builder.edit") == "admin_forms"

    def test_forms(self):
        assert activity_category_for_endpoint("forms.entry") == "admin_forms"

    def test_forms_api(self):
        assert activity_category_for_endpoint("forms_api.submit") == "admin_forms"

    def test_forms_validation_summary(self):
        assert activity_category_for_endpoint("forms_validation_summary.view") == "admin_forms"

    def test_analytics(self):
        assert activity_category_for_endpoint("analytics.audit_trail") == "admin_analytics"

    def test_admin_analytics_api(self):
        assert activity_category_for_endpoint("admin_analytics_api.get") == "admin_analytics"

    def test_data_exploration(self):
        assert activity_category_for_endpoint("data_exploration.view") == "admin_analytics"

    def test_governance_dashboard(self):
        assert activity_category_for_endpoint("governance_dashboard.view") == "admin_analytics"

    def test_utilities(self):
        assert activity_category_for_endpoint("utilities.compile") == "admin_utilities"

    def test_documentation(self):
        assert activity_category_for_endpoint("documentation.view") == "admin_utilities"

    def test_help_docs(self):
        assert activity_category_for_endpoint("help_docs.get") == "admin_utilities"

    def test_settings(self):
        assert activity_category_for_endpoint("settings.manage") == "admin_settings"

    def test_api_key_management(self):
        assert activity_category_for_endpoint("api_key_management.create") == "admin_settings"

    def test_api_management(self):
        assert activity_category_for_endpoint("api_management.list") == "admin_settings"

    def test_rbac_management(self):
        assert activity_category_for_endpoint("rbac_management.edit") == "admin_settings"

    def test_security_dashboard(self):
        assert activity_category_for_endpoint("security_dashboard.view") == "admin_settings"

    def test_plugin_management(self):
        assert activity_category_for_endpoint("plugin_management.install") == "admin_plugin"

    def test_plugins(self):
        assert activity_category_for_endpoint("plugins.list") == "admin_plugin"

    def test_custom_plugin_suffix(self):
        assert activity_category_for_endpoint("my_custom_plugin.action") == "admin_plugin"

    def test_notifications(self):
        assert activity_category_for_endpoint("notifications.send") == "admin_notifications"

    def test_notification_singular(self):
        assert activity_category_for_endpoint("notification.mark_read") == "admin_notifications"

    def test_monitoring(self):
        assert activity_category_for_endpoint("monitoring.status") == "admin_monitoring"

    def test_main(self):
        assert activity_category_for_endpoint("main.dashboard") == "admin_portal"

    def test_public(self):
        assert activity_category_for_endpoint("public.health") == "admin_portal"

    def test_auth(self):
        assert activity_category_for_endpoint("auth.login") == "admin_portal"

    def test_unknown_blueprint(self):
        assert activity_category_for_endpoint("unknown_bp.action") == "admin_other"

    def test_no_dot(self):
        assert activity_category_for_endpoint("noblueprint") == "admin_other"


# ---------------------------------------------------------------------------
# default_generated_description
# ---------------------------------------------------------------------------


class TestDefaultGeneratedDescription:
    def test_get_raises_value_error(self):
        with pytest.raises(ValueError, match="GET is excluded"):
            default_generated_description("GET", "some.endpoint")

    def test_none_method_treated_as_get_raises(self):
        with pytest.raises(ValueError, match="GET is excluded"):
            default_generated_description(None, "some.endpoint")

    def test_empty_endpoint_returns_completed_action(self):
        result = default_generated_description("POST", "")
        assert result == "Completed action"

    def test_delete_remove_prefix(self):
        assert default_generated_description("DELETE", "bp.remove_document") == "Removed Document"

    def test_delete_delete_prefix(self):
        assert default_generated_description("DELETE", "bp.delete_document") == "Deleted Document"

    def test_delete_delete_removed_prefix(self):
        assert default_generated_description("DELETE", "bp.delete_removed_translation") == "Deleted Translation"

    def test_delete_generic_fallback(self):
        result = default_generated_description("DELETE", "bp.some_action")
        assert result.startswith("Deleted ")

    def test_delete_with_api_prefix(self):
        assert default_generated_description("DELETE", "bp.api_delete_document") == "Deleted Document"

    def test_put_update_prefix(self):
        assert default_generated_description("PUT", "bp.update_profile") == "Updated Profile"

    def test_put_edit_prefix(self):
        assert default_generated_description("PUT", "bp.edit_template") == "Edited Template"

    def test_put_delete_prefix(self):
        assert default_generated_description("PUT", "bp.delete_something") == "Deleted Something"

    def test_put_generic_fallback(self):
        result = default_generated_description("PUT", "bp.configure_settings")
        assert result.startswith("Updated ")

    def test_patch_update_prefix(self):
        assert default_generated_description("PATCH", "bp.update_record") == "Updated Record"

    def test_patch_generic_api_stripped(self):
        # api_some_action → some_action; no known prefix → "Updated Some Action"
        result = default_generated_description("PATCH", "bp.api_some_action")
        assert result.startswith("Updated ")

    def test_put_after_strip_update_prefix(self):
        # api_ stripped → update_foo → "Updated Foo"
        assert default_generated_description("PUT", "bp.api_update_settings") == "Updated Settings"

    def test_put_after_strip_edit_prefix(self):
        assert default_generated_description("PUT", "bp.api_edit_form") == "Edited Form"

    def test_post_delete_removed(self):
        assert default_generated_description("POST", "utilities.delete_removed_translation") == "Deleted Translation"

    def test_post_extract_update(self):
        assert default_generated_description("POST", "utilities.extract_update_translations") == "Extracted Translations"

    def test_post_kickout(self):
        assert default_generated_description("POST", "user_management.kickout_device") == "Kicked out Device"

    def test_post_ends_with_cancel(self):
        assert default_generated_description("POST", "ai_documents.import_ifrc_bulk_cancel") == "Cancelled Import Ifrc Bulk"

    def test_post_bulk_update(self):
        result = default_generated_description("POST", "assignment_management.bulk_update_due_date_selected")
        assert "Bulk updated" in result

    def test_post_bulk_remove(self):
        result = default_generated_description("POST", "bp.bulk_remove_members")
        assert "Bulk removed" in result

    def test_post_bulk_enable(self):
        result = default_generated_description("POST", "bp.bulk_enable_users")
        assert "Bulk enabled" in result

    def test_post_bulk_generic(self):
        result = default_generated_description("POST", "bp.bulk_archive_all")
        assert result.startswith("Bulk ")

    def test_post_regenerate(self):
        assert "Regenerated" in default_generated_description("POST", "bp.regenerate_token")

    def test_post_deactivate(self):
        assert "Deactivated" in default_generated_description("POST", "bp.deactivate_user")

    def test_post_duplicate(self):
        assert "Duplicated" in default_generated_description("POST", "bp.duplicate_template")

    def test_post_reprocess(self):
        assert "Reprocessed" in default_generated_description("POST", "bp.reprocess_job")

    def test_post_redetect(self):
        assert "Redetected" in default_generated_description("POST", "bp.redetect_language")

    def test_post_process(self):
        assert "Processed" in default_generated_description("POST", "bp.process_document")

    def test_post_uninstall(self):
        assert "Uninstalled" in default_generated_description("POST", "bp.uninstall_plugin")

    def test_post_configure(self):
        assert "Configured" in default_generated_description("POST", "bp.configure_system")

    def test_post_decline(self):
        assert "Declined" in default_generated_description("POST", "bp.decline_request")

    def test_post_approve(self):
        assert "approved" in default_generated_description("POST", "bp.approve_assignment").lower()

    def test_post_answer(self):
        assert default_generated_description("POST", "ai_documents.answer_documents") == "Answered Documents"

    def test_post_discard(self):
        assert "Discarded" in default_generated_description("POST", "bp.discard_draft")

    def test_post_generate(self):
        assert "Generated" in default_generated_description("POST", "bp.generate_report")

    def test_post_cleanup(self):
        assert "Cleaned up" in default_generated_description("POST", "bp.cleanup_old_data")

    def test_post_activate(self):
        assert "Activated" in default_generated_description("POST", "bp.activate_account")

    def test_post_import(self):
        assert "Imported" in default_generated_description("POST", "bp.import_data")

    def test_post_export(self):
        assert "Exported" in default_generated_description("POST", "bp.export_records")

    def test_post_preview(self):
        assert "Previewed" in default_generated_description("POST", "bp.preview_email")

    def test_post_resolve(self):
        assert "Resolved" in default_generated_description("POST", "bp.resolve_conflict")

    def test_post_install(self):
        assert "Installed" in default_generated_description("POST", "bp.install_plugin")

    def test_post_submit(self):
        assert "submitted" in default_generated_description("POST", "bp.submit_form").lower()

    def test_post_send(self):
        assert "Sent" in default_generated_description("POST", "admin_notifications.api_send_notifications")

    def test_post_deploy(self):
        assert "Deployed" in default_generated_description("POST", "bp.deploy_release")

    def test_post_reorder(self):
        assert "Reordered" in default_generated_description("POST", "bp.reorder_sections")

    def test_post_compile(self):
        assert default_generated_description("POST", "utilities.compile_translations") == "Compiled Translations"

    def test_post_reload(self):
        assert default_generated_description("POST", "utilities.reload_translations") == "Reloaded Translations"

    def test_post_archive(self):
        assert "Archived" in default_generated_description("POST", "bp.archive_records")

    def test_post_remove(self):
        assert "Removed" in default_generated_description("POST", "bp.remove_member")

    def test_post_delete(self):
        assert "Deleted" in default_generated_description("POST", "bp.delete_document")

    def test_post_update(self):
        assert "Updated" in default_generated_description("POST", "bp.update_profile")

    def test_post_toggle(self):
        assert "Toggled" in default_generated_description("POST", "bp.toggle_feature")

    def test_post_reject(self):
        assert "rejected" in default_generated_description("POST", "bp.reject_application").lower()

    def test_post_reopen(self):
        assert "Reopened" in default_generated_description("POST", "bp.reopen_assignment")

    def test_post_create(self):
        assert "Created" in default_generated_description("POST", "bp.create_form")

    def test_post_edit(self):
        assert "Edited" in default_generated_description("POST", "bp.edit_resource")

    def test_post_sync(self):
        assert "Synced" in default_generated_description("POST", "bp.sync_data")

    def test_post_close(self):
        assert "Closed" in default_generated_description("POST", "bp.close_ticket")

    def test_post_clear(self):
        assert "Cleared" in default_generated_description("POST", "bp.clear_cache")

    def test_post_manage(self):
        assert "Managed" in default_generated_description("POST", "bp.manage_settings")

    def test_post_add(self):
        assert "Added" in default_generated_description("POST", "utilities.add_translation")

    def test_post_new(self):
        assert "Created" in default_generated_description("POST", "bp.new_document")

    def test_post_run(self):
        assert "Ran" in default_generated_description("POST", "bp.run_job")

    def test_post_no_known_prefix_completed(self):
        result = default_generated_description("POST", "bp.some_unknown_action")
        assert result.startswith("Completed ")

    def test_other_method_fallback(self):
        result = default_generated_description("OPTIONS", "bp.some_action")
        assert result.startswith("Completed ")

    def test_delete_removed_prefix_with_delete_removed(self):
        # "delete_removed_" compound case
        result = default_generated_description("DELETE", "bp.delete_removed_data")
        assert result == "Deleted Data"

    def test_delete_delete_removed_inner(self):
        # delete_ with tail starting with "removed_"
        result = default_generated_description("DELETE", "bp.delete_removed_entries")
        assert result == "Deleted Entries"


# ---------------------------------------------------------------------------
# catalog_display_description
# ---------------------------------------------------------------------------


class TestCatalogDisplayDescription:
    def test_manual_override_exact_method(self):
        result = catalog_display_description("POST", "ai_management.traces_bulk_delete")
        assert result == "Deleted traces"

    def test_generated_fallback(self):
        result = catalog_display_description("POST", "ai_documents.answer_documents")
        assert result == "Answered Documents"

    def test_get_method_returns_empty(self):
        # GET raises ValueError in default_generated_description → returns ""
        result = catalog_display_description("GET", "some.endpoint_that_does_not_exist")
        assert result == ""

    def test_wildcard_manual_override(self):
        """If ('*', endpoint) exists in MANUAL_ACTIVITY_OVERRIDES, return that description."""
        from app.utils.activity_endpoint_catalog.manual_overrides import MANUAL_ACTIVITY_OVERRIDES

        # Find any wildcard entry to test against
        wildcard_entries = [(m, ep) for (m, ep) in MANUAL_ACTIVITY_OVERRIDES if m == "*"]
        if wildcard_entries:
            _, ep = wildcard_entries[0]
            spec = MANUAL_ACTIVITY_OVERRIDES[("*", ep)]
            result = catalog_display_description("DELETE", ep)
            assert result == spec.description
        else:
            # No wildcard entries; test by injecting one
            from unittest.mock import patch

            fake_spec = ActivityEndpointSpec(description="Wildcard Description")
            fake_overrides = {("*", "fake.wildcard_endpoint"): fake_spec}
            with patch(
                "app.utils.activity_endpoint_catalog.defaults.MANUAL_ACTIVITY_OVERRIDES",
                fake_overrides,
            ):
                result = catalog_display_description("PUT", "fake.wildcard_endpoint")
                assert result == "Wildcard Description"
