"""Bot UA heuristics: mobile/native clients must not be flagged as crawlers."""

import pytest

from app.services.user_analytics_service import analyze_ua_for_bot


@pytest.mark.unit
@pytest.mark.parametrize(
    'ua',
    [
        'Dart/3.5 (dart:io)',
        'okhttp/4.12.0',
        'MyApp/1.0 CFNetwork/1494.0.7 Darwin/24.2.0',
    ],
)
def test_native_mobile_user_agents_not_bots(ua):
    is_bot, reason = analyze_ua_for_bot(ua)
    assert is_bot is False
    assert reason is None


@pytest.mark.unit
def test_curl_still_flagged():
    is_bot, reason = analyze_ua_for_bot('curl/8.0.1')
    assert is_bot is True
    assert reason is not None


@pytest.mark.unit
def test_empty_ua_flagged():
    is_bot, _ = analyze_ua_for_bot('')
    assert is_bot is True


@pytest.mark.unit
def test_desktop_chrome_not_flagged():
    ua = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    is_bot, reason = analyze_ua_for_bot(ua)
    assert is_bot is False
    assert reason is None
