"""
OpenAPI 3.0 specification for the Backoffice ``/api/v1`` API.

The path list is generated from the live Flask url map (see ``route_spec``).
Overlays add query parameters and response schemas that the route scan cannot
see. Mobile (``/api/mobile/v1``) and the legacy Indicator Bank compatibility
routes (``/Indicator``, ``/Sector``, ...) are separate surfaces and are not
part of this document.
"""
from __future__ import annotations

import os

from app.swagger.overlays import operation_overlays
from app.swagger.route_spec import build_paths, tag_definitions


def _org_name() -> str:
    org_name = "Humanitarian Databank"
    try:
        from flask import has_app_context
        if has_app_context():
            from app.utils.organization_helpers import get_org_name as _get_org_name
            org_name = _get_org_name()
    except Exception:
        pass
    return org_name


def _contact(org_name: str) -> dict:
    contact = {"name": f"{org_name} API Support"}
    try:
        from flask import has_app_context
        if has_app_context():
            from app.utils.organization_helpers import get_org_team_email
            email = get_org_team_email()
            if email:
                contact["email"] = email
    except Exception:
        pass
    return contact


def _servers() -> list:
    """One server, so Swagger UI does not offer a host dropdown.

    A request always documents the host that served it. Try it out then
    cannot send a pasted API key to a different environment. Localhost is
    only the fallback when there is no request (tests and offline generation).
    """
    try:
        from flask import has_request_context, request
        if has_request_context():
            origin = (request.host_url or "").rstrip("/")
            if origin:
                return [{
                    "url": f"{origin}/api/v1",
                    "description": "The server that served this page.",
                }]
    except Exception:
        pass

    configured = (os.environ.get("API_BASE_URL") or "").strip().rstrip("/")
    if configured:
        return [{"url": f"{configured}/api/v1", "description": "API_BASE_URL"}]
    return [{"url": "http://localhost:5000/api/v1", "description": "Local development"}]


def _components() -> dict:
    return {
        "securitySchemes": {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "API Key",
                "description": "Database-managed API key in the Authorization header: `Bearer <key>`.",
            },
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key",
                "description": "Same API key in the X-API-Key header. Query-string keys are deprecated and only work for keys that opted in.",
            },
            "SessionAuth": {
                "type": "apiKey",
                "in": "cookie",
                "name": "session",
                "description": "A logged-in Backoffice session is accepted on some routes. Try it out on this page sends an API key only, so a route that accepts a session and nothing else cannot be called from this page.",
            },
        },
        "schemas": {
            "Error": {
                "type": "object",
                "description": "Error body from api_error(). `success` is not part of this payload.",
                "properties": {
                    "error": {"type": "string", "example": "Could not fetch indicator bank data"},
                    "error_id": {
                        "type": "string",
                        "format": "uuid",
                        "example": "123e4567-e89b-12d3-a456-426614174000",
                    },
                    "debug": {
                        "type": "string",
                        "description": "Present only when the server is in debug mode.",
                    },
                },
                "required": ["error", "error_id"],
            },
            "Country": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "example": 1},
                    "name": {"type": "string", "example": "Afghanistan"},
                    "localized_name": {"type": "string"},
                    "iso2": {"type": "string", "example": "AF"},
                    "iso3": {"type": "string", "example": "AFG"},
                    "region": {"type": "string", "example": "Asia Pacific"},
                    "multilingual_names": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "description": "Country names in languages other than English.",
                    },
                    "national_society_name": {"type": "string"},
                },
            },
            "Indicator": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "definition": {"type": "string"},
                    "type": {"type": "string"},
                    "type_translations": {"type": "object", "additionalProperties": {"type": "string"}},
                    "unit": {"type": "string"},
                    "unit_translations": {"type": "object", "additionalProperties": {"type": "string"}},
                    "sector": {"type": "object"},
                    "archived": {"type": "boolean"},
                },
            },
            "Template": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "created_at": {"type": "string", "format": "date-time"},
                    "sections_count": {"type": "integer"},
                    "pages_count": {"type": "integer"},
                    "items_count": {"type": "integer"},
                },
            },
            "Submission": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "type": {"type": "string", "description": "assigned or public"},
                    "template_id": {"type": "integer"},
                    "period_name": {"type": "string"},
                    "status": {"type": "string"},
                    "submitted_at": {"type": "string", "format": "date-time"},
                    "country_info": {"type": "object"},
                },
            },
            "Pagination": {
                "type": "object",
                "description": (
                    "List endpoints on this API use total_items, total_pages, and current_page. "
                    "page, per_page, total, and pages are kept for clients that still look for those names."
                ),
                "properties": {
                    "page": {"type": "integer", "example": 1},
                    "per_page": {"type": "integer", "example": 20},
                    "total": {"type": "integer", "example": 100},
                    "pages": {"type": "integer", "example": 5},
                    "total_items": {"type": "integer"},
                    "total_pages": {"type": "integer"},
                    "current_page": {"type": "integer"},
                },
            },
        },
        "parameters": {
            "PageParam": {
                "name": "page",
                "in": "query",
                "description": "Page number (1-indexed).",
                "required": False,
                "schema": {"type": "integer", "minimum": 1, "default": 1},
            },
            "PerPageParam": {
                "name": "per_page",
                "in": "query",
                "description": "Page size. The default and the maximum depend on the endpoint and on API_KEY_MAX_PER_PAGE.",
                "required": False,
                "schema": {"type": "integer", "minimum": 1},
            },
            "LocaleParam": {
                "name": "locale",
                "in": "query",
                "description": "Locale code for localized labels (en, fr, es, ar, zh, ru, hi).",
                "required": False,
                "schema": {"type": "string", "default": "en"},
            },
        },
        "responses": {
            "Unauthorized": {
                "description": "Missing or invalid API key, or no session on a session-only route.",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
            },
            "Forbidden": {
                "description": "Authenticated, but the key lacks the required capability or is out of scope.",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
            },
            "NotFound": {
                "description": "Resource not found, or hidden because the key is out of scope.",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
            },
            "BadRequest": {
                "description": "Invalid parameters or JSON body.",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
            },
            "ServerError": {
                "description": "Internal server error. `error_id` correlates with the server log.",
                "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
            },
        },
    }


def get_api_paths() -> dict:
    """OpenAPI paths relative to ``/api/v1``. Empty when there is no app context."""
    from flask import current_app, has_app_context
    if not has_app_context():
        return {}
    return build_paths(current_app._get_current_object(), operation_overlays())


def get_openapi_spec() -> dict:
    """OpenAPI 3.0 document for the routes registered on ``/api/v1``."""
    org_name = _org_name()
    paths = get_api_paths()
    used_tags = []
    for item in paths.values():
        for operation in item.values():
            if isinstance(operation, dict):
                used_tags.extend(operation.get("tags") or [])

    return {
        "openapi": "3.0.3",
        "info": {
            "title": f"{org_name} API",
            "description": (
                f"Integration API for the {org_name}. It covers the data an API key or a public client can read: "
                "countries, the indicator bank, templates, submissions, form data, resources, documents, and the "
                "public assistant endpoints. "
                "Click Authorize and paste a key. Swagger sends `Authorization: Bearer` or `X-API-Key`. "
                "Public routes can be tried with no key. "
                "A route that accepts only a logged-in session cannot be called with an API key. "
                "Session helpers, the form editor, browser error reports, the mobile API (`/api/mobile/v1`), "
                "and the legacy Indicator Bank routes (`/Indicator`, `/Sector`, `/Subsector`) are separate and are not listed here."
            ),
            "version": "1.0.0",
            "contact": _contact(org_name),
            "license": {"name": "Proprietary"},
        },
        "servers": _servers(),
        "tags": tag_definitions(used_tags),
        "components": _components(),
        "paths": paths,
    }
