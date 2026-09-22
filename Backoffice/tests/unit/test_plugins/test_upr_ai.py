"""Unit tests for services.upr — pure functions (no database, no LLM).

Covers:
  - plugins.upr.ai.query_detection  (query_prefers_upr_documents)
  - plugins.upr.excel.validation       (upr_kpi_applicable, upr_document_label,
                                        upr_suggestion_reason, format_ifrc_upr_extraction,
                                        _parse_int_number private helper)
  - plugins.upr.excel.pns_parsing      (parse_participating_national_societies_lines,
                                        shared by visual_chunking.py and document_answering.py)
  - plugins.upr.ai.data_retrieval   (get_upr_kpi_value / get_upr_kpi_timeseries /
                                        get_upr_visual_blocks — country-level ACL gate, mocked at the
                                        resolve_country/check_country_access boundary
                                        so no database is needed)
  - plugins.upr.ai.ux               (step_display_message_get_upr_kpi_value)
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# query_detection
# ---------------------------------------------------------------------------

class TestQueryPrefersUprDocuments:
    """query_prefers_upr_documents — heuristic detection of UPR-targeted queries."""

    from plugins.upr.ai.query_detection import query_prefers_upr_documents as _fn

    def _fn(self, q):
        from plugins.upr.ai.query_detection import query_prefers_upr_documents
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
        from plugins.upr.excel.validation import upr_kpi_applicable
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
        from plugins.upr.excel.validation import upr_document_label
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
        from plugins.upr.excel.validation import upr_suggestion_reason
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
        from plugins.upr.excel.validation import format_ifrc_upr_extraction
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
        from plugins.upr.excel.validation import _parse_int_number
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
# and document_answering.py — see plugins.upr.excel.pns_parsing)
# ---------------------------------------------------------------------------

class TestParseParticipatingNationalSocietiesLines:
    """Shared "Participating National Societies" OCR-panel parser."""

    def _fn(self, lines):
        from plugins.upr.excel.pns_parsing import parse_participating_national_societies_lines
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
        from plugins.upr.ai.document_answering import _extract_participating_national_societies
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
# (plugins.upr.ai.data_retrieval). Mocked at the resolve_country /
# check_country_access boundary (both imported lazily inside the functions),
# so these run with no database or Flask app context, matching the check used
# by the analogous FDRS lookup in app.services.ai.data.form_retrieval.
# ---------------------------------------------------------------------------

class TestUprKpiCountryAccessControl:
    @staticmethod
    def _fake_country(country_id=99):
        return SimpleNamespace(id=country_id, name="Fakeland", iso3="FAK", primary_national_society=None)

    def test_get_upr_kpi_value_denies_inaccessible_country(self):
        from plugins.upr.ai.data_retrieval import get_upr_kpi_value

        with patch("app.services.data_retrieval.country.resolve_country", return_value=self._fake_country()), \
                patch("app.services.data_retrieval.country.check_country_access", return_value=False) as mock_check:
            result = get_upr_kpi_value(country_identifier="Fakeland", metric="volunteers")

        mock_check.assert_called_once_with(99)
        assert result == {"success": False, "error": "Access denied for this country"}

    def test_get_upr_kpi_timeseries_denies_inaccessible_country(self):
        from plugins.upr.ai.data_retrieval import get_upr_kpi_timeseries

        with patch("app.services.data_retrieval.country.resolve_country", return_value=self._fake_country()), \
                patch("app.services.data_retrieval.country.check_country_access", return_value=False) as mock_check:
            result = get_upr_kpi_timeseries(country_identifier="Fakeland", metric="volunteers")

        mock_check.assert_called_once_with(99)
        assert result == {"success": False, "error": "Access denied for this country", "series": []}

    def test_get_upr_kpi_value_missing_country_short_circuits_before_acl_check(self):
        """Country-not-found must return before the ACL check even runs (no country id to check)."""
        from plugins.upr.ai.data_retrieval import get_upr_kpi_value

        with patch("app.services.data_retrieval.country.resolve_country", return_value=None), \
                patch("app.services.data_retrieval.country.check_country_access") as mock_check:
            result = get_upr_kpi_value(country_identifier="Nowhere", metric="volunteers")

        mock_check.assert_not_called()
        assert result == {"success": False, "error": "Country not found: Nowhere"}

    def test_get_upr_kpi_value_unsupported_metric_short_circuits_before_country_lookup(self):
        from plugins.upr.ai.data_retrieval import get_upr_kpi_value

        with patch("app.services.data_retrieval.country.resolve_country") as mock_resolve:
            result = get_upr_kpi_value(country_identifier="Fakeland", metric="donations")

        mock_resolve.assert_not_called()
        assert result["success"] is False
        assert "Unsupported metric" in result["error"]


# ---------------------------------------------------------------------------
# _resolve_upr_block_year (plugins.upr.ai.data_retrieval) — shared year
# resolution used by both get_upr_kpi_value's prefer_year ranking and
# get_upr_kpi_timeseries's year bucketing.
# ---------------------------------------------------------------------------

class TestResolveUprBlockYear:
    def _fn(self, upr, doc):
        from plugins.upr.ai.data_retrieval import _resolve_upr_block_year
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
        from plugins.upr.ai.data_retrieval import get_upr_kpi_value

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
                patch("plugins.upr.ai.data_retrieval.db", mock_db):
            result = get_upr_kpi_value(country_identifier="Fakeland", metric="volunteers", prefer_year=2024)

        assert result["success"] is True
        assert result["value"] == "2000"
        assert result["source"]["year"] == 2024

    def test_without_prefer_year_falls_back_to_confidence(self):
        """Same rows, no prefer_year: highest-confidence candidate should win instead."""
        from plugins.upr.ai.data_retrieval import get_upr_kpi_value

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
                patch("plugins.upr.ai.data_retrieval.db", mock_db):
            result = get_upr_kpi_value(country_identifier="Fakeland", metric="volunteers")

        assert result["success"] is True
        assert result["value"] == "1000"
        assert result["source"]["year"] == 2023


# ---------------------------------------------------------------------------
# step_display_message_get_upr_kpi_value (plugins.upr.ai.ux) — step line shown
# while the get_upr_kpi_value tool runs; must surface the optional "year" tool arg
# now that the chat-facing tool spec/registry wrapper accept one (see tool_specs.py
# / app/services/ai/tools/registry.py).
# ---------------------------------------------------------------------------

class TestStepDisplayMessageGetUprKpiValue:
    def _fn(self, tool_args):
        from plugins.upr.ai.ux import step_display_message_get_upr_kpi_value
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


# ---------------------------------------------------------------------------
# Form-data AI validation helpers (plugins.upr.ai.form_validation / prompts)
# ---------------------------------------------------------------------------

class TestUprFormdataValidation:
    def test_is_upr_form_template_ids(self):
        from plugins.upr.ai.prompts import is_upr_form_template

        assert is_upr_form_template(24) is True
        assert is_upr_form_template(22) is True
        assert is_upr_form_template(33) is True
        assert is_upr_form_template(23) is True
        assert is_upr_form_template(21) is False
        assert is_upr_form_template(None) is False
        assert is_upr_form_template("not-a-number") is False

    def test_infer_people_to_be_reached(self):
        from plugins.upr.ai.form_validation import infer_upr_item_kind

        assert infer_upr_item_kind({
            "template_id": 24,
            "form_item_label": "Longer term programmes",
            "section_name": "People to be reached by Madagascar",
        }) == "people_to_be_reached"

    def test_infer_funding_from_blank_label_and_section(self):
        from plugins.upr.ai.form_validation import effective_upr_item_label, infer_upr_item_kind

        ctx = {
            "template_id": 24,
            "form_item_label": "-",
            "section_name": "Funding requirements (CHF)",
            "subsection_name": "Funding Requirements for 2027",
            "disagg_values": {"HNS - Health and wellbeing": 850100},
        }
        assert infer_upr_item_kind(ctx) == "funding"
        assert "Funding Requirements" in effective_upr_item_label(ctx)

    def test_infer_bilateral_and_comments(self):
        from plugins.upr.ai.form_validation import infer_upr_item_kind, is_upr_comment_field

        bilateral = {
            "template_id": 24,
            "form_item_label": "List National Societies supporting bilaterally",
        }
        comments = {
            "template_id": 24,
            "form_item_label": "Please include any comments you have on the data you entered above",
            "section_name": "Comments",
        }
        assert infer_upr_item_kind(bilateral) == "bilateral_support"
        assert is_upr_comment_field(comments) is True
        assert is_upr_comment_field({"template_id": 21, "form_item_label": "Comments"}) is False

    def test_comment_heuristic_does_not_use_historical_numbers(self):
        from plugins.upr.ai.form_validation import upr_comment_heuristic

        result = upr_comment_heuristic({
            "value": "On a gardé les sommes déjà mentionnées dans le plan unifié.",
        })
        assert result["verdict"] == "good"
        assert result["quality"] == 0.8
        assert "not a numeric" in result["opinion"].lower()

    def test_comments_still_skip_historical_retrieval(self):
        from plugins.upr.ai.form_validation import apply_upr_validation_context

        ctx = apply_upr_validation_context({
            "template_id": 24,
            "form_item_label": "Please include any comments you have on the data you entered above",
            "section_name": "Comments",
        })
        assert ctx["upr_skip_historical"] is True

    def test_validation_prompt_warns_off_annual_reports(self):
        from plugins.upr.ai.prompts import get_upr_formdata_validation_prompt

        text = get_upr_formdata_validation_prompt({
            "template_id": 24,
            "period_name": "2027",
            "upr_item_kind": "funding",
            "upr_effective_label": "Funding Requirements for 2027",
        })
        assert "Unified Country Plan" in text
        assert "Annual Reports" in text
        assert "context only" in text.lower() or "CONTEXT ONLY" in text
        assert "CHF" in text
        assert "year+2" in text.lower() or "Year+2" in text
        assert "not independent" in text.lower() or "NOT independent" in text

    def test_query_hint_does_not_force_funding_on_people_matrix(self):
        from plugins.upr.ai.form_validation import upr_evidence_query_hint

        hint = upr_evidence_query_hint({
            "template_id": 24,
            "form_item_label": "Longer term programmes",
            "section_name": "People to be reached",
        })
        assert "people to be reached" in hint.lower()
        assert "Unified Plan" in hint
        assert hint.lower().count("funding") == 0

    def test_apply_context_without_upr_docs_skips_visual_fetch(self):
        from plugins.upr.ai.form_validation import apply_upr_validation_context

        ctx = apply_upr_validation_context(
            {
                "template_id": 24,
                "form_item_label": "-",
                "section_name": "Funding requirements (CHF)",
                "subsection_name": "Funding Requirements for 2027",
                "disagg_values": {"HNS - Health": 1},
                "value": "matrix total 1",
            },
            sources_cfg={"historical": True, "system_documents": True, "upr_documents": False},
        )
        assert ctx["upr_form"] is True
        assert ctx["upr_item_kind"] == "funding"
        assert "upr_visuals" not in ctx
        assert ctx["value"] == "matrix total 1"
        assert "upr_skip_historical" not in ctx
        assert ctx["upr_matrix_reading"]["value_role"] == "possibly_not_chf_small_integers"
        assert "upr_value_preview" in ctx

    def test_parse_funding_and_people_cell_keys(self):
        from plugins.upr.ai.matrix_reading import parse_matrix_cell_key

        funding = parse_matrix_cell_key("HNS- Response - Disasters and crises")
        assert funding["actor"] == "HNS"
        assert funding["programme"] == "Response (emergency)"
        assert funding["sp_key"] == "disasters_and_crises"

        secretariat = parse_matrix_cell_key("IFRC Secretariat - Resilience - Climate and environment")
        assert secretariat["actor"] == "IFRC Secretariat"
        assert secretariat["programme"] == "Resilience (longer-term)"
        assert secretariat["sp_key"] == "climate_and_environment"

        people = parse_matrix_cell_key("2028 - Resilience - Climateand environment")
        assert people["year"] == 2028
        assert people["sp_key"] == "climate_and_environment"

        compact = parse_matrix_cell_key("2027_SP1")
        assert compact["year"] == 2027
        assert compact["sp_key"] == "climate_and_environment"

        compact_health = parse_matrix_cell_key("2026_SP3")
        assert compact_health["year"] == 2026
        assert compact_health["sp_key"] == "health_and_wellbeing"

        bilateral = parse_matrix_cell_key("100- Enabling Functions")
        assert bilateral["actor"] == "PNS #100"
        assert bilateral["sp_key"] == "enabling_functions"

        tight = parse_matrix_cell_key("100 -Resilience - Migration and displacement")
        assert tight["actor"] == "PNS #100"
        assert tight["programme"] == "Resilience (longer-term)"
        assert tight["sp_key"] == "migration_and_displacement"

    def test_interpret_people_matrix_keeps_small_ints_as_people_targets(self):
        from plugins.upr.ai.matrix_reading import format_upr_matrix_reading_for_prompt, interpret_upr_matrix

        reading = interpret_upr_matrix({
            "upr_item_kind": "people_to_be_reached",
            "period_year": 2027,
            "disagg_values": {
                "2027 - Resilience - Climate and environment": 5,
                "2027 - Response - Disasters and crises": 1,
                "2028 - Resilience - Climateand environment": 3,
            },
        })
        assert reading is not None
        assert reading["value_role"] == "people_count"
        assert reading["unit"] == "people"
        assert reading["implausible_small_people_targets"] is True
        assert reading["grand_total"] == 9
        assert "people target" in reading["value_preview"].lower()
        text = format_upr_matrix_reading_for_prompt({"upr_matrix_reading": reading})
        assert "DO NOT validate this sum" in text
        assert "not independent confirmation" in text.lower()
        assert "not programme flags" in text.lower()
        assert "NOT people-to-be-reached totals" not in text

    def test_compare_people_flags_to_historical_people_counts(self):
        from plugins.upr.ai.form_validation import (
            apply_upr_matrix_history_guardrail,
            attach_upr_historical_matrix_context,
            upr_matrix_history_heuristic,
        )
        from plugins.upr.ai.matrix_reading import (
            compare_upr_matrix_to_history,
            format_upr_historical_matrices_for_prompt,
            interpret_upr_matrix,
        )

        current = interpret_upr_matrix({
            "upr_item_kind": "people_to_be_reached",
            "period_year": 2027,
            "disagg_values": {
                "2027 - Resilience - Climate and environment": 1,
                "2027 - Resilience - Disasters and crises": 1,
                "2027 - Resilience - Health and wellbeing": 1,
                "2027 - Response - Disasters and crises": 0,
                "2028 - Resilience - Climate and environment": 1,
            },
        })
        historical = interpret_upr_matrix({
            "upr_item_kind": "people_to_be_reached",
            "period_year": 2026,
            "disagg_values": {
                "2026 - Resilience - Climate and environment": 150000,
                "2026 - Resilience - Disasters and crises": 220000,
                "2026 - Resilience - Health and wellbeing": 80000,
            },
        })
        assert current["value_role"] == "people_count"
        assert current["implausible_small_people_targets"] is True
        assert historical["value_role"] == "people_count"

        comparison = compare_upr_matrix_to_history(current, [{
            "period_name": "Annual 2026",
            "reading": historical,
        }])
        assert comparison["unit_or_scale_change"] is True
        assert comparison["notes"][0]["match"] == "unit_or_scale_change"

        ctx = {
            "upr_form": True,
            "upr_item_kind": "people_to_be_reached",
            "section_name": "People to be reached",
            "form_item_label": "Longer term programmes",
            "upr_matrix_reading": current,
        }
        hist = {
            "summary": {"count": 1},
            "series": [{
                "period_name": "Annual 2026",
                "period_year": 2026,
                "value_int": 450000,
                "disagg_values": {
                    "2026 - Resilience - Climate and environment": 150000,
                    "2026 - Resilience - Disasters and crises": 220000,
                    "2026 - Resilience - Health and wellbeing": 80000,
                },
            }],
        }
        attach_upr_historical_matrix_context(ctx, hist)
        assert ctx["upr_historical_comparison"]["unit_or_scale_change"] is True
        prompt = format_upr_historical_matrices_for_prompt(ctx)
        assert "UNIT/SCALE CHANGE" in prompt
        assert "150000" in prompt or "150,000" in prompt

        heuristic = upr_matrix_history_heuristic(ctx)
        assert heuristic is not None
        assert heuristic["verdict"] == "discrepancy"

        verdict, _conf, opinion = apply_upr_matrix_history_guardrail(
            "good", 0.9,
            "The submitted matrix aligns with the authoritative UPR matrix reading.",
            ctx,
        )
        assert verdict == "discrepancy"
        assert "internally consistent" in opinion.lower() or "unit" in opinion.lower()
        assert "people" in opinion.lower()

    def test_people_targets_compact_keys_vs_prior_assignment_scale(self):
        from plugins.upr.ai.form_validation import (
            apply_upr_matrix_history_guardrail,
            attach_upr_historical_matrix_context,
            upr_matrix_history_heuristic,
        )
        from plugins.upr.ai.matrix_reading import interpret_upr_matrix, people_history_magnitude_reason

        current_disagg = {
            "2027_SP1": 5,
            "2027_SP2": 1,
            "2027_SP4": 0,
            "2028_SP1": 3,
            "2028_SP2": 1,
            "2028_SP4": 0,
            "2029_SP4": 0,
            "2029_SP2": 0,
            "2028_SP5": 1,
            "2029_SP5": 0,
            "2029_SP3": 0,
            "2027_SP5": 1,
            "2027_SP3": 1,
            "2028_SP3": 1,
            "2029_SP1": 0,
        }
        prior_disagg = {
            "2026_SP1": 30000,
            "2026_SP2": 70000,
            "2026_SP3": 2500000,
            "2026_SP5": 6574,
            "2027_SP1": 40500,
            "2027_SP2": 94500,
            "2027_SP3": 3000000,
            "2027_SP5": 6574,
            "2028_SP1": 45000,
            "2028_SP2": 127575,
            "2028_SP3": 3500000,
            "2028_SP5": 6574,
        }
        current = interpret_upr_matrix({
            "upr_item_kind": "people_to_be_reached",
            "form_item_label": "Longer term programmes",
            "disagg_values": current_disagg,
        })
        assert current["value_role"] == "people_count"
        assert current["implausible_small_people_targets"] is True
        assert current["by_sp"]["climate_and_environment"] == 8  # 5+3+0
        assert current["by_year"]["2027"] == 8  # 5+1+0+1+1

        ctx = {
            "upr_form": True,
            "upr_item_kind": "people_to_be_reached",
            "section_name": "People to be reached",
            "form_item_label": "Longer term programmes",
            "upr_matrix_reading": current,
        }
        hist = {
            "summary": {"count": 1, "max": 3500000},
            "series": [{
                "period_name": "Annual 2026",
                "period_year": 2026,
                "value_int": 9507223,
                "disagg_values": prior_disagg,
            }],
        }
        attach_upr_historical_matrix_context(ctx, hist)
        assert ctx["upr_historical_comparison"]["unit_or_scale_change"] is True
        assert "people targets" in (ctx["upr_historical_comparison"]["notes"][0].get("reason") or "").lower()

        heuristic = upr_matrix_history_heuristic(ctx, hist)
        assert heuristic["verdict"] == "discrepancy"

        verdict, _conf, opinion = apply_upr_matrix_history_guardrail(
            "good", 0.9,
            "The submitted matrix aligns with the authoritative UPR matrix reading: "
            "15 cells with 8 non-zero programme flags.",
            ctx,
            hist,
        )
        assert verdict == "discrepancy"
        assert "2,500,000" in opinion or "3,500,000" in opinion or "people" in opinion.lower()

        # Scalar history only (prior disagg missing) still flags the collapse.
        scalar_only = {
            "upr_form": True,
            "upr_item_kind": "people_to_be_reached",
            "upr_matrix_reading": current,
        }
        reason = people_history_magnitude_reason(scalar_only, {
            "summary": {"count": 1, "max": 3500000},
            "series": [{"period_name": "Annual 2026", "value_int": 3500000}],
        })
        assert reason is not None
        assert "3,500,000" in reason

    def test_interpret_funding_matrix_totals_by_actor(self):
        from plugins.upr.ai.matrix_reading import interpret_upr_matrix

        reading = interpret_upr_matrix({
            "upr_item_kind": "funding",
            "period_year": 2027,
            "section_name": "Funding requirements (CHF)",
            "subsection_name": "Funding Requirements for [assignment_period]",
            "disagg_values": {
                "HNS - Resilience - Climate and environment": 461320,
                "IFRC Secretariat - Resilience - Climate and environment": 276792,
                "HNS- Response - Disasters and crises": 1845281,
                "col - header|EA1": "Madagascar Tropical Cyclone",
            },
        })
        assert reading is not None
        assert reading["year_slot"] == 2027
        assert reading["unit"] == "CHF"
        assert reading["by_actor"]["HNS"] == 461320 + 1845281
        assert reading["by_actor"]["IFRC Secretariat"] == 276792
        assert reading["grand_total"] == 461320 + 276792 + 1845281
        assert "ignored_header_cells" in reading

    def test_year_slot_plus_two_from_subsection(self):
        from plugins.upr.ai.matrix_reading import year_slot_from_context

        assert year_slot_from_context({
            "period_year": 2027,
            "subsection_name": "Funding Requirements for [[assignment_period]+2]",
        }) == 2029

    def test_apply_context_non_upr_unchanged(self):
        from plugins.upr.ai.form_validation import apply_upr_validation_context

        original = {"template_id": 21, "form_item_label": "Volunteers"}
        ctx = apply_upr_validation_context(original, sources_cfg=None)
        assert ctx == original
        assert "upr_form" not in ctx

    def test_get_upr_visual_blocks_denies_inaccessible_country(self):
        from plugins.upr.ai.data_retrieval import get_upr_visual_blocks

        fake = SimpleNamespace(id=99, name="Fakeland", iso3="FAK", primary_national_society=None)
        with patch("app.services.data_retrieval.country.resolve_country", return_value=fake), \
                patch("app.services.data_retrieval.country.check_country_access", return_value=False) as mock_check:
            result = get_upr_visual_blocks(
                country_identifier="Fakeland",
                block_types=["funding_requirements"],
            )

        mock_check.assert_called_once_with(99)
        assert result["success"] is False
        assert result["error"] == "Access denied for this country"
        assert result.get("blocks") == []

    def test_get_upr_visual_blocks_rejects_unknown_types(self):
        from plugins.upr.ai.data_retrieval import get_upr_visual_blocks

        with patch("app.services.data_retrieval.country.resolve_country") as mock_resolve:
            result = get_upr_visual_blocks(country_identifier="Fakeland", block_types=["not_a_block"])

        mock_resolve.assert_not_called()
        assert result["success"] is False
        assert "No supported" in result["error"]


class TestUprAssignmentReview:
    def _item(self, item_id, label, section=""):
        section_obj = SimpleNamespace(name=section, parent_section=None) if section else None
        return SimpleNamespace(id=item_id, label=label, form_section=section_obj)

    def _entry(self, cells=None, value=None):
        payload = {"values": cells or {}}
        return SimpleNamespace(
            value=value,
            disagg_data=payload,
            get_display_disagg_data=lambda: payload,
            get_display_value=lambda: value,
        )

    def test_ifrc_secretariat_selected_ea_without_value_is_flag(self):
        from plugins.upr.ai.assignment_review import audit_funding_ifrc_secretariat

        item = self._item(967, "-", "Funding Requirements for 2027")
        entry = self._entry({
            "IFRC Secretariat_SP1": 1000,
            "IFRC Secretariat_SP2": 2000,
            "IFRC Secretariat_SP3": 3000,
            "IFRC Secretariat_SP4": 4000,
            "IFRC Secretariat_SP5": 5000,
            "IFRC Secretariat_EFs": 6000,
            "col_header|EA1": "Madagascar Tropical Cyclone (MDRMG019)",
        })
        result = audit_funding_ifrc_secretariat(item, entry, available_emergencies=[])
        codes = {f["code"] for f in result["findings"]}
        assert "ifrc_secretariat_selected_ea_blank" in codes

    def test_ifrc_secretariat_unselected_available_emergency_is_highlight(self):
        from plugins.upr.ai.assignment_review import audit_funding_ifrc_secretariat

        item = self._item(967, "Funding Requirements for 2027")
        entry = self._entry({
            "IFRC Secretariat_SP1": 1000,
            "IFRC Secretariat_SP2": 2000,
            "IFRC Secretariat_SP3": 3000,
            "IFRC Secretariat_SP4": 4000,
            "IFRC Secretariat_SP5": 5000,
            "IFRC Secretariat_EFs": 6000,
        })
        result = audit_funding_ifrc_secretariat(
            item,
            entry,
            available_emergencies=[{"label": "Madagascar Tropical Cyclone (MDRMG019)", "code": "MDRMG019"}],
        )
        codes = {f["code"] for f in result["findings"]}
        assert "ifrc_secretariat_ea_not_selected" in codes
        assert all(f["severity"] == "highlight" for f in result["findings"] if f["code"] == "ifrc_secretariat_ea_not_selected")

    def test_empty_ns_key_figures_is_flag(self):
        from plugins.upr.ai.assignment_review import audit_ns_key_figures

        items = [
            self._item(1, "Branches", "National Society key figures"),
            self._item(2, "Staff", "National Society key figures"),
            self._item(3, "Volunteers", "National Society key figures"),
        ]
        result = audit_ns_key_figures(items, {})
        assert result["finding"]["code"] == "ns_key_figures_empty"
        assert result["finding"]["severity"] == "flag"

    def test_comment_is_kept_for_review(self):
        from plugins.upr.ai.assignment_review import audit_comments

        item = self._item(956, "Please include any comments")
        entry = self._entry(value="Les chiffres 2027 restent indicatifs.")
        result = audit_comments(item, entry)
        assert result["text"].startswith("Les chiffres")
        assert result["finding"]["code"] == "assignment_comment_present"

    def test_people_emergency_not_added_is_flag(self):
        from plugins.upr.ai import assignment_review as ar

        item = self._item(960, "Emergency Appeals")
        entry = self._entry({})
        with patch.object(ar, "list_available_emergencies", return_value=[
            {"label": "Cyclone (MDRMG019)", "code": "MDRMG019", "name": "Cyclone"},
        ]):
            result = ar.audit_people_emergency(item, entry, aes=SimpleNamespace(id=1))
        codes = {f["code"] for f in result["findings"]}
        assert "emergency_people_not_added" in codes

    def test_finding_label_resolves_assignment_period_placeholder(self):
        """Item labels stored with `[assignment_period]` placeholders (resolved by
        VariableResolutionService on the entry form) must not leak the literal
        bracket text into the numbered "Needs attention" list."""
        from plugins.upr.ai import assignment_review as ar

        item = self._item(960, "Emergency Appeals in [assignment_period]")
        entry = self._entry({})
        with patch.object(ar, "list_available_emergencies", return_value=[
            {"label": "Cyclone (MDRMG019)", "code": "MDRMG019", "name": "Cyclone"},
        ]):
            result = ar.audit_people_emergency(
                item, entry, aes=SimpleNamespace(id=1),
                resolved_variables={"assignment_period": "2027"},
                variable_configs={},
            )
        finding = next(f for f in result["findings"] if f["code"] == "emergency_people_not_added")
        assert finding["label"] == "Emergency Appeals in 2027"
        assert "[assignment_period]" not in finding["label"]

    def test_status_for_figures_worst_severity_wins(self):
        """_status_for_figures — single source of truth for whether an overview-figure
        tile is shown (app/services/ai/validation/assignment_review.py._fallback_review
        only tiles a check whose status is "ok"). Flag beats highlight beats ok."""
        from plugins.upr.ai.assignment_review import _status_for_figures

        figs = {"filled": 4, "total": 4}
        assert _status_for_figures(figs, {"severity": "ok"})["status"] == "ok"
        assert _status_for_figures(figs, {"severity": "flag"})["status"] == "flag"
        assert _status_for_figures(figs, {"severity": "highlight"})["status"] == "highlight"
        # A findings LIST (audit_people_emergency / audit_funding_ifrc_secretariat shape):
        # any flag among several findings wins over highlights/oks in the same list.
        assert _status_for_figures(figs, [
            {"severity": "ok"}, {"severity": "highlight"}, {"severity": "flag"},
        ])["status"] == "flag"
        assert _status_for_figures(figs, [{"severity": "ok"}, {"severity": "highlight"}])["status"] == "highlight"
        # Original figures keys are preserved alongside the new "status" key.
        tagged = _status_for_figures(figs, {"severity": "ok"})
        assert tagged["filled"] == 4 and tagged["total"] == 4

    def test_status_for_figures_empty_figures_dict_stays_empty(self):
        """An unresolved item's {} figures dict must stay exactly {} (falsy) rather than
        becoming a truthy {"status": None} — callers gate tile-building on `if ns:` etc."""
        from plugins.upr.ai.assignment_review import _status_for_figures

        assert _status_for_figures({}, {"severity": "flag"}) == {}
        assert _status_for_figures(None, {"severity": "flag"}) == {}

    def test_status_for_figures_no_findings_at_all_is_none(self):
        from plugins.upr.ai.assignment_review import _status_for_figures

        result = _status_for_figures({"filled": 0, "total": 4}, None, [])
        assert result["status"] is None

    def test_assignment_review_prompt_includes_policy(self):
        from plugins.upr.ai.prompts import get_upr_assignment_review_prompt, get_upr_formdata_validation_prompt

        text = get_upr_assignment_review_prompt(pack_text="- Findings: none\n", field_opinions=[], counts={"good": 6})
        assert "item 960" in text.lower() or "960" in text
        assert "IFRC Secretariat" in text
        assert "956" in text
        funding = get_upr_formdata_validation_prompt({
            "template_id": 24,
            "upr_item_kind": "funding",
            "upr_effective_label": "Funding Requirements for 2027",
        })
        assert "IFRC Secretariat" in funding
        assert "col_header" in funding or "EA1" in funding
        comments = get_upr_formdata_validation_prompt({
            "template_id": 24,
            "upr_item_kind": "comments",
        })
        assert "LANGUAGE OTHER THAN ENGLISH" in comments


class TestListAvailableEmergencies:
    """list_available_emergencies / _emops_config_sources.

    Regression coverage for assignment 4301: the funding matrix (item 967's real
    shape) has EA1/EA2/EA3 *selectable header* columns sourced from the
    emergency_operations list, each with its own ``header_plugin_config`` — and NO
    matrix-level ``plugin_config`` at all. Reading only the matrix-level key (the old
    behaviour) applied almost no filtering (all types, closed included, no date
    cutoff) and reported emergencies as "available to select" that none of the
    item's real per-column dropdowns would ever offer, producing a false
    "no emergency appeal selected, but N are available" finding. See
    ``app/static/js/forms/modules/matrix/selectable-headers.js`` for the live picker
    this must match: ``columnDef?.header_plugin_config || matrix?.config?.plugin_config``.
    """

    def _matrix_item(self, matrix_config, item_id=967):
        return SimpleNamespace(id=item_id, config={"matrix_config": matrix_config})

    def _patch_lookup(self, fake_fetch, iso="GMB", period="2027"):
        return (
            patch(
                "app.services.forms.emergency_section_binding._country_iso_for_aes",
                lambda aes: iso,
            ),
            patch(
                "app.services.forms.emergency_section_binding._assignment_period_for_aes",
                lambda aes: period,
            ),
            patch(
                "plugins.emergency_operations.routes.get_emergency_operations_data",
                fake_fetch,
            ),
        )

    def test_row_mode_matrix_uses_matrix_level_plugin_config(self):
        """Item 960's shape: row_mode=list_library rows sourced from emergency_operations
        — unchanged behaviour, filters come from the single matrix-level plugin_config."""
        from plugins.upr.ai.assignment_review import list_available_emergencies

        calls = []

        def fake_fetch(country_iso=None, config=None):
            calls.append(config)
            return [{"id": "1", "code": "MDRXX001", "name": "Storm"}]

        item = self._matrix_item({
            "row_mode": "list_library",
            "lookup_list_id": "emergency_operations",
            "plugin_config": {
                "emops_operation_types": ["Emergency Appeal"],
                "emops_show_closed_operations": False,
            },
            "columns": [{"name": "Total People to be reached", "type": "number"}],
        }, item_id=960)

        p1, p2, p3 = self._patch_lookup(fake_fetch)
        with p1, p2, p3:
            result = list_available_emergencies(item, aes=SimpleNamespace(id=1))

        assert [op["code"] for op in result] == ["MDRXX001"]
        assert len(calls) == 1
        assert calls[0]["operation_types"] == ["Emergency Appeal"]

    def test_selectable_header_columns_use_their_own_config_not_matrix_level(self):
        """Item 967's real shape: no matrix-level plugin_config — each EA column's own
        header_plugin_config decides what it offers, and they can disagree with each
        other (one EA slot can be filtered far more strictly than another)."""
        from plugins.upr.ai.assignment_review import list_available_emergencies

        def fake_fetch(country_iso=None, config=None):
            if config.get("operation_types") == ["Emergency Appeal"] and config.get("end_date_gt") == "2023-12-31":
                return [{"id": "1", "code": "MDRGM017", "name": "Gambia - Population Movement"}]
            return []

        item = self._matrix_item({
            # No top-level "plugin_config" key at all — matches item 967 in production.
            "columns": [
                {
                    "name": "EA1",
                    "header_type": "selectable",
                    "header_source": "list_library",
                    "header_lookup_list_id": "emergency_operations",
                    "header_plugin_config": {
                        "emops_end_date_gt": "2023-12-31",
                        "emops_show_closed_operations": False,
                        "emops_operation_types": ["Emergency Appeal"],
                    },
                },
                {
                    "name": "EA2",
                    "header_type": "selectable",
                    "header_source": "list_library",
                    "header_lookup_list_id": "emergency_operations",
                    "header_plugin_config": {
                        # A cutoff so strict nothing in the fake feed matches.
                        "emops_end_date_gt": "2099-12-31",
                        "emops_show_closed_operations": False,
                        "emops_operation_types": ["Emergency Appeal"],
                    },
                },
            ],
        })

        p1, p2, p3 = self._patch_lookup(fake_fetch)
        with p1, p2, p3:
            result = list_available_emergencies(item, aes=SimpleNamespace(id=1))

        assert [op["code"] for op in result] == ["MDRGM017"]

    def test_selectable_header_all_filtered_out_returns_empty(self):
        """The exact assignment-4301 regression: every EA column's own filters
        legitimately resolve to zero options — must not fall back to an unfiltered
        matrix-level lookup and invent availability that the live picker never shows."""
        from plugins.upr.ai.assignment_review import list_available_emergencies

        def fake_fetch(country_iso=None, config=None):
            return []

        item = self._matrix_item({
            "columns": [
                {
                    "name": "EA1",
                    "header_type": "selectable",
                    "header_lookup_list_id": "emergency_operations",
                    "header_plugin_config": {
                        "emops_end_date_gt": "2023-12-31",
                        "emops_show_closed_operations": False,
                        "emops_operation_types": ["Emergency Appeal"],
                    },
                },
            ],
        })

        p1, p2, p3 = self._patch_lookup(fake_fetch)
        with p1, p2, p3:
            result = list_available_emergencies(item, aes=SimpleNamespace(id=1))

        assert result == []

    def test_selectable_header_without_own_config_falls_back_to_matrix_level(self):
        """A column with no header_plugin_config of its own uses the matrix-level
        plugin_config, same fallback order as the live "Selectable header" picker."""
        from plugins.upr.ai.assignment_review import list_available_emergencies

        def fake_fetch(country_iso=None, config=None):
            assert config.get("operation_types") == ["DREF"]
            return [{"id": "9", "code": "MDRYY009", "name": "Flood"}]

        item = self._matrix_item({
            "plugin_config": {"emops_operation_types": ["DREF"]},
            "columns": [
                {
                    "name": "EA3",
                    "header_type": "selectable",
                    "header_lookup_list_id": "emergency_operations",
                    # No header_plugin_config of its own.
                },
            ],
        })

        p1, p2, p3 = self._patch_lookup(fake_fetch)
        with p1, p2, p3:
            result = list_available_emergencies(item, aes=SimpleNamespace(id=1))

        assert [op["code"] for op in result] == ["MDRYY009"]

    def test_matrix_with_no_emops_source_returns_empty_without_fetching(self):
        """A matrix with plain static columns (no row-mode or selectable-header link
        to the emergency_operations list) must short-circuit to [] and never call the
        GO lookup at all."""
        from plugins.upr.ai.assignment_review import list_available_emergencies

        called = []

        def fake_fetch(country_iso=None, config=None):
            called.append(config)
            return [{"id": "1", "code": "SHOULD_NOT_APPEAR"}]

        item = self._matrix_item({"columns": [{"name": "SP1", "type": "number_whole"}]})

        p1, p2, p3 = self._patch_lookup(fake_fetch)
        with p1, p2, p3:
            result = list_available_emergencies(item, aes=SimpleNamespace(id=1))

        assert result == []
        assert called == []

    def test_same_emergency_available_via_two_columns_is_deduped(self):
        """Two EA columns whose filters both happen to surface the same appeal must
        not show up twice in the "available" list used for the highlight text."""
        from plugins.upr.ai.assignment_review import list_available_emergencies

        def fake_fetch(country_iso=None, config=None):
            return [{"id": "1", "code": "MDRGM017", "name": "Gambia - Population Movement"}]

        item = self._matrix_item({
            "columns": [
                {
                    "name": "EA1",
                    "header_type": "selectable",
                    "header_lookup_list_id": "emergency_operations",
                    "header_plugin_config": {"emops_operation_types": ["Emergency Appeal"]},
                },
                {
                    "name": "EA2",
                    "header_type": "selectable",
                    "header_lookup_list_id": "emergency_operations",
                    "header_plugin_config": {"emops_operation_types": ["Emergency Appeal", "DREF"]},
                },
            ],
        })

        p1, p2, p3 = self._patch_lookup(fake_fetch)
        with p1, p2, p3:
            result = list_available_emergencies(item, aes=SimpleNamespace(id=1))

        assert len(result) == 1
        assert result[0]["code"] == "MDRGM017"

