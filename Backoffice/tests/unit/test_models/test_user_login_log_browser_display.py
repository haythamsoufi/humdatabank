"""UserLoginLog browser_name / browser_version must handle multi-word product names."""

import pytest

from app.models.core import UserLoginLog


@pytest.mark.unit
def test_multi_word_app_name_not_split_as_version():
    log = UserLoginLog()
    log.browser = 'Humanitarian Databank App'
    assert log.browser_name == 'Humanitarian Databank App'
    assert log.browser_version is None


@pytest.mark.unit
def test_mobile_safari_splits_trailing_numeric_version():
    log = UserLoginLog()
    log.browser = 'Mobile Safari 17.2'
    assert log.browser_name == 'Mobile Safari'
    assert log.browser_version == '17.2'


@pytest.mark.unit
def test_single_word_browser_no_version():
    log = UserLoginLog()
    log.browser = 'Chrome'
    assert log.browser_name == 'Chrome'
    assert log.browser_version is None
