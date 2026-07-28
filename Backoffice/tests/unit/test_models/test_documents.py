"""
Unit tests for documents.py models to achieve 100% code coverage.

Covers: SubmittedDocument, ResourceSubcategory, Resource, ResourceTranslation
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import date

from app.models.documents import (
    SubmittedDocument,
    ResourceSubcategory,
    Resource,
    ResourceTranslation,
)
from app.models.enums import DocumentStatusValue
from tests.factories import (
    create_test_user,
    create_test_country,
    create_test_assignment_entity_status,
    create_test_public_submission,
)


@pytest.mark.unit
class TestSubmittedDocument:
    """Tests for SubmittedDocument model."""

    def _create_doc(self, db_session, user, **kwargs):
        defaults = {
            'filename': 'test.pdf',
            'uploaded_by_user_id': user.id,
        }
        defaults.update(kwargs)
        doc = SubmittedDocument(**defaults)
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)
        return doc

    def test_create_basic_document(self, db_session, app):
        """Test creating a basic submitted document."""
        with app.app_context():
            user = create_test_user(db_session)
            doc = self._create_doc(db_session, user)
            assert doc.id is not None
            assert doc.filename == 'test.pdf'
            assert doc.status == DocumentStatusValue.pending.value

    def test_document_country_from_aes(self, db_session, app):
        """Test document_country returns country from assignment_entity_status."""
        with app.app_context():
            user = create_test_user(db_session)
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            doc = self._create_doc(db_session, user, assignment_entity_status_id=aes.id)
            # Reload to get relationship
            db_session.refresh(doc)
            result = doc.document_country
            assert result is not None

    def test_document_country_from_public_submission(self, db_session, app):
        """Test document_country returns country from public_submission."""
        with app.app_context():
            user = create_test_user(db_session)
            country = create_test_country(db_session)
            submission, _, _ = create_test_public_submission(db_session, country=country)
            doc = self._create_doc(db_session, user, public_submission_id=submission.id)
            db_session.refresh(doc)
            result = doc.document_country
            assert result is not None

    def test_document_country_from_country_id(self, db_session, app):
        """Test document_country returns country from country_id."""
        with app.app_context():
            user = create_test_user(db_session)
            country = create_test_country(db_session)
            doc = self._create_doc(db_session, user, country_id=country.id)
            db_session.refresh(doc)
            result = doc.document_country
            assert result is not None
            assert result.id == country.id

    def test_document_country_from_linked_entity(self, db_session, app):
        """Test document_country with linked_entity_type calls EntityService."""
        with app.app_context():
            user = create_test_user(db_session)
            doc = self._create_doc(
                db_session, user,
                linked_entity_type='country',
                linked_entity_id=999
            )
            db_session.refresh(doc)
            with patch('app.services.organization.entity_service.EntityService.get_country_for_entity', return_value=None):
                result = doc.document_country
                assert result is None

    def test_document_country_none(self, db_session, app):
        """Test document_country returns None when no linkage."""
        with app.app_context():
            user = create_test_user(db_session)
            doc = self._create_doc(db_session, user)
            db_session.refresh(doc)
            result = doc.document_country
            assert result is None

    def test_standalone_linked_display_with_aes_id(self, db_session, app):
        """Test standalone_linked_display returns None when has assignment_entity_status_id."""
        with app.app_context():
            user = create_test_user(db_session)
            country = create_test_country(db_session)
            aes = create_test_assignment_entity_status(db_session, country=country)
            doc = self._create_doc(db_session, user, assignment_entity_status_id=aes.id)
            db_session.refresh(doc)
            assert doc.standalone_linked_display is None

    def test_standalone_linked_display_with_public_submission_id(self, db_session, app):
        """Test standalone_linked_display returns None when has public_submission_id."""
        with app.app_context():
            user = create_test_user(db_session)
            country = create_test_country(db_session)
            submission, _, _ = create_test_public_submission(db_session, country=country)
            doc = self._create_doc(db_session, user, public_submission_id=submission.id)
            db_session.refresh(doc)
            assert doc.standalone_linked_display is None

    def test_standalone_linked_display_with_linked_entity(self, db_session, app):
        """Test standalone_linked_display with linked_entity_type calls EntityService."""
        with app.app_context():
            user = create_test_user(db_session)
            doc = self._create_doc(
                db_session, user,
                linked_entity_type='country',
                linked_entity_id=999
            )
            db_session.refresh(doc)
            with patch('app.services.organization.entity_service.EntityService.get_entity_display_name', return_value='Test Entity'):
                result = doc.standalone_linked_display
                assert result == 'Test Entity'

    def test_standalone_linked_display_with_country(self, db_session, app):
        """Test standalone_linked_display with country_id returns country name."""
        with app.app_context():
            user = create_test_user(db_session)
            country = create_test_country(db_session)
            doc = self._create_doc(db_session, user, country_id=country.id)
            db_session.refresh(doc)
            result = doc.standalone_linked_display
            assert result == country.name

    def test_standalone_linked_display_no_link(self, db_session, app):
        """Test standalone_linked_display returns None with no linkage."""
        with app.app_context():
            user = create_test_user(db_session)
            doc = self._create_doc(db_session, user)
            db_session.refresh(doc)
            assert doc.standalone_linked_display is None

    def test_document_label_from_form_item(self, db_session, app):
        """Test document_label when form_item is present uses form_item.label."""
        with app.app_context():
            user = create_test_user(db_session)
            doc = self._create_doc(db_session, user)
            # Mock form_item
            mock_item = MagicMock()
            mock_item.label = 'My Field Label'
            doc.form_item = mock_item
            assert doc.document_label == 'My Field Label'

    def test_document_label_from_document_type(self, db_session, app):
        """Test document_label uses document_type when no form_item."""
        with app.app_context():
            user = create_test_user(db_session)
            doc = self._create_doc(db_session, user, document_type='Annual Report')
            db_session.refresh(doc)
            assert doc.document_label == 'Annual Report'

    def test_document_label_default(self, db_session, app):
        """Test document_label returns 'Document' when no form_item or type."""
        with app.app_context():
            user = create_test_user(db_session)
            doc = self._create_doc(db_session, user)
            db_session.refresh(doc)
            assert doc.document_label == 'Document'

    def test_repr_with_country(self, db_session, app):
        """Test __repr__ includes filename and country."""
        with app.app_context():
            user = create_test_user(db_session)
            country = create_test_country(db_session)
            doc = self._create_doc(db_session, user, country_id=country.id)
            db_session.refresh(doc)
            result = repr(doc)
            assert 'test.pdf' in result

    def test_repr_without_country(self, db_session, app):
        """Test __repr__ shows N/A when no country."""
        with app.app_context():
            user = create_test_user(db_session)
            doc = self._create_doc(db_session, user)
            db_session.refresh(doc)
            result = repr(doc)
            assert 'N/A' in result

    def test_document_with_optional_fields(self, db_session, app):
        """Test document with all optional fields."""
        with app.app_context():
            user = create_test_user(db_session)
            doc = self._create_doc(
                db_session, user,
                language='en',
                period='2024',
                is_public=True,
                source_url='https://example.com/doc.pdf',
                thumbnail_source_url='https://example.com/thumb.jpg',
                storage_path='/path/to/file.pdf',
                thumbnail_filename='thumb.jpg',
                thumbnail_relative_path='thumbnails/thumb.jpg',
                archived_versions=[{'version': 1, 'path': 'old/path.pdf'}],
                file_pending=True,
            )
            assert doc.language == 'en'
            assert doc.is_public is True
            assert doc.file_pending is True


@pytest.mark.unit
class TestResourceSubcategory:
    """Tests for ResourceSubcategory model."""

    def test_create_subcategory(self, db_session, app):
        """Test creating a resource subcategory."""
        with app.app_context():
            sub = ResourceSubcategory(name='Annual Reports', display_order=1)
            db_session.add(sub)
            db_session.commit()
            db_session.refresh(sub)
            assert sub.id is not None
            assert sub.name == 'Annual Reports'
            assert sub.display_order == 1

    def test_subcategory_default_display_order(self, db_session, app):
        """Test default display_order is 0."""
        with app.app_context():
            sub = ResourceSubcategory(name='Misc')
            db_session.add(sub)
            db_session.commit()
            db_session.refresh(sub)
            assert sub.display_order == 0

    def test_subcategory_repr(self, db_session, app):
        """Test __repr__ for subcategory."""
        with app.app_context():
            sub = ResourceSubcategory(name='Fact Sheets')
            db_session.add(sub)
            db_session.commit()
            assert "Fact Sheets" in repr(sub)

    def test_subcategory_timestamps(self, db_session, app):
        """Test created_at and updated_at are set."""
        with app.app_context():
            sub = ResourceSubcategory(name='Test Category')
            db_session.add(sub)
            db_session.commit()
            db_session.refresh(sub)
            assert sub.created_at is not None
            assert sub.updated_at is not None


@pytest.mark.unit
class TestResource:
    """Tests for Resource model."""

    def _create_resource(self, db_session, **kwargs):
        defaults = {
            'default_title': 'Test Resource',
            'resource_type': 'publication',
        }
        defaults.update(kwargs)
        r = Resource(**defaults)
        db_session.add(r)
        db_session.commit()
        db_session.refresh(r)
        return r

    def test_create_resource(self, db_session, app):
        """Test creating a resource."""
        with app.app_context():
            r = self._create_resource(db_session)
            assert r.id is not None
            assert r.default_title == 'Test Resource'
            assert r.resource_type == 'publication'

    def test_resource_repr(self, db_session, app):
        """Test __repr__ for resource."""
        with app.app_context():
            r = self._create_resource(db_session, default_title='My Resource')
            assert 'My Resource' in repr(r)

    def test_get_translation_none_code(self, db_session, app):
        """Test get_translation returns None when language_code is None."""
        with app.app_context():
            r = self._create_resource(db_session)
            result = r.get_translation(None)
            assert result is None

    def test_get_translation_empty_code(self, db_session, app):
        """Test get_translation returns None when language_code is empty."""
        with app.app_context():
            r = self._create_resource(db_session)
            result = r.get_translation('  ')
            assert result is None

    def test_get_translation_exact_match(self, db_session, app):
        """Test get_translation returns translation for exact language match."""
        with app.app_context():
            r = self._create_resource(db_session)
            trans = ResourceTranslation(
                resource_id=r.id,
                language_code='en',
                title='English Title',
            )
            db_session.add(trans)
            db_session.commit()
            result = r.get_translation('en')
            assert result is not None
            assert result.title == 'English Title'

    def test_get_translation_case_insensitive_fallback(self, db_session, app):
        """Test get_translation falls back to case-insensitive search."""
        with app.app_context():
            r = self._create_resource(db_session)
            trans = ResourceTranslation(
                resource_id=r.id,
                language_code='FR',
                title='French Title',
            )
            db_session.add(trans)
            db_session.commit()
            result = r.get_translation('fr')
            assert result is not None

    def test_get_translation_missing(self, db_session, app):
        """Test get_translation returns None when translation not found."""
        with app.app_context():
            r = self._create_resource(db_session)
            result = r.get_translation('de')
            assert result is None

    def test_get_title_with_translation(self, db_session, app):
        """Test get_title returns translated title when available."""
        with app.app_context():
            r = self._create_resource(db_session)
            trans = ResourceTranslation(
                resource_id=r.id,
                language_code='fr',
                title='Titre Français',
            )
            db_session.add(trans)
            db_session.commit()
            result = r.get_title('fr')
            assert result == 'Titre Français'

    def test_get_title_fallback(self, db_session, app):
        """Test get_title returns default_title when translation not found."""
        with app.app_context():
            r = self._create_resource(db_session, default_title='Default Title')
            result = r.get_title('de')
            assert result == 'Default Title'

    def test_get_description_with_translation(self, db_session, app):
        """Test get_description returns translated description."""
        with app.app_context():
            r = self._create_resource(db_session)
            trans = ResourceTranslation(
                resource_id=r.id,
                language_code='es',
                title='Título',
                description='Descripción',
            )
            db_session.add(trans)
            db_session.commit()
            result = r.get_description('es')
            assert result == 'Descripción'

    def test_get_description_fallback(self, db_session, app):
        """Test get_description returns default_description when translation not found."""
        with app.app_context():
            r = self._create_resource(db_session, default_description='Default Desc')
            result = r.get_description('de')
            assert result == 'Default Desc'

    def test_get_available_languages(self, db_session, app):
        """Test get_available_languages returns list of language codes."""
        with app.app_context():
            r = self._create_resource(db_session)
            for lang in ['en', 'fr', 'es']:
                trans = ResourceTranslation(
                    resource_id=r.id,
                    language_code=lang,
                    title=f'Title {lang}',
                )
                db_session.add(trans)
            db_session.commit()
            langs = r.get_available_languages()
            assert 'en' in langs
            assert 'fr' in langs
            assert 'es' in langs
            assert len(langs) == 3

    def test_resource_with_subcategory(self, db_session, app):
        """Test resource linked to a subcategory."""
        with app.app_context():
            sub = ResourceSubcategory(name='Reports', display_order=0)
            db_session.add(sub)
            db_session.commit()
            r = self._create_resource(db_session, resource_subcategory_id=sub.id)
            db_session.refresh(r)
            assert r.resource_subcategory_id == sub.id

    def test_resource_with_publication_date(self, db_session, app):
        """Test resource with a publication date."""
        with app.app_context():
            r = self._create_resource(db_session, publication_date=date(2024, 1, 1))
            assert r.publication_date == date(2024, 1, 1)


@pytest.mark.unit
class TestResourceTranslation:
    """Tests for ResourceTranslation model."""

    def _create_resource_and_translation(self, db_session, lang='en', **kwargs):
        r = Resource(default_title='Base Resource', resource_type='publication')
        db_session.add(r)
        db_session.flush()
        defaults = {
            'resource_id': r.id,
            'language_code': lang,
            'title': f'Title {lang}',
        }
        defaults.update(kwargs)
        trans = ResourceTranslation(**defaults)
        db_session.add(trans)
        db_session.commit()
        db_session.refresh(trans)
        return r, trans

    def test_create_translation(self, db_session, app):
        """Test creating a resource translation."""
        with app.app_context():
            r, trans = self._create_resource_and_translation(db_session)
            assert trans.id is not None
            assert trans.language_code == 'en'
            assert trans.title == 'Title en'

    def test_repr(self, db_session, app):
        """Test __repr__ for translation."""
        with app.app_context():
            r, trans = self._create_resource_and_translation(db_session, lang='fr', title='Mon Titre')
            result = repr(trans)
            assert 'Mon Titre' in result
            assert 'fr' in result

    def test_has_uploaded_document_with_filename(self, db_session, app):
        """Test has_uploaded_document returns True when filename is set."""
        with app.app_context():
            r, trans = self._create_resource_and_translation(
                db_session, filename='report.pdf'
            )
            assert trans.has_uploaded_document is True

    def test_has_uploaded_document_with_path(self, db_session, app):
        """Test has_uploaded_document returns True when file_relative_path is set."""
        with app.app_context():
            r, trans = self._create_resource_and_translation(
                db_session, file_relative_path='some/path/report.pdf'
            )
            assert trans.has_uploaded_document is True

    def test_has_uploaded_document_false(self, db_session, app):
        """Test has_uploaded_document returns False when neither is set."""
        with app.app_context():
            r, trans = self._create_resource_and_translation(db_session)
            assert trans.has_uploaded_document is False

    def test_has_uploaded_document_empty_string(self, db_session, app):
        """Test has_uploaded_document returns False for empty strings."""
        with app.app_context():
            r, trans = self._create_resource_and_translation(
                db_session, filename='  ', file_relative_path='  '
            )
            assert trans.has_uploaded_document is False

    def test_document_display_name_from_filename(self, db_session, app):
        """Test document_display_name prefers filename."""
        with app.app_context():
            r, trans = self._create_resource_and_translation(
                db_session,
                filename='annual_report.pdf',
                file_relative_path='folder/annual_report.pdf',
            )
            assert trans.document_display_name == 'annual_report.pdf'

    def test_document_display_name_from_path(self, db_session, app):
        """Test document_display_name extracts from path when no filename."""
        with app.app_context():
            r, trans = self._create_resource_and_translation(
                db_session, file_relative_path='folder/subdir/report.pdf'
            )
            assert trans.document_display_name == 'report.pdf'

    def test_document_display_name_none(self, db_session, app):
        """Test document_display_name returns None when no file info."""
        with app.app_context():
            r, trans = self._create_resource_and_translation(db_session)
            assert trans.document_display_name is None

    def test_document_display_name_windows_path(self, db_session, app):
        """Test document_display_name normalizes Windows backslashes."""
        with app.app_context():
            r, trans = self._create_resource_and_translation(
                db_session, file_relative_path='folder\\subdir\\report.pdf'
            )
            assert trans.document_display_name == 'report.pdf'

    def test_source_document_is_pdf_filename(self, db_session, app):
        """Test source_document_is_pdf True when filename ends with .pdf."""
        with app.app_context():
            r, trans = self._create_resource_and_translation(
                db_session, filename='report.pdf'
            )
            assert trans.source_document_is_pdf is True

    def test_source_document_is_pdf_path(self, db_session, app):
        """Test source_document_is_pdf True when path ends with .pdf."""
        with app.app_context():
            r, trans = self._create_resource_and_translation(
                db_session, file_relative_path='folder/report.PDF'
            )
            assert trans.source_document_is_pdf is True

    def test_source_document_is_pdf_false(self, db_session, app):
        """Test source_document_is_pdf False for non-PDF file."""
        with app.app_context():
            r, trans = self._create_resource_and_translation(
                db_session, filename='report.docx'
            )
            assert trans.source_document_is_pdf is False

    def test_source_document_is_pdf_no_file(self, db_session, app):
        """Test source_document_is_pdf False when no file info."""
        with app.app_context():
            r, trans = self._create_resource_and_translation(db_session)
            assert trans.source_document_is_pdf is False
