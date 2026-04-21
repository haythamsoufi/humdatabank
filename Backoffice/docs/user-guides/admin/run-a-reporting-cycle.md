# Run a reporting cycle (admin playbook)

Use this playbook when you need to run a collection round end-to-end (from preparing a template to exporting approved data).

## Before you start

- You need **Admin** access for templates and assignments.
- Agree internally on:
  - the reporting period name (example: "2026 Q1")
  - the list of participating countries
  - what "good quality" means (required documents, validation expectations)

## Step 1 — Prepare the template

1. Open **Admin Panel** → **Form & Data Management** → **Manage Templates**.
2. Open the template you will use.
3. Confirm the template is:
   - clear (labels/help text)
   - not overly strict (reasonable required fields)
   - consistent (dropdown options standardized)
4. If you made edits, test with a small draft assignment.

Tip: For complex changes, follow [Form Builder (advanced)](form-builder-advanced.md).

## Step 2 — Create the assignment

1. Open **Admin Panel** → **Form & Data Management** → **Manage Assignments**.
2. Click **Create** (or similar).
3. Select:
   - the template
   - the countries (or organizations) included
   - the start date and deadline
4. Add a short instruction message:
   - what you need
   - the deadline
   - who to contact for questions

## Step 3 — Confirm access (before launch)

For each country:
- Confirm focal points have:
  - the correct assignment role (data entry)
  - the correct country access

If you expect supporting documents:
- Confirm the right users have a role that allows uploads (see [Supporting documents (admin)](supporting-documents.md)).

## Step 4 — Monitor progress during collection

During the open period, monitor:
- not started
- in progress
- submitted
- overdue

What to do when progress is low:
- send reminders (short + specific)
- clarify confusing fields (labels/help text)
- extend deadline if your workflow allows it

## Step 5 — Review and approve submissions

1. Open the assignment.
2. Review submissions for:
   - missing values that should exist
   - outliers (values far outside expected range)
   - required documents (if applicable)
3. Approve submissions that meet the minimum quality bar.
4. Reopen/return submissions that need correction (with a short explanation of what to fix).

Tip: Use [Submission statuses and what you can do](../common/submission-statuses-and-permissions.md) to explain why "Edit/Submit" is locked/unlocked.

## Step 6 — Export data for reporting

1. Navigate to the entry form page for each assignment/country you want to export:
   - Open the assignment from **Manage Assignments**.
   - Click on a country/entity to open the entry form.
2. Use the export options available on the entry form page:
   - **Export Excel Template** (if enabled): Downloads an Excel file with form structure and data.
   - **Export PDF** (if enabled): Downloads a PDF version of the form with current data.
3. Save exported files with a consistent naming convention:
   - `2026-Q1_TemplateName_CountryName.xlsx` (for individual country exports)
   - Note: Exports are per country/entity, not for all countries at once from the assignment list.
4. If you need repeatable analysis, keep IDs/codes in the export (don't delete them).

For interpretation guidance, see [Exports: how to interpret files](exports-how-to-interpret.md).

## Step 7 — Close and document decisions

At the end of the cycle:
- Record any mid-cycle changes (deadline extensions, template updates).
- Record your rule for duplicates (especially for public submissions).
- Capture known issues to improve next cycle.

## Common problems

- **A country can't see the assignment**: roles and country access are missing.
- **Users can't submit**: too many required fields or strict validation; add help text and reduce required.
- **Template changes caused confusion**: avoid major edits mid-cycle; roll out via a new assignment.
- **Export doesn't match expectations**: confirm you exported the correct assignment and template version.

## Related

- [Assignment lifecycle](assignment-lifecycle.md)
- [Manage assignments](manage-assignments.md)
- [Review and approve submissions](review-approve-submissions.md)
- [Export and download data](export-download-data.md)
