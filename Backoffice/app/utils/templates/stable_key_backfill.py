"""Pure helpers for sharing stable_key across template versions.

The ops backfill must give one logical field one key. A fresh UUID per row
breaks deploy-time submission remapping.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set


def lineage_order(versions: Sequence[Any]) -> List[Any]:
    """Return versions parents-first so a minted key is copied down the chain."""
    pending = list(versions)
    ordered: List[Any] = []
    while pending:
        pending_ids = {version.id for version in pending}
        ready = [
            version
            for version in pending
            if version.based_on_version_id not in pending_ids
        ]
        if not ready:
            ordered.extend(pending)
            break
        ordered.extend(ready)
        ready_ids = {version.id for version in ready}
        pending = [version for version in pending if version.id not in ready_ids]
    return ordered


def index_by_position(rows: Iterable[Any], key_fn: Callable[[Any], Any]) -> Dict[Any, Any]:
    """Index rows by position. Positions that match more than one row are omitted."""
    indexed: Dict[Any, Any] = {}
    collisions: Set[Any] = set()
    for row in rows:
        pos = key_fn(row)
        if pos in collisions or pos in indexed:
            collisions.add(pos)
            indexed.pop(pos, None)
            continue
        indexed[pos] = row
    return indexed


def align_stable_key(source: Any, target: Any, mint: Callable[[], str]) -> str:
    """Share one key between a lineage pair.

    Returns ``copied``, ``minted``, or ``unchanged``. Never overwrites a key
    that is already set to a different value.
    """
    src_key = source.stable_key or None
    tgt_key = target.stable_key or None
    if src_key and tgt_key:
        return "unchanged"
    if src_key and not tgt_key:
        target.stable_key = src_key
        return "copied"
    if tgt_key and not src_key:
        source.stable_key = tgt_key
        return "copied"
    key = mint()
    source.stable_key = key
    target.stable_key = key
    return "minted"


def shared_key_for_group(existing_keys: Iterable[Optional[str]], mint: Callable[[], str]) -> Optional[str]:
    """Pick the key for a logical group.

    One existing key is reused. No keys means mint. Several different keys
    means the group has already diverged and must be left alone.
    """
    keys = {key for key in existing_keys if key}
    if len(keys) > 1:
        return None
    if len(keys) == 1:
        return next(iter(keys))
    return mint()


def fill_null_stable_keys(
    rows_by_version: Dict[Any, Sequence[Any]],
    canonical: Optional[str],
    mint: Callable[[], str],
) -> int:
    """Set stable_key on null rows when each version has exactly one row.

    Reuses the group's single existing key. Uses ``canonical`` when every row
    is null and a canonical key was provided, otherwise mints one.
    """
    if any(len(rows) != 1 for rows in rows_by_version.values()):
        return 0
    flat = [row for rows in rows_by_version.values() for row in rows]
    if not flat:
        return 0
    existing = {row.stable_key for row in flat if row.stable_key}
    if len(existing) > 1:
        return 0
    if len(existing) == 1:
        key = next(iter(existing))
    elif canonical:
        key = canonical
    else:
        key = mint()
    updated = 0
    for row in flat:
        if not row.stable_key:
            row.stable_key = key
            updated += 1
    return updated
