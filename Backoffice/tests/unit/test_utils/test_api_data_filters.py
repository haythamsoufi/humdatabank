"""Unit tests for api_data_filters helpers."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.utils.api_data_filters import (
    VERSION_SCOPE_ALL,
    VERSION_SCOPE_PUBLISHED,
    apply_form_data_version_scoping,
    build_data_api_scope_meta,
    parse_assignment_id_filters,
    parse_data_item_filters,
    parse_version_scope,
    resolve_assignment_entity_status_fallback,
    resolve_assignment_scope,
    resolve_template_id_from_assignment_ids,
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
class TestParseAssignmentIdFilters:
    def test_single_assignment_id(self):
        assert parse_assignment_id_filters({'assignment_id': '123'}) == [123]

    def test_comma_separated_assignment_ids(self):
        assert parse_assignment_id_filters({'assignment_id': '123,456'}) == [123, 456]

    def test_legacy_assigned_form_id_alias(self):
        assert parse_assignment_id_filters({'assigned_form_id': '99'}) == [99]

    def test_repeated_query_params(self):
        args = {'assignment_id': ['10', '20']}
        assert parse_assignment_id_filters(args) == [10, 20]

    def test_empty_returns_none(self):
        assert parse_assignment_id_filters({}) is None


@pytest.mark.unit
class TestResolveAssignmentScope:
    def _row(self, row_id, template_id, template_name='Template'):
        row = MagicMock()
        row.id = row_id
        row.template_id = template_id
        template = MagicMock()
        template.name = template_name
        row.template = template
        return row

    @patch('app.utils.api_data_filters.joinedload')
    @patch('app.utils.api_data_filters.AssignedForm')
    def test_derives_template_when_all_match(self, mock_assigned_form, _mock_joinedload):
        mock_assigned_form.query.options.return_value.filter.return_value.all.return_value = [
            self._row(4, 33, 'Unified Country Report'),
            self._row(5, 33, 'Unified Country Report'),
        ]
        template_id, template_ids, error = resolve_assignment_scope([4, 5])
        assert error is None
        assert template_id == 33
        assert template_ids == [33]

    @patch('app.utils.api_data_filters.joinedload')
    @patch('app.utils.api_data_filters.AssignedForm')
    def test_allows_mixed_templates(self, mock_assigned_form, _mock_joinedload):
        mock_assigned_form.query.options.return_value.filter.return_value.all.return_value = [
            self._row(4, 33, 'Unified Country Report'),
            self._row(34, 23, 'Reporting - International Bilateral Support'),
        ]
        template_id, template_ids, error = resolve_assignment_scope([4, 34])
        assert error is None
        assert template_id is None
        assert template_ids == [23, 33]

    @patch('app.utils.api_data_filters.joinedload')
    @patch('app.utils.api_data_filters.AssignedForm')
    def test_validates_against_explicit_template_id(self, mock_assigned_form, _mock_joinedload):
        mock_assigned_form.query.options.return_value.filter.return_value.all.return_value = [
            self._row(34, 23, 'Reporting - International Bilateral Support'),
        ]
        template_id, template_ids, error = resolve_assignment_scope([34], template_id=33)
        assert template_id is None
        assert template_ids == [23]
        assert error['status'] == 400
        assert '34 → template 23' in error['message']

    @patch('app.utils.api_data_filters.joinedload')
    @patch('app.utils.api_data_filters.AssignedForm')
    def test_wrapper_returns_single_template_only(self, mock_assigned_form, _mock_joinedload):
        mock_assigned_form.query.options.return_value.filter.return_value.all.return_value = [
            self._row(4, 33, 'Unified Country Report'),
        ]
        template_id, error = resolve_template_id_from_assignment_ids([4])
        assert error is None
        assert template_id == 33

    @patch('app.utils.api_data_filters.joinedload')
    @patch('app.utils.api_data_filters.AssignedForm')
    def test_not_found_error_hints_at_submission_id(self, mock_assigned_form, _mock_joinedload):
        """Regression: assignment_id=1610 (an AssignmentEntityStatus/submission id, not an
        AssignedForm id) used to 404 with a bare 'not found' message."""
        mock_assigned_form.query.options.return_value.filter.return_value.all.return_value = []
        template_id, template_ids, error = resolve_assignment_scope([1610])
        assert template_id is None
        assert template_ids == []
        assert error['status'] == 404
        assert '1610' in error['message']
        assert 'submission_id' in error['message']

    @patch('app.utils.api_data_filters.joinedload')
    @patch('app.utils.api_data_filters.AssignedForm')
    def test_not_found_error_lists_all_missing_ids(self, mock_assigned_form, _mock_joinedload):
        mock_assigned_form.query.options.return_value.filter.return_value.all.return_value = [
            self._row(4, 33, 'Unified Country Report'),
        ]
        _, _, error = resolve_assignment_scope([4, 999])
        assert error['status'] == 404
        assert '999' in error['message']


@pytest.mark.unit
class TestResolveAssignmentEntityStatusFallback:
    def test_none_when_no_ids(self):
        assert resolve_assignment_entity_status_fallback(None) is None
        assert resolve_assignment_entity_status_fallback([]) is None

    def test_none_for_multiple_ids(self):
        """Mixing AssignedForm and AssignmentEntityStatus ids in one request is
        inherently ambiguous, so the fallback only handles the single-id case."""
        assert resolve_assignment_entity_status_fallback([1610, 1611]) is None

    @patch('app.utils.api_data_filters.joinedload')
    @patch('app.models.assignments.AssignmentEntityStatus')
    def test_none_when_submission_not_found(self, mock_aes_cls, _mock_joinedload):
        mock_aes_cls.query.options.return_value.filter.return_value.first.return_value = None
        assert resolve_assignment_entity_status_fallback([1610]) is None

    @patch('app.utils.api_data_filters.joinedload')
    @patch('app.models.assignments.AssignmentEntityStatus')
    def test_resolves_submission_id_and_template_id(self, mock_aes_cls, _mock_joinedload):
        aes = MagicMock()
        aes.id = 1610
        aes.assigned_form = MagicMock()
        aes.assigned_form.template_id = 21
        mock_aes_cls.query.options.return_value.filter.return_value.first.return_value = aes

        result = resolve_assignment_entity_status_fallback([1610])
        assert result == (1610, 21)

    @patch('app.utils.api_data_filters.joinedload')
    @patch('app.models.assignments.AssignmentEntityStatus')
    def test_resolves_submission_id_without_assigned_form(self, mock_aes_cls, _mock_joinedload):
        aes = MagicMock()
        aes.id = 1610
        aes.assigned_form = None
        mock_aes_cls.query.options.return_value.filter.return_value.first.return_value = aes

        result = resolve_assignment_entity_status_fallback([1610])
        assert result == (1610, None)


@pytest.mark.unit
class TestBuildDataApiScopeMeta:
    def test_none_without_template_or_assignment_scope(self):
        assert build_data_api_scope_meta(
            template_id=None,
            published_version_id=None,
            version_scope=VERSION_SCOPE_PUBLISHED,
        ) is None

    @patch('app.utils.api_data_filters._resolve_scope_period_names', return_value=['Jan-Jun 2026'])
    @patch('app.utils.api_data_filters._resolve_scope_template_names_for_ids', return_value=['A', 'B'])
    @patch('app.utils.api_data_filters.resolve_template_published_version_id', side_effect=[11, 22])
    def test_multi_template_assignment_scope(self, _mock_pub, _mock_names, _mock_periods):
        meta = build_data_api_scope_meta(
            template_id=None,
            template_ids=[23, 33],
            published_version_id=None,
            version_scope=VERSION_SCOPE_PUBLISHED,
            assignment_ids=[4, 34],
        )
        assert meta['template_ids'] == [23, 33]
        assert meta['published_version_ids'] == {'23': 11, '33': 22}
        assert meta['template_names'] == ['A', 'B']
        assert meta['assignment_ids'] == [4, 34]
        assert 'template_id' not in meta

    @patch('app.utils.api_data_filters._resolve_scope_period_names', return_value=[])
    @patch('app.utils.api_data_filters._resolve_scope_template_names', return_value=['FDRS'])
    def test_includes_template_and_version_fields(self, _mock_periods, _mock_templates):
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
            'template_names': ['FDRS'],
        }

    @patch('app.utils.api_data_filters._resolve_scope_period_names', return_value=['2024'])
    @patch('app.utils.api_data_filters._resolve_scope_template_names', return_value=['Annual Report'])
    def test_includes_template_and_period_names(self, _mock_templates, _mock_periods):
        meta = build_data_api_scope_meta(
            template_id=5,
            published_version_id=9,
            version_scope=VERSION_SCOPE_PUBLISHED,
            assignment_ids=[42],
            period_name='2024',
        )
        assert meta['template_names'] == ['Annual Report']
        assert meta['period_names'] == ['2024']
        assert meta['assignment_ids'] == [42]
        _mock_templates.assert_called_once_with(5)
        _mock_periods.assert_called_once_with(
            template_id=5,
            assignment_ids=[42],
            period_name='2024',
        )


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
