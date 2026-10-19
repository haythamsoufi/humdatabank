"""Copy global FDRS resources (data.ifrc.org) into Manage Resources.

The legacy catalog is ``GET /api/documents?isglobal=true`` on
``https://data-api.ifrc.org``. Each row is one file or one video, not one
library record. This groups language copies of the same publication, skips
files already stored under the same filename, and leaves Databank-only
resources in place.

Dry-run planning is pure. Writing files and rows is ``apply_plan``.
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Optional

SUBCATEGORY_BY_TYPE = {
    "EveryoneCounts": "Everyone Counts",
    "Analysis": "Analysis",
    "DocumentGuide": "Document Guide",
    "FrontendVideo": "Frontend Video",
    "VideoGuide": "Video Guide",
}
_LANG_WORDS = {"en", "fr", "es", "ar", "sp", "english", "french", "spanish", "arabic"}
_LANG_ALIASES = {"sp": "es"}
_DUP_SUFFIX_RE = re.compile(r"(?:\(\d+\)|_[1-9]\d?)$")
_YOUTUBE_HOSTS = {"youtu.be", "www.youtu.be", "youtube.com", "www.youtube.com", "m.youtube.com"}


@dataclass(frozen=True)
class FdrsResourceDoc:
    document_type: str
    year: Optional[int]
    language: str
    name: str
    description: str
    url: str
    thumbnail: str

    @property
    def is_video(self) -> bool:
        return _is_youtube(self.url) or self.document_type in {"FrontendVideo", "VideoGuide"}


@dataclass
class ResourceGroup:
    key: tuple
    document_type: str
    year: Optional[int]
    title: str
    description: str
    docs: list[FdrsResourceDoc] = field(default_factory=list)


@dataclass(frozen=True)
class StoredTranslation:
    resource_id: int
    resource_title: str
    resource_type: str
    subcategory: Optional[str]
    language: str
    filename: str
    external_url: str


def normalize_filename(name: str | None) -> str:
    """Lower-case file name used to match a FDRS row to a stored translation."""
    text = urllib.parse.unquote((name or "").replace("\\", "/").split("/")[-1]).casefold()
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_language(code: str | None) -> str:
    lang = (code or "").strip().casefold()
    lang = _LANG_ALIASES.get(lang, lang)
    if not re.fullmatch(r"[a-z]{2}", lang or ""):
        return "en"
    return lang


def _is_youtube(url: str) -> bool:
    host = (urllib.parse.urlsplit(url or "").netloc or "").casefold()
    return host in _YOUTUBE_HOSTS


def canonical_url(url: str) -> str:
    """Identity for a file URL or a YouTube link."""
    raw = (url or "").strip()
    parts = urllib.parse.urlsplit(raw)
    host = (parts.netloc or "").casefold()
    if host in _YOUTUBE_HOSTS:
        if host.endswith("youtu.be"):
            video_id = parts.path.strip("/").split("/")[0]
        else:
            video_id = urllib.parse.parse_qs(parts.query).get("v", [""])[0]
            if not video_id and parts.path.startswith("/embed/"):
                video_id = parts.path.split("/")[2] if len(parts.path.split("/")) > 2 else ""
        if video_id:
            return f"youtube:{video_id}"
    path = urllib.parse.unquote(parts.path or "").casefold()
    return f"{host}{path}"


def _stem(name: str) -> str:
    base = urllib.parse.unquote((name or "").replace("\\", "/").split("/")[-1])
    if "." in base:
        base = base.rsplit(".", 1)[0]
    return base.strip()


def _without_duplicate_suffix(stem: str) -> str:
    return _DUP_SUFFIX_RE.sub("", stem).strip()


def _content_stem(name: str) -> str:
    """Title stem with language words and a trailing duplicate suffix removed."""
    stem = _without_duplicate_suffix(_stem(name))
    tokens = re.sub(r"[^a-z0-9]+", " ", stem.casefold()).split()
    kept = [token for token in tokens if token not in _LANG_WORDS]
    return " ".join(kept).strip()


def _display_title(name: str) -> str:
    stem = _without_duplicate_suffix(_stem(name))
    stem = re.sub(r"\((?:en|fr|es|ar|sp|english|french|spanish|arabic)\)", " ", stem, flags=re.IGNORECASE)
    tokens = []
    for token in re.sub(r"[_\s]+", " ", stem).split():
        if token.casefold() in _LANG_WORDS:
            continue
        tokens.append(token)
    text = " ".join(tokens).strip()
    return (text or stem).strip()[:255] or "Untitled"


def parse_catalog(payload: Any) -> list[FdrsResourceDoc]:
    """Flatten ``[{code, documents}]`` into resource rows. Society documents are ignored."""
    if not isinstance(payload, list):
        return []
    docs: list[FdrsResourceDoc] = []
    for block in payload:
        if not isinstance(block, dict):
            continue
        code = (block.get("code") or "").strip()
        if code:
            continue
        for row in block.get("documents") or []:
            if not isinstance(row, dict):
                continue
            url = (row.get("url") or "").strip()
            name = (row.get("name") or row.get("title") or "").strip()
            if not url or not name:
                continue
            year_raw = row.get("year")
            try:
                year = int(year_raw) if year_raw not in (None, "") else None
            except (TypeError, ValueError):
                year = None
            docs.append(FdrsResourceDoc(
                document_type=(row.get("document_type") or "DocumentGuide").strip() or "DocumentGuide",
                year=year,
                language=normalize_language(row.get("LangCode") or row.get("language")),
                name=name,
                description=(row.get("Description") or row.get("description") or "").strip(),
                url=url,
                thumbnail=(row.get("thumbnail") or row.get("Thumbnail") or "").strip(),
            ))
    return docs


def _duplicate_rank(doc: FdrsResourceDoc) -> tuple:
    """Prefer the copy without a ``(1)`` / ``_1`` suffix, then Frontend Video."""
    type_rank = 1 if doc.document_type == "FrontendVideo" else 0
    clean = 1 if _without_duplicate_suffix(_stem(doc.name)) == _stem(doc.name) else 0
    return (clean, type_rank, len(doc.description))


def dedupe_documents(docs: Iterable[FdrsResourceDoc]) -> tuple[list[FdrsResourceDoc], list[FdrsResourceDoc]]:
    """Drop same-URL copies and ``(1)`` / ``_1`` twins of a file we already keep."""
    by_url: dict[str, FdrsResourceDoc] = {}
    for doc in docs:
        key = canonical_url(doc.url)
        current = by_url.get(key)
        if current is None or _duplicate_rank(doc) > _duplicate_rank(current):
            by_url[key] = doc
    kept = list(by_url.values())
    by_loose: dict[tuple, FdrsResourceDoc] = {}
    for doc in kept:
        if doc.is_video:
            loose = ("video", canonical_url(doc.url))
        else:
            loose = (doc.document_type, doc.year, doc.language, _content_stem(doc.name))
        current = by_loose.get(loose)
        if current is None or _duplicate_rank(doc) > _duplicate_rank(current):
            by_loose[loose] = doc
    chosen_ids = {id(doc) for doc in by_loose.values()}
    skipped = [doc for doc in docs if id(doc) not in chosen_ids]
    return list(by_loose.values()), skipped


def _group_key(doc: FdrsResourceDoc) -> tuple:
    if doc.document_type == "EveryoneCounts":
        return ("EveryoneCounts", doc.year or 0)
    if doc.is_video:
        return ("video", _content_stem(doc.name))
    return (doc.document_type, _content_stem(doc.name))


def _group_type(docs: list[FdrsResourceDoc]) -> str:
    types = {doc.document_type for doc in docs}
    if "FrontendVideo" in types:
        return "FrontendVideo"
    if "VideoGuide" in types:
        return "VideoGuide"
    return docs[0].document_type


def group_documents(docs: Iterable[FdrsResourceDoc]) -> list[ResourceGroup]:
    buckets: dict[tuple, list[FdrsResourceDoc]] = {}
    for doc in docs:
        buckets.setdefault(_group_key(doc), []).append(doc)
    groups: list[ResourceGroup] = []
    for key, rows in buckets.items():
        english = next((row for row in rows if row.language == "en"), None)
        source = english or min(rows, key=lambda row: (len(_display_title(row.name)), row.name.casefold()))
        years = [row.year for row in rows if row.year]
        year = years[0] if len(set(years)) == 1 else source.year
        title = _display_title(source.name)
        document_type = _group_type(rows)
        if document_type == "EveryoneCounts" and year and "count" not in title.casefold():
            title = f"Everyone Counts {year}"
        groups.append(ResourceGroup(
            key=key,
            document_type=document_type,
            year=year,
            title=title,
            description=source.description,
            docs=sorted(rows, key=lambda row: (row.language != "en", row.language, row.name)),
        ))
    return sorted(groups, key=lambda group: (group.document_type, group.year or 0, group.title.casefold()))


def build_plan(
    docs: Iterable[FdrsResourceDoc],
    stored: Iterable[StoredTranslation],
) -> dict[str, Any]:
    """Compare the FDRS catalog with stored translations. Nothing is written."""
    catalog = list(docs)
    deduped, skipped = dedupe_documents(catalog)
    groups = group_documents(deduped)
    by_filename = {}
    by_url = {}
    for row in stored:
        if row.filename:
            by_filename.setdefault(normalize_filename(row.filename), row)
        if row.external_url:
            by_url.setdefault(canonical_url(row.external_url), row)

    file_rows: list[dict[str, Any]] = []
    to_create: list[dict[str, Any]] = []
    to_attach: list[dict[str, Any]] = []
    matched_filenames: set[str] = set()
    matched_urls: set[str] = set()

    for group in groups:
        hits: list[StoredTranslation] = []
        pending: list[FdrsResourceDoc] = []
        for doc in group.docs:
            if doc.is_video:
                found = by_url.get(canonical_url(doc.url))
            else:
                found = by_filename.get(normalize_filename(doc.name))
            if found is None:
                pending.append(doc)
                continue
            hits.append(found)
            if doc.is_video:
                matched_urls.add(canonical_url(doc.url))
            else:
                matched_filenames.add(normalize_filename(doc.name))
            file_rows.append({
                "status": "in_databank",
                "type": doc.document_type,
                "year": doc.year,
                "language": doc.language,
                "name": doc.name,
                "databank_id": found.resource_id,
                "databank_title": found.resource_title,
            })
        resource_id = hits[0].resource_id if hits else None
        for doc in pending:
            file_rows.append({
                "status": "missing",
                "type": doc.document_type,
                "year": doc.year,
                "language": doc.language,
                "name": doc.name,
                "databank_id": resource_id,
                "databank_title": hits[0].resource_title if hits else None,
            })
        action = {
            "type": group.document_type,
            "subcategory": SUBCATEGORY_BY_TYPE.get(group.document_type, group.document_type),
            "year": group.year,
            "title": group.title,
            "description": group.description,
            "resource_id": resource_id,
            "files": [
                {
                    "language": doc.language,
                    "name": doc.name,
                    "url": doc.url,
                    "thumbnail": doc.thumbnail,
                    "video": doc.is_video,
                }
                for doc in pending
            ],
        }
        if not pending:
            continue
        if resource_id is None:
            to_create.append(action)
        else:
            to_attach.append(action)

    only_databank = []
    for row in stored:
        filename_key = normalize_filename(row.filename) if row.filename else ""
        url_key = canonical_url(row.external_url) if row.external_url else ""
        if filename_key and filename_key in matched_filenames:
            continue
        if url_key and url_key in matched_urls:
            continue
        if not filename_key and not url_key:
            continue
        only_databank.append({
            "status": "only_databank",
            "resource_id": row.resource_id,
            "title": row.resource_title,
            "language": row.language,
            "name": row.filename or row.external_url,
            "subcategory": row.subcategory,
        })

    return {
        "fdrs_rows": len(catalog),
        "deduped": len(deduped),
        "duplicates_skipped": len(skipped),
        "in_databank": sum(1 for row in file_rows if row["status"] == "in_databank"),
        "missing": sum(1 for row in file_rows if row["status"] == "missing"),
        "create_resources": len(to_create),
        "attach_to_existing": len(to_attach),
        "only_databank": len(only_databank),
        "files": sorted(file_rows, key=lambda row: (row["type"], row["year"] or 0, row["name"].casefold())),
        "only_databank_files": only_databank,
        "create": to_create,
        "attach": to_attach,
        "skipped_duplicates": [
            {"type": doc.document_type, "language": doc.language, "name": doc.name}
            for doc in skipped
        ],
    }


def fetch_global_catalog(base_url: str, api_key: str, *, timeout: int = 180) -> Any:
    """Download the global FDRS document list. The key is not logged."""
    import json
    import urllib.request

    base = (base_url or "https://data-api.ifrc.org").rstrip("/")
    query = urllib.parse.urlencode({"apiKey": api_key, "isglobal": "true"})
    request = urllib.request.Request(
        f"{base}/api/documents?{query}",
        headers={"User-Agent": "HumanitarianDatabank-FDRS-resource-sync/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator base
        return json.loads(response.read().decode("utf-8"))


def download_bytes(url: str, *, timeout: int = 120) -> bytes:
    """GET a FDRS file. Spaces in the path are percent-encoded."""
    import urllib.error
    import urllib.request

    raw = (url or "").strip()
    if not raw or _is_youtube(raw):
        raise ValueError("not a file url")
    parts = urllib.parse.urlsplit(raw)
    encoded = urllib.parse.urlunsplit((
        parts.scheme,
        parts.netloc,
        urllib.parse.quote(parts.path, safe="/"),
        parts.query,
        parts.fragment,
    ))
    request = urllib.request.Request(
        encoded,
        headers={"User-Agent": "HumanitarianDatabank-FDRS-resource-sync/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.read()
    except urllib.error.HTTPError as exc:
        raise ValueError(f"HTTP {exc.code}") from exc


def ensure_external_url_column() -> None:
    """Add the link column when this build of the app has not been migrated yet."""
    from app.extensions import db
    from sqlalchemy import text

    db.session.execute(text(
        "ALTER TABLE resource_translation ADD COLUMN IF NOT EXISTS external_url VARCHAR(1000)"
    ))
    db.session.commit()


def _external_urls() -> dict[int, str]:
    from app.extensions import db
    from sqlalchemy import text

    try:
        rows = db.session.execute(text(
            "SELECT id, external_url FROM resource_translation "
            "WHERE external_url IS NOT NULL AND external_url <> ''"
        )).all()
    except Exception:
        db.session.rollback()
        return {}
    return {int(row[0]): str(row[1]).strip() for row in rows if row[1]}


def _store_external_url(translation, url: str) -> None:
    """Persist a public link even when the running model predates the column."""
    from app.extensions import db
    from sqlalchemy import text

    cleaned = (url or "").strip()[:1000]
    if hasattr(type(translation), "external_url"):
        translation.external_url = cleaned
    db.session.flush()
    db.session.execute(
        text("UPDATE resource_translation SET external_url = :url WHERE id = :id"),
        {"url": cleaned, "id": translation.id},
    )


def apply_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Create missing resources and download their files. Existing files stay."""
    import uuid
    from io import BytesIO

    from werkzeug.datastructures import FileStorage
    from werkzeug.utils import secure_filename

    from app.extensions import db
    from app.models.documents import Resource, ResourceSubcategory, ResourceTranslation
    from app.services.platform import storage_service as storage

    created = 0
    attached = 0
    saved = 0
    errors: list[str] = []

    def subcategory_for(name: str) -> ResourceSubcategory:
        row = ResourceSubcategory.query.filter(
            db.func.lower(ResourceSubcategory.name) == name.casefold()
        ).first()
        if row is not None:
            return row
        row = ResourceSubcategory(name=name[:120], display_order=100)
        db.session.add(row)
        db.session.flush()
        return row

    def folder_for(resource: Resource) -> str:
        for translation in resource.translations:
            path = (translation.file_relative_path or "").replace("\\", "/")
            if path:
                return path.split("/")[0]
        return str(uuid.uuid4())

    def store_thumbnail(translation, folder: str, *, file_bytes: bytes | None = None, remote_url: str = "") -> None:
        """Keep a cover image: the FDRS thumbnail, otherwise one we render."""
        if translation.thumbnail_relative_path:
            return
        from app.services.content.thumbnail_service import ThumbnailService

        before = translation.thumbnail_relative_path
        ThumbnailService.ensure_for_translation(
            translation,
            folder,
            category=storage.RESOURCES,
            file_bytes=file_bytes,
            remote_thumbnail_url=remote_url,
        )
        if not translation.thumbnail_relative_path and (remote_url or file_bytes or translation.file_relative_path or translation.external_url):
            label = translation.filename or translation.title or translation.language_code
            if before == translation.thumbnail_relative_path:
                errors.append(f"{label}: thumbnail was not generated")

    def store_file(resource: Resource, language: str, filename: str, data: bytes, *, thumbnail: bool) -> str:
        safe = secure_filename(filename) or "document"
        folder = folder_for(resource)
        middle = f"{language}/thumbnails" if thumbnail else language
        relative = f"{folder}/{middle}/{safe}"
        storage.upload(storage.RESOURCES, relative, FileStorage(stream=BytesIO(data), filename=safe))
        return relative

    for action in list(plan.get("create") or []) + list(plan.get("attach") or []):
        try:
            resource = Resource.query.get(action["resource_id"]) if action.get("resource_id") else None
            if resource is None:
                published = date(action["year"], 1, 1) if action.get("year") else None
                resource = Resource(
                    resource_type="publication",
                    default_title=(action.get("title") or "Untitled")[:255],
                    default_description=action.get("description") or None,
                    publication_date=published,
                    resource_subcategory=subcategory_for(action["subcategory"]),
                )
                db.session.add(resource)
                db.session.flush()
                created += 1
            else:
                attached += 1
                if resource.resource_type != "publication":
                    resource.resource_type = "publication"
                if resource.resource_subcategory_id is None:
                    resource.resource_subcategory = subcategory_for(action["subcategory"])
            print(f"syncing {action.get('title')}", flush=True)
            for item in action.get("files") or []:
                language = normalize_language(item.get("language"))
                translation = resource.get_translation(language)
                if translation is None:
                    translation = ResourceTranslation(
                        resource_id=resource.id,
                        language_code=language,
                        title=(action.get("title") or item.get("name") or "Untitled")[:255],
                        description=action.get("description") or None,
                    )
                    db.session.add(translation)
                    db.session.flush()
                if item.get("video"):
                    _store_external_url(translation, item.get("url") or "")
                    store_thumbnail(
                        translation,
                        folder_for(resource),
                        remote_url=(item.get("thumbnail") or "").strip(),
                    )
                    saved += 1
                    continue
                if translation.file_relative_path:
                    store_thumbnail(
                        translation,
                        folder_for(resource),
                        remote_url=(item.get("thumbnail") or "").strip(),
                    )
                    continue
                data = download_bytes(item["url"])
                translation.file_relative_path = store_file(
                    resource, language, item.get("name") or "document", data, thumbnail=False,
                )
                translation.filename = (item.get("name") or "")[:255]
                saved += 1
                store_thumbnail(
                    translation,
                    folder_for(resource),
                    file_bytes=data,
                    remote_url=(item.get("thumbnail") or "").strip(),
                )
            db.session.commit()
        except Exception as exc:  # noqa: BLE001 — keep going and report the publication
            db.session.rollback()
            errors.append(f"{action.get('title')}: {exc}")
    return {"created": created, "attached": attached, "saved": saved, "errors": errors}


def stored_translations_from_db() -> list[StoredTranslation]:
    from app.models.documents import Resource

    saved_urls = _external_urls()
    rows: list[StoredTranslation] = []
    for resource in Resource.query.order_by(Resource.id.asc()).all():
        subcategory = resource.resource_subcategory.name if resource.resource_subcategory else None
        for translation in resource.translations:
            rows.append(StoredTranslation(
                resource_id=resource.id,
                resource_title=resource.default_title,
                resource_type=resource.resource_type,
                subcategory=subcategory,
                language=normalize_language(translation.language_code),
                filename=(translation.filename or "").strip(),
                external_url=saved_urls.get(translation.id) or (getattr(translation, "external_url", None) or "").strip(),
            ))
    return rows
