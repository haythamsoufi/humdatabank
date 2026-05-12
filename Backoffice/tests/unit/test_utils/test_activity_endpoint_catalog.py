"""Tests for per-endpoint activity catalog."""

from app.utils.activity_endpoint_catalog import (
    ENDPOINT_ACTIVITY_SPECS,
    resolve_activity_catalog_spec,
)
from app.utils.activity_endpoint_catalog.defaults import (
    catalog_display_description,
    default_generated_description,
    describe_get_request_without_catalog,
)
from app.utils.activity_endpoint_catalog.spec import merge_activity_specs


def test_catalog_keys_unique_after_merge():
    assert len(ENDPOINT_ACTIVITY_SPECS) == len(set(ENDPOINT_ACTIVITY_SPECS.keys()))


def test_manual_override_traces_bulk_delete():
    s = resolve_activity_catalog_spec("POST", "ai_management.traces_bulk_delete")
    assert s is not None
    assert s.description == "Deleted traces"
    assert s.activity_type == "admin_ai"


def test_manual_override_edit_resource():
    s = resolve_activity_catalog_spec("POST", "content_management.edit_resource")
    assert s is not None
    assert s.description == "Edited resource"


def test_manual_override_embed_content():
    s = resolve_activity_catalog_spec("POST", "embed_management.create_embed_content")
    assert s is not None
    assert s.description == "Created embed content"


def test_default_generated_description_verbs():
    assert default_generated_description("POST", "ai_management.delete_document") == "Deleted Document"
    assert (
        default_generated_description("DELETE", "assignment_management.remove_entity_from_assignment")
        == "Removed Entity From Assignment"
    )
    assert default_generated_description("PUT", "embed_management.update_embed_content") == "Updated Embed Content"
    assert default_generated_description("PATCH", "embed_management.update_embed_content") == "Updated Embed Content"
    assert default_generated_description("POST", "x.api_delete_document") == "Deleted Document"
    assert "Bulk updated" in default_generated_description(
        "POST", "assignment_management.bulk_update_due_date_selected"
    )
    assert default_generated_description("POST", "utilities.delete_removed_translation") == "Deleted Translation"
    assert default_generated_description(
        "POST", "utilities.extract_update_translations"
    ) == "Extracted Translations"
    assert default_generated_description("POST", "utilities.reload_translations") == "Reloaded Translations"
    assert default_generated_description("POST", "utilities.compile_translations") == "Compiled Translations"
    assert default_generated_description("POST", "utilities.add_translation") == "Added Translation"
    assert default_generated_description("POST", "user_management.kickout_device") == "Kicked out Device"
    assert default_generated_description(
        "POST", "ai_documents.import_ifrc_bulk_cancel"
    ) == "Cancelled Import Ifrc Bulk"
    assert default_generated_description(
        "POST", "admin_notifications.api_send_notifications"
    ) == "Sent Notifications"
    assert default_generated_description("POST", "ai_documents.answer_documents") == "Answered Documents"


def test_catalog_display_description_respects_manual_overrides():
    assert catalog_display_description("POST", "ai_management.traces_bulk_delete") == "Deleted traces"
    assert catalog_display_description("POST", "ai_documents.answer_documents") == "Answered Documents"


def test_describe_get_api_vs_page():
    assert describe_get_request_without_catalog("admin_notifications.api_get_all_notifications").startswith(
        "Session ·"
    )
    assert describe_get_request_without_catalog("analytics.audit_trail").startswith("Session ·")


def test_merge_activity_specs_later_wins():
    from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec

    a = {("POST", "x.y"): ActivityEndpointSpec(description="a")}
    b = {("POST", "x.y"): ActivityEndpointSpec(description="b")}
    m = merge_activity_specs(a, b)
    assert m[("POST", "x.y")].description == "b"
