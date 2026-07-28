"""
Sync denormalized indicator type/unit string columns with central lookup tables.
"""
from __future__ import annotations

from typing import Optional

from app.extensions import db
from app.models import IndicatorBank, IndicatorBankType, IndicatorBankUnit, FormItem

# Legacy free-text + IFRC display strings that map to code ``ns`` (not equal to DB code/name).
_NS_UNIT_STRING_ALIASES = frozenset(
    {"ns", "n.s.", "n.s", "ns.", "n s", "national society"}
)


def resolve_type_id_for_legacy_string(type_str: Optional[str]) -> Optional[int]:
    if not type_str or not str(type_str).strip():
        return None
    s = str(type_str).strip().lower()
    row = IndicatorBankType.query.filter(db.func.lower(IndicatorBankType.code) == s).first()
    if row:
        return row.id
    norm = s.replace(" ", "")
    for row in IndicatorBankType.query.filter_by(is_active=True).all():
        c = (row.code or "").lower()
        if c == s or c.replace("_", "") == norm:
            return row.id
    return None


def resolve_unit_id_for_legacy_string(unit_str: Optional[str]) -> Optional[int]:
    """Map a free-text / IFRC unit string to ``indicator_bank_unit.id``.

    The remote API often sends display names (e.g. ``National Society``) while the
    catalog stores a short ``code`` (e.g. ``ns``). Match by code, by English name,
    then by known legacy abbreviations.
    """
    if not unit_str or not str(unit_str).strip():
        return None
    s = " ".join(str(unit_str).strip().lower().split())
    code_row = IndicatorBankUnit.query.filter(db.func.lower(IndicatorBankUnit.code) == s).first()
    if code_row:
        return code_row.id
    name_row = IndicatorBankUnit.query.filter(db.func.lower(IndicatorBankUnit.name) == s).first()
    if name_row:
        return name_row.id
    # Punctuation / abbreviation variants (see migration add_ns_indicator_bank_unit)
    s_alnum = "".join(c for c in s if c.isalnum())
    if s in _NS_UNIT_STRING_ALIASES or s_alnum in ("ns", "nationalsociety"):
        ns = IndicatorBankUnit.query.filter(db.func.lower(IndicatorBankUnit.code) == "ns").first()
        if ns:
            return ns.id
    return None


def sync_bank_codes_from_fks(bank: IndicatorBank) -> None:
    bank.sync_type_unit_string_columns()


def backfill_fk_from_strings_bank(bank: IndicatorBank) -> None:
    if not bank.indicator_type_id and bank.type:
        tid = resolve_type_id_for_legacy_string(bank.type)
        if tid:
            bank.indicator_type_id = tid
    # When the canonical string changes (e.g. IFRC sync), re-resolve the FK from it.
    if bank.unit:
        uid = resolve_unit_id_for_legacy_string(bank.unit)
        if uid:
            bank.indicator_unit_id = uid
    bank.sync_type_unit_string_columns()


def backfill_fk_from_strings_item(item: FormItem) -> None:
    if not item.is_indicator:
        return
    if not item.indicator_type_id and item.type:
        tid = resolve_type_id_for_legacy_string(item.type)
        if tid:
            item.indicator_type_id = tid
    if item.unit:
        uid = resolve_unit_id_for_legacy_string(item.unit)
        if uid:
            item.indicator_unit_id = uid


def sync_form_item_strings_from_fks(item: FormItem) -> None:
    if not item.is_indicator:
        return
    if item.measurement_type is not None:
        item.type = (item.measurement_type.code or "")[:50]
    if item.indicator_unit_id and item.measurement_unit is not None:
        item.unit = (item.measurement_unit.code or "")[:50]
