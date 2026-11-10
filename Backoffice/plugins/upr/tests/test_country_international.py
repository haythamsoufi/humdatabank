"""Unit tests for country-scoped international bilateral support helpers."""

from __future__ import annotations

from unittest.mock import patch

from plugins.upr.analysis.country_international import (
    build_country_international,
    clear_pns_country_iso3s_cache,
    country_is_pns,
    pns_country_iso3s,
)


def _flows(**overrides):
    base = {
        "years": [2026, 2025],
        "nodes": [
            {"iso3": "NOR", "name": "Norway", "out_weight": 1, "in_weight": 0, "role": "donor"},
            {"iso3": "SYR", "name": "Syria", "out_weight": 0, "in_weight": 1, "role": "host"},
        ],
        "edges": [
            {"from": "NOR", "to": "SYR", "years": [2026], "weight": 1},
        ],
        "funding": [
            {
                "year": 2026,
                "from": "NOR",
                "from_name": "Norwegian Red Cross",
                "to": "SYR",
                "to_name": "Syria",
                "value": 1_500_000,
            }
        ],
        "figures": [
            {
                "year": 2026,
                "from": "NOR",
                "to": "SYR",
                "funding": 1_500_000,
                "requirement": 2_000_000,
                "expenditure": 900_000,
            }
        ],
    }
    base.update(overrides)
    return base


class TestPnsCountryIso3s:
    def test_returns_assigned_pns_countries(self, app, db_session):
        from tests.factories import (
            create_test_assignment_entity_status,
            create_test_country,
            create_test_template,
        )

        clear_pns_country_iso3s_cache()
        template = create_test_template(db_session, name="PNS plan fixture")
        country = create_test_country(db_session, name="Norwayland", iso3="NRL")
        create_test_assignment_entity_status(
            db_session, country=country, template=template, period_name="2026",
        )
        db_session.commit()
        clear_pns_country_iso3s_cache()

        with patch(
            "plugins.upr.analysis.country_international._PNS_TEMPLATE_IDS",
            (template.id,),
        ):
            clear_pns_country_iso3s_cache()
            codes = pns_country_iso3s()
            assert "NRL" in codes
            assert country_is_pns("nrl") is True
            assert country_is_pns("ZZZ") is False
        clear_pns_country_iso3s_cache()


class TestBuildCountryInternational:
    def test_pns_payload_uses_overview_embed(self, app):
        with app.app_context():
            with patch(
                "plugins.upr.analysis.country_international.country_is_pns",
                return_value=True,
            ), patch(
                "plugins.upr.analysis.flow.build_support_flows",
                return_value=_flows(),
            ):
                payload = build_country_international("NOR")

        assert payload["is_pns"] is True
        assert payload["role"] == "pns"
        assert payload["has_support"] is True
        assert payload["summary"]["countries_supported"] == 1
        assert payload["summary"]["funding"] == 1_500_000
        assert payload["partners"][0]["iso3"] == "SYR"
        assert "pns=NOR" in payload["embeds"]["primary"]
        assert payload["embeds"]["primary"].startswith("/upr/support-overview")

    def test_host_payload_uses_flow_embed(self, app):
        with app.app_context():
            with patch(
                "plugins.upr.analysis.country_international.country_is_pns",
                return_value=False,
            ), patch(
                "plugins.upr.analysis.flow.build_support_flows",
                return_value=_flows(),
            ):
                payload = build_country_international("SYR")

        assert payload["is_pns"] is False
        assert payload["role"] == "host"
        assert payload["summary"]["supporting_partners"] == 1
        assert payload["partners"][0]["iso3"] == "NOR"
        assert "recipient=SYR" in payload["embeds"]["primary"]
        assert payload["embeds"]["primary"].startswith("/upr/support-flow")
