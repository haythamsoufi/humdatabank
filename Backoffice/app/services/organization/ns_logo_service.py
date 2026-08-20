"""Download FDRS National Society logos (ISO3 filenames) into system storage."""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from io import BytesIO
from typing import Any, Callable

from werkzeug.datastructures import FileStorage

from app.extensions import db
from app.models.core import Country
from app.models.organization import NationalSociety
from app.utils.file_paths import save_system_logo
from app.utils.sector_logo_urls import github_ns_logo_url

logger = logging.getLogger(__name__)

NS_LOGO_SUBDIR = "ns"
GITHUB_CONTENTS_URL = "https://api.github.com/repos/FDRS-ifrc/general/contents/ns_logos"
_ISO3_RE = re.compile(r"^[A-Za-z]{3}$")
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_USER_AGENT = "Humanitarian-Databank-NS-Logo-Sync"


class NsLogoSyncError(RuntimeError):
    """Raised when GitHub listing or download fails."""


def iso3_from_logo_filename(name: str | None) -> str | None:
    raw = (name or "").strip().replace("\\", "/").split("/")[-1]
    if not raw or "." not in raw:
        return None
    stem, ext = raw.rsplit(".", 1)
    if f".{ext.lower()}" not in _IMAGE_EXTS:
        return None
    if not _ISO3_RE.match(stem):
        return None
    return stem.upper()


def _http_get(url: str, timeout: int = 30) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise NsLogoSyncError(f"HTTP {exc.code} fetching {url}") from exc
    except urllib.error.URLError as exc:
        raise NsLogoSyncError(f"Could not fetch {url}: {exc.reason}") from exc


def list_github_logo_files(*, fetch: Callable[[str], bytes] | None = None) -> dict[str, str]:
    """Map ISO3 -> GitHub download URL for image files in ns_logos."""
    getter = fetch or _http_get
    payload = json.loads(getter(GITHUB_CONTENTS_URL).decode("utf-8"))
    if not isinstance(payload, list):
        raise NsLogoSyncError("Unexpected GitHub contents response for ns_logos.")
    out: dict[str, str] = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        iso3 = iso3_from_logo_filename(row.get("name") or "")
        url = (row.get("download_url") or "").strip()
        if iso3 and url:
            out[iso3] = url
    return out


def _file_storage(filename: str, data: bytes) -> FileStorage:
    return FileStorage(stream=BytesIO(data), filename=filename, content_type="image/png")


def societies_for_iso3(iso3: str) -> list[NationalSociety]:
    code = (iso3 or "").strip().upper()
    if not code:
        return []
    countries = Country.query.filter(db.func.upper(Country.iso3) == code).all()
    rows: list[NationalSociety] = []
    for country in countries:
        rows.extend(list(getattr(country, "national_societies", []) or []))
    return rows


def sync_ns_logos_from_github(
    *,
    dry_run: bool = False,
    overwrite: bool = False,
    iso3: str | None = None,
    fetch: Callable[[str], bytes] | None = None,
) -> dict[str, Any]:
    """Download FDRS ns_logos and attach them to National Societies by country ISO3."""
    getter = fetch or _http_get
    wanted = (iso3 or "").strip().upper() or None
    try:
        listed = list_github_logo_files(fetch=getter)
    except NsLogoSyncError:
        if not wanted:
            raise
        listed = {}
    if wanted:
        listed = {code: url for code, url in listed.items() if code == wanted}
        if wanted not in listed:
            listed[wanted] = github_ns_logo_url(wanted) or ""

    matched = 0
    updated = 0
    skipped = 0
    missing_ns = 0
    errors: list[str] = []

    for code, url in sorted(listed.items()):
        nss = societies_for_iso3(code)
        if not nss:
            missing_ns += 1
            continue
        matched += 1
        existing = [row for row in nss if (row.logo_filename or "").strip()]
        if existing and not overwrite:
            skipped += len(nss)
            continue
        if dry_run:
            updated += len(nss)
            continue
        if not url:
            errors.append(f"{code}: no download URL")
            continue
        try:
            data = getter(url)
        except NsLogoSyncError as exc:
            errors.append(f"{code}: {exc}")
            continue
        if not data:
            errors.append(f"{code}: empty file")
            continue
        filename = f"{code}.png"
        try:
            stored = save_system_logo(_file_storage(filename, data), code, subdir=NS_LOGO_SUBDIR)
        except Exception as exc:
            logger.exception("NS logo upload failed for %s", code)
            errors.append(f"{code}: {exc}")
            continue
        if not stored:
            errors.append(f"{code}: storage returned no filename")
            continue
        for row in nss:
            row.logo_filename = stored
            updated += 1
        db.session.flush()

    if not dry_run:
        db.session.commit()

    return {
        "github_files": len(listed),
        "countries_with_ns": matched,
        "updated": updated,
        "skipped": skipped,
        "no_national_society": missing_ns,
        "errors": errors,
        "dry_run": dry_run,
    }
