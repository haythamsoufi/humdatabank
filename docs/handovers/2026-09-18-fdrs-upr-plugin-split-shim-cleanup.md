# FDRS / UPR plugin split — remaining shim cleanup (2026-09-18)

**Status:** Done  
**Audience:** Historical handoff; no further shim-cut work unless a stricter plugin boundary is requested  
**Plan (do not edit):** Cursor plan `fdrs_and_upr_plugin_split_455a9f15` (`fdrs_and_upr_plugin_split_455a9f15.plan.md`)

---

## 1. Outcome

The FDRS/UPR plugin split is complete, including the last planned cut: `app.services.upr` is gone. Implementations live under `Backoffice/plugins/fdrs/` and `Backoffice/plugins/upr/`. Core AI/routes/tests import plugin modules directly.

Plugin Management settings pages:

- `/admin/plugins/fdrs/settings`
- `/admin/plugins/upr/settings`

Do not relocate registries, constants, chunking dispatchers, or every FDRS/UPR string in core.

---

## 2. What was finished

### A. Retargeted imports, then deleted the UPR shim package

Callers now import the plugin modules listed below. `Backoffice/app/services/upr/` has been deleted.

| Former core path | Real module |
|---|---|
| `app.services.upr.query_detection` | `plugins.upr.ai.query_detection` |
| `app.services.upr.validation` | `plugins.upr.excel.validation` |
| `app.services.upr.pns_parsing` | `plugins.upr.excel.pns_parsing` |
| `app.services.upr.data_retrieval` | `plugins.upr.ai.data_retrieval` |
| `app.services.upr.ux` | `plugins.upr.ai.ux` |
| `app.services.upr.document_answering` | `plugins.upr.ai.document_answering` |
| `app.services.upr.focus_area_analysis` | `plugins.upr.ai.focus_area_analysis` |
| `app.services.upr.tool_specs` | `plugins.upr.ai.tool_specs` |
| `app.services.upr.prompts` | `plugins.upr.ai.prompts` |
| `app.services.upr.visual_chunking` | `plugins.upr.ai.visual_chunking` |
| `app.services.upr.excel_import_service` | `plugins.upr.excel.excel_import_service` |
| `app.services.upr.unified_country_plan_excel_service` | `plugins.upr.excel.unified_country_plan_excel_service` |
| `app.services.upr.country_reporting_excel_service` | `plugins.upr.excel.country_reporting_excel_service` |
| `app.services.upr._scripts_path` | `plugins.upr.excel._scripts_path` |
| `app.services.upr` (`is_upr_active`, `query_prefers_upr_documents`, `get_upr_knowledge`) | `plugins.upr.ai` |

Package-level helpers remain on `plugins.upr.ai`.

### B. Deleted the two AI shims

| Former shim | Real module |
|---|---|
| `app/services/ai/tools/_focus_area_analysis.py` | `plugins.upr.ai.focus_area_tools` |
| `app/services/ai/validation/upr_rules.py` | `plugins.upr.ai.upr_rules` |

### C. Extra leftovers cleaned after the first cut

- Unused `app/routes/admin/upr_excel_import.py` shim removed (`admin/__init__.py` already registered the plugin blueprints).
- `app/routes/ai_documents/ifrc.py` stays as a same-package registration shim so `ai_documents.__init__` does not import `plugins.upr` (that loads `plugins.upr.routes` and can deadlock). Job resume in `ai_management.py` imports `plugins.upr.ai.ifrc_routes` directly.
- `upr-excel-import-apply.js` stays in core `app/static/js/forms/modules/` (live ES import from `excel-export.js`); the unused identical plugin copy was deleted.

---

## 3. Optional later (not done)

Only if a stricter plugin cut is requested:

- `get_fdrs_income_sources_for_all_countries()` in `app/services/ai/data/form_retrieval.py` → `plugins/fdrs`
- `fdrs_compliance_doc_label_matches()` and nearby FDRS-only helpers in `app/services/data_quality/helpers.py` → `plugins/fdrs`
- FDRS download helpers in `app/services/ai/documents/ingest.py` → `plugins/fdrs` (leave a generic `source_url` hook in ingest)

---

## 4. Leave in core (do not move)

- `app/utils/data_quality_constants.py`
- `app/services/imports/import_change_log.py`, `async_import_job_store.py`
- Validation and data-quality **registries** (they import plugin implementations)
- `chunk_upr_visuals()` dispatcher in `app/services/ai/documents/chunking.py` (domain term; do not rename)
- `IndicatorBank.fdrs_kpi_code` and assignment Excel enable flags
- NS logos (`ns_logo_service.py`, `sector_logo_urls.py`)
- Activity catalog / `activity_logging_skip.py` labels
- Public `report_service.py` and governance tiles (import updates only)
- Thin mobile wrappers in `app/routes/api/mobile/public_data.py` (already delegate to `plugins.upr.mobile`)
- Entry-form JS `upr-excel-import-apply.js` (sibling ES module of `excel-export.js`)

---

## 5. Import trap (still true)

Do **not** import `plugin_admin_route_wrapper` from `app.plugins.plugin_utils` in `plugins/fdrs/routes.py` or `plugins/upr/routes.py`. That circular-imports `app.routes.admin` → FDRS. Settings routes use `permission_required("admin.plugins.manage")` instead.

---

## 6. How it was verified

```powershell
cd Backoffice
rg "app\.services\.upr" --glob "*.py"
rg "ai\.tools\._focus_area_analysis|ai\.validation\.upr_rules" --glob "*.py"

python -m pytest tests/unit/test_plugins/test_upr_ai.py tests/unit/test_ai_fastpaths.py tests/unit/test_services/test_public_document_service.py tests/unit/test_plugins/test_upr_routes.py tests/unit/test_plugins/test_fdrs_routes.py tests/unit/test_plugins/test_base.py -q --tb=short
```

Both greps returned zero hits. Targeted suite: 242 passed. Broader AI suite: 192 passed.

Playwright (isolated MCP, `http://127.0.0.1:5000`): Act as System Manager → FDRS/UPR settings pages load; AI chat “How many volunteers does the Kenya Unified Plan report?” ran `search_documents` then `get_upr_kpi_value` and completed.

---

## 7. Out of scope

- Editing the original plugin-split plan file
- Relocating historical Alembic migrations
- Renaming `chunk_upr_visuals` or PDF “UPR visuals” strings
