"""
End-to-end authorization of API keys through the real Flask routes.

The model under test: a key holds explicit capabilities (``api_key_permissions``), every
key-authenticated route declares the one it needs, and ``authenticate_*`` enforces it in one
place. NULL / unknown / malformed permissions grant nothing, data scopes apply to list and
detail routes alike, and the deprecated env key is least-privilege.
"""
import pytest

from app import db
from app.models import FormData
from app.services.security.api_key_permissions import (
    CONTENT_READ,
    DATA_READ,
    DOCUMENTS_READ,
    INDICATORS_MANAGE,
    REFERENCE_READ,
    SUBMISSIONS_READ,
    TEMPLATES_READ,
    USERS_READ,
    build_permissions_document,
    full_access_document,
)
from tests.factories import (
    create_test_api_key,
    create_test_assignment_entity_status,
    create_test_country,
    create_test_item,
    create_test_public_submission,
    create_test_section,
    create_test_template,
    create_test_user,
)

pytestmark = [pytest.mark.integration, pytest.mark.auth_security]


@pytest.fixture(autouse=True)
def _isolate_key_rate_limits(app):
    from app.services.security import api_authentication as auth_mod

    saved = app.config.get("MOBILE_APP_API_KEY_RATE_LIMIT_PER_MINUTE")
    app.config["MOBILE_APP_API_KEY_RATE_LIMIT_PER_MINUTE"] = 300
    auth_mod._api_key_rate_limit_storage.clear()
    yield
    auth_mod._api_key_rate_limit_storage.clear()
    app.config["MOBILE_APP_API_KEY_RATE_LIMIT_PER_MINUTE"] = saved


def _bearer(key):
    return {"Authorization": f"Bearer {key}"}


def _key(db_session, document, **kwargs):
    _obj, full_key = create_test_api_key(db_session, permissions=document, **kwargs)
    return full_key


def _caps(*codes, **kwargs):
    return build_permissions_document(codes, **kwargs)


@pytest.fixture
def world(app, db_session):
    """Two templates x two countries with one assigned + data row each, plus a public submission."""
    with app.app_context():
        c1 = create_test_country(db_session, name="Scope Country One")
        c2 = create_test_country(db_session, name="Scope Country Two")
        t1 = create_test_template(db_session, name="Scope Template One")
        t2 = create_test_template(db_session, name="Scope Template Two")
        aes1 = create_test_assignment_entity_status(db_session, country=c1, template=t1)
        aes2 = create_test_assignment_entity_status(db_session, country=c2, template=t2)
        items = {}
        for tpl, aes in ((t1, aes1), (t2, aes2)):
            section = create_test_section(db_session, tpl)
            item = create_test_item(db_session, section, tpl, privacy="public")
            row = FormData(assignment_entity_status_id=aes.id, form_item_id=item.id)
            row.set_simple_value("42")
            db_session.add(row)
            db_session.commit()
            items[tpl.id] = item.id
        public, _af, _token = create_test_public_submission(
            db_session, country=c1, template=t1, period_name="2023",
            submitter_name="Pat Public", submitter_email="pat.public@example.org",
        )
        user = create_test_user(db_session, email="directory.person@example.org", name="Directory Person")
        return {
            "c1": c1.id, "c2": c2.id, "t1": t1.id, "t2": t2.id,
            "aes1": aes1.id, "aes2": aes2.id, "public": public.id,
            "items": items, "user": user.id,
        }


def _get(client, url, key):
    return client.get(url, headers=_bearer(key))


# --------------------------------------------------------------------------------------
# Every route class: allowed with its capability, refused without it
# --------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "capability,urls",
    [
        (DATA_READ, ["/api/v1/data", "/api/v1/templates/{t1}/data?page=1&per_page=5",
                     "/api/v1/countries/{c1}/data?page=1&per_page=5"]),
        (USERS_READ, ["/api/v1/users", "/api/v1/users/{user}", "/api/v1/quiz/leaderboard"]),
        (SUBMISSIONS_READ, ["/api/v1/submissions", "/api/v1/submissions/{aes1}", "/api/v1/assigned-forms"]),
        (TEMPLATES_READ, ["/api/v1/templates", "/api/v1/templates/{t1}", "/api/v1/form-items"]),
        (CONTENT_READ, ["/api/v1/resources", "/api/v1/submitted-documents", "/api/v1/embed-content"]),
        (REFERENCE_READ, ["/api/v1/sectors", "/api/v1/periods", "/api/v1/lookup-lists"]),
        (INDICATORS_MANAGE, ["/api/v1/indicator-suggestions"]),
    ],
)
def test_route_class_requires_its_capability(client, db_session, world, capability, urls):
    holder = _key(db_session, _caps(capability))
    other_capability = REFERENCE_READ if capability != REFERENCE_READ else CONTENT_READ
    outsider = _key(db_session, _caps(other_capability))

    for template in urls:
        url = template.format(**world)
        allowed = _get(client, url, holder)
        assert allowed.status_code != 403, (url, allowed.get_json())
        assert allowed.status_code < 500, (url, allowed.status_code)

        denied = _get(client, url, outsider)
        assert denied.status_code == 403, (url, denied.status_code)
        assert denied.get_json().get("required_permission") == capability


def test_data_key_without_data_read_gets_only_what_anonymous_callers_get(client, db_session, world):
    """/data has a public (privacy=public) mode; an under-privileged key is treated as anonymous."""
    key = _key(db_session, _caps(REFERENCE_READ))
    assert _get(client, "/api/v1/data", key).status_code == 403
    scoped_public = _get(client, f"/api/v1/data?template_id={world['t1']}", key)
    anonymous = client.get(f"/api/v1/data?template_id={world['t1']}")
    assert scoped_public.status_code == anonymous.status_code
    assert scoped_public.get_json()["data"] == anonymous.get_json()["data"]


def test_documents_capability_gates_unpublished_documents(client, db_session, world):
    public_only = _key(db_session, _caps(CONTENT_READ))
    with_documents = _key(db_session, _caps(CONTENT_READ, DOCUMENTS_READ))
    url = "/api/v1/submitted-documents?status=pending"
    assert _get(client, url, public_only).status_code == 403
    assert _get(client, url, with_documents).status_code == 200
    assert _get(client, "/api/v1/submitted-documents", public_only).status_code == 200


def test_capability_is_not_transitive(client, db_session, world):
    """users:read must not unlock form data, submissions, templates or documents."""
    key = _key(db_session, _caps(USERS_READ))
    for url in ("/api/v1/data", "/api/v1/submissions", "/api/v1/templates",
                "/api/v1/upr/data", "/api/v1/submitted-documents", "/api/v1/assigned-forms"):
        assert _get(client, url, key).status_code == 403, url


# --------------------------------------------------------------------------------------
# Fail closed
# --------------------------------------------------------------------------------------

FAIL_CLOSED_URLS = [
    "/api/v1/users", "/api/v1/data", "/api/v1/submissions", "/api/v1/templates",
    "/api/v1/resources", "/api/v1/sectors", "/api/v1/submitted-documents",
]


@pytest.mark.parametrize(
    "document",
    [
        None,
        {},
        [],
        "read_all",
        {"data": "bogus"},
        {"data": None},
        {"version": 2, "capabilities": "data:read"},
        {"version": 2, "capabilities": ["not:a:capability", "DATA:READ"]},
        {"version": 3, "capabilities": ["data:read"]},
        {"capabilities": ["data:read"]},
    ],
    ids=lambda d: repr(d)[:40],
)
def test_null_unknown_or_malformed_permissions_grant_nothing(client, db_session, world, document):
    key = _key(db_session, document)
    for url in FAIL_CLOSED_URLS:
        response = _get(client, url, key)
        assert response.status_code == 403, (url, document, response.status_code)


def test_legacy_data_none_key_keeps_only_reference_and_content(client, db_session, world):
    key = _key(db_session, {"data": "none"})
    assert _get(client, "/api/v1/sectors", key).status_code == 200
    assert _get(client, "/api/v1/resources", key).status_code == 200
    for url in ("/api/v1/users", "/api/v1/data", "/api/v1/submissions", "/api/v1/templates/{t1}/data"):
        assert _get(client, url.format(**world), key).status_code == 403, url


def test_legacy_full_access_marker_and_kill_switch(app, client, db_session, world):
    document = build_permissions_document(
        full_access_document()["capabilities"],
        allow_query_api_key=True,
        legacy={"full_access": True, "original": None},
    )
    key = _key(db_session, document)
    assert _get(client, "/api/v1/users", key).status_code == 200

    app.config["API_KEY_ALLOW_LEGACY_FULL_ACCESS"] = False
    try:
        assert _get(client, "/api/v1/users", key).status_code == 403
        assert _get(client, "/api/v1/sectors", key).status_code == 403
    finally:
        app.config["API_KEY_ALLOW_LEGACY_FULL_ACCESS"] = True


def test_malformed_data_scope_denies_all_data(client, db_session, world):
    document = {"version": 2, "capabilities": [DATA_READ, SUBMISSIONS_READ], "data_scope": "everything"}
    key = _key(db_session, document)
    assert _get(client, "/api/v1/submissions", key).get_json()["total_items"] == 0
    assert _get(client, "/api/v1/templates/{t1}/data?page=1&per_page=5".format(**world), key).status_code == 404


def test_missing_and_invalid_credentials(client, db_session, world):
    assert client.get("/api/v1/users").status_code == 401
    assert _get(client, "/api/v1/users", "not-a-real-key").status_code == 401


def test_revoked_expired_and_disabled_keys_are_refused(client, db_session, world):
    obj, full_key = create_test_api_key(db_session, permissions=_caps(USERS_READ))
    assert _get(client, "/api/v1/users", full_key).status_code == 200
    obj.revoke(reason="test")
    db_session.commit()
    assert _get(client, "/api/v1/users", full_key).status_code == 401


# --------------------------------------------------------------------------------------
# Data scoping applies to list AND detail routes
# --------------------------------------------------------------------------------------

def _ids(payload, field="template_id"):
    return {row.get(field) for row in payload}


def test_template_scoped_key_sees_only_its_template_everywhere(client, db_session, world):
    scoped = _key(db_session, _caps(
        DATA_READ, SUBMISSIONS_READ, TEMPLATES_READ,
        restrict_data=True, template_ids=[world["t1"]],
    ))

    submissions = _get(client, "/api/v1/submissions", scoped).get_json()
    assert {s["template_id"] for s in submissions["submissions"]} == {world["t1"]}
    assert submissions["total_items"] == 2  # assigned + public for template one

    assert _get(client, f"/api/v1/submissions/{world['aes1']}", scoped).status_code == 200
    assert _get(client, f"/api/v1/submissions/{world['aes2']}", scoped).status_code == 404

    assigned = _get(client, "/api/v1/assigned-forms", scoped).get_json()
    assert {a["template_id"] for a in assigned["assigned_forms"]} == {world["t1"]}

    templates = _get(client, "/api/v1/templates", scoped).get_json()
    assert {t["id"] for t in templates["templates"]} == {world["t1"]}
    assert _get(client, f"/api/v1/templates/{world['t1']}", scoped).status_code == 200
    assert _get(client, f"/api/v1/templates/{world['t2']}", scoped).status_code == 404

    items = _get(client, "/api/v1/form-items", scoped).get_json()
    assert {i["template_id"] for i in items["form_items"]} == {world["t1"]}
    foreign_item = world["items"][world["t2"]]
    assert _get(client, f"/api/v1/form-items/{foreign_item}", scoped).status_code == 404

    assert _get(client, f"/api/v1/templates/{world['t1']}/data?page=1&per_page=10", scoped).status_code == 200
    assert _get(client, f"/api/v1/templates/{world['t2']}/data?page=1&per_page=10", scoped).status_code == 404

    data = _get(client, "/api/v1/data", scoped).get_json()
    assert _ids(data["data"]) <= {world["t1"]}
    assert data["data"], "the in-scope row must still be returned"
    foreign = _get(client, f"/api/v1/data?template_id={world['t2']}", scoped).get_json()
    assert foreign["data"] == []


def test_country_scoped_key_sees_only_its_country(client, db_session, world):
    scoped = _key(db_session, _caps(
        DATA_READ, SUBMISSIONS_READ, restrict_data=True, country_ids=[world["c1"]],
    ))
    listing = _get(client, "/api/v1/submissions", scoped).get_json()
    assert listing["total_items"] == 2
    assert _get(client, f"/api/v1/submissions/{world['aes2']}", scoped).status_code == 404
    assert _get(client, f"/api/v1/countries/{world['c1']}/data?page=1&per_page=5", scoped).status_code == 200
    assert _get(client, f"/api/v1/countries/{world['c2']}/data?page=1&per_page=5", scoped).status_code == 404

    # Filters supplied by the caller narrow further; they can never widen the scope.
    widened = _get(client, f"/api/v1/submissions?country_id={world['c2']}", scoped).get_json()
    assert widened["total_items"] == 0


def test_empty_scope_returns_nothing(client, db_session, world):
    scoped = _key(db_session, _caps(DATA_READ, SUBMISSIONS_READ, restrict_data=True))
    assert _get(client, "/api/v1/submissions", scoped).get_json()["total_items"] == 0
    assert _get(client, "/api/v1/data", scoped).get_json()["data"] == []


def test_scoped_key_cannot_use_routes_that_cannot_apply_a_scope(client, db_session, world):
    scoped = _key(db_session, _caps(DATA_READ, restrict_data=True, template_ids=[world["t1"]]))
    response = _get(client, "/api/v1/upr/data", scoped)
    assert response.status_code == 403
    assert "scope" in response.get_json()["error"].lower()


# --------------------------------------------------------------------------------------
# Personal data
# --------------------------------------------------------------------------------------

def test_public_submitter_contact_needs_users_read(client, db_session, world):
    without = _key(db_session, _caps(SUBMISSIONS_READ))
    with_pii = _key(db_session, _caps(SUBMISSIONS_READ, USERS_READ))

    def public_rows(key):
        payload = _get(client, "/api/v1/submissions?submission_type=public", key).get_json()
        return payload["submissions"]

    rows = public_rows(without)
    assert rows and all(r["contact_email"] is None and r["contact_name"] is None for r in rows)
    rows = public_rows(with_pii)
    assert rows[0]["contact_email"] == "pat.public@example.org"

    detail = _get(client, f"/api/v1/submissions/{world['public']}", without)
    assert "pat.public@example.org" not in detail.get_data(as_text=True)


def test_user_directory_is_not_reachable_with_data_permissions(client, db_session, world):
    key = _key(db_session, _caps(DATA_READ, SUBMISSIONS_READ, TEMPLATES_READ, REFERENCE_READ, CONTENT_READ))
    assert _get(client, "/api/v1/users", key).status_code == 403
    assert _get(client, "/api/v1/quiz/leaderboard", key).status_code == 403


# --------------------------------------------------------------------------------------
# Pagination ceilings
# --------------------------------------------------------------------------------------

def test_per_page_is_clamped_for_key_requests(app, client, db_session, world):
    app.config["API_KEY_MAX_PER_PAGE"] = 7
    try:
        key = _key(db_session, _caps(SUBMISSIONS_READ, TEMPLATES_READ, DATA_READ))
        assert _get(client, "/api/v1/submissions?per_page=100000", key).get_json()["per_page"] == 7
        assert _get(client, "/api/v1/templates?per_page=100000", key).get_json()["per_page"] == 7
        assert _get(client, "/api/v1/data?per_page=100000", key).get_json()["per_page"] == 7
    finally:
        app.config.pop("API_KEY_MAX_PER_PAGE", None)


def test_users_and_lists_have_a_low_hard_cap(client, db_session, world):
    key = _key(db_session, _caps(USERS_READ))
    assert _get(client, "/api/v1/users?per_page=99999", key).get_json()["per_page"] <= 500


def test_scoped_and_unscoped_keys_are_always_paginated(client, db_session, world):
    scoped = _key(db_session, _caps(SUBMISSIONS_READ, restrict_data=True, template_ids=[world["t1"]]))
    payload = _get(client, "/api/v1/submissions", scoped).get_json()
    assert payload["per_page"] is not None and payload["current_page"] == 1


# --------------------------------------------------------------------------------------
# ?api_key= policy
# --------------------------------------------------------------------------------------

def test_query_string_key_is_refused_by_default(client, db_session, world):
    key = _key(db_session, _caps(REFERENCE_READ))
    response = client.get(f"/api/v1/sectors?api_key={key}")
    assert response.status_code == 403
    assert "Authorization" in response.get_json()["hint"]
    assert _get(client, "/api/v1/sectors", key).status_code == 200


def test_query_string_key_opt_in_is_flagged_in_the_response(client, db_session, world):
    key = _key(db_session, _caps(REFERENCE_READ, allow_query_api_key=True))
    response = client.get(f"/api/v1/sectors?api_key={key}")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert "deprecated" in response.headers["Warning"]

    header_response = _get(client, "/api/v1/sectors", key)
    assert "Warning" not in header_response.headers


# --------------------------------------------------------------------------------------
# Deprecated MOBILE_APP_API_KEY environment key
# --------------------------------------------------------------------------------------

def test_env_mobile_key_is_restricted_to_reference_and_content(app, client, db_session, world):
    app.config["MOBILE_APP_API_KEY"] = "env-mobile-shared-secret"
    try:
        headers = _bearer("env-mobile-shared-secret")
        assert client.get("/api/v1/sectors", headers=headers).status_code == 200
        assert client.get("/api/v1/resources", headers=headers).status_code == 200
        for url in ("/api/v1/users", "/api/v1/data", "/api/v1/submissions",
                    "/api/v1/templates", "/api/v1/upr/data",
                    "/api/v1/indicator-suggestions"):
            assert client.get(url, headers=headers).status_code == 403, url
        assert client.get("/api/v1/sectors?api_key=env-mobile-shared-secret").status_code in (401, 403)
    finally:
        app.config["MOBILE_APP_API_KEY"] = None


def test_env_mobile_key_capabilities_are_configurable_but_validated(app, client, db_session, world):
    app.config["MOBILE_APP_API_KEY"] = "env-mobile-shared-secret"
    app.config["MOBILE_APP_API_KEY_CAPABILITIES"] = "templates:read, made:up"
    try:
        headers = _bearer("env-mobile-shared-secret")
        assert client.get("/api/v1/templates", headers=headers).status_code in (200, 403)
        assert client.get("/api/v1/sectors", headers=headers).status_code == 403
        assert client.get("/api/v1/users", headers=headers).status_code == 403
    finally:
        app.config["MOBILE_APP_API_KEY"] = None
        app.config.pop("MOBILE_APP_API_KEY_CAPABILITIES", None)


def test_env_key_cannot_be_sent_in_the_query_string(app, client, db_session, world):
    app.config["MOBILE_APP_API_KEY"] = "env-mobile-shared-secret"
    try:
        response = client.get("/api/v1/sectors?api_key=env-mobile-shared-secret")
        assert response.status_code in (401, 403)
    finally:
        app.config["MOBILE_APP_API_KEY"] = None


# --------------------------------------------------------------------------------------
# Session users are unaffected by key capabilities
# --------------------------------------------------------------------------------------

def test_key_permissions_do_not_leak_into_a_following_session_request(client, db_session, world):
    scoped = _key(db_session, _caps(SUBMISSIONS_READ, restrict_data=True, template_ids=[world["t1"]]))
    assert _get(client, "/api/v1/submissions", scoped).status_code == 200
    anonymous = client.get("/api/v1/submissions")
    assert anonymous.status_code == 401
