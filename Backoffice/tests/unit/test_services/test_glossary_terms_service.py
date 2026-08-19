"""Tests for the glossary_terms service's candidate inbox listing.

``list_glossary_candidates`` is the single shared implementation used by both
the admin quality dashboard and the inline translation-review tool's API --
see routes/admin/utilities/translations.py and routes/translation_review.
"""

import pytest


@pytest.mark.unit
class TestListGlossaryCandidatesTargetLangFilter:
    def test_target_lang_filters_candidates(self, db_session):
        from app.models.translation_quality import TranslationGlossaryCandidate
        from app.services.translation.glossary_terms import list_glossary_candidates

        db_session.add_all([
            TranslationGlossaryCandidate(
                source_term="Appeal", target_term="appel", source_lang="en", target_lang="fr",
                extractor="test", confidence=0.8, proposed_tier="preferred", status="pending",
            ),
            TranslationGlossaryCandidate(
                source_term="Appeal", target_term="llamamiento", source_lang="en", target_lang="es",
                extractor="test", confidence=0.9, proposed_tier="preferred", status="pending",
            ),
        ])
        db_session.commit()

        fr_only = list_glossary_candidates(target_lang="fr")
        assert fr_only["total"] == 1
        assert all(item["target_lang"] == "fr" for item in fr_only["items"])

        unfiltered = list_glossary_candidates()
        assert unfiltered["total"] == 2

    def test_target_lang_en_is_treated_as_no_filter(self, db_session):
        """'en' is the source language, not a valid candidate target -- it must
        not be treated as a real filter that hides every candidate."""
        from app.models.translation_quality import TranslationGlossaryCandidate
        from app.services.translation.glossary_terms import list_glossary_candidates

        db_session.add(TranslationGlossaryCandidate(
            source_term="Appeal", target_term="appel", source_lang="en", target_lang="fr",
            extractor="test", confidence=0.8, proposed_tier="preferred", status="pending",
        ))
        db_session.commit()

        result = list_glossary_candidates(target_lang="en")
        assert result["total"] == 1


@pytest.mark.unit
class TestListGlossaryCandidatesConflictSort:
    def test_conflicting_low_confidence_candidate_still_ranks_first(self, db_session):
        """Regression guard: the conflict-first re-sort must see every pending row,
        not just the top-N by confidence -- otherwise a low-confidence conflict
        could be cut off by an early SQL-level LIMIT before Python ever sees it."""
        from app.models.translation_quality import TranslationGlossaryCandidate
        from app.services.translation.glossary_terms import list_glossary_candidates

        db_session.add(TranslationGlossaryCandidate(
            source_term="Conflict term", target_term="terme en conflit", source_lang="en", target_lang="fr",
            extractor="test", confidence=0.1, proposed_tier="preferred", status="pending",
            evidence={"conflict": True, "official_term": "terme officiel"},
        ))
        for i in range(5):
            db_session.add(TranslationGlossaryCandidate(
                source_term=f"Noise {i}", target_term=f"bruit {i}", source_lang="en", target_lang="fr",
                extractor="test", confidence=0.9, proposed_tier="preferred", status="pending",
            ))
        db_session.commit()

        result = list_glossary_candidates(target_lang="fr", limit=3)
        assert len(result["items"]) == 3
        assert result["items"][0]["source_term"] == "Conflict term"
        assert result["items"][0]["conflict"] is True
        assert result["conflicts"] == 1


@pytest.mark.unit
class TestSerializeCandidate:
    def test_includes_evidence_and_example_sentences(self, db_session):
        from app.models.translation_quality import TranslationGlossaryCandidate
        from app.services.translation.glossary_terms import serialize_candidate

        row = TranslationGlossaryCandidate(
            source_term="Appeal", target_term="appel", source_lang="en", target_lang="fr",
            extractor="test", confidence=0.8, proposed_tier="preferred", status="pending",
            evidence={"conflict": False}, example_sentences=["The appeal was launched."],
        )
        db_session.add(row)
        db_session.commit()

        serialized = serialize_candidate(row)
        assert serialized["evidence"] == {"conflict": False}
        assert serialized["example_sentences"] == ["The appeal was launched."]
