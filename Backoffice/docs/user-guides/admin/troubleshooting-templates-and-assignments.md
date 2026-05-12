# Troubleshooting templates and assignments (admin)

Use this guide when something looks wrong with templates/assignments (wrong version, missing countries, blocked submissions, confusing exports).

## Template problems

### “My template changes don’t show up for focal points”

Common causes:
- you edited a draft but did not publish (if publishing exists in your setup)
- the assignment is tied to an older template/version

What to do:
- Confirm which template/version the assignment uses.
- For major changes, create a new assignment and communicate the change.

### “Users can’t submit after we updated the template”

Common causes:
- new required fields were added
- validation rules are too strict
- a matrix/table has required cells

What to do:
- Test as a focal point on a small assignment.
- Reduce required fields and add clearer help text.

See: [Form Builder (advanced)](form-builder-advanced.md)

## Assignment problems

### “A country is missing from the assignment”

Common causes:
- the country was not selected during creation
- the country was removed later
- the country is filtered out by status/view settings

What to do:
- Check assignment settings and add the country if needed.
- Confirm focal points for that country have country access.

### “A focal point says they can’t see the assignment”

Most common reasons:
- missing assignment role (data entry/view)
- missing country access
- the assignment is not active for that period

First checks:
- confirm the user’s roles (see [User Roles and Permissions](user-roles.md))
- confirm the user’s country access
- confirm the assignment includes that country

### “We need to correct data after submission”

Typical approaches:
- Reopen/return the submission (if your workflow supports it)
- Ask the focal point to correct and re-submit

See: [Review and approve submissions](review-approve-submissions.md) and [Submission statuses and what you can do](../common/submission-statuses-and-permissions.md)

## Export problems

### “Export is missing data or has unexpected columns”

Common causes:
- exporting the wrong assignment/period
- template version changed
- export filter excluded certain statuses/countries

See: [Exports: how to interpret files](exports-how-to-interpret.md)

## Related

- [Assignment lifecycle](assignment-lifecycle.md)
- [Manage assignments](manage-assignments.md)
- [Form Builder (advanced)](form-builder-advanced.md)
