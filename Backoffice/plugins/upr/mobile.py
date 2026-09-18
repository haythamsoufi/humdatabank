"""Mobile unified-planning config and PDF thumbnail helpers."""

from __future__ import annotations

from collections import OrderedDict
from contextlib import suppress
from hashlib import sha256
from threading import Lock

from flask import current_app, make_response, request

from app.utils.constants import APPEALS_TYPE_DEFAULT_IDS_STR, APPEALS_TYPE_DISPLAY_NAMES
from app.utils.mobile_responses import mobile_bad_request, mobile_ok, mobile_server_error

_UNIFIED_PLANNING_THUMB_JPEG: "OrderedDict[str, bytes]" = OrderedDict()
_UNIFIED_PLANNING_THUMB_LOCK = Lock()
_UNIFIED_PLANNING_THUMB_MAX_ENTRIES = 128


def unified_planning_config():
    """Public config for unified planning documents: IFRC GO API URL and type IDs."""
    from app.routes.ai_documents.helpers import _get_ifrc_basic_auth

    base = "https://go-api.ifrc.org/Api/PublicSiteAppeals"
    ids = APPEALS_TYPE_DEFAULT_IDS_STR
    document_types = [
        {"id": tid, "label": APPEALS_TYPE_DISPLAY_NAMES[tid]}
        for tid in sorted(APPEALS_TYPE_DISPLAY_NAMES.keys())
    ]
    return mobile_ok(
        data={
            "ifrc_public_site_appeals_base_url": base,
            "appeals_type_ids": ids,
            "ifrc_public_site_appeals_url": f"{base}?AppealsTypeId={ids}",
            "document_types": document_types,
            "pdf_thumbnail_enabled": _get_ifrc_basic_auth() is not None,
        },
    )


def unified_planning_thumbnail():
    """Return a small JPEG of the PDF first page for unified-planning grid tiles."""
    import base64
    from urllib.parse import unquote

    import fitz  # PyMuPDF
    import requests

    from app.routes.ai_documents.helpers import (
        _get_ifrc_basic_auth,
        _ifrc_get_with_validated_redirects,
        _validate_ifrc_fetch_url,
    )
    from app.utils.api_helpers import get_json_safe

    _max_url_len = int(current_app.config.get("UNIFIED_PLANNING_THUMB_MAX_URL_CHARS") or 16384)
    _max_b64_len = int(current_app.config.get("UNIFIED_PLANNING_THUMB_MAX_URL_B64_CHARS") or 32768)

    if request.method == "POST":
        data = get_json_safe()
        raw = ""
        if isinstance(data, dict):
            url_b64 = (data.get("url_b64") or "").strip()
            if url_b64:
                if len(url_b64) > _max_b64_len:
                    return mobile_bad_request("url_b64 is too long")
                try:
                    pad = (-len(url_b64)) % 4
                    if pad:
                        url_b64 += "=" * pad
                    raw = base64.urlsafe_b64decode(url_b64.encode("ascii")).decode("utf-8")
                except Exception:
                    return mobile_bad_request("Invalid url_b64")
            else:
                raw = (data.get("url") or "").strip()
    else:
        raw = (request.args.get("url") or "").strip()
    if len(raw) > _max_url_len:
        return mobile_bad_request("url is too long")
    url = unquote(raw).strip()
    ok, err = _validate_ifrc_fetch_url(url)
    if not ok:
        return mobile_bad_request(err)

    cache_key = sha256(url.encode("utf-8")).hexdigest()
    with _UNIFIED_PLANNING_THUMB_LOCK:
        cached = _UNIFIED_PLANNING_THUMB_JPEG.get(cache_key)
        if cached is not None:
            _UNIFIED_PLANNING_THUMB_JPEG.move_to_end(cache_key)
            resp = make_response(cached)
            resp.headers["Content-Type"] = "image/jpeg"
            resp.headers["Cache-Control"] = "public, max-age=86400"
            return resp

    max_bytes = int(current_app.config.get("UNIFIED_PLANNING_THUMB_MAX_BYTES") or (12 * 1024 * 1024))
    auth = _get_ifrc_basic_auth()
    if auth is None:
        current_app.logger.warning("unified_planning_thumbnail: IFRC basic auth not configured")
        return mobile_bad_request("IFRC credentials are not configured on the server")

    r = None
    try:
        r = _ifrc_get_with_validated_redirects(
            url,
            headers={"User-Agent": "hum-databank-backoffice/1.0"},
            auth=auth,
            timeout=90,
            stream=True,
        )
        if r.status_code != 200:
            return mobile_bad_request(f"Upstream HTTP {r.status_code}")
        cl = r.headers.get("Content-Length")
        if cl is not None:
            with suppress(ValueError):
                if int(cl) > max_bytes:
                    return mobile_bad_request("PDF too large for thumbnail")
        chunks = []
        total = 0
        for chunk in r.iter_content(chunk_size=65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                return mobile_bad_request("PDF too large for thumbnail")
            chunks.append(chunk)
        pdf_bytes = b"".join(chunks)
    except requests.RequestException as e:
        current_app.logger.warning("unified_planning_thumbnail fetch: %s", e)
        return mobile_server_error()
    finally:
        if r is not None:
            with suppress(Exception):
                r.close()

    doc = None
    jpeg_bytes = b""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if doc.page_count < 1:
            return mobile_bad_request("PDF has no pages")
        page = doc.load_page(0)
        rect = page.rect
        if rect.width <= 0:
            return mobile_bad_request("Invalid PDF page size")
        zoom = min(280.0 / float(rect.width), 2.5)
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        jpeg_bytes = pix.tobytes("jpeg", jpg_quality=82)
    except Exception as e:
        current_app.logger.warning("unified_planning_thumbnail render: %s", e, exc_info=True)
        return mobile_bad_request("Could not render PDF thumbnail")
    finally:
        if doc is not None:
            with suppress(Exception):
                doc.close()

    if not jpeg_bytes:
        return mobile_server_error()

    with _UNIFIED_PLANNING_THUMB_LOCK:
        _UNIFIED_PLANNING_THUMB_JPEG[cache_key] = jpeg_bytes
        _UNIFIED_PLANNING_THUMB_JPEG.move_to_end(cache_key)
        while len(_UNIFIED_PLANNING_THUMB_JPEG) > _UNIFIED_PLANNING_THUMB_MAX_ENTRIES:
            _UNIFIED_PLANNING_THUMB_JPEG.popitem(last=False)

    resp = make_response(jpeg_bytes)
    resp.headers["Content-Type"] = "image/jpeg"
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp
