"""PPP dashboard aggregation, without a database."""

from __future__ import annotations

from datetime import date

from flask import Flask

from app.plugins.jinja_plugin_loader import PluginTemplateLoader
from plugins.ifrc import _PLUGIN_DIR, bp
from plugins.ifrc.ppp.catalogue import is_activity_field, is_pillar_reach, is_public_indicator
from plugins.ifrc.ppp.dashboard import assemble_dashboard, choose_latest

def _row(country_id, template_key, period_end, fields, name="Mali", region="Africa"):
    return {
        "status": "approved",
        "aes_id": country_id,
        "template_key": template_key,
        "country_id": country_id,
        "name": name,
        "iso2": "ML",
        "iso3": "MLI",
        "region": region,
        "lat": 17.0,
        "lng": -4.0,
        "period_end": period_end,
        "fields": fields,
    }


def test_latest_approved_window_replaces_an_earlier_one():
    early = _row(1, "drm", date(2023, 6, 30), [])
    early["aes_id"] = 1
    late = _row(1, "drm", date(2025, 6, 30), [])
    late["aes_id"] = 2
    held = _row(1, "drm", date(2026, 1, 1), [])
    held["status"] = "submitted"
    held["aes_id"] = 3
    chosen = choose_latest([early, late, held])
    assert len(chosen) == 1
    assert chosen[0]["aes_id"] == 2


def test_headline_is_unique_people_and_pillars_stay_separate():
    overview = _row(1, "overview", date(2025, 6, 30), [
        {
            "kobo_name": "unique_indiv_country_q",
            "label": "How many unique individuals have been reached across all results",
            "item_type": "indicator",
            "question_type": "number",
            "number": 100,
        }
    ])
    drm = _row(1, "drm", date(2025, 6, 30), [
        {
            "kobo_name": "individuals_num_1",
            "label": "How many unique individuals your National Society has reached by disaster risk management",
            "item_type": "indicator",
            "question_type": "number",
            "number": 80,
        },
        {
            "kobo_name": "R1DRM_act_1.1",
            "label": "1.1 At-risk communities receive actionable risk information",
            "item_type": "question",
            "question_type": "single_choice",
            "text": "applicable",
            "order": 2,
        },
        {
            "kobo_name": "R1DRM_act_1.1_nar",
            "label": "Please explain",
            "item_type": "question",
            "question_type": "textarea",
            "text": "Early warning messages were shared.",
            "order": 3,
        },
        {
            "kobo_name": "R1DRM_ind_1_warning_system",
            "label": "1.1 How many people have been reached by a functional early warning system?",
            "item_type": "indicator",
            "question_type": "number",
            "number": 40,
            "order": 4,
        },
    ], name="Mali")
    other = _row(2, "overview", date(2025, 6, 30), [
        {
            "kobo_name": "unique_indiv_country_q",
            "label": "How many unique individuals have been reached across all results",
            "item_type": "indicator",
            "question_type": "number",
            "number": 50,
        }
    ], name="Niger", region="Africa")
    payload = assemble_dashboard([overview, drm, other])
    mali = next(country for country in payload["countries"] if country["name"] == "Mali")
    assert mali["reached"] == 100
    assert mali["pillars"]["drm"] == 80
    assert mali["indicators"]["R1DRM_ind_1_warning_system"] == 40
    assert mali["activities"]["R1DRM_act_1.1"]["applicable"] is True
    assert "Early warning" in mali["activities"]["R1DRM_act_1.1"]["narrative"]
    assert sum(country["reached"] for country in payload["countries"]) == 150
    assert payload["activity_catalogue"][0]["title"].startswith("At-risk communities")
    assert payload["indicator_catalogue"][0]["title"].startswith("How many people have been reached")


def test_activity_and_reach_classification():
    assert is_activity_field("R1DRM_act_1.1")
    assert not is_activity_field("R1DRM_act_1.1_nar")
    assert not is_activity_field("R2EPPR_ind_1_KAP")
    assert is_pillar_reach("drm", "individuals_num_1", "")
    assert not is_public_indicator(
        "individuals_num_1",
        "How many unique individuals your National Society has reached",
        "indicator",
        "number",
    )
    assert is_public_indicator(
        "R1DRM_ind_5_contingency",
        "Does your National Society coordinate early action?",
        "question",
        "yesno",
    )


def _ppp_app():
    app = Flask(__name__)
    app.config.update(TESTING=True, DEBUG=True, SECRET_KEY="test", RATE_LIMIT_SKIP_DEBUG=True)
    app.jinja_loader = PluginTemplateLoader(
        lambda pid: (_PLUGIN_DIR / "templates") if pid == "ifrc" else None
    )
    app.register_blueprint(bp)
    return app


def test_dashboard_page_uses_the_plugin_template():
    client = _ppp_app().test_client()
    response = client.get("/ifrc/ppp")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert "Pilot Programmatic Partnership" in html
    assert 'data-view="overview"' in html
    assert 'id="ppp-app"' in html
    assert "/ifrc/ppp/data" in html
    assert "ppp-dashboard.css" in html
    assert "ppp-dashboard.js" in html


def test_dashboard_detail_view_and_legacy_redirect():
    client = _ppp_app().test_client()
    detail = client.get("/ifrc/ppp?view=detail")
    assert detail.status_code == 200
    assert 'data-view="detail"' in detail.get_data(as_text=True)

    redirect = client.get("/ifrc/ppp/detail")
    assert redirect.status_code == 302
    assert redirect.headers["Location"].endswith("/ifrc/ppp?view=detail")


def test_powerbi_format_wraps_the_live_dashboard():
    client = _ppp_app().test_client()
    response = client.get("/ifrc/ppp?format=powerbi")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "<iframe" in html
    assert "Pilot Programmatic Partnership" in html
    assert "/ifrc/ppp" in html
