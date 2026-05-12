"""Unit tests for audit trail display helpers (no DB)."""

from app.services.audit_trail_display_service import (
    consolidate_activity_type,
    create_consistent_description,
    refine_activity_row_consolidated_type,
    _extract_aes_and_template_ids_from_context,
)


def test_consolidate_activity_type_legacy_form_save():
    assert consolidate_activity_type("form_save") == "form_saved"


def test_consolidate_activity_type_data_save_normalized():
    assert consolidate_activity_type("data_save") == "form_saved"


def test_consolidate_activity_type_admin_action():
    assert consolidate_activity_type(None, "user_create") == "user_create"


def test_refine_request_from_endpoint():
    t = refine_activity_row_consolidated_type(
        "request",
        "Submitted Manage Settings",
        "settings.manage_settings",
        http_method="POST",
    )
    assert t == "admin_settings"


def test_extract_aes_from_enter_data_url():
    aes_id, tid = _extract_aes_and_template_ids_from_context(
        {"url_path": "/forms/enter_data/42/extra", "form_data": {}}
    )
    assert aes_id == 42
    assert tid is None


def test_create_consistent_description_page_view_strip_prefix():
    d = create_consistent_description(
        "activity",
        "page_view",
        None,
        None,
        "main.api_get_notifications",
        {},
    )
    assert "Session ·" in d
    assert "Notification" in d


def test_create_consistent_description_form_saved_uses_lookups():
    from app.services.audit_trail_display_service import FormContextLookups

    lookups = FormContextLookups(
        aes_by_id={
            1: {
                "template_name": "T1",
                "assignment_name": "2024",
                "country_name": "Xland",
            }
        },
        template_name_by_id={},
    )
    ctx = {"form_data": {"aes_id": "1"}}
    d = create_consistent_description(
        "activity",
        "form_saved",
        None,
        None,
        "forms.enter_data",
        ctx,
        form_lookups=lookups,
    )
    assert "T1" in d
    assert "Xland" in d
