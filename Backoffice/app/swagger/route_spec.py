"""
Build OpenAPI operations from the live Flask url map.

Paths, methods, path parameters, and authentication come from registered
``/api/v1`` routes and the ``_ep_auth`` / ``_ep_capability`` markers set by
``app.utils.auth``. Hand-written overlays (query parameters, response schemas)
are merged on top so new routes show up without a manual spec edit.
"""
from __future__ import annotations

import inspect
import re
from typing import Any, Dict, Iterable, List, Optional

_SKIP_METHODS = frozenset({"HEAD", "OPTIONS"})
_API_PREFIX = "/api/v1"
_CONVERTER = re.compile(r"<(?:([^:>]+):)?([^>]+)>")
_AUTH_MENTION = re.compile(r"authentication|no auth|intentionally public|public read", re.I)

_CONVERTER_SCHEMA = {
    "int": {"type": "integer"},
    "float": {"type": "number"},
    "uuid": {"type": "string", "format": "uuid"},
    "path": {"type": "string"},
    "string": {"type": "string"},
}

# First URL segment -> (tag name, tag description).
_TAG_BY_SEGMENT = {
    "countrymap": ("Countries", "Countries, national societies, and reporting periods."),
    "periods": ("Countries", "Countries, national societies, and reporting periods."),
    "nationalsocietymap": ("Countries", "Countries, national societies, and reporting periods."),
    "countries": ("Countries", "Countries, national societies, and reporting periods."),
    "indicator-bank": ("Indicator bank", "Indicator bank, suggestions, sectors, subsectors, and common words."),
    "indicator-suggestions": ("Indicator bank", "Indicator bank, suggestions, sectors, subsectors, and common words."),
    "sectors": ("Indicator bank", "Indicator bank, suggestions, sectors, subsectors, and common words."),
    "subsectors": ("Indicator bank", "Indicator bank, suggestions, sectors, subsectors, and common words."),
    "sectors-subsectors": ("Indicator bank", "Indicator bank, suggestions, sectors, subsectors, and common words."),
    "common-words": ("Indicator bank", "Indicator bank, suggestions, sectors, subsectors, and common words."),
    "templates": ("Templates", "Form templates, form items, and lookup lists."),
    "form-items": ("Templates", "Form templates, form items, and lookup lists."),
    "lookup-lists": ("Templates", "Form templates, form items, and lookup lists."),
    "data": ("Data", "Submitted form data."),
    "submissions": ("Submissions", "Assigned and public form submissions."),
    "assigned-forms": ("Assignments", "Assigned forms visible to an API key."),
    "resources": ("Resources", "Published resources."),
    "embed-content": ("Resources", "Published resources."),
    "submitted-documents": ("Documents", "Submitted documents."),
    "public": ("Public", "Unauthenticated integration endpoints for assistants and public data."),
    "fdrs": ("FDRS", "Published FDRS figures for a public website."),
    "nsd-funds": ("NSD funds", "NSD fund deadlines, projects, and implementation KPIs."),
    "nskeydata": ("NS key data", "Approved National Society key indicators by country and year."),
    "upr": ("UPR", "Unified Plan and Report extracts, plus the public document catalogue."),
}


def _unwrap_attr(view, name):
    seen = 0
    while view is not None and seen < 20:
        value = getattr(view, name, None)
        if value is not None:
            return value
        view = getattr(view, "__wrapped__", None)
        seen += 1
    return None


def _wrapped_functions(view) -> Iterable[Any]:
    seen = 0
    while view is not None and seen < 20:
        yield view
        view = getattr(view, "__wrapped__", None)
        seen += 1


def _has_login_required(view) -> bool:
    """True when Flask-Login's login_required (or fresh_login_required) wraps the view.

    functools.wraps copies the wrapped function's __qualname__ onto the wrapper,
    so the decorator name is not visible there. The wrapper's code object still
    lives in flask_login.
    """
    for fn in _wrapped_functions(view):
        code = getattr(fn, "__code__", None)
        if code is None:
            continue
        filename = (code.co_filename or "").replace("\\", "/")
        if code.co_name == "decorated_view" and "flask_login" in filename:
            return True
    return False


# First-party app routes. They stay on the server and out of this document:
# session helpers, browser telemetry, the form editor, and retired paths.
_OMITTED_PREFIXES = (
    "/csrf-token",
    "/platform-error",
    "/client-error",
    "/dashboard",
    "/matrix",
    "/variables",
    "/validation-questions",
    "/quiz",
    "/users",
    "/user",
    "/uploads",
    "/data/tables",
)


def is_omitted_from_spec(path: str) -> bool:
    """True when a live route is not part of the public integration contract."""
    for prefix in _OMITTED_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def flask_rule_to_openapi(rule: str) -> str:
    """``/api/v1/indicator-bank/<int:indicator_id>`` -> ``/indicator-bank/{indicator_id}``."""
    path = rule
    if path.startswith(_API_PREFIX):
        path = path[len(_API_PREFIX):] or "/"
    path = _CONVERTER.sub(lambda match: "{" + match.group(2) + "}", path)
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return path or "/"


def _path_parameters(rule: str) -> List[dict]:
    params = []
    for match in _CONVERTER.finditer(rule):
        converter, name = match.group(1), match.group(2)
        schema = dict(_CONVERTER_SCHEMA.get(converter) or {"type": "string"})
        params.append({
            "name": name,
            "in": "path",
            "required": True,
            "schema": schema,
        })
    return params


def _auth_mode(view) -> str:
    auth = _unwrap_attr(view, "_ep_auth")
    if auth in ("api_key", "api_key_or_session"):
        return auth
    if _has_login_required(view):
        return "session"
    return "public"


def _security_for(mode: str) -> List[dict]:
    if mode == "api_key":
        return [{"BearerAuth": []}, {"ApiKeyAuth": []}]
    if mode == "api_key_or_session":
        return [{"BearerAuth": []}, {"ApiKeyAuth": []}, {"SessionAuth": []}]
    if mode == "session":
        return [{"SessionAuth": []}]
    return []


def _auth_blurb(view, mode: str, method: str) -> str:
    capability = _unwrap_attr(view, "_ep_capability")
    scope_aware = bool(_unwrap_attr(view, "_ep_scope_aware"))
    if mode == "api_key":
        text = "Authentication: API key via `Authorization: Bearer` or the `X-API-Key` header."
    elif mode == "api_key_or_session":
        text = (
            "Authentication: API key (`Authorization: Bearer` or `X-API-Key`) or a logged-in session. "
            "Try it out on this page sends an API key only."
        )
    elif mode == "session":
        text = (
            "Authentication: logged-in session cookie. An API key is not accepted, "
            "so Try it out on this page cannot call this route."
        )
    else:
        text = "Authentication: none. This route is public."
    if capability:
        text += f" Requires capability `{capability}`."
    if scope_aware:
        text += " Data-scoped keys only see the templates and countries on the key."
    if mode in ("session", "api_key_or_session") and method not in ("get", "head"):
        text += " Browser session writes also send `X-CSRFToken` from `GET /csrf-token`."
    return text


def _summary(doc: str, method: str, path: str) -> str:
    line = ""
    for raw in (doc or "").splitlines():
        stripped = raw.strip()
        if stripped:
            line = stripped
            break
    if not line:
        return f"{method.upper()} {path}"
    if len(line) > 140:
        line = line[:137].rstrip() + "..."
    return line


def _tag_for(path: str) -> str:
    segment = path.strip("/").split("/", 1)[0] if path.strip("/") else "api"
    name, _description = _TAG_BY_SEGMENT.get(segment, (segment.replace("-", " ").title(), f"Routes under /{segment}."))
    return name


def tag_definitions(used: Iterable[str]) -> List[dict]:
    used_set = set(used)
    descriptions = {}
    for name, description in _TAG_BY_SEGMENT.values():
        descriptions.setdefault(name, description)
    tags = []
    for name in sorted(used_set):
        tags.append({
            "name": name,
            "description": descriptions.get(name) or f"{name} endpoints.",
        })
    return tags


def _operation_id(name: str, method: str, multi: bool, used: set) -> str:
    candidate = f"{name}_{method}" if multi else name
    if candidate in used:
        candidate = f"{name}_{method}"
    suffix = 2
    base = candidate
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _base_responses(mode: str) -> Dict[str, Any]:
    responses: Dict[str, Any] = {
        "200": {
            "description": "Success",
            "content": {"application/json": {"schema": {"type": "object"}}},
        },
        "400": {"$ref": "#/components/responses/BadRequest"},
        "500": {"$ref": "#/components/responses/ServerError"},
    }
    if mode != "public":
        responses["401"] = {"$ref": "#/components/responses/Unauthorized"}
    if mode in ("api_key", "api_key_or_session"):
        responses["403"] = {"$ref": "#/components/responses/Forbidden"}
    return responses


def _auto_operation(view, rule: str, method: str, path: str, operation_id: str) -> dict:
    doc = inspect.getdoc(view) or ""
    mode = _auth_mode(view)
    description = doc.strip()
    blurb = _auth_blurb(view, mode, method)
    if not _AUTH_MENTION.search(description):
        description = (description + "\n\n" + blurb).strip()
    elif _unwrap_attr(view, "_ep_capability") and f"`{_unwrap_attr(view, '_ep_capability')}`" not in description:
        description = (description + "\n\n" + blurb).strip()
    operation = {
        "tags": [_tag_for(path)],
        "summary": _summary(doc, method, path),
        "description": description or blurb,
        "operationId": operation_id,
        "parameters": _path_parameters(rule),
        "responses": _base_responses(mode),
        "security": _security_for(mode),
    }
    if not operation["parameters"]:
        operation.pop("parameters")
    return operation


def _param_key(param: dict):
    ref = param.get("$ref")
    if ref:
        return ("$ref", ref)
    return (param.get("in"), param.get("name"))


def _merge_parameters(auto_params: List[dict], overlay_params: List[dict]) -> List[dict]:
    merged = {_param_key(p): p for p in auto_params}
    order = [_param_key(p) for p in auto_params]
    for param in overlay_params:
        key = _param_key(param)
        if key not in merged:
            order.append(key)
        merged[key] = param
    return [merged[key] for key in order]


def _merge_operation(auto: dict, overlay: Optional[dict]) -> dict:
    if not overlay:
        return auto
    overlay = dict(overlay)
    extra = overlay.pop("description_extra", None)
    replace_responses = overlay.pop("x-replace-responses", False)
    merged = dict(auto)
    for key, value in overlay.items():
        if key == "parameters":
            merged["parameters"] = _merge_parameters(auto.get("parameters") or [], value)
        elif key == "responses":
            if replace_responses:
                merged["responses"] = dict(value)
            else:
                responses = dict(auto.get("responses") or {})
                responses.update(value)
                merged["responses"] = responses
        else:
            merged[key] = value
    if extra:
        merged["description"] = ((merged.get("description") or "") + "\n\n" + extra).strip()
    if not merged.get("parameters"):
        merged.pop("parameters", None)
    return merged


def iter_v1_rules(app):
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith(_API_PREFIX + "/") and rule.rule != _API_PREFIX:
            continue
        methods = sorted(m.lower() for m in (rule.methods or set()) - _SKIP_METHODS)
        if not methods:
            continue
        view = app.view_functions.get(rule.endpoint)
        if view is None:
            continue
        yield rule, view, methods


def build_paths(app, overlays: Optional[Dict[str, dict]] = None) -> Dict[str, dict]:
    """OpenAPI paths for documented ``/api/v1`` routes."""
    overlays = overlays or {}
    paths: Dict[str, dict] = {}
    used_ids: set = set()

    for rule, view, methods in iter_v1_rules(app):
        path = flask_rule_to_openapi(rule.rule)
        if is_omitted_from_spec(path):
            continue
        path_item = paths.setdefault(path, {})
        name = getattr(view, "__name__", None) or rule.endpoint.rsplit(".", 1)[-1]
        multi = len(methods) > 1
        for method in methods:
            operation_id = _operation_id(name, method, multi, used_ids)
            auto = _auto_operation(view, rule.rule, method, path, operation_id)
            key = f"{method.upper()} {path}"
            path_item[method] = _merge_operation(auto, overlays.get(key))
    return paths
