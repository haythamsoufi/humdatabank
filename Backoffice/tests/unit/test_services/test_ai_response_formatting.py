"""Tests for AI chat markdown → HTML formatting (tables + document links)."""

from app.services.ai.providers.formatting import (
    format_ai_response_for_html,
    _is_preserved_chat_href,
)


def test_preserves_relative_and_allowlisted_https_hrefs():
    assert _is_preserved_chat_href("/api/ai/documents/12/download")
    assert _is_preserved_chat_href(
        "https://go-api.ifrc.org/api/DownloadFile/89684/MDRSY013fr"
    )
    assert not _is_preserved_chat_href("https://evil.example/phish")
    assert not _is_preserved_chat_href("javascript:alert(1)")
    assert not _is_preserved_chat_href("http://go-api.ifrc.org/api/DownloadFile/1/x")


def test_markdown_table_with_go_api_download_links_survives_sanitize():
    text = (
        "Here are the emergency operation documents for Syria.\n\n"
        "| Title | Category | Date | Link |\n"
        "|---|---|---|---|\n"
        "| Syria - Fire (MDRSY013) | emergency_operation | 2024-01-01 | "
        "[Download](https://go-api.ifrc.org/api/DownloadFile/89684/MDRSY013fr) |\n"
        "| Syria - Wildfires (MDRSY015) | emergency_operation | 2025-01-01 | "
        "[Download](https://go-api.ifrc.org/api/DownloadFile/92291/MDRSY015FR) |\n"
    )
    html = format_ai_response_for_html(text)
    assert "<table" in html.lower()
    assert "Syria - Fire (MDRSY013)" in html
    assert "Syria - Wildfires (MDRSY015)" in html
    assert 'href="https://go-api.ifrc.org/api/DownloadFile/89684/MDRSY013fr"' in html
    assert 'href="https://go-api.ifrc.org/api/DownloadFile/92291/MDRSY015FR"' in html
    assert "Download" in html


def test_non_allowlisted_https_href_is_stripped():
    text = "See [docs](https://evil.example/steal)."
    html = format_ai_response_for_html(text)
    assert "evil.example" not in html
    assert "docs" in html
