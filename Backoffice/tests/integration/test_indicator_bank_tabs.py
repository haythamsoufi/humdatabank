"""Indicator Bank tabbed page markup smoke tests."""

import re

import pytest


@pytest.mark.integration
class TestIndicatorBankTabMarkup:
    def test_default_tab_renders_visible_indicators_panel(self, logged_in_sm_client):
        resp = logged_in_sm_client.get("/admin/indicator_bank")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8", errors="replace")

        assert 'id="indicator-bank-tabs"' in html
        assert 'id="panel-indicators"' in html
        assert re.search(r'class="[^"]*\bib-tab-panel\b[^"]*"[^>]*id="panel-indicators"', html)
        assert re.search(r'class="[^"]*\bib-tab-panel\b[^"]*\bhidden\b[^"]*"[^>]*id="panel-sectors"', html)

    def test_head_style_tags_are_balanced(self, logged_in_sm_client):
        resp = logged_in_sm_client.get("/admin/indicator_bank")
        html = resp.data.decode("utf-8", errors="replace")
        head_end = html.find("</head>")
        assert head_end > 0
        head = html[:head_end]
        assert head.count("<style") == head.count("</style>")

    @pytest.mark.parametrize(
        "tab",
        ["sectors", "common_words", "types", "units", "spef", "indicators", "measurement"],
    )
    def test_tab_query_param_returns_200(self, logged_in_sm_client, tab):
        resp = logged_in_sm_client.get(f"/admin/indicator_bank?tab={tab}")
        assert resp.status_code == 200

    def test_types_tab_renders_types_panel(self, logged_in_sm_client):
        resp = logged_in_sm_client.get("/admin/indicator_bank?tab=types")
        html = resp.data.decode("utf-8", errors="replace")
        assert 'id="panel-types"' in html
        assert 'id="measurementTypesGrid"' in html
        assert re.search(r'class="[^"]*\bib-tab-panel\b[^"]*"[^>]*id="panel-types"', html)
        assert re.search(r'class="[^"]*\bib-tab-panel\b[^"]*\bhidden\b[^"]*"[^>]*id="panel-units"', html)

    def test_units_tab_renders_units_panel(self, logged_in_sm_client):
        resp = logged_in_sm_client.get("/admin/indicator_bank?tab=units")
        html = resp.data.decode("utf-8", errors="replace")
        assert 'id="panel-units"' in html
        assert 'id="measurementUnitsGrid"' in html
        assert re.search(r'class="[^"]*\bib-tab-panel\b[^"]*"[^>]*id="panel-units"', html)
        assert re.search(r'class="[^"]*\bib-tab-panel\b[^"]*\bhidden\b[^"]*"[^>]*id="panel-types"', html)

    def test_legacy_measurement_tab_maps_to_types(self, logged_in_sm_client):
        resp = logged_in_sm_client.get("/admin/indicator_bank?tab=measurement")
        html = resp.data.decode("utf-8", errors="replace")
        assert 'id="panel-types"' in html
        assert re.search(r'class="[^"]*\bib-tab-panel\b[^"]*"[^>]*id="panel-types"', html)
        assert re.search(r'class="[^"]*\bib-tab-panel\b[^"]*\bhidden\b[^"]*"[^>]*id="panel-units"', html)

    @pytest.mark.parametrize(
        "panel_id",
        ["panel-indicators", "panel-common_words", "panel-types", "panel-units", "panel-spef"],
    )
    def test_edit_tab_panels_stay_inside_white_card(self, logged_in_sm_client, panel_id):
        """Regression: tab panels must not close the shared white card early."""
        from html.parser import HTMLParser

        class ParentChecker(HTMLParser):
            def __init__(self, target_id):
                super().__init__()
                self.target_id = target_id
                self.stack = []
                self.found = False
                self.parent_classes = []

            def handle_starttag(self, tag, attrs):
                if tag != "div":
                    return
                attrs_d = dict(attrs)
                self.stack.append(attrs_d.get("class", ""))
                if attrs_d.get("id") == self.target_id:
                    self.found = True
                    self.parent_classes = [c for c in self.stack[:-1] if c]

            def handle_endtag(self, tag):
                if tag == "div" and self.stack:
                    self.stack.pop()

        html = logged_in_sm_client.get("/admin/indicator_bank").data.decode("utf-8", errors="replace")
        checker = ParentChecker(panel_id)
        checker.feed(html)
        assert checker.found
        assert any("bg-white" in c and "shadow-md" in c for c in checker.parent_classes)
