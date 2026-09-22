# UPR Tools

System Managers use **UPR Tools** (`/admin/upr-tools`) to run data sync and imputation, import Excel workbooks, and upload guidance documents.

## Tabs

| Tab | Purpose |
|---|---|
| Preview / Imputation Methods | Core data-sync and imputation for UPR planning and reporting templates |
| Excel Import | Import `UPR Master.xlsx` (sheet "UPR Data") into planning and reporting templates |
| Guidance | Upload official UPR guidance PDFs, Word, or Markdown files for later AI import |

## Excel Import

Allowed rounds:

- Planning: P23–P26 (templates 24 and 22)
- Annual reports: AR21–AR25 (templates 33 and 23)
- Mid-year: MYR23–MYR25 (template 33)

Use **Dry run** to preview row counts and warnings before writing to the database.

## Guidance

Upload source guidance here. Files are stored as reusable **Guidance Documents** (`owner_key=upr`). Import them from **Admin → AI System → Knowledge Base → Upload/Import → Guidance Documents** so the chatbot can cite them.

## Related

- [Overview](overview.md)
- [Guidance documents](guidance.md)
