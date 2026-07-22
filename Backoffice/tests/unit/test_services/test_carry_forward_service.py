"""Unit tests for CarryForwardService."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest


pytestmark = [pytest.mark.unit]


def _make_item(item_id=1434, carry_forward=True, sources=None):
    return SimpleNamespace(
        id=item_id,
        config={
            'carry_forward': carry_forward,
            'carry_forward_sources': sources if sources is not None else [],
        },
        is_matrix=True,
        is_plugin=False,
    )


def _make_aes(aes_id=4114, entity_type='country', entity_id=61, template_id=23):
    assigned_form = SimpleNamespace(template_id=template_id, period_name='2026 Midyear')
    return SimpleNamespace(
        id=aes_id,
        entity_type=entity_type,
        entity_id=entity_id,
        assigned_form=assigned_form,
    )


def _make_form_data(*, value=None, disagg_data=None, data_not_available=False, not_applicable=False):
    return SimpleNamespace(
        value=value,
        disagg_data=disagg_data,
        data_not_available=data_not_available,
        not_applicable=not_applicable,
        prefilled_value=None,
        prefilled_disagg_data=None,
        imputed_value=None,
        imputed_disagg_data=None,
    )


class TestCarryForwardService:
    def test_skips_when_current_aes_has_reported_data(self):
        from app.services.carry_forward_service import CarryForwardService

        aes = _make_aes()
        item = _make_item()
        current_fd = _make_form_data(disagg_data={'61_Planned': 10})
        current_fd.form_item_id = 1434

        with patch('app.services.carry_forward_service.FormData') as fd_model:
            fd_model.query.filter.return_value.all.return_value = [current_fd]

            result = CarryForwardService.resolve_for_aes(aes, [item])

        assert result == {}

    def test_resolve_references_returns_data_even_when_current_aes_has_reported_data(self):
        from app.services.carry_forward_service import CarryForwardService

        aes = _make_aes()
        item = _make_item()
        current_fd = _make_form_data(disagg_data={'61_Planned': 10})
        current_fd.form_item_id = 1434
        prev_aes = SimpleNamespace(id=3221, assigned_form=SimpleNamespace(template_id=23, period_name='2025 Midyear'))
        prev_fd = _make_form_data(disagg_data={'61_Planned': 456})

        with patch('app.services.carry_forward_service.FormData') as fd_model:
            fd_model.query.filter.return_value.all.return_value = [current_fd]
            fd_model.query.filter_by.return_value.order_by.return_value.first.return_value = prev_fd

            with patch.object(CarryForwardService, '_find_previous_aes_with_item_data', return_value=prev_aes):
                result = CarryForwardService.resolve_references_for_aes(aes, [item])

        assert result[1434]['disagg_data'] == {'61_Planned': 456}

    def test_defaults_to_current_template_and_item_when_sources_empty(self):
        from app.services.carry_forward_service import CarryForwardService

        aes = _make_aes()
        item = _make_item(item_id=1434, sources=[])
        prev_aes = SimpleNamespace(id=3221, assigned_form=SimpleNamespace(template_id=23, period_name='2025 Midyear'))
        prev_fd = _make_form_data(disagg_data={'61_Planned': 456})

        with patch('app.services.carry_forward_service.FormData') as fd_model:
            fd_model.query.filter.return_value.all.return_value = []
            fd_model.query.filter_by.return_value.order_by.return_value.first.return_value = prev_fd

            with patch.object(CarryForwardService, '_find_previous_aes_with_item_data', return_value=prev_aes) as finder:
                result = CarryForwardService.resolve_for_aes(aes, [item])

        finder.assert_called_once()
        assert finder.call_args.kwargs['template_id'] == 23
        assert finder.call_args.kwargs['form_item_id'] == 1434
        assert result[1434]['disagg_data'] == {'61_Planned': 456}

    def test_configured_cross_template_source_is_used(self):
        from app.services.carry_forward_service import CarryForwardService

        aes = _make_aes()
        item = _make_item(
            item_id=1434,
            sources=[{'template_id': 22, 'item_id': 1314}],
        )
        prev_aes = SimpleNamespace(id=3001, assigned_form=SimpleNamespace(template_id=22, period_name='2026 Planning'))
        prev_fd = _make_form_data(disagg_data={'61_Planned': 99})

        with patch('app.services.carry_forward_service.FormData') as fd_model:
            fd_model.query.filter.return_value.all.return_value = []
            fd_model.query.filter_by.return_value.order_by.return_value.first.return_value = prev_fd

            with patch.object(CarryForwardService, '_find_previous_aes_with_item_data', return_value=prev_aes) as finder:
                with patch.object(CarryForwardService, '_get_item_stub_for_payload', return_value=_make_item(item_id=1314)):
                    result = CarryForwardService.resolve_for_aes(aes, [item])

        assert finder.call_args.kwargs['template_id'] == 22
        assert finder.call_args.kwargs['form_item_id'] == 1314
        assert result[1434]['disagg_data'] == {'61_Planned': 99}

    def test_first_configured_source_wins_when_priority_is_source(self):
        from app.services.carry_forward_service import CarryForwardService

        aes = _make_aes()
        item = _make_item(
            item_id=1434,
            sources=[
                {'template_id': 22, 'item_id': 1314},
                {'template_id': '__current__', 'item_id': '__current__'},
            ],
        )
        item.config['carry_forward_priority'] = 'source'
        planning_aes = SimpleNamespace(
            id=3001,
            submitted_at='2026-03-01',
            status_timestamp='2026-03-01',
            assigned_form=SimpleNamespace(template_id=22, period_name='2026 Planning'),
        )
        annual_aes = SimpleNamespace(
            id=2001,
            submitted_at='2025-11-01',
            status_timestamp='2025-11-01',
            assigned_form=SimpleNamespace(template_id=23, period_name='2025 Annual'),
        )
        planning_fd = _make_form_data(disagg_data={'61_Planned': 99})
        annual_fd = _make_form_data(disagg_data={'61_Planned': 456})

        with patch('app.services.carry_forward_service.FormData') as fd_model:
            fd_model.query.filter.return_value.all.return_value = []

            def _find_side_effect(*args, **kwargs):
                template_id = kwargs.get('template_id')
                if template_id == 22:
                    return planning_aes
                if template_id == 23:
                    return annual_aes
                return None

            with patch.object(CarryForwardService, '_find_previous_aes_with_item_data', side_effect=_find_side_effect) as finder:
                with patch.object(CarryForwardService, '_get_item_stub_for_payload', return_value=_make_item(item_id=1314)):
                    with patch.object(CarryForwardService, '_payload_from_form_data', side_effect=[{'disagg_data': planning_fd.disagg_data}, {'disagg_data': annual_fd.disagg_data}]):
                        result = CarryForwardService.resolve_for_aes(aes, [item])

        assert finder.call_count == 1
        assert result[1434]['disagg_data'] == {'61_Planned': 99}

    def test_most_recent_assignment_wins_when_priority_is_assignment(self):
        from datetime import datetime

        from app.services.carry_forward_service import CarryForwardService

        aes = _make_aes()
        item = _make_item(
            item_id=1434,
            sources=[
                {'template_id': '__current__', 'item_id': '__current__'},
                {'template_id': 22, 'item_id': 1314},
            ],
        )
        item.config['carry_forward_priority'] = 'assignment'
        planning_aes = SimpleNamespace(
            id=3001,
            submitted_at=datetime(2026, 3, 1),
            status_timestamp=datetime(2026, 3, 1),
            assigned_form=SimpleNamespace(template_id=22, period_name='2026 Planning'),
        )
        annual_aes = SimpleNamespace(
            id=2001,
            submitted_at=datetime(2025, 11, 1),
            status_timestamp=datetime(2025, 11, 1),
            assigned_form=SimpleNamespace(template_id=23, period_name='2025 Annual'),
        )

        with patch('app.services.carry_forward_service.FormData') as fd_model:
            fd_model.query.filter.return_value.all.return_value = []

            def _find_side_effect(*args, **kwargs):
                template_id = kwargs.get('template_id')
                if template_id == 22:
                    return planning_aes
                if template_id == 23:
                    return annual_aes
                return None

            with patch.object(CarryForwardService, '_find_previous_aes_with_item_data', side_effect=_find_side_effect):
                with patch.object(CarryForwardService, '_get_item_stub_for_payload', return_value=_make_item(item_id=1314)):
                    with patch.object(
                        CarryForwardService,
                        '_payload_from_form_data',
                        side_effect=lambda prev_aes, *args, **kwargs: {
                            'disagg_data': {'61_Planned': 99 if prev_aes.id == 3001 else 456},
                            'is_matrix': True,
                        },
                    ):
                        result = CarryForwardService.resolve_for_aes(aes, [item])

        assert result[1434]['disagg_data'] == {'61_Planned': 99}

    def test_scalar_indicator_carry_forward(self):
        from app.services.carry_forward_service import CarryForwardService

        aes = _make_aes()
        item = SimpleNamespace(
            id=500,
            config={'carry_forward': True, 'carry_forward_sources': []},
            is_matrix=False,
            is_plugin=False,
        )
        prev_aes = SimpleNamespace(id=900, assigned_form=SimpleNamespace(template_id=23, period_name='2025'))
        prev_fd = _make_form_data(value='42')

        with patch('app.services.carry_forward_service.FormData') as fd_model:
            fd_model.query.filter.return_value.all.return_value = []
            fd_model.query.filter_by.return_value.order_by.return_value.first.return_value = prev_fd

            with patch.object(CarryForwardService, '_find_previous_aes_with_item_data', return_value=prev_aes):
                result = CarryForwardService.resolve_for_aes(aes, [item])

        assert result[500]['is_matrix'] is False
        assert result[500]['value'] == '42'

    def test_normalize_source_for_storage_accepts_current_sentinels(self):
        from app.services.carry_forward_service import CarryForwardService

        assert CarryForwardService.normalize_source_for_storage({
            'template_id': '__current__',
            'item_id': 1314,
        }) == {'template_id': '__current__', 'item_id': 1314}

        assert CarryForwardService.normalize_source_for_storage({
            'template_id': 22,
            'item_id': '__current__',
        }) == {'template_id': 22, 'item_id': '__current__'}

    def test_normalize_priority_for_storage(self):
        from app.services.carry_forward_service import CarryForwardService

        assert CarryForwardService.normalize_priority_for_storage('assignment') == 'assignment'
        assert CarryForwardService.normalize_priority_for_storage('source') == 'source'
        assert CarryForwardService.normalize_priority_for_storage('invalid') == 'source'

    def test_iter_carry_forward_items_collects_flagged_fields(self):
        from app.services.carry_forward_service import CarryForwardService

        flagged = SimpleNamespace(id=1, config={'carry_forward': True})
        plain = SimpleNamespace(id=2, config={})
        section = SimpleNamespace(fields_ordered=[flagged, plain])

        items = CarryForwardService.iter_carry_forward_items([section])
        assert [item.id for item in items] == [1]
