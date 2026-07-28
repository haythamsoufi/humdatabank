#!/usr/bin/env python3
"""
CI guard: translations catalog is current and all .po files compile cleanly.

Two checks:

1. Staleness — extracts a fresh messages.pot from the source code (without
   touching the committed file) and compares msgids.  Fails if any msgid is
   present in the source but absent from the committed catalog, which means
   a developer added a new _() call without running
   scripts/extract_update_translations.py.

2. Compile — loads every locale .po file via polib.  Fails if any file raises
   a parse error, which would cause gettext to silently fall back to msgids at
   runtime.

Exit code 0 → all checks pass.
Exit code 1 → at least one check failed (details printed to stderr).

Usage (from Backoffice/):
    python scripts/check_translations_current.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
BACKOFFICE_DIR = CURRENT_DIR.parent.parent
BABEL_CFG = BACKOFFICE_DIR / "config" / "babel.cfg"
TRANSLATIONS_DIR = BACKOFFICE_DIR / "translations"
COMMITTED_POT = TRANSLATIONS_DIR / "messages.pot"

errors: list[str] = []


# ── Check 1: staleness ────────────────────────────────────────────────────────

def _extract_msgids_from_pot(pot_path: Path) -> set[str]:
    try:
        import polib  # type: ignore
        po = polib.pofile(str(pot_path))
        return {e.msgid for e in po if e.msgid and not getattr(e, "obsolete", False)}
    except Exception as exc:
        print(f"[translations-check] Warning: could not parse {pot_path}: {exc}", file=sys.stderr)
        return set()


def check_staleness() -> None:
    if not BABEL_CFG.exists():
        print(
            "[translations-check] babel.cfg not found — skipping staleness check",
            file=sys.stderr,
        )
        return
    if not COMMITTED_POT.exists():
        errors.append(
            "translations/messages.pot does not exist. "
            "Run: py scripts/extract_update_translations.py"
        )
        return

    with tempfile.NamedTemporaryFile(suffix=".pot", delete=False) as tmp:
        tmp_pot = Path(tmp.name)

    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "babel.messages.frontend",
                "extract",
                "-F",
                str(BABEL_CFG),
                "-o",
                str(tmp_pot),
                "--sort-output",
                ".",
            ],
            cwd=str(BACKOFFICE_DIR),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            errors.append(
                "pybabel extract failed — fix template/syntax errors before checking staleness:\n"
                f"{result.stderr or result.stdout or '(no output)'}"
            )
            return

        fresh_ids = _extract_msgids_from_pot(tmp_pot)
        committed_ids = _extract_msgids_from_pot(COMMITTED_POT)

        new_ids = fresh_ids - committed_ids
        if new_ids:
            sample = sorted(new_ids)[:10]
            more = len(new_ids) - len(sample)
            msg = (
                f"{len(new_ids)} translatable string(s) are in the source code but "
                f"missing from translations/messages.pot.\n"
                f"  Run: py scripts/extract_update_translations.py\n"
                f"  New strings (first {len(sample)}):\n"
            )
            for s in sample:
                msg += f"    • {s!r}\n"
            if more > 0:
                msg += f"    … and {more} more"
            errors.append(msg.rstrip())
    finally:
        try:
            tmp_pot.unlink()
        except OSError:
            pass


# ── Check 2: compile ──────────────────────────────────────────────────────────

def check_compile() -> None:
    try:
        import polib  # type: ignore
    except ImportError:
        errors.append(
            "polib is not installed. Run: pip install polib\n"
            "(Also check that requirements.txt includes polib.)"
        )
        return

    for po_file in sorted(TRANSLATIONS_DIR.rglob("messages.po")):
        try:
            po = polib.pofile(str(po_file))
            # Exercise the .mo serialization path — this catches encoding and
            # plural-forms errors that polib.pofile() alone may not surface.
            import io

            buf = io.BytesIO()
            po.save_as_mofile(buf)  # type: ignore[arg-type]
        except Exception as exc:
            rel = po_file.relative_to(BACKOFFICE_DIR)
            errors.append(f"PO compile error in {rel}: {exc}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print("[translations-check] Running staleness check…")
    check_staleness()

    print("[translations-check] Running compile check…")
    check_compile()

    if errors:
        print("\n[translations-check] FAILED — issues found:\n", file=sys.stderr)
        for i, err in enumerate(errors, 1):
            print(f"  [{i}] {err}\n", file=sys.stderr)
        return 1

    print("[translations-check] All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
