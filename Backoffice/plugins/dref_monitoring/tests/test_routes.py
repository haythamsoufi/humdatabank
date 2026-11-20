"""Settings page access for the DREF monitoring plugin."""

from __future__ import annotations

import pytest

import plugins.dref_monitoring.models  # noqa: F401 — tables exist before the test schema is built
from plugins.dref_monitoring.plugin import DrefMonitoringPlugin

pytestmark = pytest.mark.db


def test_plugin_class_loads():
    plugin = DrefMonitoringPlugin()
    assert plugin.plugin_id == "dref_monitoring"
    assert plugin.version == "0.7.0"
    assert plugin.get_blueprint().name == "dref_monitoring"
    assert plugin.get_seed_permissions()
    assert plugin.get_scheduled_jobs()


def test_settings_page_is_registered(app):
    endpoint, values = app.url_map.bind("localhost").match("/admin/plugins/dref_monitoring/settings")
    assert endpoint == "dref_monitoring.settings_page"
    assert values == {}


def test_settings_page_is_denied_to_anonymous_users(client):
    response = client.get("/admin/plugins/dref_monitoring/settings")
    assert response.status_code in (302, 401, 403, 404)


def test_operations_page_hides_closed_until_requested(app, db_session, logged_in_sm_client):
    from app.plugins.lifecycle_store import save_active_plugin_ids
    from plugins.dref_monitoring.models import DrefOperation

    previous = set(app.plugin_manager.active_plugins)
    save_active_plugin_ids(sorted(previous | {"dref_monitoring"}))
    app.plugin_manager.sync_activation_state()
    db_session.add(DrefOperation(appeal_code="MDROPEN1", disaster_name="Open flood", operation_status="active", workflow_status="plan_draft"))
    db_session.add(DrefOperation(appeal_code="MDRSHUT1", disaster_name="Closed flood", operation_status="closed"))
    db_session.add(DrefOperation(appeal_code="MDRNONE1", disaster_name="Unset flood", operation_status="unspecified"))
    db_session.commit()
    try:
        hidden = logged_in_sm_client.get("/dref-monitoring/operations")
        assert hidden.status_code == 200
        hidden_body = hidden.get_data(as_text=True)
        assert "MDROPEN1" in hidden_body
        assert "MDRSHUT1" not in hidden_body
        assert "MDRNONE1" not in hidden_body
        assert "Show closed" in hidden_body
        assert "Plan draft" in hidden_body
        assert "status-label--pending" in hidden_body
        assert "status-label--success" in hidden_body
        assert "plan_draft" not in hidden_body

        shown = logged_in_sm_client.get("/dref-monitoring/operations?include_closed=1")
        assert shown.status_code == 200
        shown_body = shown.get_data(as_text=True)
        assert "MDROPEN1" in shown_body
        assert "MDRSHUT1" in shown_body
        assert "MDRNONE1" in shown_body
        assert "Not set" in shown_body
        assert "Hide closed" in shown_body
        assert 'data-closed="1"' in shown_body
        assert "data-closed" not in hidden_body
    finally:
        app.plugin_manager.active_plugins = previous


def test_draft_page_previews_the_document_and_serves_word(app, db_session, logged_in_sm_client):
    from app.plugins.lifecycle_store import save_active_plugin_ids
    from plugins.dref_monitoring.models import DrefDraft, DrefOperation

    previous = set(app.plugin_manager.active_plugins)
    save_active_plugin_ids(sorted(previous | {"dref_monitoring"}))
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
        page = logged_in_sm_client.get(f"/dref-monitoring/operations/{operation.id}/drafts/{draft.id}")
        assert page.status_code == 200
        body = page.get_data(as_text=True)
        assert "DREF Operational Update" in body
        assert "Description of the event" in body
        assert "dref-report" in body
        assert "export.docx" in body
        assert "export.pdf" in body
        assert "export.json" not in body
        assert 'name="edited_body"' not in body
        missing = logged_in_sm_client.get(
            f"/dref-monitoring/operations/{operation.id}/drafts/{draft.id}/export.json"
        )
        assert missing.status_code == 404
        word = logged_in_sm_client.get(
            f"/dref-monitoring/operations/{operation.id}/drafts/{draft.id}/export.docx"
        )
        assert word.status_code == 200
        assert word.data.startswith(b"PK")
        assert "wordprocessingml" in word.mimetype
    finally:
        app.plugin_manager.active_plugins = previous


def test_settings_page_renders_for_a_system_manager(app, db_session, logged_in_sm_client):
    from app.plugins.lifecycle_store import save_active_plugin_ids

    previous = set(app.plugin_manager.active_plugins)
    save_active_plugin_ids(sorted(previous | {"dref_monitoring"}))
    app.plugin_manager.sync_activation_state()
    try:
        response = logged_in_sm_client.get("/admin/plugins/dref_monitoring/settings")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "DREF" in body
        assert "plugins/_plugin_info_card.html" not in body
        assert 'id="dref-settings-tabs"' in body
        assert 'data-tab="settings"' in body
        assert 'data-tab="sync"' in body
        assert 'id="panel-overview"' in body
        assert "Sync history" in body
        assert "/dref-monitoring/operations" in body
        assert "dref-sync-filter" not in body
        assert "What Sync from GO does" in body
        assert 'id="dref-go-sync-form"' in body
        assert "go_sync.js" in body
        assert "The sync runs in the background" in body
    finally:
        app.plugin_manager.active_plugins = previous
