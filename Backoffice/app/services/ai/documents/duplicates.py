"""
AI knowledge-base duplicate detection and deduplication.

Duplicates are identified by exact ``content_hash`` (SHA-256 of file bytes) as the
primary key. When a document has no hash, normalized ``source_url`` is used as a
secondary signal. Titles/filenames are never used for matching.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit, urlunsplit

from app.extensions import db
from app.models import AIDocument

logger = logging.getLogger(__name__)

_STATUS_RANK = {
    "completed": 3,
    "processing": 2,
    "pending": 1,
    "failed": 0,
}


def normalize_dedupe_source_url(url: Optional[str]) -> str:
    """
    Normalize a source URL for duplicate matching.

    Mirrors IFRC import normalization: lowercase host, drop default ports,
    collapse duplicate slashes, keep query, drop fragment.
    """
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
        scheme = (parts.scheme or "").lower()
        hostname = (parts.hostname or "").lower()
        netloc = hostname
        if parts.port:
            if not (
                (scheme == "https" and int(parts.port) == 443)
                or (scheme == "http" and int(parts.port) == 80)
            ):
                netloc = f"{hostname}:{int(parts.port)}"
        path = parts.path or "/"
        path = re.sub(r"/{2,}", "/", path)
        return urlunsplit((scheme, netloc, path, parts.query or "", ""))
    except Exception as e:
        logger.debug("normalize_dedupe_source_url failed: %s", e)
        return raw


def _is_linked(doc: AIDocument) -> bool:
    return bool(getattr(doc, "submitted_document_id", None) or getattr(doc, "guidance_document_id", None))


def _status_rank(doc: AIDocument) -> int:
    status = (getattr(doc, "processing_status", None) or "").strip().lower()
    return _STATUS_RANK.get(status, 0)


def choose_keeper(docs: Sequence[AIDocument]) -> AIDocument:
    """
    Pick which document to keep in a duplicate group.

    Preference order:
    1. Linked to SubmittedDocument / GuidanceDocument
    2. Higher processing status (completed > processing > pending > failed)
    3. Higher chunk count
    4. Older id (stable)
    """
    if not docs:
        raise ValueError("choose_keeper requires at least one document")
    return sorted(
        docs,
        key=lambda d: (
            0 if _is_linked(d) else 1,
            -_status_rank(d),
            -(int(getattr(d, "total_chunks", 0) or 0)),
            int(getattr(d, "id", 0) or 0),
        ),
    )[0]


def _doc_match_keys(doc: AIDocument) -> List[Tuple[str, str]]:
    keys: List[Tuple[str, str]] = []
    content_hash = (getattr(doc, "content_hash", None) or "").strip()
    if content_hash:
        keys.append(("hash", content_hash.lower()))
    else:
        source_url = normalize_dedupe_source_url(getattr(doc, "source_url", None))
        if source_url:
            keys.append(("url", source_url))
    return keys


def find_duplicate_groups(
    documents: Optional[Sequence[AIDocument]] = None,
) -> List[Dict[str, Any]]:
    """
    Return duplicate groups among AI documents.

    Each group dict:
      - group_id: stable string (e.g. ``hash:abc...`` or ``url:https://...``)
      - match_type: ``hash`` | ``url``
      - match_value: the shared key
      - keeper_id: preferred document id to keep
      - document_ids: all ids in the group (keeper first)
      - documents: lightweight dicts for API/UI
    """
    if documents is None:
        documents = (
            AIDocument.query.order_by(AIDocument.id.asc()).all()
        )

    buckets: Dict[Tuple[str, str], List[AIDocument]] = defaultdict(list)
    for doc in documents:
        for key in _doc_match_keys(doc):
            buckets[key].append(doc)

    groups: List[Dict[str, Any]] = []
    seen_group_members: set[frozenset[int]] = set()

    for (match_type, match_value), members in buckets.items():
        # Deduplicate member list (same doc shouldn't appear twice)
        by_id: Dict[int, AIDocument] = {}
        for doc in members:
            by_id[int(doc.id)] = doc
        unique = list(by_id.values())
        if len(unique) < 2:
            continue

        member_ids = frozenset(int(d.id) for d in unique)
        if member_ids in seen_group_members:
            continue
        seen_group_members.add(member_ids)

        keeper = choose_keeper(unique)
        ordered = [keeper] + [d for d in unique if int(d.id) != int(keeper.id)]
        group_id = f"{match_type}:{match_value}"
        groups.append(
            {
                "group_id": group_id,
                "match_type": match_type,
                "match_value": match_value,
                "keeper_id": int(keeper.id),
                "document_ids": [int(d.id) for d in ordered],
                "documents": [_lightweight_doc(d, keeper_id=int(keeper.id), match_type=match_type) for d in ordered],
            }
        )

    groups.sort(key=lambda g: (-len(g["document_ids"]), g["group_id"]))
    return groups


def _lightweight_doc(doc: AIDocument, *, keeper_id: int, match_type: str) -> Dict[str, Any]:
    return {
        "id": int(doc.id),
        "title": doc.title,
        "filename": doc.filename,
        "processing_status": doc.processing_status,
        "total_chunks": int(getattr(doc, "total_chunks", 0) or 0),
        "content_hash": getattr(doc, "content_hash", None),
        "source_url": getattr(doc, "source_url", None),
        "submitted_document_id": getattr(doc, "submitted_document_id", None),
        "guidance_document_id": getattr(doc, "guidance_document_id", None),
        "is_keeper": int(doc.id) == int(keeper_id),
        "match_type": match_type,
    }


def annotate_document_dicts(document_dicts: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Annotate API document dicts with duplicate fields for the Knowledge Base grid.

    Adds: ``duplicate_group_id``, ``duplicate_match``, ``is_duplicate``,
    ``duplicate_keeper_id``, ``is_duplicate_keeper``.
    """
    if not document_dicts:
        return list(document_dicts)

    class _Shim:
        __slots__ = (
            "id",
            "content_hash",
            "source_url",
            "submitted_document_id",
            "guidance_document_id",
            "processing_status",
            "total_chunks",
            "title",
            "filename",
        )

        def __init__(self, d: Dict[str, Any]):
            self.id = d.get("id")
            self.content_hash = d.get("content_hash")
            self.source_url = d.get("source_url")
            self.submitted_document_id = d.get("submitted_document_id")
            self.guidance_document_id = d.get("guidance_document_id")
            self.processing_status = d.get("processing_status")
            self.total_chunks = d.get("total_chunks") or 0
            self.title = d.get("title")
            self.filename = d.get("filename")

    shims = [_Shim(d) for d in document_dicts]
    groups = find_duplicate_groups(shims)  # type: ignore[arg-type]
    by_id: Dict[int, Dict[str, Any]] = {}
    for group in groups:
        for doc_id in group["document_ids"]:
            by_id[int(doc_id)] = {
                "duplicate_group_id": group["group_id"],
                "duplicate_match": group["match_type"],
                "is_duplicate": True,
                "duplicate_keeper_id": group["keeper_id"],
                "is_duplicate_keeper": int(doc_id) == int(group["keeper_id"]),
            }

    out: List[Dict[str, Any]] = []
    for d in document_dicts:
        row = dict(d)
        info = by_id.get(int(d["id"])) if d.get("id") is not None else None
        if info:
            row.update(info)
        else:
            row.setdefault("duplicate_group_id", None)
            row.setdefault("duplicate_match", None)
            row.setdefault("is_duplicate", False)
            row.setdefault("duplicate_keeper_id", None)
            row.setdefault("is_duplicate_keeper", False)
        out.append(row)
    return out


def _merge_loser_metadata_into_keeper(keeper: AIDocument, loser: AIDocument) -> None:
    """Copy useful provenance from a duplicate onto the keeper before delete."""
    if not keeper.content_hash and loser.content_hash:
        keeper.content_hash = loser.content_hash

    loser_url = (loser.source_url or "").strip()
    keeper_url = (keeper.source_url or "").strip()
    if loser_url:
        if not keeper_url:
            keeper.source_url = loser_url
        elif normalize_dedupe_source_url(keeper_url) != normalize_dedupe_source_url(loser_url):
            try:
                meta = dict(keeper.extra_metadata or {})
                alt_urls = list(meta.get("alt_source_urls") or [])
                if loser_url not in alt_urls and loser_url != keeper_url:
                    alt_urls.append(loser_url)
                meta["alt_source_urls"] = alt_urls
                keeper.extra_metadata = meta
            except Exception as e:
                logger.debug("Failed to merge alt_source_urls on keeper %s: %s", keeper.id, e)

    if not keeper.submitted_document_id and loser.submitted_document_id:
        # Only adopt if no other AIDocument already claims that submitted doc.
        conflict = (
            AIDocument.query.filter(
                AIDocument.submitted_document_id == loser.submitted_document_id,
                AIDocument.id != keeper.id,
                AIDocument.id != loser.id,
            )
            .first()
        )
        if not conflict:
            keeper.submitted_document_id = loser.submitted_document_id

    if not keeper.guidance_document_id and loser.guidance_document_id:
        conflict = (
            AIDocument.query.filter(
                AIDocument.guidance_document_id == loser.guidance_document_id,
                AIDocument.id != keeper.id,
                AIDocument.id != loser.id,
            )
            .first()
        )
        if not conflict:
            keeper.guidance_document_id = loser.guidance_document_id


def delete_ai_document_for_dedupe(doc: AIDocument) -> None:
    """
    Delete an AIDocument row and its AI-owned storage blob.

    Does not delete linked SubmittedDocument / GuidanceDocument storage.
    """
    storage_path = getattr(doc, "storage_path", None)
    linked_submitted = bool(getattr(doc, "submitted_document_id", None))
    if storage_path and not linked_submitted:
        try:
            from app.routes.ai_documents.helpers import _ai_doc_storage_delete

            _ai_doc_storage_delete(storage_path)
        except Exception as e:
            logger.warning("Failed to delete AI storage for doc %s during dedupe: %s", doc.id, e)

    db.session.delete(doc)


def find_reclaimable_ai_document(
    *,
    content_hash: Optional[str] = None,
    source_url: Optional[str] = None,
    exclude_submitted_document_id: Optional[int] = None,
) -> Optional[AIDocument]:
    """
    Find an existing AIDocument that can be reclaimed when linking a submitted doc.

    Prefer an unlinked row matching content_hash, then normalized source_url.
    Never reclaim a row already linked to a different submitted document.
    """
    hash_val = (content_hash or "").strip()
    url_val = normalize_dedupe_source_url(source_url)

    candidates: List[AIDocument] = []
    if hash_val:
        candidates = (
            AIDocument.query.filter(AIDocument.content_hash == hash_val)
            .order_by(AIDocument.id.asc())
            .all()
        )
    if not candidates and url_val:
        from sqlalchemy import or_

        raw_url = (source_url or "").strip()
        url_filters = [AIDocument.source_url == url_val]
        if raw_url and raw_url != url_val:
            url_filters.append(AIDocument.source_url == raw_url)
        candidates = (
            AIDocument.query.filter(or_(*url_filters))
            .order_by(AIDocument.id.asc())
            .all()
        )

    for doc in candidates:
        existing_sid = getattr(doc, "submitted_document_id", None)
        if existing_sid is None:
            return doc
        if exclude_submitted_document_id is not None and int(existing_sid) == int(
            exclude_submitted_document_id
        ):
            return doc
    return None


def dedupe_documents(
    *,
    all_groups: bool = False,
    document_ids: Optional[Iterable[int]] = None,
    keep_id: Optional[int] = None,
    remove_ids: Optional[Iterable[int]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Deduplicate AI documents.

    Modes:
    - ``all_groups=True``: dedupe every detected group (auto keeper).
    - ``document_ids=[...]``: dedupe only groups that intersect the given ids.
    - ``keep_id`` + ``remove_ids``: explicit keep/remove within one group.
    """
    removed: List[int] = []
    kept: List[int] = []
    groups_processed = 0

    if keep_id is not None and remove_ids is not None:
        remove_list = [int(x) for x in remove_ids]
        keeper = AIDocument.query.get(int(keep_id))
        if not keeper:
            return {
                "ok": False,
                "error": "Keeper document not found",
                "kept": [],
                "removed": [],
                "groups_processed": 0,
            }
        losers = (
            AIDocument.query.filter(AIDocument.id.in_(remove_list)).all() if remove_list else []
        )
        if not losers:
            return {
                "ok": True,
                "kept": [int(keeper.id)],
                "removed": [],
                "groups_processed": 0,
                "dry_run": dry_run,
            }
        if not dry_run:
            for loser in losers:
                if int(loser.id) == int(keeper.id):
                    continue
                _merge_loser_metadata_into_keeper(keeper, loser)
                delete_ai_document_for_dedupe(loser)
                removed.append(int(loser.id))
            db.session.commit()
        else:
            removed = [int(d.id) for d in losers if int(d.id) != int(keeper.id)]
        kept.append(int(keeper.id))
        groups_processed = 1 if removed else 0
        return {
            "ok": True,
            "kept": kept,
            "removed": removed,
            "groups_processed": groups_processed,
            "dry_run": dry_run,
        }

    groups = find_duplicate_groups()
    id_filter: Optional[set[int]] = None
    if document_ids is not None:
        id_filter = {int(x) for x in document_ids}
        groups = [
            g for g in groups if id_filter.intersection(int(i) for i in g["document_ids"])
        ]
    elif not all_groups:
        return {
            "ok": False,
            "error": "Specify all=true, document_ids, or keep_id/remove_ids",
            "kept": [],
            "removed": [],
            "groups_processed": 0,
        }

    for group in groups:
        keeper_id = int(group["keeper_id"])
        loser_ids = [int(i) for i in group["document_ids"] if int(i) != keeper_id]
        if id_filter is not None:
            # Only remove selected losers; if keeper wasn't selected, still keep it.
            loser_ids = [i for i in loser_ids if i in id_filter]
            if not loser_ids:
                continue
        keeper = AIDocument.query.get(keeper_id)
        if not keeper:
            continue
        losers = AIDocument.query.filter(AIDocument.id.in_(loser_ids)).all() if loser_ids else []
        if not losers:
            continue
        groups_processed += 1
        kept.append(keeper_id)
        if dry_run:
            removed.extend(int(d.id) for d in losers)
            continue
        for loser in losers:
            _merge_loser_metadata_into_keeper(keeper, loser)
            delete_ai_document_for_dedupe(loser)
            removed.append(int(loser.id))
        db.session.flush()

    if not dry_run and (removed or kept):
        db.session.commit()

    return {
        "ok": True,
        "kept": kept,
        "removed": removed,
        "groups_processed": groups_processed,
        "dry_run": dry_run,
    }
