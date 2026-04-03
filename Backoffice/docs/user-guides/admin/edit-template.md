# Edit a form template (Form Builder)

Use this guide when you need to update an existing template (the questions and sections focal points will fill in).

## Before you start

- You need **Admin** access with template permissions.
- Confirm whether the template is already in use (has active assignments).
- Decide what kind of change you need:
  - **Safe**: label/help text fixes, adding optional fields, reordering sections.
  - **Risky**: changing field types, changing required rules, deleting fields (can break consistency across countries).

## Open the template

1. Open **Admin Panel** → **Form & Data Management** → **Manage Templates**.
2. Find the template and open it.
3. If the system shows multiple versions (draft/published), start from the **latest draft** (or create a new draft version if required).

## Common edits (step-by-step)

### Add a new section

1. Click **Add section**.
2. Give the section a clear name (this becomes a navigation item for focal points).
3. Save.

### Add a new field

1. Open the section where you want the field.
2. Click **Add field**.
3. Choose the field type (text/number/date/dropdown, etc.).
4. Set the **label** (exactly what users will see).
5. If available, add **help text** (one short sentence).
6. Set **Required** only when truly needed.
7. Save.

### Update a label or help text

1. Open the field.
2. Change the label/help text to match the meaning you want.
3. Save.

### Reorder sections or fields

1. Use the drag handle (or move controls) to reorder.
2. Save.

## Field types (what to choose)

- **Text**: names, notes, short explanations.
- **Number**: counts and quantities. Prefer number when you need totals or validation.
- **Date**: dates (not free text).
- **Dropdown / single choice**: when answers must be consistent across countries.
- **Multi-select**: when multiple answers may apply.
- **Matrix / table** (if available): repeated values across categories. Use when users must enter the same measure for multiple rows.

## Validation and required fields

- Mark a field **required** only when it must be present for a submission to be usable.
- If users often get blocked at **Submit**, reduce required fields or add clearer instructions.
- When you change validation rules, test the impact with a small assignment first.

## Indicator Bank linking (when applicable)

If your workflow uses the **Indicator bank**:

- Link a field to an indicator when you need standardized definitions and consistent reporting.
- Keep the field label user-friendly, even if the indicator name is technical.
- Avoid linking multiple different questions to the same indicator unless they truly represent the same measure.

## Publishing and testing

1. Save your draft changes.
2. If your system requires publishing, **publish** the new version.
3. Create a small test assignment (one country) and complete it yourself.
4. Fix any confusing labels and remove unnecessary required fields.

## Common problems

- **My changes don’t show up for focal points**: the template version may not be published or the assignment may be using an older published version.
- **Users can’t submit after my change**: a required field or new validation is blocking submission—test the form as a focal point.
- **Data looks inconsistent across countries**: avoid changing field types/meaning mid-collection; create a new template/version and communicate the change.

## Related

- [Create form template](create-template.md)
- [Create new assignment](create-assignment.md)
- [Manage assignments](manage-assignments.md)
- [Submit form data (Focal point)](../focal-point/submit-data.md)
- [Form Builder (advanced)](form-builder-advanced.md)
