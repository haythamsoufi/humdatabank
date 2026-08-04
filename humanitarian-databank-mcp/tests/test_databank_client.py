"""Tests for humanitarian-databank-mcp."""

import json
from unittest.mock import MagicMock, patch

import pytest

from databank_client import (
    DatabankAPIError,
    get_public_data_page,
    search_indicators,
)


class TestSearchIndicators:
    def test_parses_indicator_list(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"indicators": [{"id": 1, "name": "Test"}]}

        with patch("databank_client.httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.get.return_value = mock_resp
            out = search_indicators(search="volunteers")

        assert out["count"] == 1
        assert out["indicators"][0]["id"] == 1


class TestPublicData:
    def test_requires_scope_filter(self):
        with pytest.raises(DatabankAPIError, match="scope filter"):
            get_public_data_page()

    def test_builds_query(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [], "total_items": 0}

        with patch("databank_client.httpx.Client") as client_cls:
            mock_get = client_cls.return_value.__enter__.return_value.get
            mock_get.return_value = mock_resp
            get_public_data_page(indicator_bank_id=42, page=1, per_page=100)
            call_kwargs = mock_get.call_args
            assert "/data" in call_kwargs[0][0]
            assert call_kwargs[1]["params"]["indicator_bank_id"] == 42
