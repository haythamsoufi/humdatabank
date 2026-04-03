"""
Shared AI chat request handling.

Centralizes parsing, validation, conversation resolution, and idempotency
for both HTTP (ai.py) and WebSocket (ai_ws.py) chat endpoints to avoid drift.
"""

from __future__ import annotations

import logging
import os
import uuid

logger = logging.getLogger(__name__)
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app

from app.extensions import db
from app.models.ai_chat import AIConversation, AIMessage
from app.utils.datetime_helpers import utcnow
from app.utils.ai_utils import detect_query_language, normalize_language_code, sanitize_page_context


MAX_CLIENT_MESSAGE_ID_CHARS = 64
# Cap user-provided history to avoid excessive payload/cost.
# (DB-backed history is already bounded by CHATBOT_MAX_HISTORY.)
MAX_CLIENT_CONVERSATION_HISTORY_ITEMS = 200


@dataclass
class ChatRequestParsed:
    """Parsed and validated chat request payload."""
    message: str
    page_context: Dict[str, Any]
    conversation_id: Optional[str]
    preferred_language: str
    conversation_history: List[Dict[str, Any]]
    client_message_id: Optional[str]
    branch_from_edit: bool
    sources_cfg: Optional[Dict[str, bool]] = None


def _ai_debug_enabled() -> bool:
    try:
        v = current_app.config.get("AI_CHAT_DEBUG_LOGS", None)
        if v is not None:
            return bool(v)
    except Exception as e:
        logger.debug("_ai_debug_enabled config check failed: %s", e)
    raw = (os.getenv("AI_CHAT_DEBUG_LOGS") or "").strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


def _parse_sources_cfg(raw: Any) -> Optional[Dict[str, bool]]:
    """
    Parse optional source selection, e.g.:
      - ['historical','system_documents','upr_documents'] (list/tuple/set)
      - {'historical': True, 'system_documents': True, 'upr_documents': False} (dict-like)
      - 'historical,system_documents' (comma-separated string)

    UI labels may refer to "databank" which maps to "historical".
    Returns a normalized dict with keys: historical, system_documents, upr_documents.
    If raw is None, returns None (meaning "no explicit selection" => use default behavior).
    """
    if raw is None:
        return None

    allowed = {"historical", "system_documents", "upr_documents"}
    alias = {
        "databank": "historical",
        "database": "historical",
        "indicator_bank": "historical",
        "system": "system_documents",
        "system_docs": "system_documents",
        "upr": "upr_documents",
        "upr_docs": "upr_documents",
    }

    out: Dict[str, bool] = {"historical": False, "system_documents": False, "upr_documents": False}

    def _norm_key(k: Any) -> Optional[str]:
        try:
            s = str(k or "").strip().lower()
        except Exception as e:
            logger.debug("_norm_key failed for %r: %s", k, e)
            return None
        if not s:
            return None
        s = alias.get(s, s)
        return s if s in allowed else None

    selected_any = False

    if isinstance(raw, str):
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        for p in parts:
            k = _norm_key(p)
            if not k:
                continue
            out[k] = True
            selected_any = True
    elif isinstance(raw, (list, tuple, set)):
        for v in raw:
            k = _norm_key(v)
            if not k:
                continue
            out[k] = True
            selected_any = True
    elif isinstance(raw, dict):
        for k_raw, v in raw.items():
            k = _norm_key(k_raw)
            if not k:
                continue
            try:
                enabled = bool(v)
            except Exception as e:
                logger.debug("Could not coerce sources_cfg value to bool: %s", e)
                enabled = False
            out[k] = enabled
            selected_any = selected_any or enabled
    else:
        # Unknown shape: ignore
        return None

    # Guardrail: if the client sent an empty/invalid selection, preserve current behavior (all sources).
    if not selected_any:
        out["historical"] = True
        out["system_documents"] = True
        out["upr_documents"] = True

    return out


def load_conversation_history_for_llm(conversation_id: str, user_id: int) -> List[Dict[str, Any]]:
    """
    Load recent conversation messages from DB for LLM context.
    Returns list of {"isUser": bool, "message": str} for user/assistant turns.
    """
    try:
        max_hist = int(current_app.config.get("CHATBOT_MAX_HISTORY", 10))
    except Exception as e:
        logger.debug("CHATBOT_MAX_HISTORY config invalid, using default: %s", e)
        max_hist = 10
    try:
        q = (
            AIMessage.query.filter_by(conversation_id=conversation_id, user_id=user_id)
            .order_by(AIMessage.created_at.desc())
            .limit(max_hist * 2)
            .all()
        )
        q = list(reversed(q))
        return [
            {"isUser": (m.role == "user"), "message": (m.content or "")}
            for m in q
            if m.role in ("user", "assistant") and (m.content or "").strip()
        ]
    except Exception as e_hist:
        current_app.logger.debug("AI chat: failed to load conversation history: %s", e_hist, exc_info=True)
        return []


def replace_conversation_messages(
    *,
    conversation_id: str,
    user_id: int,
    history: List[Dict[str, Any]],
) -> None:
    """
    Replace all messages in a conversation with the given history (edit branch).
    history: list of {"isUser": bool, "message": str}. Persisted as user/assistant AIMessage rows.
    """
    if not history or not isinstance(history, list):
        return
    try:
        # Ensure parent conversation exists first (FK safety).
        convo = AIConversation.query.filter_by(id=conversation_id, user_id=user_id).first()
        if not convo:
            # Best-effort title based on first user message in provided history.
            title_hint = None
            for entry in history:
                if isinstance(entry, dict) and entry.get("isUser"):
                    msg = (entry.get("message") or "").strip()
                    if msg:
                        title_hint = msg
                        break
            if not title_hint:
                title_hint = "Conversation"
            title = (title_hint[:80] + "…") if len(title_hint) > 80 else title_hint
            convo = AIConversation(
                id=conversation_id,
                user_id=user_id,
                title=title,
                created_at=utcnow(),
                updated_at=utcnow(),
                last_message_at=utcnow(),
                meta={"client": "unknown", "source": "branch_from_edit"},
            )
            db.session.add(convo)
            # Flush so inserts into ai_message cannot race FK constraints.
            db.session.flush()
        else:
            convo.updated_at = utcnow()

        # Replace messages (this effectively truncates any "later" messages after an edit).
        AIMessage.query.filter_by(
            conversation_id=conversation_id,
            user_id=user_id,
        ).delete(synchronize_session=False)

        inserted_any = False
        for entry in history:
            if not isinstance(entry, dict):
                continue
            role = "user" if entry.get("isUser") else "assistant"
            content = (entry.get("message") or "").strip()
            if not content:
                continue
            inserted_any = True
            db.session.add(
                AIMessage(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    role=role,
                    content=content,
                    client_message_id=None,
                    meta=None,
                )
            )

        if inserted_any:
            convo.last_message_at = utcnow()
        convo.updated_at = utcnow()

        db.session.commit()
    except Exception as e:
        logger.debug("replace_conversation_messages failed: %s", e, exc_info=True)
        with db.session.no_autoflush:
            db.session.rollback()
        raise


def find_existing_reply_for_client_message_id(
    *,
    conversation_id: str,
    user_id: int,
    client_message_id: str,
) -> Optional[Tuple[str, int, int]]:
    """
    Best-effort idempotency: if the same client_message_id was already answered,
    return (reply_text, user_msg_id, assistant_msg_id). Otherwise None.
    """
    try:
        user_msg = (
            AIMessage.query.filter_by(
                conversation_id=conversation_id,
                user_id=user_id,
                client_message_id=client_message_id,
                role="user",
            )
            .order_by(AIMessage.id.asc())
            .first()
        )
        if not user_msg:
            return None

        assistant_msg = (
            AIMessage.query.filter(
                AIMessage.conversation_id == conversation_id,
                AIMessage.user_id == user_id,
                AIMessage.role == "assistant",
                AIMessage.id > user_msg.id,
            )
            .order_by(AIMessage.id.asc())
            .first()
        )
        if assistant_msg and (assistant_msg.content or "").strip():
            return (assistant_msg.content, int(user_msg.id), int(assistant_msg.id))
        return None
    except Exception as e:
        logger.debug("_last_assistant_message failed: %s", e, exc_info=True)
        return None


def parse_chat_request(
    data: Dict[str, Any],
    *,
    max_message_chars: Optional[int] = None,
) -> Tuple[Optional[ChatRequestParsed], Optional[str], int]:
    """
    Parse and validate chat request payload.

    Returns:
        (parsed, error_message, status_code). If error_message is set, parsed is None.
    """
    if max_message_chars is None:
        try:
            max_message_chars = int(current_app.config.get("AI_MAX_MESSAGE_CHARS", 4000))
        except Exception as e:
            logger.debug("AI_MAX_MESSAGE_CHARS config invalid, using default: %s", e)
            max_message_chars = 4000

    message = (data.get("message") or "").strip()
    if not message:
        return None, "Message is required", 400
    if len(message) > max_message_chars:
        return None, "Message too long", 413

    page_context = sanitize_page_context(data.get("page_context") or {})

    conversation_id = data.get("conversation_id")
    if isinstance(conversation_id, str):
        conversation_id = conversation_id.strip() or None
        if conversation_id:
            if len(conversation_id) > 64:
                conversation_id = None
            else:
                try:
                    uuid.UUID(conversation_id)
                except Exception as e:
                    logger.debug("Invalid conversation_id UUID format: %s", e)
                    conversation_id = None
    else:
        conversation_id = None

    # Client/UI language (may be different from the message language)
    preferred_language_raw = (data.get("preferred_language") or "en")
    # AI/chat supported languages (kept consistent with chatbot prompt language support)
    allowed_langs = {"en", "fr", "es", "ar", "ru", "zh", "hi"}
    ui_language = normalize_language_code(preferred_language_raw, default="en", allowed=allowed_langs)

    # Detect language from the user's query and use it for the LLM response language.
    # This ensures: if UI is Arabic but the user asks in English, the LLM answers in English.
    detected_lang, confidence = detect_query_language(message, allowed=allowed_langs)
    preferred_language = detected_lang if confidence >= 0.20 else ui_language

    conversation_history = data.get("conversationHistory") or []
    if not isinstance(conversation_history, list):
        conversation_history = []
    if len(conversation_history) > MAX_CLIENT_CONVERSATION_HISTORY_ITEMS:
        # Keep the most recent items (the client typically sends oldest->newest).
        conversation_history = conversation_history[-MAX_CLIENT_CONVERSATION_HISTORY_ITEMS:]

    client_message_id = data.get("client_message_id")
    if isinstance(client_message_id, str):
        client_message_id = client_message_id.strip() or None
        if client_message_id:
            client_message_id = client_message_id[:MAX_CLIENT_MESSAGE_ID_CHARS]
    else:
        client_message_id = None

    branch_from_edit = bool(data.get("branch_from_edit"))

    sources_cfg = _parse_sources_cfg(data.get("sources"))

    parsed = ChatRequestParsed(
        message=message,
        page_context=page_context,
        conversation_id=conversation_id,
        preferred_language=preferred_language,
        conversation_history=conversation_history,
        client_message_id=client_message_id,
        branch_from_edit=branch_from_edit,
        sources_cfg=sources_cfg,
    )
    return parsed, None, 0


def resolve_conversation_and_history(
    identity: Any,
    parsed: ChatRequestParsed,
) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """
    Apply persistence rules: resolve conversation_id and conversation_history
    for the given identity (authenticated vs anonymous).

    Returns (conversation_id, conversation_history) to use for the LLM.
    For anonymous users, conversation_id is None and history is cleared.
    """
    if not getattr(identity, "is_authenticated", False) or not getattr(identity, "user", None):
        return None, []

    user_id = int(identity.user.id)
    conversation_id = parsed.conversation_id
    if not conversation_id:
        conversation_id = str(uuid.uuid4())

    history = parsed.conversation_history
    if _ai_debug_enabled():
        try:
            current_app.logger.debug(
                "AI chat resolve_conversation_and_history user_id=%s conv_id=%s branch_from_edit=%s client_history_items=%s client_message_id=%s",
                user_id,
                conversation_id,
                bool(parsed.branch_from_edit),
                len(history or []),
                parsed.client_message_id,
            )
        except Exception as e:
            logger.debug("resolve_conversation_and_history debug log failed: %s", e)
    if parsed.branch_from_edit and conversation_id and history:
        try:
            replace_conversation_messages(
                conversation_id=conversation_id,
                user_id=user_id,
                history=history,
            )
        except Exception as e_replace:
            current_app.logger.debug(
                "AI chat: failed to replace conversation on edit branch: %s", e_replace, exc_info=True
            )
            history = []
    elif conversation_id:
        history = load_conversation_history_for_llm(conversation_id, user_id)
        if _ai_debug_enabled():
            try:
                current_app.logger.debug(
                    "AI chat loaded DB history user_id=%s conv_id=%s db_items=%s",
                    user_id,
                    conversation_id,
                    len(history or []),
                )
            except Exception as e:
                logger.debug("resolve_conversation_and_history history debug log failed: %s", e)

    return conversation_id, history


def get_idempotent_reply(
    identity: Any,
    conversation_id: Optional[str],
    client_message_id: Optional[str],
) -> Optional[Tuple[str, int, int]]:
    """
    If the client resubmitted with the same client_message_id, return the
    existing assistant reply. Otherwise return None.
    """
    if not getattr(identity, "is_authenticated", False) or not getattr(identity, "user", None):
        return None
    if not conversation_id or not client_message_id:
        return None
    return find_existing_reply_for_client_message_id(
        conversation_id=conversation_id,
        user_id=int(identity.user.id),
        client_message_id=client_message_id,
    )


def apply_anonymous_rules(parsed: ChatRequestParsed) -> ChatRequestParsed:
    """For anonymous users: clear conversation_id and persistence fields; keep client conversation_history for LLM context."""
    return ChatRequestParsed(
        message=parsed.message,
        page_context=parsed.page_context,
        conversation_id=None,
        preferred_language=parsed.preferred_language,
        conversation_history=parsed.conversation_history,
        client_message_id=None,
        branch_from_edit=False,
        sources_cfg=getattr(parsed, "sources_cfg", None),
    )
