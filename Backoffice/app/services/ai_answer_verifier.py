"""
AI Answer Verifier (Self-Correction)

After the agent produces a final answer, this service:
1. Checks whether all major claims in the answer are supported by retrieved evidence.
2. Optionally uses the LLM to identify unsupported claims.
3. Returns the original or corrected answer along with a list of caveats.

Gated by AI_ANSWER_VERIFICATION_ENABLED (default True).
Falls back gracefully if LLM is unavailable.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Simple fact indicators — numbers and proper nouns that could be unsupported
_NUMERIC_CLAIM_RE = re.compile(r"\b\d[\d,./\s%]+\b")
_CAVEAT_MARKER = "\n\n> **Note:** Some details in this response could not be verified against the available sources. Please consult the original documents for confirmation."


def _remove_unsupported_claims(answer: str, unsupported_claims: List[str]) -> str:
    """
    Remove sentences containing unsupported claims from the answer.
    Falls back to the original answer if removal would leave it empty.
    """
    _SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
    sentences = _SENTENCE_SPLIT_RE.split(answer)
    claims_lower = [c.lower().strip() for c in unsupported_claims if c and c.strip()]
    if not claims_lower:
        return answer

    kept: List[str] = []
    for sentence in sentences:
        sentence_lower = sentence.lower()
        has_unsupported = any(claim in sentence_lower for claim in claims_lower)
        if not has_unsupported:
            kept.append(sentence)

    return " ".join(kept)


def _build_verification_prompt(answer: str, chunks: List[Dict[str, Any]], max_chunk_chars: int = 3000) -> str:
    """Build the LLM verification prompt."""
    chunk_texts = "\n\n---\n\n".join(
        f"[Source: {c.get('document_title', 'Unknown')}]\n{c.get('content', '')[:500]}"
        for c in chunks[:8]
    )
    if len(chunk_texts) > max_chunk_chars:
        chunk_texts = chunk_texts[:max_chunk_chars] + "\n...[truncated]"

    return (
        "You are an evidence verifier. Given an AI-generated answer and source excerpts, "
        "identify any factual claims in the answer that are NOT supported by the provided sources.\n\n"
        "Respond with a JSON object:\n"
        "{\n"
        '  "has_unsupported_claims": true/false,\n'
        '  "unsupported_claims": ["..."],  // list of exact phrases, empty if none\n'
        '  "recommendation": "ok" | "add_caveat" | "remove_claim"\n'
        "}\n\n"
        f"ANSWER:\n{answer[:1500]}\n\n"
        f"SOURCES:\n{chunk_texts}"
    )


class AIAnswerVerifier:
    """
    Verifies an agent answer against retrieved source evidence.
    Adds caveats or removes unsupported claims when needed.
    """

    def verify(
        self,
        answer: str,
        retrieved_chunks: List[Dict[str, Any]],
        *,
        trace_steps: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[str, bool, List[str]]:
        """
        Verify the answer against evidence and optionally self-correct.

        Returns:
            (final_answer, was_modified, unsupported_claims)
        """
        try:
            from flask import current_app
            enabled = current_app.config.get("AI_ANSWER_VERIFICATION_ENABLED", True)
            if not enabled:
                return answer, False, []
        except Exception:
            return answer, False, []

        if not answer or not retrieved_chunks:
            return answer, False, []

        # Fast path: if answer has no numeric claims and is short, skip LLM check
        has_numeric = bool(_NUMERIC_CLAIM_RE.search(answer))
        if not has_numeric and len(answer) < 200:
            return answer, False, []

        unsupported: List[str] = []
        recommendation = "ok"

        try:
            from flask import current_app
            from openai import OpenAI
            api_key = current_app.config.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("No API key")

            model = current_app.config.get("OPENAI_MODEL", "gpt-4o-mini")
            client = OpenAI(api_key=api_key)

            prompt = _build_verification_prompt(answer, retrieved_chunks)
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            import json
            result = json.loads(resp.choices[0].message.content or "{}")
            has_unsupported = result.get("has_unsupported_claims", False)
            unsupported = result.get("unsupported_claims", [])
            recommendation = result.get("recommendation", "ok")

        except Exception as exc:
            logger.debug("Answer verification LLM call failed: %s", exc)
            # Heuristic fallback: check if answer contains numeric claims not in sources
            chunk_combined = " ".join(
                (c.get("content") or "")[:500] for c in retrieved_chunks[:5]
            ).lower()
            answer_nums = _NUMERIC_CLAIM_RE.findall(answer)
            unverified = [n.strip() for n in answer_nums if n.strip().replace(",", "") not in chunk_combined]
            if len(unverified) > 2:
                recommendation = "add_caveat"
                unsupported = unverified[:5]

        final_answer = answer
        modified = False

        if recommendation == "remove_claim" and unsupported:
            cleaned = _remove_unsupported_claims(answer, unsupported)
            if cleaned and cleaned.strip() and len(cleaned.strip()) > 30:
                final_answer = cleaned.rstrip() + _CAVEAT_MARKER
                modified = True
                logger.info(
                    "Answer verifier: removed %d unsupported claim(s) and added caveat: %s",
                    len(unsupported), unsupported[:3],
                )
            else:
                final_answer = answer + _CAVEAT_MARKER
                modified = True
                logger.info(
                    "Answer verifier: remove_claim would leave answer too short; added caveat only for %d claim(s): %s",
                    len(unsupported), unsupported[:3],
                )
        elif recommendation == "add_caveat" and unsupported:
            final_answer = answer + _CAVEAT_MARKER
            modified = True
            logger.info(
                "Answer verifier: added caveat for %d unsupported claim(s): %s",
                len(unsupported), unsupported[:3],
            )

        # Log the verification step into trace_steps if provided
        if trace_steps is not None:
            trace_steps.append({
                "step": len(trace_steps) + 1,
                "type": "verification",
                "thought": f"Verification: {len(unsupported)} unsupported claim(s) found. Recommendation: {recommendation}.",
                "action": "verify_answer",
                "observation": {
                    "recommendation": recommendation,
                    "unsupported_claims": unsupported[:5],
                    "modified": modified,
                },
            })

        return final_answer, modified, unsupported


def verify_answer(
    answer: str,
    retrieved_chunks: List[Dict[str, Any]],
    trace_steps: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, bool, List[str]]:
    """Convenience wrapper. Safe to call; never raises."""
    try:
        return AIAnswerVerifier().verify(answer, retrieved_chunks, trace_steps=trace_steps)
    except Exception as exc:
        logger.warning("verify_answer: unexpected error: %s", exc)
        return answer, False, []
