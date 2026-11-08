"""Unit tests for validation check orchestration."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.data_quality.helpers import resolve_assignment_aes
from app.services.validation.check_service import evaluate_validation_checks, run_validation_checks


def test_resolve_assignment_aes_matches_by_year(monkeypatch):
    aes = object()

    monkeypatch.setattr(
        "app.services.data_quality.helpers.get_assignment_aes",
        lambda template_id, entity_type, entity_id, period_name: (
            aes if period_name == "FDRS 2024" else None
        ),
    )
    monkeypatch.setattr(
        "app.services.data_quality.helpers.list_assignment_periods",
        lambda *args, **kwargs: ["FDRS 2024", "FDRS 2023"],
    )

    resolved_aes, resolved_period = resolve_assignment_aes(21, "country", 86, "2024")
    assert resolved_aes is aes
    assert resolved_period == "FDRS 2024"


def test_run_validation_checks_requires_rule_pack():
    template = MagicMock()
    template.published_version_id = 1

    with patch("app.services.validation.check_service.FormTemplate.query") as mock_tpl:
        mock_tpl.get.return_value = template
        with patch(
            "app.services.validation.check_service.get_rule_pack_for_template",
            return_value=None,
        ):
            with pytest.raises(ValueError, match="validation checks enabled"):
                run_validation_checks(21, "country", 86, "2024")


def test_run_validation_checks_requires_assignment():
    template = MagicMock()
    template.published_version_id = 1

    with patch("app.services.validation.check_service.FormTemplate.query") as mock_tpl:
        mock_tpl.get.return_value = template
        with patch(
            "app.services.validation.check_service.get_rule_pack_for_template",
            return_value="fdrs_matrix_v1",
        ):
            with patch(
                "app.services.validation.check_service.resolve_assignment_aes",
                return_value=(None, "2024"),
            ):
                with patch(
                    "app.services.validation.check_service.list_assignment_periods",
                    return_value=["FDRS 2024"],
                ):
                    with pytest.raises(ValueError, match="No assignment found"):
                        run_validation_checks(21, "country", 86, "2024")
