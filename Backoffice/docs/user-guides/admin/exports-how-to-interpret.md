# Exports: how to interpret files (admin)

Use this guide when you downloaded an export (CSV/Excel) and want to understand what the columns mean and how to avoid common mistakes.

## Before you start

- Export content depends on the template and your workflow.
- If your export supports “filters” (status, country, period), write down what you selected so you can reproduce it.

## What you usually get in an export

Most exports include a mix of:

- **Metadata columns** (context)
  - assignment name / assignment id
  - country / organization
  - submission status
  - submitted/updated timestamps
  - submitted by (user)
- **Answer columns** (your template fields)
  - one column per field, or multiple columns for complex fields (like matrices)
- **Codes/IDs**
  - internal ids, indicator codes, or question ids that help join datasets reliably

## How matrix/table fields usually export

Matrix answers often become multiple columns, for example:
- one column per row (if it’s a single numeric column), or
- row × column combinations (if it’s a multi-column matrix)

Tip: Keep the column headers as-is until you finish cleaning your dataset; renaming too early makes it hard to compare across periods.

## How to avoid “wrong export” mistakes

### Confirm you exported the correct scope

Before analysis, confirm:
- the assignment name and period are correct
- the country list matches your intended scope
- the status filter matches your intent (e.g. only “Approved”)

### Watch out for template version changes

If template versions changed between periods, exports may differ:
- new columns appear
- old columns disappear
- meanings change (worst case)

Recommendation:
- For major changes, treat it as a new reporting instrument and document the change clearly.

## Recommended cleaning approach (simple and safe)

1. **Keep a raw copy** of the export (do not edit it).
2. Make a working copy and add your cleaning steps there.
3. Keep IDs/codes:
   - they help with merges and deduplication
4. If you need a single “country-period” row, decide how you will handle:
   - multiple submissions
   - reopened/resubmitted entries

## Common problems

- **Export is missing a country**: the country may not be included in the assignment, has not submitted, or you need to export it separately from the entry form page.
- **Numbers don’t match the form**: check template version/period and whether rounding or formatting is applied.
- **Duplicate rows**: you exported multiple statuses (draft + submitted + approved) or multiple submissions exist.
- **Export takes too long**: export smaller scopes (one assignment at a time).

## Related

- [Export and download data](export-download-data.md)
- [Run a reporting cycle](run-a-reporting-cycle.md)
- [Submission statuses and what you can do](../common/submission-statuses-and-permissions.md)
