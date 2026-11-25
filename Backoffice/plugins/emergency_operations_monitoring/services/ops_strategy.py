"""Draft an Emergency Appeal monitoring plan from its GO operational strategy.

An appeal has no approved plan of sectors, indicators, and activities. GO publishes
that in the appeal document whose type is ``Operational strategy`` (for example
``MDRCO036OS``). Sync stores the document. When AI drafting is on, the Databank
OpenAI provider — the same engine as the AI agent — reads the file and returns
the sectors, indicators, and activities. Those become the draft monitoring plan.
"""

from __future__ import annotations

import copy
import json
import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from plugins.emergency_operations_monitoring.constants import GO_API_ROOT, SECTOR_LABELS, SECTORS
from plugins.emergency_operations_monitoring.services.go_application import INTERVENTION_TO_SECTOR

logger = logging.getLogger(__name__)

STRATEGY_TYPE = "operational strategy"
STRATEGY_SOURCE = "operational_strategy"
_TEXT_LIMIT = 90_000
_MIN_TEXT = 400
_MAX_BYTES = 12_000_000
_MAX_SECTORS = 16
_MAX_INDICATORS = 15
_MAX_ACTIVITIES = 12
_USER_AGENT = "IFRC-Network-Databank/emergency-operations"

_LABEL_TO_KEY = {label.casefold(): key for key, label in SECTORS}
_LABEL_TO_KEY.update({key.casefold(): key for key, _label in SECTORS})
_LABEL_TO_KEY.update({key.replace("_", " ").casefold(): key for key, _label in SECTORS})
_LABEL_TO_KEY.update(INTERVENTION_TO_SECTOR)
_LABEL_TO_KEY.update(
    {
        "wash": "water_sanitation_and_hygiene",
        "shelter": "shelter_and_basic_household_items",
        "pgi": "protection_gender_and_inclusion",
        "cea": "community_engagement_and_accountability",
        "cash": "multi_purpose_cash_grants",
        "multi-purpose cash": "multi_purpose_cash_grants",
        "migration": "migration_and_displacement",
        "coordination": "coordination_and_partnerships",
        "secretariat": "secretariat_services",
        "nss": "national_society_strengthening",
        "national society strengthening": "national_society_strengthening",
    }
)

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def document_id(value) -> int | str | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        text = str(value).strip()
        return text or None


def select_strategy(documents) -> dict | None:
    """The newest operational strategy in a GO appeal-document page. Other types are ignored."""
    chosen = None
    chosen_at = ""
    for item in documents or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip().casefold() != STRATEGY_TYPE:
            continue
        url = str(item.get("document_url") or item.get("document") or "").strip()
        if not url.startswith("https://"):
            continue
        created = str(item.get("created_at") or "")[:40]
        if chosen is not None and created < chosen_at:
            continue
        chosen_at = created
        chosen = {
            "id": document_id(item.get("id")),
            "url": url,
            "name": str(item.get("name") or "")[:200],
            "created_at": created,
            "description": str(item.get("description") or "")[:200],
        }
    return chosen


def strategy_record(application) -> dict | None:
    if not isinstance(application, dict):
        return None
    raw = application.get("operational_strategy")
    if not isinstance(raw, dict) or not str(raw.get("url") or "").startswith("https://"):
        return None
    return raw


def public_strategy(baseline) -> dict | None:
    """The link shown on the plan tab. Only an https address is returned."""
    application = getattr(baseline, "application", None)
    raw = strategy_record(application)
    if raw is None:
        return None
    name = str(raw.get("name") or raw.get("description") or "").strip()
    return {"url": str(raw["url"]), "name": name}


def _results(payload) -> list:
    if isinstance(payload, dict):
        rows = payload.get("results")
        return rows if isinstance(rows, list) else []
    return payload if isinstance(payload, list) else []


def attach_strategies(rows: list[dict], http_get) -> dict:
    """Store the operational strategy address on each Emergency Appeal row. The file is not downloaded."""
    found = 0
    errors = 0
    root = GO_API_ROOT.rstrip("/")
    for row in rows:
        if not isinstance(row, dict) or not row.get("appeal_feed"):
            continue
        appeal_id = document_id(row.get("appeal_id"))
        if not isinstance(appeal_id, int):
            continue
        try:
            payload = http_get(f"{root}/appeal_document/", {"appeal": appeal_id, "limit": 100})
        except Exception as exc:
            errors += 1
            logger.info("Operational strategy lookup failed for appeal %s: %s", appeal_id, exc)
            continue
        chosen = select_strategy(_results(payload))
        if chosen is None:
            continue
        application = row.get("application")
        if not isinstance(application, dict):
            application = {
                "source": "emergency_appeal",
                "interventions": [],
                "narrative": {"source": "emergency_appeal"},
            }
            row["application"] = application
        application["operational_strategy"] = chosen
        found += 1
    if found or errors:
        logger.info("Operational strategies: %s appeal(s), %s lookup(s) failed.", found, errors)
    return {"found": found, "errors": errors}


def _extracted(strategy: dict) -> bool:
    return document_id(strategy.get("extracted_document_id")) == document_id(strategy.get("id"))


def carry_strategy_plan(latest: dict, stored) -> None:
    """Keep a plan already extracted from the same operational strategy.

    A later sync builds a fresh application with no interventions. Without this,
    that empty list would replace the drafted plan. A different document id drops
    the old extraction so the new file can be read.
    """
    if not isinstance(stored, dict):
        return
    application = latest.get("application")
    if not isinstance(application, dict):
        return
    stored_strategy = strategy_record(stored)
    new_strategy = strategy_record(application)
    if new_strategy is None and stored_strategy is not None:
        application["operational_strategy"] = dict(stored_strategy)
        if stored.get("source") == STRATEGY_SOURCE and _extracted(stored_strategy):
            application["interventions"] = copy.deepcopy(stored.get("interventions") or [])
            application["source"] = STRATEGY_SOURCE
        return
    if new_strategy is None or stored_strategy is None:
        return
    if document_id(new_strategy.get("id")) != document_id(stored_strategy.get("id")):
        return
    if stored.get("source") != STRATEGY_SOURCE or not _extracted(stored_strategy):
        return
    application["interventions"] = copy.deepcopy(stored.get("interventions") or [])
    application["source"] = STRATEGY_SOURCE
    merged = dict(new_strategy)
    merged["extracted_document_id"] = document_id(stored_strategy.get("id"))
    application["operational_strategy"] = merged


def _clip(value, limit: int) -> str:
    """Shorten text on a word boundary so a stored title is not cut mid-word."""
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(".,;:")
    return (cut or text[:limit]).strip()


def _whole(value) -> int | None:
    if isinstance(value, bool) or value is None or value == "":
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value >= 0 else None
    text = re.sub(r"[^\d.]", "", str(value))
    if not text:
        return None
    try:
        number = int(Decimal(text))
    except (InvalidOperation, ValueError, ArithmeticError):
        return None
    return number if number >= 0 else None


def sector_key(raw) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    if text in SECTOR_LABELS:
        return text
    mapped = INTERVENTION_TO_SECTOR.get(text, "")
    if mapped:
        return mapped
    return _LABEL_TO_KEY.get(text.casefold(), "")


def interventions_from_model(text: str) -> list[dict]:
    """The sectors, indicators, and activities the model returned. Empty when the reply is not usable."""
    raw = _FENCE.sub("", str(text or "").strip()).strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except ValueError:
        return []
    rows = None
    if isinstance(payload, dict):
        rows = payload.get("interventions")
        if not isinstance(rows, list):
            rows = payload.get("sectors")
    elif isinstance(payload, list):
        rows = payload
    if not isinstance(rows, list):
        return []
    found: list[dict] = []
    seen: set[str] = set()
    for item in rows:
        if len(found) >= _MAX_SECTORS or not isinstance(item, dict):
            continue
        key = sector_key(item.get("key") or item.get("sector") or item.get("title") or item.get("label"))
        label = str(item.get("label") or item.get("sector") or item.get("title") or "").strip()
        if not key:
            slug = re.sub(r"[^a-z0-9]+", "-", label.casefold()).strip("-")[:60]
            key = f"other:{slug}" if slug else ""
        if not key or key in seen:
            continue
        indicators = []
        titles: set[str] = set()
        for raw_indicator in item.get("indicators") or []:
            if len(indicators) >= _MAX_INDICATORS:
                break
            if isinstance(raw_indicator, str):
                title, target = raw_indicator, None
            elif isinstance(raw_indicator, dict):
                title, target = raw_indicator.get("title") or raw_indicator.get("name"), raw_indicator.get("target")
            else:
                continue
            title = _clip(title, 255)
            if not title or title.casefold() in titles:
                continue
            titles.add(title.casefold())
            indicators.append({"title": title, "target": _whole(target)})
        activities = []
        for line in item.get("activities") or []:
            if len(activities) >= _MAX_ACTIVITIES:
                break
            activity = _clip(line, 255)
            if activity and activity.casefold() not in {row.casefold() for row in activities}:
                activities.append(activity)
        if not indicators and not activities:
            continue
        seen.add(key)
        found.append(
            {
                "key": key,
                "label": _clip(SECTOR_LABELS.get(key) or label or key, 180),
                "budget": _whole(item.get("budget")),
                "people_targeted": _whole(item.get("people_targeted")),
                "indicators": indicators,
                "activities": activities,
            }
        )
    return found


def document_text(data: bytes) -> str:
    """Plain text of a PDF or Word operational strategy. Empty when the file is neither."""
    if not data:
        return ""
    if data[:5] == b"%PDF-":
        return _pdf_text(data)
    if data[:2] == b"PK":
        return _docx_text(data)
    return ""


def _pdf_text(data: bytes) -> str:
    try:
        import fitz
    except ImportError:
        logger.warning("PyMuPDF is not installed, so the operational strategy PDF could not be read.")
        return ""
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        logger.info("Operational strategy PDF could not be opened: %s", exc)
        return ""
    try:
        parts = []
        total = 0
        for page in document:
            piece = page.get_text("text") or ""
            parts.append(piece)
            total += len(piece)
            if total >= _TEXT_LIMIT:
                break
        return "\n".join(parts)[:_TEXT_LIMIT]
    finally:
        document.close()


def _docx_text(data: bytes) -> str:
    from io import BytesIO

    try:
        from docx import Document
    except ImportError:
        return ""
    try:
        document = Document(BytesIO(data))
    except Exception as exc:
        logger.info("Operational strategy Word file could not be opened: %s", exc)
        return ""
    lines = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    return "\n".join(lines)[:_TEXT_LIMIT]


def _bank_lines() -> str:
    try:
        from plugins.emergency_operations_monitoring.services.plans import appeal_indicator_specs

        specs = appeal_indicator_specs()
    except Exception:
        logger.debug("Indicator bank titles were not added to the strategy prompt", exc_info=True)
        return ""
    lines = []
    for spec in specs:
        names = []
        for row in spec.get("indicators") or []:
            name = str(getattr(row, "name", "") or "").strip()
            if name:
                names.append(name)
            if len(names) >= 25:
                break
        if names:
            lines.append(f"{spec['key']}: " + "; ".join(names))
    return "\n".join(lines)


def extraction_messages(operation, text: str) -> list[dict]:
    """Ask the model for the monitoring plan as one JSON object."""
    sectors = "\n".join(f"- {key}: {label}" for key, label in SECTORS)
    bank = _bank_lines() or "(none supplied)"
    system = (
        "You extract a monitoring plan from an IFRC Emergency Appeal operational strategy. "
        "Reply with one JSON object and no other text. "
        "Use only figures and actions written in the document. Do not invent budgets, targets, or activities."
    )
    user = (
        f"Appeal {operation.appeal_code}. {operation.disaster_name}. {operation.country_name}.\n"
        f"Appeal budget CHF: {operation.total_approved}. People targeted by the appeal: {operation.people_targeted}.\n\n"
        f"Sectors. Use these keys:\n{sectors}\n\n"
        "Indicator bank titles by sector. When the strategy measures the same thing, copy that title exactly. "
        f"Otherwise use the indicator as the strategy writes it:\n{bank}\n\n"
        'Return {"interventions":[{"key":"health","budget":null,"people_targeted":null,'
        '"indicators":[{"title":"...","target":null}],"activities":["..."]}]}\n'
        "Include a sector only when the strategy says this operation will work in it. "
        "budget, people_targeted, and target are integers or null. "
        f"At most {_MAX_INDICATORS} indicators and {_MAX_ACTIVITIES} activities per sector. "
        "Each activity is one short line.\n\n"
        f"Operational strategy:\n{text}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _ai_on() -> bool:
    try:
        from plugins.emergency_operations_monitoring.config_store import ai_enabled

        return bool(ai_enabled())
    except Exception:
        return False


def default_complete(messages: list[dict]) -> str:
    """One JSON reply from the Databank OpenAI provider. Empty when AI drafting is off or the call fails."""
    if not _ai_on():
        return ""
    try:
        from flask import current_app

        from app.services.ai.providers.openai_chat import OpenAIChatCompletionProvider
        from plugins.emergency_operations_monitoring.services.llm import configured_model

        api_key = current_app.config.get("OPENAI_API_KEY")
        if not api_key:
            return ""
        model = configured_model()
        provider = OpenAIChatCompletionProvider(api_key=api_key, default_model=model, timeout_sec=120)
        options: dict = {"response_format": {"type": "json_object"}}
        if model.lower().startswith("gpt-5") and "chat" not in model.lower():
            options["max_completion_tokens"] = 12000
            options["reasoning_effort"] = "low"
        elif model.lower().startswith("gpt-5"):
            options["max_completion_tokens"] = 6000
        else:
            options["max_tokens"] = 6000
        response = provider.create(messages, model=model, **options)
        return (response.choices[0].message.content or "").strip()
    except Exception:
        logger.warning("Operational strategy extraction failed", exc_info=True)
        return ""


def fetch_bytes(url: str) -> bytes:
    import requests

    if not str(url).startswith("https://"):
        raise ValueError("The operational strategy address is not a public https URL.")
    response = requests.get(
        url,
        timeout=(5, 60),
        headers={"User-Agent": _USER_AGENT},
    )
    response.raise_for_status()
    return response.content[:_MAX_BYTES]


def _untouched(operation, plan, baseline) -> bool:
    """True when nobody has edited this draft, so a strategy draft may replace it."""
    from plugins.emergency_operations_monitoring.services.plans import (
        groups_for,
        indicators_for_group,
        plan_can_take_strategy,
        plan_matches_sync,
    )

    if not plan_can_take_strategy(plan):
        return False
    if plan is None:
        return True
    if not plan_matches_sync(plan, operation, baseline):
        return False
    for group in groups_for(plan.id):
        for row in indicators_for_group(group.id):
            if row.enabled is False:
                return False
    return True


def draft_plan_from_strategy(
    operation,
    *,
    fetch=None,
    read_text=None,
    complete=None,
    today: date | None = None,
    force: bool = False,
) -> dict:
    """Read the operational strategy and replace the draft monitoring plan with what it contains.

    ``force`` is the button on the plan tab. The sync only drafts a plan nobody has edited.
    """
    from app.extensions import db
    from plugins.emergency_operations_monitoring.services.go_parse import is_emergency_appeal
    from plugins.emergency_operations_monitoring.services.plans import (
        latest_baseline,
        latest_plan,
        plan_can_take_strategy,
        replace_plan_with_interventions,
    )

    if not is_emergency_appeal(operation.appeal_type or ""):
        return {"ok": False, "error": "Only an Emergency Appeal is drafted from an operational strategy."}
    baseline = latest_baseline(operation.id)
    application = baseline.application if baseline is not None and isinstance(baseline.application, dict) else None
    strategy = strategy_record(application)
    if strategy is None:
        return {"ok": False, "error": "GO has not published an operational strategy for this appeal."}
    plan = latest_plan(operation.id)
    if not force and not _untouched(operation, plan, baseline):
        return {"ok": False, "error": "This plan was edited or confirmed, so it was left as it is."}
    if force and not plan_can_take_strategy(plan):
        return {"ok": False, "error": "This plan was edited or confirmed, so it was left as it is."}
    if complete is None and not _ai_on():
        return {
            "ok": False,
            "error": "Turn on AI draft reports before drafting a plan from the operational strategy.",
        }
    try:
        data = (fetch or fetch_bytes)(strategy["url"])
        text = (read_text or document_text)(data)
    except Exception:
        logger.info("Operational strategy download failed for %s", operation.appeal_code, exc_info=True)
        return {"ok": False, "error": "The operational strategy could not be read."}
    if len(str(text or "").strip()) < _MIN_TEXT:
        return {"ok": False, "error": "The operational strategy could not be read."}
    reply = (complete or default_complete)(extraction_messages(operation, text))
    interventions = interventions_from_model(reply)
    if not interventions:
        return {"ok": False, "error": "The operational strategy did not yield a monitoring plan."}
    updated = dict(application)
    updated["interventions"] = interventions
    updated["source"] = STRATEGY_SOURCE
    stored = dict(strategy)
    stored["extracted_document_id"] = document_id(strategy.get("id"))
    updated["operational_strategy"] = stored
    baseline.application = updated
    try:
        outcome = replace_plan_with_interventions(operation, baseline, today or date.today())
        if outcome in {"kept", "empty"}:
            db.session.rollback()
            return {"ok": False, "error": "This plan was edited or confirmed, so it was left as it is."}
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.warning("Operational strategy plan could not be saved for %s", operation.appeal_code, exc_info=True)
        return {"ok": False, "error": "The monitoring plan could not be drafted from the operational strategy."}
    return {"ok": True, "sectors": len(interventions)}


def draft_pending_strategies(*, fetch=None, read_text=None, complete=None, should_stop=None, progress=None) -> int:
    """Draft plans for appeals whose operational strategy has not been read, when AI drafting is on."""
    if complete is None and not _ai_on():
        return 0
    from plugins.emergency_operations_monitoring.models import DrefOperation
    from plugins.emergency_operations_monitoring.services.go_parse import is_emergency_appeal
    from plugins.emergency_operations_monitoring.services.plans import latest_baseline, latest_plan

    pending = []
    for operation in DrefOperation.query.all():
        if not is_emergency_appeal(operation.appeal_type or ""):
            continue
        baseline = latest_baseline(operation.id)
        application = baseline.application if baseline is not None and isinstance(baseline.application, dict) else None
        strategy = strategy_record(application)
        if strategy is None or _extracted(strategy):
            continue
        plan = latest_plan(operation.id)
        if not _untouched(operation, plan, baseline):
            continue
        pending.append(operation)
    drafted = 0
    total = len(pending)
    for index, operation in enumerate(pending, start=1):
        if should_stop and should_stop():
            from plugins.emergency_operations_monitoring.services.go_sync import GoSyncCancelled

            raise GoSyncCancelled()
        if progress:
            progress(
                {
                    "stage": "strategy",
                    "message": "Drafting monitoring plans from operational strategies (%(current)s of %(total)s).",
                    "message_vars": {"current": index, "total": total},
                    "current": index,
                    "total": total,
                    "percent": round(95 + 4 * index / total, 1) if total else 99,
                }
            )
        result = draft_plan_from_strategy(
            operation, fetch=fetch, read_text=read_text, complete=complete, force=False
        )
        if result.get("ok"):
            drafted += 1
        else:
            logger.info(
                "Operational strategy was not drafted for %s: %s",
                operation.appeal_code,
                result.get("error"),
            )
    return drafted
