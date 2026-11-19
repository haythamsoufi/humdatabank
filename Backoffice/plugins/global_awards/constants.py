"""Global Awards (IFRC MARC logframe) on top of core project reporting."""

from __future__ import annotations

from pathlib import Path

from app.models.enums import EntityType

PLUGIN_ID = "global_awards"
TEMPLATE_NAME = "Global Awards"
PORTFOLIO = "Global Awards"
FUND = "MARC"
ENTITY_TYPE = EntityType.project.value

ADMIN_PERMISSION = "admin.global_awards.manage"
ADMIN_ROLE = "admin_global_awards"

EXPLORE_TAB_ID = "global-awards"
EXPLORE_PERMISSION = "admin.data_explore.global_awards"
EXPLORE_ROLE = "admin_data_explorer_global_awards"

PROJECT_REFERENCE_PREFIX = "GA-"
SHEET_NAME = "Logframe_Mastersheet"

PLUGIN_DIR = Path(__file__).resolve().parent
# Backoffice/plugins/global_awards -> repository root
REPO_ROOT = PLUGIN_DIR.parents[2]
