"""US Macro Awards (IFRC MARC logframe) on top of core project reporting."""

from __future__ import annotations

from pathlib import Path

from app.models.enums import EntityType

PLUGIN_ID = "us_macro_awards"
TEMPLATE_NAME = "US Macro Awards"
PORTFOLIO = "US Macro Awards"
FUND = "MARC"
ENTITY_TYPE = EntityType.project.value

ADMIN_PERMISSION = "admin.us_macro_awards.manage"
ADMIN_ROLE = "admin_us_macro_awards"

PROJECT_REFERENCE_PREFIX = "USMA-"
SHEET_NAME = "Logframe_Mastersheet"

PLUGIN_DIR = Path(__file__).resolve().parent
# Backoffice/plugins/us_macro_awards -> repository root
REPO_ROOT = PLUGIN_DIR.parents[2]
DEFAULT_WORKBOOK = REPO_ROOT / "Annex_IFRC MARC_Logframe (work in progress).xlsx"
