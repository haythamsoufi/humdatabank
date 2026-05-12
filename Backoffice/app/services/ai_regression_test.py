"""
AI Regression Test Service

Runs golden Q&A pairs (sourced from completed AITraceReview records with ground_truth_answer)
against the current AI system and reports pass/fail per pair.

Designed to catch regressions when changing prompts, models, or retrieval configuration.

Usage (via CLI):
    flask ai-regression run
    flask ai-regression report --last 10

Usage (programmatic):
    from app.services.ai_regression_test import AIRegressionTestRunner
    runner = AIRegressionTestRunner()
    results = runner.run_all()
    runner.print_report(results)
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RegressionResult:
    """Result of a single golden Q&A pair evaluation."""
    review_id: int
    query: str
    ground_truth: str
    actual_answer: str
    passed: bool
    similarity_score: float  # 0.0–1.0 lexical/semantic similarity
    grounding_score: Optional[float]
    confidence_level: Optional[str]
    execution_time_ms: int
    error: Optional[str] = None
    notes: str = ""


@dataclass
class RegressionReport:
    """Aggregate report for a regression run."""
    total: int = 0
    passed: int = 0
    failed: int = 0
    errored: int = 0
    avg_similarity: float = 0.0
    avg_grounding: float = 0.0
    results: List[RegressionResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return (self.passed / self.total) if self.total > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "errored": self.errored,
            "pass_rate": round(self.pass_rate, 3),
            "avg_similarity": round(self.avg_similarity, 3),
            "avg_grounding": round(self.avg_grounding, 3),
            "results": [
                {
                    "review_id": r.review_id,
                    "query": r.query,
                    "passed": r.passed,
                    "similarity_score": r.similarity_score,
                    "grounding_score": r.grounding_score,
                    "confidence_level": r.confidence_level,
                    "execution_time_ms": r.execution_time_ms,
                    "error": r.error,
                }
                for r in self.results
            ],
        }


def _simple_token_overlap(a: str, b: str, min_length: int = 3) -> float:
    """
    Compute token overlap ratio between two texts (Jaccard on word sets).
    Used as a fast similarity proxy when no embedding is available.
    """
    def tokenize(text: str):
        return {w.lower() for w in text.split() if len(w) >= min_length}

    a_set, b_set = tokenize(a), tokenize(b)
    if not a_set or not b_set:
        return 0.0
    intersection = a_set & b_set
    union = a_set | b_set
    return len(intersection) / len(union)


class AIRegressionTestRunner:
    """
    Loads golden Q&A pairs from AITraceReview and runs them against the live AI system.
    """

    PASS_SIMILARITY_THRESHOLD = 0.35  # Jaccard overlap must exceed this to pass

    def load_golden_pairs(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Load completed reviews that have a ground_truth_answer (golden pairs)."""
        from app.models.embeddings import AITraceReview
        from app.extensions import db

        reviews = (
            db.session.query(AITraceReview)
            .join(AITraceReview.trace)
            .filter(
                AITraceReview.verdict == "correct",
                AITraceReview.ground_truth_answer.isnot(None),
                AITraceReview.ground_truth_answer != "",
            )
            .limit(limit)
            .all()
        )
        return [
            {
                "review_id": r.id,
                "query": r.trace.query if r.trace else "",
                "ground_truth": r.ground_truth_answer,
            }
            for r in reviews
            if r.trace and r.trace.query
        ]

    def run_single(self, *, query: str, ground_truth: str, review_id: int) -> RegressionResult:
        """Run one golden pair and return a RegressionResult."""
        start = time.time()
        actual_answer = ""
        grounding_score: Optional[float] = None
        confidence_level: Optional[str] = None
        error: Optional[str] = None

        try:
            from app.services.ai_agent import AIAgentExecutor
            executor = AIAgentExecutor()
            result = executor.execute(
                query=query,
                user_id=None,
                conversation_id=None,
                context={},
            )
            actual_answer = result.get("answer") or ""
            grounding_score = result.get("grounding_score")
            confidence_level = result.get("confidence_level")
        except Exception as exc:
            error = str(exc)
            logger.warning("Regression test error for review %s: %s", review_id, exc)

        elapsed = int((time.time() - start) * 1000)

        similarity = _simple_token_overlap(ground_truth, actual_answer)
        passed = bool(actual_answer) and similarity >= self.PASS_SIMILARITY_THRESHOLD and not error

        return RegressionResult(
            review_id=review_id,
            query=query,
            ground_truth=ground_truth,
            actual_answer=actual_answer,
            passed=passed,
            similarity_score=round(similarity, 3),
            grounding_score=grounding_score,
            confidence_level=confidence_level,
            execution_time_ms=elapsed,
            error=error,
        )

    def run_all(self, limit: int = 50) -> RegressionReport:
        """Run all golden pairs and produce an aggregate report."""
        pairs = self.load_golden_pairs(limit=limit)
        report = RegressionReport(total=len(pairs))

        if not pairs:
            logger.info("Regression runner: no golden pairs found. Add reviews with ground_truth_answer.")
            return report

        logger.info("Running regression tests on %d golden pairs...", len(pairs))
        similarity_sum = 0.0
        grounding_sum = 0.0
        grounding_count = 0

        for pair in pairs:
            result = self.run_single(
                query=pair["query"],
                ground_truth=pair["ground_truth"],
                review_id=pair["review_id"],
            )
            report.results.append(result)
            if result.passed:
                report.passed += 1
            elif result.error:
                report.errored += 1
            else:
                report.failed += 1
            similarity_sum += result.similarity_score
            if result.grounding_score is not None:
                grounding_sum += result.grounding_score
                grounding_count += 1

        report.avg_similarity = similarity_sum / len(pairs)
        report.avg_grounding = grounding_sum / grounding_count if grounding_count > 0 else 0.0
        return report

    @staticmethod
    def print_report(report: RegressionReport) -> None:
        """Print a human-readable regression report to stdout."""
        print("\n" + "=" * 60)
        print("  AI Regression Test Report")
        print("=" * 60)
        print(f"  Total pairs : {report.total}")
        print(f"  Passed      : {report.passed}  ({report.pass_rate:.0%})")
        print(f"  Failed      : {report.failed}")
        print(f"  Errors      : {report.errored}")
        print(f"  Avg Sim     : {report.avg_similarity:.2%}")
        print(f"  Avg Ground  : {report.avg_grounding:.2%}")
        print("=" * 60)
        if report.results:
            print(f"\n  {'ID':>5}  {'Pass':>5}  {'Sim':>5}  {'Query':<50}")
            print(f"  {'-'*5}  {'-'*5}  {'-'*5}  {'-'*50}")
            for r in report.results:
                status = "PASS" if r.passed else ("ERR " if r.error else "FAIL")
                q = (r.query[:47] + "...") if len(r.query) > 50 else r.query
                print(f"  {r.review_id:>5}  {status:>5}  {r.similarity_score:5.2f}  {q:<50}")
        print()
