from __future__ import annotations

import gzip
import hashlib
import logging
import io
import json
import os

logger = logging.getLogger(__name__)
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app
from sqlalchemy import func

from app.extensions import db
from app.models.ai_chat import AIConversation, AIMessage
from app.utils.datetime_helpers import utcnow


@dataclass
class MaintenanceStats:
    archived_conversations: int = 0
    purged_conversations: int = 0
    deleted_archive_objects: int = 0
    errors: int = 0


def _effective_last_activity_expr():
    return func.coalesce(AIConversation.last_message_at, AIConversation.updated_at, AIConversation.created_at)


def _effective_last_activity(convo: AIConversation):
    return convo.last_message_at or convo.updated_at or convo.created_at


def _archive_provider() -> str:
    return (current_app.config.get("AI_CHAT_ARCHIVE_PROVIDER") or "filesystem").strip().lower()


def _archive_dir() -> str:
    return (current_app.config.get("AI_CHAT_ARCHIVE_DIR") or "ai_chat_archives").strip() or "ai_chat_archives"


def _encryption_key() -> Optional[str]:
    # Optional; only used if cryptography is available.
    key = current_app.config.get("AI_CHAT_ARCHIVE_ENCRYPTION_KEY")
    return (key.strip() if isinstance(key, str) else None) or None


def _compress_json_bytes(payload: Dict[str, Any]) -> bytes:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        gz.write(raw)
    return buf.getvalue()


def _maybe_encrypt(data: bytes) -> Tuple[bytes, Dict[str, Any]]:
    """
    Best-effort encryption using Fernet if available and AI_CHAT_ARCHIVE_ENCRYPTION_KEY is set.
    Returns (bytes_to_store, archive_meta).
    """
    key = _encryption_key()
    if not key:
        return data, {"encrypted": False, "encryption": None}
    try:
        from cryptography.fernet import Fernet  # type: ignore

        f = Fernet(key.encode("utf-8"))
        return f.encrypt(data), {"encrypted": True, "encryption": "fernet"}
    except Exception as e:
        current_app.logger.warning(f"AI chat archive encryption not available; storing unencrypted. Reason: {e}")
        return data, {"encrypted": False, "encryption": None}


def _maybe_decrypt(data: bytes, meta: Dict[str, Any]) -> bytes:
    if not meta or not meta.get("encrypted"):
        return data
    if meta.get("encryption") != "fernet":
        raise ValueError("Unsupported archive encryption")
    key = _encryption_key()
    if not key:
        raise ValueError("Archive is encrypted but AI_CHAT_ARCHIVE_ENCRYPTION_KEY is not configured")
    from cryptography.fernet import Fernet  # type: ignore

    f = Fernet(key.encode("utf-8"))
    return f.decrypt(data)


def _write_filesystem_archive(*, rel_path: str, data: bytes) -> None:
    upload_base = (current_app.config.get("UPLOAD_FOLDER") or "").strip()
    if not upload_base:
        upload_base = os.path.join(current_app.instance_path, "uploads")
    full_path = os.path.join(upload_base, rel_path)
    full_dir = os.path.dirname(full_path)
    os.makedirs(full_dir, exist_ok=True)
    with open(full_path, "wb") as f:
        f.write(data)


def _read_filesystem_archive(*, rel_path: str) -> bytes:
    upload_base = (current_app.config.get("UPLOAD_FOLDER") or "").strip()
    if not upload_base:
        upload_base = os.path.join(current_app.instance_path, "uploads")
    full_path = os.path.join(upload_base, rel_path)
    with open(full_path, "rb") as f:
        return f.read()


def _delete_filesystem_archive(*, rel_path: str) -> bool:
    try:
        upload_base = (current_app.config.get("UPLOAD_FOLDER") or "").strip()
        if not upload_base:
            upload_base = os.path.join(current_app.instance_path, "uploads")
        full_path = os.path.join(upload_base, rel_path)
        if os.path.exists(full_path) and os.path.isfile(full_path):
            os.remove(full_path)
            return True
        return False
    except Exception as e:
        logger.debug("Local file delete failed: %s", e)
        return False


def _azure_blob_client():
    conn = current_app.config.get("AI_CHAT_ARCHIVE_AZURE_CONNECTION_STRING")
    container = current_app.config.get("AI_CHAT_ARCHIVE_AZURE_CONTAINER") or "ai-chat-archives"
    if not conn:
        raise RuntimeError("AI_CHAT_ARCHIVE_AZURE_CONNECTION_STRING is required for azure_blob provider")
    try:
        from azure.storage.blob import BlobServiceClient  # type: ignore

        svc = BlobServiceClient.from_connection_string(conn)
        return svc.get_container_client(container)
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Azure Blob client: {e}") from e


def _write_azure_blob_archive(*, blob_name: str, data: bytes) -> None:
    container = _azure_blob_client()
    container.upload_blob(name=blob_name, data=data, overwrite=True)


def _read_azure_blob_archive(*, blob_name: str) -> bytes:
    container = _azure_blob_client()
    blob = container.get_blob_client(blob_name)
    return blob.download_blob().readall()


def _delete_azure_blob_archive(*, blob_name: str) -> bool:
    try:
        container = _azure_blob_client()
        blob = container.get_blob_client(blob_name)
        blob.delete_blob()
        return True
    except Exception as e:
        logger.debug("Azure blob delete failed: %s", e)
        return False


def _build_archive_payload(convo: AIConversation, messages: List[AIMessage]) -> Dict[str, Any]:
    return {
        "conversation": {
            "id": convo.id,
            "user_id": int(convo.user_id),
            "title": convo.title,
            "created_at": convo.created_at.isoformat() if convo.created_at else None,
            "updated_at": convo.updated_at.isoformat() if convo.updated_at else None,
            "last_message_at": convo.last_message_at.isoformat() if convo.last_message_at else None,
            "meta": convo.meta or None,
        },
        "messages": [
            {
                "id": int(m.id) if m.id is not None else None,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "client_message_id": m.client_message_id,
                "meta": m.meta or None,
            }
            for m in messages
        ],
        "format_version": 1,
        "archived_at": utcnow().isoformat(),
    }


def archive_conversation(*, conversation_id: str, user_id: int, dry_run: bool = False) -> Optional[AIConversation]:
    convo = AIConversation.query.filter_by(id=conversation_id, user_id=user_id).first()
    if not convo:
        return None
    if convo.is_archived:
        return convo

    messages = (
        AIMessage.query.filter_by(conversation_id=conversation_id, user_id=user_id)
        .order_by(AIMessage.created_at.asc())
        .all()
    )
    if not messages:
        # No messages; mark as archived without writing anything
        if not dry_run:
            convo.is_archived = True
            convo.archived_at = utcnow()
            convo.archive_provider = _archive_provider()
            convo.archive_path = None
            db.session.commit()
        return convo

    payload = _build_archive_payload(convo, messages)
    compressed = _compress_json_bytes(payload)
    stored_bytes, crypto_meta = _maybe_encrypt(compressed)

    sha256 = hashlib.sha256(stored_bytes).hexdigest()
    size_bytes = len(stored_bytes)
    provider = _archive_provider()

    # Path/name
    ts = utcnow().strftime("%Y%m%dT%H%M%SZ")
    if provider == "filesystem":
        rel = os.path.join(_archive_dir(), str(user_id), f"{conversation_id}-{ts}.json.gz")
        if dry_run:
            return convo
        _write_filesystem_archive(rel_path=rel, data=stored_bytes)
        convo.archive_provider = "filesystem"
        convo.archive_path = rel.replace("\\", "/")
    elif provider == "azure_blob":
        base = _archive_dir().strip("/").strip()
        blob_name = f"{base}/{user_id}/{conversation_id}-{ts}.json.gz".replace("\\", "/")
        if dry_run:
            return convo
        _write_azure_blob_archive(blob_name=blob_name, data=stored_bytes)
        convo.archive_provider = "azure_blob"
        convo.archive_path = blob_name
    else:
        raise ValueError(f"Unsupported AI_CHAT_ARCHIVE_PROVIDER: {provider}")

    if not dry_run:
        # Record archive metadata
        convo.is_archived = True
        convo.archived_at = utcnow()
        convo.archive_size_bytes = int(size_bytes)
        convo.archive_sha256 = sha256
        meta = convo.meta or {}
        meta["archive"] = {
            "compression": "gzip",
            **crypto_meta,
        }
        convo.meta = meta

        # Delete messages after successful archive
        AIMessage.query.filter_by(conversation_id=conversation_id, user_id=user_id).delete(synchronize_session=False)
        db.session.commit()

    return convo


def _load_archive_bytes(convo: AIConversation) -> bytes:
    if not convo.archive_provider or not convo.archive_path:
        raise FileNotFoundError("Conversation has no archive reference")
    provider = (convo.archive_provider or "").strip().lower()
    if provider == "filesystem":
        return _read_filesystem_archive(rel_path=convo.archive_path)
    if provider == "azure_blob":
        return _read_azure_blob_archive(blob_name=convo.archive_path)
    raise ValueError(f"Unsupported archive provider: {provider}")


def load_archived_conversation(convo: AIConversation) -> Dict[str, Any]:
    raw = _load_archive_bytes(convo)
    if convo.archive_sha256:
        sha = hashlib.sha256(raw).hexdigest()
        if sha != convo.archive_sha256:
            raise ValueError("Archive checksum mismatch")

    meta = (convo.meta or {}).get("archive") or {}
    decrypted = _maybe_decrypt(raw, meta)
    with gzip.GzipFile(fileobj=io.BytesIO(decrypted), mode="rb") as gz:
        decoded = gz.read()
    payload = json.loads(decoded.decode("utf-8"))
    return payload


def delete_archive_object(convo: AIConversation) -> bool:
    if not convo.archive_provider or not convo.archive_path:
        return False
    provider = (convo.archive_provider or "").strip().lower()
    if provider == "filesystem":
        return _delete_filesystem_archive(rel_path=convo.archive_path)
    if provider == "azure_blob":
        return _delete_azure_blob_archive(blob_name=convo.archive_path)
    return False


def purge_conversation(*, conversation_id: str, user_id: int, dry_run: bool = False) -> bool:
    convo = AIConversation.query.filter_by(id=conversation_id, user_id=user_id).first()
    if not convo:
        return False
    if not dry_run:
        # best-effort delete archive object first
        delete_archive_object(convo)
        AIMessage.query.filter_by(conversation_id=conversation_id, user_id=user_id).delete(synchronize_session=False)
        db.session.delete(convo)
        db.session.commit()
    return True


def maintain_ai_chat_retention(
    *,
    archive_after_days: Optional[int] = None,
    purge_after_days: Optional[int] = None,
    batch_size: Optional[int] = None,
    dry_run: bool = False,
    user_id: Optional[int] = None,
) -> MaintenanceStats:
    stats = MaintenanceStats()
    if not current_app.config.get("AI_CHAT_RETENTION_ENABLED", True):
        return stats

    archive_days = int(archive_after_days if archive_after_days is not None else current_app.config.get("AI_CHAT_ARCHIVE_AFTER_DAYS", 90))
    purge_days = int(purge_after_days if purge_after_days is not None else current_app.config.get("AI_CHAT_PURGE_AFTER_DAYS", 365))
    batch = int(batch_size if batch_size is not None else current_app.config.get("AI_CHAT_MAINTENANCE_BATCH_SIZE", 200))

    now = utcnow()
    archive_cutoff = now - timedelta(days=max(0, archive_days))
    purge_cutoff = now - timedelta(days=max(0, purge_days))

    # 1) Purge oldest conversations (and their archives)
    try:
        purge_q = AIConversation.query.filter(_effective_last_activity_expr() < purge_cutoff)
        if user_id is not None:
            purge_q = purge_q.filter(AIConversation.user_id == int(user_id))
        purge_list = purge_q.order_by(_effective_last_activity_expr().asc()).limit(batch).all()
        for c in purge_list:
            if dry_run:
                stats.purged_conversations += 1
                continue
            try:
                if delete_archive_object(c):
                    stats.deleted_archive_objects += 1
            except Exception as e:
                # Deleting an archive object should not block retention, but we must surface failures.
                stats.errors += 1
                current_app.logger.warning(
                    "AI chat retention: failed deleting archive object for conversation %s (user_id=%s): %s",
                    getattr(c, "id", None),
                    getattr(c, "user_id", None),
                    e,
                    exc_info=True,
                )
            AIMessage.query.filter_by(conversation_id=c.id, user_id=c.user_id).delete(synchronize_session=False)
            db.session.delete(c)
            stats.purged_conversations += 1
        if not dry_run and purge_list:
            db.session.commit()
    except Exception as e:
        stats.errors += 1
        current_app.logger.error(f"AI chat purge job failed: {e}", exc_info=True)
        if not dry_run:
            db.session.rollback()

    # 2) Archive conversations older than archive_cutoff (but not yet archived)
    try:
        archive_q = AIConversation.query.filter(AIConversation.is_archived.is_(False), _effective_last_activity_expr() < archive_cutoff)
        if user_id is not None:
            archive_q = archive_q.filter(AIConversation.user_id == int(user_id))
        archive_list = archive_q.order_by(_effective_last_activity_expr().asc()).limit(batch).all()
        for c in archive_list:
            try:
                archived = archive_conversation(conversation_id=c.id, user_id=int(c.user_id), dry_run=dry_run)
                if archived:
                    stats.archived_conversations += 1
            except Exception as e:
                stats.errors += 1
                current_app.logger.error(f"AI chat archive failed for conversation {c.id}: {e}", exc_info=True)
                if not dry_run:
                    db.session.rollback()
    except Exception as e:
        stats.errors += 1
        current_app.logger.error(f"AI chat archive job failed: {e}", exc_info=True)

    return stats
