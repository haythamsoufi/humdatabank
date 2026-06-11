"""Unit tests for services.upr — pure functions (no database, no LLM).

Covers:
  - app.services.upr.query_detection  (query_prefers_upr_documents)
  - app.services.upr.validation       (upr_kpi_applicable, upr_document_label,
                                        upr_suggestion_reason, format_ifrc_upr_extraction,
                                        _parse_int_number private helper)
"""
import pytest


# ---------------------------------------------------------------------------
# query_detection
# ---------------------------------------------------------------------------

class TestQueryPrefersUprDocuments:
    """query_prefers_upr_documents — heuristic detection of UPR-targeted queries."""

    from app.services.upr.query_detection import query_prefers_upr_documents as _fn

    def _fn(self, q):
        from app.services.upr.query_detection import query_prefers_upr_documents
        return query_prefers_upr_documents(q)

    def test_empty_string_returns_false(self):
        assert self._fn("") is False

    def test_none_returns_false(self):
        assert self._fn(None) is False  # type: ignore[arg-type]

    def test_whitespace_only_returns_false(self):
        assert self._fn("   ") is False

    def test_upr_keyword_matches(self):
        assert self._fn("Tell me about the UPR document for 2024") is True

    def test_unified_plan_phrase_matches(self):
        assert self._fn("What does the unified plan say about volunteers?") is True

    def test_upl_code_matches(self):
        assert self._fn("Find the UPL-2023 document") is True

    def test_up_plan_abbreviated_matches(self):
        assert self._fn("up plan 2025 KPIs") is True

    def test_annual_report_negative_flag(self):
        assert self._fn("UPR annual report 2022") is False

    def test_myr_negative_flag(self):
        assert self._fn("UPR MYR statistics") is False

    def test_ar_negative_flag(self):
        assert self._fn("UPR AR document") is False

    def test_semi_annual_report_negative_flag(self):
        assert self._fn("unified plan semi-annual report 2023") is False

    def test_generic_query_returns_false(self):
        assert self._fn("Number of volunteers in Nepal") is False

    def test_case_insensitive_upr(self):
        assert self._fn("show me the upr targets") is True

    def test_case_insensitive_unified_plan(self):
        assert self._fn("UNIFIED PLAN 2025 key indicators") is True

    def test_mixed_upr_with_midyear_negative(self):
        assert self._fn("upr midyear report") is False


# ---------------------------------------------------------------------------
# upr_kpi_applicable
# ---------------------------------------------------------------------------

class TestUprKpiApplicable:
    """upr_kpi_applicable — guardrail to prevent misuse of UPR KPI cards."""

    def _fn(self, label, keyword):
        from app.services.upr.validation import upr_kpi_applicable
        return upr_kpi_applicable(label, keyword)

    def test_generic_volunteers_applicable(self):
        assert self._fn("Number of volunteers", "volunteers") is True

    def test_generic_staff_applicable(self):
        # Avoid "paid" — substring "aid" is a subset-term guard
        assert self._fn("Total staff headcount", "staff") is True

    def test_generic_branches_applicable(self):
        assert self._fn("Number of branches", "branches") is True

    def test_generic_local_units_applicable(self):
        assert self._fn("Number of local units", "local units") is True

    def test_insured_volunteers_not_applicable(self):
        assert self._fn("Volunteers covered by accident insurance", "volunteers") is False

    def test_active_volunteers_not_applicable(self):
        assert self._fn("Active volunteers", "volunteers") is False

    def test_trained_volunteers_not_applicable(self):
        assert self._fn("Trained volunteers", "volunteers") is False

    def test_youth_volunteers_not_applicable(self):
        assert self._fn("Youth volunteers", "volunteers") is False

    def test_disability_label_not_applicable(self):
        assert self._fn("Volunteers with disability", "volunteers") is False

    def test_percentage_label_not_applicable(self):
        assert self._fn("Percentage of volunteers", "volunteers") is False

    def test_unknown_keyword_not_applicable(self):
        assert self._fn("Total donations", "donations") is False

    def test_empty_label_returns_false(self):
        assert self._fn("", "volunteers") is False

    def test_empty_keyword_returns_false(self):
        assert self._fn("Number of volunteers", "") is False

    def test_none_label_returns_false(self):
        assert self._fn(None, "volunteers") is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# upr_document_label
# ---------------------------------------------------------------------------

class TestUprDocumentLabel:
    """upr_document_label — human-readable label for a UPR source document."""

    def _fn(self, doc):
        from app.services.upr.validation import upr_document_label
        return upr_document_label(doc)

    def test_none_returns_default(self):
        assert self._fn(None) == "UPR document"

    def test_non_dict_returns_default(self):
        assert self._fn("string") == "UPR document"  # type: ignore[arg-type]

    def test_short_title_returned_as_is(self):
        doc = {"source": {"document_title": "UPR Plan 2024"}}
        assert self._fn(doc) == "UPR Plan 2024"

    def test_year_extracted_from_filename_when_title_missing(self):
        # Year token must sit on a word boundary (e.g. space-separated, not _2023)
        doc = {"source": {"document_filename": "nepal upr 2023.pdf"}}
        assert self._fn(doc) == "UPR Plan 2023"

    def test_year_extracted_from_long_title(self):
        long_title = "A" * 90  # >80 chars — should fall back to year extraction
        doc = {"source": {"document_title": long_title, "document_filename": "plan 2022.pdf"}}
        result = self._fn(doc)
        assert "2022" in result

    def test_no_source_returns_default(self):
        assert self._fn({}) == "UPR document"

    def test_title_max_year_used_when_multiple_years(self):
        doc = {"source": {"document_title": "UPR 2020 and 2023 review"}}
        result = self._fn(doc)
        assert "2023" in result


# ---------------------------------------------------------------------------
# upr_suggestion_reason
# ---------------------------------------------------------------------------

class TestUprSuggestionReason:
    """upr_suggestion_reason — user-facing reason string for a UPR suggestion."""

    def _fn(self, upr, value_int):
        from app.services.upr.validation import upr_suggestion_reason
        return upr_suggestion_reason(upr, value_int)

    def test_basic_reason_contains_value(self):
        upr = {"source": {"document_title": "UPR Plan 2024"}}
        reason = self._fn(upr, 1500)
        assert "1,500" in reason

    def test_includes_title(self):
        upr = {"source": {"document_title": "Syria Plan 2024"}}
        reason = self._fn(upr, 200)
        assert "Syria Plan 2024" in reason

    def test_includes_page_when_present(self):
        upr = {"source": {"document_title": "Plan", "page_number": 12}}
        reason = self._fn(upr, 100)
        assert "p. 12" in reason

    def test_confidence_included(self):
        upr = {"source": {"document_title": "Plan", "confidence": 0.85}}
        reason = self._fn(upr, 300)
        assert "85%" in reason

    def test_none_upr_falls_back(self):
        reason = self._fn(None, 500)
        assert "500" in reason

    def test_extraction_appended(self):
        upr = {"source": {"document_title": "Plan", "extraction": "some extracted text"}}
        reason = self._fn(upr, 50)
        assert "some extracted text" in reason

    def test_zero_value_formatted(self):
        upr = {"source": {}}
        reason = self._fn(upr, 0)
        assert "0" in reason


# ---------------------------------------------------------------------------
# format_ifrc_upr_extraction
# ---------------------------------------------------------------------------

class TestFormatIfrcUprExtraction:
    """format_ifrc_upr_extraction — prettify internal extraction token strings."""

    def _fn(self, s):
        from app.services.upr.validation import format_ifrc_upr_extraction
        return format_ifrc_upr_extraction(s)

    def test_empty_string_returns_empty(self):
        assert self._fn("") == ""

    def test_none_like_values_handled(self):
        assert self._fn("none") == ""
        assert self._fn("null") == ""

    def test_midyear_report_formatted(self):
        result = self._fn("ype=midyear_report; year=2024 - local units: 94")
        assert "Mid-year Report" in result
        assert "2024" in result

    def test_annual_report_formatted(self):
        result = self._fn("ype=annual_report; year=2023 - volunteers: 5000")
        assert "Annual Report" in result
        assert "2023" in result

    def test_unified_plan_formatted(self):
        result = self._fn("ype=unified_plan; year=2025 - branches: 10")
        assert "Unified Plan" in result

    def test_raw_string_without_meta_returned_as_is(self):
        result = self._fn("just some raw text without tokens")
        assert "just some raw text" in result

    def test_newlines_replaced_with_spaces(self):
        result = self._fn("ype=annual_report\nyear=2022")
        assert "\n" not in result


# ---------------------------------------------------------------------------
# _parse_int_number (private helper — tested via validation module import)
# ---------------------------------------------------------------------------

class TestParseIntNumber:
    """Private _parse_int_number handles various numeric string formats."""

    def _fn(self, v):
        from app.services.upr.validation import _parse_int_number
        return _parse_int_number(v)

    def test_plain_integer(self):
        assert self._fn(1234) == 1234

    def test_string_integer(self):
        assert self._fn("5000") == 5000

    def test_comma_separated_thousands(self):
        assert self._fn("1,500,000") == 1_500_000

    def test_float_rounds_half_up(self):
        assert self._fn(2.5) == 3
        assert self._fn(3.4) == 3

    def test_none_returns_none(self):
        assert self._fn(None) is None

    def test_bool_returns_none(self):
        assert self._fn(True) is None

    def test_empty_string_returns_none(self):
        assert self._fn("") is None

    def test_non_numeric_string_returns_none(self):
        assert self._fn("abc") is None

    def test_string_with_currency_prefix(self):
        result = self._fn("$1,200")
        assert result == 1200

    def test_narrow_no_break_space_separator(self):
        result = self._fn("10\u202F000")
        assert result == 10_000
