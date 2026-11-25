"""Country dashboards include that country's project reporting cycles."""

from types import SimpleNamespace

import pytest

from app import db
from app.models.enums import EntityType
from app.models.projects import Project
from app.routes.api.users import _project_dashboard_fields
from app.routes.main.helpers import (
    dashboard_assignment_entity_filter,
    dashboard_cycle_label,
    dashboard_project_card_heading,
)
from tests.factories import create_test_country

pytestmark = pytest.mark.unit


def _sql(clause) -> str:
    return str(clause.compile(db.engine, compile_kwargs={"literal_binds": True}))


class TestDashboardAssignmentEntityFilter:
    def test_country_filter_includes_only_that_countrys_projects(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            other = create_test_country(db_session)
            db_session.commit()
            home = Project(
                reference=f"P-HOME-{country.id}",
                title="Home project",
                country_id=country.id,
                status="Open",
            )
            away = Project(
                reference=f"P-AWAY-{other.id}",
                title="Other project",
                country_id=other.id,
                status="Closed",
            )
            db_session.add_all([home, away])
            db_session.commit()

            sql = _sql(
                dashboard_assignment_entity_filter(EntityType.country.value, country.id)
            )
            assert f"IN ({home.id})" in sql or f"IN ({home.id}," in sql or f", {home.id})" in sql
            assert str(away.id) not in sql
            assert "project" in sql

    def test_non_country_filter_does_not_expand(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            db_session.commit()
            project = Project(
                reference=f"P-ONLY-{country.id}",
                title="Only",
                country_id=country.id,
                status="Open",
            )
            db_session.add(project)
            db_session.commit()

            sql = _sql(
                dashboard_assignment_entity_filter(EntityType.project.value, project.id)
            ).lower()
            assert " or " not in sql
            assert "project" in sql


class TestProjectDashboardFields:
    def test_closed_project_is_flagged_and_other_entities_are_empty(self, app):
        with app.app_context():
            project = Project(
                reference="NSD-1",
                title="Water",
                status="Closed",
                country_id=1,
            )
            project.id = 9
            fields = _project_dashboard_fields(
                {9: project},
                SimpleNamespace(entity_type="project", entity_id=9),
            )
            assert fields["project_reference"] == "NSD-1"
            assert fields["project_title"] == "Water"
            assert fields["project_closed"] is True
            assert _project_dashboard_fields({}, SimpleNamespace(entity_type="country", entity_id=1)) == {}


class TestDashboardProjectCardHeading:
    def test_dref_card_puts_fund_code_and_name_in_the_title(self):
        title, subtitle = dashboard_project_card_heading(
            "Emergency Operations", "DREF", "MDRZZ001", "Zedland Flood"
        )
        assert title == "DREF MDRZZ001 — Zedland Flood"
        assert subtitle == ""

    def test_imminent_dref_uses_its_fund_label(self):
        title, subtitle = dashboard_project_card_heading(
            "Emergency Operations", "i-DREF", "MDRIM009", "Imminent flood"
        )
        assert title == "i-DREF MDRIM009 — Imminent flood"
        assert subtitle == ""

    def test_dref_without_a_distinct_name_has_no_subtitle(self):
        title, subtitle = dashboard_project_card_heading("DREF", "", "MDRZZ001", "MDRZZ001")
        assert title == "DREF MDRZZ001"
        assert subtitle == ""

    def test_nsd_card_title_is_the_project_name_without_a_code_subtitle(self):
        title, subtitle = dashboard_project_card_heading(
            "NSD", "CBF", "CBF-AF-2412-258", "Bridging the digital divide"
        )
        assert title == "Bridging the digital divide"
        assert subtitle == ""

    def test_nsd_without_a_name_uses_the_reference_as_the_title(self):
        title, subtitle = dashboard_project_card_heading("NSD", "CBF", "CBF-AF-2412-258", "")
        assert title == "CBF-AF-2412-258"
        assert subtitle == ""

    def test_project_cards_omit_the_code_subtitle(self):
        title, subtitle = dashboard_project_card_heading("Global Award", "CBF", "GA-1", "Water")
        assert title == "Water"
        assert subtitle == ""

    def test_a_project_without_a_name_uses_the_reference_as_the_title(self):
        title, subtitle = dashboard_project_card_heading("Global Award", "", "GA-1", "")
        assert title == "GA-1"
        assert subtitle == ""


class TestDashboardCycleLabel:
    def test_dref_cycle_drops_the_appeal_code(self):
        assert dashboard_cycle_label("MDRZZ001 · 2026-01", "MDRZZ001") == "2026-01"

    def test_dref_day_slot_keeps_the_date(self):
        assert dashboard_cycle_label("MDRIM009 · 2026-01-15", "MDRIM009") == "2026-01-15"

    def test_project_cycle_drops_the_code(self):
        assert dashboard_cycle_label("CBF-AF-2412-258 · Y2Q3", "CBF-AF-2412-258") == "Y2Q3"
        assert dashboard_cycle_label("GA-1 · Y1Q2", "GA-1") == "Y1Q2"
        assert dashboard_cycle_label("CBF-AF-2412-258 · Final", "CBF-AF-2412-258") == "Final"

    def test_a_period_without_the_code_prefix_is_unchanged(self):
        assert dashboard_cycle_label("2026 Annual", "GA-1") == "2026 Annual"
