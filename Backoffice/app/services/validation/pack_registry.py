"""Registry of template validation packs contributed by plugins.

Core dashboard, question, and dispatch code looks packs up here. A missing or
inactive plugin leaves the registry without that pack, and checks for it return
nothing instead of failing the page.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from app.services.validation.types import CheckResult

logger = logging.getLogger(__name__)

CheckRunner = Callable[[Any], list[CheckResult]]
SuffixFormatter = Callable[[str, dict], str]


@dataclass(frozen=True)
class ValidationPack:
    """One product's automatic checks, rule metadata, and optional dashboard extras."""

    code: str
    label: str
    run_checks: CheckRunner
    rules: tuple[Any, ...]
    format_suffix: SuffixFormatter | None = None
    threshold_kpi_codes: tuple[str, ...] = ()
    # Indicator codes the core missing-data check treats as required for this product.
    required_indicator_codes: tuple[str, ...] = ()
    # "fdrs" draws governance/finance/reach and FDRS document columns on the tracker.
    tracker_id: str | None = None


_PACKS: dict[str, ValidationPack] = {}
_manager_synced = False


def register_pack(pack: ValidationPack) -> None:
    """Register or replace a pack. Repeated calls for the same code are safe."""
    _PACKS[pack.code] = pack


def unregister_pack(code: str) -> None:
    _PACKS.pop(code, None)


def get_pack(code: str | None) -> ValidationPack | None:
    if not code:
        return None
    ensure_validation_packs()
    return _PACKS.get(code)


def list_packs() -> list[ValidationPack]:
    ensure_validation_packs()
    return [_PACKS[code] for code in sorted(_PACKS)]


def mark_synced_from_plugins() -> None:
    """Plugin manager has already registered every active plugin's packs."""
    global _manager_synced
    _manager_synced = True


def ensure_validation_packs() -> None:
    """Load the core pack, then plugin packs.

    Unit tests and scripts often call validation services without booting the
    plugin manager. In a running app the manager syncs active plugins first and
    this function does not import inactive ones. The general checks pack is
    always registered.
    """
    from app.utils.data_quality_constants import RULE_PACK_CORE

    if RULE_PACK_CORE not in _PACKS:
        from app.services.validation.core_checks import register_core_validation_pack

        register_core_validation_pack()
    if _manager_synced or any(code != RULE_PACK_CORE for code in _PACKS):
        return
    try:
        from plugins.fdrs.validation.register import register_fdrs_validation_pack

        register_fdrs_validation_pack()
    except Exception:
        logger.debug("FDRS validation pack was not registered", exc_info=True)


def reset_validation_packs_for_tests() -> None:
    """Clear registry state. Tests that boot the plugin manager should not need this."""
    global _manager_synced
    _PACKS.clear()
    _manager_synced = False
