"""Catalog hygiene: dead locales and the three UI string stores."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

# Not in Config.DEFAULT_LANGUAGES / product language list.
DEAD_GETTEXT_LOCALES = ("hu", "ja", "nl")

# gold_eval uses parents[3] = Backoffice; this file is the same depth.
BACKOFFICE_ROOT = Path(__file__).resolve().parents[3]


def dead_locale_paths() -> List[Path]:
    base = BACKOFFICE_ROOT / "translations"
    return [base / loc for loc in DEAD_GETTEXT_LOCALES if (base / loc).exists()]


def prune_dead_locales() -> List[str]:
    """Remove unused hu/ja/nl gettext trees. They are not in the product language list."""
    import shutil

    removed: List[str] = []
    for path in dead_locale_paths():
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            removed.append(str(path))
    return removed


def website_locale_status() -> Dict[str, str]:
    website = BACKOFFICE_ROOT.parent / "Website" / "public" / "locales"
    out = {}
    if not website.exists():
        return {"error": "Website locales directory missing"}
    for path in sorted(website.glob("*/common.json")):
        loc = path.parent.name
        try:
            json.loads(path.read_text(encoding="utf-8"))
            out[loc] = "ok"
        except json.JSONDecodeError as exc:
            out[loc] = f"invalid_json: {exc}"
    return out


def store_key_counts() -> Dict[str, int]:
    """Reconcile the three UI string stores by counting keys (not merging wording)."""
    counts = {}
    pot = BACKOFFICE_ROOT / "translations" / "messages.pot"
    if pot.exists():
        try:
            import polib

            counts["backoffice_pot"] = sum(1 for e in polib.pofile(str(pot)) if e.msgid and not e.obsolete)
        except Exception:
            counts["backoffice_pot"] = -1
    en_web = BACKOFFICE_ROOT.parent / "Website" / "public" / "locales" / "en" / "common.json"
    if en_web.exists():
        try:
            data = json.loads(en_web.read_text(encoding="utf-8"))

            def _count(obj):
                if isinstance(obj, dict):
                    return sum(_count(v) if isinstance(v, dict) else 1 for v in obj.values())
                return 1

            counts["website_en"] = _count(data)
        except Exception:
            counts["website_en"] = -1
    dart = BACKOFFICE_ROOT.parent / "MobileApp" / "lib" / "l10n" / "app_localizations.dart"
    if dart.exists():
        text = dart.read_text(encoding="utf-8", errors="replace")
        counts["mobile_dart_lines"] = text.count("String get ")
    return counts


def filelock_status() -> Dict[str, object]:
    """Whether PO writes are actually lock-protected in this environment.

    filelock is a hard-pinned dependency (requirements.txt), so `available`
    should always be True; False indicates the installed packages have
    drifted from requirements.txt (e.g. a stale venv/image) and concurrent
    Gunicorn workers can corrupt .po files with lost updates.
    """
    from app.utils.po_lock import filelock_protection_status

    return filelock_protection_status()


def hygiene_report() -> Dict[str, object]:
    return {
        "dead_gettext_locales": list(DEAD_GETTEXT_LOCALES),
        "dead_locale_paths_present": [str(p) for p in dead_locale_paths()],
        "website_locales": website_locale_status(),
        "store_key_counts": store_key_counts(),
        "filelock_protection": filelock_status(),
        "note": (
            "hu/ja/nl are unused by the product language list and should not be imported. "
            "Website, Backoffice gettext, and Mobile l10n remain separate stores; "
            "the shared glossary is what unifies terminology across them."
        ),
    }
