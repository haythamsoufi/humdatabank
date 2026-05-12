# Form Operations

Guide for creating, managing, and exporting forms in the Backoffice. Covers the full lifecycle from template design through submission review and data export.

---

## Concepts

| Term | Meaning |
|------|---------|
| **Form Template** | The structural definition of a form: its sections and indicators/questions. Reusable across multiple country assignments. |
| **Form Section** | A logical grouping of items within a template (e.g. "Volunteers", "Financial Data"). |
| **Form Item** | A single field within a section — can be an **Indicator** (numeric with disaggregation), a **Question** (free text or choice), or a **Document** field. |
| **Assignment** | A specific instance of a template assigned to a country for a reporting period. Focal points submit through assignments. |
| **Submission** | A focal point's completed (or in-progress) response to an assignment. |
| **AES** (`AssignmentEntityStatus`) | The status record tracking each country's progress through an assignment (open, submitted, approved, etc.). |

---

## 1. Creating a Form Template

**Route:** Admin → Form Builder → Templates → New Template

**Steps:**
1. Enter a template name (and translations for each active language).
2. Set the template type and any global settings.
3. Save the template — you will be redirected to the section builder.

### Adding Sections

**Route:** Admin → Form Builder → [template] → Add Section

- Enter section name and translations.
- Set display order (drag to reorder later).
- Optionally configure repeat behavior (for variable-length data like multiple projects).

### Adding Items to a Section

**Route:** Admin → Form Builder → [template] → [section] → Add Item

**Item types:**

| Type | Use when |
|------|----------|
| **Indicator** | Collecting numeric data (e.g. number of volunteers). Supports disaggregation by age/sex and calculated totals. |
| **Question** | Free-text or multiple-choice responses. |
| **Document** | Requesting a file upload (e.g. an annual report PDF). |

**Indicator-specific settings:**
- Link to Indicator Bank entry (ensures consistency across templates).
- Enable disaggregation (age groups, sex categories) — the form auto-generates breakdown rows.
- Add relevance conditions (hide this item unless another item has a specific value).
- Mark as calculated (the value is derived from other items; not editable by focal point).

**After adding all items:** Preview the form with Admin → Form Builder → [template] → Preview to confirm layout and logic before assigning to countries.

---

## 2. Editing an Existing Template

> **Caution:** Editing a template that already has open or submitted assignments may affect how existing data is displayed or exported. Prefer adding new items at the end of sections rather than reordering or removing existing ones mid-cycle.

**Route:** Admin → Form Builder → [template] → Edit

- Items can be reordered via drag-and-drop.
- To retire an item without deleting (to preserve historical data): mark it as **inactive** rather than deleting it.
- Rebuild CSS if you add new layout classes: `npm run build:css` in `Backoffice/`.

---

## 3. Assigning a Form to Countries

**Route:** Admin → Assignment Management → Create Assignment

**Fields:**

| Field | Description |
|-------|-------------|
| Form Template | Which template to assign |
| Countries | One or more countries receiving this assignment |
| Reporting Period | Label or date range (displayed to focal points) |
| Open Date / Close Date | When submissions are accepted |
| Status | Set to **Open** when ready; **Draft** while still configuring |

**After creating:**
- Each selected country gets an individual `AssignmentEntityStatus` (AES) record.
- Focal points for those countries will see the form in their dashboard.

**Bulk assignment:** If assigning the same template to many countries simultaneously, use the "Assign to All Countries" or multi-select option if available for your template type.

---

## 4. Monitoring Submissions

**Route:** Admin → Assignment Management → [assignment] → View Submissions

The submission table shows:

| Column | Meaning |
|--------|---------|
| Country | Which National Society |
| Status | Not started / In progress / Submitted / Approved / Returned |
| Last Updated | When the focal point last saved |
| Assigned Focal Point | Who is responsible |
| Actions | View, Edit, Approve, Return, Export |

### Submission statuses explained

| Status | What it means |
|--------|--------------|
| **Not started** | AES is open but no data saved yet |
| **In progress** | Focal point has saved partial data |
| **Submitted** | Focal point marked it complete |
| **Approved** | Admin/System Manager confirmed data quality |
| **Returned** | Sent back to focal point for corrections |

### Returning a submission for corrections

1. Admin → Assignment Management → [assignment] → [country row] → Return
2. Enter a comment explaining what needs correcting.
3. The focal point receives a notification and can edit and re-submit.

---

## 5. Exporting Submission Data

### Single country export

**Route:** Admin → Assignment Management → [assignment] → [country row] → Export Excel

Downloads an Excel file with all submitted values for that country and assignment.

### Bulk export (all countries)

**Route:** Admin → Assignment Management → [assignment] → Export All → Excel

Downloads a consolidated Excel with one row/sheet per country.

**Notes on Excel exports:**
- Disaggregated values (age/sex breakdowns) appear as separate rows.
- Calculated fields are included at their computed values.
- If export fails on large datasets: check server logs for timeout or memory errors; consider exporting per-region or per-country batch.

### Indicator Bank export

**Route:** Admin → System Admin → Indicator Bank → Export

Exports the full indicator library for use in external analysis or as a reference.

---

## 6. Auto-Saving and Draft Recovery

The entry form uses AJAX auto-save (triggers after field blur + periodic interval). If a focal point reports losing data:

1. Check `VERBOSE_FORM_DEBUG=true` logs to confirm save calls were reaching the server.
2. Check the AES record — in-progress data is stored server-side and survives browser refresh.
3. If the save endpoint returned an error, check for WAF 403 issues on large payloads: see [WAF 403 guide](../incidents/waf-403-form-payload-refactor-guide.md).

---

## 7. Indicator Bank Management

The Indicator Bank is the central library of indicators that form items reference.

**Route:** Admin → System Admin → Indicator Bank

**Adding a new indicator:**
1. Enter name, definition, unit of measure, and sector.
2. Add translations for each active language.
3. Save.
4. After adding/editing indicators: sync embeddings for AI search (requires server access):
   ```bash
   cd Backoffice
   python -m flask sync-indicator-embeddings
   ```

**Editing existing indicators:** Changes propagate to all form items linked to that indicator bank entry. Review any open assignments that use the indicator before making significant wording changes.

---

## 8. Public form assignments

Some indicators are published for transparency reporting and consumed via Backoffice public APIs.

**Route:** Admin → Public Assignments

- Assign which countries and indicators are publicly visible.
- Set visibility status (draft / live).
- Consumers outside Backoffice read these definitions through published endpoints; allow time for any intermediary caches to refresh after changes.

> If stakeholders report stale public content, confirm the assignment is **published** here first, then consider cache TTL or CDN behaviour outside this runbook.

---

## 9. Common Issues

| Issue | Likely cause | Fix |
|-------|-------------|-----|
| Focal point cannot see the form | Assignment not open, or user not assigned to country | Check AES status and user country assignment |
| Form items appear in wrong order | Display order not set on section items | Form Builder → section → drag to correct order |
| Calculated field showing wrong value | Calculation formula references item that was moved/renamed | Review relevance conditions and calculated field formulas |
| Export shows blank cells for some countries | Focal point did not save those fields | Check "last updated" — if blank, data was never entered |
| Large export fails (timeout) | Too many submissions in one request | Export per region or per-country batch |
| Auto-save not working | WAF blocking save endpoint | See [WAF 403 guide](../incidents/waf-403-form-payload-refactor-guide.md) |
| Disaggregation rows missing from export | Age/sex categories not configured in system settings | Admin → Settings → Age Groups / Sex Categories |
