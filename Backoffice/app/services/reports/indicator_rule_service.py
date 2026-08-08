"""Resolve Indicator Bank rows from report builder rules (dynamic, not stored IDs)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Country, IndicatorBank


def _normalize_rule(rule: dict[str, Any] | None) -> dict[str, Any]:
    rule = rule or {}
    return {
        "related_programs_any": [str(v).strip() for v in (rule.get("related_programs_any") or []) if str(v).strip()],
        "tags_any": [str(v).strip() for v in (rule.get("tags_any") or []) if str(v).strip()],
        "spef_codes_any": [str(v).strip().upper() for v in (rule.get("spef_codes_any") or []) if str(v).strip()],
        "emergency": rule.get("emergency") if rule.get("emergency") is not None else None,
        "search_text": (rule.get("search_text") or "").strip(),
        "sort_by": (rule.get("sort_by") or "name").strip(),
        "sort_direction": (rule.get("sort_direction") or "asc").strip().lower(),
        "limit": rule.get("limit"),
        "any": rule.get("any") or [],
        "all": rule.get("all") or [],
        "none": rule.get("none") or [],
    }


def _programme_match_clause(programmes: list[str]):
    dialect = db.session.bind.dialect.name if db.session.bind else ""
    if dialect == "postgresql":
        return or_(
            *[
                IndicatorBank._related_programs_list.contains([programme])  # type: ignore[attr-defined]
                for programme in programmes
            ]
        )
    return None


def _tag_match_clause(tags: list[str]):
    dialect = db.session.bind.dialect.name if db.session.bind else ""
    if dialect == "postgresql":
        return or_(*[IndicatorBank.tags.contains([tag]) for tag in tags])  # type: ignore[attr-defined]
    return None


def build_indicator_rule_query(rule: dict[str, Any] | None):
    """Return a SQLAlchemy query for active indicators matching the rule."""
    normalized = _normalize_rule(rule)
    query = IndicatorBank.query.filter(IndicatorBank.archived.isnot(True))

    if normalized["emergency"] is not None:
        query = query.filter(IndicatorBank.emergency.is_(bool(normalized["emergency"])))

    if normalized["spef_codes_any"]:
        from app.models.indicator_bank import IndicatorBankSpef

        query = query.join(IndicatorBankSpef, IndicatorBank.indicator_spef_id == IndicatorBankSpef.id).filter(
            func.upper(IndicatorBankSpef.code).in_(normalized["spef_codes_any"])
        )

    if normalized["search_text"]:
        like = f"%{normalized['search_text']}%"
        query = query.filter(or_(IndicatorBank.name.ilike(like), IndicatorBank.definition.ilike(like)))

    programmes = normalized["related_programs_any"]
    tags = normalized["tags_any"]
    programme_clause = _programme_match_clause(programmes) if programmes else None
    tag_clause = _tag_match_clause(tags) if tags else None

    if programme_clause is not None and tag_clause is not None:
        query = query.filter(or_(programme_clause, tag_clause))
    elif programme_clause is not None:
        query = query.filter(programme_clause)
    elif tag_clause is not None:
        query = query.filter(tag_clause)

    sort_by = normalized["sort_by"]
    direction = normalized["sort_direction"]
    if sort_by == "updated_at":
        col = IndicatorBank.updated_at
    elif sort_by == "spef_code":
        col = IndicatorBank.area
    else:
        col = IndicatorBank.name
    query = query.order_by(col.desc() if direction == "desc" else col.asc())
    return query.options(joinedload(IndicatorBank.spef_area))


def _python_filter_rows(rows: list[IndicatorBank], rule: dict[str, Any] | None) -> list[IndicatorBank]:
    normalized = _normalize_rule(rule)
    programmes = set(normalized["related_programs_any"])
    tags = set(normalized["tags_any"])
    spef_codes = set(normalized["spef_codes_any"])
    search = normalized["search_text"].lower()

    def matches(row: IndicatorBank) -> bool:
        if normalized["emergency"] is not None and bool(row.emergency) != bool(normalized["emergency"]):
            return False
        if spef_codes:
            code = ((row.spef_area.code if row.spef_area else None) or row.area or "").upper()
            if code not in spef_codes:
                return False
        if search:
            haystack = " ".join(filter(None, [row.name, row.definition])).lower()
            if search not in haystack:
                return False
        programme_ok = not programmes
        tag_ok = not tags
        if programmes:
            row_programmes = set(row.related_programs_list or [])
            programme_ok = bool(row_programmes.intersection(programmes))
        if tags:
            row_tags = set(row.tags_list or [])
            tag_ok = bool(row_tags.intersection(tags))
        if programmes and tags:
            return programme_ok or tag_ok
        if programmes:
            return programme_ok
        if tags:
            return tag_ok
        return True

    return [row for row in rows if matches(row)]


def _row_matches_leaf_rule(row: IndicatorBank, rule: dict[str, Any] | None) -> bool:
    return row in _python_filter_rows([row], rule)


def _row_matches_rule(row: IndicatorBank, rule: dict[str, Any] | None) -> bool:
    normalized = _normalize_rule(rule)
    if normalized["any"]:
        return any(_row_matches_rule(row, child) for child in normalized["any"])
    if normalized["all"]:
        return all(_row_matches_rule(row, child) for child in normalized["all"])
    if normalized["none"]:
        return not any(_row_matches_rule(row, child) for child in normalized["none"])
    return _row_matches_leaf_rule(row, rule)


def _rule_has_criteria(rule: dict[str, Any] | None) -> bool:
    normalized = _normalize_rule(rule)
    if normalized["any"] or normalized["all"] or normalized["none"]:
        return True
    return bool(
        normalized["related_programs_any"]
        or normalized["tags_any"]
        or normalized["spef_codes_any"]
        or normalized["search_text"]
        or normalized["emergency"] is not None
    )


def resolve_indicator_bank_rows(rule: dict[str, Any] | None, *, limit: int | None = None) -> list[IndicatorBank]:
    normalized = _normalize_rule(rule)
    effective_limit = limit if limit is not None else normalized.get("limit")
    if not _rule_has_criteria(rule):
        return []

    if normalized["any"] or normalized["all"] or normalized["none"]:
        base = IndicatorBank.query.filter(IndicatorBank.archived.isnot(True)).options(joinedload(IndicatorBank.spef_area)).all()
        rows = [row for row in base if _row_matches_rule(row, rule)]
    else:
        query = build_indicator_rule_query(rule)
        dialect = db.session.bind.dialect.name if db.session.bind else ""
        needs_python_filter = dialect != "postgresql" and (normalized["related_programs_any"] or normalized["tags_any"])
        if needs_python_filter:
            rows = _python_filter_rows(query.all(), rule)
        else:
            rows = query.all()

    if effective_limit is not None:
        rows = rows[: int(effective_limit)]
    return rows


def resolve_indicator_bank_ids(rule: dict[str, Any] | None, *, limit: int | None = None) -> list[int]:
    return [row.id for row in resolve_indicator_bank_rows(rule, limit=limit)]


def serialize_indicator_rule_match(row: IndicatorBank) -> dict[str, Any]:
    guidance = (row.disaggregation_guidance or "").strip()
    spef = row.spef_area
    spef_code = ""
    spef_name = ""
    if spef is not None:
        spef_code = (spef.code or "").strip().upper()
        spef_name = (spef.name or "").strip()
    if not spef_code:
        spef_code = (row.area or "").strip().upper()
    return {
        "id": row.id,
        "name": row.name,
        "type": row.type,
        "unit": row.unit,
        "spef_code": spef_code or None,
        "spef_name": spef_name or None,
        "related_programs": row.related_programs_list or [],
        "tags": row.tags_list or [],
        "disaggregation_guidance": guidance[:240] + ("…" if len(guidance) > 240 else "") if guidance else "",
    }


def preview_indicator_rule(
    rule: dict[str, Any] | None,
    *,
    sample_limit: int = 8,
    full_list: bool = False,
    group_by: str | None = None,
) -> dict[str, Any]:
    rows = resolve_indicator_bank_rows(rule)
    limit = len(rows) if full_list else sample_limit
    limit = min(limit, 250)
    serialized = [serialize_indicator_rule_match(row) for row in rows[:limit]]
    result: dict[str, Any] = {
        "count": len(rows),
        "sample": serialized[:sample_limit],
    }
    if full_list:
        result["matches"] = serialized
    if group_by == "spef_section":
        result["groups"] = [
            {"code": code, "count": len(items), "title": spef_section_title(items, code)}
            for code, items in resolve_indicators_grouped_by_spef(rule)
        ]
    elif group_by == "country":
        result["groups"] = [
            {"code": str(country_id), "count": len(items), "title": title}
            for country_id, title, items in resolve_indicators_grouped_by_country(rule)
        ]
    return result


def list_distinct_related_programmes(*, limit: int = 500) -> list[str]:
    programmes: set[str] = set()
    rows = (
        db.session.query(IndicatorBank._related_programs_list)
        .filter(IndicatorBank._related_programs_list.isnot(None), IndicatorBank.archived.isnot(True))
        .limit(5000)
        .all()
    )
    for (value,) in rows:
        if isinstance(value, list):
            programmes.update(str(item).strip() for item in value if str(item).strip())
    return sorted(programmes)[:limit]


def indicator_spef_code(row: IndicatorBank) -> str:
    spef = row.spef_area
    if spef is not None and (spef.code or "").strip():
        return str(spef.code).strip().upper()
    return str(row.area or "").strip().upper()


def resolve_indicators_grouped_by_spef(rule: dict[str, Any] | None) -> list[tuple[str, list[IndicatorBank]]]:
    """Return (spef_code, indicators) pairs sorted by SPEF catalog sort_order."""
    rows = resolve_indicator_bank_rows(rule)
    grouped: dict[str, list[IndicatorBank]] = {}
    for row in rows:
        code = indicator_spef_code(row) or "UNASSIGNED"
        grouped.setdefault(code, []).append(row)

    if not grouped:
        return []

    from app.models.indicator_bank import IndicatorBankSpef

    codes = list(grouped.keys())
    spef_rows = (
        IndicatorBankSpef.query.filter(
            IndicatorBankSpef.is_active.is_(True),
            func.upper(IndicatorBankSpef.code).in_(codes),
        ).all()
    )
    sort_by_code = {(row.code or "").upper(): row.sort_order for row in spef_rows}

    def _sort_key(code: str) -> tuple[Any, ...]:
        order = sort_by_code.get(code, 9999)
        prefix = code[:2] if len(code) >= 2 else code
        prefix_rank = {"CC": 0, "SP": 1, "EF": 2}.get(prefix, 9)
        return (prefix_rank, order, code)

    ordered_codes = sorted(grouped.keys(), key=_sort_key)
    return [(code, grouped[code]) for code in ordered_codes]


def resolve_indicators_grouped_by_country(rule: dict[str, Any] | None) -> list[tuple[int, str, list[IndicatorBank]]]:
    """Return (country_id, country_name, indicators) tuples for repeat-by-country layouts."""
    rows = resolve_indicator_bank_rows(rule)
    if not rows:
        return []
    countries = Country.query.order_by(Country.name.asc()).all()
    return [(country.id, country.name or f"Country {country.id}", rows) for country in countries]


def spef_section_title(indicators: list[IndicatorBank], spef_code: str, *, language: str = "en") -> str:
    for row in indicators:
        if row.spef_area is not None:
            translated = row.spef_area.get_name_translation(language)
            if translated:
                return translated
            if (row.spef_area.name or "").strip():
                return row.spef_area.name.strip()
    from app.models.indicator_bank import IndicatorBankSpef

    spef = IndicatorBankSpef.query.filter(func.upper(IndicatorBankSpef.code) == spef_code.upper()).first()
    if spef:
        translated = spef.get_name_translation(language)
        if translated:
            return translated
        if (spef.name or "").strip():
            return spef.name.strip()
    return spef_code


def list_distinct_tags(*, limit: int = 500) -> list[str]:
    tags: set[str] = set()
    rows = (
        db.session.query(IndicatorBank.tags)
        .filter(IndicatorBank.tags.isnot(None), IndicatorBank.archived.isnot(True))
        .limit(5000)
        .all()
    )
    for (value,) in rows:
        if isinstance(value, list):
            tags.update(str(item).strip() for item in value if str(item).strip())
    return sorted(tags)[:limit]
