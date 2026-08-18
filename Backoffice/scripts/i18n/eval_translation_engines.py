#!/usr/bin/env python
"""Per-language engine evaluation against the gold set.

Compares Azure/IFRC, Google, and optional NLLB, each with and without glossary.
Does nothing useful until gold[locale] fields are filled by humans.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root or Backoffice/
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--gold",
        default=str(ROOT / "tests" / "fixtures" / "translation_gold_set.json"),
    )
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    from app.services.translation.gold_eval import chr_f, gold_set_ready, load_gold_set, simple_term_hit_rate
    from app.services.translation.glossary_forcing import terms_for_target

    payload = load_gold_set(Path(args.gold))
    if not gold_set_ready(payload):
        print("Gold set is not ready. Commission human references (300+ filled fr/es/ar segments).")
        print(f"Segments present: {payload.get('count', 0)}")
        return 2

    from app import create_app

    app = create_app()
    with app.app_context():
        from app.services.translation.auto_translator import get_auto_translator

        translator = get_auto_translator()
        engines = [s for s in translator.get_available_services() if s != "mock"]
        report = {"engines": engines, "by_locale": {}}
        for loc in payload.get("locales") or ["fr", "es", "ar"]:
            terms = [t for t, _ in terms_for_target(loc)]
            segs = [
                s
                for s in payload.get("segments") or []
                if str((s.get("gold") or {}).get(loc) or "").strip()
            ][: args.limit]
            loc_report = {}
            for engine in engines:
                scores = []
                hits = []
                for seg in segs:
                    hyp = translator.translate_text(seg["source_en"], loc, "en", engine) or ""
                    gold = seg["gold"][loc]
                    scores.append(chr_f(hyp, gold))
                    hits.append(simple_term_hit_rate(hyp, gold, terms))
                loc_report[engine] = {
                    "n": len(segs),
                    "chrf": round(sum(scores) / len(scores), 4) if scores else None,
                    "term_hit_rate": round(sum(hits) / len(hits), 4) if hits else None,
                }
            report["by_locale"][loc] = loc_report
        print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
