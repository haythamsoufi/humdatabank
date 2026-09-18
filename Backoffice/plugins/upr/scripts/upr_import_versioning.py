"""Label-matching helpers for UPR import (no Flask dependency)."""

from __future__ import annotations

from typing import Dict, Optional


def find_item_by_label(labels: Dict[str, int], *needles: str) -> Optional[int]:
    """Resolve form item id by exact or substring label match (case-insensitive)."""
    for needle in needles:
        key = (needle or "").strip().lower()
        if not key:
            continue
        if key in labels:
            return labels[key]
    for needle in needles:
        key = (needle or "").strip().lower()
        if not key:
            continue
        for label, item_id in labels.items():
            if key in label:
                return item_id
    return None
