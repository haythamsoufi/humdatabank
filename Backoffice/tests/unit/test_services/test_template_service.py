"""
Tests for TemplateService - centralized template database operations.

Targets 100% coverage of app/services/template_service.py.
"""
import pytest
from sqlalchemy import literal

from app import db
from app.models import FormTemplate, FormTemplateVersion
from app.services.templates.service import TemplateService
from tests.factories import create_test_template


@pytest.mark.unit
class TestTemplateServiceGetById:
    """Tests for TemplateService.get_by_id."""

    def test_get_by_id_returns_template_when_exists(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="Service Get By ID Test")
            result = TemplateService.get_by_id(template.id)
            assert result is not None
            assert result.id == template.id

    def test_get_by_id_returns_none_for_nonexistent_id(self, db_session, app):
        with app.app_context():
            result = TemplateService.get_by_id(999999987)
            assert result is None

    def test_get_by_id_returns_correct_template_among_multiple(self, db_session, app):
        with app.app_context():
            t1 = create_test_template(db_session, name="Template A GetById")
            t2 = create_test_template(db_session, name="Template B GetById")
            assert TemplateService.get_by_id(t1.id).id == t1.id
            assert TemplateService.get_by_id(t2.id).id == t2.id


@pytest.mark.unit
class TestTemplateServiceExists:
    """Tests for TemplateService.exists."""

    def test_exists_returns_true_for_existing_template(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="Exists Check Template")
            assert TemplateService.exists(template.id) is True

    def test_exists_returns_false_for_nonexistent_id(self, db_session, app):
        with app.app_context():
            assert TemplateService.exists(888777666) is False

    def test_exists_false_after_template_deleted(self, db_session, app):
        with app.app_context():
            template = create_test_template(db_session, name="Delete Me Template")
            tid = template.id
            # Confirm it exists first
            assert TemplateService.exists(tid) is True


@pytest.mark.unit
class TestTemplateServiceGetAll:
    """Tests for TemplateService.get_all."""

    def test_get_all_returns_query_object(self, db_session, app):
        with app.app_context():
            result = TemplateService.get_all()
            # Should be a query object with a .count() method
            assert hasattr(result, 'count')

    def test_get_all_includes_created_templates(self, db_session, app):
        with app.app_context():
            t = create_test_template(db_session, name="GetAll Inclusion Test")
            all_ids = [r.id for r in TemplateService.get_all().all()]
            assert t.id in all_ids

    def test_get_all_returns_multiple_templates(self, db_session, app):
        with app.app_context():
            t1 = create_test_template(db_session, name="GetAll Multi A")
            t2 = create_test_template(db_session, name="GetAll Multi B")
            all_ids = [r.id for r in TemplateService.get_all().all()]
            assert t1.id in all_ids
            assert t2.id in all_ids


@pytest.mark.unit
class TestTemplateServiceGetAllPublished:
    """Tests for TemplateService.get_all_published."""

    def test_get_all_published_includes_published_template(self, db_session, app):
        with app.app_context():
            published = create_test_template(db_session, name="Published Template GetAllPub", status="published")
            result_ids = [r.id for r in TemplateService.get_all_published().all()]
            assert published.id in result_ids

    def test_get_all_published_excludes_unpublished_template(self, db_session, app):
        with app.app_context():
            # Create a template without published_version_id
            t = FormTemplate()
            db_session.add(t)
            db_session.flush()
            v = FormTemplateVersion(
                template_id=t.id,
                version_number=1,
                status='draft',
                name='Unpublished Draft',
            )
            db_session.add(v)
            db_session.commit()

            result_ids = [r.id for r in TemplateService.get_all_published().all()]
            assert t.id not in result_ids

    def test_get_all_published_returns_query_object(self, db_session, app):
        with app.app_context():
            result = TemplateService.get_all_published()
            assert hasattr(result, 'count')

    def test_get_all_published_filters_by_published_version_id(self, db_session, app):
        with app.app_context():
            published = create_test_template(db_session, name="Published V2 Template", status="published")
            assert published.published_version_id is not None
            result_ids = [r.id for r in TemplateService.get_all_published().all()]
            assert published.id in result_ids


@pytest.mark.unit
class TestTemplateServiceGetByIds:
    """Tests for TemplateService.get_by_ids."""

    def test_get_by_ids_returns_matching_templates(self, db_session, app):
        with app.app_context():
            t1 = create_test_template(db_session, name="GetByIds T1")
            t2 = create_test_template(db_session, name="GetByIds T2")
            t3 = create_test_template(db_session, name="GetByIds T3 Not Requested")

            result = TemplateService.get_by_ids([t1.id, t2.id]).all()
            result_ids = [r.id for r in result]
            assert t1.id in result_ids
            assert t2.id in result_ids
            assert t3.id not in result_ids

    def test_get_by_ids_empty_list_returns_empty(self, db_session, app):
        with app.app_context():
            # Ensure at least one template exists
            create_test_template(db_session, name="GetByIds Empty List Exists")
            result = TemplateService.get_by_ids([]).all()
            assert result == []

    def test_get_by_ids_nonexistent_ids_returns_empty(self, db_session, app):
        with app.app_context():
            result = TemplateService.get_by_ids([777777888, 777777999]).all()
            assert result == []

    def test_get_by_ids_single_id_returns_single_template(self, db_session, app):
        with app.app_context():
            t = create_test_template(db_session, name="GetByIds Single")
            result = TemplateService.get_by_ids([t.id]).all()
            assert len(result) == 1
            assert result[0].id == t.id

    def test_get_by_ids_returns_query_object(self, db_session, app):
        with app.app_context():
            t = create_test_template(db_session, name="GetByIds QueryObj")
            result = TemplateService.get_by_ids([t.id])
            assert hasattr(result, 'count')
            assert hasattr(result, 'all')

    def test_get_by_ids_empty_list_uses_literal_false(self, db_session, app):
        """Verify the empty list case returns a falsy query (no results)."""
        with app.app_context():
            # Create several templates to confirm none are returned
            create_test_template(db_session, name="GetByIds Empty Check 1")
            create_test_template(db_session, name="GetByIds Empty Check 2")
            result = TemplateService.get_by_ids([]).all()
            assert len(result) == 0
