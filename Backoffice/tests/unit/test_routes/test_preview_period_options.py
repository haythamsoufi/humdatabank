"""Template preview assignment periods follow the selected view-as entity."""

import pytest

from app.models.assignments import AssignedForm, AssignmentEntityStatus
from app.models.enums import AssignmentEntityStatusValue, AssignmentScope, EntityType
from app.models.projects import Project
from app.routes.forms.entry import _preview_period_name_options
from tests.factories import create_test_country, create_test_template

pytestmark = pytest.mark.unit


def _project_cycle(db_session, template, project, period_name):
    assignment = AssignedForm(
        template_id=template.id,
        period_name=period_name,
        scope=AssignmentScope.project_cycle.value,
        project_id=project.id,
    )
    db_session.add(assignment)
    db_session.flush()
    db_session.add(
        AssignmentEntityStatus(
            assigned_form_id=assignment.id,
            entity_type=EntityType.project.value,
            entity_id=project.id,
            status=AssignmentEntityStatusValue.pending,
        )
    )
    db_session.flush()
    return assignment


class TestPreviewPeriodNameOptions:
    def test_country_view_lists_only_that_countrys_project_assignments(self, db_session, app):
        with app.app_context():
            home = create_test_country(db_session, name="Home Country")
            other = create_test_country(db_session, name="Other Country")
            template = create_test_template(db_session)
            home_project = Project(
                reference=f"P-HOME-{home.id}",
                title="Home project",
                country_id=home.id,
                status="Open",
            )
            other_project = Project(
                reference=f"P-AWAY-{other.id}",
                title="Other project",
                country_id=other.id,
                status="Open",
            )
            db_session.add_all([home_project, other_project])
            db_session.flush()
            _project_cycle(db_session, template, home_project, "HOME · Y1Q1")
            _project_cycle(db_session, template, other_project, "AWAY · Y1Q1")
            country_assignment = AssignedForm(
                template_id=template.id,
                period_name="Annual 2024",
            )
            db_session.add(country_assignment)
            db_session.flush()
            db_session.add(
                AssignmentEntityStatus(
                    assigned_form_id=country_assignment.id,
                    entity_type=EntityType.country.value,
                    entity_id=home.id,
                    status=AssignmentEntityStatusValue.pending,
                )
            )
            db_session.commit()

            periods = _preview_period_name_options(
                template.id, EntityType.country.value, home.id
            )

            assert periods == ["Annual 2024", "HOME · Y1Q1"]

    def test_project_view_lists_only_that_project(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            first = Project(
                reference=f"P-A-{country.id}",
                title="First",
                country_id=country.id,
                status="Open",
            )
            second = Project(
                reference=f"P-B-{country.id}",
                title="Second",
                country_id=country.id,
                status="Open",
            )
            db_session.add_all([first, second])
            db_session.flush()
            _project_cycle(db_session, template, first, "FIRST · Y1Q1")
            _project_cycle(db_session, template, second, "SECOND · Y1Q2")
            db_session.commit()

            periods = _preview_period_name_options(
                template.id, EntityType.project.value, first.id
            )

            assert periods == ["FIRST · Y1Q1"]

    def test_no_entity_lists_every_period_on_the_template(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            project = Project(
                reference=f"P-ALL-{country.id}",
                title="All",
                country_id=country.id,
                status="Open",
            )
            db_session.add(project)
            db_session.flush()
            _project_cycle(db_session, template, project, "ALL · Y1Q1")
            db_session.commit()

            periods = _preview_period_name_options(template.id)

            assert periods == ["ALL · Y1Q1"]

    def test_project_cycles_are_listed_in_slot_order(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            project = Project(
                reference=f"GA-BGD-{country.id}",
                title="Bangladesh",
                country_id=country.id,
                status="Open",
            )
            db_session.add(project)
            db_session.flush()
            for slot in ("Y1Q3", "Final", "Y1Q1", "Y1Q2"):
                _project_cycle(db_session, template, project, f"GA-BGD · {slot}")
            db_session.commit()

            periods = _preview_period_name_options(
                template.id, EntityType.country.value, country.id
            )

            assert periods == [
                "GA-BGD · Y1Q1",
                "GA-BGD · Y1Q2",
                "GA-BGD · Y1Q3",
                "GA-BGD · Final",
            ]
