"""
Sync denormalized indicator type/unit string columns with central lookup tables.
"""
from __future__ import annotations

from typing import Optional

from app.extensions import db
from app.models import IndicatorBank, IndicatorBankType, IndicatorBankUnit, FormItem


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
    if not unit_str or not str(unit_str).strip():
        return None
    s = str(unit_str).strip().lower()
    row = IndicatorBankUnit.query.filter(db.func.lower(IndicatorBankUnit.code) == s).first()
    if row:
        return row.id
    return None


def sync_bank_codes_from_fks(bank: IndicatorBank) -> None:
    bank.sync_type_unit_string_columns()


def backfill_fk_from_strings_bank(bank: IndicatorBank) -> None:
    if not bank.indicator_type_id and bank.type:
        tid = resolve_type_id_for_legacy_string(bank.type)
        if tid:
            bank.indicator_type_id = tid
    if not bank.indicator_unit_id and bank.unit:
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
    if not item.indicator_unit_id and item.unit:
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
    elif not item.indicator_unit_id:
        item.unit = None
