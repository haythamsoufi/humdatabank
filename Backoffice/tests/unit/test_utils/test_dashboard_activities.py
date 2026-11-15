"""JSON shape of dashboard recent activities."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit]


def _activity(**overrides):
    base = dict(
        id=5,
        user=SimpleNamespace(
            id=2,
            name='Ada Lovelace',
            email='ada@example.org',
            title='Focal point',
        ),
        timestamp=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        assignment_id=9,
        summary_key='activity.assignment_submitted',
        summary_params={
            'template': 'Plan',
            'assignment_title': 'Plan – 2026',
            'template_period': 'Plan – 2026',
        },
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_serialize_assignment_submitted_uses_assignment_title(app):
    from app.utils.organization.dashboard_activities import (
        serialize_dashboard_activity,
    )

    with app.test_request_context('/'):
        payload = serialize_dashboard_activity(_activity())

    assert payload['id'] == 5
    assert payload['assignment_id'] == 9
    assert payload['assignment_title'] == 'Plan – 2026'
    assert payload['template_period'] == 'Plan – 2026'
    assert payload['user']['name'] == 'Ada Lovelace'
    assert payload['user']['email'] == 'ada@example.org'
    assert payload['change_type'] is None
    assert payload['changes'] == []
    assert 'Plan – 2026' in payload['summary']
    assert payload['timestamp'].startswith('2026-03-01')


def test_serialize_single_field_change_is_plain_text(app):
    from app.utils.organization.dashboard_activities import (
        serialize_dashboard_activity,
    )

    activity = _activity(
        summary_key='activity.form_data_updated.single',
        summary_params={
            'change_type': 'updated',
            'field': 'People reached',
            'field_id': None,
            'old': '1',
            'new': '4',
            'assignment_title': 'Plan – 2026',
            'template_period': 'Plan – 2026',
        },
    )
    with app.test_request_context('/'):
        payload = serialize_dashboard_activity(activity)

    assert payload['change_type'] == 'updated'
    assert payload['summary'] == 'People reached: 1 → 4'
    assert '<' not in payload['summary']


def test_html_matrix_markup_becomes_plain_lines():
    from app.utils.organization.dashboard_activities import _html_to_text

    text = _html_to_text(
        "People reached:<br><span class='font-semibold'>Syria</span>:<br>"
        "SP1: 0 &rarr; 1<br>"
    )
    assert text == 'People reached:\nSyria:\nSP1: 0 → 1'


def test_no_country_returns_an_empty_page(app):
    from app.utils.organization.dashboard_activities import (
        load_dashboard_recent_activities,
    )

    with app.app_context(), patch(
        'app.services.organization.entity_service.EntityService.get_country_for_entity',
        return_value=None,
    ):
        activities, has_more = load_dashboard_recent_activities('country', 1)

    assert activities == []
    assert has_more is False
