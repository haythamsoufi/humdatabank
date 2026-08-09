"""
Tests for server.py's serialization of concurrent databank_search_public_documents
calls — see the "Parallel document-search calls" investigation notes at the top of
server.py. Production incident review (2026-08-09) showed an LLM client firing several
of these calls back-to-back; overlapping requests landed on the same upstream Gunicorn
worker and contended for its DB pool, tripping the 18s statement_timeout on some calls.
_DOCUMENT_SEARCH_SEMAPHORE bounds how many of these calls can be in flight at once so
extra calls queue in-process (cheap) instead of stacking load on the upstream endpoint.
"""

import json
import threading
import time
from unittest.mock import patch

import server


def _run_concurrent_calls(num_calls: int, sleep_seconds: float = 0.05):
    """
    Fire num_calls concurrent databank_search_public_documents calls against a mocked
    search_public_documents that tracks how many calls were in flight simultaneously.

    Returns (max_observed_concurrency, results) where results[i] is the raw string
    returned by the i-th call (in call order, not completion order).
    """
    lock = threading.Lock()
    state = {"current": 0, "max": 0}
    results = [None] * num_calls

    def fake_search(query, **kwargs):
        with lock:
            state["current"] += 1
            state["max"] = max(state["max"], state["current"])
        time.sleep(sleep_seconds)
        with lock:
            state["current"] -= 1
        return {"query": query, "chunks": [], "count": 0}

    with patch("server.search_public_documents", side_effect=fake_search):
        threads = []
        for i in range(num_calls):
            def call(i=i):
                results[i] = server.databank_search_public_documents(query=f"q{i}")

            t = threading.Thread(target=call)
            threads.append(t)
            t.start()
        for t in threads:
            t.join(timeout=5)

    return state["max"], results


class TestDocumentSearchSerialization:
    def test_default_semaphore_serializes_calls(self):
        """Default MCP_MAX_CONCURRENT_DOCUMENT_SEARCHES=1: only one call should ever
        be executing search_public_documents at a time, even when fired concurrently."""
        max_concurrency, results = _run_concurrent_calls(num_calls=5)

        assert max_concurrency == 1
        for i, raw in enumerate(results):
            assert raw is not None, f"call {i} never completed"
            payload = json.loads(raw)
            assert payload["query"] == f"q{i}"

    def test_semaphore_allows_configured_concurrency(self):
        """Bumping the semaphore (e.g. via MCP_MAX_CONCURRENT_DOCUMENT_SEARCHES=2) should
        allow that many calls in flight at once, proving the cap is real (not accidental
        serialization from the GIL) and is tunable."""
        with patch("server._DOCUMENT_SEARCH_SEMAPHORE", threading.Semaphore(2)):
            max_concurrency, _results = _run_concurrent_calls(num_calls=6, sleep_seconds=0.08)

        assert max_concurrency == 2

    def test_semaphore_is_released_after_error(self):
        """A failed call must release its slot — otherwise every subsequent call would
        block forever waiting on a permanently-held semaphore."""
        with patch("server.search_public_documents", side_effect=RuntimeError("boom")):
            result = server.databank_search_public_documents(query="q")
        assert "Error" in result

        acquired = server._DOCUMENT_SEARCH_SEMAPHORE.acquire(blocking=False)
        assert acquired is True, "semaphore slot was not released after an error"
        server._DOCUMENT_SEARCH_SEMAPHORE.release()

    def test_happy_path_still_returns_result_unchanged(self):
        """Serialization must not alter the successful single-call result shape."""
        with patch("server.search_public_documents", return_value={"query": "health", "chunks": [], "count": 0}):
            result = server.databank_search_public_documents(query="health")
        payload = json.loads(result)
        assert payload == {"query": "health", "chunks": [], "count": 0}
