"""Project rows live on the Assignments list; old project URLs redirect there."""

import pytest
from flask import url_for

from app.models.projects import Project
from app.models.rbac import RbacPermission, RbacRole, RbacRolePermission, RbacUserRole
from app.services.projects.service import ensure_project_cycle_assignment
from tests.factories import create_test_country, create_test_template, create_test_user
from tests.helpers import login_session

pytestmark = pytest.mark.unit


def _project(db_session, country, reference, manager_email, portfolio="Test"):
    project = Project(
        reference=reference,
        title=reference,
        country_id=country.id,
        status="Open",
        portfolio=portfolio,
        manager_email=manager_email,
    )
    db_session.add(project)
    db_session.commit()
    return project


def _grant(db_session, user, code):
    perm = db_session.query(RbacPermission).filter_by(code=code).first()
    if perm is None:
        perm = RbacPermission(code=code, name=code, description=code)
        db_session.add(perm)
        db_session.flush()
    role = RbacRole(code=f"role-{code}-{user.id}", name=code, kind="permission")
    db_session.add(role)
    db_session.flush()
    db_session.add(RbacRolePermission(role_id=role.id, permission_id=perm.id))
    db_session.add(RbacUserRole(user_id=user.id, role_id=role.id))
    db_session.commit()


class TestProjectAssignmentRoutes:
    def test_old_project_urls_redirect(self, logged_in_client, db_session, app):
        country = create_test_country(db_session)
        project = _project(db_session, country, "P-REDIR", "pm@example.com")
        with app.app_context():
            list_url = url_for("project_management.project_list")
            detail_url = url_for("project_management.project_detail", project_id=project.id)
        listing = logged_in_client.get(list_url)
        assert listing.status_code == 302
        assert "type=project" in listing.headers["Location"]
        detail = logged_in_client.get(detail_url, follow_redirects=True)
        assert detail.status_code == 200
        page = detail.get_data(as_text=True)
        assert "Reports" in page
        assert "Enable Export PDF button" in page
        assert f"/admin/assignments/projects/{project.id}" in page

    def test_editing_a_report_goes_to_the_project(self, logged_in_client, db_session, app):
        country = create_test_country(db_session)
        template = create_test_template(db_session)
        project = _project(db_session, country, "P-GUARD", "pm@example.com")
        assignment, _aes = ensure_project_cycle_assignment(project, template.id, "Y1Q1")
        db_session.commit()
        with app.app_context():
            edit_url = url_for("assignment_management.edit_assignment", assignment_id=assignment.id)
        response = logged_in_client.get(edit_url)
        assert response.status_code == 302
        assert f"/admin/assignments/projects/{project.id}" in response.headers["Location"]

    def test_assignments_list_contains_the_project_not_each_report(self, logged_in_client, db_session, app):
        country = create_test_country(db_session)
        template = create_test_template(db_session)
        project = _project(db_session, country, "P-LIST", "pm@example.com")
        assignment, _aes = ensure_project_cycle_assignment(project, template.id, "Y1Q1")
        db_session.commit()
        response = logged_in_client.get("/admin/assignments")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Test" in body
        assert "country projects" in body
        assert assignment.period_name not in body
        assert "P-LIST" not in body
        assert 'data-tab="monitoring"' not in body
        assert "pmRoot" not in body

    def test_pm_viewer_sees_only_their_projects(self, client, db_session, app):
        country = create_test_country(db_session)
        own = _project(db_session, country, "P-OWN", "pm.only@example.com")
        _project(db_session, country, "P-OTHER", "someone.else@example.com")
        user = create_test_user(db_session, email="pm.only@example.com", role="user")
        _grant(db_session, user, "nsd_funds.pm_overview")
        login_session(client, user.id)
        response = client.get("/admin/assignments/projects/portfolio/Test")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert own.reference in body
        assert "P-OTHER" not in body

    def test_portfolio_page_has_monitoring_for_that_programme(self, logged_in_client, db_session, app):
        country = create_test_country(db_session)
        _project(db_session, country, "P-NSD", "pm@example.com", portfolio="NSD")
        _project(db_session, country, "P-OTHER-PROG", "pm@example.com", portfolio="CBF")
        response = logged_in_client.get("/admin/assignments/projects/portfolio/NSD")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'data-tab="monitoring"' in body
        assert 'id="pmFilter-portfolio" value="NSD"' in body
        assert "P-NSD" in body
        assert "P-OTHER-PROG" not in body

    def test_monitoring_data_stays_inside_the_programme(self, logged_in_client, db_session, app):
        country = create_test_country(db_session)
        _project(db_session, country, "P-NSD", "pm@example.com", portfolio="NSD")
        _project(db_session, country, "P-OTHER-PROG", "pm@example.com", portfolio="CBF")
        _project(db_session, country, "P-UNSORTED", "pm@example.com", portfolio=None)
        named = logged_in_client.get("/admin/assignments/projects/monitoring/data?portfolio=NSD&status=open")
        assert named.status_code == 200
        named_body = named.get_json()
        assert named_body["kpis"]["projects_total"] == 1
        refs = [row["reference"] for row in named_body["lists"]["data_quality"]]
        assert refs == ["P-NSD"]
        other = logged_in_client.get("/admin/assignments/projects/monitoring/data?portfolio=_&status=open")
        assert other.status_code == 200
        other_refs = [row["reference"] for row in other.get_json()["lists"]["data_quality"]]
        assert other_refs == ["P-UNSORTED"]

    def test_anonymous_project_page_asks_for_login(self, client, db_session, app):
        country = create_test_country(db_session)
        project = _project(db_session, country, "P-ANON", "pm@example.com")
        response = client.get(f"/admin/assignments/projects/{project.id}")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
