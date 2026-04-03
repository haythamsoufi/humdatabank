"""
Seed a low-quality AI trace review item for end-to-end queue testing.

Usage (from Backoffice):
  python scripts/seed_low_quality_review.py
  python scripts/seed_low_quality_review.py --trace-id 491
  python scripts/seed_low_quality_review.py --score 0.25 --verdict poor --reasoning "Seeded test case"
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

# Allow running as: python scripts/seed_low_quality_review.py
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app import create_app
from app.extensions import db
from app.models.embeddings import AIReasoningTrace, AITraceReview


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed a low-quality pending review trace for testing.")
    parser.add_argument("--trace-id", type=int, default=None, help="Optional existing trace ID to mark as low-quality.")
    parser.add_argument("--score", type=float, default=0.2, help="LLM quality score to set (default: 0.2).")
    parser.add_argument(
        "--verdict",
        type=str,
        default="poor",
        choices=["excellent", "good", "acceptable", "poor", "incorrect"],
        help="LLM quality verdict to set.",
    )
    parser.add_argument(
        "--reasoning",
        type=str,
        default="TEST: seeded low-quality trace for review queue validation.",
        help="Reasoning text to store on the trace.",
    )
    parser.add_argument(
        "--create-trace-if-missing",
        action="store_true",
        help="Create a synthetic trace when --trace-id is missing/not found.",
    )
    return parser.parse_args()


def _select_trace(trace_id: Optional[int]) -> Optional[AIReasoningTrace]:
    query = db.session.query(AIReasoningTrace)
    if trace_id is not None:
        return query.filter(AIReasoningTrace.id == int(trace_id)).first()
    return query.order_by(AIReasoningTrace.id.desc()).first()


def _create_synthetic_trace(preferred_id: Optional[int] = None) -> AIReasoningTrace:
    trace = AIReasoningTrace(
        id=preferred_id if preferred_id is not None else None,
        query="TEST: seeded trace for review queue validation",
        original_query="TEST: seeded trace for review queue validation",
        query_language="en",
        status="completed",
        steps=[
            {
                "step": 1,
                "thought": "Synthetic trace for test automation.",
                "action": "finish",
                "observation": {
                    "answer": "This is a synthetic test trace created for queue testing."
                },
            }
        ],
        tools_used=[],
        tool_call_count=0,
        final_answer="This is a synthetic test trace created for queue testing.",
        llm_provider="test",
        llm_model="test-model",
        execution_path="test_seed",
        output_payloads={"seeded_test_trace": True},
    )
    db.session.add(trace)
    db.session.flush()
    return trace


def main() -> None:
    args = _parse_args()
    app = create_app(os.getenv("FLASK_CONFIG", "development"))
    with app.app_context():
        trace = _select_trace(args.trace_id)
        if trace is None:
            if args.create_trace_if_missing:
                trace = _create_synthetic_trace(preferred_id=args.trace_id)
                print(f"Created synthetic trace #{trace.id} for testing.")
            else:
                raise SystemExit(
                    "No AIReasoningTrace found for the requested id. "
                    "Run at least one AI query first, or use --create-trace-if-missing."
                )

        score = max(0.0, min(1.0, float(args.score)))
        trace.llm_quality_score = score
        trace.llm_quality_verdict = args.verdict
        trace.llm_quality_reasoning = args.reasoning
        trace.llm_needs_review = True

        review = db.session.query(AITraceReview).filter(AITraceReview.trace_id == trace.id).first()
        created_review = False
        if review is None:
            review = AITraceReview(trace_id=trace.id, status="pending")
            db.session.add(review)
            created_review = True
        else:
            review.status = "pending"

        db.session.commit()

        action = "created" if created_review else "updated"
        print(
            f"OK: trace #{trace.id} marked low-quality "
            f"(score={trace.llm_quality_score}, verdict={trace.llm_quality_verdict}, needs_review={trace.llm_needs_review})."
        )
        print(f"OK: review #{review.id} {action} with status={review.status}.")
        print(f"Queue URL: /admin/ai/reviews?status=pending")


if __name__ == "__main__":
    main()
