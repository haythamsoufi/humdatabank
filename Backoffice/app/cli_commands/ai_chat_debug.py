"""
CLI for debugging chatbot prompts locally (same agent path as the UI).

Usage:
    flask ai-chat ask "Volunteers in Syria over time"
    flask ai-chat convo -m "Volunteers in Syria over time" -m "look in the available documents for context behind the number changes" -m "what documents did you check"
    flask ai-chat scenario scripts/ai/scenarios/syria-volunteers.json
    flask ai-chat interactive
    flask ai-chat show-trace 597
    flask ai-chat --help

Related: ``flask ai-regression`` scores golden Q&A pairs from completed reviews.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional

import click
from flask.cli import with_appcontext


@click.group("ai-chat")
def ai_chat_cli():
    """Send prompts through the live AI chat engine and inspect responses/traces."""
    pass


def _common_options(fn):
    fn = click.option(
        "--user", "user_spec", default=None,
        help="User email, local-part, or preset: admin | sys | focal (default: test_admin).",
    )(fn)
    fn = click.option("--language", default="en", show_default=True, help="Preferred reply language.")(fn)
    fn = click.option("--json-out", "json_out", default=None, type=click.Path(), help="Write full result JSON to this path.")(fn)
    fn = click.option("--as-json", "as_json", is_flag=True, help="Print JSON to stdout instead of human text.")(fn)
    fn = click.option("--no-agent", is_flag=True, help="Disable the agent (direct LLM path).")(fn)
    fn = click.option("--quiet-steps", is_flag=True, help="Do not stream progress step lines.")(fn)
    return fn


def _print_turn(turn, *, verbose: bool = True) -> None:
    click.echo("")
    click.secho(f"=== Turn {turn.index} ===", fg="cyan", bold=True)
    click.echo(f"Prompt : {turn.prompt}")
    click.echo(
        f"Status : {'OK' if turn.success else 'FAIL'}"
        f" | model={turn.model or '?'} | {turn.elapsed_ms or '?'}ms"
        f" | trace_id={turn.trace_id or 'n/a'}"
    )
    if turn.tools_used:
        click.echo(f"Tools  : {', '.join(turn.tools_used)}")
    else:
        click.echo("Tools  : (none)")
    if turn.failed_tools:
        click.secho("Failed tools:", fg="red")
        for f in turn.failed_tools:
            click.echo(
                f"  - {f.get('tool')}: {f.get('error_type')}"
                + (f" caused by {f.get('error_cause_type')}" if f.get("error_cause_type") else "")
                + (f" — {f.get('error')}" if f.get("error") else "")
            )
    extras = []
    if turn.has_chart:
        extras.append("chart")
    if turn.has_map:
        extras.append("map")
    if turn.has_table:
        extras.append("table")
    if turn.confidence:
        extras.append(f"confidence={turn.confidence}")
    if turn.grounding_score is not None:
        extras.append(f"grounding={turn.grounding_score:.2f}")
    if turn.llm_quality_verdict:
        score = f"{turn.llm_quality_score:.0%}" if turn.llm_quality_score is not None else "?"
        extras.append(f"quality={score} ({turn.llm_quality_verdict})")
    if extras:
        click.echo("Meta   : " + " | ".join(extras))
    click.secho("--- Answer ---", fg="green")
    click.echo(turn.answer_text or "(empty)")
    if verbose and turn.tool_digest:
        click.secho("--- Tool digest (fed into next-turn history) ---", fg="yellow")
        click.echo(turn.tool_digest)


def _emit_result(result, *, as_json: bool, json_out: Optional[str], verbose: bool = True) -> None:
    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        click.echo(f"Conversation: {result.conversation_id}")
        click.echo(f"User        : {result.user_email}")
        for turn in result.turns:
            _print_turn(turn, verbose=verbose)
        click.echo("")
    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
        click.echo(f"Wrote {json_out}", err=True)


def _make_runner(user_spec, language, no_agent, quiet_steps):
    from app.services.ai.runtime.chat_debug_runner import ChatDebugRunner

    def on_step(msg, detail=None):
        if quiet_steps:
            return
        line = (msg or "").strip()
        if detail:
            line = f"{line} — {detail}"
        click.echo(f"  · {line}", err=True)

    return ChatDebugRunner(
        user_spec=user_spec,
        language=language,
        enable_agent=not no_agent,
        on_step=None if quiet_steps else on_step,
    )


@ai_chat_cli.command("ask")
@click.argument("prompt")
@_common_options
@with_appcontext
def ask_cmd(prompt, user_spec, language, json_out, as_json, no_agent, quiet_steps):
    """Send a single prompt and print the answer + tool summary."""
    runner = _make_runner(user_spec, language, no_agent, quiet_steps)
    result = runner.run_prompts([prompt])
    _emit_result(result, as_json=as_json, json_out=json_out)


@ai_chat_cli.command("convo")
@click.option("-m", "--message", "messages", multiple=True, required=True, help="Prompt (repeatable, in order).")
@_common_options
@with_appcontext
def convo_cmd(messages, user_spec, language, json_out, as_json, no_agent, quiet_steps):
    """Run a multi-turn conversation (each -m is a user turn)."""
    runner = _make_runner(user_spec, language, no_agent, quiet_steps)
    result = runner.run_prompts(list(messages))
    _emit_result(result, as_json=as_json, json_out=json_out)


@ai_chat_cli.command("scenario")
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@_common_options
@with_appcontext
def scenario_cmd(path, user_spec, language, json_out, as_json, no_agent, quiet_steps):
    """Run prompts from a JSON scenario file (list, or {prompts|turns})."""
    from app.services.ai.runtime.chat_debug_runner import load_scenario

    prompts = load_scenario(path)
    click.echo(f"Loaded {len(prompts)} prompt(s) from {path}", err=True)
    runner = _make_runner(user_spec, language, no_agent, quiet_steps)
    result = runner.run_prompts(prompts)
    _emit_result(result, as_json=as_json, json_out=json_out)


@ai_chat_cli.command("interactive")
@_common_options
@with_appcontext
def interactive_cmd(user_spec, language, json_out, as_json, no_agent, quiet_steps):
    """Interactive REPL. Empty line or /quit to exit. /trace prints last trace id."""
    runner = _make_runner(user_spec, language, no_agent, quiet_steps)
    click.echo(f"AI chat REPL as {runner.user_email} (conversation {runner.conversation_id})")
    click.echo("Type a prompt, or /quit. Commands: /trace  /json  /help")
    last_result = None
    turns_for_dump: List[Any] = []
    while True:
        try:
            line = click.prompt("you", prompt_suffix="> ", default="", show_default=False)
        except (EOFError, KeyboardInterrupt):
            click.echo("")
            break
        cmd = (line or "").strip()
        if not cmd or cmd in {"/q", "/quit", "/exit"}:
            break
        if cmd == "/help":
            click.echo("  /quit  end session\n  /trace show last trace_id\n  /json  print last turn as JSON")
            continue
        if cmd == "/trace":
            click.echo(f"last trace_id={getattr(last_result, 'trace_id', None)}")
            continue
        if cmd == "/json":
            if last_result is None:
                click.echo("(no turns yet)")
            else:
                click.echo(json.dumps(last_result.to_dict(), indent=2, ensure_ascii=False))
            continue
        try:
            last_result = runner.run_turn(cmd)
            turns_for_dump.append(last_result)
            if as_json:
                click.echo(json.dumps(last_result.to_dict(), indent=2, ensure_ascii=False))
            else:
                _print_turn(last_result)
        except Exception as exc:
            click.secho(f"Error: {exc}", fg="red", err=True)
    if json_out and turns_for_dump:
        payload = {
            "conversation_id": runner.conversation_id,
            "user_email": runner.user_email,
            "turns": [t.to_dict() for t in turns_for_dump],
        }
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        click.echo(f"Wrote {json_out}", err=True)


@ai_chat_cli.command("show-trace")
@click.argument("trace_id", type=int)
@click.option("--full", is_flag=True, help="Include full observation JSON (can be large).")
@click.option("--as-json", "as_json", is_flag=True, help="Print the whole trace row as JSON.")
@with_appcontext
def show_trace_cmd(trace_id: int, full: bool, as_json: bool):
    """Inspect a stored AIReasoningTrace (tools, failures, final answer)."""
    from app.models.embeddings import AIReasoningTrace
    from app.extensions import db
    from app.services.ai.runtime.chat_debug_runner import html_to_text, summarize_trace_steps

    trace = db.session.get(AIReasoningTrace, trace_id)
    if trace is None:
        raise click.ClickException(f"Trace #{trace_id} not found")

    steps = trace.steps if isinstance(trace.steps, list) else []
    summary = summarize_trace_steps(steps)
    answer = html_to_text(trace.final_answer or "") if getattr(trace, "final_answer", None) else ""

    if as_json:
        payload: Dict[str, Any] = {
            "id": trace.id,
            "status": str(getattr(trace.status, "value", trace.status)),
            "query": trace.query,
            "original_query": getattr(trace, "original_query", None),
            "model": getattr(trace, "model_name", None) or getattr(trace, "model", None),
            "execution_path": getattr(trace, "execution_path", None) or getattr(trace, "agent_mode", None),
            "grounding_score": getattr(trace, "grounding_score", None),
            "confidence_level": getattr(trace, "confidence_level", None),
            "llm_quality_score": getattr(trace, "llm_quality_score", None),
            "llm_quality_verdict": getattr(trace, "llm_quality_verdict", None),
            "tools_used": summary["tools_used"],
            "failed_tools": summary["failed_tools"],
            "tool_digest": summary["tool_digest"],
            "final_answer": answer,
            "steps": steps if full else [
                {
                    "step": s.get("step"),
                    "action": s.get("action"),
                    "action_input": s.get("action_input"),
                    "thought": s.get("thought"),
                    "success": (s.get("observation") or {}).get("success")
                    if isinstance(s.get("observation"), dict) else None,
                    "error": (s.get("observation") or {}).get("error")
                    if isinstance(s.get("observation"), dict) else None,
                    "error_type": (s.get("observation") or {}).get("error_type")
                    if isinstance(s.get("observation"), dict) else None,
                }
                for s in steps
            ],
        }
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return

    click.secho(f"=== AI Trace #{trace.id} ===", fg="cyan", bold=True)
    click.echo(f"Status : {getattr(trace.status, 'value', trace.status)}")
    click.echo(f"Query  : {trace.query}")
    if getattr(trace, "original_query", None) and trace.original_query != trace.query:
        click.echo(f"Orig   : {trace.original_query}")
    click.echo(f"Path   : {getattr(trace, 'execution_path', None) or getattr(trace, 'agent_mode', None)}")
    click.echo(f"Tools  : {', '.join(summary['tools_used']) or '(none)'}")
    if summary["failed_tools"]:
        click.secho("Failed :", fg="red")
        for f in summary["failed_tools"]:
            click.echo(f"  - {f}")
    click.echo(f"Grounding: {getattr(trace, 'grounding_score', None)} ({getattr(trace, 'confidence_level', None)})")
    click.echo(
        f"Quality  : {getattr(trace, 'llm_quality_score', None)} "
        f"({getattr(trace, 'llm_quality_verdict', None)})"
    )
    click.secho("--- Steps ---", fg="yellow")
    for s in steps:
        action = s.get("action")
        obs = s.get("observation")
        flag = ""
        if isinstance(obs, dict) and (obs.get("success") is False or obs.get("error")):
            flag = click.style(" FAIL", fg="red")
        click.echo(f"  {s.get('step')}. {action}{flag}")
        if s.get("action_input"):
            click.echo(f"     in : {json.dumps(s.get('action_input'), ensure_ascii=False)[:240]}")
        if full and obs is not None:
            click.echo(f"     out: {json.dumps(obs, ensure_ascii=False, default=str)[:800]}")
        elif isinstance(obs, dict) and obs.get("error"):
            click.echo(f"     err: {obs.get('error_type')}: {obs.get('error')}")
    if summary["tool_digest"]:
        click.secho("--- Digest ---", fg="yellow")
        click.echo(summary["tool_digest"])
    click.secho("--- Final answer ---", fg="green")
    click.echo(answer or "(empty)")


def register_ai_chat_commands(app):
    app.cli.add_command(ai_chat_cli)
