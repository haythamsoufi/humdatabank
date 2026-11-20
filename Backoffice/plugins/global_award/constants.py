"""Global Award (IFRC MARC logframe) on top of core project reporting."""

from __future__ import annotations

from pathlib import Path

from app.models.enums import EntityType

PLUGIN_ID = "global_award"
TEMPLATE_NAME = "Global Award"
PORTFOLIO = "Global Award"
FUND = "MARC"
ENTITY_TYPE = EntityType.project.value

ADMIN_PERMISSION = "admin.global_award.manage"
ADMIN_ROLE = "admin_global_award"

EXPLORE_TAB_ID = "global-award"
EXPLORE_PERMISSION = "admin.data_explore.global_award"
EXPLORE_ROLE = "admin_data_explorer_global_award"

PROJECT_REFERENCE_PREFIX = "GA-"
SHEET_NAME = "Logframe_Mastersheet"

PLUGIN_DIR = Path(__file__).resolve().parent
# Backoffice/plugins/global_award -> repository root
REPO_ROOT = PLUGIN_DIR.parents[2]
