"""
Tests for server.py tool-level error handling — the "silent abort" bug from Round 1
feedback: two parallel/rapid-fire databank_search_public_documents calls returned no
result and no error at all.

Root cause: FastMCP's @mcp.tool sync handlers run in a thread pool; client-side
cancellation surfaces as asyncio.CancelledError, which subclasses BaseException (not
Exception) since Python 3.8 — a bare `except Exception` does not catch it, so a
cancelled call raised uncaught instead of returning an error string.
"""

import asyncio
from unittest.mock import patch

import server
from databank_client import DatabankAPIError


class TestToolError:
    def test_formats_databank_api_error(self):
        msg = server._tool_error(DatabankAPIError("boom", status_code=404))
        assert "HTTP 404" in msg
        assert "boom" in msg

    def test_formats_cancelled_error_gracefully(self):
        msg = server._tool_error(asyncio.CancelledError())
        assert "cancelled" in msg.lower()

    def test_formats_generic_exception(self):
        msg = server._tool_error(ValueError("bad input"))
        assert "bad input" in msg


class TestToolsSurfaceCancellationInsteadOfSilentAbort:
    """
    Each of these calls the real @mcp.tool()-decorated function (FastMCP's decorator
    returns the original function unchanged) with the underlying client call mocked to
    raise asyncio.CancelledError, simulating a cancelled/aborted request. Before the fix,
    this exception would propagate uncaught past `except Exception`; the tool must instead
    return a descriptive error string.
    """

    def test_search_public_documents_tool(self):
        with patch("server.search_public_documents", side_effect=asyncio.CancelledError()):
            result = server.databank_search_public_documents(query="Post Office")
        assert isinstance(result, str)
        assert "cancelled" in result.lower()

    def test_get_chunk_context_tool(self):
        with patch("server.get_chunk_context", side_effect=asyncio.CancelledError()):
            result = server.databank_get_chunk_context(chunk_id=17842)
        assert isinstance(result, str)
        assert "cancelled" in result.lower()

    def test_aggregate_global_trend_tool(self):
        with patch("server.get_public_global_trend", side_effect=asyncio.CancelledError()):
            result = server.databank_aggregate_global_trend(query="volunteers")
        assert isinstance(result, str)
        assert "cancelled" in result.lower()

    def test_get_public_document_tool(self):
        with patch("server.get_public_document", side_effect=asyncio.CancelledError()):
            result = server.databank_get_public_document(document_id=244)
        assert isinstance(result, str)
        assert "cancelled" in result.lower()
