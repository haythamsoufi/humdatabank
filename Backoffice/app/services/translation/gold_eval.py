"""Sample and evaluate a human gold reference set (gating artifact)."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Dict, List


GOLD_LOCALES = ("fr", "es", "ar")
DEFAULT_FIXTURE = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "translation_gold_set.json"


def sample_gold_set(*, per_locale: int = 400) -> Dict[str, Any]:
    """Build a commissioning file: English source + empty gold fields for humans."""
    from flask import current_app

    from app.routes.admin.utilities.helpers import _translations_po_path

    try:
        import polib
    except ImportError:
        return {"count": 0, "locales": list(GOLD_LOCALES), "segments": [], "error": "polib missing"}

    en_path = _translations_po_path("en")
    msgids: List[str] = []
    if en_path and Path(en_path).exists():
        po = polib.pofile(en_path)
        for entry in po:
            if entry.msgid and not entry.obsolete:
                msgids.append(entry.msgid)

    # Mix short UI labels with longer definition-like strings.
    short = [m for m in msgids if 1 <= len(m.split()) <= 6]
    long = [m for m in msgids if len(m.split()) >= 7]
    rng = random.Random(2030)
    picked = []
    half = max(1, per_locale // 2)
    picked.extend(rng.sample(short, min(half, len(short))) if short else [])
    picked.extend(rng.sample(long, min(per_locale - len(picked), len(long))) if long else [])
    if len(picked) < per_locale and msgids:
        extra = [m for m in msgids if m not in picked]
        picked.extend(rng.sample(extra, min(per_locale - len(picked), len(extra))))

    segments = []
    for msgid in picked[:per_locale]:
        segments.append(
            {
                "msgid": msgid,
                "source_en": msgid,
                "gold": {loc: "" for loc in GOLD_LOCALES},
                "domain": "ui" if len(msgid.split()) <= 6 else "prose",
                "status": "needs_human",
            }
        )

    return {
        "version": 1,
        "count": len(segments),
        "locales": list(GOLD_LOCALES),
        "commissioning_note": (
            "Commission professional translators for fr, es, and ar. "
            "Fill gold[locale] only. Do not copy machine output. "
            "This file gates every engine-quality claim."
        ),
        "app_languages": list(current_app.config.get("SUPPORTED_LANGUAGES") or []),
        "segments": segments,
    }


def load_gold_set(path: Path | None = None) -> Dict[str, Any]:
    p = path or DEFAULT_FIXTURE
    if not p.exists():
        return {"count": 0, "segments": [], "locales": list(GOLD_LOCALES)}
    return json.loads(p.read_text(encoding="utf-8"))


def gold_set_ready(payload: Dict[str, Any] | None = None) -> bool:
    data = payload or load_gold_set()
    segs = data.get("segments") or []
    if len(segs) < 300:
        return False
    filled = 0
    for seg in segs:
        gold = seg.get("gold") or {}
        if all(str(gold.get(loc) or "").strip() for loc in GOLD_LOCALES):
            filled += 1
    return filled >= 300


def chr_f(hyp: str, ref: str) -> float:
    """Tiny chrF-like character n-gram F score (n=3) for offline use."""

    def ngrams(s, n=3):
        s = (s or "").lower()
        return {s[i : i + n] for i in range(max(0, len(s) - n + 1))} or {s}

    h, r = ngrams(hyp), ngrams(ref)
    if not h or not r:
        return 0.0
    overlap = len(h & r)
    prec = overlap / len(h)
    rec = overlap / len(r)
    if prec + rec == 0:
        return 0.0
    return 2 * prec * rec / (prec + rec)


def simple_term_hit_rate(hypothesis: str, gold: str, terms: List[str]) -> float:
    if not terms:
        return 1.0
    hits = 0
    hay_h = (hypothesis or "").lower()
    hay_g = (gold or "").lower()
    relevant = [t for t in terms if t.lower() in hay_g]
    if not relevant:
        return 1.0
    for t in relevant:
        if t.lower() in hay_h:
            hits += 1
    return hits / len(relevant)
