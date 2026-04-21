# Form Builder (advanced): field types, validation, and safe changes

Use this guide when you need to design templates that are consistent across countries and easy to submit.

## Before you start

- You need **Admin** access with template permissions.
- If the template is already used in active assignments, prefer **small, safe changes** and test carefully.

## How to choose the right field type

### Text

Use for names, short descriptions, and “explain why” answers.

Good examples:
- “Describe the main challenge (1–2 sentences)”

Avoid:
- Using text for numbers (“10”) or dates (“Jan 2026”) when you can use a structured field.

### Number

Use for counts, totals, and quantities.

Good examples:
- “Total volunteers (number)”
- “Budget (local currency)”

Tips:
- Decide upfront whether you accept decimals.
- Be explicit about units in the label (e.g. “(people)”, “(CHF)”).

### Date

Use when the value is a date, not a comment.

Tips:
- If you need a period (start/end), use two date fields with clear labels.

### Single choice (dropdown / radio)

Use when answers must be consistent across countries.

Tips:
- Keep option labels short.
- Avoid overlapping meanings (e.g. “Partially” vs “Somewhat”).

### Multi-select

Use when multiple options may apply.

Tips:
- Add an “Other (specify)” option only if you truly need it, and pair it with a text field.

### Matrix / table (repeating rows)

Use when the same measure is collected across multiple categories (rows).

Good example:
- Rows: “Women”, “Men”, “Girls”, “Boys”
- Columns: “People reached”

Best practices:
- Keep the matrix small (users struggle with very wide tables).
- Ensure each row label is unambiguous.
- Prefer number fields inside matrices when you expect totals and validation.

## Validation and required fields (what blocks submission)

### Required fields

Make a field **required** only when you cannot accept a submission without it.

If users frequently get stuck at **Submit**:
- Reduce required fields, especially in long forms.
- Add help text to explain what “good enough” looks like.

### Common validation rules (when available)

If your Form Builder supports them, use validation rules to prevent common errors:
- Minimum/maximum number (e.g. “must be ≥ 0”)
- Allowed formats (e.g. year)
- Required matrix cells (only when necessary)

Tip: If validation rules are strict, users will need clearer labels and examples.

## Conditional logic (when to use it)

If your Form Builder supports conditional display (show/hide fields):
- Use it to reduce clutter (ask follow-up questions only when needed).
- Avoid deep branching trees; they are hard to test and easy to break.

Always add help text on the “parent” question so users understand why follow-ups appear.

## Template versioning and “safe vs risky” changes

### Safe changes (usually OK during a live collection)

- Fix typos and wording in labels/help text
- Reorder sections/fields (when it does not change meaning)
- Add a new optional field

### Risky changes (can break comparisons or confuse users)

- Change a field type (text → number, dropdown → multi-select)
- Change meaning of a question but keep the same label
- Delete fields (can remove historical context)
- Change required rules mid-collection

Recommended approach for risky changes:
1. Create a new draft/version (if supported).
2. Test on a small assignment (one country).
3. Roll out via a new assignment (preferred) and communicate the change.

## Indicator Bank linking (practical rules)

Link a question to an indicator when you need:
- standardized definitions
- consistent reporting across countries

Avoid:
- Linking different questions to the same indicator unless they truly represent the same measure.
- Forcing technical indicator names into user-facing labels (keep labels human-readable).

## Test plan (quick checklist)

Before publishing/using a template:
- Complete the form yourself as a focal point.
- Confirm required fields are reasonable.
- Try submitting with intentional mistakes (missing required, wrong formats).
- Export a test submission and confirm the data columns make sense.

## Common problems

- **Focal points can’t submit**: too many required fields or strict validation; add help text and reduce required.
- **Data is inconsistent across countries**: dropdown options are unclear; tighten definitions and link to indicators where appropriate.
- **The wrong template version is used**: assignments may be tied to older versions; create a new assignment when rolling out major changes.

## Related

- [Edit a template (Form Builder)](edit-template.md)
- [Create a form template](create-template.md)
- [Assignment lifecycle](assignment-lifecycle.md)
- [Troubleshooting (Focal point)](../focal-point/troubleshooting.md)
