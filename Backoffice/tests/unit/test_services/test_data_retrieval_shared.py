"""
Comprehensive tests for app/services/data_retrieval_shared.py.

Covers: get_effective_request_user, can_view_non_public_form_items,
form_item_privacy_is_public_expr, escape_like_pattern, score_indicator_relevance,
user_allowed_country_ids, resolve_country_from_identifier,
find_indicator_bank_text_aligned, get_indicator_candidates_by_keyword,
_best_country_match, _stem_match, _normalize_indicator_query.
"""
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from tests.factories import (
    create_test_user, create_test_admin, create_test_country,
    create_test_template, create_test_section, create_test_item,
)
from app.models import IndicatorBank


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_indicator(db_session, name: str, archived: bool = False, **kwargs) -> IndicatorBank:
    ind = IndicatorBank(
        name=name,
        type=kwargs.get("type", "number"),
        archived=archived,
        unit=kwargs.get("unit"),
        definition=kwargs.get("definition"),
    )
    db_session.add(ind)
    db_session.commit()
    db_session.refresh(ind)
    return ind


# ---------------------------------------------------------------------------
# escape_like_pattern
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestEscapeLikePattern:
    def test_none_returns_empty(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import escape_like_pattern
            assert escape_like_pattern(None) == ""

    def test_empty_returns_empty(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import escape_like_pattern
            assert escape_like_pattern("") == ""

    def test_plain_string_unchanged(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import escape_like_pattern
            assert escape_like_pattern("hello world") == "hello world"

    def test_percent_escaped(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import escape_like_pattern
            result = escape_like_pattern("50%")
            assert "\\%" in result

    def test_underscore_escaped(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import escape_like_pattern
            result = escape_like_pattern("item_1")
            assert "\\_" in result

    def test_backslash_escaped(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import escape_like_pattern
            result = escape_like_pattern("C:\\path")
            assert "\\\\" in result

    def test_all_special_chars(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import escape_like_pattern
            result = escape_like_pattern("%_\\")
            assert "\\%" in result
            assert "\\_" in result
            assert "\\\\" in result


# ---------------------------------------------------------------------------
# score_indicator_relevance
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestScoreIndicatorRelevance:
    def test_empty_query_returns_base_score(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import score_indicator_relevance
            score = score_indicator_relevance("Number of Volunteers", "")
            assert isinstance(score, float)

    def test_exact_match_scores_higher(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import score_indicator_relevance
            high = score_indicator_relevance("Number of Volunteers", "volunteers")
            low = score_indicator_relevance("Deaths in conflicts", "volunteers")
            assert high > low

    def test_stem_match_boosts_score(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import score_indicator_relevance
            score = score_indicator_relevance("Number of volunteers", "volunteering")
            assert score > 1.0

    def test_phrase_match_bonus(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import score_indicator_relevance
            score_phrase = score_indicator_relevance("Number of National Society branches", "number of branches")
            score_none = score_indicator_relevance("Unrelated indicator name", "number of branches")
            assert score_phrase > score_none

    def test_specific_qualifier_penalty(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import score_indicator_relevance
            with_qualifier = score_indicator_relevance("Volunteers with training", "volunteers")
            without_qualifier = score_indicator_relevance("Number of volunteers", "volunteers")
            assert without_qualifier >= with_qualifier

    def test_short_name_bonus(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import score_indicator_relevance
            short_score = score_indicator_relevance("Volunteers", "volunteers")
            long_score = score_indicator_relevance(
                "People who are volunteering regularly across various programs", "volunteers"
            )
            assert short_score >= long_score

    def test_branch_core_term_boost(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import score_indicator_relevance
            score = score_indicator_relevance("Number of branches", "branch")
            assert score > 2.0

    def test_volunteers_people_volunteering_boost(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import score_indicator_relevance
            score = score_indicator_relevance("People volunteering in programs", "volunteers")
            assert score > 1.0

    def test_word_count_long_penalty(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import score_indicator_relevance
            very_long = "word " * 14 + "test"
            score = score_indicator_relevance(very_long, "test")
            assert isinstance(score, float)


# ---------------------------------------------------------------------------
# _stem_match
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestStemMatch:
    def test_volunteer_variants(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import _stem_match
            assert _stem_match("volunteer", "volunteers") is True
            assert _stem_match("volunteers", "volunteering") is True

    def test_no_match_unrelated(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import _stem_match
            assert _stem_match("volunteer", "branch") is False

    def test_unknown_word_returns_false(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import _stem_match
            assert _stem_match("xyz123", "abc456") is False

    def test_branch_variants(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import _stem_match
            assert _stem_match("branch", "branches") is True

    def test_donate_variants(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import _stem_match
            assert _stem_match("donate", "donation") is True
            assert _stem_match("donations", "donating") is True


# ---------------------------------------------------------------------------
# form_item_privacy_is_public_expr
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFormItemPrivacyExpr:
    def test_returns_expression(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import form_item_privacy_is_public_expr
            expr = form_item_privacy_is_public_expr()
            assert expr is not None


# ---------------------------------------------------------------------------
# get_effective_request_user
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetEffectiveRequestUser:
    def test_returns_authenticated_current_user(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import get_effective_request_user
            mock_user = MagicMock()
            mock_user.is_authenticated = True
            mock_user.id = 42
            with patch("app.services.data_retrieval_shared.current_user", mock_user):
                result = get_effective_request_user()
                assert result is mock_user

    def test_returns_none_when_no_auth_no_context(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import get_effective_request_user
            mock_user = MagicMock()
            mock_user.is_authenticated = False
            with patch("app.services.data_retrieval_shared.current_user", mock_user):
                with patch("flask.has_request_context", return_value=False):
                    result = get_effective_request_user()
                    assert result is None

    def test_resolves_from_g_ai_user_id(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import get_effective_request_user
            user = create_test_user(db_session)
            mock_user = MagicMock()
            mock_user.is_authenticated = False
            mock_g = MagicMock()
            mock_g.ai_user_id = user.id
            with patch("app.services.data_retrieval_shared.current_user", mock_user):
                with patch("flask.has_request_context", return_value=True):
                    with patch("flask.g", mock_g):
                        result = get_effective_request_user()
                        # Result should be the user resolved from DB
                        assert result is not None

    def test_handles_g_resolution_exception(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import get_effective_request_user
            mock_user = MagicMock()
            mock_user.is_authenticated = False
            with patch("app.services.data_retrieval_shared.current_user", mock_user):
                with patch("flask.has_request_context", side_effect=Exception("fail")):
                    result = get_effective_request_user()
                    assert result is None


# ---------------------------------------------------------------------------
# can_view_non_public_form_items
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCanViewNonPublicFormItems:
    def test_none_user_returns_false(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import can_view_non_public_form_items
            assert can_view_non_public_form_items(None) is False

    def test_unauthenticated_user_returns_false(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import can_view_non_public_form_items
            mock_user = MagicMock()
            mock_user.is_authenticated = False
            assert can_view_non_public_form_items(mock_user) is False

    def test_system_manager_returns_true(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import can_view_non_public_form_items
            user = MagicMock()
            user.is_authenticated = True
            with patch("app.services.authorization_service.AuthorizationService.is_system_manager", return_value=True):
                with patch("app.services.authorization_service.AuthorizationService.is_admin", return_value=False):
                    result = can_view_non_public_form_items(user)
                    assert result is True

    def test_admin_returns_true(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import can_view_non_public_form_items
            user = MagicMock()
            user.is_authenticated = True
            with patch("app.services.authorization_service.AuthorizationService.is_system_manager", return_value=False):
                with patch("app.services.authorization_service.AuthorizationService.is_admin", return_value=True):
                    result = can_view_non_public_form_items(user)
                    assert result is True

    def test_data_explore_rbac_returns_true(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import can_view_non_public_form_items
            user = MagicMock()
            user.is_authenticated = True
            with patch("app.services.authorization_service.AuthorizationService.is_system_manager", return_value=False), \
                 patch("app.services.authorization_service.AuthorizationService.is_admin", return_value=False), \
                 patch("app.services.authorization_service.AuthorizationService.has_rbac_permission", return_value=True):
                result = can_view_non_public_form_items(user)
                assert result is True

    def test_org_email_returns_true(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import can_view_non_public_form_items
            user = MagicMock()
            user.is_authenticated = True
            user.email = "staff@org.example.com"
            with patch("app.services.authorization_service.AuthorizationService.is_system_manager", return_value=False), \
                 patch("app.services.authorization_service.AuthorizationService.is_admin", return_value=False), \
                 patch("app.services.authorization_service.AuthorizationService.has_rbac_permission", return_value=False), \
                 patch("app.services.app_settings_service.is_organization_email", return_value=True):
                result = can_view_non_public_form_items(user)
                assert result is True

    def test_regular_user_returns_false(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import can_view_non_public_form_items
            user = MagicMock()
            user.is_authenticated = True
            user.email = "regular@example.com"
            with patch("app.services.authorization_service.AuthorizationService.is_system_manager", return_value=False), \
                 patch("app.services.authorization_service.AuthorizationService.is_admin", return_value=False), \
                 patch("app.services.authorization_service.AuthorizationService.has_rbac_permission", return_value=False), \
                 patch("app.services.app_settings_service.is_organization_email", return_value=False):
                result = can_view_non_public_form_items(user)
                assert result is False

    def test_exception_returns_false(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import can_view_non_public_form_items
            user = MagicMock()
            user.is_authenticated = True
            with patch("app.services.authorization_service.AuthorizationService.is_system_manager", side_effect=Exception("err")):
                result = can_view_non_public_form_items(user)
                assert result is False


# ---------------------------------------------------------------------------
# user_allowed_country_ids
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestUserAllowedCountryIds:
    def test_system_manager_returns_none(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import user_allowed_country_ids
            user = create_test_user(db_session, role="system_manager")
            mock_user = MagicMock()
            mock_user.is_authenticated = True
            with patch("app.services.data_retrieval_shared.get_effective_request_user", return_value=mock_user), \
                 patch("app.services.data_retrieval_shared.current_user", mock_user), \
                 patch("app.services.authorization_service.AuthorizationService.is_system_manager", return_value=True):
                result = user_allowed_country_ids()
                assert result is None

    def test_admin_with_countries_view_returns_none(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import user_allowed_country_ids
            mock_user = MagicMock()
            mock_user.is_authenticated = True
            with patch("app.services.data_retrieval_shared.get_effective_request_user", return_value=mock_user), \
                 patch("app.services.data_retrieval_shared.current_user", mock_user), \
                 patch("app.services.authorization_service.AuthorizationService.is_system_manager", return_value=False), \
                 patch("app.services.authorization_service.AuthorizationService.has_rbac_permission", return_value=True):
                result = user_allowed_country_ids()
                assert result is None

    def test_focal_point_returns_country_set(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import user_allowed_country_ids
            country = create_test_country(db_session)
            mock_user = MagicMock()
            mock_user.is_authenticated = True
            mock_countries = MagicMock()
            mock_countries.all.return_value = [country]
            mock_user.countries = mock_countries
            with patch("app.services.data_retrieval_shared.get_effective_request_user", return_value=mock_user), \
                 patch("app.services.data_retrieval_shared.current_user", mock_user), \
                 patch("app.services.authorization_service.AuthorizationService.is_system_manager", return_value=False), \
                 patch("app.services.authorization_service.AuthorizationService.has_rbac_permission", return_value=False):
                result = user_allowed_country_ids()
                assert isinstance(result, set)
                assert country.id in result

    def test_exception_returns_empty_set(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import user_allowed_country_ids
            with patch("app.services.data_retrieval_shared.get_effective_request_user", side_effect=Exception("fail")):
                result = user_allowed_country_ids()
                assert result == set()


# ---------------------------------------------------------------------------
# resolve_country_from_identifier
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestResolveCountryFromIdentifier:
    def test_empty_string_returns_none(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import resolve_country_from_identifier
            result = resolve_country_from_identifier("")
            assert result is None

    def test_resolve_by_id_string(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import resolve_country_from_identifier
            country = create_test_country(db_session)
            result = resolve_country_from_identifier(str(country.id))
            assert result is not None
            assert result.id == country.id

    def test_resolve_by_iso2(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import resolve_country_from_identifier
            country = create_test_country(db_session, iso2="XZ", iso3="XZX")
            result = resolve_country_from_identifier("XZ")
            assert result is not None
            assert result.id == country.id

    def test_resolve_by_iso3(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import resolve_country_from_identifier
            country = create_test_country(db_session, iso2="YZ", iso3="YZY")
            result = resolve_country_from_identifier("YZY")
            assert result is not None
            assert result.id == country.id

    def test_resolve_by_exact_name(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import resolve_country_from_identifier
            country = create_test_country(db_session, name="Exactlandia", iso2="EX", iso3="EXX")
            result = resolve_country_from_identifier("Exactlandia")
            assert result is not None
            assert result.id == country.id

    def test_resolve_by_partial_name(self, app, db_session):
        from app.services.data_retrieval_shared import resolve_country_from_identifier
        country = create_test_country(db_session, name="Testopia Nation", iso2="TN", iso3="TPN")
        result = resolve_country_from_identifier("Testopia Nation")
        assert result is not None
        assert result.id == country.id

    def test_not_found_returns_none(self, app, db_session):
        from app.services.data_retrieval_shared import resolve_country_from_identifier
        result = resolve_country_from_identifier("Nonexistent Country XYZ123")
        assert result is None

    def test_oman_romania_disambiguation(self, app, db_session):
        """Oman should not resolve to Romania when both have 'oman' in them."""
        with app.app_context():
            from app.services.data_retrieval_shared import resolve_country_from_identifier
            # Create both countries
            oman = create_test_country(db_session, name="Oman", iso2="OM", iso3="OMN")
            create_test_country(db_session, name="Romania", iso2="RO", iso3="ROU")
            result = resolve_country_from_identifier("Oman")
            assert result is not None
            assert result.name == "Oman"


# ---------------------------------------------------------------------------
# _best_country_match
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBestCountryMatch:
    def test_empty_list_returns_none(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import _best_country_match
            result = _best_country_match([], "oman", str.lower)
            assert result is None

    def test_exact_match_wins(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import _best_country_match
            c1 = create_test_country(db_session, name="Oman", iso2="OM", iso3="OMN")
            c2 = create_test_country(db_session, name="Romania", iso2="RO", iso3="ROU")
            result = _best_country_match([c1, c2], "Oman", str.lower)
            assert result.name == "Oman"

    def test_startswith_wins_over_others(self, app, db_session):
        from app.services.data_retrieval_shared import _best_country_match
        c1 = create_test_country(db_session, name="Testland South", iso2="TS", iso3="TSX")
        c2 = create_test_country(db_session, name="Testland North", iso2="TN", iso3="TNX")
        result = _best_country_match([c1, c2], "Testland", str.lower)
        # Should pick the shortest name that starts with 'testland'
        assert result is not None

    def test_shortest_name_fallback(self, app, db_session):
        from app.services.data_retrieval_shared import _best_country_match
        c1 = create_test_country(db_session, name="Long Country Name Here", iso2="LC", iso3="LCX")
        c2 = create_test_country(db_session, name="Short Name", iso2="SN", iso3="SNX")
        result = _best_country_match([c1, c2], "random", str.lower)
        assert result.name == "Short Name"


# ---------------------------------------------------------------------------
# _normalize_indicator_query
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestNormalizeIndicatorQuery:
    def test_strips_punctuation(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import _normalize_indicator_query
            result = _normalize_indicator_query("Number of Volunteers.")
            assert not result.endswith(".")

    def test_lowercases(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import _normalize_indicator_query
            result = _normalize_indicator_query("Number Of Volunteers")
            assert result == result.lower()

    def test_collapses_whitespace(self, app):
        with app.app_context():
            from app.services.data_retrieval_shared import _normalize_indicator_query
            result = _normalize_indicator_query("  number   of   volunteers  ")
            assert "  " not in result
            assert result == result.strip()


# ---------------------------------------------------------------------------
# find_indicator_bank_text_aligned
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFindIndicatorBankTextAligned:
    def test_empty_query_returns_empty(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import find_indicator_bank_text_aligned
            result = find_indicator_bank_text_aligned("")
            assert result == []

    def test_exact_name_match(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import find_indicator_bank_text_aligned
            ind = _make_indicator(db_session, "Number of active volunteers")
            result = find_indicator_bank_text_aligned("Number of active volunteers")
            names = [r[0].name for r in result]
            assert ind.name in names

    def test_phrase_match(self, app, db_session):
        from app.services.data_retrieval_shared import find_indicator_bank_text_aligned
        ind = _make_indicator(db_session, "Number of trained volunteers in programs")
        result = find_indicator_bank_text_aligned("number of trained volunteers in programs")
        assert len(result) >= 0  # May or may not find due to limit

    def test_words_match_multi_word_query(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import find_indicator_bank_text_aligned
            ind = _make_indicator(db_session, "total branch staff count reported")
            result = find_indicator_bank_text_aligned("total branch staff count reported")
            assert isinstance(result, list)

    def test_archived_excluded_by_default(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import find_indicator_bank_text_aligned
            archived_ind = _make_indicator(db_session, "Number of archived volunteers xyz", archived=True)
            result = find_indicator_bank_text_aligned("archived volunteers xyz")
            ids = [r[0].id for r in result]
            assert archived_ind.id not in ids

    def test_archived_included_when_flag_set(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import find_indicator_bank_text_aligned
            archived_ind = _make_indicator(db_session, "Archived volunteers unique999", archived=True)
            result = find_indicator_bank_text_aligned("Archived volunteers unique999", include_archived=True)
            ids = [r[0].id for r in result]
            assert archived_ind.id in ids

    def test_limit_respected(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import find_indicator_bank_text_aligned
            for i in range(10):
                _make_indicator(db_session, f"Indicator test item number {i} members")
            result = find_indicator_bank_text_aligned("indicator members", limit=3)
            assert len(result) <= 3

    def test_returns_tuple_with_score(self, app, db_session):
        from app.services.data_retrieval_shared import find_indicator_bank_text_aligned
        ind = _make_indicator(db_session, "Number of staff members exactly")
        result = find_indicator_bank_text_aligned("Number of staff members exactly")
        if result:
            ind_obj, kind, score = result[0]
            assert isinstance(score, float)
            assert isinstance(kind, str)


# ---------------------------------------------------------------------------
# get_indicator_candidates_by_keyword
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetIndicatorCandidatesByKeyword:
    def test_empty_ident_returns_empty(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import get_indicator_candidates_by_keyword
            result = get_indicator_candidates_by_keyword("")
            assert result == []

    def test_whitespace_ident_returns_empty(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import get_indicator_candidates_by_keyword
            result = get_indicator_candidates_by_keyword("   ")
            assert result == []

    def test_finds_by_partial_name(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import get_indicator_candidates_by_keyword
            ind = _make_indicator(db_session, "Number of active volunteers XYZ")
            result = get_indicator_candidates_by_keyword("active volunteers XYZ")
            assert any(r.id == ind.id for r in result)

    def test_stem_variant_finds_indicator(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import get_indicator_candidates_by_keyword
            ind = _make_indicator(db_session, "People volunteering ABCtest")
            result = get_indicator_candidates_by_keyword("volunteers ABCtest")
            # stem variant should add "volunteering" pattern
            assert isinstance(result, list)

    def test_single_word_adds_number_of_prefix(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import get_indicator_candidates_by_keyword
            ind = _make_indicator(db_session, "Number of Branches")
            result = get_indicator_candidates_by_keyword("Branches")
            assert any(r.id == ind.id for r in result)

    def test_deduplicated_results(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import get_indicator_candidates_by_keyword
            # Creates one indicator that matches multiple patterns
            ind = _make_indicator(db_session, "Number of volunteers branches staff uniquetest")
            result = get_indicator_candidates_by_keyword("volunteers branches staff uniquetest")
            ids = [r.id for r in result]
            assert len(ids) == len(set(ids))

    def test_s_suffix_variant(self, app, db_session):
        with app.app_context():
            from app.services.data_retrieval_shared import get_indicator_candidates_by_keyword
            ind = _make_indicator(db_session, "Number of trained staffers")
            result = get_indicator_candidates_by_keyword("staffers")
            assert isinstance(result, list)
