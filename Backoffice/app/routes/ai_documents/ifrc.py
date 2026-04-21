"""
AI Document IFRC API integration routes: list, import, bulk import.
"""

import os
import logging
import re
import requests
import json
import base64
import threading
import uuid
import time
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import request, current_app, g
from flask_login import current_user
from sqlalchemy import or_

from app.extensions import db, limiter
from app.models import AIDocument, AIDocumentChunk, AIEmbedding, Country, AIJob, AIJobItem
from app.services.ai_document_processor import AIDocumentProcessor
from app.utils.datetime_helpers import utcnow
from app.routes.admin.shared import admin_required, permission_required
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.api_responses import (
    json_accepted, json_auth_required, json_bad_request, json_error,
    json_forbidden, json_not_found, json_ok, json_server_error, require_json_keys,
)
from app.utils.sql_utils import safe_ilike_pattern
from app.utils.constants import (
    APPEALS_TYPE_DEFAULT_IDS_STR,
    APPEALS_TYPE_DISPLAY_NAMES,
    APPEALS_TYPE_IDS,
    APPEALS_TYPE_LEGACY_MAPPING,
)

from . import ai_docs_bp
from .helpers import (
    IFRC_APPEALS_TITLE_YEAR_RE,
    _get_ifrc_basic_auth,
    _validate_ifrc_fetch_url,
    _normalize_ifrc_source_url,
    _ifrc_url_match_variants,
    _download_ifrc_document,
    _summarize_processing_error,
)
from .upload import _process_document_sync, _run_import_process_in_thread

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# IFRC-specific helpers (only used by routes in this module)
# ---------------------------------------------------------------------------


def _fetch_ifrc_public_site_types():
    """
    Fetch document types from IFRC PublicSiteTypes API.
    Returns list of dicts: [{'id': int, 'name': str}, ...]
    Caches result for the request lifetime.
    """
    cache_key = "_ifrc_public_site_types_cache"
    cached = getattr(g, cache_key, None)
    if cached is not None:
        return cached
    auth = _get_ifrc_basic_auth()
    if not auth:
        return []
    try:
        response = requests.get(
            "https://go-api.ifrc.org/Api/PublicSiteTypes",
            headers={"User-Agent": "hum-databank/1.0", "Accept": "application/json"},
            auth=auth,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            return []
        types_list = []
        for item in data:
            tid = item.get("AppealsTypeID") or item.get("AppealsTypeId")
            name = (item.get("AppealsName") or "").strip()
            if tid is not None and name:
                types_list.append({"id": int(tid), "name": name})
        types_list.sort(key=lambda x: (x["name"].lower(), x["id"]))
        setattr(g, cache_key, types_list)
        return types_list
    except Exception as e:
        logger.warning("IFRC PublicSiteTypes fetch failed: %s", e)
        return []


_UNIFIED_PLANNING_TYPES = [
    {'id': tid, 'name': APPEALS_TYPE_DISPLAY_NAMES[tid], 'group': 'Unified Planning'}
    for tid in sorted(APPEALS_TYPE_IDS)
]


def _fetch_ifrc_appeals_filter_options(*, appeals_type_ids: Optional[str] = None):
    """
    Fetch PublicSiteAppeals from IFRC API and return raw items for filter-options processing.
    """
    base_api = "https://go-api.ifrc.org/Api/PublicSiteAppeals"
    if appeals_type_ids and str(appeals_type_ids).strip().lower() not in ("", "all"):
        api_url = f"{base_api}?AppealsTypeId={appeals_type_ids}"
    else:
        api_url = base_api
    auth = _get_ifrc_basic_auth()
    if not auth:
        return None
    try:
        response = requests.get(
            api_url,
            headers={"User-Agent": "hum-databank/1.0", "Accept": "application/json"},
            auth=auth,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning("IFRC appeals fetch for filter options failed: %s", e)
        return []


# IFRC location labels sometimes include a trailing ISO2-style suffix, e.g. "Haiti (HT)".
_IFRC_LOC_NAME_ISO2_SUFFIX_RE = re.compile(r"\s*\([A-Z]{2}\)\s*$")


def _ifrc_display_country_name(
    api_location_name: Optional[str],
    country_info: Optional[Dict[str, Any]],
) -> str:
    """Prefer mapped DB country name; otherwise strip trailing \" (XY)\" from API text."""
    if country_info:
        dbn = (country_info.get("name") or "").strip()
        if dbn:
            return dbn
    raw = (api_location_name or "").strip()
    if not raw:
        return ""
    stripped = _IFRC_LOC_NAME_ISO2_SUFFIX_RE.sub("", raw).strip()
    return stripped or raw


_IMPORT_JOB_CANCEL_EVENTS: Dict[str, threading.Event] = {}
_IMPORT_JOB_CANCEL_LOCK = threading.Lock()


def _get_import_job_cancel_event(job_id: str) -> threading.Event:
    with _IMPORT_JOB_CANCEL_LOCK:
        ev = _IMPORT_JOB_CANCEL_EVENTS.get(job_id)
        if ev is None:
            ev = threading.Event()
            _IMPORT_JOB_CANCEL_EVENTS[job_id] = ev
        return ev


def _clear_import_job_cancel_event(job_id: str) -> None:
    with _IMPORT_JOB_CANCEL_LOCK:
        _IMPORT_JOB_CANCEL_EVENTS.pop(job_id, None)


def _process_ifrc_job_item_sync(app, *, job_id: str, item_id: int) -> None:
    """
    Sync processing for one IFRC import job item.
    """
    with app.app_context():
        cancel_ev = _get_import_job_cancel_event(job_id)
        item = AIJobItem.query.get(int(item_id))
        if not item:
            return

        job = AIJob.query.get(str(job_id))
        job_user_id = int(job.user_id) if job and job.user_id else None

        if cancel_ev.is_set():
            item.status = "cancelled"
            item.error = None
            db.session.commit()
            return

        payload = item.payload or {}
        raw_url = (payload.get("url") or payload.get("source_url") or "").strip() if isinstance(payload, dict) else ""
        url = _normalize_ifrc_source_url(raw_url)
        if not url:
            item.status = "failed"
            item.error = "Missing URL"
            db.session.commit()
            return

        item.status = "downloading"
        item.error = None
        db.session.commit()
        db.session.remove()

        temp_path = None
        filename = None
        try:
            logger.info("Bulk IFRC import item start: job=%s item=%s url=%s", job_id, item_id, url)
            import time as _time
            _time.sleep(0)
            temp_path, filename, file_size, content_hash, file_type = _download_ifrc_document(url)

            if cancel_ev.is_set():
                item = AIJobItem.query.get(int(item_id))
                if item:
                    item.status = "cancelled"
                    item.error = None
                    db.session.commit()
                return

            existing = AIDocument.query.filter(
                or_(AIDocument.content_hash == content_hash, AIDocument.source_url == url)
            ).first()

            country_id = payload.get("country_id") if isinstance(payload, dict) else None
            country_name = payload.get("country_name") if isinstance(payload, dict) else None

            title = (payload.get("title") or "").strip() if isinstance(payload, dict) else ""
            title = title or (filename or "").strip() or url
            if isinstance(payload, dict) and "is_public" in payload:
                is_public = bool(payload.get("is_public") or False)
            else:
                is_public = True

            if existing:
                previous_source_url = existing.source_url
                existing.title = title
                existing.filename = filename or existing.filename
                existing.file_type = file_type or existing.file_type
                existing.file_size_bytes = file_size
                existing.content_hash = content_hash
                existing.source_url = url
                existing.is_public = is_public
                existing.searchable = True
                if not existing.user_id and job_user_id:
                    existing.user_id = job_user_id
                if country_id is not None:
                    existing.country_id = int(country_id)
                    existing.country_name = country_name or None
                    try:
                        c = db.session.get(Country, int(country_id))
                        if c and c not in existing.countries:
                            existing.countries.append(c)
                    except Exception as e:
                        logger.debug("Country M2M append (existing) failed: %s", e)
                existing.total_chunks = 0
                existing.total_embeddings = 0
                existing.processing_status = "pending"
                existing.processing_error = None
                existing.storage_path = temp_path
                if previous_source_url and previous_source_url != url:
                    logger.info(
                        "Bulk IFRC import dedupe collision: job=%s item=%s doc_id=%s existing_url=%s new_url=%s",
                        job_id, item_id, int(existing.id), previous_source_url, url
                    )
                    try:
                        old_meta = dict(existing.extra_metadata or {})
                        alt_urls = list(old_meta.get("alt_source_urls") or [])
                        if previous_source_url not in alt_urls:
                            alt_urls.append(previous_source_url)
                        old_meta["alt_source_urls"] = alt_urls
                        existing.extra_metadata = old_meta
                    except Exception as e:
                        logger.debug("Alt source URL metadata update failed: %s", e)
                db.session.commit()
                doc = existing
            else:
                doc = AIDocument(
                    title=title,
                    filename=filename or "ifrc_document",
                    file_type=file_type or "pdf",
                    file_size_bytes=file_size,
                    storage_path=temp_path,
                    content_hash=content_hash,
                    source_url=url,
                    processing_status="pending",
                    user_id=job_user_id,
                    is_public=is_public,
                    searchable=True,
                    country_id=int(country_id) if country_id is not None else None,
                    country_name=country_name or None,
                )
                db.session.add(doc)
                db.session.flush()
                if country_id is not None:
                    try:
                        c = db.session.get(Country, int(country_id))
                        if c and c not in doc.countries:
                            doc.countries.append(c)
                    except Exception as e:
                        logger.debug("Country M2M append (new doc) failed: %s", e)
                db.session.commit()

            item.entity_type = "ai_document"
            item.entity_id = int(doc.id)
            item.status = "processing"
            item.error = None
            try:
                base_payload = item.payload if isinstance(item.payload, dict) else {}
                new_payload = dict(base_payload)
                new_payload["ai_document_id"] = int(doc.id)
                item.payload = new_payload
            except Exception as e:
                logger.debug("Job item payload update failed: %s", e)
            db.session.commit()
            _doc_id_for_processing = int(doc.id)
            _filename_for_processing = filename or doc.filename
            db.session.remove()
            _time.sleep(0)

            logger.info(
                "Bulk IFRC import item processing: job=%s item=%s doc_id=%s existing=%s",
                job_id, item_id, _doc_id_for_processing, bool(existing)
            )
            _process_document_sync(_doc_id_for_processing, temp_path, _filename_for_processing)

            try:
                doc = AIDocument.query.get(_doc_id_for_processing)
                if doc:
                    doc.storage_path = None
                    db.session.commit()
            except Exception as e:
                logger.debug("Clear storage_path after bulk import: %s", e)
                db.session.rollback()

            item = AIJobItem.query.get(int(item_id))
            if item:
                doc_id = int(item.entity_id) if (item.entity_type == "ai_document" and item.entity_id) else None
                doc = AIDocument.query.get(int(doc_id)) if doc_id else None
                if doc and doc.processing_status == "completed":
                    item.status = "completed"
                    item.error = None
                elif doc and doc.processing_status == "failed":
                    item.status = "failed"
                    item.error = doc.processing_error or "Processing failed"
                else:
                    item.status = "failed"
                    item.error = "Unknown processing state"
                db.session.commit()
                logger.info(
                    "Bulk IFRC import item finished: job=%s item=%s doc_id=%s status=%s",
                    job_id, item_id, int(doc_id or 0), item.status
                )

        except Exception as e:
            logger.error("Bulk IFRC import item failed: job=%s item=%s err=%s", job_id, item_id, e, exc_info=True)
            try:
                item = AIJobItem.query.get(int(item_id))
                if item:
                    item.status = "failed"
                    item.error = _summarize_processing_error(e)
                    db.session.commit()
            except Exception as update_e:
                logger.debug("Bulk import item status update failed: %s", update_e)
                db.session.rollback()
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass


def _run_ifrc_bulk_import_job(app, job_id: str) -> None:
    """Background runner for IFRC bulk import jobs."""
    with app.app_context():
        job = AIJob.query.get(str(job_id))
        if not job:
            return
        if job.status in ("completed", "failed", "cancelled"):
            return
        job.status = "running"
        job.started_at = utcnow()
        db.session.commit()
        logger.info("Bulk IFRC import job running: job=%s total_items=%s", job_id, int(job.total_items or 0))

    cancel_ev = _get_import_job_cancel_event(job_id)
    try:
        with app.app_context():
            job = AIJob.query.get(str(job_id))
            if not job:
                return
            concurrency = int((job.meta or {}).get("concurrency") or current_app.config.get("AI_DOCS_IFRC_IMPORT_CONCURRENCY", 2))
            concurrency = max(1, min(concurrency, 4))
            item_ids = [it.id for it in (job.items or []) if (it.status or "queued") == "queued"]

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = []
            for item_id in item_ids:
                if cancel_ev.is_set():
                    break
                futures.append(pool.submit(_process_ifrc_job_item_sync, app, job_id=job_id, item_id=int(item_id)))
                import time as _time_job
                _time_job.sleep(0.5)

            for _f in as_completed(futures):
                if cancel_ev.is_set():
                    continue

        with app.app_context():
            job = AIJob.query.get(str(job_id))
            if not job:
                return
            if cancel_ev.is_set() or job.status == "cancel_requested":
                try:
                    for it in (job.items or []):
                        if it.status == "queued":
                            it.status = "cancelled"
                            it.error = None
                    db.session.commit()
                except Exception as e:
                    logger.debug("cancel job items commit failed: %s", e)
                    db.session.rollback()
                job.status = "cancelled"
            else:
                terminal = {"completed", "failed", "cancelled"}
                all_terminal = all((it.status in terminal) for it in (job.items or []))
                job.status = "completed" if all_terminal else "failed"
            job.finished_at = utcnow()
            db.session.commit()
            logger.info("Bulk IFRC import job finished: job=%s status=%s", job_id, job.status)
    except Exception as e:
        logger.error("Bulk IFRC import job failed: job=%s err=%s", job_id, e, exc_info=True)
        with app.app_context():
            job = AIJob.query.get(str(job_id))
            if job:
                job.status = "failed"
                job.error = "Processing failed."
                job.finished_at = utcnow()
                db.session.commit()
    finally:
        _clear_import_job_cancel_event(job_id)


# ---------------------------------------------------------------------------
# IFRC API Routes
# ---------------------------------------------------------------------------


@ai_docs_bp.route('/ifrc-api/types', methods=['GET'])
@admin_required
@permission_required('admin.documents.manage')
@limiter.limit("60 per minute")
def list_ifrc_api_types():
    """
    Fetch available document types from IFRC PublicSiteTypes API.
    """
    auth = _get_ifrc_basic_auth()
    if not auth:
        return json_server_error('External document API credentials are not configured. Set IFRC_API_USER and IFRC_API_PASSWORD.')
    api_types = _fetch_ifrc_public_site_types()
    unified_ids = {t['id'] for t in _UNIFIED_PLANNING_TYPES}
    unified_names = {t['name'].lower() for t in _UNIFIED_PLANNING_TYPES}
    other_types = [
        {'id': t['id'], 'name': t['name']}
        for t in api_types
        if t['id'] not in unified_ids and t['name'].lower() not in unified_names
    ]
    other_types.sort(key=lambda x: (x['name'].lower(), x['id']))
    types_list = _UNIFIED_PLANNING_TYPES + other_types
    return json_ok(types=types_list)


@ai_docs_bp.route('/ifrc-api/filter-options', methods=['GET'])
@admin_required
@permission_required('admin.documents.manage')
@limiter.limit("60 per minute")
def list_ifrc_api_filter_options():
    """
    Return applicable types for a selected country, or applicable countries for selected type(s).
    """
    country_name = (request.args.get("country_name") or "").strip()
    appeals_type_ids = (request.args.get("appeals_type_ids") or "").strip()

    auth = _get_ifrc_basic_auth()
    if not auth:
        return json_server_error("External document API credentials not configured")

    type_mapping = dict(APPEALS_TYPE_LEGACY_MAPPING)
    for t in _fetch_ifrc_public_site_types():
        type_mapping[t["id"]] = t["name"]

    country_map = {}
    for c in Country.query.filter(Country.iso2.isnot(None)).all():
        if c.iso2:
            country_map[c.iso2.upper()] = {"name": c.name, "iso2": c.iso2}

    if country_name:
        items = _fetch_ifrc_appeals_filter_options(appeals_type_ids=None)
        if items is None:
            return json_server_error("Failed to fetch appeals from external document API")
        q = country_name.strip()
        exact_pat = safe_ilike_pattern(q, prefix=False, suffix=False)
        contains_pat = safe_ilike_pattern(q)
        match = Country.query.filter(Country.name.ilike(exact_pat)).first()
        if not match:
            match = Country.query.filter(Country.name.ilike(contains_pat)).first()
        if not match or not getattr(match, "iso2", None):
            return json_ok(types=[])
        code_for_country = str(match.iso2).strip().upper()
        unified_ids = APPEALS_TYPE_IDS
        seen_ids = set()
        types_list = []
        for item in items:
            if item.get("Hidden"):
                continue
            loc = (item.get("LocationCountryCode") or "").strip().upper()
            if loc != code_for_country:
                continue
            tid = item.get("AppealsTypeId")
            if tid is None or tid in seen_ids:
                continue
            seen_ids.add(tid)
            name = type_mapping.get(tid) or (item.get("AppealOrigType") or "").strip() or str(tid)
            group = "Unified Planning" if tid in unified_ids else ""
            types_list.append({"id": int(tid), "name": name, "group": group})
        types_list.sort(key=lambda x: (x["group"] != "Unified Planning", (x["name"] or "").lower(), x["id"]))
        return json_ok(types=types_list)

    if appeals_type_ids:
        items = _fetch_ifrc_appeals_filter_options(appeals_type_ids=appeals_type_ids)
        if items is None:
            return json_server_error("Failed to fetch appeals from external document API")
        seen_codes = set()
        countries_list = []
        for item in items:
            if item.get("Hidden"):
                continue
            code = (item.get("LocationCountryCode") or "").strip().upper()
            if not code or code in seen_codes:
                continue
            info = country_map.get(code)
            name = _ifrc_display_country_name(item.get("LocationCountryName") or "", info)
            if not name:
                name = code
            seen_codes.add(code)
            countries_list.append({"name": name, "iso2": code})
        countries_list.sort(key=lambda x: (x.get("name") or "").lower())
        return json_ok(countries=countries_list)

    return json_bad_request("Provide country_name or appeals_type_ids")


@ai_docs_bp.route('/ifrc-api/list', methods=['GET'])
@admin_required
@permission_required('admin.documents.manage')
@limiter.limit("30 per minute")
def list_ifrc_api_documents():
    """
    Fetch documents from IFRC API with filters.
    """
    try:
        raw_appeals = request.args.get('appeals_type_ids')
        appeals_type_ids = (raw_appeals or '').strip()
        if raw_appeals is None:
            appeals_type_ids = APPEALS_TYPE_DEFAULT_IDS_STR
        type_filter = request.args.get('type_filter', '').strip()
        year_filter = request.args.get('year_filter', '').strip()
        country_code = request.args.get('country_code', '').strip()
        country_name = request.args.get('country_name', '').strip()

        if country_name and not country_code:
            q = country_name.strip()
            match = None
            try:
                exact_pat = safe_ilike_pattern(q, prefix=False, suffix=False)
                contains_pat = safe_ilike_pattern(q)
                match = Country.query.filter(Country.name.ilike(exact_pat)).first()
                if not match:
                    match = Country.query.filter(Country.name.ilike(contains_pat)).first()
            except Exception as e:
                logger.debug("Country ilike query failed: %s", e)
                match = None

            if match and getattr(match, "iso2", None):
                country_code = str(match.iso2).strip().upper()
            else:
                return json_ok(documents=[], total=0, message=f'No country match found for: {country_name}')

        base_api = "https://go-api.ifrc.org/Api/PublicSiteAppeals"
        if appeals_type_ids and appeals_type_ids.lower() != 'all':
            api_url = f"{base_api}?AppealsTypeId={appeals_type_ids}"
        else:
            api_url = base_api

        headers = {
            'User-Agent': 'hum-databank/1.0',
            'Accept': 'application/json',
        }

        auth = _get_ifrc_basic_auth()
        if not auth:
            return json_server_error('External document API credentials are not configured. Set IFRC_API_USER and IFRC_API_PASSWORD.')

        try:
            response = requests.get(api_url, headers=headers, auth=auth, timeout=30)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error(f"IFRC API authentication failed: {e}", exc_info=True)
                return json_auth_required('External document API authentication failed. Please check credentials.')
            else:
                logger.error(f"IFRC API HTTP error: {e}", exc_info=True)
                return json_error(f'External document API error: {e.response.status_code} - {e.response.text[:200]}', e.response.status_code)
        except requests.exceptions.RequestException as e:
            logger.error(f"IFRC API request failed: {e}", exc_info=True)
            return json_server_error(GENERIC_ERROR_MESSAGE)

        if not isinstance(data, list):
            return json_server_error('Invalid response format from external document API')

        processed_docs = []

        type_mapping = dict(APPEALS_TYPE_LEGACY_MAPPING)
        for t in _fetch_ifrc_public_site_types():
            type_mapping[t['id']] = t['name']

        country_map_local = {}
        countries = Country.query.filter(Country.iso2.isnot(None)).all()
        for country in countries:
            if country.iso2:
                country_map_local[country.iso2.upper()] = {
                    'iso3': country.iso3,
                    'name': country.name,
                    'id': country.id
                }

        for item in data:
            if item.get('Hidden', False):
                continue

            appeals_type_id = item.get('AppealsTypeId')
            doc_type = type_mapping.get(appeals_type_id)

            if type_filter and doc_type != type_filter:
                continue

            year = None
            appeal_orig_type = (item.get('AppealOrigType') or '')
            appeals_name = (item.get('AppealsName') or '')

            year_match = IFRC_APPEALS_TITLE_YEAR_RE.search(
                appeal_orig_type + ' ' + appeals_name
            )
            if year_match:
                year = int(year_match.group(1))

            if year_filter:
                try:
                    filter_year = int(year_filter)
                    if year != filter_year:
                        continue
                except ValueError:
                    pass

            base_dir = (item.get('BaseDirectory') or '')
            base_filename = (item.get('BaseFileName') or '')
            if base_dir and base_filename:
                url = _normalize_ifrc_source_url(base_dir + base_filename)
            else:
                continue

            location_country_code = (item.get('LocationCountryCode') or '').strip().upper()
            country_info = None
            if location_country_code and location_country_code in country_map_local:
                country_info = country_map_local[location_country_code]

            if country_code and location_country_code != country_code.upper():
                continue

            processed_docs.append({
                'url': url,
                'title': (item.get('AppealsName') or ''),
                'type': doc_type,
                'year': year,
                'appeals_type_id': appeals_type_id,
                'country_code': location_country_code,
                'country_name': _ifrc_display_country_name(
                    item.get('LocationCountryName') or '',
                    country_info,
                ),
                'country_iso3': country_info['iso3'] if country_info else None,
                'country_id': country_info['id'] if country_info else None,
                'region_code': (item.get('LocationRegionCode') or ''),
                'region_name': (item.get('LocationRegionName') or ''),
                'date': (item.get('AppealsDate') or ''),
                'base_filename': base_filename
            })

        existing_urls: list[str] = []
        for r in (
            AIDocument.query
            .filter(AIDocument.source_url.isnot(None))
            .with_entities(AIDocument.source_url, AIDocument.extra_metadata)
            .all()
        ):
            if r and r[0]:
                existing_urls.append(str(r[0]).strip())
            if r and r[1] and isinstance(r[1], dict):
                for alt in (r[1].get("alt_source_urls") or []):
                    if alt:
                        existing_urls.append(str(alt).strip())

        existing_variant_pool: set[str] = set()
        for u in existing_urls:
            existing_variant_pool.update(_ifrc_url_match_variants(u))

        already_imported: set[str] = set()
        for d in processed_docs:
            candidate_url = str(d.get("url") or "").strip()
            if not candidate_url:
                continue
            if _ifrc_url_match_variants(candidate_url) & existing_variant_pool:
                already_imported.add(candidate_url)

        logger.info(
            "IFRC list loaded: total=%s imported=%s filters(type=%s year=%s country_code=%s country_name=%s)",
            len(processed_docs),
            len(already_imported),
            type_filter or "",
            year_filter or "",
            country_code or "",
            country_name or "",
        )

        return json_ok(
            documents=processed_docs,
            total=len(processed_docs),
            already_imported_urls=list(already_imported),
        )

    except Exception as e:
        logger.error(f"IFRC API list error: {e}", exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)


@ai_docs_bp.route('/ifrc-api/import', methods=['POST'])
@admin_required
@permission_required('admin.documents.manage')
@limiter.limit("10 per minute")
def import_ifrc_api_document():
    """
    Import a document from IFRC API URL.
    """
    try:
        data = get_json_safe()
        err = require_json_keys(data, ['url'])
        if err:
            return err

        raw_url = data.get('url', '').strip()
        url = _normalize_ifrc_source_url(raw_url)
        if not url:
            return json_bad_request('URL is required')

        ok, reason = _validate_ifrc_fetch_url(url)
        if not ok:
            return json_bad_request(f'Invalid or blocked URL: {reason}')

        title = data.get('title', '').strip()
        is_public = data.get('is_public', True)
        if isinstance(is_public, str):
            is_public = is_public.lower() in ('true', '1', 'yes')
        else:
            is_public = bool(is_public)
        country_id = data.get('country_id')
        country_name = data.get('country_name', '').strip()

        from app.services.authorization_service import AuthorizationService
        if is_public and not AuthorizationService.is_admin(current_user):
            return json_forbidden('Only admins can create public documents')

        temp_path = None
        try:
            logger.info(
                "IFRC single import requested: user_id=%s url=%s title=%s country_id=%s",
                getattr(current_user, "id", None),
                url,
                title or "",
                country_id,
            )

            temp_path, filename, file_size, content_hash, file_type = _download_ifrc_document(url)
            if not title:
                title = filename

            processor = AIDocumentProcessor()
            if not processor.is_supported_file(filename):
                return json_bad_request(f'Unsupported file type. Supported: {", ".join(processor.SUPPORTED_TYPES.keys())}')

            existing = AIDocument.query.filter(
                or_(AIDocument.content_hash == content_hash, AIDocument.source_url == url)
            ).first()
            if existing:
                _dedupe_by = "source_url" if (existing.source_url == url) else "content_hash"
                logger.info(
                    "IFRC single import dedupe hit: url=%s existing_doc_id=%s by=%s",
                    url,
                    existing.id,
                    _dedupe_by,
                )
                existing.title = title
                existing.filename = filename
                existing.file_type = file_type
                existing.file_size_bytes = file_size
                existing.content_hash = content_hash
                _prev_source_url = existing.source_url
                existing.source_url = url
                if _dedupe_by == "content_hash" and _prev_source_url and _prev_source_url != url:
                    try:
                        old_meta = dict(existing.extra_metadata or {})
                        alt_urls = list(old_meta.get("alt_source_urls") or [])
                        if _prev_source_url not in alt_urls:
                            alt_urls.append(_prev_source_url)
                        old_meta["alt_source_urls"] = alt_urls
                        existing.extra_metadata = old_meta
                    except Exception as e:
                        logger.debug("Alt source URL metadata update failed: %s", e)
                existing.is_public = is_public
                existing.searchable = True
                from app.services.ai_country_detection import detect_countries as _det_countries
                if country_id is not None:
                    existing.country_id = country_id
                    existing.country_name = country_name or None
                    from app.models import Country as CountryModel
                    c = db.session.get(CountryModel, int(country_id))
                    if c and c not in existing.countries:
                        existing.countries.append(c)
                else:
                    det = _det_countries(filename=filename, title=title, text=None)
                    existing.country_id = det.primary_country_id
                    existing.country_name = det.primary_country_name
                    existing.geographic_scope = det.scope
                    from app.models import Country as CountryModel
                    existing.countries.clear()
                    for cid, _cname in det.countries:
                        c = db.session.get(CountryModel, cid)
                        if c:
                            existing.countries.append(c)
                existing.total_chunks = 0
                existing.total_embeddings = 0
                existing.processing_status = 'pending'
                existing.processing_error = None
                db.session.commit()
                _run_import_process_in_thread(
                    current_app._get_current_object(), existing.id, temp_path, filename
                )
                return json_accepted(
                    document_id=existing.id,
                    status='processing',
                    message='Import started; poll document status for progress.',
                )

            from app.services.ai_country_detection import detect_countries as _det_countries2
            detected_country_id = country_id
            detected_country_name = country_name
            detected_countries = []
            detected_scope = None
            if not detected_country_id:
                det = _det_countries2(filename=filename, title=title, text=None)
                detected_country_id = det.primary_country_id
                detected_country_name = det.primary_country_name
                detected_countries = det.countries
                detected_scope = det.scope

            doc = AIDocument(
                title=title,
                filename=filename,
                file_type=file_type,
                file_size_bytes=file_size,
                storage_path=temp_path,
                content_hash=content_hash,
                source_url=url,
                processing_status='pending',
                user_id=current_user.id,
                is_public=is_public,
                searchable=True,
                country_id=detected_country_id,
                country_name=detected_country_name,
                geographic_scope=detected_scope,
            )
            db.session.add(doc)
            db.session.flush()

            if detected_countries:
                from app.models import Country as CountryModel
                for cid, _cname in detected_countries:
                    c = db.session.get(CountryModel, cid)
                    if c and c not in doc.countries:
                        doc.countries.append(c)
            elif detected_country_id:
                from app.models import Country as CountryModel
                c = db.session.get(CountryModel, int(detected_country_id))
                if c and c not in doc.countries:
                    doc.countries.append(c)

            db.session.commit()
            document_id = doc.id
            logger.info("IFRC single import created: doc_id=%s url=%s", document_id, url)
            _run_import_process_in_thread(
                current_app._get_current_object(), document_id, temp_path, filename
            )
            return json_accepted(
                document_id=document_id,
                status='processing',
                message='Import started; poll document status for progress.',
            )

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download from IFRC API: {e}", exc_info=True)
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            return json_server_error('Failed to download document.')
        except Exception as e:
            logger.debug("IFRC single import exception (cleaning up): %s", e)
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            raise

    except Exception as e:
        logger.error(f"IFRC API import error: {e}", exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)


@ai_docs_bp.route("/ifrc-api/import-bulk", methods=["POST"])
@admin_required
@permission_required("admin.documents.manage")
@limiter.limit("5 per minute")
def import_ifrc_api_documents_bulk():
    """
    Bulk import documents from IFRC API in parallel.
    """
    try:
        data = get_json_safe()
        # Support base64-wrapped payload to avoid WAF false positives on external URLs
        # in the request body (same pattern as settings/translations endpoints).
        _payload_b64 = data.get("payload") or data.get("payload_b64")
        if _payload_b64:
            try:
                data = json.loads(base64.b64decode(str(_payload_b64)).decode("utf-8"))
            except Exception:
                return json_bad_request("Invalid payload encoding")
        items = data.get("items") or []
        if not isinstance(items, list) or not items:
            return json_bad_request("items is required")

        concurrency = int(data.get("concurrency") or current_app.config.get("AI_DOCS_IFRC_IMPORT_CONCURRENCY", 2))
        concurrency = max(1, min(concurrency, 4))
        logger.info(
            "Bulk IFRC import requested: user_id=%s items=%s concurrency=%s",
            getattr(current_user, "id", None),
            len(items),
            concurrency,
        )

        job_id = str(uuid.uuid4())
        job = AIJob(
            id=job_id,
            job_type="ifrc_api_bulk",
            user_id=int(current_user.id),
            status="queued",
            total_items=len(items),
            meta={"concurrency": concurrency},
        )
        db.session.add(job)
        db.session.flush()

        for idx, it in enumerate(items):
            if not isinstance(it, dict):
                continue
            url = _normalize_ifrc_source_url((it.get("url") or "").strip())
            title = (it.get("title") or None)
            _ip = it.get("is_public")
            is_public = True if _ip is None else (bool(_ip) if not isinstance(_ip, str) else _ip.lower() in ("true", "1", "yes"))
            raw_country_id = it.get("country_id")
            country_id_val = None
            try:
                if raw_country_id is not None and str(raw_country_id).strip():
                    country_id_val = int(raw_country_id)
            except Exception as e:
                logger.debug("country_id parse failed for bulk item: %s", e)
                country_id_val = None
            country_name_val = (it.get("country_name") or None)

            status = "queued"
            err = None
            if not url:
                status = "failed"
                err = "Missing URL"
            else:
                ok, reason = _validate_ifrc_fetch_url(url)
                if not ok:
                    status = "failed"
                    err = reason

            job_item = AIJobItem(
                job_id=job_id,
                item_index=idx,
                entity_type=None,
                entity_id=None,
                status=status,
                error=err,
                payload={
                    "url": url,
                    "title": title,
                    "is_public": is_public,
                    "country_id": country_id_val,
                    "country_name": country_name_val,
                },
            )
            db.session.add(job_item)

        db.session.commit()

        t = threading.Thread(
            target=_run_ifrc_bulk_import_job,
            args=(current_app._get_current_object(), job_id),
            daemon=True,
        )
        t.start()

        return json_accepted(
            job_id=job_id,
            total=len(items),
            concurrency=concurrency,
            message="Bulk import started",
        )
    except Exception as e:
        logger.error("Bulk IFRC import start error: %s", e, exc_info=True)
        db.session.rollback()
        return json_server_error(GENERIC_ERROR_MESSAGE)


@ai_docs_bp.route("/ifrc-api/import-bulk/<job_id>/status", methods=["GET"])
@admin_required
@permission_required("admin.documents.manage")
def import_ifrc_bulk_status(job_id: str):
    """Return job + item statuses for a bulk IFRC import."""
    try:
        job = AIJob.query.get(str(job_id))
        if not job:
            return json_not_found("not_found")

        if int(job.user_id or 0) != int(current_user.id):
            pass

        items = job.items or []
        completed = sum(1 for it in items if it.status == "completed")
        failed = sum(1 for it in items if it.status == "failed")
        cancelled = sum(1 for it in items if it.status == "cancelled")
        processing = sum(1 for it in items if it.status in ("downloading", "processing", "queued"))

        doc_ids = [int(it.entity_id) for it in items if (it.entity_type == "ai_document" and it.entity_id)]
        docs_by_id = {}
        if doc_ids:
            docs = AIDocument.query.filter(AIDocument.id.in_(doc_ids)).all()
            for d in docs:
                docs_by_id[int(d.id)] = {
                    "processing_status": d.processing_status,
                    "processing_error": d.processing_error,
                    "total_chunks": d.total_chunks,
                    "processed_at": d.processed_at.isoformat() if d.processed_at else None,
                }

        job_data = {
            "id": job.id,
            "job_type": job.job_type,
            "status": job.status,
            "total_items": job.total_items,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "error": job.error,
            "meta": job.meta or {},
            "counts": {"completed": completed, "failed": failed, "cancelled": cancelled, "in_progress": processing},
        }
        items_data = [
            {
                "id": it.id,
                "index": it.item_index,
                "url": (it.payload or {}).get("url") if isinstance(it.payload, dict) else None,
                "title": (it.payload or {}).get("title") if isinstance(it.payload, dict) else None,
                "import_status": it.status,
                "import_error": it.error,
                "ai_document_id": (int(it.entity_id) if (it.entity_type == "ai_document" and it.entity_id) else None),
                "document": docs_by_id.get(int(it.entity_id)) if (it.entity_type == "ai_document" and it.entity_id) else None,
            }
            for it in items
        ]
        return json_ok(job=job_data, items=items_data)
    except Exception as e:
        logger.error("Bulk IFRC import status error: %s", e, exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)


@ai_docs_bp.route("/ifrc-api/import-bulk/<job_id>/cancel", methods=["POST"])
@admin_required
@permission_required("admin.documents.manage")
def import_ifrc_bulk_cancel(job_id: str):
    """Request cancellation for a running bulk IFRC import job (best-effort)."""
    try:
        job = AIJob.query.get(str(job_id))
        if not job:
            return json_not_found("not_found")
        if int(job.user_id or 0) != int(current_user.id):
            pass
        if job.status in ("completed", "failed", "cancelled"):
            return json_ok(status=job.status, message="Job already finished")
        job.status = "cancel_requested"
        try:
            (
                db.session.query(AIJobItem)
                .filter(
                    AIJobItem.job_id == str(job_id),
                    AIJobItem.status == "queued",
                )
                .update(
                    {
                        AIJobItem.status: "cancelled",
                        AIJobItem.error: None,
                    },
                    synchronize_session=False,
                )
            )
        except Exception as e:
            logger.debug("bulk cancel items update failed: %s", e)
            db.session.rollback()
        db.session.commit()
        _get_import_job_cancel_event(str(job_id)).set()
        return json_ok(status="cancel_requested")
    except Exception as e:
        logger.error("Bulk IFRC import cancel error: %s", e, exc_info=True)
        db.session.rollback()
        return json_server_error(GENERIC_ERROR_MESSAGE)
