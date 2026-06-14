"""Smoke tests for shared Excel import/export UI partials."""

import pytest


@pytest.mark.integration
class TestExcelIoUiMarkup:
    def test_new_template_page_renders_excel_io_dropzone(self, logged_in_sm_client):
        resp = logged_in_sm_client.get("/admin/templates/new")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8", errors="replace")
        assert 'class="excel-io-dropzone' in html
        assert 'id="excel-import-dropzone"' in html
        assert 'id="kobo-import-dropzone"' in html

    def test_indicator_bank_renders_excel_io_modal(self, logged_in_sm_client):
        resp = logged_in_sm_client.get("/admin/indicator_bank")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8", errors="replace")
        assert 'id="export-import-modal"' in html
        assert 'id="indicator-import-dropzone"' in html
        assert 'data-excel-io-layout="split"' in html

    def test_form_builder_renders_excel_io_dropzone(self, logged_in_sm_client, db_session, app, system_manager_user):
        from tests.factories import create_test_template

        with app.app_context():
            previous_csrf = app.config.get("WTF_CSRF_ENABLED")
            app.config["WTF_CSRF_ENABLED"] = True
            try:
                template = create_test_template(db_session, owner_id=system_manager_user.id)
                template_id = template.id

                resp = logged_in_sm_client.get(f"/admin/templates/edit/{template_id}")
                assert resp.status_code == 200
                html = resp.data.decode("utf-8", errors="replace")
                assert 'id="excel-options-modal"' in html
                assert 'class="excel-io-dropzone' in html
                assert 'excel-import-dropzone' in html
            finally:
                app.config["WTF_CSRF_ENABLED"] = previous_csrf
