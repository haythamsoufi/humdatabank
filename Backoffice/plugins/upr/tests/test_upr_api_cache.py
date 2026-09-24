"""UPR endpoint cache and non-paginated response tests."""

from __future__ import annotations

import json

from flask import Flask

from plugins.upr import api_cache
from plugins.upr import upr_data_routes


def setup_function():
    api_cache.reset_upr_api_cache_for_tests()


def teardown_function():
    api_cache.reset_upr_api_cache_for_tests()


def test_revision_change_invalidates_cached_payload(monkeypatch):
    revision = {"value": 10}
    loads = {"count": 0}
    monkeypatch.setattr(api_cache, "get_upr_cache_revision", lambda: revision["value"])
    monkeypatch.setattr(api_cache, "_get_redis", lambda: None)

    def load():
        loads["count"] += 1
        return {"data": [{"load": loads["count"]}]}

    first, first_hit = api_cache.get_or_build_upr_payload("data", {"round": "MYR26"}, load)
    second, second_hit = api_cache.get_or_build_upr_payload("data", {"round": "MYR26"}, load)
    revision["value"] = 11
    third, third_hit = api_cache.get_or_build_upr_payload("data", {"round": "MYR26"}, load)

    assert first == second == {"data": [{"load": 1}]}
    assert third == {"data": [{"load": 2}]}
    assert (first_hit, second_hit, third_hit) == (False, True, False)


def test_revision_read_failure_always_builds_fresh(monkeypatch):
    loads = {"count": 0}
    monkeypatch.setattr(api_cache, "get_upr_cache_revision", lambda: None)

    def load():
        loads["count"] += 1
        return {"load": loads["count"]}

    assert api_cache.get_or_build_upr_payload("master", {}, load) == ({"load": 1}, False)
    assert api_cache.get_or_build_upr_payload("master", {}, load) == ({"load": 2}, False)


def test_data_endpoint_returns_complete_extract_without_pagination(monkeypatch):
    app = Flask(__name__)
    facts = [{"Value": index} for index in range(3)]
    captured = {}

    def fake_cache(namespace, params, loader):
        captured.update({"namespace": namespace, "params": params})
        return loader(), False

    monkeypatch.setattr(upr_data_routes, "get_or_build_upr_payload", fake_cache)
    monkeypatch.setattr(
        upr_data_routes,
        "build_upr_data",
        lambda **kwargs: {"data": facts, "submissions": [{"id": 1}], "comments": []},
    )

    with app.test_request_context(
        "/api/v1/upr/data?round=myr26&iso3=afg&page=2&per_page=1"
    ):
        response = upr_data_routes.get_upr_data.__wrapped__()

    body = json.loads(response.get_data(as_text=True))
    assert body["data"] == facts
    assert body["meta"]["total"] == 3
    assert "page" not in body["meta"]
    assert "per_page" not in body["meta"]
    assert "total_pages" not in body["meta"]
    assert captured == {
        "namespace": "data",
        "params": {
            "template": None,
            "round": "MYR26",
            "iso3": "AFG",
            "table": None,
        },
    }
    assert response.headers["X-UPR-Cache"] == "MISS"
    assert response.headers["Cache-Control"] == "no-store"


def test_master_endpoint_returns_complete_extract_without_pagination(monkeypatch):
    app = Flask(__name__)
    rows = [{"ISO3": "AFG"}, {"ISO3": "KEN"}]

    monkeypatch.setattr(
        upr_data_routes,
        "get_or_build_upr_payload",
        lambda namespace, params, loader: (loader(), True),
    )
    monkeypatch.setattr(
        upr_data_routes,
        "build_upr_master",
        lambda **kwargs: {"data": rows},
    )

    with app.test_request_context("/api/v1/upr/master?page=9&per_page=1"):
        response = upr_data_routes.get_upr_master.__wrapped__()

    body = json.loads(response.get_data(as_text=True))
    assert body["data"] == rows
    assert body["meta"]["total"] == 2
    assert set(body["meta"]) == {"total", "columns"}
    assert response.headers["X-UPR-Cache"] == "HIT"
