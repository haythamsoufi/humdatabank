"""
Unit tests for app/utils/language_flags.py

Covers: normalize_language_code, _extract_region, _likely_region_from_babel,
        language_to_country_flag_code, country_code_to_flag_emoji,
        country_code_to_twemoji_svg_url, language_flag_emoji,
        language_flag_twemoji_svg_url, prefetch_language_flags_to_local_cache
"""
import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
class TestNormalizeLanguageCode:
    def test_simple_code(self):
        from app.utils.language_flags import normalize_language_code
        assert normalize_language_code("en") == "en"

    def test_locale_with_dash(self):
        from app.utils.language_flags import normalize_language_code
        assert normalize_language_code("en-US") == "en"

    def test_locale_with_underscore(self):
        from app.utils.language_flags import normalize_language_code
        assert normalize_language_code("fr_FR") == "fr"

    def test_uppercase_lowercased(self):
        from app.utils.language_flags import normalize_language_code
        assert normalize_language_code("FR") == "fr"

    def test_empty_string(self):
        from app.utils.language_flags import normalize_language_code
        assert normalize_language_code("") == ""

    def test_none_handled(self):
        from app.utils.language_flags import normalize_language_code
        assert normalize_language_code(None) == ""

    def test_whitespace_stripped(self):
        from app.utils.language_flags import normalize_language_code
        assert normalize_language_code("  en  ") == "en"

    def test_three_part_locale(self):
        from app.utils.language_flags import normalize_language_code
        assert normalize_language_code("zh_Hans_CN") == "zh"


@pytest.mark.unit
class TestExtractRegion:
    def test_with_alpha2_region(self):
        from app.utils.language_flags import _extract_region
        assert _extract_region("fr_FR") == "FR"

    def test_with_dash_separator(self):
        from app.utils.language_flags import _extract_region
        assert _extract_region("pt-BR") == "BR"

    def test_no_region(self):
        from app.utils.language_flags import _extract_region
        assert _extract_region("fr") == ""

    def test_empty_string(self):
        from app.utils.language_flags import _extract_region
        assert _extract_region("") == ""

    def test_none_handled(self):
        from app.utils.language_flags import _extract_region
        assert _extract_region(None) == ""

    def test_three_letter_region_ignored(self):
        from app.utils.language_flags import _extract_region
        assert _extract_region("zh_CHN") == ""

    def test_numeric_region_ignored(self):
        from app.utils.language_flags import _extract_region
        assert _extract_region("es_419") == ""

    def test_region_uppercased(self):
        from app.utils.language_flags import _extract_region
        assert _extract_region("en_gb") == "GB"


@pytest.mark.unit
class TestLikelyRegionFromBabel:
    def test_returns_string(self):
        from app.utils.language_flags import _likely_region_from_babel
        result = _likely_region_from_babel("en")
        assert isinstance(result, str)

    def test_empty_language_returns_empty(self):
        from app.utils.language_flags import _likely_region_from_babel
        assert _likely_region_from_babel("") == ""

    def test_exception_suppressed_returns_empty(self):
        from app.utils.language_flags import _likely_region_from_babel
        # get_global is imported locally inside the function; patch at babel.core level
        with patch("babel.core.get_global", side_effect=Exception("babel error")):
            result = _likely_region_from_babel("en")
            assert result == ""

    def test_no_likely_subtag_returns_empty(self):
        from app.utils.language_flags import _likely_region_from_babel
        with patch("babel.core.get_global", return_value={}):
            result = _likely_region_from_babel("xyz_fake")
            assert result == ""

    def test_likely_subtag_extracts_region(self):
        from app.utils.language_flags import _likely_region_from_babel
        # _extract_region only handles 2-part locales (lang_REGION), so use "sq_AL"
        with patch("babel.core.get_global", return_value={"sq": "sq_AL"}):
            result = _likely_region_from_babel("sq")
            assert result == "AL"


@pytest.mark.unit
class TestLanguageToCountryFlagCode:
    def test_en_maps_to_gb(self):
        from app.utils.language_flags import language_to_country_flag_code
        assert language_to_country_flag_code("en") == "gb"

    def test_ar_maps_to_sa(self):
        from app.utils.language_flags import language_to_country_flag_code
        assert language_to_country_flag_code("ar") == "sa"

    def test_zh_maps_to_cn(self):
        from app.utils.language_flags import language_to_country_flag_code
        assert language_to_country_flag_code("zh") == "cn"

    def test_uk_maps_to_ua_not_gb(self):
        from app.utils.language_flags import language_to_country_flag_code
        assert language_to_country_flag_code("uk") == "ua"

    def test_locale_with_region_uses_region(self):
        from app.utils.language_flags import language_to_country_flag_code
        assert language_to_country_flag_code("pt_BR") == "br"

    def test_empty_returns_none(self):
        from app.utils.language_flags import language_to_country_flag_code
        assert language_to_country_flag_code("") is None

    def test_none_returns_none(self):
        from app.utils.language_flags import language_to_country_flag_code
        assert language_to_country_flag_code(None) is None

    def test_whitespace_only_returns_none(self):
        from app.utils.language_flags import language_to_country_flag_code
        assert language_to_country_flag_code("   ") is None

    def test_two_letter_heuristic_fallback(self):
        from app.utils.language_flags import language_to_country_flag_code, LANGUAGE_TO_COUNTRY_FLAG
        # "de" is not explicitly in all override entries but babel likely subtags
        # or 2-letter heuristic should give a result
        result = language_to_country_flag_code("de")
        assert result is not None
        assert len(result) == 2

    def test_three_letter_code_returns_none_when_no_babel_data(self):
        from app.utils.language_flags import language_to_country_flag_code
        with patch("app.utils.language_flags._likely_region_from_babel", return_value=""):
            result = language_to_country_flag_code("zzz")
            assert result is None

    def test_babel_likely_region_used_as_fallback(self):
        from app.utils.language_flags import language_to_country_flag_code, LANGUAGE_TO_COUNTRY_FLAG
        # Use a code definitely not in LANGUAGE_TO_COUNTRY_FLAG
        code = "xx"
        if code not in LANGUAGE_TO_COUNTRY_FLAG:
            with patch("app.utils.language_flags._likely_region_from_babel", return_value="XY"):
                result = language_to_country_flag_code(code)
                assert result == "xy"

    def test_all_override_entries_are_two_letter_codes(self):
        from app.utils.language_flags import LANGUAGE_TO_COUNTRY_FLAG
        for lang, cc in LANGUAGE_TO_COUNTRY_FLAG.items():
            assert len(cc) == 2, f"Expected 2-letter code for {lang}, got {cc!r}"


@pytest.mark.unit
class TestCountryCodeToFlagEmoji:
    def test_us_flag(self):
        from app.utils.language_flags import country_code_to_flag_emoji
        result = country_code_to_flag_emoji("US")
        assert result is not None
        # Flag emoji = two regional indicator symbols (each is a surrogate pair)
        assert len(result) == 2

    def test_gb_flag(self):
        from app.utils.language_flags import country_code_to_flag_emoji
        result = country_code_to_flag_emoji("GB")
        assert result is not None

    def test_lowercase_code_works(self):
        from app.utils.language_flags import country_code_to_flag_emoji
        result = country_code_to_flag_emoji("us")
        assert result is not None

    def test_three_letter_returns_none(self):
        from app.utils.language_flags import country_code_to_flag_emoji
        assert country_code_to_flag_emoji("USA") is None

    def test_one_letter_returns_none(self):
        from app.utils.language_flags import country_code_to_flag_emoji
        assert country_code_to_flag_emoji("U") is None

    def test_empty_returns_none(self):
        from app.utils.language_flags import country_code_to_flag_emoji
        assert country_code_to_flag_emoji("") is None

    def test_none_returns_none(self):
        from app.utils.language_flags import country_code_to_flag_emoji
        assert country_code_to_flag_emoji(None) is None

    def test_non_alpha_returns_none(self):
        from app.utils.language_flags import country_code_to_flag_emoji
        assert country_code_to_flag_emoji("1A") is None

    def test_regional_indicator_codepoints(self):
        from app.utils.language_flags import country_code_to_flag_emoji
        result = country_code_to_flag_emoji("US")
        base = 0x1F1E6
        expected = (
            chr(base + ord("U") - ord("A")) + chr(base + ord("S") - ord("A"))
        )
        assert result == expected


@pytest.mark.unit
class TestCountryCodeToTwemojiSvgUrl:
    def test_us_url(self):
        from app.utils.language_flags import country_code_to_twemoji_svg_url
        result = country_code_to_twemoji_svg_url("US")
        assert result is not None
        assert result.endswith(".svg")

    def test_gb_url(self):
        from app.utils.language_flags import country_code_to_twemoji_svg_url
        result = country_code_to_twemoji_svg_url("GB")
        assert result is not None
        assert "cdnjs.cloudflare.com" in result

    def test_empty_returns_none(self):
        from app.utils.language_flags import country_code_to_twemoji_svg_url
        assert country_code_to_twemoji_svg_url("") is None

    def test_three_letter_returns_none(self):
        from app.utils.language_flags import country_code_to_twemoji_svg_url
        assert country_code_to_twemoji_svg_url("USA") is None

    def test_none_returns_none(self):
        from app.utils.language_flags import country_code_to_twemoji_svg_url
        assert country_code_to_twemoji_svg_url(None) is None

    def test_url_contains_hex_codepoints(self):
        from app.utils.language_flags import country_code_to_twemoji_svg_url
        result = country_code_to_twemoji_svg_url("US")
        # US -> U(0x55) -> 0x1F1FA, S(0x53) -> 0x1F1F8
        assert "1f1fa-1f1f8" in result


@pytest.mark.unit
class TestLanguageFlagEmoji:
    def test_known_language_returns_flag(self):
        from app.utils.language_flags import language_flag_emoji
        result = language_flag_emoji("en")
        assert result != "🏳️"
        assert len(result) == 2

    def test_unknown_code_returns_white_flag(self):
        from app.utils.language_flags import language_flag_emoji
        with patch("app.utils.language_flags.language_to_country_flag_code", return_value=None):
            result = language_flag_emoji("xyz")
            assert result == "🏳️"

    def test_cc_with_no_emoji_returns_white_flag(self):
        from app.utils.language_flags import language_flag_emoji
        with patch("app.utils.language_flags.language_to_country_flag_code", return_value="xx"):
            with patch("app.utils.language_flags.country_code_to_flag_emoji", return_value=None):
                result = language_flag_emoji("xx")
                assert result == "🏳️"

    def test_arabic_returns_flag(self):
        from app.utils.language_flags import language_flag_emoji
        result = language_flag_emoji("ar")
        assert result != "🏳️"


@pytest.mark.unit
class TestLanguageFlagTwemojiSvgUrl:
    def test_known_code_returns_url(self):
        from app.utils.language_flags import language_flag_twemoji_svg_url
        result = language_flag_twemoji_svg_url("en")
        assert result is not None
        assert result.endswith(".svg")

    def test_unknown_code_returns_none(self):
        from app.utils.language_flags import language_flag_twemoji_svg_url
        with patch("app.utils.language_flags.language_to_country_flag_code", return_value=None):
            result = language_flag_twemoji_svg_url("xyz")
            assert result is None

    def test_url_contains_expected_path(self):
        from app.utils.language_flags import language_flag_twemoji_svg_url
        result = language_flag_twemoji_svg_url("ar")
        assert result is not None
        assert "cdnjs.cloudflare.com" in result


@pytest.mark.unit
class TestPrefetchLanguageFlagsToLocalCache:
    def test_successful_download(self):
        from app.utils.language_flags import prefetch_language_flags_to_local_cache
        with tempfile.TemporaryDirectory() as tmp:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = lambda s: s
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_ctx.read.return_value = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'
            with patch("app.utils.language_flags.urlopen", return_value=mock_ctx):
                result = prefetch_language_flags_to_local_cache(["en"], instance_path=tmp)
            assert result["cache_dir"].endswith("flag_cache")
            assert result["requested_languages"] == ["en"]
            assert "gb" in result["downloaded"] or "gb" in result["skipped_existing"]

    def test_skips_existing_file(self):
        from app.utils.language_flags import prefetch_language_flags_to_local_cache
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = os.path.join(tmp, "flag_cache")
            os.makedirs(cache_dir)
            with open(os.path.join(cache_dir, "gb.svg"), "w") as f:
                f.write("<svg/>")
            result = prefetch_language_flags_to_local_cache(["en"], instance_path=tmp)
            assert "gb" in result["skipped_existing"]

    def test_download_failure_recorded_in_failed(self):
        from app.utils.language_flags import prefetch_language_flags_to_local_cache
        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.utils.language_flags.urlopen", side_effect=Exception("Network error")):
                result = prefetch_language_flags_to_local_cache(["en"], instance_path=tmp)
            assert any(f["cc"] == "gb" for f in result["failed"])

    def test_invalid_svg_response_goes_to_failed(self):
        from app.utils.language_flags import prefetch_language_flags_to_local_cache
        with tempfile.TemporaryDirectory() as tmp:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = lambda s: s
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_ctx.read.return_value = b"<html>Not Found</html>"
            with patch("app.utils.language_flags.urlopen", return_value=mock_ctx):
                result = prefetch_language_flags_to_local_cache(["en"], instance_path=tmp)
            assert len(result["failed"]) > 0

    def test_empty_language_list(self):
        from app.utils.language_flags import prefetch_language_flags_to_local_cache
        with tempfile.TemporaryDirectory() as tmp:
            result = prefetch_language_flags_to_local_cache([], instance_path=tmp)
            assert result["requested_languages"] == []
            assert result["country_codes"] == []
            assert result["downloaded"] == []

    def test_unknown_language_no_cc_skipped_silently(self):
        from app.utils.language_flags import prefetch_language_flags_to_local_cache
        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.utils.language_flags.language_to_country_flag_code", return_value=None):
                result = prefetch_language_flags_to_local_cache(["zz"], instance_path=tmp)
            assert result["country_codes"] == []

    def test_deduplicates_country_codes(self):
        from app.utils.language_flags import prefetch_language_flags_to_local_cache
        with tempfile.TemporaryDirectory() as tmp:
            # Both "ta" and "pa" map to "in" – should only download once
            with patch("app.utils.language_flags.language_to_country_flag_code", side_effect=lambda c: "in"):
                with patch("app.utils.language_flags.urlopen", side_effect=Exception("no net")):
                    result = prefetch_language_flags_to_local_cache(["ta", "pa"], instance_path=tmp)
            assert result["country_codes"] == ["in"]

    def test_results_keys_present(self):
        from app.utils.language_flags import prefetch_language_flags_to_local_cache
        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.utils.language_flags.urlopen", side_effect=Exception("no net")):
                result = prefetch_language_flags_to_local_cache(["fr"], instance_path=tmp)
            for key in ("cache_dir", "requested_languages", "country_codes", "downloaded", "skipped_existing", "failed"):
                assert key in result
