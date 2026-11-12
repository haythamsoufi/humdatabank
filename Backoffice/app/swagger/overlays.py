"""
Response and query-parameter detail for routes whose docstring is not enough.

Authentication, path parameters, and the operation list come from the route
scan. Entries here only correct shapes that callers would otherwise guess wrong.
"""
from __future__ import annotations

from typing import Any, Dict


def _q(name: str, schema: dict, description: str, required: bool = False) -> dict:
    return {
        "name": name,
        "in": "query",
        "required": required,
        "description": description,
        "schema": schema,
    }


_INT = {"type": "integer"}
_STR = {"type": "string"}
_BOOL = {"type": "boolean"}

_PAGE = {"$ref": "#/components/parameters/PageParam"}
_PER_PAGE = {"$ref": "#/components/parameters/PerPageParam"}
_LOCALE = {"$ref": "#/components/parameters/LocaleParam"}

_PAGED_KEYS = {
    "total_items": {"type": "integer"},
    "total_pages": {"type": "integer"},
    "current_page": {"type": "integer"},
    "per_page": {"type": "integer"},
}


def _json(description: str, schema: dict) -> dict:
    return {
        "description": description,
        "content": {"application/json": {"schema": schema}},
    }


def _object(properties: Dict[str, Any]) -> dict:
    return {"type": "object", "properties": properties}


def _paged(array_name: str, item_schema: dict, extra: Dict[str, Any] | None = None) -> dict:
    properties = {array_name: {"type": "array", "items": item_schema}, **_PAGED_KEYS}
    if extra:
        properties.update(extra)
    return _object(properties)


def _rows(description: str, extra: Dict[str, Any] | None = None) -> dict:
    """``{data: [...], meta: {...}}`` envelope used by the newer read APIs."""
    properties: Dict[str, Any] = {
        "data": {"type": "array", "items": {"type": "object"}},
        "meta": {"type": "object"},
    }
    if extra:
        properties.update(extra)
    return _json(description, _object(properties))


def _upr_extract_parameters(*, template: bool = True, section: bool = True) -> list:
    """Filters shared by the keyed UPR extract routes."""
    params = []
    if template:
        params.append(_q(
            "template",
            {"type": "string", "enum": ["report", "plan", "pns"]},
            "Omit for every template kind.",
        ))
    params.append(_q("round", _STR, "Round codes, comma-separated or repeated. Example: MYR26,P27."))
    params.append(_q("iso3", _STR, "ISO3 country code. `country_iso3` is an alias."))
    params.append(_q("country_iso3", _STR, "Alias of `iso3`."))
    if section:
        params.append(_q(
            "section",
            _STR,
            "NS Data, Core indicators, Other indicators, Funding, Support, Activities, Reach, Emergencies, or Comments.",
        ))
    params.extend([
        _q("submission_id", _INT, "Limit to one submission."),
        _q("template_id", _INT, "Limit to one template id."),
        _q("country_id", _INT, "Limit to one country id."),
        _q("item_id", _INT, "Limit to one form item."),
        _q("assignment_id", _STR, "Assigned form id, or a comma-separated list. Repeated query params are accepted."),
        _q("country_iso2", _STR, "2-letter country code. `iso2` is an alias."),
        _q("iso2", _STR, "Alias of `country_iso2`."),
        _q("period_name", _STR, "Reporting period name."),
    ])
    return params


_NSD_UNAVAILABLE = {
    "description": "NSD source data is unavailable.",
    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
}


def operation_overlays() -> Dict[str, dict]:
    country = {"$ref": "#/components/schemas/Country"}
    indicator = {"$ref": "#/components/schemas/Indicator"}
    template = {"$ref": "#/components/schemas/Template"}
    submission = {"$ref": "#/components/schemas/Submission"}

    return {
        "GET /countrymap": {
            "parameters": [_LOCALE, _PAGE, _PER_PAGE],
            "description_extra": (
                "Without `page` / `per_page` the body is a JSON array of countries "
                "(cached, with an ETag). With either parameter the body is an object "
                "`{countries, total_items, total_pages, current_page, per_page}` and is not cached. "
                "`per_page` is capped at 200."
            ),
            "responses": {
                "200": _json(
                    "Country list (array, or a paged object when page/per_page is set)",
                    {
                        "oneOf": [
                            {"type": "array", "items": country},
                            _paged("countries", country),
                        ]
                    },
                ),
            },
        },
        "GET /periods": {
            "parameters": [
                _q("template_id", _INT, "Limit periods to one template."),
                _q("country_id", _INT, "Limit periods to one country."),
                _q("country_iso2", _STR, "Resolved to country_id."),
                _q("country_iso3", _STR, "Resolved to country_id."),
            ],
            "responses": {
                "200": _json("Period names", {"type": "array", "items": {"type": "string"}}),
            },
        },
        "GET /nationalsocietymap": {
            "parameters": [
                _LOCALE,
                _q("country_id", _INT, "Filter by country."),
                _q("is_active", _STR, "Filter by active status.", ),
                _PAGE,
                _PER_PAGE,
            ],
            "description_extra": (
                "Without pagination the body is a JSON array. With `page` and `per_page` "
                "the body is `{national_societies, total_items, total_pages, current_page, per_page}`."
            ),
            "responses": {
                "200": _json(
                    "National societies",
                    {
                        "oneOf": [
                            {"type": "array", "items": {"type": "object"}},
                            _paged("national_societies", {"type": "object"}),
                        ]
                    },
                ),
            },
        },
        "GET /indicator-bank": {
            "parameters": [
                _q("search", _STR, "Match indicator name or definition."),
                _q("type", _STR, "Filter by indicator type."),
                _q("sector", _STR, "Filter by sector name."),
                _q("sub_sector", _STR, "Filter by sub-sector name."),
                _q("emergency", _STR, "Filter by emergency type."),
                _q("archived", {"type": "string", "enum": ["true", "false"]}, "true = archived only, false = active only, omit = both."),
                _q("limit", _INT, "Cap this page's size (max 500). Does not replace paging."),
                _PAGE,
                _PER_PAGE,
            ],
            "description_extra": "Default page size is 100 and the maximum is 500. Follow `total` until the pages are exhausted.",
            "responses": {
                "200": _json(
                    "One page of indicators",
                    _object({
                        "indicators": {"type": "array", "items": indicator},
                        "total": {"type": "integer"},
                        "page": {"type": "integer"},
                        "per_page": {"type": "integer"},
                    }),
                ),
            },
        },
        "GET /indicator-bank/{indicator_id}": {
            "responses": {
                "200": _json("Indicator", indicator),
                "404": {"$ref": "#/components/responses/NotFound"},
            },
        },
        "GET /sectors": {
            "responses": {
                "200": _json("Active sectors, each with nested subsectors", _object({
                    "sectors": {"type": "array", "items": {"type": "object"}},
                })),
            },
        },
        "GET /subsectors": {
            "description_extra": "Returns every active subsector with its parent sector. There is no sector filter.",
            "responses": {
                "200": _json("Active subsectors", _object({
                    "subsectors": {"type": "array", "items": {"type": "object"}},
                })),
            },
        },
        "GET /sectors-subsectors": {
            "responses": {
                "200": _json("Sectors with nested subsectors", _object({
                    "sectors": {"type": "array", "items": {"type": "object"}},
                })),
            },
        },
        "GET /templates": {
            "parameters": [
                _q("search", _STR, "Case-insensitive match on template name or published description."),
                _PAGE,
                _PER_PAGE,
            ],
            "description_extra": (
                "There is no `active` filter. API-key calls default to 20 per page; "
                "session calls default to 500. Both are capped by API_KEY_MAX_PER_PAGE."
            ),
            "responses": {
                "200": _json("Template page", _paged("templates", template, {"search_query": {"type": "string"}})),
            },
        },
        "GET /templates/{template_id}": {
            "description_extra": "The body is the template object itself (pages, sections, items), not wrapped in `{template: ...}`. A key scoped away from this template gets 404.",
            "responses": {
                "200": _json("Template structure", template),
                "404": {"$ref": "#/components/responses/NotFound"},
            },
        },
        "GET /templates/{template_id}/data": {
            "parameters": [_PAGE, _PER_PAGE],
            "description_extra": "`page` and `per_page` are both required. The key must hold `data:read` and be in scope for the template.",
            "responses": {
                "200": _json("Form data page", {"type": "object"}),
                "400": {"$ref": "#/components/responses/BadRequest"},
                "404": {"$ref": "#/components/responses/NotFound"},
            },
        },
        "GET /countries/{country_id}/data": {
            "parameters": [_PAGE, _PER_PAGE],
            "description_extra": "`page` and `per_page` are both required.",
            "responses": {
                "200": _json("Form data page", {"type": "object"}),
                "404": {"$ref": "#/components/responses/NotFound"},
            },
        },
        "GET /data": {
            "parameters": [
                _q("layout", {"type": "string", "enum": ["flat", "star"], "default": "flat"}, "flat is the legacy bundle. star is the dimensional export."),
                _q("template_id", _INT, "Filter by template."),
                _q("assignment_id", _STR, "Assigned form id, or a comma-separated list. `assigned_form_id` is an alias. Repeated query params are accepted."),
                _q("submission_id", _INT, "Assignment entity status id."),
                _q("item_id", _INT, "Filter to one form item."),
                _q("stable_key", _STR, "UUID of a form item across template versions. Requires a single template."),
                _q("version_scope", {"type": "string", "enum": ["published", "all"]}, "Which form-item version `stable_key` resolves to."),
                _q("item_type", _STR, "Filter by form item type."),
                _q("country_id", _INT, "Filter by country."),
                _q("country_iso2", _STR, "Resolved to country_id."),
                _q("country_iso3", _STR, "Resolved to country_id."),
                _q("submission_type", _STR, "assigned or public."),
                _q("period_name", _STR, "Reporting period name."),
                _q("indicator_bank_id", _INT, "Filter to one indicator."),
                _q("indicator_bank_ids", _STR, "Comma-separated indicator bank ids."),
                _q("date_from", {"type": "string", "format": "date"}, "Lower bound on submitted_at."),
                _q("date_to", {"type": "string", "format": "date"}, "Upper bound on submitted_at."),
                _q("related", {"type": "string", "enum": ["page", "all"], "default": "page"}, "Scope of related form_items."),
                _q("include_dynamic", _BOOL, "Default true. false omits dynamic_data."),
                _q("include_repeat", _BOOL, "Default true. false omits repeat_data."),
                _q("include_dimensions", _BOOL, "Authenticated calls default to true (full countries, national societies, indicator bank). Public calls default to false."),
                _q("live", _BOOL, "true reloads dimension tables from the database instead of the worker cache."),
                _q("include_calculated_totals", _BOOL, "Default true. false drops calculated matrix totals."),
                _q("include_non_reported", _BOOL, "Include rows that were not reported."),
                _q("analysis", _BOOL, "Include analysis fields. Session callers need analysis permission."),
                _q("sort", _STR, "Sort field."),
                _q("order", _STR, "Sort direction."),
                _PAGE,
                _PER_PAGE,
            ],
            "description_extra": (
                "Unauthenticated calls are allowed only when scoped filters are present, and then "
                "only privacy=public items are returned (pagination required). "
                "`include_dimensions` defaults to true for authenticated callers and false for public callers. "
                "fact_form_values in the star layout includes static, dynamic, and repeat rows."
            ),
            "responses": {
                "200": _json("Flat bundle or star layout", {
                    "oneOf": [
                        _object({
                            "data": {"type": "array", "items": {"type": "object"}},
                            "dynamic_data": {"type": "array", "items": {"type": "object"}},
                            "repeat_data": {"type": "array", "items": {"type": "object"}},
                            "dynamic_context": {"type": "array", "items": {"type": "object"}},
                            "form_items": {"type": "array", "items": {"type": "object"}},
                            "countries": {"type": "array", "items": {"type": "object"}},
                            "national_societies": {"type": "array", "items": {"type": "object"}},
                            "indicator_bank": {"type": "array", "items": {"type": "object"}},
                            "matrix_cells": {"type": "array", "items": {"type": "object"}},
                            "total_items": {"type": "integer"},
                            "total_pages": {"type": "integer"},
                            "current_page": {"type": "integer"},
                            "per_page": {"type": "integer"},
                        }),
                        _object({
                            "data": _object({
                                "schema_version": {"type": "string"},
                                "grain": {"type": "string"},
                                "tables": {"type": "object"},
                            }),
                            "meta": {"type": "object"},
                        }),
                    ]
                }),
            },
        },
        "GET /submissions": {
            "parameters": [
                _q("template_id", _INT, "Filter by template."),
                _q("country_id", _INT, "Filter by country."),
                _q("submission_type", {"type": "string", "enum": ["assigned", "public"]}, "Filter by submission type."),
                _PAGE,
                _PER_PAGE,
            ],
            "description_extra": (
                "API-key responses are paginated and limited to the key's scope. "
                "Session responses are not paginated (`total_pages` is null). "
                "Public-submission contact fields are included only when the key also holds `users:read`."
            ),
            "responses": {
                "200": _json("Submissions", _paged("submissions", submission)),
            },
        },
        "GET /submissions/{submission_id}": {
            "description_extra": "The body is the submission object itself, including its data rows.",
            "responses": {
                "200": _json("Submission", submission),
                "404": {"$ref": "#/components/responses/NotFound"},
            },
        },
        "GET /resources": {
            "parameters": [
                _q("search", _STR, "Match resource title."),
                _q("resource_type", _STR, "publication or other."),
                _q("language", _STR, "Translation language. Default en."),
                _PAGE,
                _PER_PAGE,
            ],
            "description_extra": "Default page size is 10, maximum 500. The body is not wrapped in `success`.",
            "responses": {
                "200": _json("Resource page", _paged("resources", {"type": "object"}, {
                    "search_query": {"type": "string"},
                    "resource_type_filter": {"type": "string"},
                    "language": {"type": "string"},
                })),
            },
        },
        "GET /common-words": {
            "parameters": [
                _q("language", _STR, "Translation language. Default en. This is not the `locale` parameter used by countrymap."),
            ],
            "responses": {
                "200": _json("Common words", _object({
                    "success": {"type": "boolean"},
                    "common_words": {
                        "type": "array",
                        "items": _object({
                            "id": {"type": "integer"},
                            "term": {"type": "string"},
                            "meaning": {"type": "string"},
                            "language": {"type": "string"},
                        }),
                    },
                    "total": {"type": "integer"},
                })),
            },
        },
        "POST /indicator-suggestions": {
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": _object({
                    "submitter_name": {"type": "string"},
                    "submitter_email": {"type": "string", "format": "email"},
                    "suggestion_type": {"type": "string"},
                    "indicator_name": {"type": "string"},
                    "reason": {"type": "string"},
                    "sector": {"type": "object"},
                    "sub_sector": {"type": "object"},
                })}},
            },
            "description_extra": "Required JSON fields: submitter_name, submitter_email, suggestion_type, indicator_name, reason.",
        },
        "GET /public/global-trend": {
            "parameters": [
                _q("indicator_bank_id", _INT, "Indicator to total. Alternative to `query`."),
                _q("query", _STR, "Natural-language metric name, resolved server-side."),
                _q("period_name", _STR, "Limit to one reporting period."),
                _q("max_pages", _INT, "Pages of public data to scan. Default 20."),
            ],
        },
        "GET /public/indicators/resolve": {
            "parameters": [
                _q("query", _STR, "Metric name to resolve.", required=True),
                _q("limit", _INT, "Maximum matches. Default 5, max 20."),
            ],
        },
        "GET /public/countries/resolve": {
            "parameters": [
                _q("query", _STR, "Country name, ISO2, ISO3, or numeric id.", required=True),
                _q("limit", _INT, "Maximum matches. Default 5, max 20."),
            ],
        },
        "GET /public/submissions/coverage": {
            "parameters": [
                _q("template_id", _INT, "21 FDRS, 24 Unified Country Plan, 33 country reporting, or another public template."),
                _q("indicator_bank_id", _INT, "Count countries that reported this indicator."),
                _q("query", _STR, "Metric name, used when indicator_bank_id is omitted."),
                _q("period_name", _STR, "One period, or omit for every period in range."),
                _q("country_id", _INT, "Limit the count to one country."),
                _q("max_pages", _INT, "Pages of public data to scan. Default 20."),
            ],
            "description_extra": "Counts public data rows only (data_status=available on privacy=public items). It is not assignment or workflow status.",
        },
        "GET /public/documents/search": {
            "parameters": [
                _q("query", _STR, "Search text. Required.", required=True),
                _q("top_k", _INT, "Chunk count when full_coverage is false. Default 8."),
                _q("min_score", {"type": "number"}, "Minimum relevance. Default 0.25."),
                _q("country_name", _STR, "Limit to one country by name."),
                _q("country_id", _INT, "Limit to one country by id."),
                _q("country_ids", _STR, "Comma-separated ids, or `all`."),
                _q("require_phrase", _STR, "Phrase that must appear in every returned chunk."),
                _q("file_type", _STR, "Limit by file type."),
                _q("search_mode", _STR, "hybrid (default) or another supported mode."),
                _q("full_coverage", _BOOL, "When true, page through countries instead of a single top_k."),
                _q("page", _INT, "Page, used with full_coverage."),
                _q("per_page", _INT, "Page size, used with full_coverage. Default 80."),
                _q("latest_per_country", _BOOL, "Keep the newest document per country."),
            ],
        },
        "GET /public/documents/catalog": {
            "parameters": [
                _q("document_type", _STR, "annual_report, unified_plan, emergency, or a collection alias such as dref."),
                _q("q", _STR, "Title or filename fragment (MDRSY014, UPL-2026) or a collection name."),
                _q("year", _INT, "Calendar year."),
                _q("country_id", _INT, "Limit to one country."),
                _q("country_name", _STR, "Limit to one country by name."),
                _q("file_type", _STR, "Limit by file type."),
                _q("include_documents", _BOOL, "Include document rows as well as counts. Default true."),
            ],
        },
        "GET /public/documents/{public_id}/download": {
            "description_extra": "Streams the file. The JSON error schema applies only when the document is missing.",
            "responses": {
                "200": {"description": "File bytes", "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}},
                "404": {"$ref": "#/components/responses/NotFound"},
            },
        },
        "GET /public/reports/country": {
            "parameters": [
                _q("country", _STR, "Country name, ISO code, or id.", required=True),
                _q("period_hint", _STR, "Free-text period, for example `2026 midyear`."),
                _q("report_type", _STR, "combined (default) or another supported report type."),
                _q("include_prior_period", _BOOL, "Include the previous period in the KPI bundle. Default true."),
                _q("template_style", _STR, "When set and the country resolves, `design_template` is added to the payload."),
            ],
            "description_extra": "An unresolved country is HTTP 200 with `ok=false` and `alternatives`, not an HTTP error. The endpoint returns JSON only.",
        },
        "GET /public/reports/template": {
            "parameters": [
                _q("style", _STR, "Layout name. Default `default`. An unknown style is HTTP 200 with `ok=false` and `available_styles`."),
            ],
        },
        "GET /nskeydata": {
            "parameters": [
                _q("iso2", _STR, "2-letter country code."),
                _q("iso3", _STR, "3-letter country code."),
                _q("year", _INT, "4-digit calendar year. Omit for every year."),
            ],
            "description_extra": (
                "One approved figure per country and year. Priority for that country and year is "
                "FDRS, then annual reporting, then mid-year reporting, then planning. "
                "The body is `{data, meta}`."
            ),
            "responses": {
                "200": _rows("National Society key figures"),
                "400": {"$ref": "#/components/responses/BadRequest"},
            },
        },
        "GET /upr/documents": {
            "parameters": [
                _q("q", _STR, "Title search. Capped at 120 characters."),
                _q("country", _STR, "Country name fragment."),
                _q("type", _INT, "Document type id."),
                _q("year", _INT, "Calendar year from 2000 to 2099. A value outside that range is ignored."),
                _q("sort", {"type": "string", "enum": ["newest", "oldest", "country_az", "country_za"], "default": "newest"}, "Sort order. An unknown value falls back to newest."),
                _q("format", {"type": "string", "enum": ["powerbi"]}, "When `powerbi`, the body is an iframe snippet instead of the full catalogue page."),
            ],
            "description_extra": "Returns HTML, not JSON. A rate limit is HTML with status 429 and `Retry-After: 60`.",
            "x-replace-responses": True,
            "responses": {
                "200": {
                    "description": "HTML catalogue, or an iframe snippet when format=powerbi.",
                    "content": {"text/html": {"schema": {"type": "string"}}},
                },
                "429": {"description": "Too many requests. HTML body."},
            },
        },
        "GET /fdrs/published-data": {
            "parameters": [
                _q("period_name", _STR, "Exact FDRS reporting period, for example 2024."),
                _q("assignment_id", _INT, "Assigned form id for one FDRS reporting round."),
                _q("indicator_bank_id", _INT, "Limit to one indicator."),
                _q("country_id", _INT, "Limit to one country."),
                _q("country_iso2", _STR, "2-letter country code."),
                _q("country_iso3", _STR, "3-letter country code."),
                _q("form_item_id", _INT, "Limit to one form item."),
                _q("page", _INT, "Page number. Default 1."),
                _q("per_page", _INT, "Page size. Default 20, maximum 10000."),
            ],
            "description_extra": (
                "Only published values on public FDRS (template 21) country assignments. "
                "The body is `{data, meta}` with `meta.total`, `page`, `per_page`, and `total_pages`."
            ),
            "responses": {
                "200": _rows("Published FDRS rows"),
            },
        },
        "GET /nsd-funds/deadlines": {
            "summary": "One row per NSD report deadline.",
            "parameters": [
                _q("reference", _STR, "Project reference."),
                _q("project_status", _STR, "Open, Closed, or an exact status such as Active or Archived."),
                _q("report_type", _STR, "CBF quarter or CBF final report."),
                _q("due_from", {"type": "string", "format": "date"}, "Lower bound on the due date (yyyy-mm-dd)."),
                _q("due_to", {"type": "string", "format": "date"}, "Upper bound on the due date (yyyy-mm-dd)."),
                _q("overdue", _STR, "true, 1, or yes keeps overdue deadlines only."),
                _q("active_only", _STR, "true, 1, or yes keeps active reports only."),
                _q("include_contacts", _STR, "true, 1, or yes adds NS focal and IFRC PM names and emails."),
                _q("page", _INT, "Page number. Default 1."),
                _q("per_page", _INT, "Page size. Default 1000, maximum 5000."),
            ],
            "description_extra": "API key with `submissions:read`. A browser session is not accepted. The body is `{data, meta}`.",
            "responses": {
                "200": _rows("NSD report deadlines"),
                "503": _NSD_UNAVAILABLE,
            },
        },
        "GET /nsd-funds/projects": {
            "summary": "One row per NSD project, including the latest implementation KPIs.",
            "parameters": [
                _q("project_status", _STR, "Open, Closed, or an exact status such as Active or Archived."),
                _q("country_iso3", _STR, "3-letter country code."),
                _q("include_contacts", _STR, "true, 1, or yes adds NS focal and IFRC PM names and emails."),
                _q("page", _INT, "Page number. Default 1."),
                _q("per_page", _INT, "Page size. Default 1000, maximum 5000."),
            ],
            "description_extra": "API key with `submissions:read`. A browser session is not accepted. The body is `{data, meta}`.",
            "responses": {
                "200": _rows("NSD projects"),
                "503": _NSD_UNAVAILABLE,
            },
        },
        "GET /nsd-funds/kpis": {
            "summary": "One row per NSD report with its implementation KPIs.",
            "parameters": [
                _q("reference", _STR, "Project reference."),
                _q("project_status", _STR, "Open, Closed, or an exact status such as Active or Archived."),
                _q("report_type", _STR, "CBF quarter or CBF final report."),
                _q("period", _STR, "Report period, for example Y1Q1."),
                _q("status", _STR, "Report status: pending, in_progress, submitted, or approved."),
                _q("page", _INT, "Page number. Default 1."),
                _q("per_page", _INT, "Page size. Default 1000, maximum 5000."),
            ],
            "description_extra": "API key with `submissions:read`. A browser session is not accepted. The body is `{data, meta}`.",
            "responses": {
                "200": _rows("NSD implementation KPIs"),
                "503": _NSD_UNAVAILABLE,
            },
        },
        "GET /upr": {
            "description_extra": "Returns the query-parameter and column catalogue for the UPR extracts. It does not return the data.",
            "responses": {
                "200": _json("Extract catalogue", {"type": "object"}),
            },
        },
        "GET /upr/data": {
            "parameters": _upr_extract_parameters(),
            "description_extra": "The body is `{data, submissions, meta}`. Comment answers are rows in `data`.",
            "responses": {
                "200": _rows("UPR facts", {"submissions": {"type": "array", "items": {"type": "object"}}}),
                "400": {"$ref": "#/components/responses/BadRequest"},
            },
        },
        "GET /upr/overall": {
            "parameters": [
                _q("iso3", _STR, "ISO3 country code. `country_iso3` is an alias."),
                _q("country_iso3", _STR, "Alias of `iso3`."),
                _q("year", _INT, "4-digit calendar year."),
                _q("section", _STR, "Section name. See GET /upr for the list."),
            ],
            "description_extra": "FDRS wins where both FDRS and Unified Reporting have a value. The body is `{data, meta}`.",
            "responses": {
                "200": _rows("Merged FDRS and Unified Reporting rows"),
                "400": {"$ref": "#/components/responses/BadRequest"},
            },
        },
        "GET /upr/submissions": {
            "parameters": _upr_extract_parameters(section=False),
            "description_extra": "The body is `{data, meta}`.",
            "responses": {
                "200": _rows("UPR assignment statuses"),
                "400": {"$ref": "#/components/responses/BadRequest"},
            },
        },
        "GET /upr/master": {
            "parameters": _upr_extract_parameters() + [
                _q("layout", {"type": "string", "enum": ["long", "wide", "detail"], "default": "long"}, "Row shape."),
            ],
            "description_extra": "The body is `{data, secondary_summary, meta}`.",
            "responses": {
                "200": _rows("UPR master rows", {"secondary_summary": {"type": "array", "items": {"type": "object"}}}),
                "400": {"$ref": "#/components/responses/BadRequest"},
            },
        },
    }

