"""
AI Grounding Evaluator

Evaluates how well a generated answer is grounded in the retrieved source documents.
Computes a grounding_score (0.0–1.0) and a confidence_level ('high'/'medium'/'low').

Design:
- Fast heuristic pass: check whether key noun phrases from the answer appear in retrieved chunks.
- Optional LLM-as-judge pass (gated by AI_GROUNDING_LLM_ENABLED): a separate LLM call
  evaluates the user's query against the final response for relevance, accuracy,
  completeness, and overall quality. Produces llm_quality_score (0.0–1.0),
  llm_quality_verdict, llm_quality_reasoning, and llm_needs_review.
- Stores grounding_score and confidence_level on AIReasoningTrace.
- Flags traces with grounding_score < AI_GROUNDING_REVIEW_THRESHOLD for expert review.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Heuristic helpers
# ---------------------------------------------------------------------------

# Strip markdown formatting for plain-text comparison
_MD_STRIP_RE = re.compile(r"(\*\*|__|`+|\[.*?\]\(.*?\)|#{1,6}\s+)")
# Sentence splitter (rough)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
# Key noun-phrase extraction: sequences of 2–5 capitalized or quoted words / numbers
_CLAIM_WORD_RE = re.compile(r"\b[A-Z][a-zA-Z]{2,}\b|\b\d[\d,.]+\b|\b\"[^\"]{3,}\"\b")


def _strip_markdown(text: str) -> str:
    return _MD_STRIP_RE.sub(" ", text)


def _extract_claim_tokens(text: str, max_tokens: int = 40) -> List[str]:
    """Extract the most informative tokens from an answer for grounding checks."""
    clean = _strip_markdown(text).lower()
    raw_words = re.findall(r"\b\d[\d,.]+\b|\b[a-z]{4,}\b", clean)
    seen: set = set()
    tokens: List[str] = []
    for w in raw_words:
        if w not in seen:
            seen.add(w)
            tokens.append(w)
        if len(tokens) >= max_tokens:
            break
    return tokens


_NUMERIC_RE = re.compile(r"\b\d[\d,.\s]*\d\b|\b\d+\b")


def _extract_numeric_claims(text: str) -> List[str]:
    """Extract concrete numbers from the answer for targeted verification."""
    clean = _strip_markdown(text)
    nums = _NUMERIC_RE.findall(clean)
    normalized: List[str] = []
    for n in nums:
        n = n.strip().replace(",", "").replace(" ", "")
        if n and len(n) >= 2 and n not in normalized:
            normalized.append(n)
    return normalized


def _numeric_grounding_score(answer: str, combined_source: str) -> Optional[float]:
    """
    Check what fraction of numeric claims in the answer appear in source text.
    Returns None if there are too few numbers to evaluate.
    """
    nums = _extract_numeric_claims(answer)
    if len(nums) < 2:
        return None
    source_clean = combined_source.replace(",", "").replace(" ", "")
    matched = sum(1 for n in nums if n in source_clean)
    return matched / len(nums)


def _chunk_texts_combined(chunks: List[Dict[str, Any]], max_chars: int = 20000) -> str:
    """Flatten retrieved chunk contents into a single lower-case string for fast matching."""
    parts = []
    total = 0
    for chunk in chunks:
        content = (chunk.get("content") or "").lower()
        parts.append(content)
        total += len(content)
        if total >= max_chars:
            break
    return " ".join(parts)


def heuristic_grounding_score(
    answer: str,
    retrieved_chunks: List[Dict[str, Any]],
    min_tokens: int = 5,
) -> float:
    """
    Fast heuristic combining token overlap and numeric claim verification.

    Returns 0.0-1.0. Returns 0.5 (neutral) when the answer is too short to evaluate.
    Numeric claims are weighted more heavily because getting numbers wrong is
    more consequential than missing a generic word.
    """
    if not answer or not answer.strip():
        return 0.0
    if not retrieved_chunks:
        return 0.1

    tokens = _extract_claim_tokens(answer)
    if len(tokens) < min_tokens:
        return 0.5

    combined_source = _chunk_texts_combined(retrieved_chunks)
    matched = sum(1 for t in tokens if t in combined_source)
    token_score = matched / len(tokens)

    numeric_score = _numeric_grounding_score(answer, combined_source)

    if numeric_score is not None:
        score = 0.4 * token_score + 0.6 * numeric_score
    else:
        score = token_score

    return round(min(1.0, max(0.0, score)), 3)


def score_to_confidence_level(grounding_score: float) -> str:
    """Convert a grounding score to a human-readable confidence level."""
    if grounding_score >= 0.75:
        return "high"
    if grounding_score >= 0.45:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# LLM-as-judge evaluation
# ---------------------------------------------------------------------------

_LLM_JUDGE_VALID_VERDICTS = frozenset({"excellent", "good", "acceptable", "poor", "incorrect"})

_VERDICT_TO_SCORE_RANGE = {
    "excellent": (0.9, 1.0),
    "good": (0.7, 0.89),
    "acceptable": (0.5, 0.69),
    "poor": (0.2, 0.49),
    "incorrect": (0.0, 0.19),
}


def _build_llm_judge_prompt(
    query: str,
    answer: str,
    retrieved_chunks: List[Dict[str, Any]],
    *,
    output_context: Optional[Dict[str, Any]] = None,
    max_answer_chars: int = 2000,
    max_chunk_chars: int = 3000,
) -> str:
    """Build the system + user prompt for the LLM judge."""
    chunk_texts = "\n\n---\n\n".join(
        f"[Source: {c.get('document_title', 'Unknown')}]\n{(c.get('content') or '')[:500]}"
        for c in retrieved_chunks[:8]
    )
    if len(chunk_texts) > max_chunk_chars:
        chunk_texts = chunk_texts[:max_chunk_chars] + "\n...[truncated]"

    output_section = ""
    if output_context:
        parts: List[str] = []
        if output_context.get("has_chart"):
            chart_type = output_context.get("chart_type", "chart")
            metric = output_context.get("chart_metric", "")
            desc = f"a {chart_type} visualization"
            if metric:
                desc += f" of \"{metric}\""
            parts.append(desc)
        if output_context.get("has_map"):
            parts.append("an interactive map")
        if output_context.get("has_table"):
            parts.append("a data table")
        if parts:
            visuals = ", ".join(parts)
            output_section = (
                f"\nOUTPUT FORMAT CONTEXT:\n"
                f"The user sees the text ANSWER below alongside {visuals} rendered in the UI. "
                f"The text answer is intentionally concise because the visual element(s) present the detailed data. "
                f"Do NOT penalise clarity or completeness for brevity when visual payloads carry the detail.\n"
            )

    return (
        "You are a strict quality-assurance judge for an AI assistant. "
        "Given the user's QUERY, the AI-generated ANSWER, and the SOURCE documents the answer was based on, "
        "evaluate the response on these dimensions:\n\n"
        "1. **Relevance**: Does the answer address what the user actually asked?\n"
        "2. **Accuracy**: Are the facts and figures in the answer correct and supported by the sources?\n"
        "3. **Completeness**: Does the answer cover the key aspects of the query, or is important information missing?\n"
        "4. **Clarity**: Is the answer well-structured and easy to understand?\n\n"
        "Respond with a JSON object (no extra text):\n"
        "{\n"
        '  "relevance": 0-10,\n'
        '  "accuracy": 0-10,\n'
        '  "completeness": 0-10,\n'
        '  "clarity": 0-10,\n'
        '  "overall_score": 0.0-1.0,\n'
        '  "verdict": "excellent" | "good" | "acceptable" | "poor" | "incorrect",\n'
        '  "needs_review": true/false,\n'
        '  "reasoning": "2-3 sentence explanation of your assessment"\n'
        "}\n\n"
        "Scoring guidance:\n"
        '- "excellent" (0.9-1.0): Fully answers the query with accurate, well-sourced information.\n'
        '- "good" (0.7-0.89): Mostly correct and relevant, minor gaps or improvements possible.\n'
        '- "acceptable" (0.5-0.69): Partially answers the query, some inaccuracies or missing info.\n'
        '- "poor" (0.2-0.49): Significant issues — wrong data, misses the point, or largely unsupported.\n'
        '- "incorrect" (0.0-0.19): Factually wrong, irrelevant, or harmful.\n\n'
        'Set "needs_review" to true if you have any doubt about accuracy, '
        "if the answer contains unsupported claims, or if the quality is below \"good\".\n\n"
        f"QUERY:\n{query[:1000]}\n\n"
        f"ANSWER:\n{answer[:max_answer_chars]}\n"
        f"{output_section}\n"
        f"SOURCES:\n{chunk_texts}"
    )


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def _extract_json(raw: str) -> str:
    """Extract JSON from the response, stripping markdown code fences if present."""
    text = (raw or "").strip()
    if not text:
        return "{}"
    if text.startswith("{"):
        return text
    m = _JSON_FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return text


def _parse_llm_judge_response(raw: str) -> Dict[str, Any]:
    """Parse and validate the JSON response from the LLM judge.

    Resilient: synthesises a fallback reasoning string when the model omits it
    rather than discarding the entire evaluation.
    """
    cleaned = _extract_json(raw)
    result = json.loads(cleaned)

    score = float(result.get("overall_score", 0.5))
    score = round(min(1.0, max(0.0, score)), 3)

    verdict = str(result.get("verdict", "acceptable")).lower().strip()
    if verdict not in _LLM_JUDGE_VALID_VERDICTS:
        verdict = "acceptable"
        for v, (vlo, vhi) in _VERDICT_TO_SCORE_RANGE.items():
            if vlo <= score <= vhi:
                verdict = v
                break

    needs_review = bool(result.get("needs_review", score < 0.7))

    reasoning = str(result.get("reasoning") or "").strip()[:1000]
    if not reasoning:
        reasoning = (
            f"Auto-assessed as {verdict} (score {score:.2f}). "
            f"Relevance={result.get('relevance', '?')}, "
            f"Accuracy={result.get('accuracy', '?')}, "
            f"Completeness={result.get('completeness', '?')}, "
            f"Clarity={result.get('clarity', '?')}."
        )
        logger.debug("LLM judge: reasoning was empty; synthesised fallback")

    return {
        "llm_quality_score": score,
        "llm_quality_verdict": verdict,
        "llm_quality_reasoning": reasoning,
        "llm_needs_review": needs_review,
        "sub_scores": {
            "relevance": min(10, max(0, int(result.get("relevance", 5)))),
            "accuracy": min(10, max(0, int(result.get("accuracy", 5)))),
            "completeness": min(10, max(0, int(result.get("completeness", 5)))),
            "clarity": min(10, max(0, int(result.get("clarity", 5)))),
        },
    }


_JUDGE_SAFE_MODELS = ("gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1-nano")

_STRUCTURED_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "llm_quality_judge_result",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "relevance",
                "accuracy",
                "completeness",
                "clarity",
                "overall_score",
                "verdict",
                "needs_review",
                "reasoning",
            ],
            "properties": {
                "relevance": {"type": "integer"},
                "accuracy": {"type": "integer"},
                "completeness": {"type": "integer"},
                "clarity": {"type": "integer"},
                "overall_score": {"type": "number"},
                "verdict": {
                    "type": "string",
                    "enum": ["excellent", "good", "acceptable", "poor", "incorrect"],
                },
                "needs_review": {"type": "boolean"},
                "reasoning": {"type": "string"},
            },
        },
    },
}

_JSON_OBJECT_FORMAT: Dict[str, Any] = {"type": "json_object"}


def _resolve_llm_judge_config() -> Tuple[bool, str]:
    """Resolve AI_GROUNDING_LLM_ENABLED and model from DB settings first, then Flask config.

    Returns (enabled: bool, model: str).
    """
    from flask import current_app

    def _to_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "y", "on"}:
                return True
            if lowered in {"0", "false", "no", "n", "off", ""}:
                return False
        return bool(default)

    enabled_cfg = current_app.config.get("AI_GROUNDING_LLM_ENABLED", False)
    model_cfg = (
        current_app.config.get("AI_GROUNDING_LLM_MODEL")
        or ""
    )

    try:
        from app.utils.app_settings import get_ai_settings
        ai_db = get_ai_settings()
        raw_enabled = ai_db.get("AI_GROUNDING_LLM_ENABLED")
        if raw_enabled is not None:
            enabled_cfg = _to_bool(raw_enabled, enabled_cfg)
        raw_model = ai_db.get("AI_GROUNDING_LLM_MODEL")
        if raw_model and isinstance(raw_model, str) and raw_model.strip():
            model_cfg = raw_model.strip()
    except Exception:
        pass

    enabled = _to_bool(enabled_cfg, False)

    if not model_cfg:
        main_model = current_app.config.get("OPENAI_MODEL", "") or ""
        model_cfg = (
            main_model if main_model.lower() in _JUDGE_SAFE_MODELS
            else "gpt-4o-mini"
        )

    return enabled, model_cfg


def _model_supports_strict_schema(model: str) -> bool:
    """Whether the model reliably supports response_format json_schema with strict=True."""
    m = (model or "").strip().lower()
    if m.startswith("gpt-5"):
        return False
    if m.startswith("o1") or m.startswith("o3") or m.startswith("o4"):
        return False
    return True


def llm_judge_evaluate(
    *,
    query: str,
    answer: str,
    retrieved_chunks: List[Dict[str, Any]],
    output_context: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Call the LLM to evaluate response quality.

    Returns a dict with llm_quality_score, llm_quality_verdict,
    llm_quality_reasoning, llm_needs_review, and sub_scores.
    Returns None if the LLM call fails or is not configured.
    """
    try:
        from flask import current_app
    except Exception:
        return None

    enabled, model = _resolve_llm_judge_config()
    if not enabled:
        return None

    if not query or not answer or not answer.strip():
        return None

    try:
        from openai import OpenAI
        from app.utils.ai_utils import openai_model_supports_sampling_params

        api_key = current_app.config.get("OPENAI_API_KEY")
        if not api_key:
            logger.debug("LLM judge: no OPENAI_API_KEY configured")
            return None

        timeout_sec = int(current_app.config.get("AI_HTTP_TIMEOUT_SECONDS", 30))
        client = OpenAI(api_key=api_key, timeout=timeout_sec)

        prompt = _build_llm_judge_prompt(
            query, answer, retrieved_chunks, output_context=output_context,
        )

        use_strict = _model_supports_strict_schema(model)
        response_fmt = _STRUCTURED_OUTPUT_SCHEMA if use_strict else _JSON_OBJECT_FORMAT

        kwargs_base: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_completion_tokens": 700,
            "response_format": response_fmt,
        }
        if openai_model_supports_sampling_params(str(model)):
            kwargs_base["temperature"] = 0.0

        resp = None
        result = None
        last_err: Optional[Exception] = None

        for attempt in (1, 2):
            try:
                resp = client.chat.completions.create(**kwargs_base)
                choice = resp.choices[0] if resp.choices else None
                if choice is None:
                    raise ValueError("LLM judge: empty choices array")

                msg = choice.message
                refusal = getattr(msg, "refusal", None)
                if refusal:
                    raise ValueError(f"LLM judge: model refused — {refusal}")

                raw_content = msg.content or ""
                if not raw_content.strip():
                    finish = getattr(choice, "finish_reason", None)
                    raise ValueError(
                        f"LLM judge: empty content (finish_reason={finish})"
                    )

                result = _parse_llm_judge_response(raw_content)
                break

            except (json.JSONDecodeError, ValueError, KeyError, TypeError) as attempt_err:
                last_err = attempt_err
                if attempt == 1:
                    logger.warning(
                        "LLM judge attempt %d failed (model=%s): %s — retrying with json_object format",
                        attempt, model, attempt_err,
                    )
                    kwargs_base["response_format"] = _JSON_OBJECT_FORMAT
                else:
                    logger.warning(
                        "LLM judge attempt %d failed (model=%s): %s",
                        attempt, model, attempt_err,
                    )

        if result is None:
            if last_err:
                raise last_err
            raise ValueError("LLM judge returned no result")

        if resp is not None:
            usage = getattr(resp, "usage", None)
            if usage:
                in_tok = getattr(usage, "prompt_tokens", 0) or 0
                out_tok = getattr(usage, "completion_tokens", 0) or 0
                try:
                    from app.utils.ai_pricing import estimate_chat_cost
                    cost = estimate_chat_cost(model, in_tok, out_tok)
                    result["eval_cost_usd"] = cost
                    result["eval_input_tokens"] = in_tok
                    result["eval_output_tokens"] = out_tok
                except Exception:
                    pass

        logger.info(
            "LLM judge: score=%.3f verdict=%s needs_review=%s model=%s",
            result["llm_quality_score"],
            result["llm_quality_verdict"],
            result["llm_needs_review"],
            model,
        )
        return result

    except Exception as exc:
        logger.warning("LLM judge evaluation failed: %s", exc)
        return None


def _persist_llm_judge_result(
    trace_id: Optional[int],
    llm_result: Dict[str, Any],
) -> None:
    """Store LLM judge results on AIReasoningTrace and optionally queue for review."""
    if not trace_id or not llm_result:
        return
    try:
        from app.extensions import db
        from app.models import AIReasoningTrace

        trace = db.session.get(AIReasoningTrace, trace_id)
        if trace is None:
            return

        trace.llm_quality_score = llm_result.get("llm_quality_score")
        trace.llm_quality_verdict = llm_result.get("llm_quality_verdict")
        trace.llm_quality_reasoning = llm_result.get("llm_quality_reasoning")
        trace.llm_needs_review = llm_result.get("llm_needs_review")

        eval_cost = llm_result.get("eval_cost_usd")
        if eval_cost and trace.total_cost_usd is not None:
            trace.total_cost_usd = (trace.total_cost_usd or 0.0) + float(eval_cost)

        db.session.commit()

        if llm_result.get("llm_needs_review"):
            _auto_queue_trace_for_review(trace_id)

    except Exception as exc:
        logger.warning("Failed to persist LLM judge result for trace %s: %s", trace_id, exc)
        try:
            from app.extensions import db
            db.session.rollback()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main evaluator
# ---------------------------------------------------------------------------

class AIGroundingEvaluator:
    """
    Evaluates answer grounding against retrieved sources.

    Usage:
        evaluator = AIGroundingEvaluator()
        score, level = evaluator.evaluate(answer=answer_text, retrieved_chunks=chunks)
        evaluator.persist(trace_id=trace_id, score=score, level=level)
    """

    def evaluate(
        self,
        *,
        answer: str,
        retrieved_chunks: List[Dict[str, Any]],
    ) -> Tuple[float, str]:
        """
        Compute grounding_score and confidence_level for an answer.

        Returns:
            (grounding_score: float, confidence_level: str)
        """
        try:
            score = heuristic_grounding_score(answer, retrieved_chunks)
            level = score_to_confidence_level(score)
            if level == "low":
                logger.warning(
                    "QUALITY: Low grounding score=%.3f level=%s chunks=%d answer_len=%d",
                    score, level, len(retrieved_chunks), len(answer),
                )
            else:
                logger.info(
                    "Grounding evaluation: score=%.3f level=%s chunks=%d",
                    score, level, len(retrieved_chunks),
                )
            return score, level
        except Exception as exc:
            logger.warning("Grounding evaluation failed: %s", exc)
            return 0.5, "medium"

    def persist(
        self,
        *,
        trace_id: Optional[int],
        score: float,
        level: str,
        auto_queue_for_review: bool = True,
    ) -> None:
        """
        Store grounding_score and confidence_level on AIReasoningTrace.
        Optionally queues the trace for expert review when score is low.
        """
        if not trace_id:
            return
        try:
            from flask import current_app
            from app.extensions import db
            from app.models import AIReasoningTrace

            trace = db.session.get(AIReasoningTrace, trace_id)
            if trace is None:
                logger.debug("Grounding persist: trace %s not found", trace_id)
                return

            trace.grounding_score = score
            trace.confidence_level = level
            db.session.commit()

            threshold = float(current_app.config.get("AI_GROUNDING_REVIEW_THRESHOLD", 0.5))
            if auto_queue_for_review and score < threshold:
                logger.info(
                    "Grounding score %.3f below threshold %.2f for trace %s — flagging for review",
                    score, threshold, trace_id,
                )
                _auto_queue_trace_for_review(trace_id)

        except Exception as exc:
            logger.warning("Grounding persist failed for trace %s: %s", trace_id, exc)
            try:
                from app.extensions import db
                db.session.rollback()
            except Exception:
                pass


def _auto_queue_trace_for_review(trace_id: int) -> None:
    """Create an AITraceReview row with status='pending' if one does not already exist."""
    try:
        from app.extensions import db
        from app.models.embeddings import AITraceReview

        existing = AITraceReview.query.filter_by(trace_id=trace_id).first()
        if existing:
            return
        review = AITraceReview(
            trace_id=trace_id,
            status="pending",
        )
        db.session.add(review)
        db.session.commit()
        logger.info("Auto-queued trace %s for expert review", trace_id)
    except Exception as exc:
        logger.warning("Failed to auto-queue trace %s for review: %s", trace_id, exc)
        try:
            from app.extensions import db
            db.session.rollback()
        except Exception:
            pass


def evaluate_and_persist(
    *,
    trace_id: Optional[int],
    answer: str,
    retrieved_chunks: List[Dict[str, Any]],
    auto_queue_for_review: bool = True,
) -> Tuple[float, str]:
    """
    Convenience wrapper: evaluate heuristic grounding and persist.
    Safe to call from agent executor; never raises.

    Returns:
        (grounding_score, confidence_level)
    """
    try:
        evaluator = AIGroundingEvaluator()
        score, level = evaluator.evaluate(answer=answer, retrieved_chunks=retrieved_chunks)
        evaluator.persist(
            trace_id=trace_id,
            score=score,
            level=level,
            auto_queue_for_review=auto_queue_for_review,
        )

        return score, level
    except Exception as exc:
        logger.warning("evaluate_and_persist: unexpected error: %s", exc)
        return 0.5, "medium"


def evaluate_quality_and_persist(
    *,
    trace_id: Optional[int],
    query: str,
    answer: str,
    retrieved_chunks: Optional[List[Dict[str, Any]]] = None,
    output_context: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Convenience wrapper: run LLM quality judge and persist results on trace.
    Safe to call even when no retrieved chunks are available.
    """
    try:
        llm_result = llm_judge_evaluate(
            query=query,
            answer=answer,
            retrieved_chunks=retrieved_chunks or [],
            output_context=output_context,
        )
        if llm_result:
            _persist_llm_judge_result(trace_id, llm_result)
        return llm_result
    except Exception as exc:
        logger.debug("evaluate_quality_and_persist skipped: %s", exc)
        return None
