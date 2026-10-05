"""JSON snapshots of external series used by Everyone Counts.

Sources such as the World Bank revise published history. A snapshot is the
copy the analysis reads until someone refreshes it, so a later download does
not move figures that have already been read.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SNAPSHOT_DIR = Path(__file__).resolve().parents[1] / "data" / "snapshots"


def snapshot_path(name: str, directory: Path | None = None) -> Path:
    root = directory or SNAPSHOT_DIR
    safe = "".join(character for character in name if character.isalnum() or character in {"_", "-"})
    if not safe:
        raise ValueError("snapshot name is empty")
    return root / f"{safe}.json"


def load_snapshot(name: str, directory: Path | None = None) -> dict[str, Any] | None:
    path = snapshot_path(name, directory)
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        return None
    return payload


def save_snapshot(name: str, payload: dict[str, Any], directory: Path | None = None) -> Path:
    path = snapshot_path(name, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = dict(payload)
    document.setdefault("fetched_at", datetime.now(timezone.utc).isoformat())
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
    os.replace(temporary, path)
    return path
