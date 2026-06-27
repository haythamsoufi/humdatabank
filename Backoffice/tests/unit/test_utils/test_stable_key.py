"""Tests for stable_key utilities."""

import pytest

from app.utils.stable_key import generate_stable_key, is_valid_stable_key, normalize_stable_key
from tests.factories import create_test_item, create_test_section, create_test_template


pytestmark = pytest.mark.unit


def test_generate_stable_key_is_valid_uuid():
    key = generate_stable_key()
    assert is_valid_stable_key(key)
    assert normalize_stable_key(key) == key


def test_normalize_stable_key_rejects_invalid():
    assert normalize_stable_key('not-a-uuid') is None
    assert normalize_stable_key('') is None
    assert normalize_stable_key(None) is None


def test_resolve_published_form_item_id(db_session, admin_user):
    from app.models import FormItem
    from app.utils.stable_key import generate_stable_key, resolve_published_form_item_id

    template = create_test_template(db_session, owner_id=admin_user.id)
    version = template.published_version
    section = create_test_section(db_session, template, version=version)
    key = generate_stable_key()
    item = create_test_item(db_session, section, template, version=version, item_type='question')
    item.stable_key = key
    db_session.commit()

    assert resolve_published_form_item_id(template.id, key) == item.id
    assert resolve_published_form_item_id(template.id, 'bad-key') is None


def test_resolve_form_item_refs(db_session, admin_user):
    from app.utils.stable_key import generate_stable_key, resolve_form_item_refs

    template = create_test_template(db_session, owner_id=admin_user.id)
    version = template.published_version
    section = create_test_section(db_session, template, version=version)
    key = generate_stable_key()
    item = create_test_item(db_session, section, template, version=version, item_type='question')
    item.stable_key = key
    db_session.commit()

    resolved, errors = resolve_form_item_refs(
        [{'stable_key': key, 'value': '42'}],
        template.id,
    )
    assert not errors
    assert resolved[0]['form_item_id'] == item.id
