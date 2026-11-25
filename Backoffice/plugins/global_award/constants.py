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

# Access Group (``rbac_role.kind = 'group'``) that every imported focal point joins.
ACCESS_GROUP_NAME = "Global Award"
ACCESS_GROUP_CODE = "group_global_award"
# Role given to a user the sectoral import creates; existing users keep their roles.
DEFAULT_USER_ROLE_CODE = "assignment_viewer"
SHEET_NAME = "Logframe_Mastersheet"

PLUGIN_DIR = Path(__file__).resolve().parent
# Backoffice/plugins/global_award -> repository root
REPO_ROOT = PLUGIN_DIR.parents[2]
