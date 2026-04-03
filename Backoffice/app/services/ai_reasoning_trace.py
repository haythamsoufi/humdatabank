"""
AI Reasoning Trace Service

Handles saving and retrieving agent reasoning traces for transparency and debugging.
Traces are persisted only when called within an active Flask app context (and for
tool usage, request context). Callers (e.g. WebSocket handlers) must run agent
logic inside app.app_context() and app.test_request_context() so db.session works.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _has_app_context() -> bool:
    """True if we're inside a Flask application context (required for db.session)."""
    try:
        from flask import has_app_context
        return has_app_context()
    except Exception as e:
        logger.debug("has_app_context check failed: %s", e)
        return False


class AIReasoningTraceService:
    """Service for saving and retrieving reasoning traces."""

    @staticmethod
    def _extract_tools_used(steps: List[Dict[str, Any]]) -> List[str]:
        tools = []
        for step in steps or []:
            action = step.get("action")
            if action and action != "finish":
                tools.append(action)
        # preserve a stable order
        return sorted(set(tools))

    @staticmethod
    def _estimate_token_counts(query: str, final_answer: Optional[str]) -> Tuple[int, int]:
        # Very rough approximation; good enough for dashboard trends.
        input_tokens = int(len((query or "").split()) * 1.3)
        output_tokens = int(len((final_answer or "").split()) * 1.3) if final_answer else 0
        return input_tokens, output_tokens

    def create_trace(
        self,
        *,
        query: str,
        user_id: Optional[int],
        conversation_id: Optional[str],
        llm_provider: str,
        llm_model: str,
        agent_mode: str = "react",
        max_iterations: Optional[int] = None,
        query_language: Optional[str] = None,
        original_query: Optional[str] = None,
    ) -> Optional[int]:
        """Create a trace row early so we can attach tool usage to it."""
        if not _has_app_context():
            logger.warning("create_trace called without app context; trace will not be persisted")
            return None
        try:
            from app.models import AIReasoningTrace
            from app.extensions import db

            input_tokens, output_tokens = self._estimate_token_counts(query, None)
            lang = (query_language or "en").strip()[:10] if query_language else "en"

            trace = AIReasoningTrace(
                conversation_id=conversation_id,
                user_id=user_id,
                query=query,
                original_query=original_query if (original_query and (original_query or "").strip() != (query or "").strip()) else None,
                query_language=lang,
                agent_mode=agent_mode,
                max_iterations=max_iterations or 10,
                actual_iterations=0,
                status="running",
                steps=[],
                tools_used=[],
                tool_call_count=0,
                total_input_tokens=input_tokens,
                total_output_tokens=output_tokens,
                total_cost_usd=0.0,
                final_answer=None,
                llm_provider=llm_provider,
                llm_model=llm_model,
            )

            db.session.add(trace)
            db.session.commit()
            logger.info("Created reasoning trace id=%s for query=%s", trace.id, (query or "")[:60])
            return trace.id
        except Exception as e:
            logger.error(f"Failed to create reasoning trace: {e}", exc_info=True)
            try:
                db.session.rollback()
            except Exception as rollback_e:
                logger.debug("Rollback failed: %s", rollback_e)
            return None

    def finalize_trace(
        self,
        *,
        trace_id: Optional[int],
        query: str,
        user_id: Optional[int],
        conversation_id: Optional[str],
        steps: Optional[List[Dict[str, Any]]],
        final_answer: Optional[str],
        status: str,
        total_cost: float,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        agent_mode: str = "react",
        max_iterations: Optional[int] = None,
        execution_time_ms: Optional[int] = None,
        error_message: Optional[str] = None,
        total_input_tokens: Optional[int] = None,
        total_output_tokens: Optional[int] = None,
        query_language: Optional[str] = None,
        execution_path: Optional[str] = None,
        output_payloads: Optional[Dict[str, Any]] = None,
        original_query: Optional[str] = None,
    ) -> None:
        """Finalize (and if needed create) a reasoning trace with full details."""
        if not _has_app_context():
            logger.warning("finalize_trace called without app context; trace will not be persisted")
            return
        try:
            from app.models import AIReasoningTrace
            from app.extensions import db

            normalized_steps = steps or []
            tools_used = self._extract_tools_used(normalized_steps)
            tool_call_count = len([s for s in normalized_steps if s.get("action") and s.get("action") != "finish"])
            # Use real token counts from LLM when provided; otherwise estimate
            if total_input_tokens is not None and total_input_tokens >= 0 and total_output_tokens is not None and total_output_tokens >= 0:
                input_tokens, output_tokens = total_input_tokens, total_output_tokens
            else:
                input_tokens, output_tokens = self._estimate_token_counts(query=query, final_answer=final_answer)

            trace = None
            if trace_id:
                trace = db.session.get(AIReasoningTrace, trace_id)

            if not trace:
                # Fallback: create a new trace row if early creation failed.
                lang = (query_language or "en").strip()[:10] if query_language else "en"
                trace = AIReasoningTrace(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    query=query,
                    original_query=original_query if (original_query and (original_query or "").strip() != (query or "").strip()) else None,
                    query_language=lang,
                    agent_mode=agent_mode,
                    max_iterations=max_iterations or 10,
                    actual_iterations=0,
                    status="running",
                    steps=[],
                    tools_used=[],
                    tool_call_count=0,
                    total_input_tokens=input_tokens,
                    total_output_tokens=output_tokens,
                    total_cost_usd=0.0,
                    final_answer=None,
                    llm_provider=llm_provider,
                    llm_model=llm_model,
                )
                db.session.add(trace)
                db.session.flush()  # get ID without committing yet

            if original_query is not None and (original_query or "").strip() != (query or "").strip():
                trace.original_query = (original_query or "").strip() or None
            trace.steps = normalized_steps
            trace.actual_iterations = len(normalized_steps)
            trace.status = status or "completed"
            trace.error_message = error_message
            trace.tools_used = tools_used
            trace.tool_call_count = tool_call_count
            trace.total_input_tokens = input_tokens
            trace.total_output_tokens = output_tokens
            trace.total_cost_usd = float(total_cost or 0.0)
            trace.execution_time_ms = int(execution_time_ms) if execution_time_ms is not None else trace.execution_time_ms
            if query_language is not None:
                trace.query_language = (query_language or "en").strip()[:10] or "en"
            if execution_path is not None and hasattr(trace, "execution_path"):
                trace.execution_path = (execution_path or "").strip()[:50] or None
            if output_payloads is not None and hasattr(trace, "output_payloads"):
                trace.output_payloads = output_payloads
            if llm_provider is not None:
                trace.llm_provider = llm_provider
            if llm_model is not None:
                trace.llm_model = llm_model
            # Set final_answer last so it is never overwritten by optional fields; always persist the answer
            trace.final_answer = final_answer

            db.session.commit()
            logger.info(
                "Finalized reasoning trace id=%s status=%s steps=%s",
                trace.id,
                trace.status,
                len(normalized_steps),
            )
        except Exception as e:
            logger.error(f"Failed to finalize reasoning trace: {e}", exc_info=True)
            try:
                db.session.rollback()
            except Exception as rollback_e:
                logger.debug("Rollback failed: %s", rollback_e)

    def save_trace(
        self,
        query: str,
        steps: List[Dict[str, Any]],
        final_answer: Optional[str],
        status: str,
        total_cost: float,
        user_id: Optional[int],
        conversation_id: Optional[str],
        llm_provider: str,
        llm_model: str
    ):
        """Save a reasoning trace to the database (legacy helper)."""
        try:
            from app.models import AIReasoningTrace
            from app.extensions import db

            # Extract tool names
            tools_used = self._extract_tools_used(steps)

            # Count tokens (approximate)
            total_input_tokens, total_output_tokens = self._estimate_token_counts(query, final_answer)

            trace = AIReasoningTrace(
                conversation_id=conversation_id,
                user_id=user_id,
                query=query,
                agent_mode='react',
                actual_iterations=len(steps),
                status=status,
                steps=steps,
                tools_used=tools_used,
                tool_call_count=len([s for s in steps if s.get('action') != 'finish']),
                total_input_tokens=int(total_input_tokens),
                total_output_tokens=int(total_output_tokens),
                total_cost_usd=total_cost,
                final_answer=final_answer,
                llm_provider=llm_provider,
                llm_model=llm_model
            )

            db.session.add(trace)
            db.session.commit()

            logger.info(f"Saved reasoning trace for query: {query[:50]}...")

        except Exception as e:
            logger.error(f"Failed to save reasoning trace: {e}", exc_info=True)

    def get_trace(self, trace_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve a reasoning trace."""
        try:
            from app.models import AIReasoningTrace
            from app.extensions import db

            trace = db.session.get(AIReasoningTrace, trace_id)
            if trace:
                return trace.to_dict()
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve trace: {e}")
            return None

    def get_traces_for_user(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get reasoning traces for a user."""
        try:
            from app.models import AIReasoningTrace

            traces = AIReasoningTrace.query.filter_by(user_id=user_id).order_by(
                AIReasoningTrace.created_at.desc()
            ).offset(offset).limit(limit).all()

            return [t.to_dict(include_steps=False) for t in traces]
        except Exception as e:
            logger.error(f"Failed to retrieve traces for user {user_id}: {e}")
            return []

    def get_traces_for_conversation(
        self,
        conversation_id: str
    ) -> List[Dict[str, Any]]:
        """Get all reasoning traces for a conversation."""
        try:
            from app.models import AIReasoningTrace

            traces = AIReasoningTrace.query.filter_by(
                conversation_id=conversation_id
            ).order_by(AIReasoningTrace.created_at.asc()).all()

            return [t.to_dict() for t in traces]
        except Exception as e:
            logger.error(f"Failed to retrieve traces for conversation {conversation_id}: {e}")
            return []
