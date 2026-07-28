"""
Runtime utility helpers for AI agent execution.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def estimate_openai_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate OpenAI API call cost using centralized pricing (config or defaults)."""
    from app.utils.ai_pricing import estimate_chat_cost
    return estimate_chat_cost(model, input_tokens, output_tokens)


def synthesize_partial_answer(steps: List[Dict[str, Any]], client: Any, model: str) -> str:
    """
    Synthesize a partial answer from completed steps when agent stops early.

    Attempts a quick LLM call to summarize the tool observations into a
    human-readable answer. Falls back to a brief textual summary.
    """
    if not steps:
        return "I was unable to complete the analysis."

    observations = [step.get("observation", "") for step in steps if step.get("observation")]
    if not observations:
        return "The analysis was interrupted before completion."

    digest_parts: List[str] = []
    for step in steps:
        action = step.get("action")
        obs = step.get("observation")
        if not action or action == "finish" or not obs:
            continue
        if isinstance(obs, dict):
            if obs.get("success") is False:
                digest_parts.append(f"Tool {action}: error - {obs.get('error', 'unknown')}")
            elif "result" in obs:
                result = obs["result"]
                if isinstance(result, list):
                    count = len(result)
                    snippet = ""
                    if count > 0 and isinstance(result[0], dict):
                        snippet = (result[0].get("content") or result[0].get("document_title") or "")[:200]
                    digest_parts.append(f"Tool {action}: found {count} result(s). First: {snippet}…" if snippet else f"Tool {action}: found {count} result(s).")
                elif isinstance(result, dict):
                    digest_parts.append(f"Tool {action}: returned data with keys {list(result.keys())[:8]}")
                else:
                    digest_parts.append(f"Tool {action}: {str(result)[:300]}")
            else:
                digest_parts.append(f"Tool {action}: completed (keys: {list(obs.keys())[:6]})")
        else:
            digest_parts.append(f"Tool {action}: {str(obs)[:300]}")

    digest = "\n".join(digest_parts) if digest_parts else "Partial data collected."

    try:
        synthesis_messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. The user asked a question and an automated agent "
                    "collected partial data before being interrupted. Summarize the collected data "
                    "into a concise, helpful answer for the user. Do NOT include raw JSON, tool "
                    "names, or internal metadata. If the data is insufficient, say so clearly."
                ),
            },
            {
                "role": "user",
                "content": f"Summarize these findings into a helpful answer:\n\n{digest}",
            },
        ]
        resp = client.chat.completions.create(
            model=model,
            messages=synthesis_messages,
            max_completion_tokens=600,
        )
        answer = (resp.choices[0].message.content or "").strip()
        if answer:
            return answer
    except Exception as e:
        logger.warning("synthesize_partial_answer LLM call failed: %s", e)

    return f"Based on partial analysis:\n\n{digest}"
