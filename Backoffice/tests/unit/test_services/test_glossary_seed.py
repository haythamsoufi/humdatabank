"""Tests for must-tier glossary seeding from Indicator Bank / Common Words."""

from app.services.translation.glossary_seed import _upsert_term


def test_upsert_term_rejects_untranslated_target_case_insensitive(db_session):
    """Regression test: source == target (case-insensitively) must not be seeded."""
    from app.models.translation_quality import TranslationGlossaryTerm

    assert _upsert_term("Focal Point", "focal point", "fr", "indicator_bank") is False
    assert _upsert_term("Focal Point", "FOCAL POINT", "fr", "indicator_bank") is False
    assert TranslationGlossaryTerm.query.filter_by(target_lang="fr").count() == 0


def test_upsert_term_rejects_english_target_lang():
    assert _upsert_term("Focal Point", "Point focal", "en", "indicator_bank") is False


def test_upsert_term_rejects_blank_source_or_target():
    assert _upsert_term("", "Point focal", "fr", "indicator_bank") is False
    assert _upsert_term("Focal Point", "", "fr", "indicator_bank") is False
    assert _upsert_term("  ", "  ", "fr", "indicator_bank") is False


def test_upsert_term_creates_once_and_skips_on_repeat(db_session):
    from app.models.translation_quality import TranslationGlossaryTerm

    assert _upsert_term("Focal Point", "Point focal", "fr", "indicator_bank") is True
    db_session.commit()
    # Same (source, source_lang, target_lang) already exists -- skip, do not overwrite.
    assert _upsert_term("Focal Point", "Point focal modifie", "fr", "indicator_bank") is False

    row = TranslationGlossaryTerm.query.filter_by(source_term="Focal Point", target_lang="fr").one()
    assert row.target_term == "Point focal"
    assert row.origin == "indicator_bank"
    assert row.tier == "must"
