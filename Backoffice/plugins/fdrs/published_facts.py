"""Shared filters for public FDRS consumers of the published snapshot.

The public website and the mobile home/disaggregation screens should show the
curated ``published_*`` columns, not the live editable ``value`` / ``disagg_data``.
"""

from __future__ import annotations

from typing import Any, Optional

from app.extensions import db
from app.models import FormData, FormItem
from app.services.data_retrieval.shared import form_item_privacy_is_public_expr
from app.utils.api_helpers import extract_numeric_value


def public_form_item_ids(
    *,
    indicator_bank_id: Optional[int] = None,
    template_id: Optional[int] = None,
) -> list[int]:
    """Form items marked privacy=public, optionally scoped to one indicator and template."""
    query = FormItem.query.filter(form_item_privacy_is_public_expr())
    if indicator_bank_id:
        query = query.filter(FormItem.indicator_bank_id == indicator_bank_id)
    if template_id:
        query = query.filter(FormItem.template_id == template_id)
    return [row.id for row in query.with_entities(FormItem.id).all()]


def published_snapshot_clause():
    """Rows an admin has actually published (scalar and/or disaggregation)."""
    return db.or_(
        FormData.published_value.isnot(None),
        FormData.published_disagg_data.isnot(None),
    )


def published_numeric(numeric: Any, value: Any) -> Optional[float]:
    """Prefer the stored published numeric, then a numeric parse of the published text."""
    if numeric is not None:
        try:
            return float(numeric)
        except (TypeError, ValueError):
            pass
    parsed = extract_numeric_value(value)
    if parsed is None:
        return None
    try:
        return float(parsed)
    except (TypeError, ValueError):
        return None
