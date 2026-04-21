"""
CLI commands for AI regression testing.

Usage:
    flask ai-regression run [--limit N]
    flask ai-regression report
    flask ai-regression golden-pairs
"""

import click
import json
from flask.cli import with_appcontext


@click.group("ai-regression")
def ai_regression_cli():
    """AI regression testing commands."""
    pass


@ai_regression_cli.command("run")
@click.option("--limit", default=50, show_default=True, help="Max golden pairs to run.")
@click.option("--output", default=None, help="Write JSON report to this file path.")
@with_appcontext
def run_regression(limit: int, output):
    """Run regression tests against golden Q&A pairs and print a report."""
    from app.services.ai_regression_test import AIRegressionTestRunner

    click.echo(f"Running regression tests (limit={limit})...")
    runner = AIRegressionTestRunner()
    report = runner.run_all(limit=limit)
    runner.print_report(report)

    if output:
        import os
        with open(output, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        click.echo(f"Report written to {os.path.abspath(output)}")

    # Exit with non-zero if any tests failed (useful for CI)
    if report.failed > 0 or report.errored > 0:
        raise SystemExit(1)


@ai_regression_cli.command("golden-pairs")
@with_appcontext
def list_golden_pairs():
    """List all available golden Q&A pairs."""
    from app.services.ai_regression_test import AIRegressionTestRunner

    runner = AIRegressionTestRunner()
    pairs = runner.load_golden_pairs(limit=500)
    if not pairs:
        click.echo("No golden pairs found. Complete some trace reviews with ground_truth_answer.")
        return

    click.echo(f"\nFound {len(pairs)} golden pair(s):\n")
    for p in pairs:
        q = (p["query"][:70] + "...") if len(p["query"]) > 73 else p["query"]
        click.echo(f"  Review #{p['review_id']:>4}: {q}")
    click.echo()


@ai_regression_cli.command("report")
@click.option("--last", default=20, show_default=True, help="Show last N regression results from DB.")
@with_appcontext
def show_report(last: int):
    """Show a summary of recent AI quality metrics from stored traces."""
    from app.extensions import db
    from app.models.embeddings import AIReasoningTrace
    from sqlalchemy import func

    traces = (
        db.session.query(AIReasoningTrace)
        .filter(AIReasoningTrace.grounding_score.isnot(None))
        .order_by(AIReasoningTrace.created_at.desc())
        .limit(last)
        .all()
    )

    if not traces:
        click.echo("No grounded traces found yet. Run some queries to populate.")
        return

    avg_grounding = sum(t.grounding_score for t in traces) / len(traces)
    high = sum(1 for t in traces if t.confidence_level == "high")
    medium = sum(1 for t in traces if t.confidence_level == "medium")
    low = sum(1 for t in traces if t.confidence_level == "low")
    likes = sum(1 for t in traces if t.user_rating == "like")
    dislikes = sum(1 for t in traces if t.user_rating == "dislike")

    click.echo(f"\nAI Quality Report (last {last} grounded traces)")
    click.echo("=" * 50)
    click.echo(f"  Avg grounding score : {avg_grounding:.2%}")
    click.echo(f"  Confidence — High   : {high}")
    click.echo(f"  Confidence — Medium : {medium}")
    click.echo(f"  Confidence — Low    : {low}")
    click.echo(f"  User likes          : {likes}")
    click.echo(f"  User dislikes       : {dislikes}")
    click.echo()
