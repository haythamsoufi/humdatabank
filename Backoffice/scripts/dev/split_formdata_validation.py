"""One-off script to split formdata_validation.py into focused modules."""
import os
import textwrap

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SRC = os.path.join(ROOT, "app", "services", "ai", "validation", "formdata_validation.py")
PKG = os.path.join(ROOT, "app", "services", "ai", "validation")

with open(SRC, "r", encoding="utf-8") as f:
    lines = f.readlines()


def slice_lines(start, end):
    return "".join(lines[start - 1 : end])


def dedent_block(body: str, spaces: int = 4) -> str:
    out = []
    for line in body.splitlines(keepends=True):
        if line.strip() and line.startswith(" " * spaces):
            out.append(line[spaces:])
        else:
            out.append(line)
    return "".join(out)


# --- parsers.py ---
parsers_header = '''"""Parsing helpers for AI form-data validation (claim extraction)."""
from __future__ import annotations

import json
import logging
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_YEAR_RE = re.compile(r"\\b(19\\d{2}|20\\d{2})\\b")
_PAREN_CODE_RE = re.compile(r"\\(([A-Za-z0-9_\\-]{1,40})\\)")
_NUMBER_TOKEN_RE = re.compile(r"[-+]?\\d[\\d,\\u00A0\\u202F ]*(?:\\.\\d+)?")

'''
with open(os.path.join(PKG, "parsers.py"), "w", encoding="utf-8") as f:
    f.write(parsers_header + slice_lines(34, 426))

# --- upr_rules.py ---
upr_header = '''"""UPR KPI applicability and reference helpers."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.services.ai.validation.parsers import (
    _format_int,
    _infer_primary_keyword,
    _parse_int_number,
    _safe_int,
)

logger = logging.getLogger(__name__)

'''
retrieve_body = dedent_block(slice_lines(487, 524))
upr_content = upr_header + slice_lines(200, 244) + slice_lines(264, 337) + "\n\n" + retrieve_body.replace(
    "        self._retrieve_upr_kpi_reference", "        retrieve_upr_kpi_reference"
).replace(
    "def _retrieve_upr_kpi_reference(self, context: Dict[str, Any])",
    "def retrieve_upr_kpi_reference(context: Dict[str, Any])",
)
with open(os.path.join(PKG, "upr_rules.py"), "w", encoding="utf-8") as f:
    f.write(upr_content)

# --- ui_payload.py ---
ui_header = '''"""UI payload builders for AI validation opinions and suggestions."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from flask import current_app

from app.services.ai.validation.parsers import (
    _PAREN_CODE_RE,
    _YEAR_RE,
    _extract_keyword_number_claims,
    _is_blankish_value,
    _parse_int_number,
)
from app.services.ai.validation.upr_rules import (
    _format_int,
    _infer_primary_keyword,
    _median_int,
    _parse_year_from_period,
    _required_terms_for_claims,
    _upr_document_label,
    _upr_suggestion_reason,
)

logger = logging.getLogger(__name__)

'''
build_body = dedent_block(slice_lines(1083, 1767))
compute_body = dedent_block(slice_lines(3242, 3561))
ui_content = (
    ui_header
    + "def build_opinion_ui(\n"
    + "    *,\n"
    + "    context: Dict[str, Any],\n"
    + "    verdict: str,\n"
    + "    confidence: Optional[float],\n"
    + "    opinion_full_text: str,\n"
    + "    evidence_chunks: List[Dict[str, Any]],\n"
    + "    historical: Optional[Dict[str, Any]],\n"
    + "    llm_json: Optional[Dict[str, Any]],\n"
    + "    heuristic: Dict[str, Any],\n"
    + "    suggestion: Optional[Dict[str, Any]],\n"
    + ") -> Dict[str, Any]:\n"
    + build_body
    + "\n\n"
    + "def compute_suggestion(\n"
    + "    *,\n"
    + "    context: Dict[str, Any],\n"
    + "    evidence_chunks: List[Dict[str, Any]],\n"
    + "    historical: Optional[Dict[str, Any]],\n"
    + "    llm_json: Optional[Dict[str, Any]],\n"
    + "    heuristic: Dict[str, Any],\n"
    + ") -> Optional[Dict[str, Any]]:\n"
    + compute_body
)
with open(os.path.join(PKG, "ui_payload.py"), "w", encoding="utf-8") as f:
    f.write(ui_content)

# --- orchestrator ---
orchestrator_header = '''from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app

from app.extensions import db
from app.models import (
    AIFormDataValidation,
    AssignedForm,
    AssignmentEntityStatus,
    DynamicIndicatorData,
    FormData,
    FormItem,
    IndicatorBank,
    PublicSubmission,
)
from app.models.enums import AssignmentEntityStatusValue
from app.services.ai.documents.vector_store import AIVectorStore
from app.utils.datetime_helpers import utcnow

from app.services.ai.validation.parsers import (
    ValidationResult,
    _PAREN_CODE_RE,
    _YEAR_RE,
    _extract_json_object,
    _extract_keyword_number_claims,
    _format_int,
    _infer_primary_keyword,
    _is_blankish_value,
    _median_int,
    _normalize_disagg_for_presence,
    _parse_int_number,
    _parse_year_from_period,
    _required_terms_for_claims,
    _safe_int,
    _upr_document_label,
    _upr_kpi_applicable,
    _upr_suggestion_reason,
)
from app.services.ai.validation.upr_rules import retrieve_upr_kpi_reference
from app.services.ai.validation.ui_payload import build_opinion_ui, compute_suggestion

logger = logging.getLogger(__name__)

'''
parts = [
    slice_lines(429, 479),
    slice_lines(525, 1069),
    slice_lines(1769, 3232),
    slice_lines(3563, len(lines)),
]
orchestrator_body = "".join(parts)
orchestrator_body = orchestrator_body.replace(
    "upr_kpi = self._retrieve_upr_kpi_reference(context) or None",
    "upr_kpi = retrieve_upr_kpi_reference(context) or None",
)
orchestrator_body = orchestrator_body.replace(
    "suggestion_obj = self._compute_suggestion(",
    "suggestion_obj = compute_suggestion(",
)
orchestrator_body = orchestrator_body.replace(
    "opinion_ui = self._build_opinion_ui(",
    "opinion_ui = build_opinion_ui(",
)
wrappers = '''
    def _retrieve_upr_kpi_reference(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        return retrieve_upr_kpi_reference(context)

    def _build_opinion_ui(self, **kwargs: Any) -> Dict[str, Any]:
        return build_opinion_ui(**kwargs)

    def _compute_suggestion(self, **kwargs: Any) -> Optional[Dict[str, Any]]:
        return compute_suggestion(**kwargs)

'''
orchestrator_body = orchestrator_body.replace(
    "    def _resolve_disagg_labels(",
    wrappers + "    def _resolve_disagg_labels(",
)
reexports = '''

from app.services.ai.validation.parsers import ValidationResult  # noqa: F401

__all__ = [
    "AIFormDataValidationService",
    "ValidationResult",
    "build_opinion_ui",
    "compute_suggestion",
    "retrieve_upr_kpi_reference",
]
'''
with open(SRC, "w", encoding="utf-8") as f:
    f.write(orchestrator_header + orchestrator_body + reexports)

print("formdata_validation split complete")
