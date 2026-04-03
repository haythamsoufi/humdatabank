"""
AI Chat Integration Service

Integrates the agentic RAG system with existing chat endpoints.
Provides a simple interface to use either the agent or direct LLM based on configuration.
"""

import logging
from typing import Callable, Dict, Any, List, Optional, Tuple

from flask import current_app
from flask_login import current_user

logger = logging.getLogger(__name__)


class AIChatIntegration:
    """
    Service that integrates the agent executor with existing chat system.

    Automatically decides whether to use:
    - Agent with tools (for complex queries requiring data/documents)
    - Direct LLM (for simple questions)
    
    Provider policy:
    - OpenAI only (no Gemini/Azure/Copilot/provider fallbacks)
    """

    def __init__(self):
        """Initialize the integration service."""
        self.agent_enabled = current_app.config.get('AI_AGENT_ENABLED', True)

        # Initialize agent if enabled
        if self.agent_enabled:
            try:
                from app.services.ai_agent import AIAgentExecutor
                self.agent = AIAgentExecutor()
                logger.info("Agent executor initialized successfully")
            except Exception as e:
                logger.warning(
                    "AI agent disabled due to init failure; chat will use direct LLM only. Error: %s",
                    e,
                    exc_info=True,
                )
                self.agent = None
                self.agent_enabled = False
        else:
            self.agent = None
            logger.info("AI agent disabled by config (AI_AGENT_ENABLED=false)")

    def process_query(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        page_context: Optional[Dict[str, Any]] = None,
        platform_context: Optional[Dict[str, Any]] = None,
        preferred_language: str = 'en',
        on_step: Optional[Callable[[str], None]] = None,
        map_requested: bool = False,
        chart_requested: bool = False,
        original_message: Optional[str] = None,
    ) -> Tuple[str, str, List[str], Dict[str, Any]]:
        """
        Process a user query using the best available method.

        Args:
            message: Message as sent to the agent (may be rewritten).
            conversation_history: Previous messages
            page_context: Current page context
            platform_context: Platform data context
            preferred_language: Response language
            on_step: Optional callback(message: str) invoked before each tool run with a user-facing step message.
            original_message: User's raw message before rewriting (for trace display when different from message).

        Returns:
            Tuple of (response_text, model_name, function_calls, metadata)
        """
        # Message is already rewritten by AIChatEngine.run() when AI_QUERY_REWRITE_ENABLED is true
        # Prepare user context for agent
        user_context = self._build_user_context(platform_context, page_context)
        user_context['map_requested'] = map_requested
        user_context['chart_requested'] = chart_requested

        # Try agent first if enabled
        if self.agent_enabled and self.agent:
            return self._process_with_agent(
                message=message,
                conversation_history=conversation_history,
                user_context=user_context,
                language=preferred_language,
                platform_context=platform_context,
                on_step=on_step,
                original_message=original_message,
            )

        # Fallback to existing LLM integration
        return self._process_with_direct_llm(
            message=message,
            conversation_history=conversation_history,
            platform_context=platform_context,
            page_context=page_context,
            language=preferred_language
        )

    def _process_with_agent(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, Any]]],
        user_context: Dict[str, Any],
        language: str,
        platform_context: Optional[Dict[str, Any]] = None,
        on_step: Optional[Callable[[str], None]] = None,
        original_message: Optional[str] = None,
    ) -> Tuple[str, str, List[str], Dict[str, Any]]:
        """Process query using the agent executor."""
        # Keep the agent.execute() call in its own try/except so that fallback
        # logic that runs AFTER the agent (lines below) is not accidentally caught
        # by the same handler — which would cause _process_with_direct_llm to be
        # called twice (once from the else-branch, once from the except-branch).
        result = None
        try:
            logger.info(f"Processing query with agent: {message[:100]}...")
            result = self.agent.execute(
                query=message,
                conversation_history=conversation_history,
                user_context=user_context,
                language=language,
                on_step_callback=on_step,
                original_message=original_message,
            )
        except Exception as e:
            logger.error("Agent execution error: %s", e, exc_info=True)
            try:
                return self._process_with_direct_llm(
                    message=message,
                    conversation_history=conversation_history,
                    platform_context=platform_context,
                    page_context=None,
                    language=language,
                )
            except Exception as fallback_err:
                logger.error("Direct LLM fallback also failed: %s", fallback_err)
                raise RuntimeError(
                    "Both the AI agent and the direct LLM failed to produce a response. "
                    "Please try again in a moment."
                ) from fallback_err

        # --- Process agent result (outside the try/except for agent.execute) ---

        if result.get('success'):
            response_text = result.get('answer', '')
            # Safety net: strip any leaked agent internals from the response
            try:
                from app.services.ai_response_policy import sanitize_agent_answer
                response_text = sanitize_agent_answer(
                    response_text,
                    has_table_payload=bool(result.get("table_payload")),
                )
            except Exception as e:
                logger.debug("sanitize_agent_answer failed: %s", e)
            metadata = {
                'used_agent': True,
                'provider': getattr(self.agent, 'provider', 'agent'),
                'model': getattr(self.agent, 'model', None),
                'iterations': result.get('iterations', 0),
                'tool_calls': result.get('tool_calls', 0),
                'tools_used': result.get('steps', []),
                'total_cost': result.get('total_cost', 0),
                'status': result.get('status', 'completed'),
                'input_tokens': result.get('total_input_tokens'),
                'output_tokens': result.get('total_output_tokens'),
                'map_payload': result.get('map_payload'),
                'chart_payload': result.get('chart_payload'),
                'table_payload': result.get('table_payload'),
                'answer_content': result.get('answer_content'),
                'output_hint': result.get('output_hint'),
                'trace_id': result.get('trace_id'),
                'confidence': result.get('confidence'),
                'grounding_score': result.get('grounding_score'),
                'sources': result.get('sources'),
            }

            # Extract function calls from steps
            function_calls = [
                step.get('action')
                for step in result.get('steps', [])
                if step.get('action') != 'finish'
            ]

            return response_text, self.agent.model, function_calls, metadata

        elif result.get('status') == 'timeout':
            # Prefer returning a partial answer when available.
            partial_answer = (result.get('answer') or '').strip()
            if partial_answer:
                logger.info(
                    "Agent timed out but has partial answer (%d chars); returning partial output",
                    len(partial_answer),
                )
                metadata = {
                    'used_agent': True,
                    'provider': getattr(self.agent, 'provider', 'agent'),
                    'model': getattr(self.agent, 'model', None),
                    'iterations': result.get('iterations', 0),
                    'tool_calls': result.get('tool_calls', 0),
                    'tools_used': result.get('steps', []),
                    'total_cost': result.get('total_cost', 0),
                    'status': 'timeout_partial',
                    'input_tokens': result.get('total_input_tokens'),
                    'output_tokens': result.get('total_output_tokens'),
                    'map_payload': result.get('map_payload'),
                    'chart_payload': result.get('chart_payload'),
                    'table_payload': result.get('table_payload'),
                    'answer_content': result.get('answer_content'),
                    'output_hint': result.get('output_hint'),
                    'trace_id': result.get('trace_id'),
                }
                function_calls = [
                    step.get('action')
                    for step in result.get('steps', [])
                    if step.get('action') and step.get('action') != 'finish'
                ]
                return partial_answer, self.agent.model, function_calls, metadata

            # No partial answer available; return timeout message.
            timeout_message = (
                "The request took too long to process. Please try again or ask a simpler question."
            )
            metadata = {
                'used_agent': True,
                'provider': getattr(self.agent, 'provider', 'agent'),
                'model': getattr(self.agent, 'model', None),
                'status': 'timeout',
                'trace_id': result.get('trace_id'),
            }
            return timeout_message, self.agent.model, [], metadata

        else:
            # Agent failed but may have a partial answer from completed steps.
            # Use it if available instead of falling back blindly.
            partial_answer = (result.get('answer') or '').strip()
            if partial_answer:
                logger.info(
                    "Agent failed (%s) but has partial answer (%d chars); using it",
                    result.get("error"),
                    len(partial_answer),
                )
                metadata = {
                    'used_agent': True,
                    'provider': getattr(self.agent, 'provider', 'agent'),
                    'model': getattr(self.agent, 'model', None),
                    'iterations': result.get('iterations', 0),
                    'tool_calls': result.get('tool_calls', 0),
                    'tools_used': result.get('steps', []),
                    'total_cost': result.get('total_cost', 0),
                    'status': result.get('status', 'partial'),
                    'input_tokens': result.get('total_input_tokens'),
                    'output_tokens': result.get('total_output_tokens'),
                    'map_payload': result.get('map_payload'),
                    'chart_payload': result.get('chart_payload'),
                    'answer_content': result.get('answer_content'),
                    'output_hint': result.get('output_hint'),
                }
                function_calls = [
                    step.get('action')
                    for step in result.get('steps', [])
                    if step.get('action') and step.get('action') != 'finish'
                ]
                return partial_answer, self.agent.model, function_calls, metadata

            # For llm_error (API-level failure such as timeout) with no steps completed,
            # the same endpoint is likely still struggling. Skip the direct-LLM attempt
            # and propagate immediately so the chat engine's streaming fallback runs.
            if result.get('status') == 'llm_error' and not result.get('steps'):
                raise RuntimeError(
                    "The AI provider failed to respond in time. "
                    "Please try again in a moment."
                )

            # No partial answer; fall back to direct OpenAI (same provider policy).
            logger.warning("Agent failed: %s; using direct OpenAI", result.get("error"))
            try:
                return self._process_with_direct_llm(
                    message=message,
                    conversation_history=conversation_history,
                    platform_context=platform_context,
                    page_context=None,
                    language=language,
                )
            except Exception as fallback_err:
                logger.error("Direct LLM fallback also failed: %s", fallback_err)
                raise RuntimeError(
                    "Both the AI agent and the direct LLM failed to produce a response. "
                    "Please try again in a moment."
                ) from fallback_err

    def _process_with_direct_llm(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, Any]]],
        platform_context: Optional[Dict[str, Any]],
        page_context: Optional[Dict[str, Any]],
        language: str
    ) -> Tuple[str, str, List[str], Dict[str, Any]]:
        """Process query using existing LLM integration (without agent)."""
        try:
            from app.routes.chatbot import integrate_openai_with_telemetry

            if not current_app.config.get("OPENAI_API_KEY"):
                raise RuntimeError("OPENAI_API_KEY not configured")

            response_text, model_name, function_calls = integrate_openai_with_telemetry(
                message,
                platform_context or {},
                conversation_history or [],
                page_context or {},
                language,
            )
            if response_text:
                metadata = {"used_agent": False, "provider": "openai"}
                return response_text, model_name, function_calls, metadata
            raise RuntimeError("OpenAI returned empty response")
        except Exception as e:
            logger.error("Direct OpenAI processing error: %s", e, exc_info=True)
            raise

    def _build_user_context(
        self,
        platform_context: Optional[Dict[str, Any]],
        page_context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build user context dictionary for agent."""
        from app.services.authorization_service import AuthorizationService
        # Primary: use authenticated current_user.
        user_id = getattr(current_user, 'id', None) if getattr(current_user, "is_authenticated", False) else None
        access_level = None

        if user_id is not None:
            access_level = (
                "system_manager"
                if AuthorizationService.is_system_manager(current_user)
                else "admin"
                if AuthorizationService.is_admin(current_user)
                else "user"
            )
        else:
            # Fallback: derive identity from platform_context (HTTP + WS both provide it).
            try:
                if platform_context and isinstance(platform_context, dict):
                    acc = platform_context.get("access") if isinstance(platform_context.get("access"), dict) else {}
                    ui = platform_context.get("user_info") if isinstance(platform_context.get("user_info"), dict) else {}
                    user_id = acc.get("user_id") or ui.get("id") or user_id
                    access_level = acc.get("access_level") or ui.get("access_level") or access_level
            except Exception as e:
                logger.debug("derive identity from platform_context failed: %s", e)

        # If we have a user_id but still no reliable access_level, compute it from DB.
        if user_id is not None and (not access_level or access_level == "public"):
            try:
                from app.models import User
                u = User.query.get(int(user_id))
                if u:
                    access_level = AuthorizationService.access_level(u)
            except Exception as e:
                logger.debug("access_level from User query failed: %s", e)

        access_level = access_level or "public"

        context = {
            'user_id': int(user_id) if user_id is not None else None,
            # Legacy-free: keep a stable classification for downstream agent logic
            'role': access_level,
            'access_level': access_level,
        }

        # Add ONLY a small, allowlisted subset of platform context to avoid prompt bloat.
        if platform_context and isinstance(platform_context, dict):
            for k in ("user_info", "access", "user_data", "available_countries", "conversation_id"):
                if k in platform_context and platform_context.get(k) is not None:
                    context[k] = platform_context.get(k)

        # Add page context if provided
        if page_context:
            context['page_context'] = page_context

        return context
