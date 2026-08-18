"""Country / geographic-scope detection for AI documents."""

from unittest.mock import patch

import pytest

from app.services.ai.documents.country_detection import (
    SCOPE_GLOBAL,
    CountryDetectionResult,
    _matched_scope_keyword,
    _norm_space_text,
    score_keyword_confidence,
)
from app.services.ai.documents.country_detection_llm import refine_if_needed

pytestmark = [pytest.mark.unit]


class TestScopeKeywordMatching:
    def test_english_global(self):
        scope, kw = _matched_scope_keyword(_norm_space_text("IFRC Strategy 2030 is a global strategy"))
        assert scope == SCOPE_GLOBAL
        assert kw == "global"

    def test_french_mondiale(self):
        scope, kw = _matched_scope_keyword(_norm_space_text("La Strategie 2030 est une strategie mondiale"))
        assert scope == SCOPE_GLOBAL
        assert kw == "mondiale"

    def test_spanish_mundial(self):
        scope, kw = _matched_scope_keyword(_norm_space_text("La Estrategia 2030 es una estrategia mundial"))
        assert scope == SCOPE_GLOBAL
        assert kw == "mundial"

    def test_arabic_global_survives_normalization(self):
        hay = _norm_space_text("الاستراتيجية العالمية للاتحاد الدولي")
        assert "العالمية" in hay
        scope, kw = _matched_scope_keyword(hay)
        assert scope == SCOPE_GLOBAL
        assert kw == "العالمية"

    def test_no_scope_for_country_only_text(self):
        scope, kw = _matched_scope_keyword(_norm_space_text("Country plan for Kenya 2024"))
        assert scope is None
        assert kw is None


class TestKeywordConfidence:
    def test_empty_with_text_is_low(self):
        conf, reason = score_keyword_confidence(
            upl_hit=False,
            scope=None,
            scope_source=None,
            title_filename_countries=[],
            all_countries=[],
            strong_global=False,
            had_text=True,
        )
        assert conf < 0.7
        assert reason == "empty"

    def test_switzerland_hq_is_low(self):
        conf, reason = score_keyword_confidence(
            upl_hit=False,
            scope=None,
            scope_source=None,
            title_filename_countries=[],
            all_countries=[(1, "Switzerland")],
            strong_global=False,
            had_text=True,
        )
        assert conf < 0.7
        assert reason == "possible_hq_false_positive"

    def test_strong_global_is_high(self):
        conf, reason = score_keyword_confidence(
            upl_hit=False,
            scope=SCOPE_GLOBAL,
            scope_source="content",
            title_filename_countries=[],
            all_countries=[],
            strong_global=True,
            had_text=True,
        )
        assert conf >= 0.7
        assert reason == "strong_global_keyword"

    def test_filename_country_is_high(self):
        conf, _reason = score_keyword_confidence(
            upl_hit=False,
            scope=None,
            scope_source=None,
            title_filename_countries=[(4, "Kenya")],
            all_countries=[(4, "Kenya")],
            strong_global=False,
            had_text=True,
        )
        assert conf >= 0.7


class TestLlmRefine:
    def test_skips_llm_when_disabled(self):
        keyword = CountryDetectionResult(
            countries=[(1, "Switzerland")],
            scope=None,
            confidence=0.25,
            source="keyword",
            reason="possible_hq_false_positive",
        )
        with patch(
            "app.services.ai.documents.country_detection_llm.classify_geography_with_llm"
        ) as classify:
            out = refine_if_needed(
                keyword,
                filename="Strategy-2030-AR.pdf",
                title="Strategy 2030",
                text="Geneva Switzerland IFRC",
                use_llm=False,
            )
            classify.assert_not_called()
            assert out is keyword

    def test_skips_llm_when_confident(self):
        keyword = CountryDetectionResult(
            countries=[],
            scope=SCOPE_GLOBAL,
            confidence=0.9,
            source="keyword",
            reason="strong_global_keyword",
        )
        with patch(
            "app.services.ai.documents.country_detection_llm.classify_geography_with_llm"
        ) as classify:
            out = refine_if_needed(
                keyword,
                filename="S2030-EN.pdf",
                title="Strategy 2030",
                text="worldwide strategy",
                use_llm=True,
            )
            classify.assert_not_called()
            assert out.scope == SCOPE_GLOBAL

    def test_uses_llm_when_low_confidence(self):
        keyword = CountryDetectionResult(
            countries=[(1, "Switzerland")],
            scope=None,
            confidence=0.25,
            source="keyword",
            reason="possible_hq_false_positive",
        )
        llm = CountryDetectionResult(
            countries=[],
            scope=SCOPE_GLOBAL,
            confidence=0.86,
            source="llm",
            reason="federation strategy",
        )
        with patch(
            "app.services.ai.documents.country_detection_llm.classify_geography_with_llm",
            return_value=llm,
        ) as classify:
            out = refine_if_needed(
                keyword,
                filename="Strategy-2030-AR.pdf",
                title="Strategy 2030",
                text="IFRC Strategy 2030 Arabic edition printed in Geneva",
                use_llm=True,
            )
            classify.assert_called_once()
            assert out.scope == SCOPE_GLOBAL
            assert out.source == "llm"
            assert out.countries == []

    def test_keeps_keyword_when_llm_returns_none(self):
        keyword = CountryDetectionResult(
            countries=[],
            scope=None,
            confidence=0.12,
            source="keyword",
            reason="empty",
        )
        with patch(
            "app.services.ai.documents.country_detection_llm.classify_geography_with_llm",
            return_value=None,
        ):
            out = refine_if_needed(
                keyword,
                filename="doc.pdf",
                title="Untitled",
                text="some extracted text",
                use_llm=True,
            )
            assert out is keyword
