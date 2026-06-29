"""Tests for campaign email template settings service."""
from __future__ import annotations

import pytest

from app.services.campaign_email_templates_service import (
    CAMPAIGN_EMAIL_TEMPLATE_KEYS,
    get_all_campaign_email_templates,
    get_campaign_compose_templates,
    get_campaign_email_template,
    get_email_template_html_from_attachment_config,
    merge_campaign_email_attachment_config,
    merge_email_template_key_into_attachment_config,
    normalize_campaign_email_template_key,
    set_all_campaign_email_templates,
)


@pytest.mark.usefixtures("app")
class TestCampaignEmailTemplatesService:
    def test_normalize_campaign_email_template_key(self):
        valid = CAMPAIGN_EMAIL_TEMPLATE_KEYS[0]
        assert normalize_campaign_email_template_key(valid) == valid
        assert normalize_campaign_email_template_key("  " + valid + "  ") == valid
        assert normalize_campaign_email_template_key("invalid") is None
        assert normalize_campaign_email_template_key(None) is None

    def test_merge_email_template_key_into_attachment_config(self, monkeypatch):
        key = CAMPAIGN_EMAIL_TEMPLATE_KEYS[0]
        merged = merge_email_template_key_into_attachment_config(
            {"static_attachments": []},
            key,
        )
        assert merged["email_template_key"] == key
        assert merged["static_attachments"] == []

        cleared = merge_email_template_key_into_attachment_config(merged, "")
        assert "email_template_key" not in (cleared or {})

    def test_merge_campaign_email_attachment_config_html(self):
        key = CAMPAIGN_EMAIL_TEMPLATE_KEYS[0]
        html = "<html><body>{{ title }}</body></html>"
        merged = merge_campaign_email_attachment_config(
            {"static_attachments": []},
            email_template_key=key,
            email_template_html=html,
        )
        assert merged["email_template_key"] == key
        assert merged["email_template_html"] == html
        assert get_email_template_html_from_attachment_config(merged) == html

        cleared = merge_campaign_email_attachment_config(merged, email_template_html="")
        assert "email_template_html" not in (cleared or {})
        assert cleared["email_template_key"] == key

    def test_set_and_get_campaign_templates(self, monkeypatch):
        key = CAMPAIGN_EMAIL_TEMPLATE_KEYS[0]
        html = "<html><body>{{ title }}</body></html>"
        storage = {}

        def fake_write(data, user_id=None):
            storage.clear()
            storage.update(data)
            return True

        def fake_read():
            return dict(storage)

        monkeypatch.setattr(
            "app.services.campaign_email_templates_service.read_settings",
            fake_read,
        )
        monkeypatch.setattr(
            "app.services.campaign_email_templates_service.write_settings",
            fake_write,
        )

        ok = set_all_campaign_email_templates(
            {key: {"en": html, "fr": "<html>fr</html>"}},
            metadata={
                key: {
                    "label": "Launch",
                    "compose_title": "Reporting open",
                    "compose_message": "Please submit data.",
                    "priority": "high",
                }
            },
        )
        assert ok is True

        assert get_campaign_email_template(key, language="en") == html
        assert get_campaign_email_template(key, language="de") == html

        all_tpl = get_all_campaign_email_templates()
        assert all_tpl[key]["en"] == html

        compose = get_campaign_compose_templates()[key]
        assert compose["label"] == "Launch"
        assert compose["title"] == "Reporting open"
        assert compose["message"] == "Please submit data."
        assert compose["priority"] == "high"
