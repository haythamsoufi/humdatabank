"""Country dashboards include that country's project reporting cycles."""

from types import SimpleNamespace

import pytest

from app import db
from app.models.enums import EntityType
from app.models.projects import Project
from app.routes.api.users import _project_dashboard_fields
from app.routes.main.helpers import dashboard_assignment_entity_filter
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
