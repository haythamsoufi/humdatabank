"""Visual themes for public form links.

An admin picks a theme on the assignment (for example the orange "16 Days of
Activism" look). The public page then drops the back-office chrome and loads the
theme's stylesheet and banner. Assignments without a theme are unchanged.
"""
from __future__ import annotations

import uuid

import pytest

from app.models import AssignedForm, PublicSubmission
from app.models.enums import PublicSubmissionStatus
from app.services.public.form_themes import (
    BASE_STYLESHEET,
    PUBLIC_FORM_THEMES,
    get_public_form_theme,
    normalize_theme_key,
    public_form_theme_choices,
    public_form_theme_for_assignment,
)
from tests.factories import (
    create_test_assignment_entity_status,
    create_test_country,
    create_test_template,
)

pytestmark = [pytest.mark.unit]

THEME_KEY = "16_days_of_activism"
THEME_CSS = "css/public-form-themes/16-days-of-activism.css"


def _public_assignment(db_session, *, theme=None):
    template = create_test_template(db_session)
    assigned_form = AssignedForm(
        template_id=template.id,
        period_name=f"survey-{uuid.uuid4().hex[:8]}",
        unique_token=str(uuid.uuid4()),
        is_public_active=True,
        is_active=True,
        public_form_theme=theme,
    )
    db_session.add(assigned_form)
    db_session.commit()
    return assigned_form


class TestThemeRegistry:
    def test_16_days_theme_is_registered(self):
        theme = get_public_form_theme(THEME_KEY)
        assert theme is not None
        assert theme.stylesheet == THEME_CSS
        assert theme.hero_template

    def test_unknown_and_empty_keys_mean_no_theme(self):
        assert get_public_form_theme("does_not_exist") is None
        assert get_public_form_theme("") is None
        assert get_public_form_theme(None) is None
        assert normalize_theme_key("  does_not_exist ") == ""
        assert normalize_theme_key(f" {THEME_KEY} ") == THEME_KEY

    def test_choices_start_with_the_default_look(self):
        choices = public_form_theme_choices()
        assert choices[0][0] == ""
        assert [key for key, _label in choices[1:]] == list(PUBLIC_FORM_THEMES)

    def test_assignment_without_the_attribute_has_no_theme(self):
        assert public_form_theme_for_assignment(object()) is None

    def test_every_theme_ships_its_files(self, app):
        from pathlib import Path

        static_root = Path(app.root_path) / "static"
        for theme in PUBLIC_FORM_THEMES.values():
            assert theme.base_stylesheet == BASE_STYLESHEET
            for rel in (theme.stylesheet, theme.base_stylesheet):
                assert (static_root / rel).is_file(), rel
            if theme.hero_template:
                assert app.jinja_env.get_template(theme.hero_template)


class TestThemedPublicForm:
    def test_default_look_has_no_theme_assets(self, client, db_session):
        assigned_form = _public_assignment(db_session)

        body = client.get(f"/forms/public/{assigned_form.unique_token}").get_data(as_text=True)

        assert "public-form-themed" not in body
        assert "public-form-themes/" not in body
        assert "theme-hero" not in body

    def test_theme_adds_stylesheets_banner_and_body_class(self, client, db_session):
        assigned_form = _public_assignment(db_session, theme=THEME_KEY)

        resp = client.get(f"/forms/public/{assigned_form.unique_token}")

        body = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "public-form-themed public-form-theme-16-days-of-activism" in body
        assert "public-form-themes/base.css" in body
        assert THEME_CSS in body
        assert 'class="theme-hero"' in body
        assert "16 Days of Activism against Gender-based Violence" in body
        assert assigned_form.display_name in body

    def test_theme_banner_offers_language_links(self, client, db_session):
        assigned_form = _public_assignment(db_session, theme=THEME_KEY)

        body = client.get(f"/forms/public/{assigned_form.unique_token}").get_data(as_text=True)

        assert 'class="theme-lang"' in body
        assert 'class="theme-lang__link' in body
        assert "/language/en" in body

    def test_unknown_stored_theme_falls_back_to_default_look(self, client, db_session):
        assigned_form = _public_assignment(db_session, theme="removed_theme")

        resp = client.get(f"/forms/public/{assigned_form.unique_token}")

        assert resp.status_code == 200
        assert "public-form-themed" not in resp.get_data(as_text=True)

    def test_unavailable_page_uses_the_theme(self, client, db_session):
        assigned_form = _public_assignment(db_session, theme=THEME_KEY)
        assigned_form.is_public_active = False
        db_session.commit()

        body = client.get(f"/forms/public/{assigned_form.unique_token}").get_data(as_text=True)

        assert "currently not active" in body
        assert THEME_CSS in body
        assert "public-form-theme-16-days-of-activism" in body

    def test_unavailable_page_without_theme_is_unchanged(self, client, db_session):
        assigned_form = _public_assignment(db_session)
        assigned_form.is_public_active = False
        db_session.commit()

        body = client.get(f"/forms/public/{assigned_form.unique_token}").get_data(as_text=True)

        assert "currently not active" in body
        assert "public-form-themes/" not in body

    def test_success_page_uses_the_theme(self, client, db_session):
        from app.services.public.submission_receipt import public_submission_success_token

        assigned_form = _public_assignment(db_session, theme=THEME_KEY)
        submission = PublicSubmission(
            assigned_form_id=assigned_form.id,
            status=PublicSubmissionStatus.pending,
        )
        db_session.add(submission)
        db_session.commit()

        resp = client.get(
            f"/forms/public-submission/success/{public_submission_success_token(submission.id)}"
        )

        body = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert THEME_CSS in body
        assert 'class="theme-hero"' in body
        assert "Submission Successful!" in body

    def test_success_page_without_theme_keeps_the_admin_header(self, client, db_session):
        from app.services.public.submission_receipt import public_submission_success_token

        assigned_form = _public_assignment(db_session)
        submission = PublicSubmission(
            assigned_form_id=assigned_form.id,
            status=PublicSubmissionStatus.pending,
        )
        db_session.add(submission)
        db_session.commit()

        body = client.get(
            f"/forms/public-submission/success/{public_submission_success_token(submission.id)}"
        ).get_data(as_text=True)

        assert "theme-hero" not in body
        assert "public-form-themes/" not in body


class TestAdminPicksTheme:
    def _assignment(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(
                db_session, country=country, template=template
            )
            return aes.assigned_form_id, template.id

    def _post(self, client, assignment_id, template_id, **extra):
        return client.post(
            f"/admin/assignments/edit/{assignment_id}",
            data={
                "template_id": str(template_id),
                "period_name": "2024",
                "submit": "1",
                **extra,
            },
            follow_redirects=False,
        )

    def test_edit_page_lists_the_themes(self, logged_in_client, db_session, app):
        assignment_id, _template_id = self._assignment(db_session, app)

        html = logged_in_client.get(f"/admin/assignments/edit/{assignment_id}").get_data(as_text=True)

        assert 'id="public_form_theme"' in html
        assert f'value="{THEME_KEY}"' in html

    def test_post_saves_the_theme(self, logged_in_client, db_session, app):
        assignment_id, template_id = self._assignment(db_session, app)

        resp = self._post(logged_in_client, assignment_id, template_id, public_form_theme=THEME_KEY)

        assert resp.status_code in (200, 302)
        with app.app_context():
            db_session.expire_all()
            assert db_session.get(AssignedForm, assignment_id).public_form_theme == THEME_KEY

    def test_post_with_default_clears_the_theme(self, logged_in_client, db_session, app):
        assignment_id, template_id = self._assignment(db_session, app)
        with app.app_context():
            db_session.get(AssignedForm, assignment_id).public_form_theme = THEME_KEY
            db_session.commit()

        self._post(logged_in_client, assignment_id, template_id, public_form_theme="")

        with app.app_context():
            db_session.expire_all()
            assert db_session.get(AssignedForm, assignment_id).public_form_theme is None

    def test_post_without_the_field_keeps_the_theme(self, logged_in_client, db_session, app):
        assignment_id, template_id = self._assignment(db_session, app)
        with app.app_context():
            db_session.get(AssignedForm, assignment_id).public_form_theme = THEME_KEY
            db_session.commit()

        self._post(logged_in_client, assignment_id, template_id)

        with app.app_context():
            db_session.expire_all()
            assert db_session.get(AssignedForm, assignment_id).public_form_theme == THEME_KEY

    def test_post_rejects_an_unknown_theme(self, logged_in_client, db_session, app):
        assignment_id, template_id = self._assignment(db_session, app)

        self._post(logged_in_client, assignment_id, template_id, public_form_theme="nope")

        with app.app_context():
            db_session.expire_all()
            assert db_session.get(AssignedForm, assignment_id).public_form_theme is None
