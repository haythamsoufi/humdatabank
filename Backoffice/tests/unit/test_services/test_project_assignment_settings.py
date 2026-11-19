"""Project settings are copied onto reports, and only a new report inherits them."""

from unittest.mock import patch

import pytest

from app.models.forms import FormTemplateVersion
from app.models.projects import Project, ProjectAssignment
from app.services.assignments.access_service import campaign_only
from app.services.projects.assignment_settings import (
    apply_to_reports,
    get_or_create_project_assignment,
    settings_drift,
)
from app.services.projects.service import ensure_project_cycle_assignment
from tests.factories import create_test_country, create_test_template

pytestmark = pytest.mark.unit


def _project(db_session, country, reference="P-SET"):
    project = Project(
        reference=reference,
        title="Settings project",
        country_id=country.id,
        status="Open",
        portfolio="Test",
    )
    db_session.add(project)
    db_session.commit()
    return project


def _version(db_session, template):
    return db_session.query(FormTemplateVersion).filter_by(id=template.published_version_id).one()


class TestProjectAssignmentSettings:
    def test_new_report_without_settings_takes_template_export_flags(self, db_session, app):
        country = create_test_country(db_session)
        template = create_test_template(db_session)
        version = _version(db_session, template)
        version.enable_export_pdf = True
        version.enable_export_excel = True
        db_session.commit()
        project = _project(db_session, country, "P-SEED")

        assignment, _aes = ensure_project_cycle_assignment(project, template.id, "Y1Q1")
        db_session.commit()

        assert assignment.enable_export_pdf is True
        assert assignment.enable_export_excel is True
        assert ProjectAssignment.query.filter_by(project_id=project.id).first() is None

    def test_new_report_inherits_existing_settings_and_reimport_does_not_overwrite(self, db_session, app):
        country = create_test_country(db_session)
        template = create_test_template(db_session)
        version = _version(db_session, template)
        version.enable_export_pdf = True
        db_session.commit()
        project = _project(db_session, country, "P-KEEP")
        settings = ProjectAssignment(project_id=project.id, enable_export_pdf=False, enable_export_excel=True)
        db_session.add(settings)
        db_session.commit()

        assignment, _aes = ensure_project_cycle_assignment(project, template.id, "Y1Q1")
        db_session.commit()
        assert assignment.enable_export_pdf is False
        assert assignment.enable_export_excel is True

        assignment.enable_export_excel = False
        db_session.commit()
        again, _aes = ensure_project_cycle_assignment(project, template.id, "Y1Q1")
        db_session.commit()
        assert again.id == assignment.id
        assert again.enable_export_excel is False

    def test_apply_copies_flags_and_reports_drift(self, db_session, app):
        country = create_test_country(db_session)
        template = create_test_template(db_session)
        project = _project(db_session, country, "P-APPLY")
        first, _aes = ensure_project_cycle_assignment(project, template.id, "Y1Q1")
        second, _aes = ensure_project_cycle_assignment(project, template.id, "Final")
        db_session.commit()
        settings = get_or_create_project_assignment(project)
        settings.enable_export_pdf = True
        db_session.commit()

        drifted = settings_drift(project)
        assert {row.id for row in drifted} == {first.id, second.id}

        changed = apply_to_reports(project)
        db_session.commit()
        assert changed == 2
        assert first.enable_export_pdf is True
        assert second.enable_export_pdf is True
        assert settings_drift(project) == []

    def test_page_submission_flip_is_applied_per_report(self, db_session, app):
        country = create_test_country(db_session)
        template = create_test_template(db_session)
        project = _project(db_session, country, "P-PAGE")
        ensure_project_cycle_assignment(project, template.id, "Y1Q1")
        db_session.commit()
        settings = get_or_create_project_assignment(project)
        settings.enable_page_submission = True
        db_session.commit()

        with patch(
            "app.services.assignments.page_submission_service.apply_page_submission_mode_change"
        ) as mode_change:
            changed = apply_to_reports(project, user_id=1)
        assert changed == 1
        mode_change.assert_called_once()
        assert mode_change.call_args.args[1] is True

    def test_campaign_only_still_excludes_project_reports(self, db_session, app):
        from app.models.assignments import AssignedForm

        country = create_test_country(db_session)
        template = create_test_template(db_session)
        project = _project(db_session, country, "P-HIDE")
        cycle, _aes = ensure_project_cycle_assignment(project, template.id, "Y1Q1")
        campaign = AssignedForm(template_id=template.id, period_name="Annual 2026", scope="campaign")
        db_session.add(campaign)
        db_session.commit()

        ids = {row.id for row in campaign_only(AssignedForm.query).all()}
        assert campaign.id in ids
        assert cycle.id not in ids
