"""Public integration endpoints optimized for Custom GPT Actions."""

from __future__ import annotations

import uuid

from flask import current_app, request

from app.routes.api import api_bp
from app.services.public.analytics_service import (
    aggregate_global_trend,
    aggregate_submission_coverage,
    resolve_country_query,
    resolve_indicator_query,
)
from app.services.public.document_service import (
    PublicDocumentScopeTooLarge,
    PublicDocumentSearchUnavailable,
    catalog_public_documents,
    get_public_document_metadata,
    search_public_documents,
    stream_public_ai_document_download,
)
from app.services.public.report_service import build_country_report, get_report_template
from app.utils.api_helpers import api_error, json_response
from app.utils.rate_limiting import api_rate_limit


@api_bp.route("/public/global-trend", methods=["GET"])
@api_rate_limit()
def public_global_trend():
    """
    Compact global totals by reporting period for public indicators.

    Preferred for AI assistants (Custom GPT) — returns ~1–2 KB instead of multi-MB /data payloads.
    """
    try:
        indicator_bank_id = request.args.get("indicator_bank_id", type=int)
        query = request.args.get("query", default="", type=str).strip()
        period_name = request.args.get("period_name", default="", type=str).strip()
        max_pages = request.args.get("max_pages", default=20, type=int)

        payload = aggregate_global_trend(
            indicator_bank_id=indicator_bank_id,
            query=query,
            period_name=period_name,
            max_pages=max_pages,
        )
        response = json_response(payload)
        response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=60"
        response.headers["X-Public-Data-Access"] = "true"
        return response
    except ValueError as exc:
        return api_error(str(exc), 400)
    except Exception as exc:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            "public/global-trend failed [ID: %s]: %s",
            error_id,
            exc,
            exc_info=True,
        )
        return api_error("Could not compute global trend", 500, error_id, None)


@api_bp.route("/public/indicators/resolve", methods=["GET"])
@api_rate_limit()
def public_resolve_indicator():
    """Map a natural-language metric name to an indicator bank id (compact response)."""
    try:
        query = request.args.get("query", default="", type=str).strip()
        limit = request.args.get("limit", default=5, type=int)
        if not query:
            return api_error("query is required", 400)
        payload = resolve_indicator_query(query, limit=max(1, min(limit, 20)))
        response = json_response(payload)
        response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=60"
        return response
    except Exception as exc:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            "public/indicators/resolve failed [ID: %s]: %s",
            error_id,
            exc,
            exc_info=True,
        )
        return api_error("Could not resolve indicator", 500, error_id, None)


@api_bp.route("/public/submissions/coverage", methods=["GET"])
@api_rate_limit()
def public_submission_coverage():
    """
    Count countries with a public submitted value for a template/indicator, by period.

    Answers "how many countries submitted FDRS/UPR data for <period>, or across all
    years?" — pass ``template_id=21`` for FDRS or ``22``/``24`` for UPR. Counts **public
    data coverage** only (rows with data_status='available' on privacy=public form
    items) — never internal assignment/workflow status, which requires an API key.
    """
    try:
        template_id = request.args.get("template_id", type=int)
        indicator_bank_id = request.args.get("indicator_bank_id", type=int)
        query = request.args.get("query", default="", type=str).strip()
        period_name = request.args.get("period_name", default="", type=str).strip()
        country_id = request.args.get("country_id", type=int)
        max_pages = request.args.get("max_pages", default=20, type=int)

        payload = aggregate_submission_coverage(
            template_id=template_id,
            indicator_bank_id=indicator_bank_id,
            query=query,
            period_name=period_name,
            country_id=country_id,
            max_pages=max_pages,
        )
        response = json_response(payload)
        response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=60"
        response.headers["X-Public-Data-Access"] = "true"
        return response
    except ValueError as exc:
        return api_error(str(exc), 400)
    except Exception as exc:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            "public/submissions/coverage failed [ID: %s]: %s",
            error_id,
            exc,
            exc_info=True,
        )
        return api_error("Could not compute submission coverage", 500, error_id, None)


@api_bp.route("/public/countries/resolve", methods=["GET"])
@api_rate_limit()
def public_resolve_country():
    """Map a country name, ISO2/ISO3 code, or numeric id to Country reference fields."""
    try:
        query = request.args.get("query", default="", type=str).strip()
        limit = request.args.get("limit", default=5, type=int)
        if not query:
            return api_error("query is required", 400)
        payload = resolve_country_query(query, limit=max(1, min(limit, 20)))
        response = json_response(payload)
        response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=60"
        return response
    except Exception as exc:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            "public/countries/resolve failed [ID: %s]: %s",
            error_id,
            exc,
            exc_info=True,
        )
        return api_error("Could not resolve country", 500, error_id, None)


@api_bp.route("/public/documents/search", methods=["GET"])
@api_rate_limit()
def public_search_documents():
    """
    Search public AI document chunks for Custom GPT and other assistants.

    Returns compact text chunks from documents marked is_public=True.
    The caller (e.g. Custom GPT) synthesizes the final answer from chunks.
    """
    try:
        query = request.args.get("query", default="", type=str).strip()
        if not query:
            return api_error("query is required", 400)

        top_k = request.args.get("top_k", default=8, type=int)
        min_score = request.args.get("min_score", default=0.25, type=float)
        country_name = request.args.get("country_name", default="", type=str).strip() or None
        country_id = request.args.get("country_id", type=int)
        country_ids = request.args.get("country_ids", default="", type=str).strip() or None
        require_phrase = request.args.get("require_phrase", default="", type=str).strip() or None
        file_type = request.args.get("file_type", default="", type=str).strip() or None
        search_mode = request.args.get("search_mode", default="hybrid", type=str)
        full_coverage_raw = request.args.get("full_coverage", default="false", type=str).strip().lower()
        full_coverage = full_coverage_raw in {"1", "true", "yes"}
        page = request.args.get("page", default=1, type=int)
        per_page = request.args.get("per_page", default=80, type=int)
        latest_per_country_raw = request.args.get("latest_per_country", default="", type=str).strip().lower()
        latest_per_country = None
        if latest_per_country_raw in {"1", "true", "yes"}:
            latest_per_country = True
        elif latest_per_country_raw in {"0", "false", "no"}:
            latest_per_country = False

        payload = search_public_documents(
            query,
            top_k=top_k,
            min_score=min_score,
            country_name=country_name,
            country_id=country_id,
            country_ids=country_ids,
            file_type=file_type,
            search_mode=search_mode,
            full_coverage=full_coverage,
            page=page,
            per_page=per_page,
            latest_per_country=latest_per_country,
            require_phrase=require_phrase,
        )
        response = json_response(payload)
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Public-Data-Access"] = "true"
        return response
    except PublicDocumentSearchUnavailable as exc:
        return api_error(str(exc), 503, extra={"error_type": "service_unavailable"})
    except PublicDocumentScopeTooLarge as exc:
        return api_error(str(exc), 400, extra={"error_type": "scope_too_large"})
    except ValueError as exc:
        return api_error(str(exc), 400)
    except Exception as exc:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            "public/documents/search failed [ID: %s]: %s",
            error_id,
            exc,
            exc_info=True,
        )
        return api_error("Could not search public documents", 500, error_id, None)


@api_bp.route("/public/documents/<int:document_id>", methods=["GET"])
@api_rate_limit()
def public_get_document(document_id: int):
    """Public metadata for one AI document (title, countries, source_url)."""
    try:
        payload = get_public_document_metadata(document_id)
        response = json_response(payload)
        response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=60"
        response.headers["X-Public-Data-Access"] = "true"
        return response
    except ValueError as exc:
        return api_error(str(exc), 404)
    except Exception as exc:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            "public/documents/%s failed [ID: %s]: %s",
            document_id,
            error_id,
            exc,
            exc_info=True,
        )
        return api_error("Could not load public document", 500, error_id, None)


@api_bp.route("/public/documents/<int:document_id>/download", methods=["GET"])
@api_rate_limit()
def public_download_ai_document(document_id: int):
    """Download or redirect to a public AI Knowledge Base document (no login)."""
    try:
        response = stream_public_ai_document_download(document_id)
        response.headers["X-Public-Data-Access"] = "true"
        return response
    except ValueError as exc:
        return api_error(str(exc), 404)
    except Exception as exc:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            "public/documents/%s/download failed [ID: %s]: %s",
            document_id,
            error_id,
            exc,
            exc_info=True,
        )
        return api_error("Could not download public document", 500, error_id, None)


@api_bp.route("/public/documents/catalog", methods=["GET"])
@api_rate_limit()
def public_documents_catalog():
    """
    Inventory public documents by type / year / country — counts, not semantic search.

    Answers "how many countries submitted an annual report (FDRS) or a Unified Plan
    (UPR) for 2024, or across all years?" directly from document metadata. Use
    ``/public/documents/search`` instead for narrative Q&A over document content.
    """
    try:
        document_type = request.args.get("document_type", default="", type=str).strip()
        year = request.args.get("year", type=int)
        country_id = request.args.get("country_id", type=int)
        country_name = request.args.get("country_name", default="", type=str).strip() or None
        file_type = request.args.get("file_type", default="", type=str).strip()
        include_documents_raw = request.args.get("include_documents", default="true", type=str).strip().lower()
        include_documents = include_documents_raw not in {"0", "false", "no"}

        payload = catalog_public_documents(
            document_type=document_type,
            year=year,
            country_id=country_id,
            country_name=country_name,
            file_type=file_type,
            include_documents=include_documents,
        )
        response = json_response(payload)
        response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=60"
        response.headers["X-Public-Data-Access"] = "true"
        return response
    except ValueError as exc:
        return api_error(str(exc), 400)
    except Exception as exc:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            "public/documents/catalog failed [ID: %s]: %s",
            error_id,
            exc,
            exc_info=True,
        )
        return api_error("Could not build document catalog", 500, error_id, None)


@api_bp.route("/public/reports/country", methods=["GET"])
@api_rate_limit()
def public_country_report():
    """
    Assemble a one-country report spec: headline FDRS KPIs, a trend, and cited
    narrative themes — the single-call equivalent of chaining resolveCountry,
    getSubmissionCoverage, getPublicData, and searchPublicDocuments by hand.

    Resolves the country and reporting period from free text (``period_hint``,
    e.g. "2026 midyear"), fetches a curated FDRS headline KPI bundle (volunteers,
    staff, branches, local units, governing board, income, expenditure, blood
    donations, first-aid trained) for the resolved period plus the prior one, a
    multi-period volunteers trend, and cited themes from public Unified
    Plan/Report/Midyear Report documents. Render the actual visual one-pager
    yourself from the returned JSON — this endpoint never returns HTML or images.
    An unresolved country returns HTTP 200 with ``ok=false`` and ``alternatives``
    (same soft-failure shape as ``resolveCountry``), not an HTTP error.
    """
    try:
        country = request.args.get("country", default="", type=str).strip()
        if not country:
            return api_error("country is required", 400)

        period_hint = request.args.get("period_hint", default="", type=str).strip()
        report_type = request.args.get("report_type", default="combined", type=str).strip()
        include_prior_raw = request.args.get("include_prior_period", default="true", type=str).strip().lower()
        include_prior_period = include_prior_raw not in {"0", "false", "no"}
        template_style = request.args.get("template_style", default="", type=str).strip()

        payload = build_country_report(
            country=country,
            period_hint=period_hint,
            report_type=report_type,
            include_prior_period=include_prior_period,
        )
        if template_style and payload.get("ok"):
            payload["design_template"] = get_report_template(template_style)

        response = json_response(payload)
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Public-Data-Access"] = "true"
        return response
    except ValueError as exc:
        return api_error(str(exc), 400)
    except Exception as exc:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            "public/reports/country failed [ID: %s]: %s",
            error_id,
            exc,
            exc_info=True,
        )
        return api_error("Could not build country report", 500, error_id, None)


@api_bp.route("/public/reports/template", methods=["GET"])
@api_rate_limit()
def public_report_template():
    """
    Return an HTML/CSS one-pager skeleton plus design tokens for a report style.

    Use alongside ``getCountryReport`` when the one-pager should follow a specific
    layout/palette instead of a freeform render: fill the returned
    ``html_template``'s ``{{PLACEHOLDER}}`` tokens with the report data (repeating
    the ``KPI_CARD`` and ``THEME_ITEM`` blocks per entry) and apply
    ``design_tokens`` (colors, fonts, spacing) even when rendering as markdown or
    an image-generation prompt instead of raw HTML. An unrecognized ``style``
    returns HTTP 200 with ``ok=false`` and ``available_styles``.
    """
    try:
        style = request.args.get("style", default="default", type=str).strip()
        payload = get_report_template(style)
        response = json_response(payload)
        response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=60"
        response.headers["X-Public-Data-Access"] = "true"
        return response
    except Exception as exc:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            "public/reports/template failed [ID: %s]: %s",
            error_id,
            exc,
            exc_info=True,
        )
        return api_error("Could not load report template", 500, error_id, None)
