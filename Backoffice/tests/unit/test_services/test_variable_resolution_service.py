import pytest

from app.services.variable_resolution_service import VariableResolutionService


def test_evaluate_formula_with_basic_operations():
    assert VariableResolutionService._evaluate_formula("+5", 10) == 15
    assert VariableResolutionService._evaluate_formula("*2", 3) == 6
    assert VariableResolutionService._evaluate_formula("-2", 5) == 3
    assert VariableResolutionService._evaluate_formula("/4", 12) == 3


def test_evaluate_formula_rejects_malicious_input():
    malicious = "__import__('os').system('whoami')"
    original_value = 7
    result = VariableResolutionService._evaluate_formula(malicious, original_value)
    assert result == original_value


def test_replace_variables_in_text_with_formula():
    text = "Total: [[amount]+2]"
    resolved = {"amount": 5}
    result = VariableResolutionService.replace_variables_in_text(text, resolved, {})
    assert "7" in result
