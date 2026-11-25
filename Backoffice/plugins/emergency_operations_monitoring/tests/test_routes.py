"""Settings page access for the Emergency Operations plugin."""

from __future__ import annotations

import pytest

import plugins.emergency_operations_monitoring.models  # noqa: F401 — tables exist before the test schema is built
from plugins.emergency_operations_monitoring.plugin import EmergencyOperationsMonitoringPlugin

pytestmark = pytest.mark.db


def test_plugin_class_loads():
    plugin = EmergencyOperationsMonitoringPlugin()
    assert plugin.plugin_id == "emergency_operations_monitoring"
    assert plugin.version == "0.13.0"
    assert plugin.get_blueprint().name == "emergency_operations_monitoring"
    assert plugin.get_seed_permissions()
    assert plugin.get_scheduled_jobs()


def test_settings_page_is_registered(app):
    endpoint, values = app.url_map.bind("localhost").match("/admin/plugins/emergency_operations_monitoring/settings")
    assert endpoint == "emergency_operations_monitoring.settings_page"
    assert values == {}


def test_the_team_tab_explains_what_members_do(app, db_session, logged_in_sm_client):
    from app.plugins.lifecycle_store import save_active_plugin_ids
    from plugins.emergency_operations_monitoring.models import DrefOperation

    previous = set(app.plugin_manager.active_plugins)
    save_active_plugin_ids(sorted(previous | {"emergency_operations_monitoring"}))
    app.plugin_manager.sync_activation_state()
    operation = DrefOperation(appeal_code="MDRHELP1", disaster_name="Help flood", operation_status="active")
    db_session.add(operation)
    db_session.commit()
    try:
        page = logged_in_sm_client.get(f"/emergency-operations/operations/{operation.id}?tab=team")
        assert page.status_code == 200
        body = page.get_data(as_text=True)
        assert 'id="dref-member-help-open"' in body
        assert "A member already holds an Emergency Operations role." in body
        assert "Opening a reporting assignment also requires the Emergency Operations access group." in body
    finally:
        app.plugin_manager.active_plugins = previous


def test_settings_page_is_denied_to_anonymous_users(client):
    response = client.get("/admin/plugins/emergency_operations_monitoring/settings")
    assert response.status_code in (302, 401, 403, 404)


def test_operations_page_hides_closed_until_requested(app, db_session, logged_in_sm_client):
    from app.plugins.lifecycle_store import save_active_plugin_ids
    from plugins.emergency_operations_monitoring.models import DrefOperation

    previous = set(app.plugin_manager.active_plugins)
    save_active_plugin_ids(sorted(previous | {"emergency_operations_monitoring"}))
    app.plugin_manager.sync_activation_state()
    db_session.add(DrefOperation(appeal_code="MDROPEN1", disaster_name="Open flood", operation_status="active", workflow_status="plan_draft"))
    db_session.add(DrefOperation(appeal_code="MDRSHUT1", disaster_name="Closed flood", operation_status="closed"))
    db_session.add(DrefOperation(appeal_code="MDRNONE1", disaster_name="Unset flood", operation_status="unspecified"))
    db_session.commit()
    try:
        hidden = logged_in_sm_client.get("/emergency-operations/operations")
        assert hidden.status_code == 200
        hidden_body = hidden.get_data(as_text=True)
        assert "MDROPEN1" in hidden_body
        assert "MDRSHUT1" not in hidden_body
        assert "MDRNONE1" not in hidden_body
        assert "Show closed" in hidden_body
        assert "Active approved emergency operations from GO." in hidden_body
        assert "Plan draft" in hidden_body
        assert "status-label--pending" in hidden_body
        assert ">Status</th>" not in hidden_body
        assert "plan_draft" not in hidden_body

        shown = logged_in_sm_client.get("/emergency-operations/operations?include_closed=1")
        assert shown.status_code == 200
        shown_body = shown.get_data(as_text=True)
        assert "MDROPEN1" in shown_body
        assert "MDRSHUT1" in shown_body
        assert "MDRNONE1" in shown_body
        assert "Not set" in shown_body
        assert ">Status</th>" in shown_body
        assert "Active approved emergency operations from GO." not in shown_body
        assert "Hide closed" in shown_body
        assert 'data-closed="1"' in shown_body
        assert "data-closed" not in hidden_body
    finally:
        app.plugin_manager.active_plugins = previous


def test_draft_page_previews_the_document_and_serves_word(app, db_session, logged_in_sm_client):
    from app.plugins.lifecycle_store import save_active_plugin_ids
    from plugins.emergency_operations_monitoring.models import DrefDraft, DrefOperation

    previous = set(app.plugin_manager.active_plugins)
    save_active_plugin_ids(sorted(previous | {"emergency_operations_monitoring"}))
    app.plugin_manager.sync_activation_state()
    operation = DrefOperation(
        appeal_code="MDRPREV1",
        disaster_name="Preview flood",
        country_name="Zedland",
        hazard="Flood",
        operation_status="active",
        workflow_status="monitoring",
    )
    db_session.add(operation)
    db_session.flush()
    draft = DrefDraft(
        operation_id=operation.id,
        report_kind="operational_update",
        input_hash="abc",
        sections={},
        body="",
    )
    db_session.add(draft)
    db_session.commit()
    try:
        page = logged_in_sm_client.get(f"/emergency-operations/operations/{operation.id}/drafts/{draft.id}")
        assert page.status_code == 200
        body = page.get_data(as_text=True)
        assert "Operational Update" in body
        assert "Description of the event" in body
        assert "dref-report" in body
        assert 'id="dref-draft-tabs"' in body
        assert 'data-tab="narrative"' in body
        assert 'data-tab="preview"' in body
        assert 'id="panel-narrative"' in body
        assert 'id="panel-preview"' in body
        assert 'id="panel-preview" role="tabpanel"' in body
        preview = logged_in_sm_client.get(
            f"/emergency-operations/operations/{operation.id}/drafts/{draft.id}?tab=preview"
        )
        assert preview.status_code == 200
        preview_body = preview.get_data(as_text=True)
        assert 'id="panel-narrative"' in preview_body
        assert 'class="settings-panel space-y-4 hidden"' in preview_body
        assert 'id="panel-preview" role="tabpanel" aria-labelledby="dref-draft-tab-preview"' in preview_body
        assert "hidden" not in preview_body.split('id="panel-preview"', 1)[1].split(">", 1)[0]
        assert "export.docx" in body
        assert "export.pdf" in body
        assert "export.json" not in body
        assert 'name="edited_body"' not in body
        missing = logged_in_sm_client.get(
            f"/emergency-operations/operations/{operation.id}/drafts/{draft.id}/export.json"
        )
        assert missing.status_code == 404
        word = logged_in_sm_client.get(
            f"/emergency-operations/operations/{operation.id}/drafts/{draft.id}/export.docx"
        )
        assert word.status_code == 200
        assert word.data.startswith(b"PK")
        assert "wordprocessingml" in word.mimetype
    finally:
        app.plugin_manager.active_plugins = previous


def test_settings_page_renders_for_a_system_manager(app, db_session, logged_in_sm_client):
    from app.plugins.lifecycle_store import save_active_plugin_ids

    previous = set(app.plugin_manager.active_plugins)
    save_active_plugin_ids(sorted(previous | {"emergency_operations_monitoring"}))
    app.plugin_manager.sync_activation_state()
    try:
        response = logged_in_sm_client.get("/admin/plugins/emergency_operations_monitoring/settings")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Emergency Operations" in body
        assert "plugins/_plugin_info_card.html" not in body
        assert 'id="dref-settings-tabs"' in body
        assert 'data-tab="settings"' in body
        assert 'data-tab="sync"' in body
        assert 'id="panel-overview"' in body
        assert "Sync history" in body
        assert "/emergency-operations/operations" in body
        assert "dref-sync-filter" not in body
        assert "What Sync from GO does" in body
        assert 'id="dref-go-sync-form"' in body
        assert "go_sync.js" in body
        assert "The sync runs in the background" in body
    finally:
        app.plugin_manager.active_plugins = previous


def test_an_earlier_plan_can_be_viewed_and_copied_back(app, db_session, logged_in_sm_client):
    from app.plugins.lifecycle_store import save_active_plugin_ids
    from plugins.emergency_operations_monitoring.models import DrefActivity, DrefGroup, DrefOperation, DrefPlan

    previous = set(app.plugin_manager.active_plugins)
    save_active_plugin_ids(sorted(previous | {"emergency_operations_monitoring"}))
    app.plugin_manager.sync_activation_state()
    operation = DrefOperation(appeal_code="MDRVER1", disaster_name="Version flood", operation_status="active")
    db_session.add(operation)
    db_session.flush()
    older = DrefPlan(operation_id=operation.id, version=1, status="validated", source="generated")
    newer = DrefPlan(operation_id=operation.id, version=2, status="draft", source="rebased")
    db_session.add_all([older, newer])
    db_session.flush()
    older_group = DrefGroup(plan_id=older.id, key="health", label="Health", sort_order=0)
    newer_group = DrefGroup(plan_id=newer.id, key="health", label="Health", sort_order=0)
    db_session.add_all([older_group, newer_group])
    db_session.flush()
    db_session.add(DrefActivity(group_id=older_group.id, title="Clinic support kept", sort_order=0))
    db_session.add(DrefActivity(group_id=newer_group.id, title="Later activity", sort_order=0))
    db_session.commit()
    try:
        page = logged_in_sm_client.get(f"/emergency-operations/operations/{operation.id}?tab=plan&plan_version=1")
        assert page.status_code == 200
        body = page.get_data(as_text=True)
        assert "Clinic support kept" in body
        assert "You are viewing version 1. Reporting uses version 2." in body
        assert "data-dref-plan-start" not in body
        assert "data-dref-funds-toggle" in body
        assert 'id="dref-plan-versions-modal"' in body
        assert "Use this version" in body
        assert "Plan versions" in body
        assert "Export Excel" in body
        assert f"/emergency-operations/operations/{operation.id}/export?plan_version=1" in body
        assert f"/emergency-operations/operations/{operation.id}/import" not in body

        exported = logged_in_sm_client.get(f"/emergency-operations/operations/{operation.id}/export?plan_version=1")
        assert exported.status_code == 200
        assert exported.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert "MDRVER1-monitoring-plan-v1.xlsx" in exported.headers.get("Content-Disposition", "")
        from plugins.emergency_operations_monitoring.services.excel_import import parse_workbook

        rows = parse_workbook(exported.data)
        assert rows[0]["activity"] == "Clinic support kept"

        current = logged_in_sm_client.get(f"/emergency-operations/operations/{operation.id}/export")
        assert parse_workbook(current.data)[0]["activity"] == "Later activity"

        missing = logged_in_sm_client.get(f"/emergency-operations/operations/{operation.id}?tab=plan&plan_version=9")
        assert missing.status_code == 200
        assert "That plan version was not found." in missing.get_data(as_text=True)
        assert "Later activity" in missing.get_data(as_text=True)

        restored = logged_in_sm_client.post(
            f"/emergency-operations/operations/{operation.id}/plan/restore",
            data={"version": "1", "tab": "plan"},
            follow_redirects=True,
        )
        assert restored.status_code == 200, (restored.status_code, restored.request.path)
        restored_body = restored.get_data(as_text=True)
        assert "Version 1 was copied into a new draft." in restored_body
        assert "Clinic support kept" in restored_body
        assert "data-dref-plan-start" in restored_body
        assert "You are viewing version" not in restored_body
        copied = DrefPlan.query.filter_by(operation_id=operation.id, version=3).one()
        assert copied.status == "draft"
        assert copied.source == "restored"
        assert DrefPlan.query.filter_by(operation_id=operation.id, version=1).one().status == "validated"
    finally:
        app.plugin_manager.active_plugins = previous
