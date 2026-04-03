"""
Trigger automated trace review packet export for terminal-driven triage.

This script is intended for agent-driven review loops:
- read pending review packets
- process traces one by one
- implement code fixes from repeated failure patterns

Run from Backoffice:
  python scripts/trigger_automated_trace_review.py --status pending --limit 5 --format text
  python scripts/trigger_automated_trace_review.py --status pending --limit 20 --format jsonl --output pending_reviews.jsonl
  python scripts/trigger_automated_trace_review.py --status pending --limit 5 --claim-in-review
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import joinedload

# Ensure Backoffice root is importable when running as:
#   python scripts/trigger_automated_trace_review.py
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app import create_app
from app.extensions import db
from app.models.embeddings import AITraceReview
from app.utils.datetime_helpers import utcnow


VALID_STATUSES = {"pending", "in_review", "completed", "dismissed", "all"}
VALID_FORMATS = {"text", "jsonl"}


def _to_text(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    return str(value)


def _summarize_observation(observation: Any, max_lines: int) -> str:
    raw = observation if isinstance(observation, str) else json.dumps(
        observation,
        indent=2,
        ensure_ascii=False,
        default=str,
    )
    lines = raw.splitlines()
    if len(lines) <= max_lines:
        return raw
    kept = "\n".join(lines[:max_lines])
    return f"{kept}\n... (truncated, {len(lines) - max_lines} more lines)"


def _build_text_packet(review: AITraceReview, max_obs_lines: int) -> str:
    trace = review.trace
    if trace is None:
        return (
            f"=== Review #{review.id} ===\n"
            f"Status: {review.status}\n"
            "Trace: missing\n"
        )

    lines: List[str] = []
    lines.append(f"=== Review #{review.id} | Trace #{trace.id} ===")
    lines.append(f"Review status: {review.status}")
    lines.append(f"Queued at: {review.created_at.isoformat() if review.created_at else '-'}")
    lines.append(f"Trace status: {_to_text(trace.status)}")
    if trace.original_query:
        lines.append(f"Original query: {_to_text(trace.original_query)}")
        lines.append(f"Rewritten query: {_to_text(trace.query)}")
    else:
        lines.append(f"Query: {_to_text(trace.query)}")
    lines.append(f"Execution path: {_to_text(trace.execution_path)}")
    lines.append(f"Model: {_to_text(trace.llm_model)} ({_to_text(trace.llm_provider)})")
    lines.append(
        "Time/Cost/Tokens: "
        f"{_to_text(trace.execution_time_ms)} ms | ${_to_text(trace.total_cost_usd)} | "
        f"{int(trace.total_input_tokens or 0)} in / {int(trace.total_output_tokens or 0)} out"
    )
    if trace.grounding_score is not None or trace.confidence_level:
        lines.append(
            "Grounding: "
            f"{trace.grounding_score if trace.grounding_score is not None else '-'} "
            f"({_to_text(trace.confidence_level)})"
        )
    if trace.llm_quality_score is not None or trace.llm_quality_verdict or trace.llm_needs_review is not None:
        lines.append(
            "LLM quality: "
            f"{trace.llm_quality_score if trace.llm_quality_score is not None else '-'} "
            f"({_to_text(trace.llm_quality_verdict)}) "
            f"[needs_review={_to_text(trace.llm_needs_review)}]"
        )
    if trace.llm_quality_reasoning:
        lines.append(f"LLM quality reasoning: {trace.llm_quality_reasoning}")
    if trace.tools_used:
        lines.append(f"Tools used: {', '.join(str(t) for t in (trace.tools_used or []))}")
    if trace.user_rating:
        lines.append(f"User rating: {trace.user_rating}")
    lines.append("")

    steps = trace.steps if isinstance(trace.steps, list) else []
    if steps:
        for idx, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue
            n = step.get("step") if step.get("step") is not None else idx
            lines.append(f"--- Step {n} ---")
            if step.get("timestamp"):
                lines.append(f"Timestamp: {step.get('timestamp')}")
            if step.get("execution_time_ms") is not None:
                lines.append(f"Execution time: {step.get('execution_time_ms')}ms")
            if step.get("thought"):
                lines.append("Thought:")
                lines.append(str(step.get("thought")))
            if step.get("action"):
                lines.append(f"Action: {step.get('action')}")
            if step.get("action_input") is not None:
                lines.append("Action input:")
                lines.append(json.dumps(step.get("action_input"), indent=2, ensure_ascii=False, default=str))
            if step.get("observation") is not None:
                lines.append("Observation:")
                lines.append(_summarize_observation(step.get("observation"), max_lines=max_obs_lines))
            lines.append("")
    else:
        lines.append("(No reasoning steps recorded)")
        lines.append("")

    lines.append("=== Final Answer ===")
    lines.append(_to_text(trace.display_answer or trace.final_answer))
    lines.append("")

    output_payloads = trace.output_payloads if isinstance(trace.output_payloads, dict) else {}
    if output_payloads:
        lines.append("=== Output Payloads ===")
        lines.append(f"keys: {', '.join(sorted(output_payloads.keys()))}")
        lines.append(json.dumps(output_payloads, indent=2, ensure_ascii=False, default=str))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _build_json_record(review: AITraceReview) -> Dict[str, Any]:
    trace = review.trace
    return {
        "review": {
            "id": review.id,
            "status": review.status,
            "created_at": review.created_at.isoformat() if review.created_at else None,
            "assigned_at": review.assigned_at.isoformat() if review.assigned_at else None,
            "completed_at": review.completed_at.isoformat() if review.completed_at else None,
            "verdict": review.verdict,
            "reviewer_notes": review.reviewer_notes,
            "ground_truth_answer": review.ground_truth_answer,
            "trace_id": review.trace_id,
        },
        "trace": trace.to_dict(include_steps=True) if trace else None,
    }


def _iter_reviews(status: str, limit: int, offset: int) -> Iterable[AITraceReview]:
    query = (
        db.session.query(AITraceReview)
        .options(joinedload(AITraceReview.trace))
        .order_by(AITraceReview.created_at.asc())
    )
    if status != "all":
        query = query.filter(AITraceReview.status == status)
    return query.offset(offset).limit(limit).all()


def _write_output(content: str, output_path: Optional[str]) -> None:
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Wrote output to {output_path}")
    else:
        safe_content = content
        try:
            encoding = sys.stdout.encoding or "utf-8"
            safe_content = content.encode(encoding, errors="replace").decode(encoding, errors="replace")
        except Exception:
            pass
        print(safe_content, end="" if safe_content.endswith("\n") else "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trigger automated trace review packet export for offline/terminal triage."
    )
    parser.add_argument("--status", default="pending", choices=sorted(VALID_STATUSES), help="Review status filter.")
    parser.add_argument("--limit", type=int, default=10, help="Max number of reviews to export.")
    parser.add_argument("--offset", type=int, default=0, help="Offset for paging through review queue.")
    parser.add_argument("--format", default="text", choices=sorted(VALID_FORMATS), help="Output format.")
    parser.add_argument("--output", default=None, help="Optional file path to write output.")
    parser.add_argument(
        "--max-observation-lines",
        type=int,
        default=120,
        help="Max lines per step observation in text output.",
    )
    parser.add_argument(
        "--claim-in-review",
        action="store_true",
        help="Mark exported pending reviews as in_review.",
    )
    args = parser.parse_args()

    if args.limit <= 0:
        raise SystemExit("--limit must be > 0")
    if args.offset < 0:
        raise SystemExit("--offset must be >= 0")
    if args.max_observation_lines <= 0:
        raise SystemExit("--max-observation-lines must be > 0")

    app = create_app(os.getenv("FLASK_CONFIG", "development"))
    with app.app_context():
        reviews = list(_iter_reviews(args.status, args.limit, args.offset))
        if not reviews:
            msg = f"No reviews found for status='{args.status}' (limit={args.limit}, offset={args.offset}).\n"
            _write_output(msg, args.output)
            return

        if args.claim_in_review:
            for review in reviews:
                if review.status == "pending":
                    review.status = "in_review"
                    review.assigned_at = utcnow()
            db.session.commit()

        if args.format == "jsonl":
            lines = [json.dumps(_build_json_record(r), ensure_ascii=False, default=str) for r in reviews]
            payload = "\n".join(lines) + "\n"
            _write_output(payload, args.output)
            return

        blocks = [_build_text_packet(r, max_obs_lines=args.max_observation_lines) for r in reviews]
        payload = ("\n" + ("=" * 80) + "\n\n").join(blocks)
        _write_output(payload, args.output)


if __name__ == "__main__":
    main()
