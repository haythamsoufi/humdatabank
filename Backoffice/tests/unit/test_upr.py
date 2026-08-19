"""Unit tests for services.upr — pure functions (no database, no LLM).

Covers:
  - app.services.upr.query_detection  (query_prefers_upr_documents)
  - app.services.upr.validation       (upr_kpi_applicable, upr_document_label,
                                        upr_suggestion_reason, format_ifrc_upr_extraction,
                                        _parse_int_number private helper)
  - app.services.upr.pns_parsing      (parse_participating_national_societies_lines,
                                        shared by visual_chunking.py and document_answering.py)
  - app.services.upr.data_retrieval   (get_upr_kpi_value / get_upr_kpi_timeseries —
                                        country-level ACL gate, mocked at the
                                        resolve_country/check_country_access boundary
                                        so no database is needed)
  - app.services.upr.ux               (step_display_message_get_upr_kpi_value)
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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

    def test_hyphenated_phrasal_verb_plan_does_not_false_positive(self):
        # Regression: "up plan" alone must not match "up" as the tail of an unrelated
        # hyphenated compound like "follow-up"/"clean-up" — the hyphen gives it a regex
        # \b even though it isn't a standalone "up" token in the intended sense.
        assert self._fn("What is the follow-up plan for Nepal?") is False
        assert self._fn("Show me the clean-up plan after the flood response") is False
        assert self._fn("the wrap-up plan for this response") is False

    def test_backup_plan_does_not_match(self):
        # No hyphen and no boundary before "up" inside "backup" — never matched, but
        # kept as an explicit regression guard alongside the hyphenated cases above.
        assert self._fn("What is the backup plan if funding falls short?") is False

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
        doc = {"source": {"document_filename": "nepal upr 2023.pdf"}}
        assert self._fn(doc) == "UPR Plan 2023"

    def test_year_extracted_from_underscore_delimited_filename(self):
        # _YEAR_RE uses digit-boundary lookarounds (not \b) so this common naming
        # convention resolves too — "_" is a word char, so \b alone would miss it.
        doc = {"source": {"document_filename": "INP_2023_Nepal.pdf"}}
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


# ---------------------------------------------------------------------------
# parse_participating_national_societies_lines (shared by visual_chunking.py
# and document_answering.py — see app.services.upr.pns_parsing)
# ---------------------------------------------------------------------------

class TestParseParticipatingNationalSocietiesLines:
    """Shared "Participating National Societies" OCR-panel parser."""

    def _fn(self, lines):
        from app.services.upr.pns_parsing import parse_participating_national_societies_lines
        return parse_participating_national_societies_lines(lines)

    def test_no_header_returns_empty_dict(self):
        assert self._fn(["Some unrelated panel", "with random lines"]) == {}

    def test_empty_lines_returns_empty_dict(self):
        assert self._fn([]) == {}

    def test_splits_starred_names_as_multilateral(self):
        lines = [
            "Participating National Societies",
            "Netherlands Red Cross*",
            "Norwegian Red Cross",
            "British Red Cross*",
            "Hazards",
            "Conflict",
        ]
        result = self._fn(lines)
        assert result["bilateral"] == ["Norwegian Red Cross"]
        assert result["multilateral"] == ["Netherlands Red Cross", "British Red Cross"]
        assert result["raw"] == ["Netherlands Red Cross*", "Norwegian Red Cross", "British Red Cross*"]

    def test_header_split_across_two_lines(self):
        lines = [
            "Participating",
            "National Societies",
            "Danish Red Cross",
            "Hazards",
        ]
        result = self._fn(lines)
        assert result["bilateral"] == ["Danish Red Cross"]

    def test_stops_at_hazards_panel(self):
        lines = [
            "Participating National Societies",
            "Danish Red Cross",
            "Hazards",
            "French Red Cross",  # must NOT be picked up — belongs to the next panel
        ]
        result = self._fn(lines)
        assert result["bilateral"] == ["Danish Red Cross"]

    def test_stops_at_ifrc_breakdown_panel(self):
        lines = [
            "Participating National Societies",
            "Danish Red Cross",
            "IFRC Breakdown",
            "Ongoing emergency operations",
        ]
        result = self._fn(lines)
        assert result["bilateral"] == ["Danish Red Cross"]

    def test_stops_at_multilateral_contributed_footnote(self):
        lines = [
            "Participating National Societies",
            "Danish Red Cross*",
            "National societies which have contributed on a multilateral basis",
            "Spanish Red Cross*",  # must NOT be picked up
        ]
        result = self._fn(lines)
        assert result["multilateral"] == ["Danish Red Cross"]

    def test_split_prefix_national_red_cross_continuation(self):
        # OCR sometimes wraps "... National Red" and "Cross*" onto separate lines/cells.
        lines = [
            "Participating National Societies",
            "Republic of Korea National Red",
            "Cross*",
            "Hazards",
        ]
        result = self._fn(lines)
        assert result["multilateral"] == ["Republic of Korea National Red Cross"]

    def test_ignores_mdr_and_total_chf_cells(self):
        lines = [
            "Participating National Societies",
            "MDR00001  Danish Red Cross  Total CHF 500,000",
            "Hazards",
        ]
        result = self._fn(lines)
        assert result["bilateral"] == ["Danish Red Cross"]

    def test_dedupes_case_insensitively_preserving_first_seen(self):
        lines = [
            "Participating National Societies",
            "Danish Red Cross",
            "danish red cross",
            "Hazards",
        ]
        result = self._fn(lines)
        assert result["bilateral"] == ["Danish Red Cross"]

    def test_no_names_found_returns_empty_dict(self):
        lines = [
            "Participating National Societies",
            "Hazards",
        ]
        assert self._fn(lines) == {}

    def test_noisy_column_split_header(self):
        lines = [
            "IFRC network Funding Requirements  Participating  IFRC Appeal codes",
            "National Societies",
            "Belgian Red Cross*",
            "Hazards",
        ]
        result = self._fn(lines)
        assert result["multilateral"] == ["Belgian Red Cross"]


# ---------------------------------------------------------------------------
# document_answering._extract_participating_national_societies — thin string-based
# wrapper around parse_participating_national_societies_lines (None on no match).
# ---------------------------------------------------------------------------

class TestDocumentAnsweringExtractParticipatingNationalSocieties:
    def _fn(self, content):
        from app.services.upr.document_answering import _extract_participating_national_societies
        return _extract_participating_national_societies(content)

    def test_empty_content_returns_none(self):
        assert self._fn("") is None
        assert self._fn(None) is None  # type: ignore[arg-type]

    def test_no_header_returns_none(self):
        assert self._fn("Just some random OCR text\nwith no NS panel") is None

    def test_valid_panel_returns_dict(self):
        content = "Participating National Societies\nDanish Red Cross\nSwedish Red Cross*\nHazards\n"
        result = self._fn(content)
        assert result == {
            "bilateral": ["Danish Red Cross"],
            "multilateral": ["Swedish Red Cross"],
            "raw": ["Danish Red Cross", "Swedish Red Cross*"],
        }


# ---------------------------------------------------------------------------
# get_upr_kpi_value / get_upr_kpi_timeseries — country-level ACL enforcement
# (app.services.upr.data_retrieval). Mocked at the resolve_country /
# check_country_access boundary (both imported lazily inside the functions),
# so these run with no database or Flask app context, matching the check used
# by the analogous FDRS lookup in app.services.ai.data.form_retrieval.
# ---------------------------------------------------------------------------

class TestUprKpiCountryAccessControl:
    @staticmethod
    def _fake_country(country_id=99):
        return SimpleNamespace(id=country_id, name="Fakeland", iso3="FAK", primary_national_society=None)

    def test_get_upr_kpi_value_denies_inaccessible_country(self):
        from app.services.upr.data_retrieval import get_upr_kpi_value

        with patch("app.services.data_retrieval.country.resolve_country", return_value=self._fake_country()), \
                patch("app.services.data_retrieval.country.check_country_access", return_value=False) as mock_check:
            result = get_upr_kpi_value(country_identifier="Fakeland", metric="volunteers")

        mock_check.assert_called_once_with(99)
        assert result == {"success": False, "error": "Access denied for this country"}

    def test_get_upr_kpi_timeseries_denies_inaccessible_country(self):
        from app.services.upr.data_retrieval import get_upr_kpi_timeseries

        with patch("app.services.data_retrieval.country.resolve_country", return_value=self._fake_country()), \
                patch("app.services.data_retrieval.country.check_country_access", return_value=False) as mock_check:
            result = get_upr_kpi_timeseries(country_identifier="Fakeland", metric="volunteers")

        mock_check.assert_called_once_with(99)
        assert result == {"success": False, "error": "Access denied for this country", "series": []}

    def test_get_upr_kpi_value_missing_country_short_circuits_before_acl_check(self):
        """Country-not-found must return before the ACL check even runs (no country id to check)."""
        from app.services.upr.data_retrieval import get_upr_kpi_value

        with patch("app.services.data_retrieval.country.resolve_country", return_value=None), \
                patch("app.services.data_retrieval.country.check_country_access") as mock_check:
            result = get_upr_kpi_value(country_identifier="Nowhere", metric="volunteers")

        mock_check.assert_not_called()
        assert result == {"success": False, "error": "Country not found: Nowhere"}

    def test_get_upr_kpi_value_unsupported_metric_short_circuits_before_country_lookup(self):
        from app.services.upr.data_retrieval import get_upr_kpi_value

        with patch("app.services.data_retrieval.country.resolve_country") as mock_resolve:
            result = get_upr_kpi_value(country_identifier="Fakeland", metric="donations")

        mock_resolve.assert_not_called()
        assert result["success"] is False
        assert "Unsupported metric" in result["error"]


# ---------------------------------------------------------------------------
# _resolve_upr_block_year (app.services.upr.data_retrieval) — shared year
# resolution used by both get_upr_kpi_value's prefer_year ranking and
# get_upr_kpi_timeseries's year bucketing.
# ---------------------------------------------------------------------------

class TestResolveUprBlockYear:
    def _fn(self, upr, doc):
        from app.services.upr.data_retrieval import _resolve_upr_block_year
        return _resolve_upr_block_year(upr, doc)

    @staticmethod
    def _doc(filename=None):
        return SimpleNamespace(filename=filename)

    def test_year_from_filename_wins_first(self):
        # Deliberately underscore-delimited (the real naming convention, e.g.
        # "INP_2023_Foo.pdf") — regex must use digit-boundary lookarounds, not \b,
        # since "_" is a word char and \b alone would miss this year token entirely.
        upr = {"upr_context": {"year": 2020}, "extraction": "year=2019"}
        assert self._fn(upr, self._doc("AR_2023_Fakeland.pdf")) == 2023

    def test_multiple_filename_years_uses_max(self):
        # e.g. a multi-year plan filename mentioning a range
        assert self._fn({}, self._doc("INP_2025_2027_Fakeland.pdf")) == 2027

    def test_year_ignored_when_part_of_a_longer_digit_run(self):
        # Digit-boundary lookarounds must still reject "20231" etc. as a 4-digit year.
        assert self._fn({}, self._doc("Report_20231_Fakeland.pdf")) is None

    def test_falls_back_to_upr_context_year_when_no_filename_year(self):
        upr = {"upr_context": {"year": 2022}}
        assert self._fn(upr, self._doc("Fakeland-plan.pdf")) == 2022

    def test_falls_back_to_extraction_year_token_when_no_context(self):
        # Defensive fallback only — no current extractor emits this format.
        upr = {"extraction": "pe=annual_report; year=2021 - volunteers: 100"}
        assert self._fn(upr, self._doc("Fakeland-plan.pdf")) == 2021

    def test_bare_extraction_tag_has_no_year_token(self):
        upr = {"extraction": "label_proximity_v2"}
        assert self._fn(upr, self._doc("Fakeland-plan.pdf")) is None

    def test_no_signals_returns_none(self):
        assert self._fn({}, self._doc(None)) is None

    def test_non_dict_upr_context_ignored(self):
        upr = {"upr_context": "not-a-dict", "extraction": "year=2021"}
        assert self._fn(upr, self._doc(None)) == 2021


# ---------------------------------------------------------------------------
# get_upr_kpi_value — prefer_year ranking (end-to-end over a mocked DB query).
#
# Regression coverage for a bug where prefer_year never actually mattered:
# ranking used to derive `year` via _parse_upr_extraction_meta(extraction),
# which only recognizes a `pe=`/`ype=`/`year=` token format that no current
# extractor emits, so year_match was always False and results were ranked by
# confidence/recency only. Fixed by resolving year via _resolve_upr_block_year
# (filename / upr_context.year) before ranking.
# ---------------------------------------------------------------------------

class TestGetUprKpiValuePreferYearRanking:
    @staticmethod
    def _fake_country(country_id=99):
        return SimpleNamespace(id=country_id, name="Fakeland", iso3="FAK", primary_national_society=None)

    @staticmethod
    def _chunk(chunk_id, extra_metadata, page_number=1):
        return SimpleNamespace(id=chunk_id, extra_metadata=extra_metadata, page_number=page_number)

    @staticmethod
    def _doc(doc_id, filename, is_public=True):
        return SimpleNamespace(
            id=doc_id, filename=filename, title=f"Doc {doc_id}",
            is_public=is_public, allowed_roles=None, user_id=None,
            processed_at=None, created_at=None,
        )

    def _mock_db_returning(self, rows):
        mock_query = MagicMock()
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = rows
        mock_db = MagicMock()
        mock_db.session.query.return_value = mock_query
        mock_db.engine.dialect.name = "sqlite"  # anything != "postgresql"
        return mock_db

    def test_prefer_year_outranks_higher_confidence_wrong_year(self):
        from app.services.upr.data_retrieval import get_upr_kpi_value

        row_high_conf_wrong_year = (
            self._chunk(1, {"upr": {"block": "in_support_kpis", "kpis": {"volunteers": "1000"},
                                     "confidence": 0.95, "extraction": "label_proximity_v2"}}),
            self._doc(1, "AR_2023_Fakeland.pdf"),
        )
        row_lower_conf_right_year = (
            self._chunk(2, {"upr": {"block": "in_support_kpis", "kpis": {"volunteers": "2000"},
                                     "confidence": 0.80, "extraction": "label_proximity_v2"}}),
            self._doc(2, "AR_2024_Fakeland.pdf"),
        )
        mock_db = self._mock_db_returning([row_high_conf_wrong_year, row_lower_conf_right_year])

        with patch("app.services.data_retrieval.country.resolve_country", return_value=self._fake_country()), \
                patch("app.services.data_retrieval.country.check_country_access", return_value=True), \
                patch("app.services.upr.data_retrieval.db", mock_db):
            result = get_upr_kpi_value(country_identifier="Fakeland", metric="volunteers", prefer_year=2024)

        assert result["success"] is True
        assert result["value"] == "2000"
        assert result["source"]["year"] == 2024

    def test_without_prefer_year_falls_back_to_confidence(self):
        """Same rows, no prefer_year: highest-confidence candidate should win instead."""
        from app.services.upr.data_retrieval import get_upr_kpi_value

        row_high_conf = (
            self._chunk(1, {"upr": {"block": "in_support_kpis", "kpis": {"volunteers": "1000"},
                                     "confidence": 0.95, "extraction": "label_proximity_v2"}}),
            self._doc(1, "AR_2023_Fakeland.pdf"),
        )
        row_low_conf = (
            self._chunk(2, {"upr": {"block": "in_support_kpis", "kpis": {"volunteers": "2000"},
                                     "confidence": 0.80, "extraction": "label_proximity_v2"}}),
            self._doc(2, "AR_2024_Fakeland.pdf"),
        )
        mock_db = self._mock_db_returning([row_high_conf, row_low_conf])

        with patch("app.services.data_retrieval.country.resolve_country", return_value=self._fake_country()), \
                patch("app.services.data_retrieval.country.check_country_access", return_value=True), \
                patch("app.services.upr.data_retrieval.db", mock_db):
            result = get_upr_kpi_value(country_identifier="Fakeland", metric="volunteers")

        assert result["success"] is True
        assert result["value"] == "1000"
        assert result["source"]["year"] == 2023


# ---------------------------------------------------------------------------
# step_display_message_get_upr_kpi_value (app.services.upr.ux) — step line shown
# while the get_upr_kpi_value tool runs; must surface the optional "year" tool arg
# now that the chat-facing tool spec/registry wrapper accept one (see tool_specs.py
# / app/services/ai/tools/registry.py).
# ---------------------------------------------------------------------------

class TestStepDisplayMessageGetUprKpiValue:
    def _fn(self, tool_args):
        from app.services.upr.ux import step_display_message_get_upr_kpi_value
        return step_display_message_get_upr_kpi_value(tool_args)

    def test_no_args_returns_generic_message(self):
        assert self._fn({}) == "Reading Unified Plans and Reports…"

    def test_country_only(self):
        assert self._fn({"country_identifier": "Kenya"}) == "Reading Unified Plans and Reports for Kenya…"

    def test_country_and_metric_without_year(self):
        result = self._fn({"country_identifier": "Kenya", "metric": "volunteers"})
        assert result == "Reading volunteers from Unified Plans and Reports for Kenya…"

    def test_country_metric_and_year_mentions_year(self):
        result = self._fn({"country_identifier": "Kenya", "metric": "volunteers", "year": 2023})
        assert result == "Reading volunteers from the 2023 Unified Plans and Reports for Kenya…"

    def test_year_ignored_when_metric_missing(self):
        # Year-aware phrasing requires country + metric + year together.
        result = self._fn({"country_identifier": "Kenya", "year": 2023})
        assert result == "Reading Unified Plans and Reports for Kenya…"
