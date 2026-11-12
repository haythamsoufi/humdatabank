"""
Programmatic multi-turn chat runner for local debugging.

Used by ``flask ai-chat`` so developers can send the same prompts the UI would,
with the same agent path, and inspect tools / failures / digests / traces without
browser automation.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from html import unescape
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")
_PRESET_EMAILS = {
    "admin": "test_admin",
    "sys": "test_sys",
    "sys_manager": "test_sys",
    "focal": "test_focal",
}


@dataclass
class TurnResult:
    index: int
    prompt: str
    answer_text: str
    success: bool
    provider: Optional[str] = None
    model: Optional[str] = None
    trace_id: Optional[int] = None
    tools_used: List[str] = field(default_factory=list)
    failed_tools: List[Dict[str, Any]] = field(default_factory=list)
    tool_digest: str = ""
    grounding_score: Optional[float] = None
    confidence: Optional[str] = None
    llm_quality_score: Optional[float] = None
    llm_quality_verdict: Optional[str] = None
    has_chart: bool = False
    has_map: bool = False
    has_table: bool = False
    error: Optional[str] = None
    elapsed_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConversationResult:
    conversation_id: str
    user_email: str
    turns: List[TurnResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "user_email": self.user_email,
            "turns": [t.to_dict() for t in self.turns],
        }


def html_to_text(html: str) -> str:
    """Best-effort strip of chat HTML for terminal display."""
    if not html:
        return ""
    text = _TAG_RE.sub(" ", html)
    text = unescape(text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +\n", "\n", text)
    text = re.sub(r" +([.,;:!?])", r"\1", text)
    return text.strip()


def resolve_debug_user(user_spec: Optional[str] = None):
    """Resolve a User for CLI debugging.

    ``user_spec`` may be:
      - a full email
      - a preset: admin | sys | sys_manager | focal
      - a local-part (matched as ``local@%``)
      - None → prefer test_admin, then any admin, then first active user
    """
    from app.models import User
    from app.services.organization.authorization_service import AuthorizationService
    from sqlalchemy import func

    spec = (user_spec or "").strip()
    if spec:
        key = spec.lower()
        if key in _PRESET_EMAILS:
            prefix = _PRESET_EMAILS[key]
            user = User.query.filter(func.lower(User.email).like(f"{prefix}@%")).first()
            if user:
                return user
            raise LookupError(f"No seeded user matching preset '{spec}' ({prefix}@…). Run: flask seed-test-data")
        if "@" in spec:
            user = User.query.filter(func.lower(User.email) == key).first()
        else:
            user = User.query.filter(func.lower(User.email).like(f"{key}@%")).first()
        if not user:
            raise LookupError(f"No user found for '{spec}'")
        return user

    for prefix in ("test_admin", "test_sys", "test_focal"):
        user = User.query.filter(func.lower(User.email).like(f"{prefix}@%")).first()
        if user:
            return user
    for u in User.query.filter_by(is_active=True).order_by(User.id.asc()).limit(50):
        if AuthorizationService.is_admin(u) or AuthorizationService.is_system_manager(u):
            return u
    user = User.query.filter_by(is_active=True).order_by(User.id.asc()).first()
    if not user:
        raise LookupError("No active users in the database. Run: flask seed-test-data")
    return user


def load_scenario(path: str) -> List[str]:
    """Load prompts from a JSON file.

    Accepted shapes:
      - ["prompt1", "prompt2"]
      - {"prompts": [...]} / {"turns": [{"message": "..."}, ...]}
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        prompts = [str(x).strip() for x in data if str(x).strip()]
    elif isinstance(data, dict):
        if isinstance(data.get("prompts"), list):
            prompts = [str(x).strip() for x in data["prompts"] if str(x).strip()]
        elif isinstance(data.get("turns"), list):
            prompts = []
            for t in data["turns"]:
                if isinstance(t, str) and t.strip():
                    prompts.append(t.strip())
                elif isinstance(t, dict):
                    msg = (t.get("message") or t.get("prompt") or t.get("query") or "").strip()
                    if msg:
                        prompts.append(msg)
        else:
            raise ValueError("Scenario JSON must have 'prompts' or 'turns'")
    else:
        raise ValueError("Scenario must be a JSON list or object")
    if not prompts:
        raise ValueError("Scenario contains no prompts")
    return prompts


def summarize_trace_steps(steps: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Compact tool summary from a stored reasoning-trace steps list."""
    from app.services.ai.runtime.turn_digest import build_turn_digest

    tools: List[str] = []
    failed: List[Dict[str, Any]] = []
    for step in steps or []:
        action = str((step or {}).get("action") or "").strip()
        if not action or action in {"finish", "evidence_plan_defer", "verify_answer"}:
            continue
        tools.append(action)
        obs = (step or {}).get("observation")
        if isinstance(obs, dict) and (obs.get("success") is False or obs.get("error")):
            failed.append({
                "tool": action,
                "error_type": obs.get("error_type"),
                "error_cause_type": obs.get("error_cause_type"),
                "error": (obs.get("error") or "")[:200],
            })
    return {
        "tools_used": tools,
        "failed_tools": failed,
        "tool_digest": build_turn_digest(steps),
    }


class ChatDebugRunner:
    """Run one or more chat turns under a real Flask request + logged-in user."""

    def __init__(
        self,
        *,
        user=None,
        user_spec: Optional[str] = None,
        language: str = "en",
        page_context: Optional[Dict[str, Any]] = None,
        enable_agent: bool = True,
        conversation_id: Optional[str] = None,
        on_step: Optional[Callable[[str], None]] = None,
    ):
        resolved = user or resolve_debug_user(user_spec)
        self.user_id = int(resolved.id)
        self.user_email = getattr(resolved, "email", "") or ""
        self.language = language or "en"
        self.page_context = page_context or {}
        self.enable_agent = enable_agent
        self.conversation_id = conversation_id or str(uuid.uuid4())
        self.on_step = on_step
        self.history: List[Dict[str, Any]] = []
        self._ensure_conversation()

    @property
    def user(self):
        """Fresh bound User for the current session (avoids DetachedInstanceError)."""
        from app.models import User
        from app.extensions import db

        u = db.session.get(User, self.user_id)
        if u is None:
            raise LookupError(f"User id={self.user_id} no longer exists")
        return u

    def _ensure_conversation(self) -> None:
        """Create the AIConversation row so reasoning traces can FK to it."""
        from app.models.ai_chat import AIConversation
        from app.extensions import db
        from app.utils.common.datetime_helpers import utcnow

        existing = AIConversation.query.filter_by(
            id=self.conversation_id, user_id=self.user_id
        ).first()
        if existing:
            return
        db.session.add(
            AIConversation(
                id=self.conversation_id,
                user_id=self.user_id,
                title="CLI debug conversation",
                created_at=utcnow(),
                updated_at=utcnow(),
                last_message_at=utcnow(),
                meta={"client": "cli", "source": "ai-chat-debug"},
            )
        )
        db.session.commit()

    def _platform_context(self) -> Dict[str, Any]:
        from app.utils.ai.ai_request_user import AIRequestIdentity
        from app.services.organization.authorization_service import AuthorizationService
        from app.routes.ai import _build_access_context, _build_platform_context

        user = self.user
        if AuthorizationService.is_system_manager(user):
            level = "system_manager"
        elif AuthorizationService.is_admin(user):
            level = "admin"
        else:
            level = "user"
        identity = AIRequestIdentity(
            is_authenticated=True,
            access_level=level,
            user=user,
            auth_source="cli",
        )
        access = _build_access_context(identity)
        ctx = _build_platform_context(identity, access)
        ctx["conversation_id"] = self.conversation_id
        return ctx

    def run_turn(self, prompt: str) -> TurnResult:
        import time
        from flask import has_request_context, current_app
        from flask_login import login_user
        from app.services.ai.chat.engine import AIChatEngine
        from app.extensions import db

        prompt = (prompt or "").strip()
        if not prompt:
            raise ValueError("Empty prompt")

        started = time.time()
        idx = len(self.history) // 2 + 1

        def _execute() -> TurnResult:
            try:
                db.session.rollback()  # clear any leftover aborted transaction
            except Exception:
                pass
            login_user(self.user, remember=False)
            engine = AIChatEngine()
            result = engine.run(
                message=prompt,
                platform_context=self._platform_context(),
                page_context=self.page_context,
                preferred_language=self.language,
                conversation_history=list(self.history),
                enable_agent=self.enable_agent,
                on_step=self.on_step,
            )
            answer_text = html_to_text(result.response_html or "")
            tools = list(result.function_calls_used or [])
            failed: List[Dict[str, Any]] = []
            digest = ""
            quality_score = None
            quality_verdict = None
            if result.trace_id:
                try:
                    from app.models.embeddings import AIReasoningTrace
                    from app.extensions import db

                    trace = db.session.get(AIReasoningTrace, int(result.trace_id))
                    if trace is not None:
                        summary = summarize_trace_steps(trace.steps if isinstance(trace.steps, list) else [])
                        tools = summary["tools_used"] or tools
                        failed = summary["failed_tools"]
                        digest = summary["tool_digest"]
                        quality_score = getattr(trace, "llm_quality_score", None)
                        quality_verdict = getattr(trace, "llm_quality_verdict", None)
                except Exception as exc:
                    logger.debug("trace enrich failed: %s", exc)

            # Update in-memory history the same way the UI does (text only), then
            # attach the digest so the *next* turn sees tool outcomes — mirrors
            # load_conversation_history_for_llm + attach_turn_digests.
            self.history.append({"isUser": True, "message": prompt})
            assistant_entry: Dict[str, Any] = {"isUser": False, "message": answer_text}
            if digest:
                assistant_entry["tool_digest"] = digest
            self.history.append(assistant_entry)

            return TurnResult(
                index=idx,
                prompt=prompt,
                answer_text=answer_text,
                success=bool(result.success),
                provider=result.provider,
                model=result.model,
                trace_id=result.trace_id,
                tools_used=tools,
                failed_tools=failed,
                tool_digest=digest,
                grounding_score=result.grounding_score,
                confidence=result.confidence,
                llm_quality_score=quality_score,
                llm_quality_verdict=quality_verdict,
                has_chart=bool(result.chart_payload),
                has_map=bool(result.map_payload),
                has_table=bool(result.table_payload),
                error=result.error_message,
                elapsed_ms=round((time.time() - started) * 1000, 1),
            )

        # Prefer a real request context so Flask-Login + g-scoped helpers work.
        if has_request_context():
            return _execute()
        with current_app.test_request_context("/ai-chat-cli"):
            return _execute()

    def run_prompts(self, prompts: List[str]) -> ConversationResult:
        out = ConversationResult(
            conversation_id=self.conversation_id,
            user_email=self.user_email,
        )
        for prompt in prompts:
            out.turns.append(self.run_turn(prompt))
        return out
