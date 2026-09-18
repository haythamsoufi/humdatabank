"""Shared parsing for the "Participating National Societies" (PNS) list.

UPR Planning visuals (funding requirements pages) often include a "Participating
National Societies" panel: a noisy, multi-column OCR block listing NS names,
where names suffixed with "*" are multilateral (routed through the IFRC) and
unsuffixed names are bilateral.

Both the OCR-driven visual-block extractor (``visual_chunking.py``) and the
direct document-answering fallback (``document_answering.py``) need to turn
this same noisy text into a bilateral/multilateral name list. This module holds
the single implementation so the heuristics (header detection across OCR line
splits, multi-space column splitting, "... National Red" / "Cross*" name
continuation, star-suffix bilateral/multilateral split) don't drift between the
two call sites.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

PARTICIPATING_NS_HEADER_RE = re.compile(r"^\s*participating\s+national\s+societies\s*$", re.IGNORECASE)


def parse_participating_national_societies_lines(lines: List[str]) -> Dict[str, Any]:
    """Parse a "Participating National Societies" list out of already-split OCR lines.

    ``lines`` may start well before the header (the header is searched for); scanning
    the list body stops at the first known following panel (Hazards, IFRC breakdown,
    IFRC country delegation, etc.), a "contributed ... multilateral" footnote, or the
    end of ``lines``.

    Returns ``{"bilateral": [...], "multilateral": [...], "raw": [...]}``, or ``{}``
    if no header or no names were found.
    """
    start: Optional[int] = None
    for i, ln in enumerate(lines):
        s = (ln or "").strip()
        low = s.lower()
        # Exact header line (robust to OCR double-spacing via the regex).
        if PARTICIPATING_NS_HEADER_RE.match(s):
            start = i + 1
            break
        # Header split across two lines: "Participating" / "National Societies"
        if low == "participating" and i + 1 < len(lines):
            nxt = (lines[i + 1] or "").strip().lower()
            if nxt == "national societies":
                start = i + 2
                break
        # Noisy split across columns, e.g. "IFRC network Funding ... Participating ...
        # IFRC Appeal codes" then next line contains "National Societies".
        if "participating" in low and i + 1 < len(lines):
            nxt = (lines[i + 1] or "").strip().lower()
            if "national societies" in nxt:
                start = i + 2
                break
        if "national societies" in low and i - 1 >= 0:
            prv = (lines[i - 1] or "").strip().lower()
            if "participating" in prv:
                start = i + 1
                break
    if start is None:
        return {}

    body: List[str] = []
    for ln in lines[start:]:
        s = (ln or "").strip()
        if not s:
            continue
        low = s.lower()
        if ("hazards" in low) or ("ifrc country delegation" in low):
            break
        if "national societies" in low and "contributed" in low and "multilateral" in low:
            break
        # Don't stop on "funding requirements" alone because it can appear in another
        # column while the NS list continues.
        if "ifrc" in low and "breakdown" in low:
            break
        # Skip separator-like lines (OCR sometimes produces underscores/dashes)
        if re.fullmatch(r"[-_—–]{2,}", s):
            continue
        body.append(s)

    if not body:
        return {}

    # Parse names from multi-column OCR:
    # - Split each line into "cells" by 2+ spaces
    # - Take the cell that contains "Red Cross"/"Red Crescent"
    # - Handle OCR splitting "... National Red" + "Cross*" across lines
    names_raw: List[str] = []
    pending_prefix: Optional[str] = None

    def add_name(name: str) -> None:
        nm = (name or "").strip()
        if nm:
            names_raw.append(nm)

    for line in body:
        cells = [c.strip() for c in re.split(r"\s{2,}", line) if c.strip()]
        if not cells:
            continue

        # If we have a pending "... Red" prefix, try to complete it with a "Cross" cell
        if pending_prefix:
            for c in cells:
                cl = c.lower()
                if cl in {"cross", "cross*", "crescent", "crescent*"}:
                    add_name(pending_prefix + " " + c)
                    pending_prefix = None
                    break

        for c in cells:
            cl = c.lower()
            if "mdr" in cl:
                continue
            if ("total" in cl and "chf" in cl) or ("projected funding requirements" in cl):
                continue
            if cl.startswith("emergency appeal") or cl.startswith("longer-term needs") or cl.startswith("longer term needs"):
                continue

            if ("red cross" in cl) or ("red crescent" in cl):
                add_name(c)
                continue

            # Capture split prefix like "The Republic of Korea National Red"
            if cl.endswith(" red") and ("national red" in cl or cl.endswith("national red")):
                pending_prefix = c

    if not names_raw:
        return {}

    # Normalize + de-dupe preserving order
    seen: set[str] = set()
    bilateral: List[str] = []
    multilateral: List[str] = []
    raw_out: List[str] = []
    for n in names_raw:
        n2 = (n or "").strip()
        if not n2:
            continue
        starred = n2.endswith("*")
        clean = n2[:-1].rstrip() if starred else n2
        clean = clean.rstrip(" ,.;")
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        raw_out.append(clean + ("*" if starred else ""))
        if starred:
            multilateral.append(clean)
        else:
            bilateral.append(clean)

    if not bilateral and not multilateral:
        return {}

    return {"bilateral": bilateral, "multilateral": multilateral, "raw": raw_out}
