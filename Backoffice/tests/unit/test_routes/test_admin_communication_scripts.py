"""Tests for Communication Center campaign template seed wiring."""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit]


def _json_headers():
    return {"Content-Type": "application/json", "Accept": "application/json"}


class TestCampaignEmailTemplatesSeed:
    def test_seed_uses_seeding_module(self, logged_in_client, app):
        mock_stats = {"email": {"seeded": 1, "skipped": 0}}
        with patch("app.routes.admin.shared.AuthorizationService.is_admin", return_value=True), \
             patch("app.routes.admin.shared.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("scripts.seeding.seed_campaign_email_templates.seed_campaign_templates", return_value=mock_stats) as mock_seed:
            resp = logged_in_client.post(
                "/admin/api/communication/campaign-email-templates/seed",
                json={"force": True},
                headers=_json_headers(),
            )
        assert resp.status_code == 200
        mock_seed.assert_called_once()
        assert mock_seed.call_args.kwargs.get("force") is True

    def test_seed_campaign_module_importable(self):
        from scripts.seeding.seed_campaign_email_templates import seed_campaign_templates

        assert callable(seed_campaign_templates)
