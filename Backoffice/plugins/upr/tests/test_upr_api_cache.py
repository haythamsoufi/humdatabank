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
        lambda **kwargs: {"data": facts, "submissions": [{"id": 1}]},
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
            "section": None,
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


def test_submissions_endpoint_returns_all_rounds_and_normalizes_filters(monkeypatch):
    app = Flask(__name__)
    rows = [
        {"Round": "AR25", "ISO3": "AFG", "status": "approved"},
        {"Round": "MYR26", "ISO3": "AFG", "status": "submitted"},
    ]
    captured = {}

    def fake_cache(namespace, params, loader):
        captured.update({"namespace": namespace, "params": params})
        return loader(), False

    monkeypatch.setattr(upr_data_routes, "get_or_build_upr_payload", fake_cache)
    monkeypatch.setattr(
        upr_data_routes,
        "build_upr_submissions",
        lambda **kwargs: {"data": rows},
    )

    with app.test_request_context(
        "/api/v1/upr/submissions?template=report&round=myr26&iso3=afg"
    ):
        response = upr_data_routes.get_upr_submissions.__wrapped__()

    body = json.loads(response.get_data(as_text=True))
    assert body["data"] == rows
    assert body["meta"]["total"] == 2
    assert "page" not in body["meta"]
    assert captured == {
        "namespace": "submissions",
        "params": {
            "template": "report",
            "round": "MYR26",
            "iso3": "AFG",
        },
    }
    assert response.headers["Cache-Control"] == "no-store"
    assert any(
        endpoint["path"] == "/api/v1/upr/submissions"
        for endpoint in upr_data_routes.API_ENDPOINTS
    )


def test_docs_endpoint_lists_parameters():
    app = Flask(__name__)

    with app.test_request_context("/api/v1/upr"):
        response = upr_data_routes.get_upr_docs.__wrapped__()

    body = json.loads(response.get_data(as_text=True))
    by_path = {endpoint["path"]: endpoint for endpoint in body["endpoints"]}
    data_params = {param["name"]: param for param in by_path["/api/v1/upr/data"]["parameters"]}
    assert data_params["template"]["values"] == ["report", "plan", "pns"]
    assert data_params["round"]["multiple"] is True
    assert data_params["round"]["example"] == "MYR26,P27"
    assert "Funding" in data_params["section"]["values"]
    assert "Round" in by_path["/api/v1/upr/data"]["columns"]["data"]
    assert by_path["/api/v1/upr/submissions"]["parameters"]
    assert "section" not in {param["name"] for param in by_path["/api/v1/upr/submissions"]["parameters"]}
    assert by_path["/api/v1/upr"]["parameters"] == []


def test_round_filter_accepts_several_codes(monkeypatch):
    app = Flask(__name__)
    captured = {}

    def fake_cache(namespace, params, loader):
        captured.update({"namespace": namespace, "params": params, "kwargs": {}})
        return loader(), False

    def fake_build(**kwargs):
        captured["kwargs"] = kwargs
        return {"data": [], "submissions": []}

    monkeypatch.setattr(upr_data_routes, "get_or_build_upr_payload", fake_cache)
    monkeypatch.setattr(upr_data_routes, "build_upr_data", fake_build)

    with app.test_request_context("/api/v1/upr/data?round=P27&round=myr26,P27"):
        upr_data_routes.get_upr_data.__wrapped__()

    assert captured["params"]["round"] == "MYR26,P27"
    assert captured["kwargs"]["round_code"] == "MYR26,P27"
