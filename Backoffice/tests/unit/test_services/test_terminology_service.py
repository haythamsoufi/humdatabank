"""Tests for app.services.ai.terminology_service.

Regression coverage for a module-level ``logger`` that was referenced but never
defined in this file's previous home (app/services/translation/terminology_service.py).
``get_focus_area_semantic_doc_hits`` is the only function that logs via the bare
module logger -- every call that reached its cosine-similarity phase raised a
``NameError`` internally, which the sole caller (_focus_area_analysis.match_focus_areas)
swallowed via a broad ``except Exception``, silently disabling semantic focus-area
detection and falling back to lexical-only matching. See docs/DEVELOPER-HANDBOOK.md.
"""

import pytest


def _unit_embedding(dimensions: int = 1536) -> list:
    """A cheap, non-zero pgvector-compatible embedding for fixtures."""
    return [1.0] + [0.0] * (dimensions - 1)


@pytest.mark.unit
class TestGetFocusAreaSemanticDocHits:
    def test_reaches_module_logger_without_nameerror(self, db_session, app):
        """Regression guard: with an active concept + embedding registered for one
        of the requested area_keys, the function must proceed past the cosine-query
        setup (which logs via the module ``logger``) instead of raising NameError."""
        from app.models.ai_terminology import AITermConcept, AITermConceptEmbedding
        from app.services.ai.terminology_service import get_focus_area_semantic_doc_hits

        concept = AITermConcept(concept_key="cash", display_name="Cash", is_active=True)
        db_session.add(concept)
        db_session.flush()

        db_session.add(AITermConceptEmbedding(
            concept_id=concept.id,
            embedding=_unit_embedding(),
            text_embedded="cash",
            model="test-model",
            dimensions=1536,
        ))
        db_session.commit()

        with app.app_context():
            result = get_focus_area_semantic_doc_hits(
                doc_ids=[999999],
                area_keys=["cash"],
                return_debug=True,
            )

        assert result["hits_by_area"] == {"cash": []}
        assert result["debug"]["concept_stats"]["cash"]["selected_docs"] == 0

    def test_no_active_concepts_short_circuits_before_logging(self, db_session, app):
        """No matching concept embeddings -> early return, no query/log attempted."""
        from app.services.ai.terminology_service import get_focus_area_semantic_doc_hits

        with app.app_context():
            result = get_focus_area_semantic_doc_hits(
                doc_ids=[1],
                area_keys=["unregistered_area"],
                return_debug=True,
            )

        assert result["hits_by_area"] == {"unregistered_area": set()}
        assert "note" in result["debug"]

    def test_empty_doc_ids_short_circuits(self, app):
        from app.services.ai.terminology_service import get_focus_area_semantic_doc_hits

        with app.app_context():
            result = get_focus_area_semantic_doc_hits(doc_ids=[], area_keys=["cash"])

        assert result == {"cash": set()}


@pytest.mark.unit
class TestModuleLocation:
    def test_importable_from_ai_package_not_translation(self):
        """terminology_service is AI retrieval/classification tooling, not a
        translation concern -- it must live under app.services.ai, not
        app.services.translation (see _focus_area_analysis / _query_utils callers)."""
        import app.services.ai.terminology_service  # noqa: F401

        with pytest.raises(ModuleNotFoundError):
            import app.services.translation.terminology_service  # noqa: F401
