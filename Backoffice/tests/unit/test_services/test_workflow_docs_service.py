"""Tests for WorkflowDocsService.get_workflow_for_tour's language/fallback labeling.

See docs/handovers/2026-07-17-defer-page-load-requests.md MEDIUM #7: generated
static/CDN tour JSON was tagging English-fallback content (used whenever a
translation file's steps can't be parsed) with the *requested* language code
instead of the actual content language, so e.g. account-settings.fr.json would
claim `"language": "fr"` while every string inside was English.

These tests exercise the real service against the real docs/workflows/ markdown
files (same source used by `flask workflows generate-static`), not mocks, since
the bug is specifically about how real translation files parse.
"""
import pytest

from app.services.documentation.workflow_docs_service import WorkflowDocsService

pytestmark = [pytest.mark.unit]


@pytest.fixture()
def service():
    svc = WorkflowDocsService()
    svc.reload()
    return svc


class TestGetWorkflowForTourLanguageTagging:
    def test_english_is_never_a_fallback(self, service):
        tour = service.get_workflow_for_tour('account-settings', 'en')
        assert tour is not None
        assert tour['language'] == 'en'
        assert tour['is_fallback'] is False

    def test_translation_without_parseable_steps_reports_english_fallback(self, service):
        # account-settings.fr.md exists but its localized field labels aren't
        # extracted by the (English-only) step parser yet, so this must fall back
        # to English content — and, per the fix, say so honestly.
        tour = service.get_workflow_for_tour('account-settings', 'fr')
        assert tour is not None
        assert tour['language'] == 'en'
        assert tour['is_fallback'] is True

    def test_falls_back_consistently_across_all_supported_languages(self, service):
        for lang in sorted(WorkflowDocsService.SUPPORTED_LANGUAGES - {'en'}):
            tour = service.get_workflow_for_tour('account-settings', lang)
            assert tour is not None, f"expected a fallback tour for lang={lang}"
            assert tour['language'] == 'en', f"lang={lang} should report actual content language 'en'"
            assert tour['is_fallback'] is True, f"lang={lang} should be flagged as a fallback"

    def test_genuinely_translated_workflow_is_not_flagged_as_fallback(self, service):
        # add-user has real fr/es/ar translations with parseable steps.
        for lang in sorted(WorkflowDocsService.SUPPORTED_LANGUAGES):
            tour = service.get_workflow_for_tour('add-user', lang)
            assert tour is not None, f"expected a tour for lang={lang}"
            assert tour['language'] == lang
            assert tour['is_fallback'] is False

    def test_unknown_workflow_returns_none(self, service):
        assert service.get_workflow_for_tour('does-not-exist', 'en') is None
