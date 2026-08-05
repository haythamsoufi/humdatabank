"""Tests for humanitarian-databank-mcp."""

import json
from unittest.mock import MagicMock, patch

import pytest

from databank_client import (
    DatabankAPIError,
    get_public_data_page,
    get_public_global_trend,
    resolve_public_indicator,
    search_indicators,
    search_public_documents,
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


class TestPublicGlobalTrend:
    def test_calls_public_endpoint(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"by_period": []}

        with patch("databank_client.httpx.Client") as client_cls:
            mock_get = client_cls.return_value.__enter__.return_value.get
            mock_get.return_value = mock_resp
            get_public_global_trend(query="volunteers")
            assert "/public/global-trend" in mock_get.call_args[0][0]
            assert mock_get.call_args[1]["params"]["query"] == "volunteers"

    def test_requires_query_or_id(self):
        with pytest.raises(DatabankAPIError, match="indicator_bank_id or query"):
            get_public_global_trend()


class TestResolvePublicIndicator:
    def test_calls_public_endpoint(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"best_match": {"id": 724}}

        with patch("databank_client.httpx.Client") as client_cls:
            mock_get = client_cls.return_value.__enter__.return_value.get
            mock_get.return_value = mock_resp
            out = resolve_public_indicator("volunteers")
            assert "/public/indicators/resolve" in mock_get.call_args[0][0]
            assert out["best_match"]["id"] == 724


class TestSearchPublicDocuments:
    def test_calls_public_endpoint(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"chunks": [], "count": 0}

        with patch("databank_client.httpx.Client") as client_cls:
            mock_get = client_cls.return_value.__enter__.return_value.get
            mock_get.return_value = mock_resp
            search_public_documents("Syria unified plan 2026", full_coverage=True)
            assert "/public/documents/search" in mock_get.call_args[0][0]
            params = mock_get.call_args[1]["params"]
            assert params["query"] == "Syria unified plan 2026"
            assert params["full_coverage"] == "true"

    def test_requires_query(self):
        with pytest.raises(DatabankAPIError, match="query is required"):
            search_public_documents("  ")
