"""Global Awards and NSD settings use the shared Excel import tab."""
import pytest


def _page(client, path):
    resp = client.get(path)
    if resp.status_code == 404:
        pytest.skip("plugin is not active in this test app")
    assert resp.status_code == 200, resp.status_code
    return resp.get_data(as_text=True)


@pytest.mark.unit
def test_global_awards_import_tab_uses_the_standard_dropzone(logged_in_sm_client):
    html = _page(logged_in_sm_client, "/admin/plugins/global_awards/settings?tab=import")
    assert 'data-tab="import"' in html
    assert 'id="ga-import-dropzone"' in html
    assert "Files on disk" in html
    assert "Last import" in html
    assert "Change logs" in html
    assert 'type="file"' in html
    assert "excel-io-dropzone" in html


@pytest.mark.unit
def test_nsd_import_tab_uses_the_standard_dropzone(logged_in_sm_client):
    html = _page(logged_in_sm_client, "/admin/plugins/nsd_report_forms/settings?tab=import")
    assert 'data-tab="import"' in html
    assert 'id="nsd-import-dropzone"' in html
    assert "Files on disk" in html
    assert "Last import" in html
    assert "Change logs" in html
    assert "excel-io-dropzone" in html
    assert 'id="nsdi-file"' not in html
