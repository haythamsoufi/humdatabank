"""Tests for variable_resolution_helpers."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.forms.variable_resolution_helpers import (
    merge_batch_resolved_variables,
    resolve_assignment_level_variables,
)

pytestmark = pytest.mark.unit


def test_resolve_assignment_level_variables_populates_assignment_keys():
    template_version = MagicMock(variables={'var_a': {}})
    aes = MagicMock()
    resolved = {'var_a': 'value'}

    with patch(
        'app.services.forms.variable_resolution_service.VariableResolutionService.resolve_variables',
        return_value=resolved,
    ):
        mapping, assignment_level = resolve_assignment_level_variables(template_version, aes)

    assert assignment_level == resolved
    assert mapping[''] == resolved
    assert mapping['assignment'] == resolved


def test_merge_batch_resolved_variables_merges_into_target():
    template_version = MagicMock()
    aes = MagicMock()
    target = {'assignment': {'x': 1}}
    batch = {42: {'row_var': 'yes'}}

    with patch(
        'app.services.forms.variable_resolution_service.VariableResolutionService.resolve_variables_batch',
        return_value=batch,
    ):
        result = merge_batch_resolved_variables(template_version, aes, [42], target)

    assert result == batch
    assert target['42'] == {'row_var': 'yes'}
    assert target['assignment'] == {'x': 1}
