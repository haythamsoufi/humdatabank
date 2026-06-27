# Template versioning and submission data identity

> **Status:** Design reviewed and finalised — ready for implementation  
> **Last updated:** June 2026  
> **Related code:** `app/models/forms.py` · `app/models/form_items.py` · `app/routes/admin/form_builder/versions.py` · `app/routes/admin/form_builder/helpers/cloning.py` · `app/services/template_excel_service.py` · `app/routes/admin/form_builder/items.py`

---

## 1. Summary

Form templates are **versioned**: each version has its own `form_page`, `form_section`, and `form_item` rows. Submission data (`form_data`, repeat rows, dynamic indicators, documents, etc.) is stored with **foreign keys to those row IDs**.

When a new version is created (manual draft clone, Excel import, or deploy), **new structure rows get new auto-increment IDs** even when the field is logically unchanged. There is **no stable logical identity** shared across versions, and **deploy does not remap** submission FKs.

This document describes the gap, current behaviour by scenario, and a recommended long-term fix: **`stable_key` on structure rows + deploy-time FK remapping**, with **explicit retention** of data for fields removed in later versions.

---

## 2. Problem statement

### 2.1 How linkage works today

| Layer | Identity used |
|-------|-----------------|
| Template structure | `form_item.id`, `form_section.id` (per `version_id`) |
| Submissions | `form_data.form_item_id`, `repeat_group_data.form_item_id`, etc. |
| Live entry form | Items from `template.published_version_id` |

There is **no** `msgid`, `stable_key`, `source_item_id`, or similar column on structure rows today.

### 2.2 What goes wrong

**Example:** Published **V1** has item "Number of volunteers" with `form_item.id = 100` and 500 `form_data` rows. Draft **V2** is cloned from V1; the same question gets `form_item.id = 250`.

| Question | Current answer |
|----------|----------------|
| Is V1 data deleted when editing V2? | **No** — different item IDs, different version |
| Does V2 "inherit" V1 submissions for the same question? | **No** |
| After deploying V2, does the live form show old answers? | **No** — live form uses V2 ids (250); data still on id 100 |
| Is orphaned data deleted? | **No** — it remains on archived V1 rows, but disconnected from UX |

So the gap is not only "data loss on draft import" (usually safe for published V1), but **lack of continuity** when a new version goes live, and **no first-class way** to keep historical data addressable for fields removed in later versions.

### 2.3 What already works (manual editing)

When an admin **deletes a single item** in the form builder, the UI offers:

- **Delete data and remove** — deletes `form_data` and the item row  
- **Keep data and archive item** — sets `archived = True`, preserves FKs and data  

See `app/routes/admin/form_builder/items.py` (`delete_item`).

**Excel import** and **full version replace** do not offer this per field. Import calls `_clear_version_structure`, which **hard-deletes** all structure and **deletes submission rows** tied to **that version's** item/section IDs (with a single preflight warning, not per-item archive).

---

## 3. Current behaviour by scenario

### 3.1 Clone V1 → draft V2 (manual "New version")

1. New `form_template_version` row (draft).  
2. `_clone_template_structure` copies pages/sections/items with **new IDs**.  
3. An `item_id_map` `{old_id → new_id}` is built and used **only** to remap relevance/validation JSON inside the template — **not** `form_data`.  
4. V1 submissions remain on V1 item IDs. V2 items typically have **no** submission data.

### 3.2 Excel import into draft V2

1. `_clear_version_structure(target_version_id)` — deletes **all** V2 pages/sections/items and submission data referencing **V2** IDs only.  
2. Structure rebuilt from Excel; **new** item IDs (Excel `id` column is export sequence, not DB id).  
3. **V1 untouched.**

Items in V1 that are **not** in the Excel file are **not** created in V2. V1 rows and data **remain in the DB**.

### 3.3 Excel import into published V1 (`import_version_mode = current_version`)

Same full replace on **published** version → **destructive** for live submission data. Preflight warns once; no archive path.

### 3.4 Deploy V2

1. Previous published version → `status = archived`.  
2. `template.published_version_id = V2.id`.  
3. **No** migration of `form_data` to new item IDs.  
4. Entry form loads V2 structure; old answers remain on V1 (archived) item IDs.

### 3.5 Summary table

| Action | V1 structure & data | V2 structure | V2 data before deploy | After deploy (live form) |
|--------|---------------------|--------------|------------------------|---------------------------|
| Clone to V2 | Unchanged | Copy, new IDs | Usually empty | Live uses V2; old data orphaned on V1 |
| Excel → V2 | Unchanged | Replaced, new IDs | Cleared then filled | Same |
| Excel → V1 | Replaced, data deleted | — | — | N/A |
| Deploy V2 | Archived, kept in DB | Published | N/A | New fields empty; old fields disconnected |

---

## 4. Requirements (target behaviour)

1. **Continuity:** If a logical field is unchanged across versions, submission data should **follow** to the new version's item when the new version is **deployed** (live assignments).  
2. **Retention:** If a field exists in V1 but not in V2, **keep all submission data in the DB** on the archived version's rows — do not delete or re-point to another field.  
3. **Excel & clone:** Both must be able to express "same field" vs "new field" vs "removed field".  
4. **Align with manual archive semantics** at version/deploy boundary where possible.  
5. **Incremental adoption:** Prefer a design that fits the existing FK model (`form_data.form_item_id`) rather than a full platform rewrite.

---

## 5. Recommended solution: `stable_key` + deploy remapping

### 5.1 Core idea

Introduce a **template-scoped logical identifier** on structure rows:

- `form_item.stable_key` (string, UUID recommended)  
- `form_section.stable_key` (same pattern for repeat/dynamic section data)

**Rules:**

| Event | `stable_key` behaviour |
|-------|-------------------------|
| New item/section in builder | Generate new UUID |
| Clone V1 → V2 | **Copy** `stable_key` from source row |
| Excel export | Include `stable_key` column |
| Excel import | Reuse key from file; generate new key for new rows |
| Rename label / change copy | Key **unchanged** (identity ≠ display text) |

Uniqueness: `(template_id, stable_key, version_id)` — the **same** `stable_key` appears on one row per version for "the same" logical field.

This mirrors common practice (ODK/XLSForm field `name`, FHIR element id, CMS slugs): **logical id ≠ physical row id**.

### 5.2 Deploy-time remapping (only place live data moves)

When **deploying** version `N` that replaces published version `M`:

```
For each submission row R pointing at item/section on M:
  key = R.target.stable_key
  If N has a row with the same stable_key:
      UPDATE R to point at N's row id
  Else:
      LEAVE R unchanged on M's row   # historical retention
```

Apply the same pattern for:

- `form_data` / `repeat_group_data` (via item `stable_key`)  
- `repeat_group_instance`, `dynamic_indicator_data`, `dynamic_section_context` (via section `stable_key`)  
- `submitted_document` (via item `stable_key`)  

**Never:**

- Delete orphaned submission rows because a key is missing in the new version  
- Heuristic match by label, order, or indicator_bank_id  
- Cascade-delete archived version structure that still has submission FKs  

### 5.3 Intended outcomes

| Scenario | Result |
|----------|--------|
| Same field in V1 and V2 (same `stable_key`) | Data remapped to V2 on deploy; live form shows historical values |
| Field removed in V2 | Data stays on V1 archived item; not shown on live form; **still in DB** |
| New field in V2 | New `stable_key`; no inherited data |
| Draft / Excel work on V2 | Does not touch V1; remapping only at **deploy** |

### 5.4 Why this is recommended long-term

| Alternative | Assessment |
|-------------|------------|
| **Heuristic matching on deploy** | Fragile (renames, reorder, Excel edits) |
| **Store clone `item_id_map` on version only** | Helps manual clone; Excel breaks lineage |
| **Single shared structure, versions = metadata** | Clean but massive refactor |
| **`form_data` → `stable_key` directly** | Purest long-term; requires rewriting all read/write paths |
| **`stable_key` + FK remap on deploy** | **Best fit:** incremental, matches existing FK model, supports Excel round-trip and retention |

Optional later enhancement: denormalize `stable_key` onto submission tables for reporting without joining archived items.

---

## 6. Design review: validation and challenges

> Code review performed June 2026. All claims below are verified against the actual model and route files.

### 6.1 What the code confirms

| Claim in §5 | Verdict |
|-------------|---------|
| No `stable_key` or equivalent exists anywhere | ✅ Confirmed — `rg stable_key` returns zero matches across the repo |
| `_clone_template_structure` remaps rule JSON but not submission FKs | ✅ Confirmed — `cloning.py` builds `item_id_map` used only for `relevance_condition` / `validation_condition` |
| `deploy_template_version` does status flip only, no FK migration | ✅ Confirmed — `versions.py` does archive + publish + cache invalidate; zero submission UPDATEs |
| `_clear_version_structure` hard-deletes submission data for the target version | ✅ Confirmed — deletes `RepeatGroupData`, `RepeatGroupInstance`, `DynamicIndicatorData`, `DynamicSectionContext`, `FormData`, `SubmittedDocument` rows tied to the target version's IDs |
| `delete_template_version` already blocks deletion when submission FKs exist | ✅ Confirmed — counts `FormData`, `RepeatGroupData`, `RepeatGroupInstance`, `DynamicIndicatorData` and aborts if non-zero (but only 4 of 6 FK tables — see Challenge B) |
| `FormTemplateVersion.based_on_version_id` records clone lineage | ✅ Confirmed in `forms.py` model |
| `SubmittedDocument.form_item_id` references `form_item.id` (nullable) | ✅ Confirmed in `documents.py` |

**Complete FK surface that must be remapped at deploy time** (verified from model files):

| Table | Column remapped | Keyed via |
|-------|----------------|-----------|
| `form_data` | `form_item_id` | item `stable_key` |
| `repeat_group_data` | `form_item_id` | item `stable_key` |
| `submitted_document` | `form_item_id` (nullable) | item `stable_key` |
| `repeat_group_instance` | `section_id` | section `stable_key` |
| `dynamic_indicator_data` | `section_id` | section `stable_key` |
| `dynamic_section_context` | `section_id` | section `stable_key` |

`repeat_group_data.repeat_instance_id` → `repeat_group_instance.id` does **not** change (the instance row itself is updated in-place; its PK stays the same).

`dynamic_indicator_data.indicator_bank_id` is already globally stable — no remapping needed.

### 6.2 Challenges and resolutions

#### Challenge A — Backfill algorithm unspecified (critical gap)

**Problem:** The original plan says "Backfill UUIDs for all existing rows" with no algorithm. If every existing row gets an independent UUID, V1 items and V2 items (cloned from V1) will have different keys, so deploying V2 after the migration would remap nothing for historical data — the entire feature would be inert for the existing dataset.

**Resolution — three-pass backfill script:**

1. **Indicator items** — group by `(template_id, indicator_bank_id)` across all versions. All items sharing the same `(template_id, indicator_bank_id)` get one shared UUID. This is fully reliable because `indicator_bank_id` is already a semantic stable key.
2. **Non-indicator items and sections on cloned versions** — for each `(V_source, V_target)` pair where `V_target.based_on_version_id = V_source.id`, match items by `(section_order_rank, item_order_rank)`. Assign the same UUID for clean positional matches. Flag ambiguous rows.
3. **Remaining unmatched rows** — assign fresh isolated UUIDs. Document as "lineage unknown."

Post-backfill: query and log `(template_id, matched_indicator, matched_positional, unmatched)` as a coverage report. The script requires a `--dry-run` flag and must run in a single transaction.

#### Challenge B — `delete_template_version` checks only 4 of 6 FK tables

**Problem:** The existing delete guard counts `FormData`, `RepeatGroupData`, `RepeatGroupInstance`, `DynamicIndicatorData` — it does not check `SubmittedDocument` or `DynamicSectionContext`.

**Resolution:** Extend the count query in `delete_template_version` to include all 6 tables before Phase 1 ships (a small, independent fix).

#### Challenge C — Transaction scope of deploy-time remapping

**Problem:** The original design does not specify whether FK remapping runs inside or outside the deploy transaction. If outside: there is a window where the live form loads V2 structure but all submission data is still on V1 IDs, so users would see blank answers immediately after deploy.

**Resolution:**
- Remapping runs **inside the same database transaction** as the status flip: archive V1 → publish V2 → bulk UPDATE FKs → commit atomically.
- Use `synchronize_session=False` bulk UPDATEs, identical to the pattern in `_clear_version_structure`.
- Expected runtime: < 30 s for templates up to ~1 M submission rows with existing indexes (`ix_form_data_form_item`, `ix_dynamic_indicator_section`, `ix_repeat_instance_section`, etc. — all confirmed present).
- Add a **preflight row count** to the deploy confirmation dialog. If total remappable rows exceed a configurable threshold (default 500,000), show a timed-operation warning — do not block.
- No background job: deploy is an admin-only action with implicit latency tolerance.

#### Challenge D — Unique constraint hazards during bulk section FK updates

**Problem:** Three tables have unique constraints that include `section_id`:

| Table | Constraint columns |
|-------|-------------------|
| `repeat_group_instance` | `(aes_id\|public_id, section_id, instance_number)` |
| `dynamic_indicator_data` | `(aes_id\|public_id, section_id, indicator_bank_id, repeat_instance_number)` |
| `dynamic_section_context` | `(aes_id\|public_id, section_id, provider_id)` |

When bulk-updating `section_id` from V_old → V_new, if any row already points at a V_new section ID, Postgres will raise a unique violation.

**Resolution:** Before any bulk UPDATE, the migration service asserts zero existing rows in these tables for V_new section IDs. If the assertion fails, abort the deploy with a clear error (indicates the draft was used for data entry, which the UI should prevent but the service must guard).

#### Challenge E — Remapping must run in a defined order

**Problem:** The document lists tables to remap without specifying order. While most UPDATEs are independent, documenting the order prevents future confusion and makes the service deterministic.

**Correct order:**
1. Section remaps: `repeat_group_instance.section_id`, `dynamic_indicator_data.section_id`, `dynamic_section_context.section_id`
2. Item remaps: `form_data.form_item_id`, `repeat_group_data.form_item_id`, `submitted_document.form_item_id`

`repeat_group_data.repeat_instance_id` is **not** remapped (the instance PK doesn't change; only its `section_id` changes).

#### Challenge F — Excel import can silently corrupt field identity

**Problem:** Rejecting duplicate `stable_key` within a file (as originally proposed) prevents in-file duplicates but not semantic corruption: an admin could accidentally paste a `stable_key` that matches a *different* field in the same template, effectively swapping two fields' identities at deploy time.

**Resolution:** During Excel import validation, for each `stable_key` from the file that already exists in the **published version**, check that `item_type` and `indicator_bank_id` match. Emit a named warning (not a block) if they differ:

```
⚠ Row 42: stable_key <uuid> matches published field "Volunteers trained" (indicator_bank_id=55)
  but this row is item_type=question. Identity mismatch — verify this is intentional.
```

#### Challenge G — `import_version_mode='current_version'` is incompatible with the new system

**Problem:** `_clear_version_structure` on the published version destroys all `stable_key` assignments for that version's items. Any subsequent deploy would find no matching keys in the previously-published version, so no data would be remapped.

**Resolution:** Once Phase 1 is deployed, `import_version_mode='current_version'` (Excel import into published version) must **hard-block** when the version has existing submission data:

> "This template has submitted data. Import into a draft version and deploy it instead."

When the version has zero submission data (new template, never submitted), allow as before.

This replaces the existing single-warning approach with a hard guard at the service level.

#### Challenge H — `stable_key` visibility and editability policy

**Resolution:** `stable_key` is **system-managed only**. It is:
- **Not** editable in the form builder UI
- **Readable** (read-only display) in the advanced item settings panel, with a "copy" button for debugging
- **Exported** in the Excel template sheet (read-only cell style)
- **Exposed** in API responses (Phase 4)

---

## 7. Final implementation plan

> Replaces the original §6. All tasks are concrete and ordered by dependency.

### Pre-work: scale inventory

Before starting Phase 1, run a one-off SQL query to gather per-template counts of: versions, items, total `form_data` rows, indicator vs question ratio, and templates where `based_on_version_id IS NULL` for all versions (no recoverable lineage). Use this to set the deploy preflight threshold and to project backfill coverage.

---

### Phase 1 — Field identity

**Goal:** Every item and section row has a `stable_key`. Create, clone, and Excel round-trip all preserve it.

**Database migration** — `Backoffice/migrations/versions/add_stable_key_to_form_structure.py`
- [ ] Add `form_item.stable_key VARCHAR(36) NULL`
- [ ] Add `form_section.stable_key VARCHAR(36) NULL`
- [ ] Partial unique index `uq_form_item_stable_key` on `(template_id, stable_key, version_id) WHERE stable_key IS NOT NULL`
- [ ] Partial unique index `uq_form_section_stable_key` on `(template_id, stable_key, version_id) WHERE stable_key IS NOT NULL`

**Model layer** — `app/models/form_items.py`, `app/models/forms.py`
- [ ] `FormItem`: add `stable_key = Column(String(36), nullable=True)` with a comment: `# Immutable after first publish — never regenerate for existing items`
- [ ] `FormSection`: same column and comment

**Creation paths** — auto-generate UUID on new rows
- [ ] `app/routes/admin/form_builder/helpers/` — `_create_form_item`: set `stable_key = str(uuid.uuid4())`
- [ ] All `FormSection` creation paths in the builder and any factory/seed scripts

**Clone path** — copy `stable_key` from source rows
- [ ] `cloning.py` — `_clone_template_structure`: add `stable_key=src_item.stable_key` and `stable_key=src_section.stable_key` in the constructor calls (one line each)
- [ ] Same for `_clone_template_structure_between_templates`

**Excel export** — `app/services/template_excel_service.py`
- [ ] Add `stable_key` column to the items sheet in `export_template`
- [ ] Style the column as read-only / locked in the workbook

**Excel import** — `app/services/template_excel_service.py`
- [ ] Read `stable_key` from items sheet; use file value if present and valid UUID, else generate new UUID
- [ ] Reject import if duplicate `stable_key` within the file (error, named field)
- [ ] Warn (do not block) if a file `stable_key` matches a published-version item with a different `item_type` or `indicator_bank_id` (Challenge F)
- [ ] Hard-block import into published version when submission data exists (Challenge G)

**Backfill script** — `Backoffice/scripts/backfill_stable_keys.py`
- [ ] `--dry-run` flag: print coverage report without committing
- [ ] Pass 1 — indicator items: `GROUP BY (template_id, indicator_bank_id)` → assign one UUID per group
- [ ] Pass 2 — non-indicator items/sections with `based_on_version_id` lineage: match by `(section_order_rank, item_order_rank)` → assign shared UUIDs
- [ ] Pass 3 — remaining unmatched: assign fresh UUIDs
- [ ] Log per-template coverage summary
- [ ] Run inside a single transaction; rollback on any error

**Delete guard fix** (independent, can ship first)
- [ ] `delete_template_version` in `versions.py`: extend the row count query to also check `SubmittedDocument` and `DynamicSectionContext` (Challenge B)

---

### Phase 2 — Deploy migration service

**Goal:** When V_new is deployed replacing V_old, all submission FKs pointing at V_old structure are bulk-updated to V_new structure where `stable_key` matches.

**New service** — `app/services/version_deploy_migration_service.py`

```python
class VersionDeployMigrationService:
    @classmethod
    def migrate_submission_fks(
        cls,
        old_version_id: int,
        new_version_id: int,
        template_id: int,
    ) -> dict:
        """
        Bulk-remaps submission rows from old_version items/sections to
        new_version items/sections using stable_key matching.
        Returns a summary dict with migrated/orphaned counts per table.
        Must be called inside the deploy transaction, after status flip,
        before db.session.flush().
        """
```

**Service implementation tasks**
- [ ] Build `item_key_map: {old_item.id → new_item.id}` by joining `form_item` twice on `(template_id, stable_key)` filtering on old and new `version_id`
- [ ] Build `section_key_map: {old_section.id → new_section.id}` (same join pattern on `form_section`)
- [ ] Assert zero existing rows for V_new section IDs in `repeat_group_instance`, `dynamic_indicator_data`, `dynamic_section_context` (Challenge D precondition); raise if non-zero
- [ ] **Section remaps** (in order — Challenge E):
  - `UPDATE repeat_group_instance SET section_id = <new> WHERE section_id IN old_section_ids AND section_id IN section_key_map`
  - `UPDATE dynamic_indicator_data SET section_id = <new>` (same pattern)
  - `UPDATE dynamic_section_context SET section_id = <new>` (same pattern)
- [ ] **Item remaps** (in order):
  - `UPDATE form_data SET form_item_id = <new> WHERE form_item_id IN old_item_ids AND form_item_id IN item_key_map`
  - `UPDATE repeat_group_data SET form_item_id = <new>` (same pattern)
  - `UPDATE submitted_document SET form_item_id = <new>` (same pattern, NULL-safe)
- [ ] Use `synchronize_session=False` for all bulk UPDATEs
- [ ] Mark orphaned V_old items (keys with no match in V_new) as `archived=True` (answers Open Question 4)
- [ ] Return summary: `{remapped_items, orphaned_items, remapped_sections, orphaned_sections, ...per table counts}`

**Deploy route** — `app/routes/admin/form_builder/versions.py`
- [ ] After `prev.status = 'archived'` and `template.published_version_id = version.id`, call `VersionDeployMigrationService.migrate_submission_fks(prev.id, version.id, template.id)` **before** `db.session.flush()`
- [ ] Include migration summary in the `log_admin_action` payload
- [ ] Include summary in flash message: "Version deployed. 2,430 field values carried forward; 12 values retained on archived version."

**Preflight endpoint**
- [ ] `GET /templates/<id>/deploy/preflight` → return per-table estimated row counts for the confirmation modal (no state changes)
- [ ] Deploy confirmation modal: show "~N rows will be remapped" with a latency warning if N > threshold

---

### Phase 3 — Safety, UX, and data guards

**Goal:** Prevent future accidental data loss; make versioning state visible in the admin UI.

- [ ] **Builder UI** — add a read-only `stable_key` display with "copy" button in the advanced item settings panel
- [ ] **Version history list** — show "fields carried forward: N / orphaned: N" per archived version if migration has been run
- [ ] **Audit log** — confirm `stable_key_migration_summary` is part of the `template_version_deploy` action payload
- [ ] **Reporting helper** — add `FormItem.by_stable_key(template_id, stable_key)` class method returning all version rows for a logical field; document in `docs/DEVELOPER-HANDBOOK.md`

---

### Phase 4 — API and mobile (deferred)

**Goal:** Remove the requirement for clients to cache DB IDs.

- [ ] Expose `stable_key` alongside `item.id` in `GET /api/form-schema/<template_id>` response
- [ ] Expose `stable_key` in the mobile API form structure endpoint
- [ ] Mobile app: submit data by `stable_key`; server resolves to current published version's item `id`
- [ ] Add deprecation timeline for clients using numeric `form_item_id` only

---

## 8. Edge cases and policy decisions

| Case | Decision |
|------|----------|
| Same `stable_key`, field **type** changed (indicator → question) | Treat as same identity; emit type-mismatch warning on Excel import. Admin may set `breaking_change: true` in item config to force a new key. |
| Duplicate `stable_key` within an Excel import file | Reject import with a named field error. |
| Re-use of a `stable_key` for a semantically different field | Forbidden by policy (model comment). No DB constraint can prevent intentional misuse, but the Excel type-mismatch warning catches the common accident. |
| Import into published version with existing submission data | **Hard block** after Phase 1 ships (replacing the current single-warning). |
| `_clear_version_structure` on a draft version | Unchanged — deletes only that draft's item IDs; no submission data should exist on draft items in normal usage. |
| Deploying V3 when V2 was discarded (never published) | V3 was cloned from V1 via `_clone_template_structure`, so V3 items have the **same** `stable_key`s as V1. Remapping from V1 → V3 works correctly. |
| Two items in the same version with the same `stable_key` | Blocked by the partial unique index `uq_form_item_stable_key`. |
| Template with no prior published version (first deploy) | No V_old to remap from; migration service returns zero counts and exits cleanly. |

---

## 9. Non-goals (for this design)

- Rewriting all submission storage to key-based lookups immediately  
- Git-style branch/merge of template versions  
- Automatic migration of orphaned data into new fields "that look similar"  
- Deleting historical submission data when a field is dropped from a new version  

---

## 10. References in codebase

| Area | Location |
|------|----------|
| Submission FK — standard fields | `FormData.form_item_id` — `app/models/forms.py` |
| Submission FK — repeat fields | `RepeatGroupData.form_item_id` — `app/models/forms.py` |
| Submission FK — repeat instances | `RepeatGroupInstance.section_id` — `app/models/forms.py` |
| Submission FK — dynamic indicators | `DynamicIndicatorData.section_id` — `app/models/forms.py` |
| Submission FK — dynamic section context | `DynamicSectionContext.section_id` — `app/models/forms.py` |
| Submission FK — documents | `SubmittedDocument.form_item_id` — `app/models/documents.py` |
| Clone + rule id remap | `app/routes/admin/form_builder/helpers/cloning.py` |
| Deploy | `app/routes/admin/form_builder/versions.py` — `deploy_template_version` |
| Excel full replace | `TemplateExcelService._clear_version_structure`, `import_template` — `app/services/template_excel_service.py` |
| Manual delete vs archive | `app/routes/admin/form_builder/items.py` — `delete_item` |
| Delete version guard (incomplete — fix in Phase 1) | `app/routes/admin/form_builder/versions.py` — `delete_template_version` |
| Preflight deletion counts | `TemplateExcelService._count_deletion_impact` |
| Live form version | `app/routes/forms/entry.py` — uses `published_version_id` |
| Version lineage | `FormTemplateVersion.based_on_version_id` — `app/models/forms.py` |

---

## 11. Answered design questions

| Question | Answer |
|----------|--------|
| Should `stable_key` be admin-visible/editable? | **System-managed only.** Read-only display in advanced item panel + Excel export. Not editable anywhere. |
| Should deploy migration run in a background job? | **No.** Runs synchronously inside the deploy transaction. A background job creates a dangerous window where the live form has V2 structure but data is still on V1 IDs. Show a row-count estimate in the deploy preflight instead. |
| Do analytics queries need a one-off backfill after first deploy migration? | **Yes.** The Phase 1 backfill script must run once before any deploy uses the migration service. After backfill, existing V1↔V2 key matches are in place for the next deploy. |
| Should orphaned V_old items be marked `archived=True` when their key has no match in V_new? | **Yes.** The migration service sets `archived=True` on V_old items with no matching `stable_key` in V_new. This makes removed fields visible in the builder on the archived version without a separate query. |

---

## 12. Decision log

| Date | Decision |
|------|----------|
| June 2026 | Document problem and propose `stable_key` + deploy remapping with orphaned data retention |
| June 2026 | Code review completed. Design validated. Eight challenges identified and resolved: backfill algorithm (A), missing FK table in delete guard (B), transaction scope (C), unique constraint hazards (D), remapping order (E), Excel identity mismatch (F), published-version import block (G), stable_key visibility policy (H). Final implementation plan written. |
