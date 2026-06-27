"""Unit tests for api_data_filters helpers."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.utils.api_data_filters import (
    VERSION_SCOPE_ALL,
    VERSION_SCOPE_PUBLISHED,
    apply_form_data_version_scoping,
    build_data_api_scope_meta,
    parse_data_item_filters,
    parse_version_scope,
    resolve_template_published_version_id,
)


@pytest.mark.unit
class TestParseVersionScope:
    def test_default_is_published(self):
        assert parse_version_scope({}) == VERSION_SCOPE_PUBLISHED

    def test_all(self):
        assert parse_version_scope({'version_scope': 'all'}) == VERSION_SCOPE_ALL

    def test_invalid_falls_back_to_published(self):
        assert parse_version_scope({'version_scope': 'draft'}) == VERSION_SCOPE_PUBLISHED


@pytest.mark.unit
class TestParseDataItemFilters:
    def test_invalid_stable_key_returns_error(self):
        _, _, scope, err = parse_data_item_filters(
            {'stable_key': 'not-a-uuid'},
            template_id=1,
            item_id=None,
        )
        assert scope == VERSION_SCOPE_PUBLISHED
        assert err['status'] == 400

    def test_stable_key_without_template_id_returns_error(self):
        key = str(uuid.uuid4())
        _, _, _, err = parse_data_item_filters(
            {'stable_key': key},
            template_id=None,
            item_id=None,
        )
        assert err['status'] == 400
        assert 'template_id' in err['message']

    @patch('app.utils.api_data_filters.resolve_published_form_item_id', return_value=42)
    def test_stable_key_resolves_to_published_item_id(self, _mock_resolve):
        key = str(uuid.uuid4())
        item_id, stable, scope, err = parse_data_item_filters(
            {'stable_key': key, 'version_scope': 'published'},
            template_id=7,
            item_id=None,
        )
        assert err is None
        assert item_id == 42
        assert stable == key
        assert scope == VERSION_SCOPE_PUBLISHED

    @patch('app.utils.api_data_filters.resolve_published_form_item_id', return_value=None)
    def test_unknown_stable_key_uses_sentinel_item_id(self, _mock_resolve):
        key = str(uuid.uuid4())
        item_id, stable, _, err = parse_data_item_filters(
            {'stable_key': key},
            template_id=7,
            item_id=None,
        )
        assert err is None
        assert item_id == -1
        assert stable == key

    def test_all_scope_keeps_stable_key_without_resolving_item_id(self):
        key = str(uuid.uuid4())
        item_id, stable, scope, err = parse_data_item_filters(
            {'stable_key': key, 'version_scope': 'all'},
            template_id=7,
            item_id=None,
        )
        assert err is None
        assert item_id is None
        assert stable == key
        assert scope == VERSION_SCOPE_ALL


@pytest.mark.unit
class TestApplyFormDataVersionScoping:
    def test_published_scope_filters_queries(self):
        assigned = MagicMock()
        public = MagicMock()
        filtered_assigned = MagicMock()
        filtered_public = MagicMock()
        assigned.filter.return_value = filtered_assigned
        public.filter.return_value = filtered_public

        out_a, out_p = apply_form_data_version_scoping(
            assigned,
            public,
            template_id=1,
            published_version_id=9,
            version_scope=VERSION_SCOPE_PUBLISHED,
        )
        assert out_a is filtered_assigned
        assert out_p is filtered_public
        assigned.filter.assert_called_once()
        public.filter.assert_called_once()

    def test_all_scope_without_stable_key_skips_filter(self):
        assigned = MagicMock()
        public = MagicMock()
        out_a, out_p = apply_form_data_version_scoping(
            assigned,
            public,
            template_id=1,
            published_version_id=9,
            version_scope=VERSION_SCOPE_ALL,
        )
        assert out_a is assigned
        assert out_p is public
        assigned.filter.assert_not_called()


@pytest.mark.unit
class TestBuildDataApiScopeMeta:
    def test_none_without_template_id(self):
        assert build_data_api_scope_meta(
            template_id=None,
            published_version_id=None,
            version_scope=VERSION_SCOPE_PUBLISHED,
        ) is None

    def test_includes_template_and_version_fields(self):
        key = str(uuid.uuid4())
        meta = build_data_api_scope_meta(
            template_id=3,
            published_version_id=11,
            version_scope=VERSION_SCOPE_PUBLISHED,
            stable_key=key,
        )
        assert meta == {
            'template_id': 3,
            'published_version_id': 11,
            'version_scope': 'published',
            'stable_key': key,
        }


@pytest.mark.unit
class TestResolveTemplatePublishedVersionId:
    @patch('app.utils.api_data_filters.db')
    def test_returns_published_version_id(self, mock_db):
        tmpl = MagicMock()
        tmpl.published_version_id = 55
        mock_db.session.get.return_value = tmpl
        assert resolve_template_published_version_id(1) == 55

    @patch('app.utils.api_data_filters.db')
    def test_missing_template_returns_none(self, mock_db):
        mock_db.session.get.return_value = None
        assert resolve_template_published_version_id(1) is None
